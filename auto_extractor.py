import os
import subprocess
import re
import shutil
from pathlib import Path
import config

class AutoExtractor:
    def __init__(self, seven_zip_path=None):
        self.seven_zip_path = seven_zip_path or config.SEVEN_ZIP_PATH

    def get_archive_type_from_magic(self, file_path: Path) -> str:
        if not file_path.is_file():
            return None
            
        try:
            with file_path.open('rb') as f:
                header = f.read(8)
            
            # ZIP
            if header.startswith(b'\x50\x4B\x03\x04'):
                return '.zip'
            # RAR / RAR5
            if header.startswith(b'\x52\x61\x72\x21\x1A\x07'):
                return '.rar'
            # 7z
            if header.startswith(b'\x37\x7A\xBC\xAF\x27\x1C'):
                return '.7z'
                
        except Exception as e:
            pass
            
        return None

    def is_archive(self, file_path: Path) -> bool:
        return self.get_archive_type_from_magic(file_path) is not None

    def fix_missing_extensions(self, directory: Path):
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                if self.is_ignored_volume(file_path):
                    continue
                # Only append extension if it literally has no extension
                if not file_path.suffix:
                    ext = self.get_archive_type_from_magic(file_path)
                    if ext:
                        new_path = file_path.with_name(file_path.name + ext)
                        file_path.rename(new_path)
                        print(f"Added missing extension {ext}: {file_path.name} -> {new_path.name}")

    def is_ignored_volume(self, file_path: Path) -> bool:
        name = file_path.name.lower()
        
        # Ignored: part2~part99, part02~part99 (but NOT part1 or part01)
        part_match = re.search(r'\.part(\d+)\.rar$', name)
        if part_match:
            vol_num = int(part_match.group(1))
            if vol_num > 1:
                return True
                
        # Ignored: .002~.999 (but NOT .001)
        num_match = re.search(r'\.(\d{3})$', name)
        if num_match:
            vol_num = int(num_match.group(1))
            if vol_num > 1:
                return True
                
        # Ignored: zip splits .z01, .z02
        z_match = re.search(r'\.z(\d{2,})$', name)
        if z_match:
            vol_num = int(z_match.group(1))
            if vol_num > 0:
                return True
                
        return False

    def delete_related_volumes(self, archive: Path):
        try:
            stem = archive.stem
            # RAR splits: .part1.rar => .part*.rar
            part_match = re.search(r'(.*)\.part0*1$', stem, re.I)
            if part_match and archive.suffix.lower() == '.rar':
                base_name = part_match.group(1)
                for f in archive.parent.glob(f"{base_name}.part*.rar"):
                    f.unlink()
                    print(f"Deleted volume: {f.name}")
                return
                
            # 7z or rar splits: .001 => .* / .\d{3}
            if archive.suffix == '.001':
                for f in archive.parent.glob(f"{stem}.*"):
                    if re.match(r'^\.\d{3}$', f.suffix):
                        f.unlink()
                        print(f"Deleted volume: {f.name}")
                return
                
            # ZIP splits: .zip => .z01, .z02 etc.
            if archive.suffix.lower() == '.zip':
                # Delete main zip
                archive.unlink()
                print(f"Deleted volume: {archive.name}")
                # Delete .z01, .z02
                for f in archive.parent.glob(f"{stem}.z*"):
                    if re.match(r'^\.z\d{2,}$', f.suffix, re.I):
                        f.unlink()
                        print(f"Deleted volume: {f.name}")
                return
                
            # Fallback for single file
            archive.unlink()
            print(f"Deleted original archive: {archive.name}")
        except Exception as e:
            print(f"Failed to delete {archive.name} or its volumes: {e}")

    def _count_extracted_files(self, dir_path: Path) -> int:
        count = 0
        for root, dirs, files in os.walk(dir_path):
            count += len(files)
        return count

    def get_top_level_archives(self, target_dir: Path) -> list:
        # No longer used
        pass

    def _extract_passwords_from_filename(self, filename: str) -> list:
        # Regex to catch pw_xxx, 密码xxx, 解压码0419, etc.
        import re
        matches = re.findall(r'(?i)(?:pw|password|密码|解压码|提取码)[_:\-\s]*([a-zA-Z0-9@#\*\.,]+)', filename)
        return matches

    def extract_with_7z(self, archive_path: Path, dest_dir: Path, passwords: list) -> bool:
        # Check filename/dirname for explicit passwords (use stem to ignore extension)
        filename_pwds = self._extract_passwords_from_filename(archive_path.stem)
        if hasattr(archive_path, 'parent') and archive_path.parent:
            filename_pwds += self._extract_passwords_from_filename(archive_path.parent.name)
            
        combined_passwords = passwords + filename_pwds
        
        if not combined_passwords:
            pwds_to_try = [""]
        else:
            # Deduplicate while preserving order
            pwds_to_try = []
            for p in combined_passwords:
                if p not in pwds_to_try:
                    pwds_to_try.append(p)
            if "" not in pwds_to_try:
                pwds_to_try.append("")

        for pwd in pwds_to_try:
            cmd = [self.seven_zip_path, 'x', str(archive_path), f'-o{str(dest_dir)}', '-y']
            if pwd:
                cmd.append(f'-p{pwd}')
                
            print(f"Trying extraction for {archive_path.name} with password: '{pwd}'")
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL)
            
            if result.returncode in [0, 1]:
                print(f"Successfully extracted {archive_path.name}")
                if result.returncode == 1:
                    print(f"Extraction warning: {result.stdout}")
                return True
        
        print(f"Failed to extract {archive_path.name} with all passwords.")
        if 'result' in locals():
            print(f"Last extraction output:\n{result.stdout}\n{result.stderr}")
        return False

    def reorganize_based_on_chain(self, target_dir: Path, final_node: Path):
        if not final_node or not final_node.exists() or final_node == target_dir:
            return

        base_rj = target_dir.name.upper()
        
        # Check if ANY part of the path from target_dir to final_node is a divergent RJ code.
        try:
            rel_path = final_node.relative_to(target_dir)
            for part in rel_path.parts:
                part_upper = part.upper()
                if re.match(r'^[RV]J\d+$', part_upper) and part_upper != base_rj:
                    print(f"Skipping reorganization: found divergent RJ code '{part}' in path, requires manual intervention.")
                    return
        except ValueError:
            # final_node is not relative to target_dir, something weird happened
            pass

        # Drill down final_node if it natively contains exactly 1 directory that is the exact same RJ code
        while True:
            items = list(final_node.iterdir())
            if len(items) == 1 and items[0].is_dir() and items[0].name.upper() == base_rj:
                final_node = items[0]
            else:
                break

        for item in list(final_node.iterdir()):
            dest = target_dir / item.name
            if dest != item and not dest.exists():
                shutil.move(str(item), str(dest))
        
        # Cleanup ALL empty directories in target_dir
        for root, dirs, files in os.walk(target_dir, topdown=False):
            for name in dirs:
                d = Path(root) / name
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except Exception:
                    pass

    def extract_recursive(self, target_dir: Path, passwords: list) -> Path:
        if not target_dir.exists() or not target_dir.is_dir():
            return None
            
        print(f"\nScanning for archives in: {target_dir}")
        self.fix_missing_extensions(target_dir)
        
        archives = []
        for file_path in target_dir.rglob('*'):
            if file_path.is_file():
                if self.is_ignored_volume(file_path):
                    continue
                if self.is_archive(file_path):
                    archives.append(file_path)
                    
        if len(archives) == 1:
            archive = archives[0]
            dest_dir = archive.parent / archive.stem
            
            success = self.extract_with_7z(archive, dest_dir, passwords)
            if success:
                self.delete_related_volumes(archive)
                final_node = dest_dir
                
                file_count = self._count_extracted_files(dest_dir)
                print(f"Extracted file count: {file_count}")
                if file_count <= 5 and file_count > 0:
                    print(f"File count <= 5, checking for nested archives in {dest_dir}")
                    child_final = self.extract_recursive(dest_dir, passwords)
                    if child_final:
                        return child_final
                return final_node
        elif len(archives) > 1:
            print("Multiple archives found! Extracting all and skipping folder organization.")
            for arc in archives:
                d = arc.parent / arc.stem
                if self.extract_with_7z(arc, d, passwords):
                    self.delete_related_volumes(arc)
                    
                    file_count = self._count_extracted_files(d)
                    if file_count <= 5 and file_count > 0:
                        self.extract_recursive(d, passwords)
            return None
            
        return None
