#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5812.py — m3u8gui.py → v5.8.12 (抓取策略: 纯被动嗅探模式)【修复版】
本版相对初版的唯一修复: ROUND_NEW 误留的占位符废稿
(elif not (pending or file_hint_placeholder) and False: / pass)已摘除。
新增设置项「抓取策略」:
  智能(默认) = 现有三级引擎(静默期 → 点击 → iframe 轮)
  纯被动嗅探  = 零点击零导航, 只监听网络/读DOM/扫源码, 静观≥50s
用法: python patch_v5812.py
(可作用于: 干净的 5.8.x / 带 BUG 的 5.8.12 / 已修复的 5.8.12)
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


def finish(text, name):
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
    print(f'[OK] {name}')


SIG_OLD = """def browser_auto_extract(page_url, log, show_browser=False, chrome_port=None,
                        proxy=None, browser=None):
    \"\"\"自动抓取(v5.8.1: Chrome默认, Edge可切)。\"\"\"
"""
SIG_NEW = """def browser_auto_extract(page_url, log, show_browser=False, chrome_port=None,
                        proxy=None, browser=None, passive=False):
    \"\"\"自动抓取(v5.8.1: Chrome默认, Edge可切; v5.8.12: 纯被动模式)。\"\"\"
"""

OBS_OLD = r'''    obs_dom = _domain_of(page_url)
    obs_limit = _obs_get(obs_dom)
    if obs_limit != OBS_DEFAULT:
'''
OBS_NEW = r'''    obs_dom = _domain_of(page_url)
    obs_limit = _obs_get(obs_dom)
    if passive:
        obs_limit = max(obs_limit, 50)     # v5.8.12: 被动模式至少静观 50s
        log('info', '[纯被动] 不点击不导航, 只监听网络与页面(≥50s)...')
    if obs_limit != OBS_DEFAULT:
'''

ROUND_OLD = r'''        if not (pending or file_hit[0]):
            if iframes:
                log('info', f'页面含 {len(iframes)} 个 iframe, 进 frame 内点击')
'''
ROUND_NEW = r'''        if passive and not (pending or file_hit[0]):
            log('info', '[纯被动] 静默期未截获 — 被动模式不做点击/导航')
        elif not (pending or file_hit[0]):
            if iframes:
                log('info', f'页面含 {len(iframes)} 个 iframe, 进 frame 内点击')
'''

SR_SIG_OLD = """def smart_resolve(page, log, proxy=None, show=False, port=None, browser=None):
"""
SR_SIG_NEW = """def smart_resolve(page, log, proxy=None, show=False, port=None, browser=None,
                  strategy=None):
"""

SR_CALL_OLD = r'''        else:
            try:
                res = browser_auto_extract(page, log, show, port, proxy,
                                           browser=browser)
                if not res and (browser or 'chrome') == 'edge':
'''
SR_CALL_NEW = r'''        else:
            passive = (strategy == 'passive') if strategy else \
                ((load_settings().get('sniff_strategy') or 'smart')
                 == 'passive')
            if passive:
                log('info', '抓取策略: 纯被动嗅探(不点击不导航, 只监听)')
            try:
                res = browser_auto_extract(page, log, show, port, proxy,
                                           browser=browser, passive=passive)
                if not res and (browser or 'chrome') == 'edge':
'''

FB_OLD = r'''                    res = browser_auto_extract(page, log, show, port,
                                               proxy, browser='chrome')
'''
FB_NEW = r'''                    res = browser_auto_extract(page, log, show, port,
                                               proxy, browser='chrome',
                                               passive=passive)
'''

RS_OLD = r'''                        res = browser_auto_extract(page, log, show, port,
                                                   proxy, browser=browser)
'''
RS_NEW = r'''                        res = browser_auto_extract(page, log, show, port,
                                                   proxy, browser=browser,
                                                   passive=passive)
'''

VAR_OLD = r'''        self.browser_var = tk.StringVar(
            value=s.get('browser') if s.get('browser') in ('edge', 'chrome')
            else 'chrome')
'''
VAR_NEW = r'''        self.browser_var = tk.StringVar(
            value=s.get('browser') if s.get('browser') in ('edge', 'chrome')
            else 'chrome')
        self.sniff_var = tk.StringVar(
            value=s.get('sniff_strategy')
            if s.get('sniff_strategy') in ('smart', 'passive') else 'smart')
'''

SAVE_OLD = r'''                browser=self.browser_var.get(),
                page_url=self.page_var.get().strip(),
'''
SAVE_NEW = r'''                browser=self.browser_var.get(),
                sniff_strategy=self.sniff_var.get(),
                page_url=self.page_var.get().strip(),
'''

UI_OLD = r'''        row = ttk.Frame(gf); row.pack(fill='x', pady=2)
        ttk.Label(row, text='接管端口:', width=10).pack(side='left')
'''
UI_NEW = r'''        row = ttk.Frame(gf); row.pack(fill='x', pady=2)
        ttk.Label(row, text='抓取策略:', width=10).pack(side='left')
        ttk.Radiobutton(row, text='智能(默认)', variable=self.sniff_var,
                        value='smart').pack(side='left', padx=(4, 0))
        ttk.Radiobutton(row, text='纯被动嗅探(不点击)',
                        variable=self.sniff_var,
                        value='passive').pack(side='left', padx=(6, 0))
        row = ttk.Frame(gf); row.pack(fill='x', pady=2)
        ttk.Label(row, text='接管端口:', width=10).pack(side='left')
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    # ---- 状态识别 ----
    if '纯被动嗅探' in text and 'file_hint_placeholder' not in text:
        print('v5.8.12(修复版)已存在, 无需重复打。')
        return

    if 'file_hint_placeholder' in text:
        # 带 BUG 的 5812: 其余 10 处锚点已替换, 原地摘除废稿即修复
        bad = ('        elif not (pending or file_hint_placeholder) '
               'and False:\n            pass\n')
        if text.count(bad) != 1:
            die('检测到废稿但形态异常 — 手动搜索 file_hint_placeholder, '
                '删除其所在 elif 行与下一行 pass')
        text = text.replace(bad, '', 1)
        finish(text, 'v5.8.12 废稿已原地摘除, NameError 修复完成')
        return

    # ---- 干净的 5.8.x: 全量打补丁 ----
    for feat in ('def browser_auto_extract', 'def smart_resolve',
                 '接管端口:'):
        if feat not in text:
            die(f'文件缺少特征: {feat!r}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.12', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.12'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.12')

    text = replace_once(text, SIG_OLD, SIG_NEW,
                        '② browser_auto_extract 增 passive')
    text = replace_once(text, OBS_OLD, OBS_NEW, '③ 被动模式观察期≥50s')
    text = replace_once(text, ROUND_OLD, ROUND_NEW, '④ 被动模式跳过点击轮')
    text = replace_once(text, SR_SIG_OLD, SR_SIG_NEW,
                        '⑤ smart_resolve 增 strategy')
    text = replace_once(text, SR_CALL_OLD, SR_CALL_NEW,
                        '⑥ 策略接入浏览器调用')
    text = replace_once(text, FB_OLD, FB_NEW, '⑦ Edge 降级调用带 passive')
    text = replace_once(text, RS_OLD, RS_NEW, '⑧ 重启调用带 passive')
    text = replace_once(text, VAR_OLD, VAR_NEW, '⑨ 设置变量')
    text = replace_once(text, SAVE_OLD, SAVE_NEW, '⑩ 设置持久化')
    text = replace_once(text, UI_OLD, UI_NEW, '⑪ 设置界面单选')

    finish(text, 'm3u8gui.py 已升级到 v5.8.12 (纯被动嗅探·修复版)')


if __name__ == '__main__':
    main()