#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_v612e.py — v6.1.1 → v6.1.2
vs v612d: ② 注入改为带缩进锚定(此前恢复行丢失12格缩进→unexpected indent)
          ① 改用换行锚定, 消除 22sp 模式在 26sp 行内的子串误报"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

raw = SRC.read_bytes()
bom = raw.startswith(b'\xef\xbb\xbf')
text = raw.decode('utf-8-sig')
crlf = '\r\n' in text
if crlf:
    text = text.replace('\r\n', '\n')

if '_batch_kind' in text:
    print('[i] 已打过。'); sys.exit(0)

# ---------- ① 元组收尾(换行锚定, 先长后短) ----------
OLD2 = '\n                          self.one_thumb_btn, self.thumb_btn):'
NEW2 = '\n                          self.one_thumb_btn):'
n2 = text.count(OLD2)
text = text.replace(OLD2, NEW2)
OLD1 = '\n                      self.one_thumb_btn, self.thumb_btn):'
NEW1 = '\n                      self.one_thumb_btn):'
n1 = text.count(OLD1)
text = text.replace(OLD1, NEW1)
print(f'[OK] ① 元组收尾: 26格×{n2} + 22格×{n1} (共{n1+n2}, 应为3)')
resid = len(re.findall(r'thumb_btn', text.replace('one_thumb_btn', '')))
print(f'[i] ① 复核: 独立 thumb_btn 引用 = {resid} (应为0)')

# ---------- ② _batch_kind 注入(带缩进锚定!) ----------
KEY2 = '\n            self._batch_stop_event = stop_ev'
if text.count(KEY2) != 1:
    print(f'[x] ② 锚点匹配 {text.count(KEY2)} 处(应为1) — 未改动')
    sys.exit(1)
text = text.replace(
    KEY2,
    '\n            self._batch_kind = m2'
    '               # v6.1.2: 任务类型' + KEY2, 1)
print('[OK] ② _batch_kind 注入(缩进保持)')

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
if text.count(OLD_CHK) == 1:
    text = text.replace(OLD_CHK, NEW_CHK, 1)
    print('[OK] ③ 拦截提示类型化')
else:
    print('[warn] ③ 提示文案锚点未命中, 跳过(不影响功能)')

# ---------- ④ work 线程兜底 ----------
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
                    if self._batch_running:
                        self._batch_running = False
                        self._batch_stop_event = None
                        self.msgq.put(('status', '空闲'))
            threading.Thread(target=_work_guard, daemon=True).start()
"""
if text.count(OLD_TH) == 1:
    text = text.replace(OLD_TH, NEW_TH, 1)
    print('[OK] ④ work 线程兜底')
else:
    print('[warn] ④ 兜底锚点未命中, 跳过')

# ---------- ⑤⑥ 弹窗居中 ----------
if 'def _center_on(' not in text:
    text = text.replace('def _mode_of(v):', '''def _center_on(parent, win):
    """v6.1.2: Toplevel 居中于主窗口"""
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


def _mode_of(v):''', 1)
    print('[OK] ⑤ _center_on 定义')
nset = nctr = 0
for geo in ("win.geometry('840x720')", "win.geometry('860x680')"):
    if text.count(geo) == 1:
        text = text.replace(geo, geo + '\n        _center_on(self, win)', 1)
        if '840' in geo:
            nset = 1
        else:
            nctr = 1
print(f'[OK] ⑥ 弹窗居中挂载: 设置×{nset} 任务中心×{nctr} (各应为1)')

# ---------- 版本号 ----------
text, n1v = re.subn(r'(m3u8gui\.py v)6\.1\.1', r'\g<1>6.1.2', text, count=1)
text, n2v = re.subn(r"(__version__ = ')6\.1\.1'", r"\g<1>6.1.2'", text, count=1)
if n1v != 1 or n2v != 1:
    print('[x] 版本号定位失败 — 未改动')
    sys.exit(1)
print('[OK] ⑦ 版本号 → 6.1.2')

try:
    compile(text, SRC.name, 'exec')
except SyntaxError as e:
    print(f'[x] 语法校验失败: {e} — 未改动')
    sys.exit(1)
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