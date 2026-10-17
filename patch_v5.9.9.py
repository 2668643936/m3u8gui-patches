#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v599.py — m3u8gui.py v5.9.8 → v5.9.9 (设置不再冲掉「保存为」文件名)

问题: 设置窗口「保存并关闭」无条件执行
      self.out_var.set(str(Path(od) / 'video.mp4'))
      只要默认目录已设置, 每次开设置→保存, 「保存为」就被重置成
      video.mp4 — 冲掉抓取自动命名的文件名/自定义路径, 且若该文件
      带 .parts 续传记录, 续传链直接被打断。

修复(语义收紧):
  · 「保存为」是裸文件名 → 移入默认目录(补全)
  · 「保存为」正位于旧默认目录内 → 跟随新默认目录, 保留文件名
  · 自定义路径 / 带 .parts 续传记录的输出 → 一律不碰
  · 默认目录没改 → 什么都不动

依赖: 需已打 v5.9.7(_po.with_name); 与 v5.9.8 相互独立
用法: python patch_v599.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_same_old', '_has_parts')


def die(msg):
    print()
    print('[x] ' + msg)
    print('[x] 未做任何修改, 原文件保持不动。')
    sys.exit(1)


def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        die(f'{name}: 锚点匹配 {n} 处(应为 1 处) — 请把完整输出发回定位')
    print(f'[OK] {name}')
    return text.replace(old, new, 1)


# ---------- ③ done() 语义收紧 ----------
D_OLD = '''        def done():
            od = self.outdir_var.get().strip()    # v5.9.1: 设了目录立即生效
            if od and Path(od).is_dir():
                self.out_var.set(str(Path(od) / 'video.mp4'))
            self._save_settings()
            win.destroy()
'''
D_NEW = '''        def done():
            od = self.outdir_var.get().strip()    # v5.9.1: 设了目录立即生效
            if od and Path(od).is_dir():
                # v5.9.9: 只在「保存为」是裸文件名、或正位于旧默认目录内
                # 时才跟随新默认目录(保留文件名); 自定义路径与带 .parts
                # 续传记录的输出一律不碰 — 旧版无条件重置成 video.mp4,
                # 会冲掉抓取自动命名的文件名并打断续传。
                cur = self.out_var.get().strip() or 'video.mp4'
                _po = Path(cur)
                _old = (self.settings.get('out_dir') or '').strip()
                _same_old = False
                if _old:
                    try:
                        _same_old = (os.path.normcase(
                            os.path.abspath(str(_po.parent)))
                            == os.path.normcase(os.path.abspath(_old)))
                    except Exception:
                        _same_old = str(_po.parent) == _old
                _follow = (_po.parent == Path('.') or _same_old)
                _has_parts = (Path(str(_po) + '.parts')
                              / 'state.json').exists()
                if _follow and not _has_parts:
                    self.out_var.set(str(Path(od) / _po.name))
            self._save_settings()
            win.destroy()
'''

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv5.9.9: 设置「保存并关闭」不再无条件重置「保存为」— 仅裸名/\n'
           '        旧默认目录内跟随新目录(保留文件名), 续传目标不碰\n'
           'v5.8.1:\n')


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请把本脚本与 m3u8gui.py 放同目录, 或传路径参数')
    raw = SRC.read_bytes()
    has_bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    had_crlf = '\r\n' in text
    if had_crlf:
        text = text.replace('\r\n', '\n')

    hits = [t for t in PATCH_TOKENS if t in text]
    if hits:
        print(f'[i] 检测到补丁痕迹 {hits} — 无需重复打。')
        return
    if '_po.with_name' not in text:
        die('未检测到 v5.9.7(_po.with_name) — 请先运行 patch_v597.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.9', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.9'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 5.9.9')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, D_OLD, D_NEW, '③ 设置done()语义收紧')

    for tok in ('PLACEHOLDER_TBD', '__TBD__', 'file_hint_placeholder'):
        if tok in text:
            die(f'自检失败: 产物含占位符 {tok!r} — 拒绝写入')
    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'语法校验失败: {e} — 原文件未改动')

    if had_crlf:
        text = text.replace('\n', '\r\n')
    data = text.encode('utf-8')
    if has_bom:
        data = b'\xef\xbb\xbf' + data

    bak = SRC.with_name(SRC.name + '.bak')
    k = 1
    while bak.exists():
        k += 1
        bak = SRC.with_name(f'{SRC.name}.bak{k}')
    shutil.copy2(SRC, bak)
    SRC.write_bytes(data)
    print()
    print(f'[OK] 原文件已备份 → {bak.name}')
    print('[OK] m3u8gui.py 已升级到 v5.9.9:')
    print('     · 开设置→保存: 「保存为」不再被重置成 video.mp4')
    print('     · 改默认目录时: 文件名保留, 仅目录跟随')
    print('     · 带 .parts 续传记录的输出永不被劫持')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()