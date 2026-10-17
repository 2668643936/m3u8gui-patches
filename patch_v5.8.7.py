#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v587.py — m3u8gui.py → v5.8.7 (白框终极兜底: OS 级挪窗)
v5.8.4 后仍可能剩一个白框的三个通道:
  · 重开型弹窗(关一个开一个, 屏幕上永远有一个)
  · Edge 原生非网页窗口(不在 window_handles, CDP 看不见)
  · closeTarget 目标 ID 对不上 → 静默失败
本补丁:
  ① Win32 层: 每轮把"自动化浏览器进程"的一切可见窗口挪出屏幕
     (按 user-data-dir 匹配 PID, 用户自己的浏览器不受影响)
  ② 注入脚本增加 window.moveTo/resizeTo 灭活(防页面把窗口拖回屏幕)
  ③ closeTarget 双 ID 形式重试 + 失败计数(关不动就靠挪窗兜底)
用法: python patch_v587.py   (需已打 patch_v584.py)
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


OS_HELPERS = r'''def _browser_pids(prof):
    """v5.8.7: 找出自动抓取浏览器的进程 PID(按档案路径匹配命令行)"""
    try:
        ps = ("Get-CimInstance Win32_Process -Filter "
              "\"Name='msedge.exe' or Name='chrome.exe'\" | "
              f"Where-Object {{$_.CommandLine -like '*{prof}*'}} | "
              "ForEach-Object { $_.ProcessId }")
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=25,
                           creationflags=SUBPROC_FLAGS)
        return {int(x) for x in (r.stdout or '').split() if x.isdigit()}
    except Exception:
        return set()


def _os_move_browser_windows(pids):
    """v5.8.7: OS 级挪窗 — 把这些进程的所有可见窗口搬出屏幕。
    连浏览器原生窗口(崩溃恢复条/通知/关不掉的弹窗)都能挪,
    CDP 管不到的也管到。返回挪了几个。"""
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        pid_set = set(pids)
        if not pid_set:
            return 0
        moved = [0]

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _l):
            try:
                if not u32.IsWindowVisible(hwnd):
                    return True
                pid = wintypes.DWORD()
                u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value not in pid_set:
                    return True
                r = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(r))
                if r.left < 9000:
                    # NOSIZE|NOZORDER|NOACTIVATE|ASYNCWINDOWPOS
                    u32.SetWindowPos(hwnd, 0, 20000, 20000, 0, 0, 0x415)
                    moved[0] += 1
            except Exception:
                pass
            return True

        u32.EnumWindows(_cb, 0)
        return moved[0]
    except Exception:
        return 0


'''

JS_OLD = r'''    _pop_js = (
        'window.open=function(){return null;};'
        'try{document.addEventListener("click",function(e){'
        'var t=e.target;while(t&&t!==document){'
        'if(t.tagName==="A"||t.tagName==="AREA"){'
        'if((t.target||"")==="_blank"){e.preventDefault();'
        'e.stopPropagation();}break;}t=t.parentNode;}},true);}catch(e){}'
    )
'''

JS_NEW = r'''    _pop_js = (
        'window.open=function(){return null;};'
        'try{window.moveTo=function(){};window.resizeTo=function(){};}catch(e){}'
        'try{document.addEventListener("click",function(e){'
        'var t=e.target;while(t&&t!==document){'
        'if(t.tagName==="A"||t.tagName==="AREA"){'
        'if((t.target||"")==="_blank"){e.preventDefault();'
        'e.stopPropagation();}break;}t=t.parentNode;}},true);}catch(e){}'
    )
'''

GUARD_NEW = r'''    # v5.8.7: 窗口守卫 v2 — OS 级挪窗(浏览器进程的一切窗口, 含非网页窗口)
    # + CDP 关闭非基线窗口(关不动也无所谓, 挪窗兜底)
    guard_run = threading.Event()
    guard_run.set()
    _gfail = {}
    prof_key = 'm3u8_br_' if used_temp_profile else prof_name

    def _win_guard():
        win_ok = (sys.platform == 'win32')
        pids = set()
        tick = 0
        while guard_run.is_set():
            if win_ok:
                try:
                    if not pids or tick <= 0:
                        pids = _browser_pids(prof_key)
                        tick = 40          # ≈20s 刷新一次进程表
                    tick -= 1
                    if pids:
                        _os_move_browser_windows(pids)
                except Exception:
                    pass
            try:
                cur = set(drv.window_handles)
            except Exception:
                return
            for h in cur - baseline:
                if _gfail.get(h, 0) > 8:
                    continue     # 关不动 → 交给 OS 挪窗兜底
                tid = h[len('CDwindow-'):] if h.startswith('CDwindow-') else h
                ok = False
                for t_ in (tid, h):
                    try:
                        drv.execute_cdp_cmd('Target.closeTarget',
                                            {'targetId': t_})
                        ok = True
                        break
                    except Exception:
                        continue
                if not ok:
                    _gfail[h] = _gfail.get(h, 0) + 1
            time.sleep(0.5)

    if not attached:
        threading.Thread(target=_win_guard, daemon=True).start()

'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_os_move_browser_windows' in text:
        print('v5.8.7 OS 挪窗补丁已存在, 无需重复打。')
        return
    if '_win_guard' not in text:
        die('未检测到 v5.8.4 窗口守卫 — 请先运行 patch_v584.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.7', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.7'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.7')

    text = replace_once(
        text, 'def browser_auto_extract(page_url, log, show_browser=False,'
              ' chrome_port=None,', None, None) if False else text
    anchor = ('def browser_auto_extract(page_url, log, show_browser=False,'
              ' chrome_port=None,')
    if text.count(anchor) != 1:
        die('② 找不到 browser_auto_extract 锚点')
    text = text.replace(anchor, OS_HELPERS + anchor, 1)
    print('[OK] ② OS 挪窗工具函数')

    text = replace_once(text, JS_OLD, JS_NEW, '③ 注入脚本+moveTo 灭活')
    text = replace_span(text, '    # v5.8.4: 窗口守卫线程',
                        '    def sweep_popups():', GUARD_NEW,
                        '④ 窗口守卫 v2(OS 级挪窗)')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.7 (白框 OS 级兜底)')


if __name__ == '__main__':
    main()