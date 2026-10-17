#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5821.py — m3u8gui.py → v5.8.21 (修复可见窗口模式)
Bug: 三道"白框挪出屏幕"逻辑(启动参数/启动挪窗/守卫OS挪窗)不分模式,
     可见窗口模式自 v5.8 起实际是"隐形窗口", 与无头无差别。
修复: 三处全部加"可见模式除外" — 可见模式主窗口留在屏幕内正常显示;
      守卫的"关弹窗"部分对可见模式保留(广告弹窗仍被秒关)。
用法: python patch_v5821.py
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


A1_OLD = "            o.add_argument('--window-position=10000,10000')  # 白框挪屏幕外\n"
A1_NEW = """            if not show_browser:              # v5.8.21: 可见窗口留在屏幕内
                o.add_argument('--window-position=10000,10000')
"""

A2_OLD = r'''        try:
            o.add_argument('--window-position=10000,10000')
        except Exception:
            pass
'''
A2_NEW = r'''        if not show_browser:                  # v5.8.21: 可见窗口不再挪出屏幕
            try:
                o.add_argument('--window-position=10000,10000')
            except Exception:
                pass
'''

A3_OLD = r'''    # v5.8.4: 启动时把当前所有窗口都挪出屏幕
    # (旧版 --window-position 只管启动创建的第一个, 会话恢复/弹出的不受它管)
    if not attached:
'''
A3_NEW = r'''    # v5.8.4: 启动时把当前所有窗口都挪出屏幕
    # (旧版 --window-position 只管启动创建的第一个, 会话恢复/弹出的不受它管)
    # v5.8.21: 可见窗口模式除外 — 用户要看的就是这个窗口
    if not attached and not show_browser:
'''

A4_OLD = r'''        while guard_run.is_set():
            if win_ok:
                try:
                    if not pids or tick <= 0:
'''
A4_NEW = r'''        while guard_run.is_set():
            if win_ok and not show_browser:   # v5.8.21: 可见模式不挪窗(仍关弹窗)
                try:
                    if not pids or tick <= 0:
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '可见窗口模式除外' in text:
        print('v5.8.21 可见窗口补丁已存在, 无需重复打。')
        return

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.21', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.21'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.21')

    text = replace_once(text, A1_OLD, A1_NEW, '② Edge 分支位置参数按模式')
    text = replace_once(text, A2_OLD, A2_NEW, '③ 通用位置参数按模式')
    text = replace_once(text, A3_OLD, A3_NEW, '④ 启动挪窗跳过可见模式')
    text = replace_once(text, A4_OLD, A4_NEW, '⑤ 守卫挪窗跳过可见模式')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.21 (可见窗口模式修复)')


if __name__ == '__main__':
    main()