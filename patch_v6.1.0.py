#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v610.py — m3u8gui.py v6.0.x → v6.1.0 (v2: 修正⑤⑥参数插入位置)

  ① 抓取记录: 解析成功 → 记录 页面→直链(link_memory.json, 数据目录)。
     下次抓同页 → 1个请求验证旧直链, 有效直接用(跳过三级解析),
     单任务/批量任务通吃。失效 → 删记录重抓; 记录后2小时内失效 →
     域名劣迹, 2次后7天不记录; 手工名单 no_record.txt 永久不记。
     失败自动重抓路径(use_memory=False)绕过记录, 防死链循环。
  ② 批量缩略图与「时间段」解耦: 只认逐项「从X到Y」。

v2 修正: 上一版把 use_memory=False 插在 smart_resolve( 调用开头,
落在位置参数之前 → SyntaxError(编译闸拦截, 未落盘)。v2 改为在
调用末尾 force_browser=True) 处拼接, 并改用与缩进无关的定位法。
依赖: v5.9.11 已打(_TIME_SEP_TRANS)。用法: python patch_v610.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_link_recall', '_no_record_domains')


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


def splice_kw(text, call_key, expect, name):
    """v2: 在 call_key 开头的 smart_resolve 调用的末尾(force_browser=True))
    处追加 use_memory=False — 与缩进/换行无关, 不会落在位置参数前面。"""
    out = []
    i, cnt = 0, 0
    END = 'force_browser=True)'
    while True:
        j = text.find(call_key, i)
        if j < 0:
            out.append(text[i:])
            break
        k = text.find(END, j)
        k2 = text.find('smart_resolve(', j + len(call_key))
        if k < 0 or (k2 != -1 and k2 < k):
            die(f'{name}: 第{cnt+1}处调用找不到结尾 force_browser=True)')
        out.append(text[i:k])
        out.append('force_browser=True, use_memory=False)')
        cnt += 1
        i = k + len(END)
    if cnt != expect:
        die(f'{name}: 拼接 {cnt} 处(应为 {expect})')
    print(f'[OK] {name} (×{cnt})')
    return ''.join(out)


LINK_BLOCK = '''# ================= v6.1 抓取记录(页→直链, 复用免解析) =================

LINK_TTL = 7 * 86400           # 记录保留上限(真过期靠复用时验证兜底)
LINK_STRIKE_AGE = 2 * 3600     # 记录后这么短时间内就失效 → 域名记劣迹
LINK_VOLATILE_TTL = 7 * 86400  # 劣迹满 → 该域名暂停记录的时长
LINK_STRIKES = 2               # 劣迹次数阈值
LINK_MAX = 500                 # 最多记录条数(超出淘汰最旧)


def _link_file():
    return _data_dir() / 'link_memory.json'


def _link_load():
    try:
        d = json.loads(_link_file().read_text(encoding='utf-8'))
        if isinstance(d, dict):
            d.setdefault('links', {})
            d.setdefault('volatile', {})
            d.setdefault('strike', {})
            return d
    except Exception:
        pass
    return {'links': {}, 'volatile': {}, 'strike': {}}


def _link_save(d):
    try:
        tmp = _link_file().with_suffix('.tmp')
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        tmp.replace(_link_file())
    except Exception:
        pass


def _link_key(page):
    u = (page or '').strip().split('#', 1)[0].rstrip('/')
    return u if u.startswith('http') else ''


def _no_record_domains():
    """手工不记录名单: 数据目录/no_record.txt, 每行一个域名, #为注释"""
    try:
        f = _data_dir() / 'no_record.txt'
        return {ln.strip().lower()
                for ln in f.read_text(encoding='utf-8').splitlines()
                if ln.strip() and not ln.strip().startswith('#')}
    except Exception:
        return set()


def _link_validate(url, referer, cookie, ua, proxy):
    """缓存直链是否仍有效 — 1 个请求"""
    try:
        k = sniff_media_url(url, referer or '', cookie or '', ua or '', proxy)
        return k in ('m3u8', 'file')
    except Exception:
        return False


def _link_recall(page, log, proxy):
    """抓取记录命中 → 验证直链仍有效 → 直接返回(跳过三级解析)。
    无效 → 删记录(短命站记劣迹), 返回 None 走原路解析。"""
    key = _link_key(page)
    if not key:
        return None
    d = _link_load()
    rec = d['links'].get(key)
    if not rec or not rec.get('url'):
        return None
    dom = _domain_of(key)
    age = time.time() - (rec.get('ts') or 0)
    if age > LINK_TTL or age < 0:
        d['links'].pop(key, None)
        _link_save(d)
        return None
    log('info', f'抓取记录: {_age_str(age)}解析过该页 → 验证旧直链...')
    if _link_validate(rec['url'], rec.get('referer') or '',
                      rec.get('cookie') or '', rec.get('ua') or '', proxy):
        log('ok', '抓取记录命中(直链仍有效) → 跳过三级解析')
        return {'url': rec['url'],
                'referer': rec.get('referer') or page,
                'cookie': rec.get('cookie') or '',
                'ua': rec.get('ua') or '',
                'title': rec.get('title') or '',
                'headers': {}, 'page': page}
    d['links'].pop(key, None)          # 失效 → 删除, 重新解析
    if age < LINK_STRIKE_AGE:          # 刚记完就死 → 短命链站点
        st = d['strike'].get(dom, 0) + 1
        d['strike'][dom] = st
        if st >= LINK_STRIKES:
            d['volatile'][dom] = time.time()
            d['strike'].pop(dom, None)
            log('info', f'{dom}: 直链寿命 <2h → 7天内不再记录该站直链')
    _link_save(d)
    log('info', '记录直链已失效, 按原路重新解析...')
    return None


def _link_store(page, got):
    """解析成功 → 记录 页→直链(明示短过期/黑名单/短命站不记)"""
    key = _link_key(page)
    if not key or not got or not str(got.get('url') or '').startswith('http'):
        return
    dom = _domain_of(key)
    if dom in _no_record_domains():
        return
    d = _link_load()
    if time.time() - d['volatile'].get(dom, 0) < LINK_VOLATILE_TTL:
        return
    try:                               # 明示1小时内过期的链接记了无意义
        v = parse_qs(urlparse(got['url']).query).get('expires')
        if v and 0 < float(v[0]) - time.time() < 3600:
            return
    except Exception:
        pass
    d['links'][key] = {'url': got['url'],
                       'referer': got.get('referer') or '',
                       'cookie': got.get('cookie') or '',
                       'ua': got.get('ua') or '',
                       'title': got.get('title') or '',
                       'ts': time.time()}
    if len(d['links']) > LINK_MAX:
        olds = sorted(d['links'].items(),
                      key=lambda kv: kv[1].get('ts') or 0)
        for k, _v in olds[:len(d['links']) - LINK_MAX]:
            d['links'].pop(k, None)
    _link_save(d)


def smart_resolve(page, log, proxy=None, show=False, port=None, browser=None,
                  strategy=None, force_browser=False, use_memory=True):
    dom = _domain_of(page)
    if use_memory:                     # v6.1: 记录命中且直链有效 → 免解析
        _hit = _link_recall(page, log, proxy)
        if _hit is not None:
            return _hit
    mem = _load_memory()
'''

SIG_OLD = '''def smart_resolve(page, log, proxy=None, show=False, port=None, browser=None,
                  strategy=None, force_browser=False):
    dom = _domain_of(page)
    mem = _load_memory()
'''

RET_OLD = '''                    except Exception as e2:
                        log('err', f'重启浏览器后仍失败: {e2!r}')
    return got
'''
RET_NEW = '''                    except Exception as e2:
                        log('err', f'重启浏览器后仍失败: {e2!r}')
    if got:                            # v6.1: 记录 页→直链 供下次免解析
        _link_store(page, got)
    return got
'''

BT_OLD = '''            '#开头为注释。只下载抽帧所需分片, 不下整片; '
            '未写从X到Y的项按主界面「时间段」。\\n'
'''
BT_NEW = '''            '#开头为注释。只下载抽帧所需分片, 不下整片; '
            '时间段只认逐项「从X到Y」, 与下载的时间段无关。\\n'
'''

BV_OLD = '''            # v5.9.11: 全局时间段(主界面) + 逐项 从X到Y 预校验
            try:
                g_ts = parse_time(self.start_var.get())
                g_te = parse_time(self.end_var.get())
            except ValueError:
                messagebox.showerror(
                    '时间格式错误',
                    '主界面「时间段」格式: 时:分:秒(点/横线/中文标点亦可)',
                    parent=win)
                return
            g_range = None if (g_ts is None and g_te is None) else (g_ts, g_te)
'''
BV_NEW = '''            # v6.1: 批量缩略图与主界面「时间段」解耦 — 只认逐项从X到Y
'''

BW_OLD = '''                    r_i = g_range                   # v5.9.11: 该项时间段
'''
BW_NEW = '''                    r_i = None    # v6.1: 批量缩略图不继承主界面时间段
'''

SET_OLD = '''        row = ttk.Frame(f); row.pack(fill='x', pady=(10, 2))
        ttk.Button(row, text='清除解析记忆(含观察期)',
                   command=clear_memory).pack(side='left')
'''
SET_NEW = '''        row = ttk.Frame(f); row.pack(fill='x', pady=(10, 2))
        ttk.Button(row, text='清除解析记忆(含观察期)',
                   command=clear_memory).pack(side='left')

        def clear_links():
            try:
                _link_file().unlink(missing_ok=True)
            except Exception:
                pass
            messagebox.showinfo('已清除', '抓取记录(页→直链)已清除', parent=win)
            self._append_log('info', '抓取记录已清除')

        def edit_norecord():
            f2 = _data_dir() / 'no_record.txt'
            if not f2.exists():
                f2.write_text('# 不写入抓取记录的站点(每行一个域名, #为注释)\\n'
                              '# 例: example.com\\n', encoding='utf-8')
            if sys.platform == 'win32':
                os.startfile(str(f2))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(f2)])
            else:
                subprocess.Popen(['xdg-open', str(f2)])

        row2 = ttk.Frame(f); row2.pack(fill='x', pady=(0, 2))
        ttk.Button(row2, text='清除抓取记录(页→直链)',
                   command=clear_links).pack(side='left')
        ttk.Button(row2, text='不记录名单(no_record.txt)',
                   command=edit_norecord).pack(side='left', padx=(8, 0))
'''

START_OLD = '''        fails, shields, obs_n = _memory_summary()
        if fails:
            self._append_log('info', f'解析记忆(7天): {" ; ".join(fails[:4])}'
                                     + (' 等' if len(fails) > 4 else ''))
'''
START_NEW = START_OLD + '''        try:
            _ln = len(_link_load().get('links') or {})
            if _ln:
                self._append_log('info', f'抓取记录: {_ln} 条 '
                                         '(同一页下次抓取免解析)')
        except Exception:
            pass
'''

DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv6.1.0: 抓取记录(页→直链复用免解析, 短命站自动识别+\n'
           '        no_record.txt名单) / 批量缩略图与时间段解耦\n'
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
    if '_TIME_SEP_TRANS' not in text:
        die('未检测到 v5.9.11(_TIME_SEP_TRANS) — 请先运行 patch_v5911.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)6\.0\.[012]',
                       r'\g<1>6.1.0', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')6\.0\.[012]'",
                       r"\g<1>6.1.0'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 6.0.x)')
    print('[OK] ① 版本号 → 6.1.0')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, SIG_OLD, LINK_BLOCK, '③ 抓取记录函数+入口钩子')
    text = replace_once(text, RET_OLD, RET_NEW, '④ 成功后写记录')
    # v2: 循环重抓×2 + 批量单项重试×1 — 全部在调用末尾拼接, 不碰位置参数
    text = splice_kw(text, 'smart_resolve(pg, lg,', 2,
                     '⑤ 循环重抓×2 绕过记录')
    text = splice_kw(text, "smart_resolve(got['page'], logL,", 1,
                     '⑥ 批量单项重试绕过记录')
    text = replace_once(text, BT_OLD, BT_NEW, '⑦ 批缩略图说明文案')
    text = replace_once(text, BV_OLD, BV_NEW, '⑧ 批缩略图 撤全局时间段')
    text = replace_once(text, BW_OLD, BW_NEW, '⑨ 批缩略图 r_i 解耦')
    text = replace_once(text, SET_OLD, SET_NEW, '⑩ 设置: 清记录+名单按钮')
    text = replace_once(text, START_OLD, START_NEW, '⑪ 启动日志记录条数')

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
    print('[OK] m3u8gui.py 已升级到 v6.1.0:')
    print('     · 抓取记录: 同一页下次抓取 1 请求验证后直接复用')
    print('     · 短命站自动识别(2h内失效×2 → 7天不记) + no_record.txt')
    print('     · 批量缩略图只认逐项「从X到Y」, 与下载时间段解耦')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()