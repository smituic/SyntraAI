from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Load all restaurant data
all_restaurants = load_all_restaurant_data()

# Convert file-style keys to display names
def format_name(name: str) -> str:
    return name.replace("_", " ").title()

# ---- NEW: fetch recent chat history (addition) ----
def fetch_recent_history(restaurant_key: str, limit: int = 10):
    """
    Returns a list of dicts like {"role": "user"|"bot", "message": "..."} in chronological order.
    Uses $natural to respect insertion order even if old docs don't have timestamps.
    """
    coll = db[restaurant_key]
    docs = list(coll.find({}, {"_id": 0, "role": 1, "message": 1})
                    .sort([("$natural", -1)]).limit(limit))
    docs.reverse()  # oldest -> newest
    return docs

# Build the model messages with system prompt + history + current user message
def build_messages(user_text: str, restaurant_key: str):
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    time_note = f"The current local date and time in Chicago is {now}."

    restaurant_info = all_restaurants.get(restaurant_key, {})

    system_prompt = f"""
You are Syntra AI, a friendly restaurant assistant.

Here is information about the restaurant '{restaurant_key}':
{json.dumps(restaurant_info, indent=2)}

Answer the user's question clearly and professionally.
If the question is not related to this restaurant, politely mention that.

{time_note}
""".strip()

    messages = [{"role": "system", "content": system_prompt}]

    # ---- NEW: include recent history (addition) ----
    history = fetch_recent_history(restaurant_key, limit=10)  # ~ last 10 messages
    for h in history:
        role = "assistant" if h.get("role") == "bot" else "user"
        content = h.get("message", "")
        if content:
            messages.append({"role": role, "content": content})

    # current user turn
    messages.append({"role": "user", "content": user_text})
    return messages

def ask_syntra(user_text: str, restaurant_key: str) -> str:
    try:
        messages = build_messages(user_text, restaurant_key)
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Sorry, something went wrong: {e}"

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/restaurants")
async def get_restaurants():
    names = [format_name(name) for name in all_restaurants.keys()]
    return JSONResponse({"restaurants": names})

# Chat history API (unchanged)
@app.get("/history/{restaurant_name}")
async def get_chat_history(restaurant_name: str):
    collection = db[restaurant_name]
    chats = list(collection.find({}, {"_id": 0}))
    return JSONResponse({"history": chats})

@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    restaurant_display = data.get("restaurant", "").strip()

    if not msg:
        return JSONResponse({"response": "Please type a message."})
    if not restaurant_display:
        return JSONResponse({"response": "Please select a restaurant first."})

    # Map display name back to key
    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)

    # Get model reply (now with memory)
    answer = ask_syntra(msg, restaurant_key)

    # Save both user and bot messages (addition: include timestamp)
    collection = db[restaurant_key]
    now_utc = datetime.utcnow()
    collection.insert_one({"role": "user", "message": msg, "ts": now_utc})
    collection.insert_one({"role": "bot", "message": answer, "ts": now_utc})

    return JSONResponse({"response": answer})
