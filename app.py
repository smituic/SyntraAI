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
    """LLM prompt for both Chat and OrderBot."""
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    restaurant_info = all_restaurants.get(restaurant_key, {})

    if mode == "chat":
        prompt = f"""
You are Syntra AI, a friendly assistant for the restaurant '{restaurant_key}'.

RULES:
- Only answer questions about this restaurant (menu, hours, pricing, address, policies, deals, contact info, or restaurant details).
- If unrelated (e.g., biology, random facts, etc.), politely say:
  "I can help with questions about this restaurant. Please ask about our menu, hours, location, or services."

Restaurant Data:
{json.dumps(restaurant_info, indent=2)}

Current local time: {now}
User: {user_text}
AI:
"""
    else:
        prompt = f"""
You are Syntra OrderBot, a helpful ordering and reservation assistant for the restaurant '{restaurant_key}'.

Your role is to help users place food orders or make table reservations. 
Behave like a polite staff member taking an order at a restaurant.

RULES:
- Always stay on topic (ordering or reservations).
- Understand requests like "I want 2 large pizzas" or "Book a table for 4 at 7pm".
- If details are missing, ask for them (item, size, quantity, pickup/delivery, time, name, or phone).
- Confirm the full order or reservation clearly when enough info is provided.
- ONLY say "I can help place an order..." if the question is completely unrelated (like a science question).
- Keep responses short, friendly, and natural.
- When user says "thank you" or "done", politely close the conversation.

Restaurant Info:
{json.dumps(restaurant_info, indent=2)}

Current local time: {now}

Example Interactions:

User: I'd like to order a pepperoni pizza.
AI: Sure! What size would you like — small, medium, or large?

User: Medium.
AI: Great! Would you like pickup or delivery?

User: Pickup please.
AI: Perfect. Your medium pepperoni pizza will be ready for pickup shortly. Anything else?

User: Book a table for 4 at 8 PM.
AI: Got it! Table for 4 reserved at 8 PM. Can I have a name for the booking?

User: John.
AI: Thank you, John. Your table for 4 is booked for 8 PM tonight. We look forward to serving you!

Now handle this new user message naturally:
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

    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)

    answer = ask_syntra(msg, restaurant_key, mode)

    # Save chat/order in MongoDB (different collections)
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
