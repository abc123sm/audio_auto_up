import json
from pathlib import Path

import re

def get_auth_from_har(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Try parsing as JSON (HAR format)
    try:
        har_data = json.loads(content)
        entries = har_data.get('log', {}).get('entries', [])
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            if 'bbs.white-plus.net' in url:
                headers = entry.get('request', {}).get('headers', [])
                ua = next((h['value'] for h in headers if h['name'].lower() == 'user-agent'), None)
                cookie = next((h['value'] for h in headers if h['name'].lower() == 'cookie'), None)
                if ua and cookie:
                    return ua, cookie
    except json.JSONDecodeError:
        pass

    # Fallback to parsing as curl command (.txt format)
    ua_match = re.search(r"-H\s+['\"]User-Agent:\s*([^'\"]+)['\"]", content, re.IGNORECASE)
    cookie_match = re.search(r"-H\s+['\"]Cookie:\s*([^'\"]+)['\"]", content, re.IGNORECASE)
    
    ua = ua_match.group(1) if ua_match else None
    cookie = cookie_match.group(1) if cookie_match else None
    
    if ua and cookie:
        return ua, cookie

    return None, None

if __name__ == "__main__":
    ua, cookie = get_auth_from_har('har.har')
    print(f"UA: {ua}")
    print(f"Cookie: {cookie}")
