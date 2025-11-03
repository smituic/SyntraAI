from openai import OpenAI
from pymongo import MongoClient
from datetime import datetime
import random
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]

# ---------- Helpers ----------
def generate_id(prefix):
    return f"{prefix}{random.randint(1000,9999)}"

def insert_order(restaurant, user_name, items, total_price):
    order = {
        "order_id": generate_id("ORD"),
        "restaurant": restaurant,
        "user_name": user_name,
        "items": items,
        "total_price": total_price,
        "order_time": datetime.now().isoformat(),
        "status": "Confirmed"
    }
    db[f"{restaurant}_order_docs"].insert_one(order)
    return order

def insert_reservation(restaurant, user_name, date, time, guests):
    reservation = {
        "reservation_id": generate_id("RES"),
        "restaurant": restaurant,
        "user_name": user_name,
        "date": date,
        "time": time,
        "guests": guests,
        "status": "Confirmed",
        "reservation_time": datetime.now().isoformat()
    }
    db[f"{restaurant}_reservation_docs"].insert_one(reservation)
    return reservation

# ---------- Chat Logic ----------
def chat_with_syntra(user_message, restaurant):
    msg = user_message.lower()

    if "order" in msg:
        items = [
            {"name": "Large Pepperoni Pizza", "quantity": 1, "price": 14.99},
            {"name": "Coke", "quantity": 1, "price": 1.99}
        ]
        total = sum(i["price"] for i in items)
        order = insert_order(restaurant, "Guest", items, total)
        return f"✅ Order {order['order_id']} placed at {restaurant}! Total ${total:.2f}."

    elif "reserve" in msg or "reservation" in msg:
        res = insert_reservation(restaurant, "Guest", "2025-11-02", "19:00", 2)
        return f"🪑 Reservation {res['reservation_id']} confirmed at {restaurant} for {res['guests']} guests."

    else:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=f"You are Syntra AI assistant for {restaurant}. Respond to: {user_message}"
        )
        return response.output[0].content[0].text
