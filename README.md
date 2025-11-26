AI-powered automation platform for restaurants — chat ordering, menu search, and smart FAQ responses.

Syntra AI is a backend platform designed to help restaurants integrate AI assistants into their websites.
It provides structured ingestion of restaurant menus, FAQs, metadata, and location data.
The system exposes clean REST APIs powered by FastAPI, MongoDB Atlas, and OpenAI LLMs, enabling restaurants to offer intelligent chat-based ordering without POS integration.

## 🎥 Demo Video

[![Syntra AI Demo](https://img.youtube.com/vi/142uBCYuPV8/hqdefault.jpg)](https://youtu.be/142uBCYuPV8)


🌟 Features

Multi-restaurant support
Each restaurant has its own menus, FAQs, metadata, locations, and settings stored in MongoDB.

Menu ingestion pipeline
Owners upload their menu in JSON → Syntra AI cleans, validates, and stores it in MongoDB for LLM consumption.

LLM-powered chatbot
Returns dynamic responses to menu queries, order requests, FAQs, and restaurant-specific info.

FastAPI backend
Modular endpoints for restaurants, menus, locations, and chat interactions.

MongoDB Atlas integration
Clean schema structure using collections like: restaurants, menus, faqs, etc.

Role-ready architecture
Perfect for embedding inside any restaurant website or POS system later.

🧱 Tech Stack
Component	Technology
Backend Framework	FastAPI
Database	MongoDB Atlas
Geolocation	geopy
AI / LLM	OpenAI API
Environment	Python 3.10+
Deployment (future)	AWS (EC2, Lambda, API Gateway)
📂 Project Structure
SyntraAI/
│
├── main.py                 # FastAPI entry point
├── config/                 # DB config, API keys
├── routes/                 # All API routes
│   ├── restaurants.py
│   ├── menu.py
│   ├── chat.py
│   └── locations.py
│
├── services/               # Business logic layer
│   ├── menu_service.py
│   ├── faq_service.py
│   └── llm_service.py
│
├── utils/                  # Helpers (validation, formatting, etc.)
│
├── schemas/                # Pydantic models
│
└── README.md

🗄️ MongoDB Schema (Core)
Restaurant Document
{
  "_id": ObjectId,
  "key": "dominos_pizza",
  "display_name": "Domino’s Pizza",
  "timezone": "America/Chicago",
  "settings": {
      "chat_enabled": true,
      "order_enabled": true
  },
  "locations": [
    {
      "name": "Domino’s Pizza - West Loop",
      "address": "1005 W Taylor St, Chicago, IL 60607",
      "latitude": 41.8698,
      "longitude": -87.6505,
      "phone": "(312) 421-9000"
    }
  ]
}

Menu Document
{
  "restaurant_key": "dominos_pizza",
  "categories": [
    {
      "name": "Pizzas",
      "items": [
        {
          "name": "Pepperoni Pizza",
          "price": 12.99,
          "description": "Classic pepperoni with mozzarella cheese."
        }
      ]
    }
  ]
}

📡 API Endpoints
Restaurant endpoints
Method	Endpoint	Description
GET	/restaurants/	Get all restaurants
GET	/restaurants/{key}	Get restaurant by key
Menu endpoints
Method	Endpoint	Description
GET	/menu/{restaurant_key}	Fetch parsed menu
POST	/menu/{restaurant_key}/import	Upload raw menu JSON
Chat endpoints
Method	Endpoint	Description
POST	/chat/{restaurant_key}	LLM-powered chat response
⚙️ Setup Instructions (Local)
1️⃣ Clone the repo
git clone https://github.com/smituic/SyntraAI.git
cd SyntraAI

2️⃣ Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

3️⃣ Install dependencies
pip install -r requirements.txt

4️⃣ Set up environment variables

Create .env in root:

MONGO_URI="your_mongodb_uri"
OPENAI_API_KEY="your_openai_key"

5️⃣ Run FastAPI server
uvicorn main:app --reload


Server runs at:
➡️ http://127.0.0.1:8000

➡️ API Docs: http://127.0.0.1:8000/docs

🧪 Testing the API
Check restaurants
curl http://127.0.0.1:8000/restaurants

Test chat
curl -X POST http://127.0.0.1:8000/chat/dominos_pizza \
  -H "Content-Type: application/json" \
  -d '{"query":"What pizzas do you have?"}'

🛣️ Roadmap

 Frontend dashboard for restaurant owners

 POS system integration

 Voice ordering

 Order payment flow

 Analytics dashboard

 Multi-LLM support (OpenAI, Anthropic, Azure)

 AWS deployment (EC2 + MongoDB Atlas)

🤝 Contributing

PRs are welcome — open an issue first to discuss major changes.
