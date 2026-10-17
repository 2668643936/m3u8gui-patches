#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v595.py — m3u8gui.py → v5.9.5 (限速爬行可见化)【锚点修正版】
  ① _dl_seg 429 分支: 每20秒报一次"全局冷却中(非卡死)"
  ② 预取池心跳: 每12秒报"分片预取 N/88 · CDN限速爬行中"
用法: python patch_v595.py
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


A1_OLD = "        _pf_q = queue.Queue()\n"
A1_NEW = """        _pf_q = queue.Queue()
        _t429 = [0.0]                   # v5.9.5: 429 日志节流
        _pf_beat = [time.time()]        # v5.9.5: 预取心跳
"""

A2_OLD = r'''                if r.status_code == 429:
                    # v5.8.13: 限速 — 尊重 Retry-After, 全局冷却后再试
                    last_err = 'HTTP 429(限速)'
                    _throttle_register(r)
                    try:
                        r.close()
                    except Exception:
                        pass
                    continue
                if r.status_code in (410, 403):
                    # v5.8.14: 链接过期/失效 — 立即放弃该分片
'''
A2_NEW = r'''                if r.status_code == 429:
                    # v5.8.13: 限速 — 尊重 Retry-After, 全局冷却后再试
                    last_err = 'HTTP 429(限速)'
                    _throttle_register(r)
                    if time.time() - _t429[0] > 20:      # v5.9.5: 可见性
                        _t429[0] = time.time()
                        log('info', f'分片 #{j} 429 → 全局冷却中'
                                   '(下载线程集体暂停, 非卡死)')
                    try:
                        r.close()
                    except Exception:
                        pass
                    continue
                if r.status_code in (410, 403):
                    # v5.8.14: 链接过期/失效 — 立即放弃该分片
'''

A3_OLD = r'''                    ev = _pf_ev.get(j)
                    if ev:
                        ev.set()
'''
A3_NEW = r'''                    ev = _pf_ev.get(j)
                    if ev:
                        ev.set()
                    if time.time() - _pf_beat[0] > 12:   # v5.9.5: 心跳
                        _pf_beat[0] = time.time()
                        q.put(('prog2', f'分片预取 {len(cache)}'
                               f'/{len(_pf_queued)} · CDN限速爬行中(非卡死)',
                               None))
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_pf_beat' in text:
        print('v5.9.5 补丁已存在, 无需重复打。')
        return
    if 'def _dl_seg' not in text:
        die('未检测到 v5.8.6 预取池 — 请先运行 patch_v586.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.5', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.5'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件在 5.8/5.9 系列')
    print('[OK] ① 版本号 → 5.9.5')

    text = replace_once(text, A1_OLD, A1_NEW, '② 心跳/节流变量')
    text = replace_once(text, A2_OLD, A2_NEW, '③ 429 冷却报行踪')
    text = replace_once(text, A3_OLD, A3_NEW, '④ 预取池心跳')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.5 (限速爬行可见化)')


if __name__ == '__main__':
    main()