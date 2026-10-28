import json
from pathlib import Path
import urllib.request

key = Path('/run/secrets/paddleocr_api_key').read_text().strip()
request = urllib.request.Request('http://127.0.0.1:8080/ready', headers={'Authorization': 'Bearer ' + key})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(request, timeout=3) as response:
    assert json.load(response)['ready'] is True
