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

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Connect to MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]
# db = mongo_client.get_database()  # default DB from URI
# Example: chat_collection = db["chat_history"]

# FastAPI setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory chat history
chat_history = []


# load restaurant data
def load_restaurant_data(file_name: str):
    """Load restaurant data JSON from /data folder."""
    file_path = os.path.join("data", file_name)
    with open(file_path, "r") as f:
        return json.load(f)
    
# Bacci menu + system prompt

# Load restaurant info dynamically from JSON
restaurant_data = load_restaurant_data("bacci_pizza.json")

# Convert menu dict to readable text for the system prompt
menu_text = "\n".join([
    f"- {category}: {', '.join([f'{item} ${price}' for item, price in items.items()])}"
    for category, items in restaurant_data["menu"].items()
])

SYSTEM_PROMPT = (
    f"You are Syntra AI, an elegant, professional restaurant assistant for {restaurant_data['name']} in {restaurant_data['location']}. "
    "Answer with warmth and precision like a maître d’. Handle menu questions, dietary needs, hours, locations, "
    "basic reservations info, and dish recommendations. If unsure about specifics, politely say you can check with staff. "
    "Keep answers concise and helpful.\n\n"
    f"{restaurant_data['description']}\n\nMenu:\n{menu_text}\n"
)

def ask_syntra(user_text: str) -> str:
    tz = pytz.timezone("America/Chicago")
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    time_note = f"The current local date and time in Chicago is {now}."

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n" + time_note},
                *chat_history,
                {"role": "user", "content": user_text},
            ],
        )
        answer = resp.choices[0].message.content
        chat_history.append({"role": "user", "content": user_text})
        chat_history.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        return f"Sorry, I couldn’t complete that request: {e}"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    if not msg:
        return JSONResponse({"response": "Please type a message."})
    answer = ask_syntra(msg)
    return JSONResponse({"response": answer})
