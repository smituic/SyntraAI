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

# Function to convert file-style names to display names
def format_name(name):
    return name.replace("_", " ").title()

# 💡 AI function with restaurant-only restriction
def ask_syntra(user_text: str, restaurant_key: str) -> str:
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    time_note = f"The current local date and time in Chicago is {now}."

    restaurant_info = all_restaurants.get(restaurant_key, {})

    prompt = f"""
You are Syntra AI, a friendly AI assistant that answers ONLY questions related to the restaurant '{restaurant_key}'.

Here is verified information about this restaurant:
{json.dumps(restaurant_info, indent=2)}

Your rules:
- You must ONLY answer questions related to {restaurant_key}, its food, pricing, hours, location, offers, delivery, or similar topics.
- If the user asks anything unrelated to restaurants, food, or dining (e.g. science, math, jokes, philosophy, politics, etc.), reply with:
  "I'm sorry, but I can only answer questions related to this restaurant or its menu. Could you please ask something about {restaurant_key}?"
- Always keep a polite, professional restaurant tone.
- Never generate random or unrelated answers.
- Always use short, clear, factual sentences.
- {time_note}

User: {user_text}
AI:
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Sorry, something went wrong: {e}"

# Home route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Fetch restaurant names
@app.get("/restaurants")
async def get_restaurants():
    restaurant_names = [format_name(name) for name in all_restaurants.keys()]
    return JSONResponse({"restaurants": restaurant_names})

# Handle user messages
@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    restaurant_display = data.get("restaurant", "").strip()

    if not msg:
        return JSONResponse({"response": "Please type a message."})
    if not restaurant_display:
        return JSONResponse({"response": "Please select a restaurant first."})

    # Match display name (e.g., 'Bacci Pizza') back to file key
    key_map = {format_name(name): name for name in all_restaurants.keys()}
    restaurant_key = key_map.get(restaurant_display, restaurant_display)

    # Generate AI response
    answer = ask_syntra(msg, restaurant_key)

    # Save chat to MongoDB (separate collection per restaurant)
    collection = db[restaurant_key]
    collection.insert_one({"role": "user", "message": msg})
    collection.insert_one({"role": "bot", "message": answer})

    return JSONResponse({"response": answer})

# Optional: Fetch chat history for a restaurant
@app.get("/history/{restaurant_name}")
async def get_chat_history(restaurant_name: str):
    collection = db[restaurant_name]
    chats = list(collection.find({}, {"_id": 0}))
    return JSONResponse({"history": chats})
