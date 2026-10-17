#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5813.py — m3u8gui.py → v5.8.13 (HTTP 429 限速感知)
旧逻辑: 429 走普通错误分支, 睡1~4s不看 Retry-After → 6次全撞限速窗口 → 丢帧。
修复(缩略图预取 + 完整下载两条路径):
  ① 模块级全局冷却: 任一请求 429 → 按 Retry-After(无则≥8s, 上限60s)登记,
     所有下载线程请求前先等冷却
  ② 429 保留 Range 续传进度
  ③ 冷却等待可被"停止"打断
用法: python patch_v5813.py
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


def finish(text, name):
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
    print(f'[OK] {name}')


THROT = r'''# ---------- v5.8.13: 429 全局冷却 ----------
_THROT = {'until': 0.0}
_THROT_LOCK = threading.Lock()


def _throttle_wait(stop=None):
    """请求前调用: 冷却未过就等(可被 stop 打断)"""
    try:
        while True:
            with _THROT_LOCK:
                left = _THROT['until'] - time.time()
            if left <= 0:
                return
            if stop is not None and stop.is_set():
                return
            time.sleep(min(left, 2.0))
    except Exception:
        pass


def _throttle_register(resp=None, base=8.0):
    """收到 429 → 登记全局冷却(尊重 Retry-After, 上限 60s)"""
    try:
        ra = 0.0
        if resp is not None:
            v = (resp.headers.get('Retry-After') or '').strip()
            try:
                ra = float(v)
            except (TypeError, ValueError):
                ra = 0.0
        delay = max(base, min(ra, 60.0))
        with _THROT_LOCK:
            _THROT['until'] = max(_THROT['until'], time.time() + delay)
    except Exception:
        pass


'''

DL_WAIT_OLD = r'''            for attempt in range(6):
                if stop.is_set():
                    return None
                hd = dict(headers)
'''
DL_WAIT_NEW = r'''            for attempt in range(6):
                if stop.is_set():
                    return None
                _throttle_wait(stop)     # v5.8.13: 429 全局冷却
                hd = dict(headers)
'''

DL_429_OLD = r'''                if r.status_code >= 400:
                    last_err = f'HTTP {r.status_code}'
                    try:
                        r.close()
                    except Exception:
                        pass
                    time.sleep(min(1 + attempt, 4))
                    continue
'''
DL_429_NEW = r'''                if r.status_code == 429:
                    # v5.8.13: 限速 — 尊重 Retry-After, 全局冷却后再试
                    last_err = 'HTTP 429(限速)'
                    _throttle_register(r)
                    try:
                        r.close()
                    except Exception:
                        pass
                    continue
                if r.status_code >= 400:
                    last_err = f'HTTP {r.status_code}'
                    try:
                        r.close()
                    except Exception:
                        pass
                    time.sleep(min(1 + attempt, 4))
                    continue
'''

JOB_OLD = r'''            offset = tmp.stat().st_size if tmp.exists() else 0
            headers = {'Range': 'bytes=%d-' % offset} if offset else {}
            try:
                r = session.get(seg['url'], headers=headers, stream=True,
                                timeout=SEG_TIMEOUT)
                if r.status_code == 416:
                    tmp.unlink(missing_ok=True)
                    continue
                r.raise_for_status()
'''
JOB_NEW = r'''            offset = tmp.stat().st_size if tmp.exists() else 0
            headers = {'Range': 'bytes=%d-' % offset} if offset else {}
            _throttle_wait(self.stop)     # v5.8.13: 429 全局冷却
            try:
                r = session.get(seg['url'], headers=headers, stream=True,
                                timeout=SEG_TIMEOUT)
                if r.status_code == 429:
                    # v5.8.13: 限速 — 尊重 Retry-After, 全局冷却后再试
                    last_err = 'HTTP 429(限速)'
                    _throttle_register(r)
                    try:
                        r.close()
                    except Exception:
                        pass
                    continue
                if r.status_code == 416:
                    tmp.unlink(missing_ok=True)
                    continue
                r.raise_for_status()
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_throttle_register' in text:
        print('v5.8.13 限速补丁已存在, 无需重复打。')
        return
    if 'for attempt in range(6):' not in text:
        die('未检测到 v5.8.6 分片续传 — 请先运行 patch_v586.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.13', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.13'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.13')

    anchor = ('def browser_auto_extract(page_url, log, show_browser=False,'
              ' chrome_port=None,')
    if text.count(anchor) != 1:
        die('② 找不到 browser_auto_extract 锚点')
    text = text.replace(anchor, THROT + anchor, 1)
    print('[OK] ② 全局冷却模块')

    text = replace_once(text, DL_WAIT_OLD, DL_WAIT_NEW,
                        '③ 预取请求前等冷却')
    text = replace_once(text, DL_429_OLD, DL_429_NEW,
                        '④ 预取 429 分支(尊重 Retry-After)')
    text = replace_once(text, JOB_OLD, JOB_NEW,
                        '⑤ 完整下载 429 分支+冷却')

    finish(text, 'm3u8gui.py 已升级到 v5.8.13 (429 限速感知)')


if __name__ == '__main__':
    main()