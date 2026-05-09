import os
import shutil
import time
import requests
from pathlib import Path
import create_torrents
import auto_upload

import config

# Configuration
TORRENT_SOURCE_DIR = Path(config.TORRENT_SOURCE_DIR_NAME)
FILE_DEST_DIR = Path(config.FILE_DEST_DIR_NAME)
TORRENT_FILE_DIR = Path(config.TORRENT_FILE_DIR_NAME)
TORRENT_DOWNLOAD_DIR = Path(config.TORRENT_DOWNLOAD_DIR_NAME)

QB_URL = config.QB_URL
QB_USER = config.QB_USER
QB_PASS = config.QB_PASS

def step_0_cleanup_old_files():
    print("\n=== Step 0: Cleaning up old .torrent files ===")
    
    # Remove from torrent_file_download (already added to qBittorrent)
    if TORRENT_DOWNLOAD_DIR.exists():
        for f in TORRENT_DOWNLOAD_DIR.glob("*.torrent"):
            try:
                os.remove(f)
                print(f"Deleted old file: {f}")
            except Exception as e:
                print(f"Error deleting {f}: {e}")

def step_1_create_torrents():
    print("\n=== Step 1: Creating torrents ===")
    try:
        create_torrents.create_torrents()
    except Exception as e:
        print(f"Error in creating torrents: {e}")

def step_2_move_files():
    print("\n=== Step 2: Moving files from torrent/ to file/ ===")
    if not TORRENT_SOURCE_DIR.exists():
        print(f"Source directory {TORRENT_SOURCE_DIR} does not exist.")
        return

    if not FILE_DEST_DIR.exists():
        FILE_DEST_DIR.mkdir(parents=True)
        print(f"Created destination directory: {FILE_DEST_DIR}")

    # Check if source is empty
    if not any(TORRENT_SOURCE_DIR.iterdir()):
        print(f"No files found in {TORRENT_SOURCE_DIR} to move.")
        return

    for item in TORRENT_SOURCE_DIR.iterdir():
        if item.is_dir():
            dest_path = FILE_DEST_DIR / item.name
            if dest_path.exists():
                print(f"Warning: Destination {dest_path} already exists. Skipping move for {item.name}.")
            else:
                try:
                    shutil.move(str(item), str(dest_path))
                    print(f"Moved {item.name} to {FILE_DEST_DIR}")
                except Exception as e:
                    print(f"Failed to move {item.name}: {e}")

def step_3_auto_upload():
    print("\n=== Step 3: Auto uploading torrents ===")
    try:
        auto_upload.main()
    except Exception as e:
        print(f"Error in auto upload: {e}")

def step_4_add_to_qbittorrent():
    print("\n=== Step 4: Adding torrents to qBittorrent ===")
    
    # 1. Login
    session = requests.Session()
    try:
        login_url = f"{QB_URL}/api/v2/auth/login"
        print(f"Logging in to {QB_URL}...")
        # qBittorrent requires Content-Type header for login sometimes, but requests handles data usually.
        # However, some versions are picky.
        login_resp = session.post(login_url, data={"username": QB_USER, "password": QB_PASS})
        
        if login_resp.status_code != 200:
            print(f"Login failed with status code {login_resp.status_code}")
            print(login_resp.text)
            return
            
        # Check for "Ok." text which confirms login on some versions
        if login_resp.text != "Ok.":
            # Just a warning, might still work if cookies are set
            pass
            
        print("Login successful.")
        
    except Exception as e:
        print(f"Failed to login to qBittorrent: {e}")
        return

    # 2. Scan for downloaded torrent files
    if not TORRENT_DOWNLOAD_DIR.exists():
        print("No torrent download directory found.")
        return

    torrent_files = list(TORRENT_DOWNLOAD_DIR.glob("*.torrent"))
    if not torrent_files:
        print("No downloaded torrent files found to add.")
        return

    save_path = os.path.abspath(FILE_DEST_DIR)
    print(f"Setting save path to: {save_path}")

    for torrent_path in torrent_files:
        print(f"Adding {torrent_path.name}...")
        try:
            files = {'torrents': open(torrent_path, 'rb')}
            data = {
                'savepath': save_path,
                'category': 'upload', # Optional: categorize as upload
                'paused': 'false',
                'autoTMM': 'false' # Disable Auto Torrent Management to force savepath
            }
            resp = session.post(f"{QB_URL}/api/v2/torrents/add", files=files, data=data)
            
            if resp.status_code == 200:
                print("Successfully added.")
            else:
                print(f"Failed to add. Status: {resp.status_code}, Response: {resp.text}")
                
        except Exception as e:
            print(f"Failed to add {torrent_path.name}: {e}")

def step_5_cleanup():
    print("\n=== Step 5: Cleaning up .torrent files ===")
    
    # Remove from torrent_file_download (already added to qBittorrent)
    if TORRENT_DOWNLOAD_DIR.exists():
        for f in TORRENT_DOWNLOAD_DIR.glob("*.torrent"):
            try:
                os.remove(f)
                print(f"Deleted {f}")
            except Exception as e:
                print(f"Error deleting {f}: {e}")

def main():
    step_0_cleanup_old_files()
    step_1_create_torrents()
    step_2_move_files()
    step_3_auto_upload()
    step_4_add_to_qbittorrent()
    step_5_cleanup()
    print("\n=== All steps completed ===")

if __name__ == "__main__":
    main()
