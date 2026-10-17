#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5814.py — m3u8gui.py → v5.8.14 (死链快速判死 + 429 惊群修复)
  ① 410/403 分片: 立即判死不重试(下载+缩略图两路径)
  ② 全作业累计 12 个过期分片 → 整体中止并提示重抓
    (续传按分片文件名, 不依赖旧URL, 已下载的分片不丢)
  ③ 429 冷却惊群: 错峰苏醒(随机0~1.5s) + 冷却期内再撞限自动加倍
用法: python patch_v5814.py
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


TW_OLD = r'''def _throttle_wait(stop=None):
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
'''

TW_NEW = r'''def _throttle_wait(stop=None):
    """请求前调用: 冷却未过就等(可被 stop 打断); 等过则错峰苏醒"""
    try:
        waited = False
        while True:
            with _THROT_LOCK:
                left = _THROT['until'] - time.time()
            if left <= 0:
                break
            waited = True
            if stop is not None and stop.is_set():
                return
            time.sleep(min(left, 2.0))
        if waited:
            time.sleep(random.uniform(0.0, 1.5))   # v5.8.14: 错峰防惊群
    except Exception:
        pass
'''

TR_OLD = r'''def _throttle_register(resp=None, base=8.0):
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

TR_NEW = r'''def _throttle_register(resp=None, base=8.0):
    """收到 429 → 登记全局冷却(尊重 Retry-After; 冷却期内再撞限自动加倍)"""
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
            now = time.time()
            if _THROT['until'] > now:
                mult = min(_THROT.get('mult', 1.0) * 2.0, 8.0)  # 冷却不够长
            else:
                mult = 1.0
            _THROT['mult'] = mult
            _THROT['until'] = max(_THROT['until'],
                                  now + min(delay * mult, 90.0))
    except Exception:
        pass
'''

THUMB_OLD = r'''                if r.status_code >= 400:
                    last_err = f'HTTP {r.status_code}'
'''

THUMB_NEW = r'''                if r.status_code in (410, 403):
                    # v5.8.14: 链接过期/失效 — 立即放弃该分片
                    try:
                        r.close()
                    except Exception:
                        pass
                    log(f'分片 #{j} 链接过期(HTTP {r.status_code}), 放弃', 'warn')
                    return None
                if r.status_code >= 400:
                    last_err = f'HTTP {r.status_code}'
'''

JOB_OLD = r'''                if r.status_code == 416:
                    tmp.unlink(missing_ok=True)
                    continue
                r.raise_for_status()
'''

JOB_NEW = r'''                if r.status_code in (410, 403):
                    # v5.8.14: 链接过期/失效 — 重试无意义, 立即判死
                    try:
                        r.close()
                    except Exception:
                        pass
                    return f'HTTP {r.status_code}(链接疑似过期)', 0
                if r.status_code == 416:
                    tmp.unlink(missing_ok=True)
                    continue
                r.raise_for_status()
'''

ALL_OLD = r'''    def _download_all(self, todo, workdir, keymap):
        task_q = queue.Queue()
        for seg in todo:
            task_q.put(seg)
        total = len(todo)

        def worker():
            s = self._mk_session()
            while not self.stop.is_set():
                try:
                    seg = task_q.get_nowait()
                except queue.Empty:
                    return
                err, size = self._download_one(s, seg, workdir, keymap)
                with self._lock:
                    if err:
                        self._failed += 1
                        self._log(f'分片失败 {seg["file"]}: {err}', 'err')
                    else:
                        self._done += 1
'''

ALL_NEW = r'''    def _download_all(self, todo, workdir, keymap):
        task_q = queue.Queue()
        for seg in todo:
            task_q.put(seg)
        total = len(todo)
        dead = [0]                      # v5.8.14: 过期类失败计数

        def worker():
            s = self._mk_session()
            while not self.stop.is_set():
                if dead[0] >= 12:       # v5.8.14: 链接已死, 不再拉新分片
                    return
                try:
                    seg = task_q.get_nowait()
                except queue.Empty:
                    return
                err, size = self._download_one(s, seg, workdir, keymap)
                with self._lock:
                    if err:
                        self._failed += 1
                        self._log(f'分片失败 {seg["file"]}: {err}', 'err')
                        if '过期' in err:      # v5.8.14: 410/403 计数
                            dead[0] += 1
                    else:
                        self._done += 1
'''

JOIN_OLD = r'''        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(max(1, self.cfg['workers']))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
'''

JOIN_NEW = r'''        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(max(1, self.cfg['workers']))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if dead[0] >= 12:
            raise JobError('多个分片返回 410/403 — 链接已过期。\n'
                           '→ 用「网页链接」重新「自动抓取」获取新链接, 再点'
                           '「开始 / 续传」: 已下载的分片会自动跳过续传, 不浪费。')
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '链接疑似过期' in text:
        print('v5.8.14 死链补丁已存在, 无需重复打。')
        return
    if '_throttle_register' not in text:
        die('未检测到 v5.8.13 限速补丁 — 请先运行 patch_v5813.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.14', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.14'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.14')

    text = replace_once(text, 'import queue\nimport re',
                        'import queue\nimport random\nimport re',
                        '② import random')
    text = replace_once(text, TW_OLD, TW_NEW, '③ 冷却错峰苏醒')
    text = replace_once(text, TR_OLD, TR_NEW, '④ 冷却自动加倍')
    text = replace_once(text, THUMB_OLD, THUMB_NEW,
                        '⑤ 缩略图路径 410/403 立即放弃')
    text = replace_once(text, JOB_OLD, JOB_NEW,
                        '⑥ 下载路径 410/403 立即判死')
    text = replace_once(text, ALL_OLD, ALL_NEW, '⑦ 过期计数与停拉')
    text = replace_once(text, JOIN_OLD, JOIN_NEW, '⑧ 整体中止+重抓指引')

    finish(text, 'm3u8gui.py 已升级到 v5.8.14 (死链判死+惊群修复)')


if __name__ == '__main__':
    main()