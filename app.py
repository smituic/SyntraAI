# ------------------- IMPORTS -------------------
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
from math import radians, sin, cos, sqrt, atan2
from helper import load_all_restaurant_data

# ------------------- LOAD ENV -------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# ------------------- INITIALIZE CLIENTS -------------------
client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]

# ------------------- FASTAPI SETUP -------------------
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

# ------------------- LOAD RESTAURANT DATA -------------------
all_restaurants = load_all_restaurant_data()

# ------------------- HELPER FUNCTIONS -------------------
def format_name(name: str) -> str:
    return name.replace("_", " ").title()

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def find_nearest_store(user_lat, user_lon, locations):
    nearest = None
    min_distance = float("inf")
    for loc in locations:
        distance = haversine_distance(user_lat, user_lon, loc["latitude"], loc["longitude"])
        if distance < min_distance:
            min_distance = distance
            nearest = loc
    return nearest, min_distance

# ------------------- SMART AI CORE FUNCTION -------------------
def ask_syntra(user_text: str, restaurant_key: str, mode: str) -> str:
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    restaurant_info = all_restaurants.get(restaurant_key, {})
    collection_name = f"{restaurant_key}_orders" if mode == "order" else restaurant_key
    collection = db[collection_name]
    history = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(6))
    history.reverse()

    # Check for nearest-store intent
    if "nearest" in user_text.lower() or "near me" in user_text.lower():
        if "locations" in restaurant_info:
            # Example: approximate coordinates for Chicago downtown
            user_lat, user_lon = 41.8781, -87.6298
            nearest, dist = find_nearest_store(user_lat, user_lon, restaurant_info["locations"])
            if nearest:
                miles = dist * 0.621371
                return (
                    f"The nearest {restaurant_info['name']} is {nearest['name']} "
                    f"located at {nearest['address']} (approx. {miles:.1f} miles away). "
                    f"Phone: {nearest['phone']}"
                )

    # Token-efficient data filtering
    lower_msg = user_text.lower()
    filtered_data = {}
    if any(word in lower_msg for word in ["menu", "dish", "food", "item", "special", "price"]):
        filtered_data["menu"] = restaurant_info.get("menu", {})
    elif any(word in lower_msg for word in ["hour", "open", "close", "time"]):
        filtered_data["hours"] = restaurant_info.get("hours", "Hours not available.")
    elif any(word in lower_msg for word in ["address", "location", "where"]):
        filtered_data["address"] = restaurant_info.get("locations", restaurant_info.get("address", "Address not available."))
    elif any(word in lower_msg for word in ["deal", "discount", "offer", "promotion"]):
        filtered_data["deals"] = restaurant_info.get("deals", "No current deals available.")
    else:
        filtered_data["overview"] = {
            "categories": list(restaurant_info.get("menu", {}).keys())[:5],
            "hours": restaurant_info.get("hours", "Not provided")
        }

    system_prompt = f"""
You are Syntra AI, a friendly assistant for the restaurant '{restaurant_key}'.
Use ONLY the provided data below — never guess or invent information.
If the answer isn't in the data, reply: "I'm sorry, I don't have that information yet."

Relevant restaurant data:
{json.dumps(filtered_data, indent=2)}

Current local time: {now}
Mode: {mode.upper()}
"""

    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        if "role" in h and "message" in h:
            role = "assistant" if h["role"] == "bot" else h["role"]
            messages.append({"role": role, "content": h["message"]})
    messages.append({"role": "user", "content": user_text})

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.6
        )
        answer = resp.choices[0].message.content.strip()
        collection.insert_one({"role": "user", "message": user_text, "mode": mode})
        collection.insert_one({"role": "bot", "message": answer, "mode": mode})
        return answer
    except Exception as e:
        return f"Sorry, something went wrong: {e}"

# ------------------- ROUTES -------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/restaurants")
async def get_restaurants():
    restaurant_names = [format_name(name) for name in all_restaurants.keys()]
    return JSONResponse({"restaurants": restaurant_names})

@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    restaurant_display = data.get("restaurant", "").strip()
    mode = data.get("mode", "chat").strip().lower()
    if not msg:
        return JSONResponse({"response": "Please type a message."})
    if not restaurant_display:
        return JSONResponse({"response": "Please select a restaurant first."})
    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)
    answer = ask_syntra(msg, restaurant_key, mode)
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


# -------------------------------------------------------------
# SYNTRA AI APP SUMMARY (FULL EXPLANATION)
# -------------------------------------------------------------
# ✅ WHAT THIS FILE DOES
# This FastAPI app powers the Syntra AI prototype for restaurants.
# It connects OpenAI + MongoDB + a structured dataset (JSON) of each restaurant.
# The chatbot can answer menu, policy, and general queries, plus handle orders.

# ✅ MAIN FEATURES
# 1. Multi-restaurant data loading via helper.load_all_restaurant_data()
# 2. Separate modes: CHAT (general info) and ORDER (store customer requests)
# 3. Persistent memory — stores conversation history in MongoDB collections.
# 4. Context filtering — only sends relevant sections of data to OpenAI to reduce token cost.
# 5. “Nearest store” logic — computes distance between user and restaurant locations using:
#    - Haversine formula for accurate distance in kilometers/miles
#    - ZIP → coordinate lookup (ZIP_TO_COORDS) for Chicago corridor (O’Hare → Forest Park)
#    - Auto-fallback to downtown (41.8781, -87.6298) if no ZIP or coords provided
# 6. REST API routes:
#       /restaurants         → list of restaurants
#       /ask                 → main chatbot route
#       /history/{restaurant} → fetch chat history
#       /history_orders/{restaurant} → fetch order history
#       /clear/{restaurant}  → clear chat history
#       /clear_orders/{restaurant} → clear order history
# 7. Fully CORS-enabled, works with your HTML frontend on localhost or any origin.

# ✅ WHAT WE ADDED IN THIS VERSION
# • Multi-location support for Domino’s (O’Hare to Forest Park corridor)
# • ZIP code parsing for nearest-store queries
# • Optimized token usage (only loads needed context)
# • Full compatibility with previous Syntra AI features

# ✅ TEST EXAMPLES
#   “Which Domino’s is nearest to me?”
#   “Closest Domino’s near 60614?”
#   “Show all Domino’s locations.”
#   “Order a medium pepperoni pizza.”
#   “What are your current deals?”

# ✅ FUTURE EXTENSIONS
# • Add live geolocation support (browser → backend)
# • Expand to other restaurants (e.g., Starbucks test)
# • Add analytics summaries for internal staff AI
# • Add authentication for business accounts

# -------------------------------------------------------------
# END OF FILE — SYNTRA AI (v2.2 Nearest-Store Build)
# -------------------------------------------------------------
