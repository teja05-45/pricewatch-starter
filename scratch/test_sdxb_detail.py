import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pricewatch.http import Client
from pricewatch.agents.normalizer import parse_money

sys.stdout.reconfigure(encoding='utf-8')

client = Client()
url = "http://localhost:4000/stores/zon/dp/SDXB88Y0?variant=FX3W7H"
r = client.get(url)
soup = BeautifulSoup(r.text, "html.parser")

main_soup = BeautifulSoup(str(soup), "html.parser")
for el in main_soup.find_all(["div", "section", "h3", "h4"]):
    if "other sellers" in el.get_text().lower() and el.name in ("h3", "h4"):
        p = el.parent
        if p:
            p.decompose()
        break

print("MAIN SOUP AFTER DECOMPOSE OTHER SELLERS:")
print(main_soup.prettify())

print("\nFIND ALL DIV, P, SPAN:")
for el in main_soup.find_all(["div", "p", "span"]):
    txt = el.get_text(" ", strip=True)
    print("EL NAME:", el.name, "TXT:", repr(txt))
