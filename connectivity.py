import socket
import time

_cached_status = None
_last_check_time = 0.0
_CACHE_TTL = 15.0  # Cache connectivity status for 15 seconds to prevent execution lag

def is_online(force_refresh=False):
    """
    Check if the internet connection is available using an ultra-fast raw socket connection.
    Caches results for 15 seconds to eliminate repeated blocking latency on reruns.
    """
    global _cached_status, _last_check_time
    now = time.time()
    
    if not force_refresh and _cached_status is not None and (now - _last_check_time < _CACHE_TTL):
        return _cached_status

    status = False
    # Try Google DNS and Cloudflare DNS directly via socket (takes < 50ms)
    for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53)]:
        try:
            sock = socket.create_connection((host, port), timeout=0.25)
            sock.close()
            status = True
            break
        except OSError:
            continue

    _cached_status = status
    _last_check_time = now
    return status
