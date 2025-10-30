from pymongo import MongoClient

# Your actual MongoDB Atlas connection string
uri = "mongodb+srv://dhwanitvag24_db_user:fos7N1Lcg9mIT0wL@syntraai.cbimrsf.mongodb.net/syntra_ai_db?retryWrites=true&w=majority&appName=SyntraAI"

# Connect to MongoDB
client = MongoClient(uri)
db = client["syntra_ai_db"]

# Create a test collection and insert a document
collection = db["test_collection"]
collection.insert_one({"message": "Hello from Syntra AI!"})

# Retrieve the inserted document
doc = collection.find_one({"message": "Hello from Syntra AI!"})
print(doc)
