import sys
import requests

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 PriceWatch/0.1",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

for pid in ["Y21ZF4QH", "SDXB88Y0", "SEMUN58S"]:
    url = f"http://localhost:4000/stores/zon/dp/{pid}"
    res = requests.get(url, headers=headers)
    print(f"=== HTML FOR {pid} ===")
    print(res.text)
    print("======================\n")
