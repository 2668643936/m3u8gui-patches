#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hotfix_v601.py — v6.0.0 → v6.0.1
① AdGuard 误桥修复(名字黑名单漏网)
② 可见/接管模式不再周期切标签抢焦点, 只在静默期结束/收尾各强制读一次
③ 无头模式保持 6s 高频轮询不变"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')


def die(msg):
    print('[x] ' + msg)
    sys.exit(1)


def rep(text, old, new, name, required=True):
    n = text.count(old)
    if n != 1:
        if not required:
            print(f'[skip] {name} (锚点缺失, 条件改动)')
            return text
        die(f'{name}: 锚点匹配 {n} 处')
    print(f'[OK] {name}')
    return text.replace(old, new, 1)


def main():
    if not SRC.exists():
        die('找不到 ' + str(SRC))
    raw = SRC.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    crlf = '\r\n' in text
    if crlf:
        text = text.replace('\r\n', '\n')

    if 'adguard' in text.lower():
        print('[i] 已修复过, 无需重复。')
        return

    text = rep(text,
        "    'cfhdojbkjhnklbpkdaibdccddilifddb',   # Adblock Plus\n}",
        "    'cfhdojbkjhnklbpkdaibdccddilifddb',   # Adblock Plus\n"
        "    'bgnkhhnnamicmpeenaelnjfhikgbkllg',   # AdGuard\n}",
        '① AdGuard ID 黑名单')
    text = rep(text,
        "r'ublock|adblock|ad ?block', name, re.I):",
        "r'ublock|adblock|ad ?block|adguard|ghostery|privacy', "
        "name, re.I):",
        '② 名字黑名单扩充')
    text = rep(text,
        '    def ext_poll():',
        '    def ext_poll(force=False):',
        '③ ext_poll 加 force 参数')
    text = rep(text,
        "        if not _ext.get('tabs') or time.time() - _ext_t[0] < 6:\n"
        "            return\n",
        "        if not _ext.get('tabs'):\n"
        "            return\n"
        "        if not force and (show_browser or attached):\n"
        "            return    # v6.0.1: 可见/接管模式 — 周期轮询会激活\n"
        "                      # 标签抢走用户正在看的画面, 只在关键时点\n"
        "                      # (静默期结束/收尾)强制读一次\n"
        "        if time.time() - _ext_t[0] < 6:\n"
        "            return\n",
        '④ 可见模式不抢焦点')
    text = rep(text,
        "                ext_poll()      # v6.0.0: 收尾前插件桥最后补收\n",
        "                ext_poll(force=True)   # v6.0.1: 收尾强制补收\n",
        '⑤ 收尾总账强制读')
    text = rep(text,
        "        cred_rescue('静默期结束')",
        "        ext_poll(force=True)   # v6.0.1: 静默期结束强制补收一次\n"
        "        cred_rescue('静默期结束')",
        '⑥ 静默期结束强制读', required=False)   # 未打5910时跳过

    text, n1 = re.subn(r'(m3u8gui\.py v)6\.0\.0', r'\g<1>6.0.1',
                       text, count=1)
    text, n2 = re.subn(r"(__version__ = ')6\.0\.0'", r"\g<1>6.0.1'",
                       text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 6.0.0)')
    print('[OK] ⑦ 版本号 → 6.0.1')

    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'语法校验失败: {e} — 未改动')
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
    print(f'[OK] v6.0.1 完成(备份 → {bak.name})')


if __name__ == '__main__':
    main()