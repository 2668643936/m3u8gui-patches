#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v620.py (V5 留档版) — m3u8gui.py v6.1.4 → v6.2.0

功能(放弃归一化, 按原网页名记录):
  ① 记录新增 fname(界面"文件名已确定"同源原名) + dur(视频秒数)字段;
     抓取成功后自动测时长入库, 旧记录字段缺失不影响使用
  ② 名字调用: 网页链接栏/批量清单接受非URL输入 → 空格分词 →
     每词生成时间等价变体(仅日期/时间样词, 固定映射) → 词变体组在
     [页面URL+fname] 中子串包含 → 全词命中:
       1条 → 自动填入走记录秒回; ≥2条 → 列URL+时长+名字不自动填;
       0条 → 提示减词重试
V4→V5 修复留档: dtxt 三行条件表达式简化为一行(并剔除残行);
  L1 末尾删除半行 def smart_resolve 死代码; 内置 L1 ast 自检;
  语法失败打印报错点前后文。
用法: python patch_v620.py
"""

import ast
import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

raw = SRC.read_bytes()
bom = raw.startswith(b'\xef\xbb\xbf')
text = raw.decode('utf-8-sig')
crlf = '\r\n' in text
if crlf:
    text = text.replace('\r\n', '\n')

MARK = '# v6.2.0: 名字调用'
if MARK in text:
    print('[i] v6.2.0 已打过。')
    sys.exit(0)
if '_BRIDGE_ENABLED' not in text:
    print('[x] 未检测到 v6.1.4(_BRIDGE_ENABLED) — 请先恢复到 v6.1.4')
    sys.exit(1)
if '_identity_core' in text:
    print('[x] 检测到旧身份核内核残留 — 请先用备份恢复到干净的 v6.1.4')
    sys.exit(1)


def rep1(old, new, name):
    global text
    n = text.count(old)
    if n != 1:
        print(f'[x] {name}: 匹配 {n} 处(应为 1) — 未改动')
        sys.exit(1)
    text = text.replace(old, new, 1)
    print(f'[OK] {name}')


# ============ 新函数块 L1 ============
NEWFUNCS = '\n'.join([
    "",
    "# ============ v6.2.0 名字调用(按原网页名记录, 无归一化) ============",
    "def _time_variants(w):",
    "    # 时间样词的等价变体(固定映射, 非时间词原样单元素)",
    "    w = w.strip()",
    "    if not w:",
    "        return [w]",
    "    m = re.fullmatch(r'(\\d{4})[-.](\\d{1,2})[-.](\\d{1,2})', w)",
    "    if m:",
    "        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))",
    "        return [w, w.replace('.', '-'), w.replace('.', '_'),",
    "                f'{d:02d}-{mo:02d}-{y}', f'{d:02d}.{mo:02d}.{y}',",
    "                f'{d:02d}_{mo:02d}_{y}', f'{y}{mo:02d}{d:02d}']",
    "    m = re.fullmatch(r'(\\d{1,2})[-.](\\d{1,2})[-.](\\d{4})', w)",
    "    if m:",
    "        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)",
    "        return [w, w.replace('.', '-'), w.replace('.', '_'),",
    "                f'{y}-{mo:02d}-{d:02d}', f'{y}.{mo:02d}.{d:02d}',",
    "                f'{y}_{mo:02d}_{d:02d}']",
    "    m = re.fullmatch(r'(\\d{2})[:._](\\d{2})', w)",
    "    if m:",
    "        hh, mi = m.group(1), m.group(2)",
    "        return [w, f'{hh}{mi}', f'{hh}-{mi}', f'{hh}_{mi}']",
    "    m = re.fullmatch(r'(\\d{2})(\\d{2})', w)",
    "    if m and 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59:",
    "        hh, mi = m.group(1), m.group(2)",
    "        return [w, f'-{w}', f'_{w}', f'{hh}:{mi}', f'{hh}.{mi}',",
    "                f'{hh}_{mi}']",
    "    return [w]",
    "",
    "",
    "def _link_find_by_words(text_in, log):",
    "    # v6.2.0: 空格分词 → 时间变体 → URL+fname 子串包含 → 全词命中",
    "    key = (text_in or '').strip()",
    "    if key.lower().endswith('.mp4'):",
    "        key = key[:-4].strip()",
    "    if not key or key.startswith('http'):",
    "        return None",
    "    words = key.split()",
    "    if not words:",
    "        return None",
    "    d = _link_load()",
    "    hits = []",
    "    for pg, rec in d['links'].items():",
    "        pool = pg + '\\n' + (rec.get('fname') or '')",
    "        ok = True",
    "        for w in words:",
    "            vs = _time_variants(w)",
    "            if not any(v in pool for v in vs):",
    "                ok = False",
    "                break",
    "        if ok:",
    "            hits.append(pg)",
    "    if not hits:",
    "        log('err', f'抓取记录中没有匹配「{key[:60]}」的条目 — '\n"
    "                   '可减少词语重试(如去掉时间只留名字+日期)')",
    "        return None",
    "    if len(hits) == 1:",
    "        return hits[0]",
    "    log('warn', f'「{key[:60]}」匹配到 {len(hits)} 条, '\n"
    "                '不自动填 — 请挑一个网址贴入:')",
    "    for h in hits[:8]:",
    "        rec = d['links'].get(h) or {}",
    "        dur = rec.get('dur')",
    "        dtxt = f'{dur // 60:.0f} 分钟' if dur else '时长未知'",
    "        fn = (rec.get('fname') or '')[:40]",
    "        log('warn', f'  [{dtxt}] {fn} | {h[:80]}')",
    "    return None",
    "",
])

# ---- 出厂自检: L1 生成文本必须独立通过 ast ----
try:
    ast.parse(NEWFUNCS)
except SyntaxError as e:
    lines = NEWFUNCS.split('\n')
    lo = max(0, (e.lineno or 1) - 4)
    hi = min(len(lines), (e.lineno or 1) + 3)
    for i in range(lo, hi):
        mk = '>>' if i + 1 == e.lineno else '  '
        print(f'{mk}{i+1:5d} | {lines[i]}')
    print(f'[x] L1 自检失败(补丁自身缺陷): {e} — 未改动, 请发回以上现场')
    sys.exit(1)


def main():
    global text

    # ---------- ① 新函数注入(抓取记录区之前) ----------
    rep1(
        '# ================= v6.1 抓取记录(页→直链, 复用免解析) =================',
        NEWFUNCS +
        '\n# ================= v6.1 抓取记录(页→直链, 复用免解析) =================',
        '① 名字调用函数注入')

    # ---------- ② _link_store: 加 fname/dur ----------
    rep1(
        "def _link_store(page, got):",
        "def _link_store(page, got, dur=None):",
        '②a _link_store 签名加 dur')
    rep1(
        "    d['links'][key] = {'url': got['url'],\n"
        "                       'referer': got.get('referer') or '',\n"
        "                       'cookie': got.get('cookie') or '',\n"
        "                       'ua': got.get('ua') or '',\n"
        "                       'title': got.get('title') or '',\n"
        "                       'ts': time.time()}",
        "    # v6.2.0: fname=界面「文件名已确定」同源(原样存, 不归一化)\n"
        "    _fn = ''\n"
        "    try:\n"
        "        _t = transform_title(got.get('title') or '', [], True)\n"
        "        _fn = safe_name(_t, url=got['url'], limit=80)\n"
        "    except Exception:\n"
        "        _fn = ''\n"
        "    d['links'][key] = {'url': got['url'],\n"
        "                       'referer': got.get('referer') or '',\n"
        "                       'cookie': got.get('cookie') or '',\n"
        "                       'ua': got.get('ua') or '',\n"
        "                       'title': got.get('title') or '',\n"
        "                       'fname': _fn,\n"
        "                       'dur': dur,\n"
        "                       'ts': time.time()}",
        '②b 记录加 fname/dur')

    # ---------- ③ smart_resolve 入口名字分流 ----------
    rep1(
        "def smart_resolve(page, log, proxy=None, show=False, port=None, "
        "browser=None,\n"
        "                  strategy=None, force_browser=False, use_memory=True):\n"
        "    dom = _domain_of(page)\n"
        "    if use_memory:                     # v6.1: 记录命中且直链有效 → 免解析\n"
        "        _hit = _link_recall(page, log, proxy)\n"
        "        if _hit is not None:\n"
        "            return _hit",
        "def smart_resolve(page, log, proxy=None, show=False, port=None, "
        "browser=None,\n"
        "                  strategy=None, force_browser=False, use_memory=True):\n"
        "    if use_memory and not page.startswith('http'):\n"
        "        # v6.2.0: 名字式输入 → 分词包含查记录\n"
        "        _hit = _link_find_by_words(page, log)\n"
        "        if _hit:\n"
        "            log('ok', f'名字命中记录 → 页面: {_hit[:80]}')\n"
        "            return _link_recall(_hit, log, proxy) or {\n"
        "                'url': '', 'referer': _hit, 'cookie': '', 'ua': '',\n"
        "                'title': '', 'headers': {}, 'page': _hit}\n"
        "        return None\n"
        "    dom = _domain_of(page)\n"
        "    if use_memory:                     # v6.1: 记录命中且直链有效 → 免解析\n"
        "        _hit = _link_recall(page, log, proxy)\n"
        "        if _hit is not None:\n"
        "            return _hit",
        '③ smart_resolve 名字分流')

    # ---------- ④ _auto_grab: 抓取后测时长 + 消息带时长 ----------
    rep1(
        "        def work():\n"
        "            got = None\n"
        "            try:\n"
        "                got = smart_resolve(page, log, proxy, show, port,\n"
        "                                    browser=browser)\n"
        "            finally:\n"
        "                self.msgq.put(('grab_done', got, page))",
        "        _grab_dur = [None]\n"
        "\n"
        "        def work():\n"
        "            got = None\n"
        "            try:\n"
        "                got = smart_resolve(page, log, proxy, show, port,\n"
        "                                    browser=browser)\n"
        "                if got and got.get('url'):\n"
        "                    try:               # v6.2.0: 抓取后测时长入库\n"
        "                        _mu = got['url']\n"
        "                        _hh = {'User-Agent': UA}\n"
        "                        if got.get('referer'):\n"
        "                            _hh['Referer'] = got['referer']\n"
        "                        if got.get('cookie'):\n"
        "                            _hh['Cookie'] = got['cookie']\n"
        "                        _hh = complete_browser_headers(_hh, _mu)\n"
        "                        _tx = http_get(_mu, _hh, timeout=15,\n"
        "                                       proxy=proxy).text\n"
        "                        while '#EXT-X-STREAM-INF' in _tx:\n"
        "                            _ls = [l.strip() for l in _tx.splitlines()]\n"
        "                            _sb = next((l for l in _ls\n"
        "                                        if l and not l.startswith('#')), '')\n"
        "                            if not _sb:\n"
        "                                break\n"
        "                            _tx = http_get(urljoin(_mu, _sb), _hh,\n"
        "                                           timeout=15, proxy=proxy).text\n"
        "                        _grab_dur[0] = _manifest_total_duration(_tx)\n"
        "                    except Exception:\n"
        "                        pass\n"
        "            finally:\n"
        "                self.msgq.put(('grab_done', got, page, _grab_dur[0]))",
        '④ _auto_grab 抓取后测时长')

    # ---------- ⑤ grab_done 接收时长并入库 ----------
    rep1(
        "        elif kind == 'grab_done':\n"
        "            got, page = msg[1], msg[2]",
        "        elif kind == 'grab_done':\n"
        "            got, page = msg[1], msg[2]\n"
        "            _gdur = msg[3] if len(msg) > 3 else None   # v6.2.0",
        '⑤a grab_done 接收时长')
    rep1(
        "            self._append_log('ok', '自动抓取成功 — 视频直链已填入, '\n"
        "                                   '正在自动测试链接...')\n"
        "            self._test_link()",
        "            try:                       # v6.2.0: 入库(含fname/dur)\n"
        "                if got and got.get('url'):\n"
        "                    _link_store(page, got, dur=_gdur)\n"
        "            except Exception:\n"
        "                pass\n"
        "            self._append_log('ok', '自动抓取成功 — 视频直链已填入, '\n"
        "                                   '正在自动测试链接...')\n"
        "            self._test_link()",
        '⑤b grab_done 调用入库')

    # ---------- ⑥ 批量抓取名字分流 ----------
    rep1(
        "                    if '.m3u8' in u.lower() or DIRECT_URL_RE.search(u):\n"
        "                        logL('ok', f'已是媒体直链(无需解析): {u[:90]}')\n"
        "                        ok_n += 1\n"
        "                        continue\n",
        "                    if '.m3u8' in u.lower() or DIRECT_URL_RE.search(u):\n"
        "                        logL('ok', f'已是媒体直链(无需解析): {u[:90]}')\n"
        "                        ok_n += 1\n"
        "                        continue\n"
        "                    if not u.startswith('http'):   # v6.2.0: 名字式输入\n"
        "                        hit = _link_find_by_words(u, logL)\n"
        "                        if not hit:\n"
        "                            fail_n += 1\n"
        "                            fails.append(u)\n"
        "                            continue\n"
        "                        logL('ok', f'名字命中记录 → 页面: {hit[:80]}')\n"
        "                        u = hit\n"
        "                        item['url'] = hit\n",
        '⑥ 批量抓取名字分流')

    # ---------- ⑦ 版本号 ----------
    text, n1 = re.subn(r'(m3u8gui\.py v)6\.1\.4', r'\g<1>6.2.0',
                       text, count=1)
    text, n2 = re.subn(r"(__version__ = ')6\.1\.4'",
                       r"\g<1>6.2.0'", text, count=1)
    if n1 != 1 or n2 != 1:
        print('[x] 版本号定位失败(应为 6.1.4) — 未改动')
        sys.exit(1)
    print('[OK] ⑦ 版本号 → 6.2.0')

    # ---------- ⑧ 文件头日志 ----------
    rep1(
        '\nv5.8.1:\n',
        '\nv6.2.0: 名字调用直链(空格分词+时间等价变体+子串包含; 多候选列\n'
        '        URL/时长/名字不自动填) / 记录加 fname+dur 字段 / 抓取后\n'
        '        自动测时长入库(放弃归一化, 按原网页名记录)\n'
        'v5.8.1:\n',
        '⑧ 文件头更新日志')

    # ---------- 语法闸(带现场) ----------
    try:
        compile(text, SRC.name, 'exec')
    except SyntaxError as e:
        print(f'[x] 语法校验失败: {e} — 未改动')
        lines = text.split('\n')
        lo = max(0, (e.lineno or 1) - 5)
        hi = min(len(lines), (e.lineno or 1) + 3)
        for i in range(lo, hi):
            mk = '>>' if i + 1 == e.lineno else '  '
            print(f'{mk}{i+1:5d} | {lines[i]}')
        print('[i] ↑ 报错点前后文(>>为报错行) — 发回定位')
        sys.exit(1)
    print('[OK] 语法校验通过')

    # ---------- 落盘 ----------
    if crlf:
        text = text.replace('\n', '\r\n')
    data = text.encode('utf-8')
    if bom:
        data = b'\xef\xbb\xbf' + data
    bak = SRC.with_name(SRC.name + '.bak')
    k = 1
    while bak.exists():
        k += 1
        bak = SRC.with_name(f'{SRC.name}.bak{k}')
    shutil.copy2(SRC, bak)
    SRC.write_bytes(data)
    print(f'[OK] 原文件已备份 → {bak.name}')
    print('[OK] m3u8gui.py 已升级到 v6.2.0 (名字调用 + 时长记录)')
    print('验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()