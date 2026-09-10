import sys
import os
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

def inspect_flux():
    url = "http://localhost:4000/stores/flux/item/FLX-4WAQ55"
    res = requests.get(url)
    print("--- FLUX ITEM HTML ---")
    print(res.text)

def inspect_zon():
    index_res = requests.get("http://localhost:4000/stores/zon/")
    soup = BeautifulSoup(index_res.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True) if "/item/" in a["href"]]
    if links:
        item_url = "http://localhost:4000" + links[0]
        res = requests.get(item_url)
        print("--- ZON ITEM HTML ---")
        print(res.text)

def inspect_shield():
    index_res = requests.get("http://localhost:4000/stores/shield/")
    print("--- SHIELD INDEX CODE ---", index_res.status_code)
    print(index_res.text[:1000])

if __name__ == "__main__":
    inspect_flux()
    inspect_zon()
    inspect_shield()
