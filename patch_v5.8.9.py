#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v589.py — m3u8gui.py → v5.8.9 (白框收尾: 三条漏网通道全堵)
  ① 驱动控制台窗口(msedgedriver/chromedriver)按进程名收编 — 只挪不关
     (关控制台=杀驱动)
  ② 最大化窗口先还原(SW_SHOWNORMAL)再挪 — 旧版 SetWindowPos 对最大化
     静默失效
  ③ PID 表查空时, 退回"驱动进程的直接子进程"当浏览器 PID
  ④ 挪窗写诊断日志: [窗口守卫] 移出屏幕: 进程名 "标题" (同一窗口只记一次)
用法: python patch_v589.py   (需已打 patch_v587.py)
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


def replace_span(text, start, end, body, name):
    if text.count(start) != 1:
        die(f'{name}: 起始锚点未找到/不唯一: {start!r}')
    i = text.find(start)
    j = text.find(end, i)
    if j < 0:
        die(f'{name}: 结束锚点未找到: {end!r}')
    print(f'[OK] {name}')
    return text[:i] + body + text[j:]


BP_NEW = r'''def _browser_pids(prof, drv_pid=None):
    """v5.8.9: 找自动抓取浏览器 PID — 先按档案路径匹配命令行,
    查空时退回'驱动进程的直接子进程'(浏览器必是它拉起的)。"""
    try:
        ps = ("Get-CimInstance Win32_Process -Filter "
              "\"Name='msedge.exe' or Name='chrome.exe'\" | "
              f"Where-Object {{$_.CommandLine -like '*{prof}*'}} | "
              "ForEach-Object { $_.ProcessId }")
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=25,
                           creationflags=SUBPROC_FLAGS)
        pids = {int(x) for x in (r.stdout or '').split() if x.isdigit()}
        if pids or not drv_pid:
            return pids
        ps2 = (f"Get-CimInstance Win32_Process -Filter "
               f"\"ParentProcessId = {drv_pid}\" | "
               "ForEach-Object { $_.ProcessId }")
        r2 = subprocess.run(['powershell', '-NoProfile', '-Command', ps2],
                            capture_output=True, text=True, timeout=25,
                            creationflags=SUBPROC_FLAGS)
        return {int(x) for x in (r2.stdout or '').split() if x.isdigit()}
    except Exception:
        return set()


'''

MW_NEW = r'''def _os_move_browser_windows(pids, log=None):
    """v5.8.9: OS 级挪窗 v2 — 目标进程的一切可见窗口搬出屏幕。
    ① 最大化窗口先还原再挪(旧版对最大化静默失效)
    ② 最小化跳过 ③ 驱动控制台(msedgedriver/chromedriver)按进程名收编
      — 只挪不关, 关控制台=杀驱动 ④ 挪动写一次诊断日志。
    只碰: PID 在集合内的窗口 + 进程名恰为驱动三件套的窗口;
    用户自己开的任何应用不会被碰。"""
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        pid_set = set(pids)
        if not pid_set:
            return 0
        if not hasattr(_os_move_browser_windows, '_seen'):
            _os_move_browser_windows._seen = set()
        moved = [0]

        def _pname(p):
            try:
                h = k32.OpenProcess(0x1000, False, p)
                if not h:
                    return ''
                buf = ctypes.create_unicode_buffer(512)
                n = wintypes.DWORD(512)
                ok = k32.QueryFullProcessImageNameW(h, 0, buf,
                                                    ctypes.byref(n))
                k32.CloseHandle(h)
                return buf.value if ok else ''
            except Exception:
                return ''

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _l):
            try:
                if not u32.IsWindowVisible(hwnd) or u32.IsIconic(hwnd):
                    return True
                pid = wintypes.DWORD()
                u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                p = pid.value
                img = _pname(p)
                base = (img.rsplit('\\', 1)[-1] or '?').lower() \
                    if img else '?'
                if p not in pid_set and base not in (
                        'msedgedriver.exe', 'chromedriver.exe',
                        'selenium-manager.exe'):
                    return True
                r = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(r))
                if r.left < 9000:
                    if u32.IsZoomed(hwnd):
                        u32.ShowWindow(hwnd, 1)      # SW_SHOWNORMAL
                    u32.SetWindowPos(hwnd, 0, 20000, 20000, 0, 0, 0x415)
                    moved[0] += 1
                    if log and (p, base) not in \
                            _os_move_browser_windows._seen:
                        tb = ctypes.create_unicode_buffer(256)
                        u32.GetWindowTextW(hwnd, tb, 256)
                        _os_move_browser_windows._seen.add((p, base))
                        log('info', f'[窗口守卫] 移出屏幕: {base} '
                                    f'"{tb.value[:40]}"')
            except Exception:
                pass
            return True

        u32.EnumWindows(_cb, 0)
        return moved[0]
    except Exception:
        return 0


'''

GD_OLD = r'''                try:
                    if not pids or tick <= 0:
                        pids = _browser_pids(prof_key)
                        tick = 40          # ≈20s 刷新一次进程表
                    tick -= 1
                    if pids:
                        _os_move_browser_windows(pids)
                except Exception:
                    pass
'''

GD_NEW = r'''                try:
                    if not pids or tick <= 0:
                        try:
                            dp = drv.service.process.pid
                        except Exception:
                            dp = None
                        pids = _browser_pids(prof_key, dp)
                        if dp:
                            pids.add(dp)   # 驱动进程(含其控制台)一并收编
                        tick = 40          # ≈20s 刷新一次进程表
                    tick -= 1
                    if pids:
                        _os_move_browser_windows(pids, log)
                except Exception:
                    pass
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'IsZoomed' in text:
        print('v5.8.9 窗口补丁已存在, 无需重复打。')
        return
    if '_os_move_browser_windows' not in text:
        die('未检测到 v5.8.7 OS 挪窗 — 请先运行 patch_v587.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.9', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.9'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.9')

    text = replace_span(text, 'def _browser_pids(prof):',
                        'def _os_move_browser_windows(pids):', BP_NEW,
                        '② _browser_pids 加子进程兜底')
    text = replace_span(text, 'def _os_move_browser_windows(pids):',
                        'def browser_auto_extract(page_url, log, '
                        'show_browser=False, chrome_port=None,', MW_NEW,
                        '③ 挪窗 v2(最大化/驱动控制台/诊断日志)')
    text = replace_once(text, GD_OLD, GD_NEW, '④ 守卫接入驱动 PID')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.9 (白框收尾)')


if __name__ == '__main__':
    main()