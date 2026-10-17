#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5825.py — m3u8gui.py → v5.8.25 (批量缩略图: 预解析流水线)
旧: 批量循环 串行(解析i→抽帧i→解析i+1→…), 抽帧时浏览器闲置。
新: 处理第 i 项时后台预解析第 i+1 项 — 解析与抽帧并行,
    总时长 ≈ N × max(解析, 抽帧) 而非 N × (解析+抽帧)。
顺带: 批量缩略图解析吃到 force_browser(v5.8.24 当时漏了此处)。
用法: python patch_v5825.py   (需已打 v5.8.24)
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


A1_OLD = r'''            def work():
                stop = self._thumb_stop
                self.thumb_job = threading.current_thread()
                ok_n = fail_n = 0
                fails = []
                for i, (label, u) in enumerate(items, 1):
'''

A1_NEW = r'''            def work():
                stop = self._thumb_stop
                self.thumb_job = threading.current_thread()
                ok_n = fail_n = 0
                fails = []

                # v5.8.25: 解析流水线 — 下一项的解析与当前项抽帧并行
                pf = {}
                pf_started = set()
                pf_lock = threading.Lock()

                def _pf_resolve(idx, plabel, pu):
                    try:
                        got = smart_resolve(pu, logL, proxy, show, port,
                                            browser=browser,
                                            force_browser=True)
                        if got and plabel:
                            got['title'] = plabel
                    except Exception as e:
                        logL('err', f'预解析异常: {e!r}')
                        got = None
                    with pf_lock:
                        pf[idx] = got

                def _pf_kick(idx, plabel, pu):
                    if idx < 1 or idx > len(items) or idx in pf_started:
                        return
                    pf_started.add(idx)
                    if ('.m3u8' in pu.lower()
                            or DIRECT_URL_RE.search(pu)):
                        with pf_lock:
                            pf[idx] = {'url': pu, 'referer': '',
                                       'cookie': '', 'ua': '',
                                       'title': plabel or '',
                                       'headers': {}, 'page': ''}
                    else:
                        threading.Thread(target=_pf_resolve,
                                         args=(idx, plabel, pu),
                                         daemon=True).start()

                def _pf_wait(idx):
                    while True:
                        with pf_lock:
                            if idx in pf:
                                return pf[idx]
                        if stop.is_set():
                            return None
                        time.sleep(0.5)

                for i, (label, u) in enumerate(items, 1):
'''

A2_OLD = r'''                        p = Path(u)
                        if p.exists() and p.is_file():
                            ok = make_thumbnails_for(p, tc, logM, self.msgq,
                                                     stop)
'''
A2_NEW = r'''                        p = Path(u)
                        if p.exists() and p.is_file():
                            if i < len(items):
                                _pf_kick(i + 1, items[i][0], items[i][1])
                            ok = make_thumbnails_for(p, tc, logM, self.msgq,
                                                     stop)
'''

A3_OLD = r'''                        else:
                            if ('.m3u8' in u.lower()
                                    or DIRECT_URL_RE.search(u)):
                                got = {'url': u, 'referer': '', 'cookie': '',
                                       'ua': '', 'title': label or '',
                                       'headers': {}, 'page': ''}
                            else:
                                got = smart_resolve(u, logL, proxy, show, port,
                                                    browser=browser)
                                if got and label:
                                    got['title'] = label
                            if not got:
                                logM('解析失败, 跳过该项', 'err')
                                fail_n += 1
                                fails.append(u)
                                continue
'''
A3_NEW = r'''                        else:
                            # v5.8.25: 等预解析结果, kick 下一项(并行抽帧)
                            _pf_kick(i, label, u)
                            got = _pf_wait(i)
                            if i < len(items):
                                _pf_kick(i + 1, items[i][0], items[i][1])
                            if not got:
                                logM('解析失败, 跳过该项', 'err')
                                fail_n += 1
                                fails.append(u)
                                continue
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_pf_kick' in text:
        print('v5.8.25 流水线补丁已存在, 无需重复打。')
        return
    if 'force_browser' not in text:
        die('未检测到 v5.8.24 — 请先运行 patch_v5824.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.25', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.25'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.25')

    text = replace_once(text, A1_OLD, A1_NEW, '② 流水线机制(预解析)')
    text = replace_once(text, A2_OLD, A2_NEW, '③ 本地文件项也预解析下一项')
    text = replace_once(text, A3_OLD, A3_NEW, '④ 解析改走预取+接力kick')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.25 (批量缩略图流水线)')


if __name__ == '__main__':
    main()