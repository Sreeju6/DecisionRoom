import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

if not api_key or "paste_your_actual" in api_key:
    print("ERROR: GROQ_API_KEY is missing from your .env file.")
    raise SystemExit(1)

try:
    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: DecisionRoom connected."
            }
        ],
        max_completion_tokens=100,
    )

    print("SUCCESS: Groq API connection established.")
    print("Model:", response.model)
    print("Response:", response.choices[0].message.content)

except Exception as error:
    print("API TEST FAILED")
    print("Error type:", type(error).__name__)
    print("Details:", str(error))