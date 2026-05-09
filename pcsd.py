from pcs_manager import PCSDownloader
import os
import sys
from pathlib import Path

def run_batch_download(limit=5):
    print(f"=== Starting Batch Download (Limit: {limit}) ===")
    
    downloader = PCSDownloader()
    dl_list_file = Path(r'c:\code\audio_auto_up\audio_auto_up\dl_list.txt')
    
    if not dl_list_file.exists():
        print("dl_list.txt not found.")
        return

    with open(dl_list_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        print("dl_list.txt is empty.")
        return

    tasks_to_run = lines[:limit]

    completed_count = 0
    for line in tasks_to_run:
        line = line.strip()
        if not line:
            continue
            
        parts = line.rstrip('\r\n').split('\t')
        # 跟pcs_manager一样的严格校验
        if len(parts) < 5:
            continue
            
        rj_code, link, pwd, nickname, post_url = parts[:5]
        passwords = parts[5:] if len(parts) > 5 else []
        
        if not passwords:
            passwords.append(rj_code)
        elif passwords == [""]:
            passwords[0] = rj_code
        elif rj_code not in passwords:
            passwords.append(rj_code)
        
        print(f"\nProcessing {completed_count + 1}/{limit}: {rj_code}")
        success = downloader.download_task(rj_code, link, pwd, passwords)
        
        if success:
            completed_count += 1
            print(f"Task {rj_code} finished successfully.")
        else:
            print(f"Task {rj_code} failed.")

    print(f"\n=== Batch download finished. Completed {completed_count} tasks. ===")

if __name__ == "__main__":
    limit = 5
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print("Invalid argument for limit. Using default: 5")
    
    # 执行一次下载指定数量的任务
    run_batch_download(limit)
