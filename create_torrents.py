import os
import shutil
import torf
from pathlib import Path

def clean_garbage_files(directory):
    """
    清理垃圾文件和目录，对应提供的 bat 脚本规则
    """
    print(f"正在清理垃圾文件: {directory}")
    
    # --- 对应 del 指令 (删除文件) ---
    # 单文件类型删除指令
    file_patterns = [
        '*.rsrc', '*.*.rsrc',
        # 基础系统垃圾
        'Thumbs.db', 'desktop.ini', '.DS_Store', '._.',
        # 苹果系统残留
        '.VolumeIcon.icns'
    ]
    
    # 遍历所有匹配的文件并删除
    for pattern in file_patterns:
        for file_path in directory.rglob(pattern):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    print(f"已删除文件: {file_path}")
                except Exception as e:
                    print(f"删除文件失败 {file_path}: {e}")

    # --- 对应 del 指令 (特殊处理: .apdisk 和 .localized) ---
    # 注: 这两个在 macOS 中通常是目录，但在 bat 中用的是 del，这里做兼容处理
    special_items = ['.apdisk', '.localized']
    for item in special_items:
        for item_path in directory.rglob(item):
            try:
                if item_path.is_dir():
                    shutil.rmtree(item_path)
                    print(f"已删除目录: {item_path}")
                elif item_path.is_file():
                    item_path.unlink()
                    print(f"已删除文件: {item_path}")
            except Exception as e:
                print(f"清理失败 {item_path}: {e}")

    # --- 对应 rd 指令 (删除目录) ---
    dir_names = ['.AppleDouble', '.Spotlight-V100', '.Trashes']
    
    for d_name in dir_names:
        for dir_path in directory.rglob(d_name):
            if dir_path.is_dir():
                try:
                    shutil.rmtree(dir_path)
                    print(f"已删除目录: {dir_path}")
                except Exception as e:
                    print(f"删除目录失败 {dir_path}: {e}")
    
    print("垃圾文件清理完成。")

def create_torrents():
    # Configuration
    base_dir = Path("torrent")
    output_dir = Path("torrent_file")
    piece_size = 16 * 1024 * 1024  # 16MB

    # Ensure output directory exists
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        print(f"Created output directory: {output_dir}")

    # Check if base directory exists
    if not base_dir.exists():
        print(f"Error: Base directory '{base_dir}' does not exist.")
        return

    # --- 新增步骤：在制作种子前先清理垃圾文件 ---
    clean_garbage_files(base_dir)
    # ----------------------------------------

    # Iterate through subdirectories
    subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
    
    if not subdirs:
        print(f"No subdirectories found in {base_dir}")
        return

    print(f"Found {len(subdirs)} subdirectories to process.")

    for subdir in subdirs:
        try:
            print(f"Processing: {subdir.name}")
            
            # Create torrent object
            # torf will automatically handle the directory structure recursively
            t = torf.Torrent(path=str(subdir))
            
            # Set piece size
            t.piece_size = piece_size
            
            # Generate the torrent metadata
            # This hashes the files. It might take time for large files.
            t.generate()
            
            # Define output filename
            torrent_filename = f"{subdir.name}.torrent"
            output_path = output_dir / torrent_filename
            
            # Write to file
            t.write(str(output_path))
            print(f"Created: {output_path}")
            
        except Exception as e:
            print(f"Failed to create torrent for {subdir.name}: {e}")

if __name__ == "__main__":
    create_torrents()