#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_v614.py — m3u8gui.py v6.1.3 → v6.1.4 (插件桥停用开关)
桥页句柄问题未修(Target.createTarget 造的标签 chromedriver 不认,
3s 拿不到句柄), 每次抓取固定白耗 ~10s 且桥从未生效。应用户要求停用:
  · 模块级开关 _BRIDGE_ENABLED = False — 修复句柄问题后改 True 即恢复
  · 桥初始化整体跳过(不扫描/不开页/不等待), [插件桥] 日志随之消失
用法: python patch_v614.py"""

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

if '_BRIDGE_ENABLED' in text:
    print('[i] v6.1.4 已打过。')
    sys.exit(0)


def rep1(old, new, name):
    global text
    n = text.count(old)
    if n != 1:
        print(f'[x] {name}: 匹配 {n} 处(应为 1) — 未改动')
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f'[OK] {name}')


# ---------- ① 模块级开关 ----------
rep1("_SNIFFER_SKIP_IDS = {",
     "_BRIDGE_ENABLED = False   # v6.1.4: 插件桥停用(句柄问题未修, 每次抓取白耗~10s)\n"
     "                          # 修复后改为 True 即恢复\n"
     "\n"
     "_SNIFFER_SKIP_IDS = {",
     '① _BRIDGE_ENABLED = False')

# ---------- ② 桥初始化门卫 ----------
rep1(
    "    _ext = {'tabs': []}\n"
    "    if not attached and not used_temp_profile:\n"
    "        _bridge_prof = _data_dir() / prof_name",
    "    _ext = {'tabs': []}\n"
    "    if not attached and not used_temp_profile and _BRIDGE_ENABLED:\n"
    "        _bridge_prof = _data_dir() / prof_name",
    '② 桥初始化加开关门卫')

# ---------- 版本号 ----------
text, n1 = re.subn(r'(m3u8gui\.py v)6\.1\.3', r'\g<1>6.1.4', text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.1\.3'", r"\g<1>6.1.4'", text, count=1)
if n1 != 1 or n2 != 1:
    print('[x] 版本号定位失败(应为 6.1.3) — 未改动')
    sys.exit(1)
print('[OK] ③ 版本号 → 6.1.4')

rep1('\nv5.8.1:\n',
     '\nv6.1.4: 插件桥停用开关(_BRIDGE_ENABLED=False — 句柄问题未修前\n'
     '        不再每次抓取白耗~10s; 修复后改 True 恢复)\n'
     'v5.8.1:\n',
     '④ 文件头更新日志')

try:
    compile(text, SRC.name, 'exec')
except SyntaxError as e:
    print(f'[x] 语法校验失败: {e} — 未改动')
    sys.exit(1)
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
print(f'[OK] v6.1.4 完成(备份 → {bak.name})')