#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5822.py — m3u8gui.py → v5.8.22 (缩略图预取线程数跟随设置)
旧: 预取池写死 6 线程, 与设置的并发数无关。
新: 跟随设置里的「并发数」(1~12 封顶), 日志如实显示实际值。
429 已由全局冷却兜底(v5.8.13/14), 高并发只会变慢不会丢帧。
用法: python patch_v5822.py
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


OLD = r'''            if _pf_queued:
                log(f'分片预取: {len(_pf_queued)} 个分片排队, '
                    '6 线程并行(断点续传)', 'info')
                for _ in range(min(6, len(_pf_queued))):
                    threading.Thread(target=_pf_worker,
                                     daemon=True).start()
'''

NEW = r'''            if _pf_queued:
                try:                    # v5.8.22: 跟随设置的并发数(1~12)
                    _pf_w = int(load_settings().get('workers') or 6)
                except (TypeError, ValueError):
                    _pf_w = 6
                _pf_w = max(1, min(_pf_w, 12))
                log(f'分片预取: {len(_pf_queued)} 个分片排队, '
                    f'{_pf_w} 线程并行(断点续传)', 'info')
                for _ in range(min(_pf_w, len(_pf_queued))):
                    threading.Thread(target=_pf_worker,
                                     daemon=True).start()
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '跟随设置的并发数' in text:
        print('v5.8.22 预取线程补丁已存在, 无需重复打。')
        return

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.22', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.22'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.22')

    text = replace_once(text, OLD, NEW, '② 预取线程数跟随并发数')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.22 (预取线程跟随设置)')


if __name__ == '__main__':
    main()