# seed_db.py
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from helper import load_all_restaurant_data
from datetime import datetime
import pprint

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["SyntraAI"]

def normalize_key(name: str) -> str:
    # ensure consistent key format (like your JSON keys)
    return name.strip().replace(" ", "_")

def prepare_menu_items(key: str, data: dict):
    """
    Normalize whatever menu structure appears in your JSON.
    Returns a list of item dicts ready for db.menus insertion.
    """
    menu_candidates = []
    # Common patterns: data["menu"], data["items"], data.get("menu_items")
    if isinstance(data.get("menu"), list):
        menu_candidates = data.get("menu")
    elif isinstance(data.get("items"), list):
        menu_candidates = data.get("items")
    elif isinstance(data.get("menu_items"), list):
        menu_candidates = data.get("menu_items")
    # Some nested structures might use categories: {'Starters': [...], 'Mains': [...]}
    elif isinstance(data.get("menu"), dict):
        for cat, items in data["menu"].items():
            if isinstance(items, list):
                for it in items:
                    it = dict(it)
                    it.setdefault("category", cat)
                    menu_candidates.append(it)
    # Fallback: maybe top-level has keys that look like items; otherwise empty
    return menu_candidates

def seed():
    print("Loading JSON restaurant data via helper.load_all_restaurant_data()...")
    all_restaurants = load_all_restaurant_data()

    print("Wiping restaurants & menus (dev only) ...")
    db.restaurants.delete_many({})
    db.menus.delete_many({})

    inserted_restaurants = 0
    inserted_items = 0

    for key, raw in all_restaurants.items():
        # handle nested like {"Dominos": {...}}
        if isinstance(raw, dict) and len(raw) == 1:
            # if the single key equals a brand name and contains details
            single_key = list(raw.keys())[0]
            if isinstance(raw[single_key], dict) and single_key.lower() in ["dominos", "domino's", "dominos pizza"]:
                data = raw[single_key]
            else:
                # not a Dominos special-case; keep raw as data
                data = raw
        else:
            data = raw

        restaurant_key = key  # keep original key form e.g., "bombay_grill"
        display_name = data.get("name") or restaurant_key.replace("_", " ").title()

        restaurant_doc = {
            "key": restaurant_key,
            "display_name": display_name,
            "name": display_name,
            "timezone": data.get("timezone", "America/Chicago"),
            "settings": data.get("settings", {"chat_enabled": True, "order_enabled": True}),
            "meta": data.get("meta", {}),
            "locations": data.get("locations", []),
            "raw": data,  # keep original JSON in case you need it later
            "created_at": datetime.utcnow()
        }
        db.restaurants.insert_one(restaurant_doc)
        inserted_restaurants += 1

        # menu items
        items = prepare_menu_items(restaurant_key, data)
        for idx, it in enumerate(items):
            item_doc = {
                "item_id": it.get("item_id") or f"{restaurant_key}_itm_{idx+1}",
                "restaurant_key": restaurant_key,
                "name": it.get("name") or it.get("title") or f"item_{idx+1}",
                "category": it.get("category") or it.get("type") or "Uncategorized",
                "price": float(it.get("price", 0.0)) if it.get("price") is not None else 0.0,
                "description": it.get("description", ""),
                "addons": it.get("addons", []),
                "availability": bool(it.get("availability", True)),
                "metadata": it.get("metadata", {}),
                "created_at": datetime.utcnow()
            }
            db.menus.insert_one(item_doc)
            inserted_items += 1

    # create indexes
    db.restaurants.create_index("key", unique=True)
    db.menus.create_index([("restaurant_key", 1), ("name", 1)])
    db.menus.create_index("item_id", unique=False)
    db.create_collection("test_index_collection", capped=False) if "test_index_collection" not in db.list_collection_names() else None

    print(f"Inserted {inserted_restaurants} restaurants and {inserted_items} menu items.")
    print("Done. Inspect the DB in MongoDB Compass or Atlas.")

if __name__ == "__main__":
    seed()
