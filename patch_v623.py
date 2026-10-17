#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v622b.py — m3u8gui.py v6.2.2 → v6.2.3 (名字调用零冗余请求)

  ① 误判保护: 记录直链验证失败时不再立即删记录(网络抖动会误判,
     16:20 实测: 同一token 90秒后验证通过) — 记录保留, 转原路解析,
     解析成功后记录被 _link_store 自然覆盖刷新
  ② grab_done 快路径: _from_record 时 — 跳过测时长请求(记录dur
     现成)、fname 优先用记录带出的(零请求), 文件名即时确定
     (名字调用全程 ≈ 命中0.1s + 验证2s + 填栏位 = ~3s)
  ③ 版本号 6.2.3 + 文件头日志
用法: python patch_v622b.py
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

if 'v6.2.3: 误判保护' in text:
    print('[i] v6.2.3 已打过。')
    sys.exit(0)
if "'_from_record': True," not in text:
    print('[x] 未检测到 v6.2.2 — 请先运行 patch_v622.py')
    sys.exit(1)

DONE = []


def rep1(old, new, name):
    global text
    n = text.count(old)
    if n != 1:
        print(f'[x] {name}: 匹配 {n} 处(应为 1) — 未改动')
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f'[OK] {name}')
    DONE.append(name)


# ---------- ① 验证失败不删记录 ----------
rep1(
    "    d['links'].pop(key, None)          # 失效 → 删除, 重新解析\n"
    "    _link_save(d)                      # v6.2.2: strike/volatile 退役\n",
    "    # v6.2.3: 记录保留(验证失败可能是网络抖动) — 转原路解析,\n"
    "    # 解析成功后 _link_store 覆盖刷新本条\n",
    '① 验证失败不删记录')

# ---------- ②a grab_done 快路径: 跳过测时长 ----------
rep1(
    "                if got and got.get('url'):\n"
    "                    try:               # v6.2.0: 抓取后测时长入库\n",
    "                if got and got.get('url') \\\n"
    "                        and not got.get('_from_record'):\n"
    "                    try:               # v6.2.0: 抓取后测时长入库\n"
    "                                   # v6.2.3: 记录复用时dur现成, 跳过\n",
    '②a 记录复用跳过测时长')

# ---------- ②b 记录复用时 base 直接用记录名(单点短路) ----------
rep1(
    "                base = safe_name(t, url=got.get('url', ''), base_dir=outdir,\n"
    "                                 limit=80, filter_words=fw)",
    "                if got.get('fname'):   # v6.2.3: 记录复用, 名字现成\n"
    "                    base = got['fname']\n"
    "                else:\n"
    "                    base = safe_name(t, url=got.get('url', ''),\n"
    "                                     base_dir=outdir,\n"
    "                                     limit=80, filter_words=fw)",
    '②b 记录复用base直取')

# ---------- ③ 版本号 + 日志 ----------
text, n1 = re.subn(r'(m3u8gui\.py v)6\.2\.2', r'\g<1>6.2.3', text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.2\.2'", r"\g<1>6.2.3'", text, count=1)
if n1 == 1 and n2 == 1:
    print('[OK] ③ 版本号 → 6.2.3')
else:
    print('[x] 版本号定位失败(应为 6.2.2) — 未改动')
    sys.exit(1)

rep1(
    '\nv5.8.1:\n',
    '\nv6.2.3: 名字调用零冗余 — 记录复用跳过测时长请求(dur现成) /\n'
    '        fname优先记录名(零计算) / 验证失败不删记录(防抖动误判,\n'
    '        转解析后自然刷新)\n'
    'v5.8.1:\n',
    '④ 文件头更新日志')

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
print(f'[OK] 备份 → {bak.name} · m3u8gui.py → v6.2.3 (名字调用零冗余)')