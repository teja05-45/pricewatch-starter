import sys
import requests
from bs4 import BeautifulSoup
from pricewatch.agents.extractor import extract_zon, Client

sys.stdout.reconfigure(encoding='utf-8')

client = Client()

res = client.get("http://localhost:4000/stores/zon/")
soup = BeautifulSoup(res.text, "html.parser")
item_links = [a["href"] for a in soup.find_all("a") if "/item/" in a.get("href", "") or "/dp/" in a.get("href", "")]

print(f"Found {len(item_links)} items on Zon")

for link in item_links:
    full_url = "http://localhost:4000" + link
    r = client.get(full_url)
    obs = extract_zon(client, "zon", full_url, r.text)
    print(f"URL: {link} -> Name: '{obs.name}', Price: {obs.price_cents}, Pack: {obs.pack_size}, Avail: {obs.availability}, Notes: {obs.notes}")
    if obs.price_cents is None:
        print("   HTML snippet:", r.text[:500])
