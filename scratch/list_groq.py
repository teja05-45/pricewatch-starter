import os
import requests
import dotenv

dotenv.load_dotenv()
key = os.environ.get("GROQ_API_KEY")
headers = {"Authorization": f"Bearer {key}"}

r = requests.get("https://api.groq.com/openai/v1/models", headers=headers)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    for m in r.json().get("data", []):
        print("-", m["id"])
else:
    print(r.text)
