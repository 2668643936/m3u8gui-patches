#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5823.py — m3u8gui.py → v5.8.23 (下载/缩略图期间并行抓取)
  ① 全局浏览器档案锁: 并发抓取自动排队, 不互踩 chrome_profile
  ② 解锁: 下载中/缩略图中可「自动抓取」(短链保鲜流水线)
  ③ 下载期间抓取按钮保持可用; 批量模式仍禁(动态读栏位会被污染)
用法: python patch_v5823.py
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


LOCK_OLD = '''def browser_auto_extract(page_url, log, show_browser=False, chrome_port=None,
                        proxy=None, browser=None, passive=False):
    """自动抓取(v5.8.1: Chrome默认, Edge可切; v5.8.12: 纯被动模式)。"""
'''
LOCK_NEW = '''_BROWSER_LOCK = threading.Lock()


def browser_auto_extract(page_url, log, show_browser=False, chrome_port=None,
                        proxy=None, browser=None, passive=False):
    """自动抓取(v5.8.23: 全局浏览器档案锁 — 并发调用自动排队)"""
    if not _BROWSER_LOCK.acquire(timeout=0.5):
        log('info', '浏览器档案正被另一路任务占用, 排队等待...')
        _BROWSER_LOCK.acquire()
    try:
        return _browser_auto_extract_impl(page_url, log, show_browser,
                                          chrome_port, proxy, browser,
                                          passive)
    finally:
        _BROWSER_LOCK.release()


def _browser_auto_extract_impl(page_url, log, show_browser=False,
                              chrome_port=None, proxy=None, browser=None,
                              passive=False):
    """自动抓取(v5.8.1: Chrome默认, Edge可切; v5.8.12: 纯被动模式)。"""
'''

GRAB_OLD = r'''    def _auto_grab(self):
        if self.job or self._batch_running:
            messagebox.showinfo('提示', '下载任务运行中, 请等它结束')
            return
        if self.thumb_job and self.thumb_job.is_alive():
            messagebox.showinfo('提示', '缩略图任务运行中, 请等它结束')
            return
        if self.grab_btn.instate(['disabled']):
            return
'''
GRAB_NEW = r'''    def _auto_grab(self):
        if self._batch_running:
            messagebox.showinfo('提示', '批量下载运行中(批量自身会动态读取'
                                        '栏位), 等它结束再抓')
            return
        # v5.8.23: 允许在下载/缩略图进行中抓取 — 两者不占浏览器档案,
        # 抓取间的档案冲突由全局锁自动排队
        if self.job:
            self._append_log('info', '(与正在进行的下载并行抓取 — '
                                     '新链接将填入栏位备用)')
        if self.grab_btn.instate(['disabled']):
            return
'''

BTN_OLD = r'''        self.start_btn.config(state='disabled')
        self.grab_btn.config(state='disabled')
        self.batch_btn.config(state='disabled')
'''
BTN_NEW = r'''        self.start_btn.config(state='disabled')
        # v5.8.23: 下载期间保留「自动抓取」可用(预抓下一条链接)
        self.grab_btn.config(state='normal')
        self.batch_btn.config(state='disabled')
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_BROWSER_LOCK' in text:
        print('v5.8.23 并行抓取补丁已存在, 无需重复打。')
        return
    for feat in ('def browser_auto_extract', 'def _auto_grab'):
        if feat not in text:
            die(f'文件缺少特征: {feat!r}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.23', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.23'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.23')

    text = replace_once(text, LOCK_OLD, LOCK_NEW, '② 全局浏览器档案锁')
    text = replace_once(text, GRAB_OLD, GRAB_NEW, '③ 解锁并行抓取')
    text = replace_once(text, BTN_OLD, BTN_NEW, '④ 下载期间抓取按钮可用')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.23 (并行抓取)')


if __name__ == '__main__':
    main()