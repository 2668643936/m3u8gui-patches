#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v585.py — m3u8gui.py → v5.8.5 (时间轴检测升级: 逐帧间隔分析)
旧检测只比"平均帧率 vs 标称帧率", 漏网场景:
  · 平均值吻合但帧间隔抖动(VFR) → "不卡顿但不流畅"
  · r_frame_rate 不在[5,60](如 1000/1) → 帧节奏检查整条跳过
本补丁:
  ① 逐帧 pts 分析: 算中位帧间隔, 偏离中位>22% 的间隔占比>3% 即判 VFR → CFR 重编码
  ② 重编码 fps 优先取 1/中位间隔(比平均帧率更准), 吸附到常用帧率
  ③ "校验通过"日志附带间隔偏差百分比, 便于以后诊断
用法: python patch_v585.py
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


def replace_span(text, start, end, body, name):
    if text.count(start) != 1:
        die(f'{name}: 起始锚点未找到/不唯一: {start!r}')
    i = text.find(start)
    j = text.find(end, i)
    if j < 0:
        die(f'{name}: 结束锚点未找到: {end!r}')
    print(f'[OK] {name}')
    return text[:i] + body + text[j:]


TIMELINE = r'''    def _timeline_pass(self, workdir, path, expected, force=False, src=None):
        ffmpeg = shutil.which('ffmpeg')
        probe = shutil.which('ffprobe')
        if not ffmpeg or not probe:
            return path
        dur = packets = rfps = None
        fr = '0/0'
        try:
            p = subprocess.run(
                [probe, '-v', 'error', '-count_packets', '-select_streams', 'v:0',
                 '-show_entries', 'stream=nb_read_packets,r_frame_rate:format=duration',
                 '-of', 'json', str(path)],
                capture_output=True, text=True, timeout=300,
                creationflags=SUBPROC_FLAGS)
            d = json.loads(p.stdout or '{}')
            streams = d.get('streams') or [{}]
            dur = float(d.get('format', {}).get('duration') or 0) or None
            packets = int(streams[0].get('nb_read_packets') or 0) or None
            fr = (streams[0].get('r_frame_rate') or '0/0')
            num, _, den = fr.partition('/')
            try:
                rfps = (float(num) / float(den or 1)) or None
            except (ValueError, ZeroDivisionError):
                rfps = None
        except Exception:
            return path

        eff = (packets / dur) if (packets and dur) else None

        # v5.8.5: 逐帧 pts 分析 — 直接测量帧间隔均匀度。
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
            if len(pts) >= 200:
                deltas = [b - a for a, b in zip(pts, pts[1:])
                          if 0.0 < (b - a) < 5.0]
                if len(deltas) >= 100:
                    ds = sorted(deltas)
                    med = ds[len(ds) // 2]
                    if med and med > 0:
                        dev = sum(1 for x in deltas
                                  if abs(x - med) > 0.22 * med)
                        jfrac = dev / len(deltas)
        except Exception:
            med = jfrac = None

        probs = []
        if expected is not None and expected >= 5 and dur \
                and not (0.8 <= dur / expected <= 1.25):
            probs.append(f'时长 {dur/60:.1f} vs 预期 {expected/60:.1f} 分钟')
        if eff and rfps and 5 <= rfps <= 60 and abs(eff - rfps) / rfps > 0.15:
            probs.append(f'帧节奏 {eff:.2f} vs 标称 {rfps:.2f}')
        if jfrac is not None and jfrac > 0.03:
            probs.append(f'帧间隔不均: {jfrac * 100:.1f}% 的帧偏离中位节奏'
                         + (f' (≈{1 / med:.2f} 帧/秒)' if med else ''))
        if force and not probs:
            probs.append('用户勾选了强制重编码')
        if not probs:
            if dur:
                self._log(f'时间轴校验通过: 时长 {dur/60:.1f} 分钟'
                          + (f' · {eff:.2f} 帧/秒' if eff else '')
                          + (f' · 间隔偏差 {jfrac * 100:.1f}%'
                             if jfrac is not None else ''), 'ok')
            return path

        self._log('检测到时间轴异常(' + '; '.join(probs) + ') — '
                  '正在重编码为恒定帧率修正...', 'warn')
        # v5.8.5: fps 优先取 1/中位间隔(比平均帧率更贴近真实节奏)
        medfps = (1.0 / med) if med else None
        if medfps:
            for c in (60, 59.94, 50, 30, 29.97, 25, 24, 23.976, 15, 12.5):
                if abs(medfps - c) / c < 0.06:
                    medfps = float(c)
                    break
        if medfps and 5 <= medfps <= 60:
            fps_arg = f'{medfps:g}'
        elif rfps and 5 <= rfps <= 60:
            fps_arg = fr
        elif eff and 5 <= eff <= 60:
            fps_arg = f'{eff:.4f}'
        else:
            fps_arg = '25'
        tmp_out = path.with_name(path.stem + '.fix' + path.suffix)
        cmd = [ffmpeg, '-y', '-loglevel', 'error',
               '-i', (src or 'local.m3u8'),
               '-vsync', 'cfr', '-r', fps_arg,
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k']
        if tmp_out.suffix.lower() in ('.mp4', '.m4v', '.mov'):
            cmd += ['-movflags', '+faststart']
        cmd.append(str(tmp_out.resolve()))
        p = subprocess.run(cmd, cwd=workdir, capture_output=True,
                           text=True, errors='replace',
                           creationflags=SUBPROC_FLAGS)
        if p.returncode != 0 or not tmp_out.exists() \
                or tmp_out.stat().st_size < 1024:
            self._log('重编码失败, 保留原结果:\n' + (p.stderr or '')[-500:], 'warn')
            tmp_out.unlink(missing_ok=True)
            return path
        tmp_out.replace(path)
        self._log(f'重编码完成(CFR {fps_arg} fps), 时间轴已修正', 'ok')
        return path


'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'frame=pts_time' in text:
        print('v5.8.5 时间轴补丁已存在, 无需重复打。')
        return
    if 'def _timeline_pass' not in text:
        die('未找到 _timeline_pass — 请确认是本系列的 m3u8gui.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.5', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.5'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.5')

    text = replace_span(
        text, '    def _timeline_pass(self, workdir, path, expected, '
              'force=False, src=None):',
        '# ================= 浏览器自动抓取 =================', TIMELINE,
        '② _timeline_pass 升级(逐帧间隔分析)')

    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'补丁后语法校验失败: {e} — 原文件未改动')

    bak = SRC.with_name(SRC.name + '.bak')
    k = 1
    while bak.exists():
        k += 1
        bak = SRC.with_name(f'{SRC.name}.bak{k}')
    shutil.copy2(SRC, bak)
    SRC.write_text(text, encoding='utf-8')
    print()
    print(f'[OK] 原文件已备份 → {bak.name}')
    print('[OK] m3u8gui.py 已升级到 v5.8.5 (时间轴逐帧检测)')


if __name__ == '__main__':
    main()