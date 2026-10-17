#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v622.py (V2) — m3u8gui.py v6.2.1 → v6.2.2 (记录直链优先)
①a/①b volatile退役 / ② 验证语境+活性刷新+_from_record(按真实文本修正锚点)
③ 单任务半自动措辞 / ④⑤ 版本号与日志。直线脚本, 尾部无main()。
用法: python patch_v622.py
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

if 'v6.2.2: 记录直链优先' in text:
    print('[i] v6.2.2 已打过。')
    sys.exit(0)
if "got.get('_fname')" not in text:
    print('[x] 未检测到 v6.2.1 — 请先运行 patch_v621.py')
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


# ---------- ①a 删 _link_recall 的 volatile 拦截(621②) ----------
rep1(
    "    dom = _domain_of(key)\n"
    "    if time.time() - d['volatile'].get(dom, 0) < LINK_VOLATILE_TTL:\n"
    "        return None   # v6.2.1: 短命站语义分离\n"
    "    age = time.time() - (rec.get('ts') or 0)\n",
    "    dom = _domain_of(key)\n"
    "    age = time.time() - (rec.get('ts') or 0)\n",
    '①a 删volatile拦截')

# ---------- ①b 删 strike/volatile 写入分支 ----------
rep1(
    "    d['links'].pop(key, None)          # 失效 → 删除, 重新解析\n"
    "    if age < LINK_STRIKE_AGE:          # 刚记完就死 → 短命链站点\n"
    "        st = d['strike'].get(dom, 0) + 1\n"
    "        d['strike'][dom] = st\n"
    "        if st >= LINK_STRIKES:\n"
    "            d['volatile'][dom] = time.time()\n"
    "            d['strike'].pop(dom, None)\n"
    "            log('info', f'{dom}: 直链寿命 <2h → 7天内不再记录该站直链')\n"
    "    _link_save(d)\n",
    "    d['links'].pop(key, None)          # 失效 → 删除, 重新解析\n"
    "    _link_save(d)                      # v6.2.2: strike/volatile 退役\n",
    '①b 删strike/volatile写入')

# ---------- ② 命中分支: 活性刷新+fname/dur+_from_record ----------
rep1(
    "    if _link_validate(rec['url'], rec.get('referer') or '',\n"
    "                      rec.get('cookie') or '', rec.get('ua') or '', proxy):\n"
    "        log('ok', '抓取记录命中(直链仍有效) → 跳过三级解析')\n"
    "        return {'url': rec['url'],\n"
    "                'referer': rec.get('referer') or page,\n"
    "                'cookie': rec.get('cookie') or '',\n"
    "                'ua': rec.get('ua') or '',\n"
    "                'title': rec.get('title') or '',\n"
    "                'headers': {}, 'page': page}",
    "    if _link_validate(rec['url'], rec.get('referer') or '',\n"
    "                      rec.get('cookie') or '', rec.get('ua') or '', proxy):\n"
    "        log('ok', '抓取记录命中(直链仍有效) → 跳过三级解析')\n"
    "        rec['ts'] = time.time()   # v6.2.2: 活性确认, 刷新时间戳\n"
    "        _link_save(d)\n"
    "        return {'url': rec['url'],\n"
    "                'referer': rec.get('referer') or page,\n"
    "                'cookie': rec.get('cookie') or '',\n"
    "                'ua': rec.get('ua') or '',\n"
    "                'title': rec.get('title') or '',\n"
    "                'fname': rec.get('fname') or '',\n"
    "                'dur': rec.get('dur'),\n"
    "                '_from_record': True,   # v6.2.2: 记录直链优先\n"
    "                'headers': {}, 'page': page}",
    '② 命中分支增强(按真实文本)')

# ---------- ③ 单任务半自动: grab_done 日志措辞 ----------
rep1(
    "            self._append_log('ok', '自动抓取成功 — 视频直链已填入, '\n"
    "                                   '正在自动测试链接...')\n"
    "            self._test_link()",
    "            if got and got.get('_from_record'):\n"
    "                # v6.2.2: 记录直链优先 — 单任务半自动\n"
    "                self._append_log('ok', '记录直链仍有效 → 栏位已填好, '\n"
    "                                       '请点「开始 / 续传」下载')\n"
    "            else:\n"
    "                self._append_log('ok', '自动抓取成功 — 视频直链已填入, '\n"
    "                                       '正在自动测试链接...')\n"
    "                self._test_link()",
    '③ 单任务半自动措辞')

# ---------- ④ 版本号 ----------
text, n1 = re.subn(r'(m3u8gui\.py v)6\.2\.1', r'\g<1>6.2.2', text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.2\.1'", r"\g<1>6.2.2'", text, count=1)
if n1 == 1 and n2 == 1:
    print('[OK] ④ 版本号 → 6.2.2')
else:
    print('[x] 版本号定位失败(应为 6.2.1) — 未改动')
    sys.exit(1)

# ---------- ⑤ 文件头日志 ----------
rep1(
    '\nv5.8.1:\n',
    '\nv6.2.2: 记录直链优先 — volatile退役(先试直链死了再重抓, 期望\n'
    '        耗时恒优) / 验证带记录语境 / 活性确认刷新时间戳 /\n'
    '        单任务半自动(填好等人点), 批量全自动(不变)\n'
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
print(f'[OK] 备份 → {bak.name} · m3u8gui.py → v6.2.2 (记录直链优先)')