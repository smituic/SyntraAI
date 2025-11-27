from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import json
from openai import OpenAI
from datetime import datetime
import pytz
from pymongo import MongoClient
from helper import load_all_restaurant_data
from geopy.distance import geodesic
from fastapi import Request
from datetime import datetime, timezone

# -------------------- Setup --------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -------------------- Load Restaurant Data --------------------
all_restaurants = load_all_restaurant_data()

def format_name(name: str) -> str:
    return name.replace("_", " ").title()


# -------------------- Nearest Store Finder --------------------
def find_nearest_store(lat, lon, locations):
    """Find nearest store given user latitude and longitude."""
    try:
        user_loc = (float(lat), float(lon))
        nearest = None
        nearest_dist = float("inf")

        for loc in locations:
            store_coords = (loc["latitude"], loc["longitude"])
            dist = geodesic(user_loc, store_coords).miles
            if dist < nearest_dist:
                nearest = loc
                nearest_dist = dist

        if nearest:
            return f"The nearest store is {nearest['name']} located at {nearest['address']} ({nearest_dist:.1f} miles away)."
        else:
            return "Sorry, I couldn’t find any nearby stores."
    except Exception as e:
        return f"Error determining nearest store: {e}"


# -------------------- Main AI Logic --------------------
# Updated ask_syntra to accept session_id and use full waiter prompt
def ask_syntra(user_text: str, restaurant_key: str, mode: str, session_id: str) -> str:
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")

    # Fetch restaurant doc
    restaurant_doc = db.restaurants.find_one({"key": restaurant_key})
    display_name = restaurant_doc.get("display_name", restaurant_key.replace("_", " ").title())
    restaurant_info = restaurant_doc.get("raw", {})

    # -------------------- Load Menu --------------------
    menu_cursor = db.menus.find({"restaurant_key": restaurant_key, "availability": True})
    menu_list = []
    for m in menu_cursor:
        menu_list.append({
            "item_id": m.get("item_id"),
            "name": m.get("name"),
            "category": m.get("category"),
            "price": m.get("price"),
            "description": m.get("description", "")
        })

    # Menu cutoff to avoid huge context
    menu_for_prompt = menu_list[:60]

    # -------------------- Load Session History --------------------
    coll = db[f"{restaurant_key}_chat"]
    recent = list(coll.find({"session_id": session_id}, {"_id": 0})
                  .sort("timestamp", -1).limit(8))
    recent.reverse()

    # -------------------- ORDER MODE STICKINESS --------------------
    # If the bot was already handling an order, stay in order mode
    for h in reversed(recent):
        if h["role"] == "bot":
            msg = h["message"].lower()
            # These phrases indicate we are mid-order
            order_indicators = [
                "how many", "quantity", "pickup", "delivery",
                "would this be", "name for the order",
                "anything else you want", "anything else you'd like",
                "you wanna add", "you want to add", "add anything"
            ]
            if any(key in msg for key in order_indicators):
                mode = "order"
                break


   # -------------------- Build System Prompt Based on Mode --------------------
    if mode == "chat":
        system_prompt = f"""
You are a super friendly, casual, human-like waiter at {display_name}.
You talk like a real waiter at a relaxed restaurant — fun, warm, a little playful, NEVER formal.

VIBE RULES:
- Say “hey!” or “hey there!” instead of “hello”
- Use natural speech (“oh nice!”, “haha yeah same”, “for sure!”, “got you!”)
- Light emoji allowed 😊🔥🍕 (max 1 per message)
- Small talk is encouraged (“how’s your day going?”, “my day’s been pretty chill haha”)
- Sound HUMAN, not professional or robotic.

WHAT YOU CAN DO:
- answer greetings (“how are you?”, “sup?”, “how’s your day?”)
- chat casually
- recommend items
- explain menu categories
- tell user what’s popular

WHAT YOU CANNOT DO (in chat mode):
- start an order unless the user clearly wants to order
- ask for pickup/delivery info
- generate order JSON

MENU REFERENCE (don’t list everything unless asked):
{json.dumps(menu_for_prompt, indent=2)}

Policies: {json.dumps(restaurant_doc.get('raw', {}).get('policies', {}), indent=2)}
Deals: {json.dumps(restaurant_doc.get('raw', {}).get('deals', []), indent=2)}

Keep messages short, warm, and super friendly.
    """

    else:  # ORDER MODE
        system_prompt = f"""
You are now in ORDER MODE for {display_name}.
The user is placing an order. Stay friendly and casual, but ensure accuracy.

ORDER FLOW RULES (follow them strictly):

1. Confirm the requested item
2. Always Confirm size/flavor 
3. Confirm quantity
After the user confirms they do NOT want anything else, your next message MUST ask:
“Would this be for pickup or delivery?”  
Never end the conversation before asking this.
4. Ask: "Would this be for pickup or delivery?"
5. If it's for delivery, Always ask for address.
6. Ask: "And can I get a name for the order?"
7. Summarize the order clearly
8. THEN output the order JSON ONLY between these markers:



When you output the final JSON, it MUST match this structure EXACTLY:

---ORDER_JSON_START---
{{
  "order": {{
    "items": [
      {{
        "item_id": "string",
        "name": "string",
        "qty": 1,
        "price": 0
      }}
    ],
    "total": 0,
    "pickup_or_delivery": "pickup or delivery",
    "customer_name": "string",
    "address": "string (required if delivery)",
    "notes": ""
  }}
}}
---ORDER_JSON_END---

IMPORTANT:
• Keys MUST be spelled exactly like this: item_id, name, qty, price, total, pickup_or_delivery, customer_name, address, notes
• Do NOT invent new keys.
• Do NOT rename keys.
• Do NOT wrap numbers as strings.
• Do NOT output JSON until ALL information is collected.


Menu reference:
{json.dumps(menu_for_prompt, indent=2)}
"""



    # Build message list: system + session history + user
    messages = [{"role": "system", "content": system_prompt}]
    for h in recent:
        # h contains {"role":"user"|"bot", "message":..., "timestamp":..., "session_id":...}
        role = "assistant" if h.get("role") == "bot" else "user"
        messages.append({"role": role, "content": h.get("message")})
    messages.append({"role": "user", "content": user_text})

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Sorry, something went wrong: {e}"


# -------------------- Routes --------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/restaurants")
async def get_restaurants():
    """Return restaurant names for dropdown — works for both nested and flat JSONs."""
    restaurant_names = []
    for name, data in all_restaurants.items():
        if "Dominos" in data:
            restaurant_names.append("Dominos Pizza")
        else:
            restaurant_names.append(format_name(name))
    return JSONResponse({"restaurants": restaurant_names})




@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    restaurant_key = data.get("restaurant_key") or data.get("restaurant")  # widget will send restaurant_key
    mode = data.get("mode", "chat").strip().lower()
    session_id = data.get("session_id") or make_session_id()

    if not msg:
        return JSONResponse({"response": "Please type a message.", "session_id": session_id})
    if not restaurant_key:
        return JSONResponse({"response": "Missing restaurant_key.", "session_id": session_id})

    # Ensure restaurant exists
    restaurant_doc = db.restaurants.find_one({"key": restaurant_key})
    if not restaurant_doc:
        return JSONResponse({"response": "Unknown restaurant_key.", "session_id": session_id})

    # Handle nearest / location shortcuts if you want
    lat = data.get("latitude")
    lon = data.get("longitude")
    if msg.lower() in ["nearest", "closest", "near me"] and lat and lon:
        locations = restaurant_doc.get("raw", {}).get("locations", [])
        answer = find_nearest_store(lat, lon, locations)
    else:
         # -------------------- Intent Detection --------------------
        # Look at the last bot message to understand context
        last_bot_msg = None
        try:
            last_chat = coll.find_one(
                {"session_id": session_id, "role": "bot"},
                sort=[("timestamp", -1)]
            )
            if last_chat:
                last_bot_msg = last_chat.get("message", "").lower()
        except:
            pass

        # New rule: if last bot message mentioned a specific item OR suggested adding items → switch to order mode
        order_context_keywords = ["wings", "pizza", "pasta", "sides", "drinks", "add"] 
        confirmation_keywords = ["yes", "yeah", "ok", "sure", "no", "not that", "that's all", "that’s all"]

        if last_bot_msg and any(word in last_bot_msg for word in order_context_keywords):
            if msg.lower() in confirmation_keywords:
                mode = "order"

            else:
                mode = "chat"
        
        # Call AI
        # -------------------- ORDER INTENT DETECTION --------------------
        msg_lower = msg.lower()

        order_keywords = [
            "i want", "i'll take", "i will take", "get me", "give me",
            "order", "buy", "add", "take", "i want to order",
            "i want a", "i want the", "i want pizza", "i want wings"
        ]

        confirmation_words = ["no", "nope", "that's it", "thats it", "no that's all", "no thats all", "ok", "okay"]

        menu_keywords = ["pizza", "wings", "pasta", "salad", "sandwich", "drinks", "sides"]
        size_keywords = ["small", "medium", "large","xl", "extra large", "extra-large",
            "10", "12", "14", "16","10 inch", "12 inch", "14 inch", "16 inch"
        ]

        # 1. If the user explicitly expresses an order
        if any(k in msg_lower for k in order_keywords):
            mode = "order"

        # 2. If user replies after item suggestion like "no", "that's it", etc.
        if any(word == msg_lower for word in confirmation_words):
            mode = "order"

        # 3. If message mentions a menu item
        if any(word in msg_lower for word in menu_keywords):
            mode = "order"

        # 4. If message mentions size of a item
        if msg_lower in size_keywords or any(word in msg_lower for word in size_keywords):
            mode = "order"

        answer = ask_syntra(msg, restaurant_key, mode, session_id)

    # Save messages in DB with session_id & timestamp
    coll = db[f"{restaurant_key}_chat"]
    now_ts = datetime.now(timezone.utc)
    coll.insert_one({"session_id": session_id, "role": "user", "message": msg, "mode": mode, "timestamp": now_ts})
    coll.insert_one({"session_id": session_id, "role": "bot", "message": answer, "mode": mode, "timestamp": datetime.now(timezone.utc)})

    return JSONResponse({"response": answer, "session_id": session_id})



@app.get("/history/{restaurant_key}")
async def get_chat_history(restaurant_key: str):
    collection = db[restaurant_key]
    chats = list(collection.find({}, {"_id": 0}))
    return JSONResponse({"history": chats})


@app.get("/history_orders/{restaurant_key}")
async def get_order_history(restaurant_key: str):
    collection = db[f"{restaurant_key}_orders"]
    items = list(collection.find({}, {"_id": 0}))
    return JSONResponse({"history": items})


@app.delete("/clear/{restaurant_key}")
async def clear_chat_history(restaurant_key: str):
    db[restaurant_key].delete_many({})
    return JSONResponse({"ok": True, "cleared": restaurant_key})


@app.delete("/clear_orders/{restaurant_key}")
async def clear_order_history(restaurant_key: str):
    db[f"{restaurant_key}_orders"].delete_many({})
    return JSONResponse({"ok": True, "cleared": f"{restaurant_key}_orders"})
