import re
import os
import time
import html
import requests
from bs4 import BeautifulSoup
import urllib3

# Disable SSL warnings for cleaner output
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import config

# Configuration
UPLOAD_URL = config.KAMEPT_UPLOAD_URL
TAKE_UPLOAD_URL = config.KAMEPT_TAKE_UPLOAD_URL
AJAX_URL = config.KAMEPT_AJAX_URL
TORRENT_DIR = os.path.abspath(config.TORRENT_FILE_DIR_NAME)
DOWNLOAD_DIR = os.path.abspath(config.TORRENT_DOWNLOAD_DIR_NAME)
RJ_LIST_FILE = config.RJ_LIST_FILE_NAME
KAMEPT_COOKIES_FILE = config.KAMEPT_COOKIES_FILE_NAME
DL_LIST_FILE = config.DL_LIST_FILE_NAME
MEGA_LIST_FILE = config.MEGA_LIST_FILE_NAME

def parse_cookies(file_path):
    """Parses cookies from the curl command in upload.txt"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"{file_path} not found.")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r"[-]{1,2}b\s+['\"]([^'\"]+)['\"]", content)
    if not match:
        match = re.search(r"[-]{1,2}b\s+([^\s]+)", content)
        
    if not match:
        raise ValueError("Could not find cookies in upload.txt.")
    
    cookie_str = match.group(1)
    cookies = {}
    for pair in cookie_str.split(';'):
        pair = pair.strip()
        if '=' in pair:
            name, value = pair.split('=', 1)
            cookies[name] = value
    return cookies

def get_rj_code(text):
    """Extracts RJ/BJ/VJ code from filename or title"""
    match = re.search(r"([RBV]J\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None

def build_kamegen_url(rj_code):
    """
    Constructs the DLSite URL based on product code (RJ/BJ/VJ) logic from kamegen.js.
    """
    # From kamegen.js:
    # dlsite: { regex: /([RVB]J\d+)/gi, buildUrl: (code) => `https://www.dlsite.com/maniax/work/=/product_id/${code.toUpperCase()}.html` }
    return f"https://www.dlsite.com/maniax/work/=/product_id/{rj_code}.html/?locale=ja_JP"

def fetch_kamegen_info(session, url_val):
    """
    Simulates the fetch('ajax.php', ...) call from kamegen.js
    """
    data = {
        "action": "getKameGen",
        "params[url]": url_val
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": UPLOAD_URL
    }
    
    print(f"Fetching info from ajax.php with url={url_val}...")
    try:
        resp = session.post(AJAX_URL, data=data, headers=headers)
        resp.raise_for_status()
        json_resp = resp.json()
        if json_resp.get("ret") != 0:
            print(f"API Error: {json_resp.get('msg')}")
            return None
        return json_resp.get("data")
    except Exception as e:
        print(f"Failed to fetch info: {e}")
        return None

def get_dl_list_info(rj_code):
    """
    Searches dl_list.txt for the given product code (RJ/BJ/VJ).
    Returns a dict with 'uploader' and 'post_url' if found, else None.
    """
    if not os.path.exists(DL_LIST_FILE):
        print(f"Warning: {DL_LIST_FILE} not found.")
        return None
        
    target_rj = rj_code.upper()
    
    try:
        with open(DL_LIST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 5:
                    continue
                
                # Check product code (Column 0)
                if parts[0].strip().upper() == target_rj:
                    return {
                        'uploader': parts[3].strip(),
                        'post_url': parts[4].strip()
                    }
    except Exception as e:
        print(f"Error reading {DL_LIST_FILE}: {e}")
        
    return None

def get_mega_list_info(rj_code):
    """
    Searches mega.txt for the given product code (RJ/BJ/VJ).
    Returns a dict with 'uploader' and 'post_url' if found, else None.
    """
    if not os.path.exists(MEGA_LIST_FILE):
        # print(f"Warning: {MEGA_LIST_FILE} not found.")
        return None
        
    target_rj = rj_code.upper()
    
    try:
        with open(MEGA_LIST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 5:
                    continue
                
                # Format: RJ_CODE \t LINK \t PWD \t NICKNAME \t POST_URL \t PASSWORDS...
                if parts[0].strip().upper() == target_rj:
                    return {
                        'uploader': parts[3].strip(),
                        'post_url': parts[4].strip()
                    }
    except Exception as e:
        print(f"Error reading {MEGA_LIST_FILE}: {e}")
        
    return None

def remove_from_dl_list(rj_code):
    """
    Removes the line corresponding to rj_code from DL_LIST_FILE.
    """
    if not os.path.exists(DL_LIST_FILE):
        return

    target_rj = rj_code.upper()
    lines_to_keep = []
    removed = False

    try:
        with open(DL_LIST_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split('\t')
            if parts and parts[0].strip().upper() == target_rj:
                removed = True
                continue # Skip this line
            lines_to_keep.append(line)

        if removed:
            with open(DL_LIST_FILE, 'w', encoding='utf-8') as f:
                f.writelines(lines_to_keep)
            print(f"Removed {rj_code} from {DL_LIST_FILE}.")

    except Exception as e:
        print(f"Error updating {DL_LIST_FILE}: {e}")

def remove_from_mega_list(rj_code):
    """
    Removes the line corresponding to rj_code from MEGA_LIST_FILE.
    """
    if not os.path.exists(MEGA_LIST_FILE):
        return

    target_rj = rj_code.upper()
    lines_to_keep = []
    removed = False

    try:
        with open(MEGA_LIST_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split('\t')
            if parts and parts[0].strip().upper() == target_rj:
                removed = True
                continue # Skip this line
            lines_to_keep.append(line)

        if removed:
            with open(MEGA_LIST_FILE, 'w', encoding='utf-8') as f:
                f.writelines(lines_to_keep)
            print(f"Removed {rj_code} from {MEGA_LIST_FILE}.")

    except Exception as e:
        print(f"Error updating {MEGA_LIST_FILE}: {e}")

def fix_chinese_title_from_dlsite(session, rj_code, descr, small_descr):
    """
    检测 descr 中的「中文商品名抓取错误」标记，若存在则直接请求 DLSite 获取中文商品名并替换。
    返回 (descr, small_descr)。
    """
    ERROR_MARKER = '中文商品名抓取错误'

    if ERROR_MARKER not in descr and ERROR_MARKER not in small_descr:
        return descr, small_descr

    print(f"[{rj_code}] 检测到中文商品名抓取错误，开始 Python 侧修复...")

    # 从 descr 中提取日文商品名
    ja_title_match = re.search(r'日文商品名[：:]\s*(.+)', descr)
    if not ja_title_match:
        print(f"[{rj_code}] 无法从简介中提取日文商品名，跳过修复")
        return descr, small_descr

    ja_title = ja_title_match.group(1).strip()

    # 判断语言：简中/繁中
    if re.search(r'[簡体中文版|简体中文版]', ja_title):
        locale = 'zh_CN'
    elif re.search(r'[繁体中文版|繁體中文版]', ja_title):
        locale = 'zh_TW'
    else:
        print(f"[{rj_code}] 日文商品名无简繁中文版标识，跳过修复")
        return descr, small_descr

    # 尝试抓取中文标题（重试2次，间隔10秒）
    chinese_title = None
    for attempt in range(2):
        time.sleep(10)
        title = fetch_dlsite_chinese_title(session, rj_code, locale)
        if title and title != ja_title:
            chinese_title = title
            print(f"[{rj_code}] Python 侧成功抓取中文商品名: {chinese_title}")
            break
        print(f"[{rj_code}] 第 {attempt + 1} 次抓取失败（标题与日文相同），重试...")

    if chinese_title:
        # 替换 descr 中的错误标记
        descr = re.sub(
            r'(中文商品名[：:]\s*)' + re.escape(ERROR_MARKER),
            r'\g<1>' + chinese_title,
            descr
        )
        # 替换 small_descr 中的错误标记
        small_descr = small_descr.replace(ERROR_MARKER, chinese_title)
    else:
        print(f"[{rj_code}] Python 侧抓取全部失败，保留错误标记")

    return descr, small_descr


def fetch_dlsite_chinese_title(session, rj_code, locale):
    """
    直接请求 DLSite 指定语言页面，返回商品标题。
    """
    url = f"https://www.dlsite.com/maniax/work/=/product_id/{rj_code}.html/?locale={locale}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = session.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        match = re.search(r'<h1[^>]*id=["\']work_name["\'][^>]*>(.*?)</h1>', resp.text, re.DOTALL)
        if match:
            title = html.unescape(match.group(1))
            return ' '.join(title.split())
    except Exception as e:
        print(f"[{rj_code}] DLSite 请求失败: {e}")
    return None


def main():
    if not os.path.exists(TORRENT_DIR):
        os.makedirs(TORRENT_DIR)
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        
    files = [f for f in os.listdir(TORRENT_DIR) if f.endswith('.torrent')]
    if not files:
        print("No .torrent files found.")
        return

    print(f"Found {len(files)} tasks.")
    
    try:
        cookies = parse_cookies(KAMEPT_COOKIES_FILE)
    except Exception as e:
        print(f"Error parsing cookies: {e}")
        return

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    for filename in files:
        filepath = os.path.join(TORRENT_DIR, filename)
        print(f"\nProcessing: {filename}")
        
        # 1. Get Product Code (RJ/BJ/VJ)
        rj_code = get_rj_code(filename)
        if not rj_code:
            print("Skipping: No product code (RJ/BJ/VJ) found in filename.")
            continue
            
        # 2. Fetch Info (Simulate KameGen)
        kamegen_url = rj_code
        # kamegen_url = build_kamegen_url(rj_code)
        info_data = fetch_kamegen_info(session, kamegen_url)
        
        if not info_data:
            print("Skipping: Could not retrieve info from KameGen.")
            continue
            
        # 3. Prepare Form Data
        # We need to extract other fields like description, title, etc.
        title = info_data.get('title', '')
        descr = info_data.get('description', '')
        small_descr = info_data.get('small_title') or ''
        product_url = info_data.get('url', '')
        
        # Integrate info from dl_list.txt or mega.txt
        source_info = get_dl_list_info(rj_code)
        source_type = "Baidu"
        if not source_info:
            source_info = get_mega_list_info(rj_code)
            source_type = "Mega"
            
        if source_info:
            print(f"Found {source_type} List info for {rj_code}: {source_info}")
            
            # 1. Modify small_descr
            if source_info['uploader']:
                suffix = f" 转自{source_info['uploader']}@南+"
                small_descr = small_descr + suffix
            
            # 2. Modify descr
            if source_info['post_url']:
                if descr is None:
                    descr = ""
                descr = f"本贴为半自动发帖，没怎么检查文件内容，如果有文件错误请直接点击举报\n发布时会自动删除一些我认为是系统垃圾的东西，如rsrc、Thumbs.db、desktop.ini、.DS_Store等系统残留\n会手动删除一些自购证明之类的图片或资料夹（已在标题简介中贴出出处），也会把乱码文件改为正确的日文，txt之类的可能会顺手转为utf-8\n[quote]{suffix}\n原帖{source_info['post_url']}[/quote]\n\n{descr}"
        else:
            print(f"No DL/Mega List info found for {rj_code}")

        # --- 中文商品名抓取错误双保险：Python 侧直接请求 DLSite 修复 ---
        descr, small_descr = fix_chinese_title_from_dlsite(session, rj_code, descr, small_descr)

        # --- START: Modified Category & Tag Logic ---
        
        # Determine Category (Type)
        # Default to 420 (Foreign Audio)
        upload_type = "420" 
        
        if "中文音聲" in title:
            upload_type = "421" # Chinese Audio
            print("Detected '中文音聲' in title. Setting type to 421.")
        
        # Check "Chinese Version" logic (Translation/Subtitle)
        # This logic is separate from the category logic above.
        is_chinese = False
        if "中文版" in title:
            is_chinese = True
            print("Detected '中文版' in title.")

        # Construct the payload for takeupload.php
        # Note: We need to handle multipart/form-data for the file upload
        
        # Default fields based on your description
        payload = {
            "name": title,
            "small_descr": small_descr,
            "url": product_url, # hidden field 'custom_field_item_link' mapping? No, usually 'url' or specific custom fields.
            # Looking at src_upload.php, 'descr' is the main description
            "descr": descr,
            "type": upload_type, # Use the determined type
            "uplver": "yes", # Anonymous
        }
        
        # --- END: Modified Logic ---

        print("Fetching upload page to parse form fields...")
        upload_page = session.get(UPLOAD_URL)
        soup = BeautifulSoup(upload_page.content, "html.parser")
        
        # Find the form
        form = soup.find("form", {"action": "takeupload.php"})
        if not form:
            print("Error: Could not find upload form.")
            continue
            
        # Extract inputs to preserve hidden values (tokens etc)
        form_data = {}
        for input_tag in form.find_all("input"):
            name = input_tag.get("name")
            val = input_tag.get("value", "")
            input_type = input_tag.get("type", "text").lower()
            
            if not name:
                continue
                
            if input_type in ["checkbox", "radio"]:
                if input_tag.has_attr("checked"):
                    form_data[name] = val
            else:
                form_data[name] = val
        
        # Update with our data
        form_data.update(payload)
        
        # Fix custom field name for URL if it exists
        cf_link_input = form.find("input", {"id": "custom_field_item_link"})
        if cf_link_input and cf_link_input.get("name"):
            form_data[cf_link_input.get("name")] = product_url
        
        # Handle "Chinese Subtitle" tag and team selection
        # Logic: Only if title has "中文版"
        if is_chinese:
            print("Applying Chinese Version settings (Tags/Team)...")
            
            # 1. Set "中文字幕" tag: tags[5][] = 8
            tag_key = "tags[5][]"
            tag_val = "8"
            
            if tag_key in form_data:
                current_val = form_data[tag_key]
                if isinstance(current_val, list):
                    if tag_val not in current_val:
                        current_val.append(tag_val)
                elif current_val != tag_val:
                    form_data[tag_key] = [current_val, tag_val]
            else:
                form_data[tag_key] = tag_val
            
            # 2. Set team_sel[5] = "1"
            form_data["team_sel[5]"] = "1"
            
        # Remove 'file' from form_data if it was caught as text input
        if "file" in form_data:
            del form_data["file"]

        # Prepare File Upload
        # We'll use a local variable to hold the success flag
        upload_success = False
        
        # Submit
        print("Submitting upload...")
        
        try:
            with open(filepath, "rb") as f_upload:
                files_data = {
                    "file": (filename, f_upload, "application/x-bittorrent")
                }
                post_resp = session.post(TAKE_UPLOAD_URL, data=form_data, files=files_data, allow_redirects=True)
            
            # The file f_upload is now closed because we are out of the 'with' block
            final_url = post_resp.url
            print(f"Final URL: {final_url}")

            if "details.php" in final_url:
                # Success based on URL
                details_soup = BeautifulSoup(post_resp.content, "html.parser")
                dl_link = details_soup.find("a", href=re.compile(r"download.php\?downhash="))

                if dl_link:
                    href = dl_link['href']
                    dl_url = href if href.startswith("http") else f"https://kamept.com/{href.lstrip('/')}"
                    
                    print(f"Success! Downloading from {dl_url}...")
                    
                    try:
                        dl_resp = session.get(dl_url)
                        if dl_resp.status_code == 200:
                            cd = dl_resp.headers.get("content-disposition")
                            saved_name = filename  # Default name
                            if cd:
                                fname_match = re.findall('filename="?([^"]+)"?', cd)
                                if fname_match:
                                    saved_name = fname_match[0]
                            
                            save_path = os.path.join(DOWNLOAD_DIR, saved_name)
                            with open(save_path, "wb") as f_dl:
                                f_dl.write(dl_resp.content)
                            print(f"Saved torrent to: {save_path}")
                            upload_success = True
                        else:
                            print(f"Download failed with status code: {dl_resp.status_code}")
                    except Exception as e:
                        print(f"Error downloading torrent: {e}")
                else:
                    print("Error: Could not find download link on details page.")
            else:
                # Failed (no details.php in URL)
                print("Upload failed. Check response content for errors.")

        except Exception as e:
            print(f"Error during upload submission: {e}")

        # Post-upload actions outside the file-open context
        if upload_success:
            # 1. Remove the original torrent file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"Removed source torrent: {filename}")
            except Exception as e:
                print(f"Error removing source torrent {filename}: {e}")
            
            # 2. Remove from dl_list.txt and mega.txt
            remove_from_dl_list(rj_code)
            remove_from_mega_list(rj_code)
            
            # 3. Record product code to RJ_list.txt
            try:
                with open(RJ_LIST_FILE, "a") as f_list:
                    f_list.write(rj_code + "\n")
                print(f"Recorded {rj_code} to list.")
            except Exception as e:
                print(f"Error recording product code: {e}")


if __name__ == "__main__":
    main()
