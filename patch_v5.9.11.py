#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5911.py — m3u8gui.py v5.9.10 → v5.9.11

  ① 设置窗口重构: 折叠分区(点标题收起) + 滚动区(滚轮可用) + 「保存并
     关闭」固定底栏永远可见; 接管启动说明挪到自动抓取区右侧竖栏;
     「只留拼图」「铺满整行」合并一行; 窗口加高(840x720)。
     v5.9.9 的「设置不冲文件名」语义原样保留。
  ② 时间段分隔符自由: 时:分:秒 / 时.分.秒 / 时-分-秒 / 中文标点
     (：。，、) / 全角数字 均可; 末段两位=分:秒, 一位=小数秒。
     下载/批量下载/批量逐项「从X到Y」自动全部受益。
  ③ 缩略图支持时间段: 单张共用主界面「时间段」栏; 批量缩略图逐项
     「标题 | 网址 | 从X到Y」, 未写项按主界面时间段; 只抓范围内的
     分片(m3u8 预取也随之省流量)。

依赖: 需已打 v5.9.7(_po.with_name) 与 v5.9.9(_same_old)
用法: python patch_v5911.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_TIME_SEP_TRANS', 't_range=None')


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


def replace_span(text, start_m, end_m, new_block, name):
    i = text.find(start_m)
    if i < 0:
        die(f'{name}: 起始锚点未找到')
    j = text.find(end_m, i + len(start_m))
    if j < 0:
        die(f'{name}: 结束锚点未找到')
    print(f'[OK] {name}')
    return text[:i] + new_block + text[j:]


# ---------- ③ parse_time 分隔符自由 ----------
PT_OLD = '''def parse_time(s):
    s = (s or '').strip()
    if not s:
        return None
    t = 0.0
    for p in s.split(':'):
        t = t * 60 + float(p)
    return t
'''
PT_NEW = '''_TIME_SEP_TRANS = str.maketrans('：，。、–—０１２３４５６７８９',
                                ':,.,--0123456789')


def parse_time(s):
    """v5.9.11: 时分秒分隔符自由 — 冒号/点/句号/横线/逗号(中英文)均可,
    全角数字亦可。例: 1:05:10 / 1-05-10 / 1.05.10 / 1。05。10 / 1，05，10
    → 1小时5分10秒。单个点/逗号: 末段两位=分:秒(1.05=65s, 10.30=630s);
    末段一位/三位=小数秒(90.5=90.5秒)。纯数字=秒。"""
    s = (s or '').strip()
    if not s:
        return None
    s = s.translate(_TIME_SEP_TRANS)
    if ':' in s or '-' in s:
        parts = s.replace('-', ':').split(':')
    elif re.search(r'[.,].*[.,]', s):
        parts = re.split(r'[.,]', s)       # ≥2 个点/逗号 → 时.分.秒
    else:
        m = re.match(r'^(\\d+)(?:[.,](\\d+))?$', s)
        if not m:
            raise ValueError(f'无法识别的时间: {s!r}')
        if m.group(2) and len(m.group(2)) == 2:
            return int(m.group(1)) * 60 + int(m.group(2))    # 分.秒
        return float(s)                                      # 秒(可小数)
    t = 0.0
    for p in parts:
        t = t * 60 + float(p)
    return t
'''

# ---------- ④ 主界面时间段提示文案 ----------
HINT_OLD = '''        ttk.Label(row, text='(秒 / 分:秒 / 时:分:秒, 留空一头 = 开头/结尾)',
                  foreground='#888888').pack(side='left', padx=10)
'''
HINT_NEW = '''        ttk.Label(row, text='(时:分:秒 / 时.分.秒 / 时-分-秒, 中英文标点'
                            '均可; 留空一头 = 开头/结尾)',
                  foreground='#888888').pack(side='left', padx=10)
'''

# ---------- ⑤ make_thumbnails_for 签名 ----------
MS_OLD = 'def make_thumbnails_for(video, tc, log, q, stop_event):'
MS_NEW = ('def make_thumbnails_for(video, tc, log, q, stop_event, '
          't_range=None):    # v5.9.11: 缩略图时间段')

# ---------- ⑥ make_thumbnails_for 时间段+span ----------
MB_OLD = '''    mode = tc.get('mode', 'grid')
    param = tc.get('param') or ('4x3' if mode == 'grid' else
                                '12' if mode == 'count' else '60')
    cols = int(tc.get('cols') or 5)
    try:
        if mode == 'grid':
            plan = compute_plan('grid', dur, grid=param)
        elif mode == 'count':
            plan = compute_plan('count', dur, count=int(float(param)), cols=cols)
        else:
            plan = compute_plan('interval', dur, step=parse_every(param), cols=cols)
    except (ValueError, ZeroDivisionError):
        log(f'缩略图参数无法识别({mode}:{param}), 用默认 4x3 网格', 'warn')
        plan = compute_plan('grid', dur, grid='4x3')
    for note in plan['notes']:
        log('⚠ ' + note, 'info')
'''
MB_NEW = '''    t0 = 0.0
    if t_range:                        # v5.9.11: 缩略图时间段
        _a, _b = t_range
        t0 = max(0.0, float(_a or 0.0))
        t1 = float(_b) if _b is not None else dur
        if t0 >= dur:
            log(f'时间段起点 {fmt_t(t0)} 超出视频长度({fmt_t(dur)})', 'err')
            return False
        t1 = min(t1, dur)
        if t1 - t0 < 1.0:
            log('时间段过短(<1秒)', 'err')
            return False
    span = (t1 - t0) if t_range else dur
    mode = tc.get('mode', 'grid')
    param = tc.get('param') or ('4x3' if mode == 'grid' else
                                '12' if mode == 'count' else '60')
    cols = int(tc.get('cols') or 5)
    try:
        if mode == 'grid':
            plan = compute_plan('grid', span, grid=param)
        elif mode == 'count':
            plan = compute_plan('count', span, count=int(float(param)), cols=cols)
        else:
            plan = compute_plan('interval', span, step=parse_every(param),
                                cols=cols)
    except (ValueError, ZeroDivisionError):
        log(f'缩略图参数无法识别({mode}:{param}), 用默认 4x3 网格', 'warn')
        plan = compute_plan('grid', span, grid='4x3')
    if t_range:                        # v5.9.11: 时间戳平移到绝对时间
        plan['ts'] = [t + t0 for t in plan['ts']]
        log(f'缩略图时间段: {fmt_t(t0)} ~ {fmt_t(t1)}')
    for note in plan['notes']:
        log('⚠ ' + note, 'info')
'''

# ---------- ⑦ online_thumbs 签名 ----------
OS_OLD = '''def online_thumbs(got, label, outdir, tc, log, q, stop, proxy=None,
                  fw=None, fixdate=True):
'''
OS_NEW = '''def online_thumbs(got, label, outdir, tc, log, q, stop, proxy=None,
                  fw=None, fixdate=True, t_range=None):
'''

# ---------- ⑧ online_thumbs 时间段+span ----------
OB_OLD = '''        mode = tc.get('mode', 'grid')
        param = tc.get('param') or ('4x3' if mode == 'grid' else
                                    '12' if mode == 'count' else '60')
        cols = int(tc.get('cols') or 5)
        try:
            if mode == 'grid':
                plan = compute_plan('grid', dur, grid=param)
            elif mode == 'count':
                plan = compute_plan('count', dur, count=int(float(param)),
                                    cols=cols)
            else:
                plan = compute_plan('interval', dur, step=parse_every(param),
                                    cols=cols)
        except (ValueError, ZeroDivisionError):
            log(f'缩略图参数无法识别({mode}:{param}), 用 4x3 网格', 'warn')
            plan = compute_plan('grid', dur, grid='4x3')
        for note in plan['notes']:
            log('⚠ ' + note, 'info')
'''
OB_NEW = '''        t0 = 0.0
        if t_range:                    # v5.9.11: 缩略图时间段
            _a, _b = t_range
            t0 = max(0.0, float(_a or 0.0))
            t1 = float(_b) if _b is not None else dur
            if t0 >= dur:
                log(f'时间段起点 {fmt_t(t0)} 超出视频长度({fmt_t(dur)})', 'err')
                return False
            t1 = min(t1, dur)
            if t1 - t0 < 1.0:
                log('时间段过短(<1秒)', 'err')
                return False
        span = (t1 - t0) if t_range else dur
        mode = tc.get('mode', 'grid')
        param = tc.get('param') or ('4x3' if mode == 'grid' else
                                    '12' if mode == 'count' else '60')
        cols = int(tc.get('cols') or 5)
        try:
            if mode == 'grid':
                plan = compute_plan('grid', span, grid=param)
            elif mode == 'count':
                plan = compute_plan('count', span, count=int(float(param)),
                                    cols=cols)
            else:
                plan = compute_plan('interval', span, step=parse_every(param),
                                    cols=cols)
        except (ValueError, ZeroDivisionError):
            log(f'缩略图参数无法识别({mode}:{param}), 用 4x3 网格', 'warn')
            plan = compute_plan('grid', span, grid='4x3')
        if t_range:                    # v5.9.11: 时间戳平移到绝对时间
            plan['ts'] = [t + t0 for t in plan['ts']]
            log(f'缩略图时间段: {fmt_t(t0)} ~ {fmt_t(t1)}')
        for note in plan['notes']:
            log('⚠ ' + note, 'info')
'''

# ---------- ⑨ _one_thumb 时间段解析 ----------
O1_OLD = '''        fw = parse_filter_words(self.filter_var.get())
        fixdate = self.fixdate_var.get()
        outdir = Path(self.out_var.get().strip() or 'video.mp4').resolve().parent
'''
O1_NEW = '''        fw = parse_filter_words(self.filter_var.get())
        fixdate = self.fixdate_var.get()
        # v5.9.11: 缩略图时间段(与下载共用主界面「时间段」栏)
        try:
            _ts = parse_time(self.start_var.get())
            _te = parse_time(self.end_var.get())
        except ValueError:
            messagebox.showerror(
                '时间格式错误', '时间段格式: 时:分:秒(点/横线/中文标点亦可)')
            return
        t_range = None if (_ts is None and _te is None) else (_ts, _te)
        outdir = Path(self.out_var.get().strip() or 'video.mp4').resolve().parent
'''

# ---------- ⑩ _one_thumb 日志+传参 ----------
O2_OLD = '''        self._append_log('info', f'缩略图: {tgt[:70]} [{tc["mode"]}:{tc["param"]}] '
                                 f'→ {outdir}')
        self.status_lbl.config(text='生成缩略图...')
'''
O2_NEW = '''        self._append_log('info', f'缩略图: {tgt[:70]} [{tc["mode"]}:{tc["param"]}] '
                                 f'→ {outdir}')
        if t_range:
            self._append_log('info', '缩略图时间段: '
                             + fmt_t(t_range[0] or 0) + ' ~ '
                             + (fmt_t(t_range[1]) if t_range[1] else '结尾'))
        self.status_lbl.config(text='生成缩略图...')
'''
O3_OLD = '''                ok = online_thumbs(got, name_hint, outdir, tc, logM,
                                   self.msgq, stop, proxy, fw=fw,
                                   fixdate=fixdate)
'''
O3_NEW = '''                ok = online_thumbs(got, name_hint, outdir, tc, logM,
                                   self.msgq, stop, proxy, fw=fw,
                                   fixdate=fixdate, t_range=t_range)
'''

# ---------- ⑪ 批量缩略图说明文案 ----------
BT_OLD = '''            '每行一个网址(播放页/m3u8/直链), 可写「标题 | 网址」; #开头为注释。\\n'
            '只下载抽帧所需分片, 不下整片。\\n'
'''
BT_NEW = '''            '每行一个网址(播放页/m3u8/直链), '
            '可写「标题 | 网址 | 从10.00到25.00」。\\n'
            '#开头为注释。只下载抽帧所需分片, 不下整片; '
            '未写从X到Y的项按主界面「时间段」。\\n'
'''

# ---------- ⑫ 批量缩略图解析器(3元组) ----------
BP_OLD = '''            items = []
            for ln in txt.get('1.0', 'end').splitlines():
                ln = ln.strip()
                if not ln or ln.startswith('#'):
                    continue
                label, u = None, ln
                if '|' in ln:
                    left, _, right = ln.partition('|')
                    left, right = left.strip(), right.strip()
                    if right.startswith('http'):
                        label, u = (left or None), right
                items.append((label, u))
'''
BP_NEW = '''            items = []
            for ln in txt.get('1.0', 'end').splitlines():
                ln = ln.strip()
                if not ln or ln.startswith('#'):
                    continue
                # v5.9.11: 支持「标题 | 网址 | 从X到Y」(无http→整行按本地路径)
                parts = [p.strip() for p in ln.split('|')]
                u = next((p for p in parts if p.startswith('http')), '') or ln
                rng = None
                label = None
                for p in parts:
                    if not p or p.startswith('http'):
                        continue
                    m = re.match(r'^从(.+?)到(.*)$', p)
                    if m:
                        rng = (m.group(1), m.group(2))
                    elif label is None:
                        label = p
                items.append((label, u, rng))
'''

# ---------- ⑬ 批量缩略图 go() 时间段校验 ----------
BV_OLD = '''            tc, proxy, show, port, browser = r
            fw = parse_filter_words(self.filter_var.get())
            fixdate = self.fixdate_var.get()
            outdir = outdir_var.get().strip() or '.'
'''
BV_NEW = '''            tc, proxy, show, port, browser = r
            fw = parse_filter_words(self.filter_var.get())
            fixdate = self.fixdate_var.get()
            outdir = outdir_var.get().strip() or '.'
            # v5.9.11: 全局时间段(主界面) + 逐项 从X到Y 预校验
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
            for _it in items:
                if not _it[2]:
                    continue
                try:
                    parse_time(_it[2][0])
                    parse_time(_it[2][1])
                except ValueError:
                    messagebox.showerror(
                        '时间格式错误',
                        f'时间段格式错误: 从{_it[2][0]}到{_it[2][1]}\\n'
                        '格式: 时:分:秒(点/横线/中文标点亦可)', parent=win)
                    return
'''

# ---------- ⑭ 批量缩略图 work 循环传参 ----------
BW_OLD = '''                for i, (label, u) in enumerate(items, 1):
                    if stop.is_set():
                        break
                    self.msgq.put(('prog2', f'[{i}/{len(items)}] '
                                            f'{label or u[:60]}', None))
                    logM(f'—— [{i}/{len(items)}] {label or u[:80]} ——')
                    try:
                        p = Path(u)
                        if p.exists() and p.is_file():
                            if i < len(items):
                                _pf_kick(i + 1, items[i][0], items[i][1])
                            ok = make_thumbnails_for(p, tc, logM, self.msgq,
                                                     stop)
                        else:
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
                            ok = online_thumbs(got, label or '', outdir, tc,
                                               logM, self.msgq, stop, proxy,
                                               fw=fw, fixdate=fixdate)
'''
BW_NEW = '''                for i, (label, u, rng) in enumerate(items, 1):
                    if stop.is_set():
                        break
                    self.msgq.put(('prog2', f'[{i}/{len(items)}] '
                                            f'{label or u[:60]}', None))
                    logM(f'—— [{i}/{len(items)}] {label or u[:80]} ——')
                    r_i = g_range                   # v5.9.11: 该项时间段
                    if rng:
                        try:
                            _a = parse_time(rng[0]) if rng[0] else None
                            _b = parse_time(rng[1]) if rng[1] else None
                        except ValueError:
                            logM('时间段格式错误, 该项按整段处理', 'err')
                            r_i = None
                        else:
                            r_i = None if (_a is None and _b is None) \\
                                else (_a, _b)
                    try:
                        p = Path(u)
                        if p.exists() and p.is_file():
                            if i < len(items):
                                _pf_kick(i + 1, items[i][0], items[i][1])
                            ok = make_thumbnails_for(p, tc, logM, self.msgq,
                                                     stop, t_range=r_i)
                        else:
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
                            ok = online_thumbs(got, label or '', outdir, tc,
                                               logM, self.msgq, stop, proxy,
                                               fw=fw, fixdate=fixdate,
                                               t_range=r_i)
'''

# ---------- ⑮ 设置窗口整体重构(整方法替换) ----------
NEW_SETTINGS = r'''    def _open_settings(self):
        win = tk.Toplevel(self)
        win.title('设置')
        win.geometry('840x720')
        win.minsize(780, 640)
        win.transient(self)

        # v5.9.11: 底栏先 pack(side='bottom') → 「保存并关闭」永远可见,
        # 不随内容滚动; 其余全部装进上方滚动区(折叠分区)。
        bar = ttk.Frame(win, padding=(12, 8))
        bar.pack(fill='x', side='bottom')

        mid = ttk.Frame(win)
        mid.pack(fill='both', expand=True)
        canvas = tk.Canvas(mid, highlightthickness=0)
        vsb = ttk.Scrollbar(mid, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        f = ttk.Frame(canvas, padding=(12, 6))
        _iid = canvas.create_window((0, 0), window=f, anchor='nw')
        f.bind('<Configure>',
               lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda _e: canvas.itemconfigure(_iid, width=_e.width))

        def _on_wheel(_e):
            step = -1 * int(_e.delta / 120) or (-1 if _e.delta > 0 else 1)
            canvas.yview_scroll(step, 'units')
        win.bind('<MouseWheel>', _on_wheel)

        def fold(title, opened=True):
            """v5.9.11: 折叠分区 — 点标题收起/展开"""
            box = ttk.Frame(f)
            box.pack(fill='x', pady=(5, 1))
            st = {'open': opened}
            hdr = tk.Label(box, text=('▾ ' if opened else '▸ ') + title,
                           cursor='hand2', anchor='w',
                           font=('微软雅黑', 9, 'bold'))
            hdr.pack(fill='x')
            body = ttk.Frame(box, padding=(2, 1))
            if opened:
                body.pack(fill='x')

            def _tg(_e=None):
                st['open'] = not st['open']
                hdr.config(text=('▾ ' if st['open'] else '▸ ') + title)
                if st['open']:
                    body.pack(fill='x')
                else:
                    body.pack_forget()
            hdr.bind('<Button-1>', _tg)
            return body

        # ================= 自动抓取 =================
        gf = fold('自动抓取')
        cols = ttk.Frame(gf)
        cols.pack(fill='x')
        lc = ttk.Frame(cols)
        lc.pack(side='left', fill='both', expand=True)
        rc = ttk.Frame(cols)
        rc.pack(side='left', padx=(14, 2), anchor='n')
        row = ttk.Frame(lc); row.pack(fill='x', pady=2)
        ttk.Label(row, text='浏览器:', width=10).pack(side='left')
        ttk.Radiobutton(row, text='Chrome(默认)',
                        variable=self.browser_var,
                        value='chrome').pack(side='left', padx=(4, 0))
        ttk.Radiobutton(row, text='Edge', variable=self.browser_var,
                        value='edge').pack(side='left', padx=(6, 0))
        row = ttk.Frame(lc); row.pack(fill='x', pady=2)
        ttk.Label(row, text='默认模式:', width=10).pack(side='left')
        ttk.Radiobutton(row, text='无头(绝不弹窗)',
                        variable=self.grabmode_var,
                        value='headless').pack(side='left', padx=(4, 0))
        ttk.Radiobutton(row, text='可见窗口', variable=self.grabmode_var,
                        value='visible').pack(side='left', padx=(6, 0))
        ttk.Radiobutton(row, text='接管模式', variable=self.grabmode_var,
                        value='attach').pack(side='left', padx=(6, 0))
        row = ttk.Frame(lc); row.pack(fill='x', pady=2)
        ttk.Label(row, text='抓取策略:', width=10).pack(side='left')
        ttk.Radiobutton(row, text='智能(默认)', variable=self.sniff_var,
                        value='smart').pack(side='left', padx=(4, 0))
        ttk.Radiobutton(row, text='纯被动嗅探(不点击)',
                        variable=self.sniff_var,
                        value='passive').pack(side='left', padx=(6, 0))
        row = ttk.Frame(lc); row.pack(fill='x', pady=2)
        ttk.Label(row, text='接管端口:', width=10).pack(side='left')
        ttk.Spinbox(row, from_=1024, to=65535, textvariable=self.grabport_var,
                    width=7).pack(side='left', padx=(4, 0))
        # v5.9.11: 接管启动说明挪到右侧 — 左栏紧凑, 右侧空白利用起来
        ttk.Label(rc, justify='left', foreground='#888888', wraplength=300,
                  text='接管启动 (先关闭所有Chrome, Win+R):\n'
                       '"C:\\Program Files\\Google\\Chrome\\Application\\'
                       'chrome.exe" --remote-debugging-port=9222\n'
                       '在该窗口过一次年龄验证 → 回来点「自动抓取」'
                   ).pack(anchor='nw')

        # ================= 下载 =================
        df = fold('下载')
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='并发数:', width=10).pack(side='left')
        ttk.Spinbox(row, from_=1, to=32, textvariable=self.workers_var,
                    width=5).pack(side='left', padx=(4, 16))
        ttk.Checkbutton(row, text='完成后保留分片',
                        variable=self.keep_var).pack(side='left')
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='默认目录:', width=10).pack(side='left')
        ttk.Entry(row, textvariable=self.outdir_var).pack(
            side='left', fill='x', expand=True)

        def _brw_out():
            d = filedialog.askdirectory(parent=win)
            if d:
                self.outdir_var.set(d)

        ttk.Button(row, text='浏览...', width=8,
                   command=_brw_out).pack(side='left', padx=(6, 0))
        ttk.Label(df, text='(设定后所有输出默认进这里; 留空=跟随上次输出目录)',
                  foreground='#888888').pack(anchor='w')
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Checkbutton(row, text='失败无限循环(自动重抓+自动续传)',
                        variable=self.loop_var).pack(side='left')
        ttk.Label(row, text='(仅单任务; 链接过期自动续命, 点「停止」退出)',
                  foreground='#888888').pack(side='left', padx=4)
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='代理:', width=10).pack(side='left')
        ttk.Entry(row, textvariable=self.proxy_var).pack(
            side='left', fill='x', expand=True)
        ttk.Label(row, text='(留空跟随系统)',
                  foreground='#888888').pack(side='left', padx=6)

        # ================= 画质 =================
        rf = fold('画质')
        row = ttk.Frame(rf); row.pack(fill='x', pady=2)
        ttk.Label(row, text='分辨率:', width=10).pack(side='left')
        ttk.Combobox(row, textvariable=self.res_var, state='readonly',
                     width=10, values=('最高', '2160p', '1440p', '1080p',
                                       '720p', '480p', '360p', '240p')
                     ).pack(side='left', padx=(4, 16))
        ttk.Label(row, text='(多码率流选≤该值的最优)',
                  foreground='#888888').pack(side='left')

        # ================= 命名 =================
        nf = fold('命名')
        row = ttk.Frame(nf); row.pack(fill='x', pady=2)
        ttk.Label(row, text='屏蔽词:', width=10).pack(side='left')
        ttk.Entry(row, textvariable=self.filter_var).pack(
            side='left', fill='x', expand=True)
        ttk.Label(row, text='(引号定词; 逗号/分号/空格分隔)',
                  foreground='#888888').pack(side='left', padx=6)
        row = ttk.Frame(nf); row.pack(fill='x', pady=2)
        ttk.Checkbutton(row, text='命名统一日期(9.9.2026→2026.09.09)',
                        variable=self.fixdate_var).pack(side='left')

        # ================= 缩略图 =================
        lf = fold('缩略图')
        row = ttk.Frame(lf); row.pack(fill='x')
        ttk.Checkbutton(row, text='下载完成后自动生成',
                        variable=self.thumbs_var).pack(side='left')
        ttk.Label(row, text='模式:').pack(side='left', padx=(12, 4))
        ttk.Radiobutton(row, text='网格', variable=self.thumbs_mode_var,
                        value='grid').pack(side='left')
        ttk.Radiobutton(row, text='数量', variable=self.thumbs_mode_var,
                        value='count').pack(side='left', padx=(6, 0))
        ttk.Radiobutton(row, text='间隔', variable=self.thumbs_mode_var,
                        value='every').pack(side='left', padx=(6, 8))
        ttk.Entry(row, textvariable=self.thumb_param_var, width=8).pack(side='left')
        ttk.Label(row, text='列数:').pack(side='left', padx=(10, 2))
        ttk.Spinbox(row, from_=2, to=10, textvariable=self.thumbs_cols_var,
                    width=4).pack(side='left')
        row = ttk.Frame(lf); row.pack(fill='x', pady=2)
        ttk.Checkbutton(row, text='只留拼图',
                        variable=self.sheetonly_var).pack(side='left')
        ttk.Checkbutton(row, text='铺满整行(多余帧删减)',
                        variable=self.fillrows_var).pack(side='left', padx=(16, 0))

        def clear_memory():
            try:
                _memory_file().unlink(missing_ok=True)
            except Exception:
                pass
            messagebox.showinfo('已清除', '解析记忆(含观察期)已清除, 下次重新积累',
                                parent=win)
            self._append_log('info', '解析记忆已清除')

        row = ttk.Frame(f); row.pack(fill='x', pady=(10, 2))
        ttk.Button(row, text='清除解析记忆(含观察期)',
                   command=clear_memory).pack(side='left')

        def done():
            od = self.outdir_var.get().strip()    # v5.9.1: 设了目录立即生效
            if od and Path(od).is_dir():
                # v5.9.9: 只在「保存为」是裸文件名、或正位于旧默认目录内
                # 时才跟随新默认目录(保留文件名); 自定义路径与带 .parts
                # 续传记录的输出一律不碰。
                cur = self.out_var.get().strip() or 'video.mp4'
                _po = Path(cur)
                _old = (self.settings.get('out_dir') or '').strip()
                _same_old = False
                if _old:
                    try:
                        _same_old = (os.path.normcase(
                            os.path.abspath(str(_po.parent)))
                            == os.path.normcase(os.path.abspath(_old)))
                    except Exception:
                        _same_old = str(_po.parent) == _old
                _follow = (_po.parent == Path('.') or _same_old)
                _has_parts = (Path(str(_po) + '.parts')
                              / 'state.json').exists()
                if _follow and not _has_parts:
                    self.out_var.set(str(Path(od) / _po.name))
            self._save_settings()
            win.destroy()

        ttk.Button(bar, text='保存并关闭', command=done).pack(side='right')

'''

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv5.9.11: 设置窗口重构(折叠分区+滚动+固定底栏+接管说明右移) /\n'
           '        时间段分隔符自由(时.分.秒/时-分-秒/中文标点均可) /\n'
           '        缩略图支持时间段(单张共用主栏位, 批量逐项从X到Y)\n'
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
    if '_same_old' not in text:
        die('未检测到 v5.9.9(_same_old) — 请先运行 patch_v599.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.11', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.11'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 5.9.11')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, PT_OLD, PT_NEW, '③ parse_time 分隔符自由')
    text = replace_once(text, HINT_OLD, HINT_NEW, '④ 主界面时间段提示')
    text = replace_once(text, MS_OLD, MS_NEW, '⑤ make_thumbnails_for 签名')
    text = replace_once(text, MB_OLD, MB_NEW, '⑥ 本地缩略图 时间段+span')
    text = replace_once(text, OS_OLD, OS_NEW, '⑦ online_thumbs 签名')
    text = replace_once(text, OB_OLD, OB_NEW, '⑧ 在线缩略图 时间段+span')
    text = replace_once(text, O1_OLD, O1_NEW, '⑨ 单张缩略图 时间段解析')
    text = replace_once(text, O2_OLD, O2_NEW, '⑩ 单张缩略图 日志')
    text = replace_once(text, O3_OLD, O3_NEW, '⑪ 单张缩略图 传参')
    text = replace_once(text, BT_OLD, BT_NEW, '⑫ 批量缩略图 说明文案')
    text = replace_once(text, BP_OLD, BP_NEW, '⑬ 批量缩略图 解析器')
    text = replace_once(text, BV_OLD, BV_NEW, '⑭ 批量缩略图 时间段校验')
    text = replace_once(text, BW_OLD, BW_NEW, '⑮ 批量缩略图 循环传参')
    text = replace_span(text, '    def _open_settings(self):',
                        '    def _thumb_cfg(self):', NEW_SETTINGS,
                        '⑯ 设置窗口重构(折叠+滚动+固定底栏)')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.11:')
    print('     · 设置窗口: 折叠分区 + 滚动 + 固定「保存并关闭」')
    print('     · 时间段: 中英文标点/横线/点 均可作时分秒分隔')
    print('     · 缩略图时间段: 单张(主栏位) + 批量(逐项 从X到Y)')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()