#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5816.py — m3u8gui.py → v5.8.16 (下载缓存命中可观测)
v5.8.3 的盲区: 下载命中 seg_cache 时静默通过, 日志看不出来。
本补丁: 命中计数 + 下载结束打印
  [缓存命中: N/总数 个分片复用了缩略图已下的数据(免下载)]
用法: python patch_v5816.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')


def die(msg):
    print()
    print('[x] ' + msg)
    print('[x] 未做任何修改。把完整输出发回去即可定位。')
    sys.exit(1)


def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        die(f'{name}: 锚点匹配 {n} 处(应为 1 处)')
    print(f'[OK] {name}')
    return text.replace(old, new, 1)


INIT_OLD = r'''        self._bytes_hist = deque()
        self.finish_state = 'fail'
'''
INIT_NEW = r'''        self._bytes_hist = deque()
        self._cache_hits = 0                       # v5.8.16
        self._chit_lock = threading.Lock()         # v5.8.16
        self.finish_state = 'fail'
'''

HIT_OLD = r'''        got = _cache_copy(seg['url'], path)
        if got is not None:
            return None, got
'''
HIT_NEW = r'''        got = _cache_copy(seg['url'], path)
        if got is not None:
            with self._chit_lock:                  # v5.8.16: 命中计数
                self._cache_hits += 1
            return None, got
'''

SUM_OLD = r'''        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(max(1, self.cfg['workers']))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
'''
SUM_NEW = r'''        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(max(1, self.cfg['workers']))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if self._cache_hits:                       # v5.8.16
            self._log(f'缓存命中: {self._cache_hits}/{total} 个分片复用了'
                      '缩略图已下的数据(免下载)', 'ok')
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '缓存命中: ' in text:
        print('v5.8.16 命中观测补丁已存在, 无需重复打。')
        return
    if 'got = _cache_copy' not in text:
        die('未找到 _cache_copy 调用 — 请确认 v5.8.3.1 手工微补丁已替换')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.16', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.16'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.16')

    text = replace_once(text, INIT_OLD, INIT_NEW, '② Job 命中计数器')
    text = replace_once(text, HIT_OLD, HIT_NEW, '③ 命中时计数')
    text = replace_once(text, SUM_OLD, SUM_NEW, '④ 结束汇总日志')

    for tok in ('file_hint_placeholder', 'PLACEHOLDER_TBD', '__TBD__'):
        if tok in text:
            die(f'自检失败: 产物含占位符字样 {tok!r} — 拒绝写入')
    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'语法校验失败: {e} — 原文件未改动')
    bak = SRC.with_name(SRC.name + '.bak')
    k = 1
    while bak.exists():
        k += 1
        bak = SRC.with_name(f'{SRC.name}.bak{k}')
    shutil.copy2(SRC, bak)
    SRC.write_text(text, encoding='utf-8')
    print()
    print(f'[OK] 原文件已备份 → {bak.name}')
    print('[OK] m3u8gui.py 已升级到 v5.8.16 (缓存命中可观测)')


if __name__ == '__main__':
    main()