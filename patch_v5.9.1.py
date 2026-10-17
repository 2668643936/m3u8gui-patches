#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v591.py — m3u8gui.py → v5.9.1 (清空连存档 + 默认输出目录)
  ① 批量缩略图/批量下载的「清空」按钮: 连 settings.json 里的
     持久化清单一起清(旧版只清文本框, 下次打开清单复活)
  ② 设置新增「默认目录」: 设定后 保存为/批量输出 默认都进这里,
     留空则维持"跟随上次输出目录"(v5.8.17 行为)
用法: python patch_v591.py
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


A1_OLD = r'''        _lod = s.get('last_outdir')                 # v5.8.17
        self.out_var = tk.StringVar(
            value=(str(Path(_lod) / 'video.mp4') if _lod else 'video.mp4'))
'''
A1_NEW = r'''        _dft = (s.get('out_dir') or '').strip()     # v5.9.1: 显式默认目录优先
        _lod = _dft or s.get('last_outdir')
        self.out_var = tk.StringVar(
            value=(str(Path(_lod) / 'video.mp4') if _lod else 'video.mp4'))
        self.outdir_var = tk.StringVar(value=_dft)
'''

A2_OLD = r'''                browser=self.browser_var.get(),
                sniff_strategy=self.sniff_var.get(),
                page_url=self.page_var.get().strip(),
'''
A2_NEW = r'''                browser=self.browser_var.get(),
                sniff_strategy=self.sniff_var.get(),
                out_dir=self.outdir_var.get().strip(),
                page_url=self.page_var.get().strip(),
'''

A3_OLD = r'''        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='代理:', width=10).pack(side='left')
'''
A3_NEW = r'''        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='默认目录:', width=10).pack(side='left')
        ttk.Entry(row, textvariable=self.outdir_var).pack(
            side='left', fill='x', expand=True)

        def _brw_out():
            d = filedialog.askdirectory(parent=win)
            if d:
                self.outdir_var.set(d)

        ttk.Button(row, text='浏览...', width=8,
                   command=_brw_out).pack(side='left', padx=(6, 0))
        ttk.Label(df, text='(设定后所有输出默认进这里; 留空=跟随上次输出目录)',
                  foreground='#888888').pack(anchor='w')
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='代理:', width=10).pack(side='left')
'''

A4_OLD = r'''        def done():
            self._save_settings()
            win.destroy()
'''
A4_NEW = r'''        def done():
            od = self.outdir_var.get().strip()    # v5.9.1: 设了目录立即生效
            if od and Path(od).is_dir():
                self.out_var.set(str(Path(od) / 'video.mp4'))
            self._save_settings()
            win.destroy()
'''

A5_OLD = r'''        ttk.Button(bar, text='清空', width=6,
                   command=lambda: txt.delete('1.0', 'end')).pack(side='left', padx=8)
'''
A5_NEW = r'''        def _clear_th():                     # v5.9.1: 清空连持久化一起
            txt.delete('1.0', 'end')
            self.settings['batch_th'] = ''
            self._save_settings()
        ttk.Button(bar, text='清空', width=6,
                   command=_clear_th).pack(side='left', padx=8)
'''

A6_OLD = r'''        ttk.Button(bar, text='清空', width=6,
                   command=lambda: txt.delete('1.0', 'end')).pack(side='right',
                                                                  padx=8)
'''
A6_NEW = r'''        def _clear_dl():                     # v5.9.1: 清空连持久化一起
            txt.delete('1.0', 'end')
            self.settings['batch_dl'] = ''
            self._save_settings()
        ttk.Button(bar, text='清空', width=6,
                   command=_clear_dl).pack(side='right', padx=8)
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_clear_th' in text:
        print('v5.9.1 补丁已存在, 无需重复打。')
        return
    for feat in ('last_outdir', 'sniff_strategy'):
        if feat not in text:
            die(f'未检测到前置特征 {feat!r} — 请确认 v5.8.12/5.8.17 已打')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.1', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.1'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件在 5.8/5.9 系列')
    print('[OK] ① 版本号 → 5.9.1')

    text = replace_once(text, A1_OLD, A1_NEW, '② 默认目录变量(优先于last_outdir)')
    text = replace_once(text, A2_OLD, A2_NEW, '③ 设置持久化')
    text = replace_once(text, A3_OLD, A3_NEW, '④ 设置界面默认目录栏')
    text = replace_once(text, A4_OLD, A4_NEW, '⑤ 保存时立即生效')
    text = replace_once(text, A5_OLD, A5_NEW, '⑥ 缩略图清空连存档')
    text = replace_once(text, A6_OLD, A6_NEW, '⑦ 下载清空连存档')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.1 (清空连存档+默认目录)')


if __name__ == '__main__':
    main()