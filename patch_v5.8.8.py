#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v588.py — m3u8gui.py → v5.8.8 (观察期棘轮 bug 修复)
旧: 成功后 observe = 命中总耗时+6, 而总耗时含上一轮静默等待本身
    → 每次成功抬一截, 2~3 轮顶死 60s; 清记忆=手动回零。
新: 区分命中来源 — 静默期命中记真实出现时间(合理);
    靠点击/导航/终验命中记 0(观察期缩到 OBS_MIN=10s, 尽快去点击)。
用法: python patch_v588.py
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


A_OLD = "    hit_at = [None]\n"
A_NEW = ("    hit_at = [None]\n"
         "    hit_via = [None]   # v5.8.8: 'silent'=静默期命中; "
         "None=靠点击/导航/终验\n")

B_OLD = r'''            if pending and hit_at[0] is None:
                hit_at[0] = time.time() - t0
            if pending and time.time() - t0 >= 6:
                log('ok', '页面加载时即出现 m3u8 — 无需点击, 直接截获')
                break
'''
B_NEW = r'''            if pending and hit_at[0] is None:
                hit_at[0] = time.time() - t0
                hit_via[0] = 'silent'
            if pending and time.time() - t0 >= 6:
                log('ok', '页面加载时即出现 m3u8 — 无需点击, 直接截获')
                break
'''

C_OLD = r'''            if (not pending and not file_hit[0]
                    and time.time() - harvested_try_t > 4):
                harvested_try_t = time.time()
                if try_dom_harvest(drv):
                    if hit_at[0] is None:
                        hit_at[0] = time.time() - t0
                    break
'''
C_NEW = r'''            if (not pending and not file_hit[0]
                    and time.time() - harvested_try_t > 4):
                harvested_try_t = time.time()
                if try_dom_harvest(drv):
                    if hit_at[0] is None:
                        hit_at[0] = time.time() - t0
                    hit_via[0] = 'silent'
                    break
'''

D_OLD = r'''        if media:
            if hit_at[0] is None:
                hit_at[0] = max(45, obs_limit)
            _obs_record_ok(obs_dom, hit_at[0])
        else:
            _obs_record_fail(obs_dom)
'''
D_NEW = r'''        if media:
            if hit_at[0] is None:
                hit_at[0] = max(45, obs_limit)
            if hit_via[0] == 'silent':
                # 静默期自己出现 → 记真实出现时间, 等待确有回报
                _obs_record_ok(obs_dom, hit_at[0])
            else:
                # v5.8.8: 靠点击/iframe导航/终验才命中 → 静默等待是白等。
                # 旧版把"总耗时"记成观察期, 每次抬一截直到顶死 60s。
                _obs_record_ok(obs_dom, 0)
        else:
            _obs_record_fail(obs_dom)
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'hit_via' in text:
        print('v5.8.8 观察期补丁已存在, 无需重复打。')
        return
    for feat in ('hit_at = [None]', '_obs_record_ok(obs_dom'):
        if feat not in text:
            die(f'文件缺少特征: {feat!r}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.8', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.8'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.8')

    text = replace_once(text, A_OLD, A_NEW, '② hit_via 声明')
    text = replace_once(text, B_OLD, B_NEW, '③ 静默期 m3u8 命中标记')
    text = replace_once(text, C_OLD, C_NEW, '④ 静默期 DOM 命中标记')
    text = replace_once(text, D_OLD, D_NEW, '⑤ finally 按来源记录')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.8 (观察期棘轮修复)')


if __name__ == '__main__':
    main()