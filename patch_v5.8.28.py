#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5828.py — m3u8gui.py → v5.8.28 (直链抽帧抗性: 重试+退避+失败可见)
现象: 直链缩略图遇并行抓取(同CDN抢流量) → 源站按IP拦截 →
     逐帧请求全灭, 且零日志(120帧只出1帧, 从拼图才发现)。
修复:
  ① 每帧失败重试一次(3s退避)
  ② 连续8帧失败: 重启本地代理+20s长退避; 每20帧报进度;
     连续40帧判定拦截 → 提前中止
  ③ 过半帧失败时明确警告(不再无声出残图)
  ④ 修代理日志参数顺序(裸"info"行的来源)
用法: python patch_v5828.py
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


A1_OLD = r'''        cells = []
        for i, t in enumerate(plan['ts']):
'''
A1_NEW = r'''        cells = []
        consec = 0                       # v5.8.28: 直链连续失败计数
        for i, t in enumerate(plan['ts']):
'''

A2_OLD = r'''            else:
                ok = try_frame(url, t, out)
'''
A2_NEW = r'''            else:
                ok = try_frame(url, t, out)
                if not ok:              # v5.8.28: 直链帧失败重试一次
                    if not stop.is_set():
                        time.sleep(3)
                        ok = try_frame(url, t, out)
'''

A3_OLD = r'''            if ok:
                cells.append((out, t))
            if (i + 1) % 5 == 0 or i + 1 == plan['n']:
                q.put(('prog2', f'帧 {i + 1}/{plan["n"]}',
                       (i + 1) * 100.0 / plan['n']))
'''
A3_NEW = r'''            if ok:
                cells.append((out, t))
                consec = 0
            elif not is_m3u8:
                consec += 1              # v5.8.28: 连续失败退避+诊断
                if consec == 8:
                    log('连续 8 帧失败 — 重启本地代理并退避 20s '
                        '(疑似源站限流/拦截, 并行抓取会加剧)', 'warn')
                    try:
                        _proxy_stop()
                        np_ = _proxy_for(url, headers)
                        if np_:
                            purl = np_
                    except Exception:
                        pass
                    time.sleep(20)
                elif consec and consec % 20 == 0:
                    log(f'已连续失败 {consec} 帧(进度 {i + 1}/{plan["n"]})',
                        'warn')
                    time.sleep(10)
                if consec >= 40:
                    log('连续 40 帧失败 — 判定源站拦截, 提前中止。'
                        '并行抓取/下载会加剧此情况, 建议稍后单独重跑', 'err')
                    break
            if (i + 1) % 5 == 0 or i + 1 == plan['n']:
                q.put(('prog2', f'帧 {i + 1}/{plan["n"]}',
                       (i + 1) * 100.0 / plan['n']))
'''

A4_OLD = r'''        if not cells:
            log('一帧都没抽出来(加密/防盗链/时长异常?)', 'err')
            shutil.rmtree(tdir, ignore_errors=True)
            return False
'''
A4_NEW = r'''        if not cells:
            log('一帧都没抽出来(加密/防盗链/时长异常?)', 'err')
            shutil.rmtree(tdir, ignore_errors=True)
            return False
        if len(cells) * 2 < plan['n']:   # v5.8.28: 过半失败要喊出来
            log(f'注意: {plan["n"]} 帧中仅 {len(cells)} 帧成功 — 源站疑似'
                '限流/拦截(并行抓取或下载会加剧), 建议稍后单独重跑本视频',
                'warn')
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'consec' in text:
        print('v5.8.28 直链抗性补丁已存在, 无需重复打。')
        return

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.28', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.28'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.28')

    text = replace_once(text, A1_OLD, A1_NEW, '② 连续失败计数器')
    text = replace_once(text, A2_OLD, A2_NEW, '③ 帧失败重试')
    text = replace_once(text, A3_OLD, A3_NEW, '④ 退避+代理重启+提前中止')
    text = replace_once(text, A4_OLD, A4_NEW, '⑤ 过半失败警告')

    # ⑥ 修裸"info"日志行(参数顺序装反) — 尽力而为, 不阻塞主修复
    bad = "log('info', f'直链经本地代理抽帧: {purl}')"
    if bad in text:
        text = text.replace(
            bad, "log(f'直链经本地代理抽帧: {purl}', 'info')", 1)
        print('[OK] ⑥ 修正代理日志参数顺序(裸info行)')
    else:
        print('[i] ⑥ 代理日志行无需修正(跳过)')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.28 (直链抽帧抗性)')


if __name__ == '__main__':
    main()