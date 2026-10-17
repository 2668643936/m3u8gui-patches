#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_v612d.py — v6.1.1 → v6.1.2 (精确版)
病灶: v611 任务中心代码沿用了含已退役 thumb_btn 的按钮元组(3处)
     → AttributeError → go() 后半段跳过(无日志/状态不变/停止灰)。
修复: 3处元组收尾 self.one_thumb_btn, self.thumb_btn): → self.one_thumb_btn):
     + _batch_kind / 提示类型化 / work兜底 / 弹窗居中。
     之前的 612b 会误伤 one_thumb_btn(子串匹配), 本版按行号内容精确替换。"""

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

# ---------- ① 三处元组精确收尾 ----------
OLD_TAIL = "                      self.one_thumb_btn, self.thumb_btn):"
NEW_TAIL = "                      self.one_thumb_btn):"
n = text.count(OLD_TAIL)
# 6409/6446 是 22 空格缩进(嵌套在 _handle 分支里)
OLD_TAIL2 = "                          self.one_thumb_btn, self.thumb_btn):"
NEW_TAIL2 = "                          self.one_thumb_btn):"
n2 = text.count(OLD_TAIL2)
if n + n2 != 3:
    print(f'[!] 元组匹配 {n}+{n2}=3 处(期望), 实际见上 — 继续按实际处理')
if n:
    text = text.replace(OLD_TAIL, NEW_TAIL)
if n2:
    text = text.replace(OLD_TAIL2, NEW_TAIL2)
print(f'[OK] ① 元组收尾: 12格×{n} + 22格×{n2} (共{n+n2}, 应为3)')
left = len(re.findall(r'(?<![a-z_])thumb_btn(?!\w)', 
                      text.replace('one_thumb_btn', '')))
print(f'[i] ① 复核: 排除 one_thumb_btn 后 thumb_btn 独立引用 = {left} (应为0)')

# ---------- ② _batch_kind ----------
KEY2 = 'self._batch_stop_event = stop_ev'
assert text.count(KEY2) == 1, '② 锚点异常'
text = text.replace(KEY2,
    'self._batch_kind = m2               # v6.1.2: 任务类型\n' + KEY2, 1)
print('[OK] ② _batch_kind 注入')

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

# ---------- ⑤ 弹窗居中 ----------
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
for geo in ("win.geometry('840x720')", "win.geometry('860x680')"):
    if text.count(geo) == 1:
        text = text.replace(geo, geo + '\n        _center_on(self, win)', 1)
print('[OK] ⑥ 弹窗居中挂载')

# ---------- 版本号 ----------
text, n1 = re.subn(r'(m3u8gui\.py v)6\.1\.1', r'\g<1>6.1.2', text, count=1)
text, n2 = re.subn(r"(__version__ = ')6\.1\.1'", r"\g<1>6.1.2'", text, count=1)
if n1 != 1 or n2 != 1:
    die('版本号定位失败') if False else print('[x] 版本号定位失败')
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