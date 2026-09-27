import requests

url = "https://www.fast2sms.com/dev/bulkV2"
querystring = {
    "authorization": "invalid_secret_key",
    "variables_values": "829103",
    "route": "otp",
    "numbers": "9999999999"
}
headers = {
    'cache-control': "no-cache"
}

try:
    response = requests.request("GET", url, headers=headers, params=querystring, timeout=5)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Exception: {e}")
