import os
import io
import struct
import tempfile
import zipfile
import subprocess
import string
import random
import unicodedata

try:
    import pyzipper
except ImportError:
    pyzipper = None

def sanitize_path(path: str) -> str:
    if not path:
        return ""
    path = path.replace('\xa0', ' ')
    path = ''.join(c for c in path if unicodedata.category(c)[0] != 'C')
    path = path.strip().strip('\u3000')
    invalid_chars = '<>:"|?*'
    for char in invalid_chars:
        path = path.replace(char, '_')
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1,10)] + [f'LPT{i}' for i in range(1,10)]
    path_parts = path.split('/')
    cleaned_parts = []
    for part in path_parts:
        part = part.strip('. ')
        if part.upper() in reserved_names:
            part = f"_{part}_"
        cleaned_parts.append(part)
    path = '/'.join(cleaned_parts)
    path = path.rstrip('.')
    if len(path) > 255:
        name, ext = os.path.splitext(path)
        path = name[:255-len(ext)] + ext
    return path

class StegoExtractor:
    def __init__(self, tools_dir=None):
        self.mkvmerge_exe = os.path.join(tools_dir, 'mkvmerge.exe') if tools_dir else 'mkvmerge'
        self.mkvextract_exe = os.path.join(tools_dir, 'mkvextract.exe') if tools_dir else 'mkvextract'
        self.mkvinfo_exe = os.path.join(tools_dir, 'mkvinfo.exe') if tools_dir else 'mkvinfo'

    def log(self, msg):
        print(f"[StegoExtractor] {msg}")

    def reveal(self, input_file_path, passwords):
        """核心解隐入口，尝试不同方法提取隐藏在音视频中的压缩包"""
        file_extension = os.path.splitext(input_file_path.lower())[1]
        output_dir = os.path.dirname(input_file_path)
        if not output_dir: output_dir = '.'
        
        methods = []
        if file_extension in ['.mp4', '.m4v', '.mov', '.webm']:
            methods.extend([
                ('mp4_zarchiver', self.extract_with_offset_correction),
                ('mp4_trailing', self._try_mp4_direct_extraction),
                ('free_atom', self.extract_from_free_atom)
            ])
        if file_extension in ['.mkv', '.webm']:
            methods.append(('mkv_attachment', self._try_mkv_extraction))
            
        if not methods:
            methods.extend([
                ('mp4_zarchiver', self.extract_with_offset_correction),
                ('mp4_trailing', self._try_mp4_direct_extraction),
                ('free_atom', self.extract_from_free_atom),
                ('mkv_attachment', self._try_mkv_extraction)
            ])

        success = False
        passwords = list(dict.fromkeys(passwords))
        if '' not in passwords:
            passwords.append('')

        for method_name, method_func in methods:
            if success:
                break
            self.log(f"Trying method: {method_name}...")
            try:
                if method_func(input_file_path, output_dir, passwords):
                    success = True
                    self.log(f"Extraction successful using {method_name}")
                    break
            except Exception as e:
                self.log(f"Method {method_name} failed with error: {e}")

        if success:
            try:
                os.remove(input_file_path)
                self.log("Original file removed successfully.")
            except Exception as e:
                self.log(f"Failed to remove original file: {e}")
            return True
        return False

    def _try_mp4_direct_extraction(self, input_file_path, output_dir, passwords):
        for pwd in passwords:
            pwd_bytes = pwd.encode('utf-8') if pwd else None
            try:
                if self._extract_with_zipfile(input_file_path, pwd_bytes, output_dir):
                    return True
            except Exception:
                pass
            
            if pyzipper:
                try:
                    if self._extract_with_pyzipper(input_file_path, pwd_bytes, output_dir):
                        return True
                except Exception:
                    pass
        return False

    def _extract_zip_members(self, zip_file, output_dir):
        for name in zip_file.namelist():
            clean_name = sanitize_path(name)
            if not clean_name: continue
            out_path = os.path.join(output_dir, clean_name)
            if name.endswith('/'):
                os.makedirs(out_path, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            if os.path.exists(out_path):
                base, ext = os.path.splitext(out_path)
                chars = string.ascii_letters + string.digits
                out_path = f"{base}_{''.join(random.choice(chars) for _ in range(6))}{ext}"
            with zip_file.open(name) as src, open(out_path, 'wb') as dst:
                while True:
                    chunk = src.read(8 * 1024 * 1024)
                    if not chunk: break
                    dst.write(chunk)

    def _extract_with_zipfile(self, file_path, pwd_bytes, output_dir):
        with open(file_path, "rb") as f:
            with zipfile.ZipFile(f, 'r') as zf:
                if pwd_bytes: zf.setpassword(pwd_bytes)
                namelist = zf.namelist()
                if not namelist: return False
                try:
                    first = [name for name in namelist if not name.endswith('/')][0]
                    with zf.open(first) as test:
                        test.read(1024)
                except RuntimeError as e:
                    if 'password' in str(e).lower() or 'Bad password' in str(e):
                        return False
                    raise
                self._extract_zip_members(zf, output_dir)
        return True

    def _extract_with_pyzipper(self, file_path, pwd_bytes, output_dir):
        with open(file_path, "rb") as f:
            with pyzipper.AESZipFile(f, 'r') as zf:
                if pwd_bytes: zf.setpassword(pwd_bytes)
                namelist = zf.namelist()
                if not namelist: return False
                try:
                    first = [name for name in namelist if not name.endswith('/')][0]
                    with zf.open(first) as test:
                        test.read(1024)
                except RuntimeError as e:
                    if 'password' in str(e).lower() or 'Bad password' in str(e):
                        return False
                    raise
                self._extract_zip_members(zf, output_dir)
        return True

    def extract_with_offset_correction(self, file_path, output_dir, passwords):
        try:
            with open(file_path, 'rb') as f:
                header = f.read(12)
                if len(header) < 12: return False
                size = struct.unpack('>I', header[:4])[0]
                atom_type = header[4:8].decode('ascii', errors='ignore')
                if atom_type != 'ftyp': return False
                f.seek(size)
                while True:
                    pos = f.tell()
                    h = f.read(8)
                    if len(h) < 8: break
                    atom_size = struct.unpack('>I', h[:4])[0]
                    atom_t = h[4:8].decode('ascii', errors='ignore')
                    if atom_t == 'free':
                        if atom_size > 8:
                            free_data = f.read(atom_size - 8)
                            if free_data.startswith(b'PK\x03\x04') and pyzipper:
                                success = False
                                for pwd in passwords:
                                    try:
                                        zip_buffer = io.BytesIO(free_data)
                                        with pyzipper.AESZipFile(zip_buffer, 'r') as zf:
                                            if pwd: zf.setpassword(pwd.encode())
                                            self._extract_zip_members(zf, output_dir)
                                            success = True
                                            break
                                    except Exception:
                                        continue
                                if success: return True
                    else:
                        if atom_size <= 8: break
                        f.seek(pos + atom_size)
        except Exception as e:
            self.log(f"ZArchiver extraction failed: {e}")
        return False

    def read_mp4_atoms(self, file_path):
        atoms = []
        with open(file_path, 'rb') as f:
            while True:
                header = f.read(8)
                if len(header) < 8: break
                size = struct.unpack('>I', header[:4])[0]
                atom_type = header[4:8].decode('ascii', errors='ignore')
                if size == 1:
                    l_size = struct.unpack('>Q', f.read(8))[0]
                    atoms.append({'type': atom_type, 'size': l_size, 'offset': f.tell() - 16, 'header_size': 16})
                    f.seek(f.tell() + l_size - 16)
                elif size == 0:
                    c_pos = f.tell()
                    f.seek(0, 2)
                    f_size = f.tell()
                    atoms.append({'type': atom_type, 'size': f_size - c_pos + 8, 'offset': c_pos - 8, 'header_size': 8})
                    break
                else:
                    atoms.append({'type': atom_type, 'size': size, 'offset': f.tell() - 8, 'header_size': 8})
                    f.seek(f.tell() + size - 8)
        return atoms

    def extract_from_free_atom(self, file_path, output_dir, passwords):
        try:
            atoms = self.read_mp4_atoms(file_path)
            target = next((a for a in atoms if a['type'] == 'free' and a['size'] > 1024), None)
            if not target: return False
            with open(file_path, 'rb') as f:
                f.seek(target['offset'] + target['header_size'])
                hidden_data = f.read(target['size'] - target['header_size'])
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as t:
                t_path = t.name
                t.write(hidden_data)
            
            try:
                for pwd in passwords:
                    try:
                        if pyzipper:
                            with pyzipper.AESZipFile(t_path, 'r') as zf:
                                if pwd: zf.setpassword(pwd.encode())
                                if zf.namelist():
                                    self._extract_zip_members(zf, output_dir)
                                    return True
                    except Exception:
                        pass
                    try:
                        with zipfile.ZipFile(t_path, 'r') as zf:
                            if pwd: zf.setpassword(pwd.encode())
                            if zf.namelist():
                                self._extract_zip_members(zf, output_dir)
                                return True
                    except Exception:
                        pass
            finally:
                if os.path.exists(t_path): os.unlink(t_path)
        except Exception as e:
            self.log(f"Free atom extraction failed: {e}")
        return False

    def _try_mkv_extraction(self, input_file_path, output_dir, passwords):
        try:
            cmd = [self.mkvinfo_exe, input_file_path]
            r = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
            lines = r.stdout.splitlines()
            att_name = None
            for idx, line in enumerate(lines):
                if "MIME" in line:
                    att_name = lines[idx-1].split(':')[-1].strip()
                    break
            if not att_name: return False

            out_path = os.path.join(output_dir, att_name)
            cmd_ext = [self.mkvextract_exe, 'attachments', input_file_path, f'1:{out_path}']
            subprocess.run(cmd_ext, check=True, capture_output=True)

            if out_path.endswith('.zip') and pyzipper:
                success = False
                for pwd in passwords:
                    try:
                        with pyzipper.AESZipFile(out_path, 'r') as zf:
                            if pwd: zf.setpassword(pwd.encode())
                            self._extract_zip_members(zf, output_dir)
                        os.remove(out_path)
                        return True
                    except Exception:
                        continue
                return False
            return True
        except Exception as e:
            self.log(f"MKV extraction failed: {e}")
            return False
