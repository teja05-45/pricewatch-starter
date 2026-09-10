import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 PriceWatch/0.1",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

url = "http://localhost:4000/stores/zon/dp/SDXB88Y0"
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, "html.parser")
print("PAGE TEXT LOWER:", repr(soup.get_text().lower()))

variant_a = soup.select_one("a[href*='variant=']")
print("VARIANT A:", variant_a)

if variant_a:
    var_url = urljoin(url, variant_a["href"])
    print("VAR URL:", var_url)
    r_var = requests.get(var_url, headers=headers)
    print("VAR STATUS:", r_var.status_code)
    soup_var = BeautifulSoup(r_var.text, "html.parser")
    print("VAR TEXT:", soup_var.get_text())
