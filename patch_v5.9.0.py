#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v590.py — m3u8gui.py → v5.9.0 (ffmpeg/ffprobe APP_DIR 兜底查找)
背景: 打包重铸(--noconfirm)清空 dist, 放在里面的 ffmpeg 被带走 →
     抽帧/合并/时长全阵亡, 而其余功能正常(哑弹式故障)。
修复: 新增 _find_tool(): 先查 PATH, 再兜底程序旁(APP_DIR/xxx.exe) —
     兑现原版注释"放exe旁"从未生效的承诺。全部 6 处查找点统一接入。
用法: python patch_v590.py
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


HELP_OLD = """class ShieldBlockedError(Exception):
    pass
"""
HELP_NEW = """class ShieldBlockedError(Exception):
    pass


def _find_tool(name):
    \"\"\"v5.9.0: 先查 PATH, 再兜底程序旁(APP_DIR) — 兑现"放exe旁"承诺。
    打包重铸清空 dist 后, 把 ffmpeg/ffprobe 放回 exe 旁即被找到。\"\"\"
    p = shutil.which(name)
    if p:
        return p
    local = APP_DIR / f'{name}.exe'
    return str(local) if local.exists() else None
"""

A2_OLD = r'''def online_thumbs(got, label, outdir, tc, log, q, stop, proxy=None,
                  fw=None, fixdate=True):
    ffmpeg = shutil.which('ffmpeg')
    probe = shutil.which('ffprobe')
    if not ffmpeg:
        log('未找到 ffmpeg, 无法抽帧', 'err')
        return False
'''
A2_NEW = r'''def online_thumbs(got, label, outdir, tc, log, q, stop, proxy=None,
                  fw=None, fixdate=True):
    ffmpeg = _find_tool('ffmpeg')          # v5.9.0: PATH→APP_DIR 兜底
    probe = _find_tool('ffprobe')
    if not ffmpeg:
        log('未找到 ffmpeg, 无法抽帧 — 放 ffmpeg.exe 到程序旁', 'err')
        return False
'''

A3_OLD = r'''def make_thumbnails_for(video, tc, log, q, stop_event):
    ffmpeg = shutil.which('ffmpeg')
    probe = shutil.which('ffprobe')
    if not ffmpeg:
        log('未找到 ffmpeg, 无法生成缩略图', 'warn')
        return False
'''
A3_NEW = r'''def make_thumbnails_for(video, tc, log, q, stop_event):
    ffmpeg = _find_tool('ffmpeg')          # v5.9.0
    probe = _find_tool('ffprobe')
    if not ffmpeg:
        log('未找到 ffmpeg, 无法生成缩略图 — 放一份到程序旁', 'warn')
        return False
'''

A4_OLD = r'''    def _merge(self, workdir, segs_sel, init_name, output):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
'''
A4_NEW = r'''    def _merge(self, workdir, segs_sel, init_name, output):
        ffmpeg = _find_tool('ffmpeg')      # v5.9.0
        if not ffmpeg:
'''

A5_OLD = r'''    def _timeline_pass(self, workdir, path, expected, force=False, src=None):
        ffmpeg = shutil.which('ffmpeg')
        probe = shutil.which('ffprobe')
        if not ffmpeg or not probe:
            return path
'''
A5_NEW = r'''    def _timeline_pass(self, workdir, path, expected, force=False, src=None):
        ffmpeg = _find_tool('ffmpeg')      # v5.9.0
        probe = _find_tool('ffprobe')
        if not ffmpeg or not probe:
            return path
'''

A6_OLD = r'''        self._append_log('info', 'ffmpeg: ' + (
            '已找到' if shutil.which('ffmpeg')
            else '未找到 — 强烈建议安装(放exe旁或加入PATH)'))
'''
A6_NEW = r'''        self._append_log('info', 'ffmpeg: ' + (
            '已找到' if _find_tool('ffmpeg')
            else '未找到 — 放 ffmpeg.exe+ffprobe.exe 到程序旁即可'))
'''

A7_OLD = r'''        probe = shutil.which('ffprobe')
        if not probe:
            return (kind, None)
'''
A7_NEW = r'''        probe = _find_tool('ffprobe')      # v5.9.0
        if not probe:
            return (kind, None)
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_find_tool' in text:
        print('v5.9.0 补丁已存在, 无需重复打。')
        return

    # 5.8 → 5.9 版本跳级
    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.9.0', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.9.0'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件在 5.8.x 系列')
    print('[OK] ① 版本号 → 5.9.0')

    text = replace_once(text, HELP_OLD, HELP_NEW, '② _find_tool 帮助函数')
    text = replace_once(text, A2_OLD, A2_NEW, '③ online_thumbs 查找')
    text = replace_once(text, A3_OLD, A3_NEW, '④ make_thumbnails_for 查找')
    text = replace_once(text, A4_OLD, A4_NEW, '⑤ _merge 查找')
    text = replace_once(text, A5_OLD, A5_NEW, '⑥ _timeline_pass 查找')
    text = replace_once(text, A6_OLD, A6_NEW, '⑦ 启动横幅查找')
    text = replace_once(text, A7_OLD, A7_NEW, '⑧ sniff 时长探测查找')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.0 (ffmpeg APP_DIR 兜底)')


if __name__ == '__main__':
    main()