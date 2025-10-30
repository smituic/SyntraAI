import json
import os

def load_all_restaurant_data():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    all_data = {}

    for file in os.listdir(data_dir):
        if file.endswith(".json"):
            name = file.replace(".json", "")
            with open(os.path.join(data_dir, file)) as f:
                all_data[name] = json.load(f)

    return all_data
