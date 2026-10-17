#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5818.py — m3u8gui.py → v5.8.18 (打包版驱动控制台根治)
打包(--windowed)时 chromedriver 自带控制台窗口, 被从任务栏关闭
= 驱动被杀 = InvalidSessionId。冻结模式下给驱动类子进程强制
CREATE_NO_WINDOW, 窗口根本不出现。开发版行为不变。
注意: 需重新 pyinstaller 打包后才对打包版生效!
用法: python patch_v5818.py
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


OLD = "SUBPROC_FLAGS = 0x08000000 if sys.platform == 'win32' else 0    # CREATE_NO_WINDOW\n"

NEW = """SUBPROC_FLAGS = 0x08000000 if sys.platform == 'win32' else 0    # CREATE_NO_WINDOW

# v5.8.18: 打包(--windowed)时 chromedriver/msedgedriver 自带控制台窗口,
# 用户从任务栏关闭它 = 杀驱动 = InvalidSessionId。
# 冻结模式下拦截 Popen, 驱动类子进程强制无窗口(开发版不受影响)。
if getattr(sys, 'frozen', False) and sys.platform == 'win32':
    import subprocess as _sp_mod
    _orig_popen_init = _sp_mod.Popen.__init__

    def _popen_hidden(self, args, *a, **kw):
        try:
            exe = str(args[0] if isinstance(args, (list, tuple))
                      else args).lower()
            if ('chromedriver' in exe or 'msedgedriver' in exe
                    or 'selenium-manager' in exe or 'geckodriver' in exe):
                kw['creationflags'] = (kw.get('creationflags', 0)
                                        | SUBPROC_FLAGS)
        except Exception:
            pass
        return _orig_popen_init(self, args, *a, **kw)

    _sp_mod.Popen.__init__ = _popen_hidden
"""


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_popen_hidden' in text:
        print('v5.8.18 驱动窗口补丁已存在, 无需重复打。')
        return
    if text.count(OLD) != 1:
        die('SUBPROC_FLAGS 锚点未找到/不唯一')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.18', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.18'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.18')

    text = text.replace(OLD, NEW, 1)
    print('[OK] ② 冻结模式驱动进程强制无窗口')

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
    print('[OK] 已升级 v5.8.18 — 请重新 pyinstaller 打包后再测打包版')


if __name__ == '__main__':
    main()