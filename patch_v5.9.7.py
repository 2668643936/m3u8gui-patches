#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v597.py — m3u8gui.py v5.9.6 → v5.9.7

修复两个问题:
  ① 抓取/重抓后输出目录丢失: grab_done/regrab_done 把「保存为」设成
     裸文件名(base + '.mp4'), 目录被丢 → 下载落到程序目录(CWD)。
     改为保留原目录(with_name); 若原本就是裸名则补「设置→默认目录」。
  ② 合并后久等: _timeline_pass 第二遍 ffprobe 用 frame=pts_time 做全片
     逐帧分析 — 解码级, 60fps 视频上万帧动辄 2-3 分钟。改为首/中/尾
     3 个 8% 窗口抽样(超长视频每窗封顶120s), 统计结论不变, 校验约 1/4 时间。

用法: python patch_v597.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_po.with_name', 'read_intervals')


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


# ---------- ① grab_done: 保留输出目录 ----------
A1_OLD = '''            title = got.get('title') or ''
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
                self._append_log('ok', f'文件名已确定: {base}')
'''
A1_NEW = '''            title = got.get('title') or ''
            if title:
                fw = parse_filter_words(self.filter_var.get())
                t = transform_title(title, fw, self.fixdate_var.get())
                cur_out = self.out_var.get().strip() or 'video.mp4'
                _po = Path(cur_out)
                if _po.parent == Path('.'):     # v5.9.7: 裸名 → 补默认目录
                    _dd = (self.outdir_var.get().strip()
                           or (self.settings.get('out_dir') or '')).strip()
                    if _dd and Path(_dd).is_dir():
                        _po = Path(_dd) / _po.name
                outdir = _po.resolve().parent
                base = safe_name(t, url=got.get('url', ''), base_dir=outdir,
                                 limit=80, filter_words=fw)
                self._out_setting = True
                self.out_var.set(str(_po.with_name(base + '.mp4')))
                self._out_setting = False
                self._append_log('ok', f'文件名已确定: {self.out_var.get()}')
'''

# ---------- ② regrab_done: 同样保留目录(缩进多4格, 锚点含 if in_loop 行) ----------
A2_OLD = '''                title = got.get('title') or ''
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
'''
A2_NEW = '''                title = got.get('title') or ''
                if title:
                    fw = parse_filter_words(self.filter_var.get())
                    t = transform_title(title, fw, self.fixdate_var.get())
                    cur_out = self.out_var.get().strip() or 'video.mp4'
                    _po = Path(cur_out)
                    if _po.parent == Path('.'):   # v5.9.7: 裸名 → 补默认目录
                        _dd = (self.outdir_var.get().strip()
                               or (self.settings.get('out_dir') or '')).strip()
                        if _dd and Path(_dd).is_dir():
                            _po = Path(_dd) / _po.name
                    outdir = _po.resolve().parent
                    base = safe_name(t, url=got.get('url', ''), base_dir=outdir,
                                     limit=80, filter_words=fw)
                    self._out_setting = True
                    self.out_var.set(str(_po.with_name(base + '.mp4')))
                    self._out_setting = False
                if in_loop and not self.job:      # v5.9.4: 无限循环·自动续传
'''

# ---------- ③ 时间轴 pts 抽样分析(合并后提速) ----------
B_OLD = '''        # v5.8.5: 逐帧 pts 分析 — 直接测量帧间隔均匀度。
        # 旧法只看平均帧率, "平均吻合但间隔抖动"的 VFR 会漏网。
        med = jfrac = None
        try:
            p2 = subprocess.run(
                [probe, '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'frame=pts_time', '-of', 'csv=p=0',
                 str(path)],
                capture_output=True, text=True, timeout=900,
                creationflags=SUBPROC_FLAGS)
            pts = []
            for ln in (p2.stdout or '').splitlines():
                ln = ln.strip().rstrip(',')
                if not ln:
                    continue
                try:
                    pts.append(float(ln))
                except ValueError:
                    pass
'''
B_NEW = '''        # v5.8.5/v5.9.7: pts 间隔均匀度分析(抓 VFR/抖动)。
        # v5.9.7: frame=pts_time 是解码级分析 — 每帧都要真的解出来,
        # 60fps 长视频动辄 2-3 分钟(正是"合并后久等"的主因)。
        # 改为首/中/尾 3 个 8% 窗口抽样(超长视频每窗封顶120s),
        # 间隔均匀度统计结论不变; 跨窗大间隔由旧有 <5s 过滤器剔除。
        med = jfrac = None
        try:
            wins = []
            if dur and dur >= 60:
                for a, b in ((0.06, 0.14), (0.46, 0.54), (0.86, 0.94)):
                    s0, e0 = dur * a, dur * b
                    if e0 - s0 > 120:          # 超长视频窗口封顶
                        e0 = s0 + 120
                    wins.append((s0, e0))
            else:
                wins = [None]                  # 短视频/时长未知 → 全片
            self._log('时间轴 pts 分析: '
                      + ('抽样 3 窗×8%(v5.9.7 提速)' if wins[0] else '全片'))
            pts = []
            for iv in wins:
                argv = [probe, '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'frame=pts_time', '-of', 'csv=p=0']
                if iv:
                    argv += ['-read_intervals', f'{iv[0]:.2f}/{iv[1]:.2f}']
                argv.append(str(path))
                p2 = subprocess.run(argv, capture_output=True, text=True,
                                    timeout=(300 if iv else 900),
                                    creationflags=SUBPROC_FLAGS)
                for ln in (p2.stdout or '').splitlines():
                    ln = ln.strip().rstrip(',')
                    if not ln:
                        continue
                    try:
                        pts.append(float(ln))
                    except ValueError:
                        pass
'''

# ---------- ④ 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv5.9.7: 抓取/重抓后保留输出目录(裸文件名不再落到程序目录) /\n'
           '        时间轴pts抽样分析(首中尾3×8%窗), 合并后校验提速~4x\n'
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
    if '_res_try_cache' not in text:
        die('未检测到 v5.9.6(_res_try_cache) — 请先运行 patch_v596.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.7', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.7'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 5.9.7')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, A1_OLD, A1_NEW, '③ grab_done 保留输出目录')
    text = replace_once(text, A2_OLD, A2_NEW, '④ regrab_done 保留输出目录')
    text = replace_once(text, B_OLD, B_NEW, '⑤ 时间轴 pts 抽样分析')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.7:')
    print('     · 抓取/重抓后文件名保留原目录(裸名时补默认目录)')
    print('     · 时间轴 pts 改抽样分析, 合并后等待约降到 1/4')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()