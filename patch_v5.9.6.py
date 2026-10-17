#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v596.py — m3u8gui.py v5.9.5 → v5.9.6 (缩略图专抓 ~480p, 整合版)

功能(原 596+597+598 三补丁合并, 一个版本号到位):
  · THUMB_RES_P=480 + _res_thumb_pick(插在 browser_auto_extract 前)
  · online_thumbs: m3u8 变体按 480p 择优(显式参数, 不动全局偏好);
    直链 -NNNp 多级就低 480→360→240, 探测结果会话内缓存(换不到也记住)
  · parse_playlist: master 无 ≤偏好 变体时回退最小可用档(不再报错)
  · Job 下载路径不受影响(唯一差异: 偏好档无匹配原本报错 → 改为回退)

实现说明: 原计划 v5.9.6 用"临时覆盖 App._res_pref + finally 恢复"。
但批量缩略图运行中允许并行「自动抓取」(v5.8.23), 全局覆盖会把并行
抓取的变体择优也压到 480p; 故改为给 parse_playlist/_res_target 加
可选参数 res_pref 显式传 480p, 影响严格限定在 online_thumbs 内。

用法:  python patch_v596.py   (与 m3u8gui.py 同目录, 或传路径参数)
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_res_thumb_pick', '_res_try_cache', 'lo_rh', 'res_pref=None')


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


# ---------- ③ _res_target 显式偏好参数 ----------
TGT_OLD = '''def _res_target():
    v = getattr(App, '_res_pref', '最高') if 'App' in globals() else '最高'
    if not v or v == '最高':
        return 0
'''
TGT_NEW = '''def _res_target(pref=None):    # v5.9.6: pref非None→显式偏好(缩略图就低, 不动全局)
    v = pref if pref is not None else (
        getattr(App, '_res_pref', '最高') if 'App' in globals() else '最高')
    if not v or v == '最高':
        return 0
'''

# ---------- ④ parse_playlist 签名 ----------
SIG_OLD = 'def parse_playlist(text, base_url, log=None):'
SIG_NEW = ('def parse_playlist(text, base_url, log=None, '
           'res_pref=None):    # v5.9.6: res_pref → 按该偏好挑变体(缩略图就低)')

# ---------- ⑤ 变体择优: 记录最小可用档 + target(res_pref) ----------
A1_OLD = '''        best_bw, best_url, best_res = -1, None, ''
        target = _res_target()
'''
A1_NEW = '''        best_bw, best_url, best_res = -1, None, ''
        lo_rh, lo_u, lo_res = None, None, ''   # v5.9.6: 记录最小可用变体
        target = _res_target(res_pref)         # v5.9.6: 缩略图路径显式传480p
'''

# ---------- ⑥ master 无匹配变体 → 回退最小可用档 ----------
A2_OLD = '''                fit = (rh == 0) or (target == 0) or (rh <= target)
                if fit and bw > best_bw:
                    best_bw, best_url = bw, urljoin(base_url, lines[i + 1])
                    best_res = a.get('RESOLUTION', '')
        if not best_url:
            raise JobError('master 播放列表中没有可用的子列表')
'''
A2_NEW = '''                fit = (rh == 0) or (target == 0) or (rh <= target)
                if rh and (lo_rh is None or rh < lo_rh):
                    lo_rh, lo_u = rh, urljoin(base_url, lines[i + 1])
                    lo_res = a.get('RESOLUTION', '')
                if fit and bw > best_bw:
                    best_bw, best_url = bw, urljoin(base_url, lines[i + 1])
                    best_res = a.get('RESOLUTION', '')
        if not best_url and lo_u:      # v5.9.6: 无≤偏好档 → 回退最小可用档
            best_bw, best_url, best_res = 0, lo_u, lo_res
            if log:
                log(f'偏好≤{target}p无匹配变体 → 回退最小可用档 {lo_res}',
                    'warn')
        if not best_url:
            raise JobError('master 播放列表中没有可用的子列表')
'''

# ---------- ⑦ THUMB_RES_P + _res_thumb_pick(多级就低 + 会话缓存) ----------
BLOCK = r'''THUMB_RES_P = 480   # v5.9.6: 缩略图专用分辨率(拼图格高480px, 更高无增益)
_res_try_cache = {}   # v5.9.6: 会话内缓存 {原URL: 换到的低档URL / None(换不到)}


def _res_thumb_pick(url, referer, cookie, ua, proxy, log):
    """v5.9.6: 缩略图专用就低 — -NNNp 直链若存在更低档(480→360→240
    逐级试)则换用, 下载量约降到 1/3(拼图格高固定 480px, 高码率无
    视觉增益)。探测结果写入 _res_try_cache: 换到的记住档位, 换不到
    的记住 None, 同一会话内不重复发探测请求(仅 in-memory, 不写磁盘)。"""
    cur = _res_of_url(url)
    if not cur or cur <= THUMB_RES_P:
        return None
    if url in _res_try_cache:              # v5.9.6: 已探测过 → 直接用结论
        return _res_try_cache[url]
    for t in (THUMB_RES_P, 360, 240):      # v5.9.6: 多级就低
        if t >= cur:
            continue
        repl = '\\g<1>' + str(t) + '\\g<2>'
        cand = re.sub(r'(-)\d{3,4}(p\.(?:mp4|webm|flv))', repl,
                      url, count=1, flags=re.I)
        if cand == url:
            continue
        if sniff_media_url(cand, referer, cookie, ua, proxy) == 'file':
            log('info', f'缩略图就低: {cur}p → {t}p(省流量 ~{cur // t}x)')
            _res_try_cache[url] = cand
            return cand
    _res_try_cache[url] = None             # v5.9.6: 记住"换不到", 不再重复
    return None


'''

# ---------- ⑧ online_thumbs: m3u8 变体按 480p 择优 ----------
PL_OLD = '''                r = http_get(url, headers, timeout=20, proxy=proxy)
                pl = parse_playlist(r.text, r.url, log)
                while pl.get('master'):
                    r = http_get(pl['variant_url'], headers, timeout=20,
                                 proxy=proxy)
                    pl = parse_playlist(r.text, r.url, log)
'''
PL_NEW = '''                r = http_get(url, headers, timeout=20, proxy=proxy)
                pl = parse_playlist(r.text, r.url, log,
                                    res_pref=f'{THUMB_RES_P}p')
                while pl.get('master'):
                    r = http_get(pl['variant_url'], headers, timeout=20,
                                 proxy=proxy)
                    pl = parse_playlist(r.text, r.url, log,
                                        res_pref=f'{THUMB_RES_P}p')
'''

# ---------- ⑨ online_thumbs: 直链就低换档 ----------
INS_OLD = '''            log('地址既不是 m3u8 也不是视频文件', 'err')
            return False

    tmpdir = Path(tempfile.mkdtemp(prefix='m3u8_thumbs_'))
'''
INS_NEW = '''            log('地址既不是 m3u8 也不是视频文件', 'err')
            return False

    # v5.9.6: 缩略图专抓 ~480p — 直链换低档; m3u8 变体在下方
    # parse_playlist(..., res_pref=f'{THUMB_RES_P}p') 处就低
    if not is_m3u8:
        _lo = _res_thumb_pick(url, headers.get('Referer') or '',
                              headers.get('Cookie') or '',
                              headers.get('User-Agent') or '',
                              proxy, log)
        if _lo:
            url = _lo

    tmpdir = Path(tempfile.mkdtemp(prefix='m3u8_thumbs_'))
'''
INS_OLD_ALT = INS_OLD.replace('m3u8_thumbs_', 'm8_thumbs_')
INS_NEW_ALT = INS_NEW.replace('m3u8_thumbs_', 'm8_thumbs_')

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv5.9.6: 缩略图专抓低档 — 直链480p→360/240多级就低+会话内缓存 /\n'
           '        m3u8变体按480p择优, 无≤偏好档回退最小可用变体\n'
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
    if '_res_of_url' not in text:
        die('未检测到 v5.9.2 的 _res_of_url — 本补丁只适用于 5.9.2+ 基线')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.6', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.6'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 5.9.6')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, TGT_OLD, TGT_NEW, '③ _res_target 显式偏好参数')
    text = replace_once(text, SIG_OLD, SIG_NEW, '④ parse_playlist 签名')
    text = replace_once(text, A1_OLD, A1_NEW, '⑤ 变体记录 + target(res_pref)')
    text = replace_once(text, A2_OLD, A2_NEW, '⑥ master 无匹配回退最小档')
    text = replace_once(
        text,
        'def browser_auto_extract(page_url, log, show_browser=False,'
        ' chrome_port=None,',
        BLOCK + 'def browser_auto_extract(page_url, log, show_browser=False,'
        ' chrome_port=None,',
        '⑦ THUMB_RES_P + _res_thumb_pick')
    text = replace_once(text, PL_OLD, PL_NEW, '⑧ online_thumbs m3u8 变体就低')
    if text.count(INS_OLD) == 1:
        text = replace_once(text, INS_OLD, INS_NEW, '⑨ online_thumbs 直链就低')
    elif text.count(INS_OLD_ALT) == 1:
        text = replace_once(text, INS_OLD_ALT, INS_NEW_ALT,
                            '⑨ online_thumbs 直链就低(m8_thumbs_ 变体锚点)')
    else:
        die('⑨ online_thumbs 入口锚点匹配 0 处 — 请把完整输出发回定位')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.6:')
    print('     · 缩略图: 直链 480→360/240 多级就低 + 会话内缓存')
    print('     · 缩略图: m3u8 变体按 480p 择优(无低档→回退最小可用档)')
    print('     · Job 下载路径不受影响')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()