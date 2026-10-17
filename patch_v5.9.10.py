#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5910.py — m3u8gui.py v5.9.9 → v5.9.10 (可见窗口抓取提速)

现象: 可见窗口模式, 用户点完播放仍要等 ~1.5 分钟才抓取成功。
时间线: 静默期25s + 点击链 + 可见模式观察窗90s(frame_watch 硬编码
        90, 且可见模式不做自动补点 = 纯死等)。

根因:
  ① m3u8 在点播放后几秒内即被 pump_logs 看见, 但 consider_m3u8 的
     一次性预检(_m3u8_quality, 浏览器外请求, 无Cookie/UA, 12s超时)
     失败后 URL 进 unknown_m3u8 且失败被 quality_cache 永久缓存 —
     直到所有观察窗走完的收尾阶段才复验, 收尾复验还因读缓存None
     而从不真正重试。
  ② 可见模式观察窗 90s(无头的3倍), 期间无任何动作。

修复:
  · cred_rescue: 已见未过验的 m3u8 立即带浏览器 cookie/UA 复验
    (静默期结束时一次 + 观察期每12s一次), 覆盖 None 毒缓存
  · 可见模式观察窗 90→45s
  · consider_m3u8 增加诊断日志(预检未过/直播流/短片段 → 可见)

依赖: 需已打 v5.9.7(_po.with_name); 与 598/599 锚点不冲突, 顺序不限
用法: python patch_v5910.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('cred_rescue', 'next_rescue')


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


# ---------- ③ cred_rescue: 已见未过验 → 立即带凭证复验 ----------
R1_OLD = '''    obs_dom = _domain_of(page_url)
    obs_limit = _obs_get(obs_dom)
'''
R1_NEW = '''    _rescued_tried = set()

    def cred_rescue(why):
        """v5.9.10: 已见但预检未过的 m3u8(unknown_m3u8)立即带浏览器
        cookie/UA 复验 — 旧版要等所有观察窗走完的收尾阶段才补救,
        且收尾复验读 quality_cache 的 None 从不真正重试。"""
        if pending or not unknown_m3u8:
            return
        todo = [u for u in dict.fromkeys(unknown_m3u8)
                if u not in _rescued_tried]
        if not todo:
            return
        try:
            ck = drv.execute_script('return document.cookie') or ''
            uag = drv.execute_script('return navigator.userAgent') or ''
        except Exception:
            ck = uag = ''
        hit_any = False
        for u in todo:
            _rescued_tried.add(u)
            q = _m3u8_quality(u, referer=page_url, cookie=ck, ua=uag,
                              proxy=proxy, timeout=8)
            quality_cache[u] = q      # v5.9.10: 覆盖 None 毒缓存
            if q is None or q[1] or q[0] < 60:
                continue
            pending.append(u)
            hit_any = True
            log('ok', f'带浏览器凭证复验命中({why}): {u[:70]}')
        if hit_any:
            log('ok', '已见未过验的媒体地址复验成功 → 进入择优')

    obs_dom = _domain_of(page_url)
    obs_limit = _obs_get(obs_dom)
'''

# ---------- ④ consider_m3u8 诊断日志 ----------
R2_OLD = '''        if q is None:
            unknown_m3u8.append(u)
            return
        dur, live = q[0], q[1]
        if live:
            if u not in weak_m3u8:
                weak_m3u8.append(u)
            return
        if dur < 60:
            if u not in weak_m3u8:
                weak_m3u8.append(u)
            return
        pending.append(u)
'''
R2_NEW = '''        if q is None:
            unknown_m3u8.append(u)
            log('info', f'媒体地址预检未过(稍后自动带凭证复验): {u[:70]}')
            return
        dur, live = q[0], q[1]
        if live:
            if u not in weak_m3u8:
                weak_m3u8.append(u)
                log('info', f'媒体地址是直播流(无ENDLIST) → 记为候补: '
                            f'{u[:70]}')
            return
        if dur < 60:
            if u not in weak_m3u8:
                weak_m3u8.append(u)
                log('info', f'媒体地址仅 {dur:.0f}s(短片段/广告?) → '
                            '记为候补')
            return
        pending.append(u)
'''

# ---------- ⑤ 静默期结束即复验 ----------
R3_OLD = '''        if not pending and not file_hit[0] and shield_active():
'''
R3_NEW = '''        # v5.9.10: 静默期一结束就复验 — 不再等到收尾
        cred_rescue('静默期结束')

        if not pending and not file_hit[0] and shield_active():
'''

# ---------- ⑥ 观察期轮: 复验计时器 ----------
R4_OLD = '''                    last_click = time.time()
                    next_harvest = time.time() + 5
'''
R4_NEW = '''                    last_click = time.time()
                    next_harvest = time.time() + 5
                    next_rescue = time.time() + 12   # v5.9.10: 复验计时
'''

# ---------- ⑦ 观察期轮内: 每12s复验一次 ----------
R5_OLD = '''                        if not pending and not file_hit[0]:
                            if time.time() >= next_harvest:
                                next_harvest = time.time() + 5
                                if try_dom_harvest(drv):
'''
R5_NEW = '''                        if not pending and not file_hit[0]:
                            if time.time() >= next_rescue:   # v5.9.10
                                next_rescue = time.time() + 12
                                cred_rescue('观察期复验')
                            if time.time() >= next_harvest:
                                next_harvest = time.time() + 5
                                if try_dom_harvest(drv):
'''

# ---------- ⑧ 可见模式观察窗 90 → 45 ----------
R6_OLD = '''                    frame_watch = 30 if not (show_browser or attached) else 90
'''
R6_NEW = '''                    # v5.9.10: 可见模式 90→45 — 用户在场, 久等无益;
                    # 且可见模式不做自动补点, 长窗口纯属死等
                    frame_watch = 30 if not (show_browser or attached) else 45
'''

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv5.9.10: 可见窗口抓取提速 — 已见未过验的m3u8立即带凭证复验\n'
           '        (不再等90s收尾) / 可见观察窗90→45s / 预检诊断日志\n'
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
    if '_po.with_name' not in text:
        die('未检测到 v5.9.7(_po.with_name) — 请先运行 patch_v597.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.10', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.10'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 5.9.10')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, R1_OLD, R1_NEW, '③ cred_rescue 复验函数')
    text = replace_once(text, R2_OLD, R2_NEW, '④ consider_m3u8 诊断日志')
    text = replace_once(text, R3_OLD, R3_NEW, '⑤ 静默期结束即复验')
    text = replace_once(text, R4_OLD, R4_NEW, '⑥ 观察期复验计时器')
    text = replace_once(text, R5_OLD, R5_NEW, '⑦ 观察期每12s复验')
    text = replace_once(text, R6_OLD, R6_NEW, '⑧ 可见观察窗 90→45s')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.10:')
    print('     · 已见未过验的 m3u8 → 立即带浏览器凭证复验(≤12s内)')
    print('     · 可见模式观察窗 90→45s')
    print('     · 预检未过/直播流/短片段均有日志可查')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()