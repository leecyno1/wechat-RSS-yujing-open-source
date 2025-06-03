import requests

VERSION = '1.3.7'

try:
    response = requests.get('https://api.github.com/repos/rachelos/we-mp-rss/releases/latest')
    response.raise_for_status()  # 检查请求是否成功
    data = response.json()
    LATEST_VERSION = data.get('tag_name', '').replace('v', '')
except requests.RequestException as e:
    print(f"Failed to fetch latest version: {e}")
    LATEST_VERSION = ''
except ValueError as e:
    print(f"Failed to parse JSON response: {e}")
    LATEST_VERSION = ''

API_BASE = "/api/v1/wx"