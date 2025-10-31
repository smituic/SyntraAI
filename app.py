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

# ------------------- LOAD ENV VARIABLES -------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# ------------------- INITIALIZE OPENAI & MONGODB -------------------
client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]

# ------------------- FASTAPI SETUP -------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ------------------- LOAD RESTAURANT DATA -------------------
all_restaurants = load_all_restaurant_data()

# ------------------- HELPER FUNCTION -------------------
def format_name(name):
    """Convert file-style names to display names"""
    return name.replace("_", " ").title()

# ------------------- AI RESPONSE FUNCTION (with context memory) -------------------
def ask_syntra(user_text: str, restaurant_key: str) -> str:
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    time_note = f"The current local date and time in Chicago is {now}."

    restaurant_info = all_restaurants.get(restaurant_key, {})
    collection = db[restaurant_key]

    # 🧠 Load last 6 messages for context (3 user + 3 bot typically)
    history = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(6))
    history.reverse()  # chronological order

    # Create conversation context
    conversation = ""
    for h in history:
        role = "User" if h["role"] == "user" else "AI"
        conversation += f"{role}: {h['message']}\n"

    prompt = f"""
You are Syntra AI, a friendly and professional restaurant assistant.

Restaurant: '{restaurant_key}'
Information:
{json.dumps(restaurant_info, indent=2)}

Conversation so far:
{conversation}

Now continue the chat naturally.
If the question is unrelated to the restaurant, politely mention that.

{time_note}
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
    """Handles user messages, generates AI responses, and saves to MongoDB"""
    data = await request.json()
    msg = data.get("message", "").strip()
    restaurant_display = data.get("restaurant", "").strip()

    if not msg:
        return JSONResponse({"response": "Please type a message."})
    if not restaurant_display:
        return JSONResponse({"response": "Please select a restaurant first."})

    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)

    # Generate response
    answer = ask_syntra(msg, restaurant_key)

    # Save chat in MongoDB
    try:
        collection = db[restaurant_key]
        collection.insert_one({"role": "user", "message": msg})
        collection.insert_one({"role": "bot", "message": answer})
    except Exception as e:
        print("MongoDB Error:", e)

    return JSONResponse({"response": answer})

@app.get("/history/{restaurant_name}")
async def get_chat_history(restaurant_name: str):
    """Fetch previous chat history for a restaurant"""
    try:
        collection = db[restaurant_name]
        chats = list(collection.find({}, {"_id": 0}))
        return JSONResponse({"history": chats})
    except Exception as e:
        return JSONResponse({"history": [], "error": str(e)})
