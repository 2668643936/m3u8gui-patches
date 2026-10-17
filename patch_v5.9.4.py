#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v594.py — m3u8gui.py → v5.9.4 (失败无限循环: 自动重抓+自动续传)
背景: 短命链接+限速的站 → 下几小时要反复手动重抓+手动续传。
修复(设置新增开关「失败无限循环」, 仅单任务, 不影响批量):
  ① 链接失效 → 自动重抓 → 成功后自动续传(不再等人点开始)
  ② 重抓失败 → 60秒后自动重试(此前直接放弃)
  ③ 循环轮次全程可见; 「停止」随时退出; 完成自动收尾
用法: python patch_v594.py
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


R1_OLD = """        self._job_page_src = ''
        self._regrab_done = False
"""
R1_NEW = """        self._job_page_src = ''
        self._regrab_done = False
        self._loop_stop = False             # v5.9.4: 循环停机牌
        self._loop_round = 0               # v5.9.4: 循环轮次
"""

R2_OLD = """        self.outdir_var = tk.StringVar(value=_dft)
"""
R2_NEW = """        self.outdir_var = tk.StringVar(value=_dft)
        self.loop_var = tk.BooleanVar(value=bool(s.get('loop_mode')))
"""

R3_OLD = """                out_dir=self.outdir_var.get().strip(),
                page_url=self.page_var.get().strip(),
"""
R3_NEW = """                out_dir=self.outdir_var.get().strip(),
                loop_mode=self.loop_var.get(),
                page_url=self.page_var.get().strip(),
"""

R4_OLD = r'''        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='代理:', width=10).pack(side='left')
'''
R4_NEW = r'''        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Checkbutton(row, text='失败无限循环(自动重抓+自动续传)',
                        variable=self.loop_var).pack(side='left')
        ttk.Label(row, text='(仅单任务; 链接过期自动续命, 点「停止」退出)',
                  foreground='#888888').pack(side='left', padx=4)
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='代理:', width=10).pack(side='left')
'''

R5_OLD = r'''            if ok and '下载完成: ' in text:
                try:
                    self._last_output = text.split('下载完成: ', 1)[1].strip()
                    self._remember_dir(str(Path(self._last_output).parent))
                except Exception:
                    pass
'''
R5_NEW = r'''            if ok and '下载完成: ' in text:
                try:
                    self._last_output = text.split('下载完成: ', 1)[1].strip()
                    self._remember_dir(str(Path(self._last_output).parent))
                except Exception:
                    pass
                self._loop_round = 0            # v5.9.4: 完成即收环
'''

R6_OLD = r'''                self._append_log('warn', '任务失败(疑似视频链接过期) → '
                                         '用原网页链接自动重抓一次...')
'''
R6_NEW = r'''                _ltxt = (f'[循环·第{self._loop_round + 1}轮] '
                         if self.loop_var.get() else '')
                self._append_log('warn', f'任务失败(疑似链接过期) → '
                                         f'{_ltxt}用原网页链接自动重抓...')
'''

R7_OLD = r'''        elif kind == 'regrab_done':
            got, pg = msg[1], msg[2]
            if got:
                self._append_log('ok', '重抓成功, 视频直链已更新 → '
                                       '请点「开始 / 续传」继续')
                self.status_lbl.config(text='已重抓, 可续传')   # v5.8.15
                for b in (self.start_btn, self.grab_btn, self.batch_btn,
                          self.one_thumb_btn, self.thumb_btn):
                    b.config(state='normal')                   # v5.8.15
                self.url_var.set(got.get('url', ''))
                if got.get('referer'):
                    self.ref_var.set(got['referer'])
                if got.get('cookie'):
                    self.cookie_var.set(got['cookie'])
                title = got.get('title') or ''
                if title:
                    fw = parse_filter_words(self.filter_var.get())
                    t = transform_title(title, fw, self.fixdate_var.get())
                    outdir = Path(self.out_var.get().strip()
                                  or 'video.mp4').resolve().parent
                    base = safe_name(t, url=got.get('url', ''), base_dir=outdir,
                                     limit=80, filter_words=fw)
                    self._out_setting = True
                    self.out_var.set(base + '.mp4')
                    self._out_setting = False
            else:
                self._append_log('err', '重抓也失败 — 请手动处理该视频')
                self.status_lbl.config(text='重抓失败')        # v5.8.15
                for b in (self.start_btn, self.grab_btn, self.batch_btn,
                          self.one_thumb_btn, self.thumb_btn):
                    b.config(state='normal')                   # v5.8.15
            self._regrab_done = False
'''

R7_NEW = r'''        elif kind == 'regrab_done':
            got, pg = msg[1], msg[2]
            in_loop = (self.loop_var.get() and not self._loop_stop
                       and bool(pg) and not self._batch_running)
            if got:
                self.url_var.set(got.get('url', ''))
                if got.get('referer'):
                    self.ref_var.set(got['referer'])
                if got.get('cookie'):
                    self.cookie_var.set(got['cookie'])
                title = got.get('title') or ''
                if title:
                    fw = parse_filter_words(self.filter_var.get())
                    t = transform_title(title, fw, self.fixdate_var.get())
                    outdir = Path(self.out_var.get().strip()
                                  or 'video.mp4').resolve().parent
                    base = safe_name(t, url=got.get('url', ''), base_dir=outdir,
                                     limit=80, filter_words=fw)
                    self._out_setting = True
                    self.out_var.set(base + '.mp4')
                    self._out_setting = False
                if in_loop and not self.job:      # v5.9.4: 无限循环·自动续传
                    self._loop_round += 1
                    self._append_log('ok', f'[循环·第{self._loop_round}轮] '
                                           '重抓成功 → 自动续传启动'
                                           '(点「停止」随时退出)')
                    self.status_lbl.config(text=f'循环·第{self._loop_round}轮')
                    self._regrab_done = False
                    self._start()
                    return
                self._append_log('ok', '重抓成功, 视频直链已更新 → '
                                       '请点「开始 / 续传」继续')
                self.status_lbl.config(text='已重抓, 可续传')   # v5.8.15
                for b in (self.start_btn, self.grab_btn, self.batch_btn,
                          self.one_thumb_btn, self.thumb_btn):
                    b.config(state='normal')                   # v5.8.15
            else:
                if in_loop:                     # v5.9.4: 循环·失败延迟重试
                    self._append_log('warn', f'[循环·第{self._loop_round}轮] '
                                             '重抓失败 — 60秒后自动重试'
                                             '(点「停止」退出循环)')
                    self.status_lbl.config(text='循环·重试等待中...')

                    def _retry_rg():
                        time.sleep(60)
                        if self._loop_stop:
                            self.msgq.put(('log', 'info',
                                           '[循环] 已停止, 退出'))
                            return

                        def lg(l, m):
                            self.msgq.put(('log', l, m))
                        self.msgq.put(('log', 'info', '[循环] 重试重抓...'))
                        try:
                            got2 = smart_resolve(pg, lg,
                                                self.proxy_var.get().strip()
                                                or None, False, None,
                                                browser=self.browser_var.get(),
                                                force_browser=True)
                        except Exception as e:
                            lg('err', f'重抓异常: {e!r}')
                            got2 = None
                        self.msgq.put(('regrab_done', got2, pg))

                    threading.Thread(target=_retry_rg,
                                     daemon=True).start()
                    self._regrab_done = False
                    return
                self._append_log('err', '重抓也失败 — 请手动处理该视频')
                self.status_lbl.config(text='重抓失败')        # v5.8.15
                for b in (self.start_btn, self.grab_btn, self.batch_btn,
                          self.one_thumb_btn, self.thumb_btn):
                    b.config(state='normal')                   # v5.8.15
            self._regrab_done = False
'''

R8_OLD = """        self._job_page_src = page_src
        self._regrab_done = False
"""
R8_NEW = """        self._job_page_src = page_src
        self._regrab_done = False
        self._loop_stop = False             # v5.9.4: 新会话解除停机牌
"""

R9_OLD = """    def _stop(self):
        if self.job:
"""
R9_NEW = """    def _stop(self):
        self._loop_stop = True              # v5.9.4: 循环停机牌(先挂上)
        if self.job:
"""


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_loop_stop' in text:
        print('v5.9.4 补丁已存在, 无需重复打。')
        return
    for feat in ('self.outdir_var', '已重抓, 可续传'):
        if feat not in text:
            die(f'未检测到前置特征 {feat!r} — 请先打 v5.8.15 / v5.9.1')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.4', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.4'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件在 5.8/5.9 系列')
    print('[OK] ① 版本号 → 5.9.4')

    text = replace_once(text, R1_OLD, R1_NEW, '② 循环状态变量')
    text = replace_once(text, R2_OLD, R2_NEW, '③ loop_var 设置变量')
    text = replace_once(text, R3_OLD, R3_NEW, '④ 设置持久化')
    text = replace_once(text, R4_OLD, R4_NEW, '⑤ 设置界面开关')
    text = replace_once(text, R5_OLD, R5_NEW, '⑥ 完成即收环')
    text = replace_once(text, R6_OLD, R6_NEW, '⑦ 失败日志带轮次')
    text = replace_once(text, R7_OLD, R7_NEW, '⑧ regrab_done: 自动续传+重试')
    text = replace_once(text, R8_OLD, R8_NEW, '⑨ start 解除停机牌')
    text = replace_once(text, R9_OLD, R9_NEW, '⑩ stop 先挂停机牌')

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
    print('[OK] m3.8gui.py 已升级到 v5.9.4 (失败无限循环)')


if __name__ == '__main__':
    main()