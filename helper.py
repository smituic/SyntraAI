import os
import json
import uuid

def load_all_restaurant_data():
    """
    Loads all restaurant JSON data files from the 'data' folder (UTF-8)
    and returns them as a dictionary keyed by filename.
    Works with both flat and nested JSONs.
    """
    data_dir = os.path.join(os.getcwd(), "data")
    all_data = {}

    for filename in os.listdir(data_dir):
        if filename.endswith(".json"):
            name = filename.replace(".json", "")
            path = os.path.join(data_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    # Flatten nested Dominos-type JSONs
                    if isinstance(content, dict) and len(content) == 1 and "Dominos" in content:
                        all_data[name] = content
                    else:
                        all_data[name] = content
            except Exception as e:
                print(f"⚠️ Error loading {filename}: {e}")

    return all_data

def make_session_id():
    return str(uuid.uuid4())