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

    # fetch restaurant doc from DB
    restaurant_doc = db.restaurants.find_one({"key": restaurant_key})
    if not restaurant_doc:
        # fallback to your earlier JSON approach if needed
        restaurant_info = all_restaurants.get(restaurant_key, {}) if 'all_restaurants' in globals() else {}
        display_name = restaurant_key.replace("_", " ").title()
    else:
        restaurant_info = restaurant_doc.get("raw", {})
        display_name = restaurant_doc.get("display_name", restaurant_doc.get("name", restaurant_key))

    # Build a compact menu for the prompt — don't send huge menus (limit to 40 items)
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
    # If menu very large, we send top categories or first N items only
    if len(menu_list) > 60:
        menu_for_prompt = menu_list[:60]
    else:
        menu_for_prompt = menu_list

    # Load session-specific recent messages for memory
    coll = db[f"{restaurant_key}_chat"]
    recent = list(coll.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", -1).limit(8))
    recent.reverse()  # chronological order

    # Build system prompt — instruct model to *act like a waiter*
    brand_voice = restaurant_doc.get("raw", {}).get("brand_voice", {})
    brand_tone = brand_voice.get("tone", "friendly and professional")
    greeting = brand_voice.get("greeting_style", f"Hi! Welcome to {display_name} — how can I help you today?")

    system_prompt = f"""
You are a virtual WAITER for the restaurant '{display_name}'. Act like a trained, friendly waiter with {brand_tone} tone.
You have access to the restaurant's menu below. Always confirm items, sizes, quantities, pickup/delivery choice, and final price before placing an order.
You MUST ask for any missing required info (size, pickup/delivery, address for delivery, name for reservation).
Use upsells when appropriate (suggest side dishes or drinks), but do so naturally.

Restaurant info (for reference):
Name: {display_name}
Policies: {json.dumps(restaurant_doc.get('raw', {}).get('policies', {}), indent=2)}
Deals: {json.dumps(restaurant_doc.get('raw', {}).get('deals', []), indent=2)}
Menu (sample items): {json.dumps(menu_for_prompt, indent=2)}

Important rules:
1) Be conversational and human-like.
2) NEVER invent menu items or prices. If uncertain, ask clarifying questions.
3) When an order is fully confirmed, output the order JSON EXACTLY in this format:

---ORDER_JSON_START---
{{
  "order": {{
     ...
  }}
}}
---ORDER_JSON_END---

RULES:
- The markers MUST be alone on their own lines.
- No text before or after the markers on the same line.
- No extra spaces.
- Human message should come BEFORE the JSON block, not after.

   The JSON should look like: {{ "order": {{ "items":[{{"item_id":"...","name":"...","qty":1,"price":9.99}}], "total": XX.XX, "pickup_or_delivery":"pickup", "customer_name":"...", "notes": "..." }} }}
4) If the user asks unrelated questions, reply: "I can help with orders, reservations, and menu questions for this restaurant."
5) Keep responses concise; ask one question at a time if clarification is needed.

Current local time: {now}
{greeting}
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


# -------------------- Notes for Developers --------------------
# 1. Supports both chat and order modes (switchable via dropdown).
# 2. Uses MongoDB to store chat/order history per restaurant.
# 3. Data is loaded from /data/*.json for each restaurant.
# 4. Added geopy-based nearest store logic (lat/lon -> closest match).
# 5. Fully UTF-8 safe (fixes Windows cp1252 decode issue).
# 6. Works with updated index.html geolocation button.
# 7. Automatically detects nested JSONs (like {"Dominos": {...}}).
# 8. Ready for production testing.
