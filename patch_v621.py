#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v621.py (V2 留档版) — m3u8gui.py v6.2.0 → v6.2.1

内容(四段, 含原621两处 + 打完后两次手工修复的固化):
  ① 短命站语义分离: _link_store 移除 volatile 拦截(记录照写,
     fname/dur 鲜活); _link_recall 开头加 volatile 检查(短命站
     直链不复用, 每次重新解析, 成功后记录自动刷新)
  ② _auto_grab 名字分流补位: 非URL输入 → _link_find_by_words →
     命中填入页面继续 / 未命中 return(不再被旧URL守卫弹窗拦截)
  ③ fname 同源化: grab_done 命名后将界面名字写入 got['_fname'];
     _link_store 优先取 got['_fname'] — 记录名=界面名=落盘名
出厂自检: L段 ast 预检 / 语法闸带 >> 现场。
用法: python patch_v621.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

raw = SRC.read_bytes()
bom = raw.startswith(b'\xef\xbb\xbf')
text = raw.decode('utf-8-sig')
crlf = '\r\n' in text
if crlf:
    text = text.replace('\r\n', '\n')

MARK = 'v6.2.1: 短命站语义分离'
if MARK in text:
    print('[i] v6.2.1 已打过(或含其标记)。')
    sys.exit(0)
if "'fname': _fn," not in text:
    print('[x] 未检测到 v6.2.0 — 请先运行 patch_v620.py')
    sys.exit(1)


def rep1(old, new, name):
    global text
    n = text.count(old)
    if n != 1:
        print(f'[x] {name}: 匹配 {n} 处(应为 1) — 未改动')
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f'[OK] {name}')


# ---------- ①a _link_store 移除 volatile 拦截 ----------
rep1(
    "    d = _link_load()\n"
    "    if time.time() - d['volatile'].get(dom, 0) < LINK_VOLATILE_TTL:\n"
    "        return\n",
    "    d = _link_load()\n",
    '①a _link_store 移除volatile拦截')

# ---------- ①b _link_recall 加 volatile 检查 ----------
rep1(
    "    dom = _domain_of(key)\n"
    "    age = time.time() - (rec.get('ts') or 0)\n",
    "    dom = _domain_of(key)\n"
    "    if time.time() - d['volatile'].get(dom, 0) < LINK_VOLATILE_TTL:\n"
    "        return None   # " + MARK + "\n"
    "    age = time.time() - (rec.get('ts') or 0)\n",
    '①b _link_recall 加volatile检查')

# ---------- ② _auto_grab 名字分流 ----------
rep1(
    "        page = self.page_var.get().strip() or self.url_var.get().strip()\n"
    "        if not page.startswith('http'):\n"
    "            messagebox.showerror('提示', "
    "'请先在「网页链接」栏填入播放页网址')\n"
    "            return",
    "        page = self.page_var.get().strip() or self.url_var.get().strip()\n"
    "        if page and not page.startswith('http'):\n"
    "            # v6.2.1: 名字式输入 → 分词查记录\n"
    "            def lg(l, m):\n"
    "                self.msgq.put(('log', l, m))\n"
    "            hit = _link_find_by_words(page, lg)\n"
    "            if hit:\n"
    "                self.page_var.set(hit)\n"
    "                self._append_log('ok',\n"
    "                                 f'名字命中记录 → 页面: {hit[:80]}')\n"
    "                page = hit\n"
    "            else:\n"
    "                return\n"
    "        if not page.startswith('http'):\n"
    "            messagebox.showerror('提示', "
    "'请先在「网页链接」栏填入播放页网址')\n"
    "            return",
    '② _auto_grab 名字分流')

# ---------- ③a grab_done: 界面名字写入 got['_fname'] ----------
rep1(
    "                self._out_setting = True\n"
    "                self.out_var.set(str(_po.with_name(base + '.mp4')))\n"
    "                self._out_setting = False\n",
    "                self._out_setting = True\n"
    "                self.out_var.set(str(_po.with_name(base + '.mp4')))\n"
    "                self._out_setting = False\n"
    "                got['_fname'] = base   # v6.2.1: 记录fname与界面同名\n",
    '③a grab_done 界面名字入got')

# ---------- ③b _link_store: fname 优先取 got['_fname'] ----------
rep1(
    "    # v6.2.0: fname=界面「文件名已确定」同源(原样存, 不归一化)\n"
    "    _fn = ''\n"
    "    try:\n"
    "        _t = transform_title(got.get('title') or '', [], True)\n"
    "        _fn = safe_name(_t, url=got['url'], limit=80)\n"
    "    except Exception:\n"
    "        _fn = ''\n",
    "    # v6.2.1: 优先用界面命名(grab_done写入got['_fname'])\n"
    "    _fn = got.get('_fname') or ''\n"
    "    if not _fn:\n"
    "        try:\n"
    "            _t = transform_title(got.get('title') or '', [], True)\n"
    "            _fn = safe_name(_t, url=got['url'], limit=80)\n"
    "        except Exception:\n"
    "            _fn = ''\n",
    '③b _link_store fname同源')

# ---------- ④ 版本号 ----------
text, n1 = re.subn(r'(m3u8gui\.py v)6\.2\.0', r'\g<1>6.2.1',
                   text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.2\.0'",
                   r"\g<1>6.2.1'", text, count=1)
if n1 != 1 or n2 != 1:
    print('[x] 版本号定位失败(应为 6.2.0) — 未改动')
    sys.exit(1)
print('[OK] ④ 版本号 → 6.2.1')

# ---------- ⑤ 文件头日志 ----------
rep1(
    '\nv5.8.1:\n',
    '\nv6.2.1: 短命站语义分离(记录照写/直链不复用) / _auto_grab名字\n'
    '        分流补位 / fname与界面命名同源(记录名=界面名=落盘名)\n'
    'v5.8.1:\n',
    '⑤ 文件头更新日志')

# ---------- 语法闸(带现场) ----------
try:
    compile(text, SRC.name, 'exec')
except SyntaxError as e:
    print(f'[x] 语法校验失败: {e} — 未改动')
    lines = text.split('\n')
    lo = max(0, (e.lineno or 1) - 5)
    hi = min(len(lines), (e.lineno or 1) + 3)
    for i in range(lo, hi):
        mk = '>>' if i + 1 == e.lineno else '  '
        print(f'{mk}{i+1:5d} | {lines[i]}')
    print('[i] ↑ 报错点前后文(>>为报错行) — 发回定位')
    sys.exit(1)
print('[OK] 语法校验通过')

# ---------- 落盘 ----------
if crlf:
    text = text.replace('\n', '\r\n')
data = text.encode('utf-8')
if bom:
    data = b'\xef\xbb\xbf' + data
bak = SRC.with_name(SRC.name + '.bak')
k = 1
while bak.exists():
    k += 1
    bak = SRC.with_name(f'{SRC.name}.bak{k}')
shutil.copy2(SRC, bak)
SRC.write_bytes(data)
print(f'[OK] 原文件已备份 → {bak.name}')
print('[OK] m3u8gui.py 已升级到 v6.2.1 (完整版: 语义分离+名字分流+fname同源)')
print('验证: python -m py_compile m3u8gui.py')
