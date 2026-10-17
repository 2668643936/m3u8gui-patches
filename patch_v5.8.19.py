#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5819.py — m3u8gui.py → v5.8.19 (打包版 Chrome 死亡记录仪)
冻结模式下给浏览器加 --enable-logging --log-path, 输出到
APP_DIR/chrome_run.log — 下次会话死亡时能读到退出原因。
(开发版不加, 避免噪音)
用法: python patch_v5819.py
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


OLD = r'''    o = (EdgeOptions() if (bname == 'edge' and not attached) else Options())
    if attached:
'''
NEW = r'''    o = (EdgeOptions() if (bname == 'edge' and not attached) else Options())
    if getattr(sys, 'frozen', False) and not attached:
        try:                     # v5.8.19: 打包版自写运行日志(死亡记录仪)
            o.add_argument(f'--log-path={APP_DIR / "chrome_run.log"}')
            o.add_argument('--enable-logging')
        except Exception:
            pass
    if attached:
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'chrome_run.log' in text:
        print('v5.8.19 记录仪补丁已存在, 无需重复打。')
        return
    if text.count(OLD) != 1:
        die('浏览器参数锚点未找到/不唯一')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.19', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.19'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.19')

    text = text.replace(OLD, NEW, 1)
    print('[OK] ② 冻结模式 Chrome 自写运行日志')

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
    print('[OK] 已升级 v5.8.19 — 重打包后生效, 日志将落在 exe 旁 chrome_run.log')


if __name__ == '__main__':
    main()