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

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# Initialize OpenAI and MongoDB
client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]

# FastAPI setup
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

# Load restaurant data
all_restaurants = load_all_restaurant_data()

def format_name(name: str) -> str:
    return name.replace("_", " ").title()

def ask_syntra(user_text: str, restaurant_key: str, mode: str) -> str:
    """Core LLM call; mode = 'chat' or 'order'."""
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    restaurant_info = all_restaurants.get(restaurant_key, {})

    if mode == "chat":
        prompt = f"""
You are Syntra AI, a friendly assistant for the restaurant '{restaurant_key}'.

RELEVANCE RULES:
- Only answer questions relevant to THIS restaurant (menu, hours, pricing, address, policies, deals).
- If irrelevant (e.g., biology, random facts, other restaurants), reply: 
  "I can help with questions about this restaurant. Please ask about our menu, hours, location, pricing, or services."

Restaurant data:
{json.dumps(restaurant_info, indent=2)}

Current local time: {now}

User: {user_text}
AI:
"""
    else:
        prompt = f"""
You are Syntra OrderBot for '{restaurant_key}'. Your job is to help place food orders or table reservations.

BEHAVIOR:
- Ask for missing details (item, size, quantity, special instructions, pickup/delivery/dine-in, time).
- Keep questions short and friendly.
- If user confirms, output a clean final "Order Summary" with items, qty, pickup/delivery time, and name/phone if provided.
- Stay strictly on this restaurant. If off-topic, respond with:
  "I can help place an order or a reservation for this restaurant."

Restaurant data:
{json.dumps(restaurant_info, indent=2)}

Current local time: {now}

User: {user_text}
AI:
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Sorry, something went wrong: {e}"

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
    if mode not in ("chat", "order"):
        mode = "chat"

    # Map display to key (e.g., "Bacci Pizza" -> "Bacci_Pizza")
    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)

    answer = ask_syntra(msg, restaurant_key, mode)

    # Save chat/order in Mongo (separate collection for orders)
    collection_name = f"{restaurant_key}_orders" if mode == "order" else restaurant_key
    collection = db[collection_name]
    collection.insert_one({"role": "user", "message": msg, "mode": mode})
    collection.insert_one({"role": "bot", "message": answer, "mode": mode})

    return JSONResponse({"response": answer})

@app.get("/history/{restaurant_key}")
async def get_chat_history(restaurant_key: str):
    # Returns chat history for the chat collection (not orders)
    collection = db[restaurant_key]
    chats = list(collection.find({}, {"_id": 0}))
    return JSONResponse({"history": chats})

@app.get("/history_orders/{restaurant_key}")
async def get_order_history(restaurant_key: str):
    # Returns order history for the order collection
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
