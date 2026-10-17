#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v592.py — m3u8gui.py → v5.9.2 (直链分辨率升级)
现象: 播放器默认只加载默认清晰度, 高清链接要点画质菜单才出现 —
     无头抓到的永远是默认那条; 且"按时长择优"对同视频不同清晰度
     无法区分(时长相同, 平票=先捕获者胜=默认画质)。
修复:
  ① URL 带 -NNNp.mp4 标记时, 生成高分辨率候选并 Range 验证,
     命中即升级(按设置「分辨率」偏好; 最高=2160→…→480 阶梯降试)
  ② 同时长候选平票: 分辨率高者胜
用法: python patch_v592.py   (需已打 v5.8.24)
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


HELPERS = r'''def _res_of_url(u):
    """v5.9.2: 从直链 URL 提取分辨率标记 -NNNp (无则 0)"""
    m = re.search(r'-(\d{3,4})p\.(?:mp4|webm|flv)(?=[/?#]|$)', u, re.I)
    return int(m.group(1)) if m else 0


def _res_ladder_up(url, referer, cookie, ua, proxy, log):
    """v5.9.2: 直链分辨率升级 — 播放器默认只加载默认清晰度, 高清
    链接要点了画质菜单才出现。URL 带 -NNNp 模式时直接生成高分辨率
    候选并验证, 免去模拟点击。按「分辨率」设置; 最高=阶梯降试。"""
    cur = _res_of_url(url)
    if not cur:
        return None
    target = _res_target()              # 0 = 最高
    if target and cur >= target:
        return None                     # 已达标, 不降级
    ladder = [t for t in (2160, 1440, 1080, 720, 480, 360)
              if t > cur and (not target or t <= target)]
    for t in ladder:
        repl = '\\g<1>' + str(t) + '\\g<2>'
        cand = re.sub(r'(-)\d{3,4}(p\.(?:mp4|webm|flv))', repl,
                      url, count=1, flags=re.I)
        if cand == url:
            continue
        if sniff_media_url(cand, referer, cookie, ua, proxy) == 'file':
            log('info', f'分辨率升级: {cur}p → {t}p 命中')
            return cand
    return None


'''

TIE_OLD = r'''                        if best is None or d > best[0]:
                            best = (d, u)
'''
TIE_NEW = r'''                        if best is None or d > best[0] or (
                                d == best[0] and
                                _res_of_url(u) > _res_of_url(best[1])):
                            best = (d, u)
'''

UP_OLD = r'''                if best:
                    media = best[1]
                    log('ok', f'直链择优: 最长 {best[0] / 60:.1f} 分钟 → 采用')
                elif best_weak:
                    media = best_weak
                    log('ok', '直链采用: 时长探测不到, 体积校验通过')
'''
UP_NEW = r'''                if best:
                    media = best[1]
                    log('ok', f'直链择优: 最长 {best[0] / 60:.1f} 分钟 → 采用')
                elif best_weak:
                    media = best_weak
                    log('ok', '直链采用: 时长探测不到, 体积校验通过')
                if media:                          # v5.9.2: 分辨率升级
                    up = _res_ladder_up(media, page_url, cookie, ua,
                                        proxy, log)
                    if up:
                        media = up
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_res_ladder_up' in text:
        print('v5.9.2 补丁已存在, 无需重复打。')
        return
    if 'best_weak' not in text:
        die('未检测到 v5.8.24 的网络候选体积兜底 — 请先运行 patch_v5824.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.2', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.2'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件在 5.8/5.9 系列')
    print('[OK] ① 版本号 → 5.9.2')

    anchor = ('def browser_auto_extract(page_url, log, show_browser=False,'
              ' chrome_port=None,')
    if text.count(anchor) != 1:
        die('② browser_auto_extract 锚点不唯一')
    text = text.replace(anchor, HELPERS + anchor, 1)
    print('[OK] ② 分辨率提取/升级函数')

    text = replace_once(text, TIE_OLD, TIE_NEW, '③ 平票判决: 分辨率高者胜')
    text = replace_once(text, UP_OLD, UP_NEW, '④ 选中后执行分辨率升级')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.2 (直链分辨率升级)')


if __name__ == '__main__':
    main()