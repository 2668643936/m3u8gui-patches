#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5811.py — m3u8gui.py → v5.8.11 (Edge 无头不稳: 加固 + 自动降级)
现象: 同一站点, Chrome 一发命中, 无头 Edge 页面加载卡死/快照为空
(renderer 死, 与"启动即断"同族)。
修复:
  ① Edge 补两个 Chrome 一直有的稳定件:
     --disable-gpu(防 renderer 崩)
     --disable-blink-features=AutomationControlled(隐藏自动化特征,
     部分站见 navigator.webdriver=true 直接白屏)
  ② 保底: Edge 未截获 → 自动换 Chrome 再试一次(不用手动切设置)
用法: python patch_v5811.py
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


EDGE_OLD = r'''        else:                                  # Edge 精简参数(防renderer崩)
            o.add_argument('--mute-audio')
            o.add_argument('--window-size=1280,800')
            o.add_argument('--window-position=10000,10000')  # 白框挪屏幕外
'''

EDGE_NEW = r'''        else:                                  # Edge 精简参数(防renderer崩)
            o.add_argument('--mute-audio')
            o.add_argument('--window-size=1280,800')
            o.add_argument('--window-position=10000,10000')  # 白框挪屏幕外
            # v5.8.11: Edge 稳定件 — 防 renderer 崩 + 隐藏自动化特征
            # (Chrome 一直带 AutomationControlled, Edge 缺它会被
            #  部分站点当机器人直接白屏)
            o.add_argument('--disable-gpu')
            o.add_argument('--disable-blink-features=AutomationControlled')
'''

FALL_OLD = r'''            try:
                res = browser_auto_extract(page, log, show, port, proxy,
                                           browser=browser)
                if res:
'''

FALL_NEW = r'''            try:
                res = browser_auto_extract(page, log, show, port, proxy,
                                           browser=browser)
                if not res and (browser or 'chrome') == 'edge':
                    # v5.8.11: 无头 Edge 在部分站点 renderer 直接不动
                    # (页面加载卡死/快照为空) → 自动降级 Chrome 再试一次
                    log('info', 'Edge 未截获(无头 Edge 对该站不友好) → '
                                '自动换 Chrome 再试一次...')
                    res = browser_auto_extract(page, log, show, port,
                                               proxy, browser='chrome')
                if res:
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '自动换 Chrome 再试一次' in text:
        print('v5.8.11 Edge 补丁已存在, 无需重复打。')
        return
    for feat in ('Edge 精简参数(防renderer崩)', 'def browser_auto_extract'):
        if feat not in text:
            die(f'文件缺少特征: {feat!r}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.11', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.11'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.11')

    text = replace_once(text, EDGE_OLD, EDGE_NEW, '② Edge 稳定件参数')
    text = replace_once(text, FALL_OLD, FALL_NEW, '③ Edge 失败自动降级 Chrome')

    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'补丁后语法校验失败: {e} — 原文件未改动')

    bak = SRC.with_name(SRC.name + '.bak')
    k = 1
    while bak.exists():
        k += 1
        bak = SRC.with_name(f'{SRC.name}.bak{k}')
    shutil.copy2(SRC, bak)
    SRC.write_text(text, encoding='utf-8')
    print()
    print(f'[OK] 原文件已备份 → {bak.name}')
    print('[OK] m3u8gui.py 已升级到 v5.8.11 (Edge 加固+自动降级)')


if __name__ == '__main__':
    main()