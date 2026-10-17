#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5824.py — m3u8gui.py → v5.8.24 (死会话自愈 + 批量免记忆毒害)【修正版】
修正: P1 锚点缩进 12→16 空格(该循环嵌于 for ti, target 内)。
  ① 每轮+收尾前会话健康检查: 死会话触发 v5.8.10 重启自愈链
  ② 网络 mp4 候选: <60s 记"疑似广告丢弃"; 时长未知走体积兜底
  ③ 批量下载/重抓 force_browser=True: 浏览器级失败记忆不再跳过
用法: python patch_v5824.py   (需已打 v5.8.2 / v5.8.10)
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


P1_OLD = r'''                for rnd in range(rounds):
                    if ti == 0 and rnd == 0:
                        pass
'''
P1_NEW = r'''                for rnd in range(rounds):
                    # v5.8.24: 每轮先查会话健康 — 死会话触发重启自愈链
                    try:
                        drv.execute_script('return 1')
                    except Exception:
                        raise RuntimeError('InvalidSessionId: 会话中途死亡'
                                           '(快照为空/点击无响应)')
                    if ti == 0 and rnd == 0:
                        pass
'''

P2_OLD = r'''        cookie = ua = title = ''
        if pending or unknown_m3u8 or file_hit[0] or file_weak[0] or mp4_cands:
'''
P2_NEW = r'''        # v5.8.24: 收尾前会话健康检查(末轮之后死亡在这里兜住)
        try:
            drv.execute_script('return 1')
        except Exception:
            raise RuntimeError('InvalidSessionId: 会话在收尾阶段死亡')
        cookie = ua = title = ''
        if pending or unknown_m3u8 or file_hit[0] or file_weak[0] or mp4_cands:
'''

P3_OLD = r'''            if not media and mp4_cands:
                log('info', '验证 mp4/webm 直链候选(按时长择优)...')
                best = None
                for u, s in list(mp4_cands.items()):
                    if s not in (200, 206, None, 0):
                        continue
                    k, d = sniff_media_url(u, page_url, cookie, ua, proxy,
                                           with_duration=True)
                    if k != 'file' or not d:
                        continue
                    if best is None or d > best[0]:
                        best = (d, u)
                if best and best[0] >= 60:
                    media = best[1]
                    log('ok', f'直链择优: 最长 {best[0] / 60:.1f} 分钟 → 采用')
'''
P3_NEW = r'''            if not media and mp4_cands:
                log('info', '验证 mp4/webm 直链候选(按时长择优)...')
                best = None
                best_weak = None
                for u, s in list(mp4_cands.items()):
                    if s not in (200, 206, None, 0):
                        continue
                    k, d = sniff_media_url(u, page_url, cookie, ua, proxy,
                                           with_duration=True)
                    if k != 'file':
                        continue
                    if d:
                        if d < 60:
                            log('info', f'候选仅 {d:.0f} 秒(疑似广告) → '
                                        f'丢弃 {u[:70]}')
                            continue
                        if best is None or d > best[0]:
                            best = (d, u)
                    elif _file_ok_not_ad(u, None, page_url, cookie, ua,
                                         proxy, log):
                        if best_weak is None:      # v5.8.24: 体积兜底
                            best_weak = u
                if best:
                    media = best[1]
                    log('ok', f'直链择优: 最长 {best[0] / 60:.1f} 分钟 → 采用')
                elif best_weak:
                    media = best_weak
                    log('ok', '直链采用: 时长探测不到, 体积校验通过')
'''

P4_OLD = """def smart_resolve(page, log, proxy=None, show=False, port=None, browser=None,
                  strategy=None):
"""
P4_NEW = """def smart_resolve(page, log, proxy=None, show=False, port=None, browser=None,
                  strategy=None, force_browser=False):
"""

P5_OLD = "        if not all_fail and skipped('browser'):\n"
P5_NEW = ("        if not all_fail and skipped('browser') "
          "and not force_browser:\n")

P6_OLD = r'''                    got = smart_resolve(u, logL, proxy, show, port,
                                       browser=browser)
'''
P6_NEW = r'''                    got = smart_resolve(u, logL, proxy, show, port,
                                       browser=browser, force_browser=True)
'''

P7_OLD = r'''                    got2 = smart_resolve(got['page'], logL, proxy, show, port,
                                        browser=browser)
'''
P7_NEW = r'''                    got2 = smart_resolve(got['page'], logL, proxy, show, port,
                                        browser=browser, force_browser=True)
'''

P8_OLD = r'''                        got = smart_resolve(pg, lg,
                                            self.proxy_var.get().strip()
                                            or None, False, None,
                                            browser=self.browser_var.get())
'''
P8_NEW = r'''                        got = smart_resolve(pg, lg,
                                            self.proxy_var.get().strip()
                                            or None, False, None,
                                            browser=self.browser_var.get(),
                                            force_browser=True)
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'force_browser' in text:
        print('v5.8.24 补丁已存在, 无需重复打。')
        return
    if '_file_ok_not_ad' not in text:
        die('未检测到 v5.8.2 反广告补丁 — 请先运行 patch_v582.py')
    if '重启浏览器后仍失败' not in text:
        die('未检测到 v5.8.10 自愈补丁 — 请先运行 patch_v5810.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.24', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.24'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.24')

    text = replace_once(text, P1_OLD, P1_NEW, '② 轮次开始会话健康检查')
    text = replace_once(text, P2_OLD, P2_NEW, '③ 收尾会话健康检查')
    text = replace_once(text, P3_OLD, P3_NEW, '④ 网络候选体积兜底+丢弃日志')
    text = replace_once(text, P4_OLD, P4_NEW, '⑤ smart_resolve 增 force_browser')
    text = replace_once(text, P5_OLD, P5_NEW, '⑥ 记忆跳过让位于 force_browser')
    text = replace_once(text, P6_OLD, P6_NEW, '⑦ 批量初次解析 force')
    text = replace_once(text, P7_OLD, P7_NEW, '⑧ 批量重试解析 force')
    text = replace_once(text, P8_OLD, P8_NEW, '⑨ GUI 重抓 force')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.24 (死会话自愈+批量免毒害)')


if __name__ == '__main__':
    main()