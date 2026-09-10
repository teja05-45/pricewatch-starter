import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 PriceWatch/0.1",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

session = requests.Session()
session.headers.update(headers)

res = session.get("http://localhost:4000/stores/zon/")
print("--- ZON INDEX WITH HEADERS --- status:", res.status_code)
print(res.text[:1500])

soup = BeautifulSoup(res.text, "html.parser")
item_links = [a["href"] for a in soup.find_all("a") if "/item/" in a.get("href", "") or "/dp/" in a.get("href", "")]
print("ITEM LINKS:", item_links)

if item_links:
    item_res = session.get("http://localhost:4000" + item_links[0])
    print("--- ZON ITEM 1 HTML ---")
    print(item_res.text)
