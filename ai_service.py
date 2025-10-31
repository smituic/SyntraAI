import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# Get the OpenAI key safely
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the client
client = OpenAI(api_key=OPENAI_API_KEY)

def ask_syntra(prompt: str):
    """
    Sends a user prompt to OpenAI and returns the assistant's response.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are Syntra AI, an intelligent assistant for businesses."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating response: {e}"
