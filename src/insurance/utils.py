from urllib.parse import urlparse
import re


def parse_gps_coords(message: str):
    parsed = urlparse(message)
    path = parsed.path
    
    pattern = r'/(?:search|place)/(-?\d+\.?\d*),(-?\d+\.?\d*)'
    match = re.search(pattern, path)
    
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        return lat, lon
    
    return None, None