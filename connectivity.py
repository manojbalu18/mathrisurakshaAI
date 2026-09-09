import requests

def is_online():
    """
    Check if the internet connection is available by trying to reach a reliable endpoint.
    Using a timeout to ensure the check doesn't block for too long.
    """
    try:
        # Using a reliable, lightweight endpoint
        requests.get("https://www.google.com", timeout=3)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False
