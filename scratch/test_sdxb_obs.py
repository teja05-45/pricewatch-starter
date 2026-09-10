import sys
import requests
import importlib.util
from pricewatch.http import Client

sys.stdout.reconfigure(encoding='utf-8')

spec = importlib.util.spec_from_file_location("test_zon_fix", "scratch/test_zon_fix.py")
test_zon_fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_zon_fix)

client = Client()
url = "http://localhost:4000/stores/zon/dp/SDXB88Y0"
r = client.get(url)
obs = test_zon_fix.extract_zon_improved(client, "zon", url, r.text)
print("OBSERVATION:", obs)
