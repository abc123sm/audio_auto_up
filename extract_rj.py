import re
from pathlib import Path

base = Path(__file__).resolve().parent
input_path = base / "audio.txt"
output_path = base / "RJ_list.txt"

# 读取已有的 RJ 号，保持原有顺序
existing_items = []
if output_path.exists():
    existing_items = output_path.read_text(encoding="utf-8").splitlines()

# 提取 audio.txt 中的所有 RJ 号
text = input_path.read_text(encoding="utf-8")
matches = re.findall(r"(?:RJ|VJ|BJ)\d{5,12}\b", text)

# 过滤掉已存在的 RJ 号，并保持新项目的顺序
seen = set(existing_items)
new_items = []
for item in matches:
    if item not in seen:
        new_items.append(item)
        seen.add(item)

# 如果有新内容，则更新 RJ_list.txt
if new_items:
    updated_list = existing_items + new_items
    output_path.write_text("\n".join(updated_list) + "\n", encoding="utf-8")
    print(f"已添加 {len(new_items)} 个新的 RJ 号到 {output_path.name}")
else:
    print("没有发现新的 RJ 号")
