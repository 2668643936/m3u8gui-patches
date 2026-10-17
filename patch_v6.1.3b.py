#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_v613b.py — v6.1.2 → v6.1.3 (b: 修防重令牌误报)
v613 用 'def logM(msg' 做防重令牌, 但 _one_thumb 里的旧局部 logM 撞车。
b版改用补丁独有注释 '缩略图引擎约定(msg-first)' 做标志。其余与 v613 相同。"""

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

MARK = '# v6.1.3: 缩略图引擎约定(msg-first)'
if MARK in text:
    print('[i] v6.1.3 已打过。')
    sys.exit(0)
if '_batch_center' not in text:
    print('[x] 未检测到 v6.1.1(_batch_center)')
    sys.exit(1)
if "_TRACK_RE" in text:
    print('[x] _TRACK_RE 已存在? 异常状态, 把本输出发回')
    sys.exit(1)


def rep1(old, new, name):
    global text
    n = text.count(old)
    if n != 1:
        print(f'[x] {name}: 匹配 {n} 处(应为 1) — 未改动')
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f'[OK] {name}')


def sub1(pat, repl, name, expect=1):
    global text
    new, n = re.subn(pat, repl, text)
    if n != expect:
        print(f'[x] {name}: 匹配 {n} 处(应为 {expect}) — 未改动')
        sys.exit(1)
    text = new
    print(f'[OK] {name}')


rep1(
    "            def logL(level, msg):\n"
    "                self.msgq.put(('log', level, msg))",
    "            def logL(level, msg):\n"
    "                self.msgq.put(('log', level, msg))\n"
    "\n"
    "            def logM(msg, level='info'):"
    "   " + MARK + "\n"
    "                self.msgq.put(('log', level, msg))",
    '① logM 定义(与 logL 并存)')

sub1(r"make_thumbnails_for\(p, tc, logL,",
     "make_thumbnails_for(p, tc, logM,",
     '② make_thumbnails_for → logM')
sub1(r"(online_thumbs\(got, label or '', outdir, tc,\s+)logL(, self\.msgq, stop_ev,)",
     r"\1logM\2",
     '③ online_thumbs → logM')

rep1(
    "log('info', f'分片 #{j} 429 → 全局冷却中'\n"
    "                                   '(下载线程集体暂停, 非卡死)')",
    "log(f'分片 #{j} 429 → 全局冷却中'\n"
    "                                   '(下载线程集体暂停, 非卡死)', 'info')",
    '④ _dl_seg 429日志 msg-first')
rep1(
    "log('info', f'缩略图就低: {cur}p → {t}p(省流量 ~{cur // t}x)')",
    "log(f'缩略图就低: {cur}p → {t}p(省流量 ~{cur // t}x)', 'info')",
    '⑤ _res_thumb_pick 日志 msg-first')

rep1("_M3U8_URL_RE = re.compile(",
     "_TRACK_RE = re.compile(\n"
     "    r'(?i)(jwpltx|/ping[.?]|analytics|/pixel|'\n"
     "    r'\\.(?:gif|png|jpe?g|webp)(?:[?#]|$))')\n"
     "\n"
     "\n"
     "_M3U8_URL_RE = re.compile(",
     '⑥ _TRACK_RE 定义')
rep1(
    "    def consider_m3u8(u, where):\n"
    "        if u in quality_cache:",
    "    def consider_m3u8(u, where):\n"
    "        if _TRACK_RE.search(u):        # v6.1.3: 统计打点不是媒体\n"
    "            return\n"
    "        if u in quality_cache:",
    '⑦ consider_m3u8 过滤打点')

text, n1 = re.subn(r'(m3u8gui\.py v)6\.1\.2', r'\g<1>6.1.3', text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.1\.2'", r"\g<1>6.1.3'", text, count=1)
if n1 != 1 or n2 != 1:
    print('[x] 版本号定位失败(应为 6.1.2) — 未改动')
    sys.exit(1)
print('[OK] ⑧ 版本号 → 6.1.3')

rep1('\nv5.8.1:\n',
     '\nv6.1.3: 批量缩略图修复 — 引擎log约定冲突(TypeError致全败+僵尸预取\n'
     '        线程429风暴) / 统计打点过滤(jwpltx ping.gif)\n'
     'v5.8.1:\n',
     '⑨ 文件头更新日志')

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
print(f'[OK] v6.1.3 完成(备份 → {bak.name})')