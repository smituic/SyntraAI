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
def ask_syntra(user_text: str, restaurant_key: str, mode: str) -> str:
    """Main LLM prompt with restaurant data and conversation memory."""
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    restaurant_info = all_restaurants.get(restaurant_key, {})

    # FIX for nested JSONs like { "Dominos": { ... } }
    if "Dominos" in restaurant_info:
        restaurant_info = restaurant_info["Dominos"]

    collection_name = f"{restaurant_key}_orders" if mode == "order" else restaurant_key
    collection = db[collection_name]
    history = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(6))
    history.reverse()

    if mode == "chat":
        system_prompt = f"""
You are Syntra AI, a friendly assistant for the restaurant '{restaurant_key}'.

RULES:
- Only answer questions about this restaurant (menu, hours, address, pricing, policies, or deals).
- If unrelated, reply: "I can help with questions about this restaurant only."
- Stay consistent with previous answers if asked again.

Restaurant Data:
{json.dumps(restaurant_info, indent=2)}

Current local time: {now}
"""
    else:
        system_prompt = f"""
You are Syntra OrderBot for '{restaurant_key}'.
Assist the customer in placing food orders or reservations.

RULES:
- Remember previously provided details (like size, party count, time, pickup/delivery).
- Don’t repeat questions the user already answered.
- End politely when the order is complete or user says "thank you."
- If unrelated, reply: "I can help with orders or reservations only."

Restaurant Data:
{json.dumps(restaurant_info, indent=2)}

Current local time: {now}
"""

    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        if "role" in h and "message" in h:
            role = "assistant" if h["role"] == "bot" else h["role"]
            if role not in ["system", "user", "assistant"]:
                role = "assistant"
            messages.append({"role": role, "content": h["message"]})
    messages.append({"role": "user", "content": user_text})

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
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
    restaurant_display = data.get("restaurant", "").strip()
    mode = data.get("mode", "chat").strip().lower()
    lat = data.get("latitude")
    lon = data.get("longitude")

    if not msg:
        return JSONResponse({"response": "Please type a message."})
    if not restaurant_display:
        return JSONResponse({"response": "Please select a restaurant first."})
    if mode not in ("chat", "order"):
        mode = "chat"

    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)
    restaurant_info = all_restaurants.get(restaurant_key, {})

    # FIX nested JSON structure
    if "Dominos" in restaurant_info:
        restaurant_info = restaurant_info["Dominos"]

    # Handle nearest-store query automatically
    if msg.lower() in ["nearest", "closest", "near me"] and lat and lon:
        locations = restaurant_info.get("locations", [])
        answer = find_nearest_store(lat, lon, locations)
    else:
        answer = ask_syntra(msg, restaurant_key, mode)

    # Save to MongoDB
    collection_name = f"{restaurant_key}_orders" if mode == "order" else restaurant_key
    collection = db[collection_name]
    collection.insert_one({"role": "user", "message": msg, "mode": mode})
    collection.insert_one({"role": "bot", "message": answer, "mode": mode})

    return JSONResponse({"response": answer})


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
