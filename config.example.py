import os
from pathlib import Path

# ==========================================
# 基础路径配置
# ==========================================
BASE_DIR = Path(r'') # 填写你的主目录路径，例如：r'c:\code\audio_auto_up\audio_auto_up'

# ==========================================
# 工具及执行文件路径
# ==========================================
SEVEN_ZIP_PATH = r"" # 填写7z路径，例如： SEVEN_ZIP_PATH = r"C:\Program Files\7-Zip-Zstandard\7z.exe"
PCS_PATH = str(BASE_DIR / 'BaiduPCS-Go.exe')

# ==========================================
# 个人账号与网盘配置
# ==========================================
BAIDU_USERNAME = '' # 填写你的百度网盘用户名 如 BAIDU_USERNAME = 'abc123'
BAIDU_DOWNLOAD_PATH = '' # 填写你的百度网盘保存路径 如 BAIDU_DOWNLOAD_PATH = '/kame/voice'
PROXY_SETTING = '' # 下载时使用的代理，不需要代理可留空 例如: PROXY_SETTING = '127.0.0.1:10805'

# ==========================================
# qBittorrent 配置
# ==========================================
QB_URL = "" # 填写qBittorrent地址 如 QB_URL = "http://127.0.0.1:123456"
QB_USER = "" # 填写qBittorrent用户名 如 QB_USER = "abc123"
QB_PASS = "" # 填写qBittorrent密码 如 QB_PASS = "abc123456"

# ==========================================
# 爬虫与上传相关地址
# ==========================================
SOUTH_PLUS_BASE_URL = "https://bbs.white-plus.net/" # 你能打开的男+网址
KAMEPT_UPLOAD_URL = "https://kamept.com/upload.php"
KAMEPT_TAKE_UPLOAD_URL = "https://kamept.com/takeupload.php"
KAMEPT_AJAX_URL = "https://kamept.com/ajax.php"

# ==========================================
# 内部文件与目录命名配置
# ==========================================
# 目录名
TORRENT_SOURCE_DIR_NAME = "torrent" # 等待发布的资料夹名称
FILE_DEST_DIR_NAME = "file" # 发布后的资料夹名称（建议与上面的资料夹分开，方便区分，也避免重复发布）
TORRENT_FILE_DIR_NAME = "torrent_file" # 自动生成的种子文件存放目录，发布成功后会删除种子文件
TORRENT_DOWNLOAD_DIR_NAME = "torrent_file_download" # 自动下载的种子文件存放目录，发布成功后会删除种子文件

# 文件名
SOUTH_PLUS_COOKIES_FILE_NAME = 'nanjia.txt' # 南+ cookies文件名称（可使用HAR格式或curl命令文本格式），用于获取南+账号权限
DL_LIST_FILE_NAME = 'dl_list.txt' # dl_list文件名称，用于获取下载链接
RJ_LIST_FILE_NAME = 'RJ_list.txt' # RJ_list文件名称，用于获取下载链接
MEGA_LIST_FILE_NAME = 'mega.txt' # mega.txt文件名称，用于获取下载链接
JIEYA_FILE_NAME = 'jieya.txt' # 解压密码文件名称，保存所有自动抓取的解压密码（可能有错）
KAMEPT_COOKIES_FILE_NAME = 'kamept_cookies.txt' # KamePT cookies文件名称，用于获取上传权限
