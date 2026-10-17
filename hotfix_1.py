#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hotfix_btn_merge.py — 不升版: 两个批量按钮合并为「批量任务」"""

import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

text = SRC.read_text(encoding='utf-8-sig')

if "text='批量任务'" in text:
    print('[i] 已合并过。')
    sys.exit(0)

OLD_BTNS = """        self.batch_btn = ttk.Button(row, text='批量下载',
                                    command=self._batch_download)
        self.batch_btn.pack(side='left', padx=8)
        self.one_thumb_btn = ttk.Button(row, text='缩略图',
                                        command=self._one_thumb)
        self.one_thumb_btn.pack(side='left', padx=8)
        self.thumb_btn = ttk.Button(row, text='批量缩略图',
                                   command=self._thumbs_only)
        self.thumb_btn.pack(side='left', padx=8)"""
NEW_BTNS = """        self.one_thumb_btn = ttk.Button(row, text='缩略图',
                                        command=self._one_thumb)
        self.one_thumb_btn.pack(side='left', padx=8)
        self.batch_btn = ttk.Button(row, text='批量任务',
                                    command=self._batch_center)
        self.batch_btn.pack(side='left', padx=8)"""
assert text.count(OLD_BTNS) == 1, '按钮锚点不匹配'
text = text.replace(OLD_BTNS, NEW_BTNS, 1)

# thumb_btn 引用清理: 五元组降四元组 + 单行 config 删除
OLD_TUP = """        for b in (self.start_btn, self.grab_btn, self.batch_btn,
                  self.one_thumb_btn, self.thumb_btn):"""
NEW_TUP = """        for b in (self.start_btn, self.grab_btn, self.batch_btn,
                  self.one_thumb_btn):"""
n = text.count(OLD_TUP)
text = text.replace(OLD_TUP, NEW_TUP)
print(f'[OK] 五元组降级 ×{n}')

n2 = 0
out = []
for ln in text.splitlines(keepends=True):
    s = ln.strip()
    if s.startswith('self.thumb_btn.config(') or s == 'self.thumb_btn.config(state=\'normal\')':
        n2 += 1
        continue
    out.append(ln)
text = ''.join(out)
print(f'[OK] 删除 thumb_btn.config 行 ×{n2}')

import re
left = re.findall(r'thumb_btn', text)
print(f'[i] 剩余 thumb_btn 引用: {len(left)} (应为 0)')

bak = SRC.with_name(SRC.name + '.bak')
k = 1
while bak.exists():
    k += 1
    bak = SRC.with_name(f'{SRC.name}.bak{k}')
shutil.copy2(SRC, bak)
SRC.write_text(text, encoding='utf-8')
print(f'[OK] 完成(备份 → {bak.name})')