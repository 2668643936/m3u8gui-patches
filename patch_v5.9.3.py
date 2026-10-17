#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v593.py — m3u8gui.py → v5.9.3 (拆除误伤播放器的防弹窗注入)
现象: 部分站换新播放器后, 播放按钮点击无效(工具点+手点都没反应),
     正常浏览器正常; 日志"已点击播放入口"但 mp4_cands 为空。
主嫌疑: v584 注入的 _blank 点击拦截 + window.open 灭活, 掐死了
     "播放=开新标签/弹窗"式播放器。
修复: 注入只保留防拖回; 弹窗防御全交给窗口守卫(0.5s 关新窗口)。
用法: python patch_v593.py
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


OLD = r'''    _pop_js = (
        'window.open=function(){return null;};'
        'try{window.moveTo=function(){};window.resizeTo=function(){};}catch(e){}'
        'try{document.addEventListener("click",function(e){'
        'var t=e.target;while(t&&t!==document){'
        'if(t.tagName==="A"||t.tagName==="AREA"){'
        'if((t.target||"")==="_blank"){e.preventDefault();'
        'e.stopPropagation();}break;}t=t.parentNode;}},true);}catch(e){}'
    )
'''

NEW = r'''    # v5.9.3: 仅保留防拖回; 拆除 _blank 点击拦截与 window.open 灭活 —
    # 它们会误伤"播放=开新标签/弹窗"的播放器(守卫 0.5s 关弹窗已足够)
    _pop_js = (
        'try{window.moveTo=function(){};window.resizeTo=function(){};}catch(e){}'
    )
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '仅保留防拖回' in text:
        print('v5.9.3 补丁已存在, 无需重复打。')
        return
    if 'window.resizeTo=function(){}' not in text:
        die('未检测到 v5.8.20 的注入脚本 — 请确认补丁链完整')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.3', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.3'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件在 5.8/5.9 系列')
    print('[OK] ① 版本号 → 5.9.3')

    n = text.count(OLD)
    if n != 1:
        die(f'② 注入脚本锚点匹配 {n} 处(应为 1 处)')
    text = text.replace(OLD, NEW, 1)
    print('[OK] ② 拆除 _blank 拦截与 window.open 灭活')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.3 (拆除误伤播放器的注入)')


if __name__ == '__main__':
    main()