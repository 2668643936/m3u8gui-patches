#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_v612b.py — v6.1.1 → v6.1.2 (锚点宽容版)
① 清扫全部 self.thumb_btn 残引(逐行, 无论缩进/位置)
② go() 里补 self._batch_kind = m2(已存在则跳过)
③ 拦截提示类型化 / finish兜底 / 弹窗居中 — 同 v612"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')


def die(msg):
    print('[x] ' + msg)
    sys.exit(1)


text_raw = SRC.read_bytes()
bom = text_raw.startswith(b'\xef\xbb\xbf')
text = text_raw.decode('utf-8-sig')
crlf = '\r\n' in text
if crlf:
    text = text.replace('\r\n', '\n')

if '_batch_kind' in text:
    print('[i] v6.1.2 已打过。')
    sys.exit(0)
if '_batch_center' not in text:
    die('未检测到 v6.1.1(_batch_center)')

# ---------- ① thumb_btn 残引清扫(无条件, 逐行) ----------
lines = text.splitlines(keepends=True)
out, n_cfg, n_tup = [], 0, 0
i = 0
while i < len(lines):
    s = lines[i].strip()
    # 单行 thumb_btn.config → 删行
    if s.startswith('self.thumb_btn.config('):
        n_cfg += 1
        i += 1
        continue
    # 五元组/四元组里的 ", self.thumb_btn" 或 "self.thumb_btn," → 删该片段
    if 'self.thumb_btn' in lines[i]:
        before = lines[i]
        lines[i] = re.sub(r',?\s*self\.thumb_btn,?', '', lines[i])
        # 修掉可能产生的悬空逗号/空括号
        lines[i] = lines[i].replace('(self.start_btn, self.grab_btn, '
                                    'self.batch_btn,\n', '(self.start_btn, '
                                    'self.grab_btn, self.batch_btn,\n')
        if lines[i] != before:
            n_tup += 1
        # 若该行清完只剩括号闭合, 保留; 若变成空行则跳过
        if lines[i].strip() in ('', ')', '):'):
            i += 1
            continue
    out.append(lines[i])
    i += 1
text = ''.join(out)
print(f'[OK] ① thumb_btn 清扫: 删config行×{n_cfg} · 改元组行×{n_tup} · '
      f'剩余引用 {text.count("thumb_btn")} (应为 0)')

# ---------- ② _batch_kind 注入(定位 go() 的 _batch_stop_event 行) ----------
if 'self._batch_kind' not in text:
    KEY = 'self._batch_stop_event = stop_ev'
    n = text.count(KEY)
    if n != 1:
        die(f'② 锚点 _batch_stop_event 匹配 {n} 处(应为 1) — 请把'
            '该行前后10行发我')
    text = text.replace(
        KEY,
        'self._batch_kind = m2               # v6.1.2: 任务类型\n'
        + KEY, 1)
    print('[OK] ② _batch_kind 注入')
else:
    print('[skip] ② _batch_kind 已存在')

# ---------- ③ 拦截提示类型化 ----------
OLD_CHK = """        if self.job or self._batch_running:
            messagebox.showinfo('提示', '已有下载任务在运行')
            return
        if self.thumb_job and self.thumb_job.is_alive():
            messagebox.showinfo('提示', '缩略图任务运行中, 请等它结束')
            return
        win = tk.Toplevel(self)
        win.title('批量任务中心')"""
NEW_CHK = """        if self.job or self._batch_running:
            messagebox.showinfo(
                '提示',
                (f'批量{getattr(self, "_batch_kind", "")}任务运行中'
                 if self._batch_running else '下载任务运行中')
                + ', 请等它结束')
            return
        if self.thumb_job and self.thumb_job.is_alive():
            messagebox.showinfo('提示', '缩略图任务运行中, 请等它结束')
            return
        win = tk.Toplevel(self)
        win.title('批量任务中心')"""
n = text.count(OLD_CHK)
if n == 1:
    text = text.replace(OLD_CHK, NEW_CHK, 1)
    print('[OK] ③ 拦截提示类型化')
elif '批量{getattr' in text:
    print('[skip] ③ 已类型化')
else:
    # 锚点不匹配不致命 — 只影响提示文案, 继续打
    print('[warn] ③ 拦截提示锚点未命中(仅提示文案不变), 跳过')

# ---------- ④ work 线程兜底复位 ----------
OLD_TH = """            _workers = {'抓取': work_grab, '缩略图': work_thumb,
                        '下载': work_download}
            threading.Thread(target=_workers[m2], daemon=True).start()
"""
NEW_TH = """            _workers = {'抓取': work_grab, '缩略图': work_thumb,
                        '下载': work_download}

            def _work_guard():
                try:
                    _workers[m2]()
                finally:
                    if self._batch_running:      # finish 丢失时兜底复位
                        self._batch_running = False
                        self._batch_stop_event = None
                        self.msgq.put(('status', '空闲'))
            threading.Thread(target=_work_guard, daemon=True).start()
"""
n = text.count(OLD_TH)
if n == 1:
    text = text.replace(OLD_TH, NEW_TH, 1)
    print('[OK] ④ work 线程兜底复位')
elif '_work_guard' in text:
    print('[skip] ④ 已存在')
else:
    print('[warn] ④ 兜底锚点未命中(不影响主流程), 跳过')

# ---------- ⑤ 弹窗居中 ----------
if 'def _center_on(' not in text:
    CENTER_FN = '''def _center_on(parent, win):
    """v6.1.2: Toplevel 居中于 parent(主窗口)而非屏幕左上角"""
    try:
        parent.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        win.update_idletasks()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f'+{px + max((pw - ww) // 2, 0)}'
                     f'+{py + max((ph - wh) // 3, 0)}')
    except Exception:
        pass


def _mode_of(v):'''
    if text.count('def _mode_of(v):') != 1:
        die('⑤ _mode_of 锚点异常')
    text = text.replace('def _mode_of(v):', CENTER_FN, 1)
    print('[OK] ⑤ _center_on 定义')
n = text.count("win.geometry('840x720')")
if n == 1:
    text = text.replace("win.geometry('840x720')",
                        "win.geometry('840x720')\n        _center_on(self, win)",
                        1)
    print('[OK] ⑥ 设置窗居中')
n = text.count("win.geometry('860x680')")
if n == 1:
    text = text.replace("win.geometry('860x680')",
                        "win.geometry('860x680')\n        _center_on(self, win)",
                        1)
    print('[OK] ⑦ 任务中心居中')

# ---------- 版本号 ----------
text, n1 = re.subn(r'(m3u8gui\.py v)6\.1\.1', r'\g<1>6.1.2', text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.1\.1'", r"\g<1>6.1.2'", text, count=1)
if n1 != 1 or n2 != 1:
    die('版本号定位失败(应为 6.1.1)')
print('[OK] ⑧ 版本号 → 6.1.2')

try:
    compile(text, SRC.name, 'exec')
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
print(f'[OK] v6.1.2 完成(备份 → {bak.name})')