#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v586.py — m3u8gui.py → v5.8.6 (缩略图分片: 断点续传 + 并行预取)
背景: 这类 CDN 限速是"先突发~1.7MB 后停滞", 旧 get_seg 60s 整体超时
且不续传 → 超时=已收字节全作废; 且串行下载。
  ① _dl_seg: 流式 + 超时30s + Range续传 + 6轮重试
  ② 6 线程预取池(按抽帧计划整队并行)
  ③ _cache_store 每8次才全量清点
用法: python patch_v586.py
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


def replace_span(text, start, end, body, name):
    if text.count(start) != 1:
        die(f'{name}: 起始锚点未找到/不唯一: {start!r}')
    i = text.find(start)
    j = text.find(end, i)
    if j < 0:
        die(f'{name}: 结束锚点未找到: {end!r}')
    print(f'[OK] {name}')
    return text[:i] + body + text[j:]


def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        die(f'{name}: 锚点匹配 {n} 处(应为 1 处)')
    print(f'[OK] {name}')
    return text.replace(old, new, 1)


SEG_NEW = r'''        cache = {}
        _pf_lock = threading.Lock()
        _pf_ev = {}
        _pf_fail = set()
        _pf_done = set()
        _pf_queued = set()
        _pf_q = queue.Queue()

        def _dl_seg(j, s):
            """v5.8.6: 流式 + 超时30s + Range断点续传 + 6轮重试。
            突发后停滞的限速下, 每次新建连接可再领一段突发, 续传拼齐。"""
            part_p = tmpdir / f'.pf_{j:05d}.part'
            received = part_p.stat().st_size if part_p.exists() else 0
            last_err = None
            for attempt in range(6):
                if stop.is_set():
                    return None
                hd = dict(headers)
                if received:
                    hd['Range'] = f'bytes={received}-'
                try:
                    r = http_get(s['url'], hd, timeout=30, proxy=proxy,
                                 stream=True)
                except Exception as e:
                    last_err = str(e)
                    time.sleep(min(1 + attempt, 4))
                    continue
                if r.status_code == 416:
                    try:
                        r.close()
                    except Exception:
                        pass
                    part_p.unlink(missing_ok=True)
                    received = 0
                    continue
                if r.status_code >= 400:
                    last_err = f'HTTP {r.status_code}'
                    try:
                        r.close()
                    except Exception:
                        pass
                    time.sleep(min(1 + attempt, 4))
                    continue
                if received and r.status_code != 206:
                    try:
                        r.close()
                    except Exception:
                        pass
                    part_p.unlink(missing_ok=True)
                    received = 0
                    continue
                total = None
                try:
                    cr = r.headers.get('Content-Range') or ''
                    if cr and '/' in cr:
                        total = int(cr.split('/')[-1])
                    else:
                        cl = r.headers.get('Content-Length') or ''
                        total = (received + int(cl)) if cl.isdigit() else None
                except Exception:
                    total = None
                ended = True
                try:
                    with open(part_p, 'ab') as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                            received += len(chunk)
                except Exception as e:
                    last_err = str(e)
                    ended = False       # 超时/断连 → 已收字节保留续传
                finally:
                    try:
                        r.close()
                    except Exception:
                        pass
                if ended and (total is None or received >= total):
                    data = part_p.read_bytes()
                    part_p.unlink(missing_ok=True)
                    return data
                time.sleep(min(1 + attempt, 4))
            try:
                part_p.unlink(missing_ok=True)
            except Exception:
                pass
            log(f'分片下载失败 #{j}(6次续传重试后放弃): {last_err}', 'warn')
            return None

        def _fetch_one(j):
            """下载/解密/落盘单个分片, 成功写入 cache[j]"""
            s = segs[j]
            data = _cache_load(s['url'])
            if data is None:
                data = _dl_seg(j, s)
            if data is None:
                return False
            ki = s.get('key')
            if ki and ki['uri'] in keymap:
                try:
                    data = decrypt_segment(data, keymap[ki['uri']],
                                           ki.get('iv'), s['seq'])
                except Exception:
                    return False
                _cache_store(s['url'], data)
            elif not ki:
                _cache_store(s['url'], data)
            p = tmpdir / (f'seg_{j:05d}.mp4' if init_bytes
                          else f'seg_{j:05d}.ts')
            p.write_bytes((init_bytes + data) if init_bytes else data)
            cache[j] = p
            return True

        def _pf_worker():
            while not stop.is_set():
                try:
                    j = _pf_q.get_nowait()
                except queue.Empty:
                    return
                try:
                    _fetch_one(j)
                except Exception:
                    pass
                with _pf_lock:
                    if j not in cache:
                        _pf_fail.add(j)
                    _pf_done.add(j)
                    ev = _pf_ev.get(j)
                    if ev:
                        ev.set()

        def get_seg(j):
            if j in cache:
                return cache[j]
            if j < 0 or j >= len(segs):
                return None
            ev = None
            with _pf_lock:
                if j in _pf_fail:
                    return None
                if j in _pf_done:
                    return cache.get(j)
                if j in _pf_queued:
                    ev = _pf_ev.setdefault(j, threading.Event())
            if ev is not None:
                deadline = time.time() + 3600
                while not ev.is_set() and not stop.is_set() \
                        and time.time() < deadline:
                    ev.wait(timeout=2.0)
                return cache.get(j) if ev.is_set() else None
            return cache.get(j) if _fetch_one(j) else None

        # v5.8.6: 预取池 — 整份抽帧计划的分片排队, 6 线程并行拉取
        if is_m3u8 and cum:
            for t in plan['ts']:
                jj = max(0, min(bisect.bisect_right(cum, t) - 1,
                                len(segs) - 1))
                if jj not in _pf_queued:
                    _pf_queued.add(jj)
                    _pf_q.put(jj)
            if _pf_queued:
                log(f'分片预取: {len(_pf_queued)} 个分片排队, '
                    '6 线程并行(断点续传)', 'info')
                for _ in range(min(6, len(_pf_queued))):
                    threading.Thread(target=_pf_worker,
                                     daemon=True).start()

'''

STORE_OLD = r'''def _cache_store(url, data):
    try:
        p = _cache_path(url)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp')
        tmp.write_bytes(data)
        tmp.replace(p)
        _cache_trim()
    except Exception:
        pass
'''

STORE_NEW = r'''def _cache_store(url, data):
    try:
        p = _cache_path(url)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp')
        tmp.write_bytes(data)
        tmp.replace(p)
        if not hasattr(_cache_store, '_n'):
            _cache_store._n = 0
        _cache_store._n += 1
        if _cache_store._n % 8 == 1:     # v5.8.6: 每8次才全量清点(省IO)
            _cache_trim()
    except Exception:
        pass
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_pf_worker' in text:
        print('v5.8.6 分片续传补丁已存在, 无需重复打。')
        return
    if '_cache_store' not in text:
        die('未检测到 v5.8.3 分片缓存 — 请先运行 patch_v583.py')
    if 'def http_get(url, headers, timeout=20, proxy=None, stream=False):' \
            not in text:
        die('未检测到 v5.8.3.1 的 http_get stream 参数 — 先运行 patch_v5831.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.6', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.6'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.6')

    text = replace_span(text, '        cache = {}',
                        '        purl = None', SEG_NEW,
                        '② get_seg 重写: 续传+重试+6线程预取池')
    text = replace_once(text, STORE_OLD, STORE_NEW,
                        '③ _cache_store 清点节流')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.6 (分片断点续传+并行预取)')


if __name__ == '__main__':
    main()