from openai import OpenAI

def ask_syntra(prompt: str):
    client = OpenAI(api_key="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")

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are Syntra AI, an intelligent assistant for businesses."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content
