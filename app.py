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

def ask_syntra(user_text: str, restaurant_name: str) -> str:
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    time_note = f"The current local date and time in Chicago is {now}."

    restaurant_info = all_restaurants.get(restaurant_name, {})
    prompt = f"""
You are Syntra AI, a friendly restaurant assistant.

Here is information about the restaurant '{restaurant_name}':
{json.dumps(restaurant_info, indent=2)}

Answer the user's question clearly and professionally.
If the question is not related to this restaurant, politely mention that.

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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/restaurants")
async def get_restaurants():
    return JSONResponse({"restaurants": list(all_restaurants.keys())})


@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    restaurant = data.get("restaurant", "").strip()

    if not msg:
        return JSONResponse({"response": "Please type a message."})
    if not restaurant:
        return JSONResponse({"response": "Please select a restaurant first."})

    answer = ask_syntra(msg, restaurant)
    return JSONResponse({"response": answer})
