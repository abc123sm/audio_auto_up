import subprocess
import os
import time
import re
from pathlib import Path
import config

class PCSDownloader:
    def __init__(self, pcs_path=None):
        self.pcs_path = pcs_path or config.PCS_PATH
        self.base_dir = config.BASE_DIR
        self.dl_list_file = self.base_dir / config.DL_LIST_FILE_NAME
        self.rj_list_file = self.base_dir / config.RJ_LIST_FILE_NAME
        self.download_path = config.BAIDU_DOWNLOAD_PATH

    def run_command(self, args):
        cmd = [self.pcs_path] + args
        print(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        return result

    def set_proxy(self, proxy=""):
        self.run_command(['config', 'set', f'--proxy={proxy}'])

    def get_local_dir_size(self, path):
        """获取本地目录大小（单位：字节）"""
        total_size = 0
        path = Path(path)
        if not path.exists():
            return 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size

    def rename_large_files(self, directory_path):
        """校验并重命名超过 500MB 的 pdf 或 z 文件为 7z"""
        path = Path(directory_path)
        if not path.exists():
            return
        
        threshold = 500 * 1024 * 1024  # 500MB
        target_extensions = {'.pdf', '.z', '.png', '.jpg'}
        count = 0
        
        print(f"Checking files in {directory_path} for renaming...")
        for file_path in path.rglob('*'):
            if file_path.is_file():
                if file_path.suffix.lower() in target_extensions:
                    try:
                        file_size = file_path.stat().st_size
                        if file_size > threshold:
                            new_path = file_path.with_suffix('.7z')
                            file_path.rename(new_path)
                            print(f"[Rename] {file_path.name} -> {new_path.name} (Size: {file_size / 1024 / 1024:.2f}MB)")
                            count += 1
                    except Exception as e:
                        print(f"[Error] Failed to rename {file_path.name}: {e}")
        
        if count > 0:
            print(f"Total renamed files: {count}")
        else:
            print("No files matched the renaming criteria.")

    def download_task(self, rj_code, link, pwd, passwords=None):
        print(f"Starting task for {rj_code}")
        
        # 1. 设定无代理进行转存
        self.set_proxy("")
        
        # 2. 切换目录并创建
        self.run_command(['cd', self.download_path])
        time.sleep(5)
        self.run_command(['mkdir', rj_code])
        time.sleep(5)
        self.run_command(['cd', rj_code])
        time.sleep(5)
        
        # 3. 转存资源
        if '?pwd=' in link:
            transfer_result = self.run_command(['transfer', link])
        elif pwd:
            transfer_result = self.run_command(['transfer', link, pwd])
        else:
            transfer_result = self.run_command(['transfer', link])
        
        time.sleep(5)

        if "错误码 -21" in transfer_result.stdout:
            print(f"Skipping {rj_code} due to transfer error -21: {transfer_result.stdout.strip()}")
            return False

        if "成功" not in transfer_result.stdout and "已存在" not in transfer_result.stdout:
            print(f"Transfer warning for {rj_code}: {transfer_result.stdout}")
        
        # 4. 设定代理进行下载
        self.set_proxy(config.PROXY_SETTING)
        
        # 5. 下载资源并进行校验
        success = False
        # 构造本地保存路径
        local_save_dir = self.base_dir / config.BAIDU_USERNAME / rj_code 
        
        for attempt in range(3):
            print(f"Download attempt {attempt + 1} for {rj_code}")
            self.run_command(['d', '.'])
            
            # 校验大小 (PRD 93-95: > 5MB 为成功)
            size = self.get_local_dir_size(local_save_dir)
            print(f"Current local directory size: {size / 1024 / 1024:.2f} MB")
            
            if size > 5 * 1024 * 1024: # 5MB
                print(f"Download successful for {rj_code}")
                success = True
                
                # 【新增】校验完文件大小后，处理大文件重命名
                self.rename_large_files(local_save_dir)
                
                # 【新增】自动套娃解压
                from auto_extractor import AutoExtractor
                extractor = AutoExtractor()
                
                final_node = extractor.extract_recursive(local_save_dir, passwords or [])
                
                if final_node:
                    extractor.reorganize_based_on_chain(local_save_dir, final_node)
                
                break
            else:
                if attempt < 2:
                    print(f"体积低于5MB，等待30秒后重试")
                    time.sleep(30)
                else:
                    print(f"Download failed after 3 attempts for {rj_code}")
        
        # 6. 清理
        self.set_proxy("")
        if success:
            self.run_command(['cd', self.download_path])
            self.run_command(['rm', rj_code])
            return True
        else:
            # 下载失败改为也要清理
            self.run_command(['cd', self.download_path])
            self.run_command(['rm', rj_code])
            return False

    def process_list(self, limit=None):
        if not self.dl_list_file.exists():
            print("No dl_list.txt found.")
            return

        with open(self.dl_list_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            return

        tasks_to_run = lines[:limit] if limit else lines

        for line in tasks_to_run:
            if not line.strip(): 
                continue
            parts = line.rstrip('\r\n').split('\t')
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
            
            success = self.download_task(rj_code, link, pwd, passwords)
            if success:
                print(f"Task finished: {rj_code}")

if __name__ == "__main__":
    downloader = PCSDownloader()
    downloader.process_list()
