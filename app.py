from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os
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

# Bacci menu + system prompt
BACCI_MENU = """
Bacci Pizzeria (Chicago) — highlights:
- Jumbo Slice: Cheese $4.99, Sausage or Pepperoni $5.49, Specialty Slice $5.99.
- Hand-Tossed Pizzas: Medium 14" $14.95, Family 18" $19.95, Party 24" $27.95.
- Starters: Jumbo Wings (5pc) $4.95.
- Sandwiches: Italian Beef $5.95, Bacci Burger $7.95.
Notes: Founded 1996 on Taylor St (Little Italy), famous for jumbo slice; multiple Chicago locations.
"""

SYSTEM_PROMPT = (
    "You are Syntra AI, an elegant, professional restaurant assistant for Bacci Pizzeria in Chicago. "
    "Answer with warmth and precision like a maître d’. Handle menu questions, dietary needs, hours, locations, "
    "basic reservations info, and dish recommendations. If unsure about specifics (e.g., today’s hours for a given store), "
    "politely say you can check with staff. Keep answers concise and helpful.\n\n"
    f"{BACCI_MENU}\n"
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
