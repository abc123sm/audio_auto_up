import sys
import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import datetime
from pathlib import Path
import html
from har_parser import get_auth_from_har
import config

class SouthPlusCrawler:
    def __init__(self, cookie_path=None):
        self.base_dir = config.BASE_DIR
        self.rj_list_file = self.base_dir / config.RJ_LIST_FILE_NAME
        self.jieya_file = self.base_dir / config.JIEYA_FILE_NAME
        self.dl_list_file = self.base_dir / config.DL_LIST_FILE_NAME
        self.mega_file = self.base_dir / config.MEGA_LIST_FILE_NAME
        
        self.base_url = config.SOUTH_PLUS_BASE_URL
        self.session = requests.Session()
        cookie_path = cookie_path or config.SOUTH_PLUS_COOKIES_FILE_NAME
        ua, cookie = get_auth_from_har(str(self.base_dir / cookie_path))
        if not ua or not cookie:
            raise Exception("Failed to extract UA or Cookie from HAR file.")
        
        self.session.headers.update({
            'User-Agent': ua,
            'Cookie': cookie,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        })
        
        self.existing_rj = self._load_rj_list()
        self.existing_mega_links = self._load_mega_list()

    def _load_rj_list(self):
        if not self.rj_list_file.exists():
            return set()
        with open(self.rj_list_file, 'r', encoding='utf-8') as f:
            return {line.strip().upper() for line in f if line.strip()}

    def _load_mega_list(self):
        if not self.mega_file.exists():
            return set()
        links = set()
        with open(self.mega_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 6:
                    links.add(parts[1])
        return links


    def _save_rj(self, rj_code):
        with open(self.rj_list_file, 'a', encoding='utf-8') as f:
            f.write(f"{rj_code}\n")
        self.existing_rj.add(rj_code.upper())

    def _save_jieya(self, password):
        if not password:
            return
        if re.search(r'RJ号|RJ码', password, re.I) or re.match(r'^[RV]J\d{5,12}$', password, re.IGNORECASE):
            return
            
        # 去重保存解压密码
        existing_passwords = set()
        if self.jieya_file.exists():
            with open(self.jieya_file, 'r', encoding='utf-8') as f:
                existing_passwords = {line.strip() for line in f if line.strip()}
        
        if password not in existing_passwords:
            with open(self.jieya_file, 'a', encoding='utf-8') as f:
                f.write(f"{password}\n")
            print(f"Added new password to jieya.txt: {password}")

    def _save_dl_list(self, info):
        # 字段顺序：编号（RJ/VJ）、分享链接、提取码或空、发布者昵称、帖子URL、所有解压密码（如果有多个依然用\t分隔）
        # 假设 info['links'] 是列表，我们处理第一个
        link_data = info['links'][0] if info['links'] else {'link': '', 'pwd': ''}
        
        passwords_str = '\t'.join(info.get('passwords', []))
        
        line = f"{info['rj_code']}\t{link_data['link']}\t{link_data['pwd']}\t{info['nickname']}\t{info['post_url']}\t{passwords_str}\n"
        with open(self.dl_list_file, 'a', encoding='utf-8') as f:
            f.write(line)

    def get_thread_list(self, page=1):
        url = f"{self.base_url}thread.php?fid-128-page-{page}.html"
        print(f"Fetching thread list: {url}")
        resp = self.session.get(url)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        threads = []
        rows = soup.find_all('tr', class_=re.compile(r'tr3'))
        for row in rows:
            # 查找所有链接到 tid 的 a 标签
            links = row.find_all('a', href=re.compile(r'tid-(\d+)'))
            title = ""
            tid = ""
            for link in links:
                text = link.get_text(strip=True)
                if text and len(text) > 5: # 标题通常较长
                    title = text
                    tid_match = re.search(r'tid-(\d+)', link.get('href'))
                    if tid_match:
                        tid = tid_match.group(1)
                    break
            
            if tid and title:
                threads.append({
                    'tid': tid,
                    'title': title,
                    'url': f"{self.base_url}read.php?tid={tid}"
                })
        return threads

    def _get_op_uid(self, soup):
        # 方法1: 从"只看GF"链接中提取 (最可靠)
        gf_link = soup.find('a', string=re.compile(r'只看GF|只看楼主'))
        if gf_link and gf_link.get('href'):
            uid_match = re.search(r'uid[-=](\d+)', gf_link['href'])
            if uid_match:
                return uid_match.group(1)
        
        # 方法2: 从主楼 read_tpc 的父级 tr 行中提取
        first_div = soup.find('div', id='read_tpc')
        if not first_div:
            first_div = soup.find('div', class_='tpc_content')
            
        if first_div:
            parent_row = first_div.find_parent(class_=re.compile(r'tr[13]'))
            if parent_row:
                uid_tag = parent_row.find('a', href=re.compile(r'uid[-=](\d+)'))
                if uid_tag:
                    uid_match = re.search(r'uid[-=](\d+)', uid_tag['href'])
                    if uid_match:
                        return uid_match.group(1)
        return None

    def parse_post_content(self, tid):
        url = f"{self.base_url}read.php?tid={tid}"
        resp = self.session.get(url)
        resp.encoding = 'utf-8'
        content = resp.text
        soup = BeautifulSoup(content, 'html.parser')
        
        gf_uid = self._get_op_uid(soup)

        # 寻找所有可能的购买选项
        candidates = []
        post_divs = soup.find_all('div', id=re.compile(r'read_'))
        
        all_op_prices = []
        op_div_strs = []

        for div in post_divs:
            if gf_uid:
                parent_row = div.find_parent(class_=re.compile(r'tr[13]'))
                if parent_row:
                    uid_tag = parent_row.find('a', href=re.compile(r'uid[-=](\d+)'))
                    if uid_tag:
                        uid_match = re.search(r'uid[-=](\d+)', uid_tag['href'])
                        if uid_match and uid_match.group(1) != gf_uid:
                            continue # 不是楼主的帖子，跳过

            # 价格通常在 div 内部的 quote 块中，或者紧邻 div 的头部
            # 这里简单处理：在 div 及其 HTML 字符串中搜索
            div_str = str(div)
            op_div_strs.append(div_str)
            
            # 记录楼主的所有标价，用于后续保底
            all_op_prices.extend(re.findall(r'此帖售价\s*(\d+)\s*SP币(?:,已有|，已有)', div_str))

            price_match = re.search(r'此帖售价\s*(\d+)\s*SP币(?:,已有|，已有)', div_str)
            if price_match:
                price = int(price_match.group(1))
                # 查找该 div 对应的购买链接
                buy_match = re.search(r"location\.href='(job\.php\?action=buytopic[^']+)'", div_str)
                if buy_match:
                    buy_url = self.base_url + buy_match.group(1)
                    buy_url = html.unescape(buy_url)
                    candidates.append({'price': price, 'buy_url': buy_url})

        # 提取价格（用于显示或逻辑判断，如果有多个购买项，优先展示最合理的）
        final_price = 0
        buy_urls = []
        
        # 全局搜索所有价格，防止漏掉没有购买链接但标价便宜的内容（可能是已购买）
        min_text_price = min([int(x) for x in all_op_prices]) if all_op_prices else float('inf')
        force_purchased = False

        if candidates:
            # 按价格排序
            candidates.sort(key=lambda x: x['price'])
            
            # 优先选择 < 6 SP 的（用户需求）
            reasonable = [c for c in candidates if c['price'] < 6]
            if reasonable:
                buy_urls = [c['buy_url'] for c in reasonable]
                # 记录其中的最大价格作为显示参考
                final_price = max(c['price'] for c in reasonable)
            else:
                best = candidates[0] # 如果都很贵，选最便宜的
                final_price = best['price']
                buy_urls = [best['buy_url']]

                # 关键修正：如果候选价格都很贵，但全文存在便宜价格（<6），
                # 说明可能存在已购买的便宜内容（没有购买链接），或者解析漏了。
                # 这种情况下，优先信任全文中的低价，并假设已购买/可获取。
                if final_price >= 6 and min_text_price < 6:
                    print(f"Found expensive candidate ({final_price} SP) but cheap text price ({min_text_price} SP). Preferring cheap text price.")
                    final_price = min_text_price
                    buy_urls = [] # 既然是文本价格，没有对应的 buy_url
                    force_purchased = True
                
            if final_price >= 6:
                print(f"Price {final_price} >= 6, refuse to buy")
                buy_urls = []
        else:
            # 如果没找到特定购买链接，尝试楼主范围搜索价格（可能是已购买或免费）
            if all_op_prices:
                nums = [int(x) for x in all_op_prices]
                reasonable = [n for n in nums if n < 1000]
                final_price = min(reasonable) if reasonable else min(nums)
            elif "免费" in content:
                final_price = 0
        
        # 检查是否已购买
        # 仅在楼主发布的楼层中检查是否还有 "愿意购买" 按钮
        op_content = "".join(op_div_strs)
        is_purchased = "愿意购买,我买,我付钱" not in op_content
        
        if force_purchased:
            is_purchased = True
        
        # 如果找到了明确的 buy_urls，那么针对该商品肯定是未购买的
        if buy_urls:
            is_purchased = False

        data = {
            'tid': tid,
            'price': final_price,
            'is_purchased': is_purchased,
            'content': content,
            'post_url': url
        }
        
        if buy_urls:
            data['buy_urls'] = buy_urls
        # 删除了全局搜索保底，防止在楼主已购买的情况下，误抓其他回复者的购买链接
        
        return data

    def buy_post(self, buy_url):
        print(f"Purchasing post: {buy_url}")
        resp = self.session.get(buy_url)
        if "交易成功" in resp.text or resp.status_code == 200:
            return True
        return False

    def extract_final_data(self, content, title=""):
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove quote headers (like "此帖售价...", "本帖隐藏的内容", "引用...") to prevent them from interrupting text flow
        for h6 in soup.find_all('h6', class_=re.compile(r'quote')):
            h6.decompose()
            
        plain_text = soup.get_text(separator=' ', strip=True)
        
        # 寻找所有相关内容块（主楼 + 楼主的回复）
        # 只提取楼主（GF）发布的内容，过滤其他人的回帖
        relevant_divs = soup.find_all('div', id=re.compile(r'read_(tpc|\d+)'))
        if not relevant_divs:
            relevant_divs = soup.find_all('div', class_='tpc_content')
        
        # --- 提取楼主 UID ---
        gf_uid = self._get_op_uid(soup)
        
        if gf_uid:
            print(f"Original poster UID: {gf_uid}")
            
        full_text_parts = []
        href_links = []
        purchase_text_parts = []
        
        for div in relevant_divs:
            # --- 过滤非楼主的帖子 ---
            if gf_uid:
                parent_row = div.find_parent(class_=re.compile(r'tr[13]'))
                if parent_row:
                    uid_tag = parent_row.find('a', href=re.compile(r'uid[-=](\d+)'))
                    if uid_tag:
                        uid_match = re.search(r'uid[-=](\d+)', uid_tag['href'])
                        if uid_match and uid_match.group(1) != gf_uid:
                            # 该帖子不是楼主发的，跳过
                            continue
            # 1. 显式提取 <a> 标签的 href
            for a in div.find_all('a', href=True):
                href = a['href']
                link_text = a.get_text(strip=True)
                if 'pan.baidu.com' in href:
                    href_links.append(href)
                    if 'pan.baidu.com' not in link_text:
                        # 插入到原 a 标签的后面，这样如果 a 标签在购买框内，URL 也会在框内
                        a.insert_after(soup.new_string(f" {href} "))
            
            # --- 收集购买框内的文本 ---
            for bq in div.find_all('blockquote', class_=re.compile(r'jumbotron|blockquote')):
                purchase_text_parts.append(bq.get_text(separator=' ', strip=True))
            
            # 移除图片标签本身但保留可能被错误解析成其子节点的文本
            for img in div.find_all('img'):
                img.unwrap()

            attr_values = []
            for el in div.find_all(True):
                for attr in ('data-clipboard-text', 'value', 'title', 'alt'):
                    if el.has_attr(attr):
                        value = el.get(attr)
                        if value:
                            attr_values.append(str(value))

            text = div.get_text(separator='\n', strip=True)
            if attr_values:
                text = text + "\n" + "\n".join(attr_values)
            full_text_parts.append(text)
            
        if not full_text_parts:
            # 保底：如果没找到特定 div，使用全文
            clean_text = soup.get_text(separator='\n', strip=True)
        else:
            clean_text = "\n".join(full_text_parts)
        clean_text = html.unescape(clean_text)
        clean_text = clean_text.replace('\u00a0', ' ').replace('\u3000', ' ')
        search_text = clean_text
            
        # 组装完整的购买框文本
        purchase_text = "\n".join(purchase_text_parts)
        purchase_text = html.unescape(purchase_text).replace('\u00a0', ' ').replace('\u3000', ' ')

        author_tag = soup.find('th', class_='r_two') or soup.find('th', class_='r_one')
        nickname = "Unknown"
        if author_tag:
            name_tag = author_tag.find('strong')
            if name_tag:
                nickname = name_tag.get_text(strip=True)
        
        # 1. 提取 RJ/VJ 号 - 强制优先从标题提取
        rj_codes = []
        if title:
            rj_codes = re.findall(r'[RV]J\d{5,12}', title, re.IGNORECASE)
        
        # 如果标题没找到，再从正文找作为保底
        if not rj_codes:
            rj_codes = re.findall(r'[RV]J\d{5,12}', clean_text, re.IGNORECASE)
        
        rj_code = rj_codes[0].upper() if rj_codes else "None"
        
        # 提取所有百度网盘链接
        baidu_links = []
        link_items = []
        # 使用 finditer 获取链接及其在文本中的位置
        link_pattern = r'https?://pan\.baidu\.com/s/([a-zA-Z0-9\-_]+)(?:\?pwd=([a-zA-Z0-9]{4}))?'
        matches = list(re.finditer(link_pattern, clean_text))
        lines = clean_text.split('\n')
        code_pattern = r'(?:提取码|提取碼|提取|提码)[:：\s]*([a-zA-Z0-9]{4})'
        code_matches = [(m.start(), m.group(1)) for m in re.finditer(code_pattern, clean_text, re.I)]
        
        if not matches and href_links:
            prev_end_href = 0
            for href in href_links:
                match = re.search(link_pattern, href)
                if not match:
                    continue
                link = match.group(0)
                link_id = match.group(1)
                start_pos = clean_text.find(link)
                in_clean_text = start_pos != -1
                if start_pos == -1:
                    start_pos = 0
                end_pos = start_pos + len(link)
                link_line_index = None
                link_line_context = ""
                chunk = clean_text[prev_end_href:start_pos]
                for i, line in enumerate(lines):
                    if link in line:
                        link_line_index = i
                        start_line = max(0, i - 2)
                        end_line = min(i + 3, len(lines))
                        link_line_context = "\n".join(lines[start_line:end_line])
                        
                        start_line_5 = max(0, i - 5)
                        start_pos_5_lines = sum(len(l) + 1 for l in lines[:start_line_5])
                        chunk_start = max(prev_end_href, start_pos_5_lines)
                        chunk = clean_text[chunk_start:start_pos]
                        break
                
                if in_clean_text:
                    context_start = max(0, start_pos - 200)
                    context_end = min(len(clean_text), end_pos + 200)
                    context = clean_text[context_start:context_end]
                else:
                    context = search_text
                
                pwd = ""
                has_pwd_in_url = bool(match.group(2))
                if has_pwd_in_url:
                    pwd = match.group(2)
                
                if not pwd and not has_pwd_in_url:
                    kw_pattern = r'(?:提取码|提取碼|提取|提码)[:：\s]*([a-zA-Z0-9]{4})'
                    kw_matches = re.findall(kw_pattern, context, re.I)
                    if kw_matches:
                        valid_pwds = [p for p in kw_matches if p not in link]
                        if valid_pwds:
                            pwd = valid_pwds[0]
                
                if not pwd and not has_pwd_in_url:
                    if link_line_index is not None:
                        for j in range(link_line_index, min(link_line_index + 4, len(lines))):
                            line_text = lines[j]
                            line_match = re.search(kw_pattern, line_text, re.I)
                            if line_match:
                                candidate = line_match.group(1)
                                if candidate not in link:
                                    pwd = candidate
                                    break
                
                if not pwd and not has_pwd_in_url and code_matches:
                    nearest = min(code_matches, key=lambda x: abs(x[0] - start_pos))
                    if nearest[1] not in link:
                        pwd = nearest[1]

                if not pwd and not has_pwd_in_url:
                    if purchase_text:
                        pt_match = re.search(r'(?<![a-zA-Z0-9])([a-zA-Z0-9]{4})(?![a-zA-Z0-9])', purchase_text.strip())
                        if pt_match:
                            cand_pwd = pt_match.group(1)
                            if cand_pwd not in link:
                                pwd = cand_pwd
                    if not pwd:
                        ctx_match = re.search(r'(?<![a-zA-Z0-9])([a-zA-Z0-9]{4})(?![a-zA-Z0-9])', clean_text)
                        if ctx_match:
                            cand_pwd = ctx_match.group(1)
                            if cand_pwd not in link:
                                pwd = cand_pwd
                
                final_link = link
                
                is_proof = False
                if link_line_index is not None:
                    curr_line = lines[link_line_index]
                    link_idx = curr_line.find(link)
                    pre_link_text = curr_line[:link_idx] if link_idx != -1 else curr_line
                    
                    if any(kw in pre_link_text for kw in ['自购证明', '自购', '证明']):
                        is_proof = True
                    
                    if not pre_link_text.strip() and link_line_index > 0:
                        prev_line = lines[link_line_index - 1]
                        if any(kw in prev_line for kw in ['自购证明', '自购', '证明']):
                            is_proof = True
                score = 0
                
                # 如果这个链接存在于购买框内，赋予绝对的最高优先级
                if purchase_text and link in purchase_text:
                    score += 10000

                if re.search(r'(?:原档|WAV|无损|Flac|本体|本篇)', chunk, re.I):
                    score += 10
                if re.search(r'(?:MP3|有损)', link_line_context, re.I):
                    score -= 2
                if re.search(r'(?:仅汉化|单汉化|单独汉化|仅补丁)', chunk, re.I):
                    score -= 5
                    
                if has_pwd_in_url:
                    score += 3
                if pwd:
                    score += 2
                if re.search(r'(?:提取码|提取|提码)', context, re.I):
                    score += 1
                if is_proof:
                    score -= 2
                if link_line_context:
                    if re.search(r'(?:失效|旧链|旧链接|原链|原链接|备用|备份|作废|废弃|补链前|换链前)', link_line_context):
                        score -= 2
                    if re.search(r'(?:补链|新链|新链接|更新|修复|补发|更换|改为)', link_line_context):
                        score += 1
                score += start_pos / max(1, len(clean_text))
                link_items.append({
                    'link': final_link,
                    'link_id': link_id,
                    'pwd': pwd,
                    'is_proof': is_proof,
                    'score': score,
                    'start_pos': start_pos
                })
                prev_end_href = end_pos
        
        prev_end = 0
        for match in matches:
            link = match.group(0)
            link_id = match.group(1)
            start_pos = match.start()
            end_pos = match.end()
            link_line_index = None
            link_line_context = ""
            chunk = clean_text[prev_end:start_pos]
            for i, line in enumerate(lines):
                if link in line:
                    link_line_index = i
                    # 包含前几行以捕捉 "原档" 等描述
                    start_line = max(0, i - 2)
                    end_line = min(i + 3, len(lines))
                    link_line_context = "\n".join(lines[start_line:end_line])
                    
                    start_line_5 = max(0, i - 5)
                    start_pos_5_lines = sum(len(l) + 1 for l in lines[:start_line_5])
                    chunk_start = max(prev_end, start_pos_5_lines)
                    chunk = clean_text[chunk_start:start_pos]
                    break
            
            # 定义搜索提取码的上下文范围（前后各 200 个字符）
            context_start = max(0, start_pos - 200)
            context_end = min(len(clean_text), end_pos + 200)
            context = clean_text[context_start:context_end]
            
            pwd = ""
            # 1. 首先检查链接本身是否带 pwd
            has_pwd_in_url = bool(match.group(2))
            if has_pwd_in_url:
                pwd = match.group(2)
            
            if not pwd and not has_pwd_in_url:
                # 2. 在上下文中寻找带关键字的提取码
                kw_pattern = r'(?:提取码|提取碼|提取|提码)[:：\s]*([a-zA-Z0-9]{4})'
                kw_matches = re.findall(kw_pattern, context, re.I)
                if kw_matches:
                    valid_pwds = [p for p in kw_matches if p not in link]
                    if valid_pwds:
                        pwd = valid_pwds[0]
            
            if not pwd and not has_pwd_in_url:
                if link_line_index is not None:
                    for j in range(link_line_index, min(link_line_index + 4, len(lines))):
                        line_text = lines[j]
                        line_match = re.search(kw_pattern, line_text, re.I)
                        if line_match:
                            candidate = line_match.group(1)
                            if candidate not in link:
                                pwd = candidate
                                break
            
            if not pwd and not has_pwd_in_url and code_matches:
                nearest = min(code_matches, key=lambda x: abs(x[0] - start_pos))
                if nearest[1] not in link:
                    pwd = nearest[1]

            if not pwd and not has_pwd_in_url:
                if purchase_text:
                    pt_match = re.search(r'(?<![a-zA-Z0-9])([a-zA-Z0-9]{4})(?![a-zA-Z0-9])', purchase_text.strip())
                    if pt_match:
                        cand_pwd = pt_match.group(1)
                        if cand_pwd not in link:
                            pwd = cand_pwd
                if not pwd:
                    ctx_match = re.search(r'(?<![a-zA-Z0-9])([a-zA-Z0-9]{4})(?![a-zA-Z0-9])', clean_text)
                    if ctx_match:
                        cand_pwd = ctx_match.group(1)
                        if cand_pwd not in link:
                            pwd = cand_pwd
            
            final_link = link
            
            # 优化 is_proof 判定：仅检查链接所在行或紧邻的前一行
            is_proof = False
            if link_line_index is not None:
                # 检查当前行
                curr_line = lines[link_line_index]
                # 截取链接前面的部分，避免匹配到链接后面的文字（虽然较少见）
                link_idx = curr_line.find(link)
                pre_link_text = curr_line[:link_idx] if link_idx != -1 else curr_line
                
                if any(kw in pre_link_text for kw in ['自购证明', '自购', '证明']):
                    is_proof = True
                
                # 如果链接位于行首（前面没有文字），检查上一行
                if not pre_link_text.strip() and link_line_index > 0:
                    prev_line = lines[link_line_index - 1]
                    if any(kw in prev_line for kw in ['自购证明', '自购', '证明']):
                        is_proof = True
            score = 0
            
            # 如果这个链接存在于购买框内，赋予绝对的最高优先级
            if purchase_text and link in purchase_text:
                score += 10000

            # 优先选择原档/WAV/无损/本体
            if re.search(r'(?:原档|WAV|无损|Flac|本体|本篇)', chunk, re.I):
                score += 10
            # 降低MP3优先级（如果有其他选择）
            if re.search(r'(?:MP3|有损)', link_line_context, re.I):
                score -= 2
            if re.search(r'(?:仅汉化|单汉化|单独汉化|仅补丁)', chunk, re.I):
                score -= 5
                
            if has_pwd_in_url:
                score += 3
            if pwd:
                score += 2
            if re.search(r'(?:提取码|提取|提码)', context, re.I):
                score += 1
            if is_proof:
                score -= 2
            if link_line_context:
                if re.search(r'(?:失效|旧链|旧链接|原链|原链接|备用|备份|作废|废弃|补链前|换链前)', link_line_context):
                    score -= 2
                if re.search(r'(?:补链|新链|新链接|更新|修复|补发|更换|改为)', link_line_context):
                    score += 1
            score += start_pos / max(1, len(clean_text))
            link_items.append({
                'link': final_link,
                'link_id': link_id,
                'pwd': pwd,
                'is_proof': is_proof,
                'score': score,
                'start_pos': start_pos
            })
            prev_end = end_pos
        
        if link_items:
            non_proof_links = [item for item in link_items if not item['is_proof']]
            selected = non_proof_links if non_proof_links else link_items
            selected_sorted = sorted(selected, key=lambda x: (x['score'], x['start_pos']), reverse=True)
            
            # 去重：保留分数最高的同ID链接
            seen_ids = set()
            unique_links = []
            for item in selected_sorted:
                if item['link_id'] not in seen_ids:
                    seen_ids.add(item['link_id'])
                    unique_links.append(item)
            
            baidu_links = [{'link': item['link'], 'pwd': item['pwd']} for item in unique_links]
        
        # 如果行内没找到提取码，尝试全局找一个（保底）
        if len(baidu_links) == 1 and not baidu_links[0]['pwd']:
            all_codes = re.findall(r'(?:提取码|提取碼|提取|提码)[:：\s]*([a-zA-Z0-9]{4})\b', search_text)
            unique_codes = list(dict.fromkeys(all_codes))
            if len(unique_codes) == 1:
                baidu_links[0]['pwd'] = unique_codes[0]

        # 解压密码
        passwords = []
        jieya_pwd = ""
        
        # 1. 更加宽松的匹配：匹配关键词后面跟着的内容
        # 支持中文、空格、特殊符号，并且支持跨行
        # 模式A: 关键词在同一行
        loose_jieya = re.search(r'(?:解压密码|解壓密碼|解压码|解壓碼|压缩包密码|压缩密码|密码|PW|解压|解壓)[:：\s]+([^\n]{1,})', search_text)
        if loose_jieya:
            pwd_candidate = loose_jieya.group(1).strip()
            # 排除一些明显的干扰（如百度网盘自带的“密码”提示）
            if "提取码" not in pwd_candidate and len(pwd_candidate) > 2:
                pwd_candidate = re.split(r'https?://', pwd_candidate)[0].strip()
                pwd_candidate = re.split(r'感谢|注意|说明|【|\[|分享|链接', pwd_candidate)[0].strip()
                if pwd_candidate:
                    jieya_pwd = pwd_candidate
        
        # 模式B: 关键词在上一行，内容在下一行
        if not jieya_pwd:
            lines = search_text.split('\n')
            for i, line in enumerate(lines):
                if re.search(r'^(?:解压密码|解壓密碼|解压码|解壓碼|压缩包密码|压缩密码|密码|PW|解压|解壓)[:：\s]*$', line.strip()):
                    if i + 1 < len(lines):
                        next_line = lines[i+1].strip()
                        if next_line and len(next_line) > 0 and "http" not in next_line:
                            jieya_pwd = next_line
                            break
        
        if jieya_pwd:
            if not re.search(r'RJ号|RJ码', jieya_pwd, re.I) and jieya_pwd.upper() != rj_code:
                passwords.append(jieya_pwd)

        # 优化正则：寻找解压密码关键字后的内容，支持中文和空格
        # 使用 \b 保护短关键字，防止匹配到 pwd=xxx 中的 pw
        # 分离"解压"关键字，要求必须有分隔符，防止匹配到"在线解压"等句子
        patterns = [
            r'(\b解压密码|解壓密碼|解压码|解壓碼|压缩包密码|压缩密码|密码|\bPW[123]?\b|\bpw[123]?\b|\bpass\b)[:：\s]*([^\n\r<（(\[【]+)',
            r'(\b解压|解壓|压缩包密码|压缩密码|\bPW[123]?\b)[:：\s]+([^\n\r<（(\[【]+)',
            r'[\(（](\b解压密码|解壓密碼|密码|\bPW[123]?\b)[:：\s]*([^\n\r<）)\]】]+)[\)）]'
        ]
        
        for pattern in patterns:
            found = re.findall(pattern, search_text, re.IGNORECASE)
            for kw, p in found:
                p = p.strip()
                # 当匹配到"RJ号"代词，或是它等于真实 RJ 号时，不再做任何替换和添加
                if re.search(r'RJ号|RJ码', p, re.I) or p.upper() == rj_code:
                    continue
                
                # 清洗：移除常见的干扰后缀
                p = re.sub(r'(?:复制这段内容|打开|即可获取|下载).*$', '', p).strip()
                p = re.split(r'https?://', p)[0].strip()
                
                # 根据中文标点截断，防止提取到超长说明文本
                # 特殊处理：如果是 pw1, pw2, pw3，则跳过标点截断（支持诗词类长密码）
                if not re.match(r'^pw[123]$', kw, re.I):
                    p = re.split(r'[。，！；]+', p)[0].strip()
                
                # 如果空格后紧跟中文字符，也在此截断 (防止 "password 度盘30天")
                p = re.split(r'\s+(?=[\u4e00-\u9fa5])', p)[0].strip()
                # 移除末尾标点
                p = p.rstrip('。.!！?？,， \t')
                # 移除开头标点（防止匹配到 "，30日内有效"）
                p = p.lstrip('。.!！?？,， \t')
                
                if p:
                    passwords.append(p)
            
        # 过滤误报
        extracted_codes = set(re.findall(code_pattern, search_text, re.I))
        filtered_passwords = []
        exclude_keywords = ['.js', '.php', '.html', 'verify', 'ajax', 'target', 'blank', 'http', 'pan.baidu', '在线', '30日', '有效', '此帖售价', 'SP币', '发现会员采用欺骗的方法', '严重者封掉ID', 'rj号']
        for p in passwords:
            if len(p) < 1 or len(p) > 120: # 密码可能很长 (例如整句英文)
                continue
            if any(kw in p.lower() for kw in exclude_keywords):
                continue
            # 过滤掉纯提取码（4位字符）
            if re.match(r'^[a-zA-Z0-9]{4}$', p) and p in extracted_codes:
                continue
            filtered_passwords.append(p)
        
        # 筛选密码：如果购买框提到了该提取码，直接剔除其他不是购买框的密码
        if purchase_text:
            purchase_pwds = []
            for p in filtered_passwords:
                if p in purchase_text:
                    purchase_pwds.append(p)
            if purchase_pwds:
                filtered_passwords = purchase_pwds
                
        # Fallback: 如果没有通过关键字提取到明保证的密码，尝试直接抽取购买框内的纯内容
        if not filtered_passwords and purchase_text:
            cand = purchase_text.strip()
            if 0 < len(cand) < 120 and not any(kw in cand.lower() for kw in exclude_keywords):
                is_baidu_pwd = any(link.get('pwd') == cand for link in baidu_links)
                # 1. 明确的“提取码XXXX”不作为解压密码
                if re.match(r'^(?:提取码|提取碼|提取|提码)[:：\s]*[a-zA-Z0-9]{4}$', cand, re.IGNORECASE):
                    pass
                # 2. 如果包含“提取码”字样，即使不是全匹配（如：提取码: av7q，密码是RJ号），也不作为解压密码
                elif re.search(r'(?:提取码|提取碼|提取|提码)[:：\s]*[a-zA-Z0-9]{4}', cand, re.IGNORECASE):
                    pass
                # 3. 如果是纯 4 位字符，且已经作为了某个链接的提取码或出现在提取码列表中，则过滤
                elif re.match(r'^[a-zA-Z0-9]{4}$', cand) and (is_baidu_pwd or cand in extracted_codes):
                    pass
                # 4. 再次检查是否包含代称关键词（针对混合文本）
                elif 'rj号' in cand.lower():
                    pass
                # 5. 剩下的内容（由于外层已经通过 exclude_keywords 过滤了模板垃圾），视为保底密码
                else:
                    filtered_passwords.append(cand)
        
        return {
            'nickname': nickname,
            'rj_code': rj_code,
            'links': baidu_links,
            'passwords': list(set(filtered_passwords))
        }

    def handle_mega_content(self, final_content, thread, rj_code):
        print(f"Extracting Mega links from thread: {thread['title']}")
        # 使用 extract_final_data 提取 RJ 号、昵称等通用元数据
        info = self.extract_final_data(final_content, title=thread['title'])
        info['post_url'] = f"{self.base_url}read.php?tid={thread['tid']}"
        info['rj_code'] = rj_code

        # Extract Mega links
        soup = BeautifulSoup(final_content, 'html.parser')
        text = soup.get_text(separator=' ')
        
        # Use regex to find links like https://mega.nz/...
        # Matches alphanumeric, slash, underscore, hyphen, hash, exclamation
        mega_links = re.findall(r'https://mega\.nz/[a-zA-Z0-9/_\-#!]+', text)
        
        # Also check hrefs
        for a in soup.find_all('a', href=True):
            if 'mega.nz' in a['href']:
                mega_links.append(a['href'])
                
        # Deduplicate
        unique_links = list(set(mega_links))
        
        # Deduplicate against existing
        new_links = [link for link in unique_links if link not in self.existing_mega_links]
        
        if new_links:
            passwords_str = '\t'.join(info.get('passwords', []))
            
            with open(self.mega_file, 'a', encoding='utf-8') as f:
                for link in new_links:
                    # 格式：RJ号 下载链接 提取码(空) 发布人 文章链接 密码...
                    line = f"{info['rj_code']}\t{link}\t\t{info['nickname']}\t{info['post_url']}\t{passwords_str}\n"
                    f.write(line)
                    self.existing_mega_links.add(link)
            
            # 同时保存解压密码（如果有）
            for pw in info['passwords']:
                self._save_jieya(pw)
                
            print(f"Saved {len(new_links)} new Mega links to mega.txt")
        else:
            print("No new Mega links found.")

    def handle_baidu_content(self, final_content, thread, rj_code):
        print(f"Extracting Baidu links from thread: {thread['title']}")
        info = self.extract_final_data(final_content, title=thread['title'])
        info['post_url'] = f"{self.base_url}read.php?tid={thread['tid']}"
        info['rj_code'] = rj_code
        
        if not info['links']:
            print("No Baidu links found after purchase/access.")
            return
        
        # 保存结果
        self._save_dl_list(info)
        for pw in info['passwords']:
            self._save_jieya(pw)
        
        print(f"Successfully processed {info['rj_code']} (Baidu)")

    def run(self, start_page=1, num_pages=1):
        for page in range(start_page, start_page + num_pages):
            threads = self.get_thread_list(page)
            for thread in threads:
                title_lower = thread['title'].lower()
                
                # 1. 首先提取 RJ/VJ 号并根据 RJ_list 进行初步过滤
                rj_codes = re.findall(r'[RV]J\d{5,12}', thread['title'], re.IGNORECASE)
                if not rj_codes:
                    # 标题没有 RJ/VJ，直接跳过
                    continue

                rj_code = rj_codes[0].upper()
                if rj_code in self.existing_rj:
                    print(f"Skipping: {rj_code} already exists in RJ_list.")
                    continue

                # 2. 识别平台 (Mega 或 百度)，过滤非度盘/mega
                is_mega = 'mega' in title_lower
                baidu_keywords = ['百度网盘', '百度', '度盘', 'BD', 'bd', 'baidu']
                is_baidu = any(kw in title_lower for kw in baidu_keywords)
                
                if not (is_mega or is_baidu):
                    # print(f"Skipping: No Baidu/Mega keyword in title: {thread['title']}")
                    continue

                # 3. 检查价格 (sp < 6)
                print(f"Processing {'Mega' if is_mega else 'Baidu'} thread: {thread['title']} ({thread['tid']})")
                post_data = self.parse_post_content(thread['tid'])
                
                if post_data['price'] >= 6:
                    print(f"Skipping: Price {post_data['price']} SP too high.")
                    continue

                # 4. 执行购买逻辑
                final_content = post_data['content']
                if not post_data['is_purchased']:
                    if 'buy_urls' in post_data and post_data['buy_urls']:
                        any_success = False
                        for b_url in post_data['buy_urls']:
                            if self.buy_post(b_url):
                                print(f"Purchase successful for box: {b_url}")
                                any_success = True
                                time.sleep(1)
                            else:
                                print(f"Purchase failed for box: {b_url}")
                        
                        if any_success:
                            # 只要有任何一个购买成功，就重新获取内容
                            resp = self.session.get(post_data['post_url'])
                            resp.encoding = 'utf-8'
                            final_content = resp.text
                        else:
                            print("All purchases failed.")
                            continue
                    else:
                        print("Not purchased and no buy URL.")
                        continue
                
                # 5. 提取并保存内容
                if is_mega:
                    self.handle_mega_content(final_content, thread, rj_code)
                else:
                    self.handle_baidu_content(final_content, thread, rj_code)
                
                time.sleep(2)

if __name__ == "__main__":
    crawler = SouthPlusCrawler()
    if len(sys.argv) >= 3:
        try:
            start_page = int(sys.argv[1])
            num_pages = int(sys.argv[2])
            print(f"Starting crawl from page {start_page} for {num_pages} pages...")
            crawler.run(start_page=start_page, num_pages=num_pages)
        except ValueError:
            print("Invalid arguments. Usage: python crawler.py [start_page] [num_pages]")
    else:
        print("No arguments provided, running default (page 1, 1 page)...")
        crawler.run(start_page=1, num_pages=10)
