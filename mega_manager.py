import subprocess
import os
import time
import re
from pathlib import Path
import config

class MegaDownloader:
    def __init__(self):
        self.base_dir = config.BASE_DIR
        self.mega_list_file = self.base_dir / config.MEGA_LIST_FILE_NAME
        self.target_parent_dir = self.base_dir / config.BAIDU_USERNAME
        
        # 确保目标父目录存在
        if not self.target_parent_dir.exists():
            self.target_parent_dir.mkdir(parents=True, exist_ok=True)

    def run_command(self, args, cwd=None):
        """执行命令，默认在当前工作目录，可选指定 cwd"""
        cmd = args
        print(f"Executing: {' '.join(cmd)} in {cwd or os.getcwd()}")
        # shell=True 在 windows 上更好用，特别是如果 megatools 在 PATH 中
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', cwd=cwd, shell=True)
        return result

    def rename_large_files(self, directory_path):
        """校验并重命名超过 500MB 的 pdf 或 z 或 png 文件为 7z"""
        path = Path(directory_path)
        if not path.exists():
            return
        
        threshold = 500 * 1024 * 1024  # 500MB
        target_extensions = {'.pdf', '.z', '.png'}
        count = 0
        
        print(f"Checking files in {directory_path} for renaming...")
        for file_path in path.rglob('*'):
            if file_path.is_file():
                if file_path.suffix.lower() in target_extensions:
                    try:
                        file_size = file_path.stat().st_size
                        if file_size > threshold:
                            new_path = file_path.with_suffix('.7z')
                            # 处理同名冲突
                            if new_path.exists():
                                new_path = file_path.with_name(f"{file_path.stem}_{int(time.time())}.7z")
                            file_path.rename(new_path)
                            print(f"[Rename] {file_path.name} -> {new_path.name} (Size: {file_size / 1024 / 1024:.2f}MB)")
                            count += 1
                    except Exception as e:
                        print(f"[Error] Failed to rename {file_path.name}: {e}")
        
        if count > 0:
            print(f"Total renamed files: {count}")
        else:
            print("No files matched the renaming criteria.")

    def download_task(self, rj_code, link, passwords=None):
        """执行单个下载任务"""
        print(f"\n--- Starting task for {rj_code} ---")
        
        # 1. 创建 RJ 号命名的文件夹
        rj_dir = self.target_parent_dir / rj_code
        if not rj_dir.exists():
            rj_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created directory: {rj_dir}")
        else:
            print(f"Directory already exists: {rj_dir}")

        # 2. 调用 megatools 下载 (在 rj_dir 目录下执行)
        # megatools dl <link>
        print(f"Downloading {link} into {rj_dir}...")
        
        # 记录开始时间以判断是否下载成功（或者通过返回值）
        start_time = time.time()
        
        # megatools dl 默认下载到当前目录
        result = self.run_command(['megatools', 'dl', link], cwd=str(rj_dir))
        
        if result.returncode != 0:
            print(f"Download failed for {rj_code}. Error: {result.stderr}")
            return False
        
        print(f"Download completed for {rj_code}.")

        # 3. 校验并重命名大文件
        self.rename_large_files(rj_dir)
        
        # 4. 自动解压
        from auto_extractor import AutoExtractor
        extractor = AutoExtractor()
        
        final_node = extractor.extract_recursive(rj_dir, passwords or [])
        
        if final_node:
            extractor.reorganize_based_on_chain(rj_dir, final_node)
            
        return True

    def process_list(self):
        if not self.mega_list_file.exists():
            print(f"No {self.mega_list_file.name} found.")
            return

        with open(self.mega_list_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            print("mega.txt is empty.")
            return

        processed_count = 0
        
        # 逐行处理
        for i, line in enumerate(lines):
            if not line.strip(): 
                continue
            
            parts = line.rstrip('\r\n').split('\t')
            # 格式：RJ号、下载链接、提取码、发布者、相关帖子链接、解压密码
            if len(parts) < 5:
                print(f"Skipping malformed or old format line: {line.rstrip('\r\n')}")
                continue
            
            rj_code = parts[0].upper()
            link = parts[1]
            pwd = parts[2]
            nickname = parts[3]
            post_url = parts[4]
            passwords = parts[5:] if len(parts) > 5 else []
            
            if not passwords:
                passwords.append(rj_code)
            elif passwords == [""]:
                passwords[0] = rj_code
            elif rj_code not in passwords:
                passwords.append(rj_code)

            success = self.download_task(rj_code, link, passwords)
            if success:
                print(f"Successfully processed {rj_code}.")
                processed_count += 1
            else:
                print(f"Failed to process {rj_code}.")

        print(f"\nProcessing finished. {processed_count} tasks completed.")

if __name__ == "__main__":
    downloader = MegaDownloader()
    downloader.process_list()
