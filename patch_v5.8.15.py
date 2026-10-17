#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5815.py — m3u8gui.py → v5.8.15 (重抓后「开始/续传」无响应修复)
Bug: finish 的重抓分支在 self.job = None 之前就 return → 僵尸任务对象
     让 _start() 第一行守卫静默拦截; 状态栏也永远停在"重抓中..."。
修复:
  ① 重抓启动时立即释放僵尸任务; 重抓期间禁用全部按钮(防旧链接竞争)
  ② regrab_done 恢复状态栏与按钮
  ③ 重抓线程异常兜底(保证 regrab_done 一定送达, 按钮不锁死)
用法: python patch_v5815.py
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


A_OLD = r'''            if not ok and style == 'err' and self._job_page_src \
                    and not self._regrab_done:
                self._regrab_done = True
                pg = self._job_page_src
                self._append_log('warn', '任务失败(疑似视频链接过期) → '
                                         '用原网页链接自动重抓一次...')
                self.status_lbl.config(text='重抓中...')
                self.start_btn.config(state='normal')
                self.stop_btn.config(state='disabled')
                self.grab_btn.config(state='normal')
                self.batch_btn.config(state='normal')
                self.one_thumb_btn.config(state='normal')
                self.thumb_btn.config(state='normal')
'''
A_NEW = r'''            if not ok and style == 'err' and self._job_page_src \
                    and not self._regrab_done:
                self._regrab_done = True
                pg = self._job_page_src
                self.job = None              # v5.8.15: 立即释放僵尸任务,
                self._job_page_src = ''      # 否则「开始/续传」被静默拦截
                self._append_log('warn', '任务失败(疑似视频链接过期) → '
                                         '用原网页链接自动重抓一次...')
                self.status_lbl.config(text='重抓中...')
                self.start_btn.config(state='disabled')
                self.stop_btn.config(state='disabled')
                self.grab_btn.config(state='disabled')
                self.batch_btn.config(state='disabled')
                self.one_thumb_btn.config(state='disabled')
                self.thumb_btn.config(state='disabled')
'''

B1_OLD = r'''            if got:
                self._append_log('ok', '重抓成功, 视频直链已更新 → '
                                       '请点「开始 / 续传」继续')
                self.url_var.set(got.get('url', ''))
'''
B1_NEW = r'''            if got:
                self._append_log('ok', '重抓成功, 视频直链已更新 → '
                                       '请点「开始 / 续传」继续')
                self.status_lbl.config(text='已重抓, 可续传')   # v5.8.15
                for b in (self.start_btn, self.grab_btn, self.batch_btn,
                          self.one_thumb_btn, self.thumb_btn):
                    b.config(state='normal')                   # v5.8.15
                self.url_var.set(got.get('url', ''))
'''

B2_OLD = r'''            else:
                self._append_log('err', '重抓也失败 — 请手动处理该视频')
            self._regrab_done = False
'''
B2_NEW = r'''            else:
                self._append_log('err', '重抓也失败 — 请手动处理该视频')
                self.status_lbl.config(text='重抓失败')        # v5.8.15
                for b in (self.start_btn, self.grab_btn, self.batch_btn,
                          self.one_thumb_btn, self.thumb_btn):
                    b.config(state='normal')                   # v5.8.15
            self._regrab_done = False
'''

C_OLD = r'''                def regrab():
                    def lg(l, m):
                        self.msgq.put(('log', l, m))
                    got = smart_resolve(pg, lg,
                                        self.proxy_var.get().strip() or None,
                                        False, None,
                                        browser=self.browser_var.get())
                    self.msgq.put(('regrab_done', got, pg))
'''
C_NEW = r'''                def regrab():
                    def lg(l, m):
                        self.msgq.put(('log', l, m))
                    try:
                        got = smart_resolve(pg, lg,
                                            self.proxy_var.get().strip()
                                            or None, False, None,
                                            browser=self.browser_var.get())
                    except Exception as e:
                        lg('err', f'重抓异常: {e!r}')
                        got = None
                    self.msgq.put(('regrab_done', got, pg))
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '已重抓, 可续传' in text:
        print('v5.8.15 重抓补丁已存在, 无需重复打。')
        return
    if '任务失败(疑似视频链接过期)' not in text:
        die('未找到重抓分支 — 请确认是本系列的 m3u8gui.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.15', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.15'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.15')

    text = replace_once(text, A_OLD, A_NEW, '② 释放僵尸任务+重抓期间锁按钮')
    text = replace_once(text, C_OLD, C_NEW, '③ 重抓线程异常兜底')
    text = replace_once(text, B1_OLD, B1_NEW, '④ 成功分支恢复状态与按钮')
    text = replace_once(text, B2_OLD, B2_NEW, '⑤ 失败分支恢复按钮')

    finish(text, 'm3u8gui.py 已升级到 v5.8.15 (重抓后可续传)')


if __name__ == '__main__':
    main()