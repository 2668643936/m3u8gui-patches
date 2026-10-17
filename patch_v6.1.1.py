#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v611.py — m3u8gui.py v6.1.0 → v6.1.1 (批量任务中心 + 批量抓取)

  ① 批量任务中心: 一个窗口三个模式(批量抓取/批量缩略图/批量下载),
     顶部单选切换, 各模式清单独立持久化(batch_grab/batch_th/batch_dl),
     切换自动换内容。原「批量缩略图」「批量下载」两个独立窗口退役,
     主界面按钮改为打开任务中心并预选对应模式。
  ② 批量抓取: 每行一个播放页(可「标题 | 网址」), 逐页解析并把
     页→直链 写入抓取记录(已有记录的页直接秒回); 已是直链的行跳过。
     不下载 — 之后用批量下载填同样的页面链接即可命中记录免解析。
  ③ 停止事件桥: 任务中心运行缩略图模式时 _stop 同步 set 停止事件。

依赖: v6.1.0 已打(_link_recall)。用法: python patch_v611.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_batch_center', 'batch_grab')


def die(msg):
    print()
    print('[x] ' + msg)
    print('[x] 未做任何修改, 原文件保持不动。')
    sys.exit(1)


def replace_span(text, start, end, new_block, name):
    i = text.find(start)
    if i < 0:
        die(f'{name}: 起始锚点未找到')
    j = text.find(end, i + len(start))
    if j < 0:
        die(f'{name}: 结束锚点未找到')
    print(f'[OK] {name}')
    return text[:i] + new_block + text[j:]


def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        die(f'{name}: 锚点匹配 {n} 处(应为 1 处) — 请把完整输出发回定位')
    print(f'[OK] {name}')
    return text.replace(old, new, 1)


# ---------- ③ 任务中心(替换 _thumbs_only 整体) ----------
NEW_CENTER = r'''    def _batch_center(self, mode='grab'):
        """v6.1.1: 批量任务中心 — 抓取/缩略图/下载 三合一窗口"""
        if self.job or self._batch_running:
            messagebox.showinfo('提示', '已有下载任务在运行')
            return
        if self.thumb_job and self.thumb_job.is_alive():
            messagebox.showinfo('提示', '缩略图任务运行中, 请等它结束')
            return
        win = tk.Toplevel(self)
        win.title('批量任务中心')
        win.geometry('860x680')
        win.minsize(780, 600)
        win.transient(self)

        mv = tk.StringVar(value={'grab': '抓取', 'thumb': '缩略图',
                                 'download': '下载'}.get(mode, '抓取'))
        MODE_KEY = {'抓取': 'batch_grab', '缩略图': 'batch_th',
                    '下载': 'batch_dl'}
        HINTS = {
            '抓取': ('每行一个播放页网址, 可写「标题 | 网址」; #开头为注释。\n'
                    '逐页解析, 成功的 页→直链 写入抓取记录(已有记录的页秒回);\n'
                    '之后在「批量下载」里填同样的页面链接即可免解析直接下载。'),
            '缩略图': ('每行一个网址(播放页/m3u8/直链/本地视频路径), '
                      '可写「标题 | 网址 | 从10.00到25.00」。\n'
                      '时间段只认逐项「从X到Y」, 与下载的时间段无关; #为注释。'),
            '下载': ('每行一个网址:\n'
                    '  https://...                          ← 播放页(自动解析)\n'
                    '  我的标题 | https://...                ← 自定义文件名\n'
                    '  标题 | https://... | 从10:00到25:00     ← 该项专用时间段\n'
                    '时长不足自动跳过; 已有文件跳过; 失败项自动重抓一次。'),
        }

        bar_top = ttk.Frame(win, padding=(10, 8))
        bar_top.pack(fill='x', side='top')
        ttk.Label(bar_top, text='任务类型:').pack(side='left')

        hint = ttk.Label(win, foreground='#555555', justify='left',
                         wraplength=800, text='')
        hint.pack(anchor='w', padx=10)

        row_out = ttk.Frame(win)
        ttk.Label(row_out, text='输出目录:').pack(side='left')
        outdir_var = tk.StringVar(value=str(
            Path(self.out_var.get().strip() or 'video.mp4').resolve().parent))
        ttk.Entry(row_out, textvariable=outdir_var).pack(
            side='left', fill='x', expand=True, padx=(8, 6))

        def _brw_dir():
            d = filedialog.askdirectory(parent=win)
            if d:
                outdir_var.set(d)

        ttk.Button(row_out, text='浏览...', width=8,
                   command=_brw_dir).pack(side='left')

        txt = scrolledtext.ScrolledText(win, wrap='none', font=('Consolas', 9))
        txt.pack(fill='both', expand=True, padx=10, pady=4)

        lists = {k: (self.settings.get(k) or '')
                 for k in ('batch_grab', 'batch_th', 'batch_dl')}
        cur = {'mode': None}

        def hint_update():
            m2 = mv.get()
            if cur['mode']:
                lists[cur['mode']] = txt.get('1.0', 'end').rstrip('\n')
            cur['mode'] = MODE_KEY[m2]
            txt.delete('1.0', 'end')
            if lists[cur['mode']]:
                txt.insert('1.0', lists[cur['mode']])
            hint.config(text=HINTS[m2])
            if m2 == '抓取':
                row_out.pack_forget()
            else:
                row_out.pack(fill='x', padx=10, before=txt)

        for _t, _v in (('批量抓取', '抓取'), ('批量缩略图', '缩略图'),
                       ('批量下载', '下载')):
            ttk.Radiobutton(bar_top, text=_t, variable=mv, value=_v,
                            command=hint_update).pack(side='left', padx=(10, 0))
        hint_update()

        def go():
            m2 = mv.get()
            if cur['mode']:
                lists[cur['mode']] = txt.get('1.0', 'end').rstrip('\n')
            items = []
            for ln in txt.get('1.0', 'end').splitlines():
                ln = ln.strip()
                if not ln or ln.startswith('#'):
                    continue
                parts = [p.strip() for p in ln.split('|')]
                u = next((p for p in parts if p.startswith('http')), '') or ln
                rng = None
                label = None
                for p in parts:
                    if not p or p.startswith('http'):
                        continue
                    mm = re.match(r'^从(.+?)到(.*)$', p)
                    if mm:
                        rng = (mm.group(1), mm.group(2))
                    elif label is None:
                        label = p
                items.append(dict(label=label, url=u, rng=rng))
            if not items:
                messagebox.showerror('提示', '请先填入至少一个网址(每行一个)',
                                     parent=win)
                return
            proxy = self.proxy_var.get().strip() or None
            browser = self.browser_var.get()
            gmode = _mode_of(self.grabmode_var.get())
            show = (gmode == 'visible')
            try:
                port = int(self.grabport_var.get()) if gmode == 'attach' else None
            except (ValueError, tk.TclError):
                port = 9222
            outdir = outdir_var.get().strip() or '.'
            if m2 in ('缩略图', '下载'):
                try:
                    Path(outdir).mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    messagebox.showerror('提示', f'输出目录不可用: {e}',
                                         parent=win)
                    return
            fw = parse_filter_words(self.filter_var.get())
            fixdate = self.fixdate_var.get()
            g_start = self.start_var.get().strip()
            g_end = self.end_var.get().strip()
            if m2 == '下载' and (g_start or g_end):
                try:
                    parse_time(g_start)
                    parse_time(g_end)
                except ValueError:
                    messagebox.showerror('时间格式错误',
                                         '主界面「时间段」格式错误',
                                         parent=win)
                    return
            for _it in items:
                if not _it['rng']:
                    continue
                try:
                    parse_time(_it['rng'][0])
                    parse_time(_it['rng'][1])
                except ValueError:
                    messagebox.showerror(
                        '时间格式错误',
                        f"从{_it['rng'][0]}到{_it['rng'][1]} 格式错误",
                        parent=win)
                    return
            tc = None
            if m2 == '缩略图':
                r = self._thumb_cfg()
                if r is None:
                    return
                tc = r[0]
            try:
                workers = max(1, min(32, int(self.workers_var.get() or 8)))
            except (ValueError, tk.TclError):
                workers = 8
            reenc = self.reenc_var.get()
            keep = self.keep_var.get()
            for _k, _key in MODE_KEY.items():
                self.settings[_key] = lists.get(_key, '')
            self.settings[cur['mode']] = txt.get('1.0', 'end').strip()
            self._save_settings()
            win.destroy()
            self._batch_running = True
            self._batch_stop_flag = False
            self._batch_cur_job = None
            stop_ev = threading.Event()
            self._batch_stop_event = stop_ev
            for b in (self.start_btn, self.grab_btn, self.batch_btn,
                      self.one_thumb_btn, self.thumb_btn):
                b.config(state='disabled')
            self.stop_btn.config(state='normal')
            self._append_log('info', '=' * 46)
            self._append_log('info', f'批量{m2}开始: {len(items)} 项'
                             + (f' → {outdir}' if m2 != '抓取' else ''))
            self.status_lbl.config(text=f'批量{m2}...')

            def logL(level, msg):
                self.msgq.put(('log', level, msg))

            def finish(msg, style):
                self.msgq.put(('finish', True, msg, style))

            # ============ 批量抓取 ============
            def work_grab():
                ok_n = fail_n = 0
                fails = []
                for i, item in enumerate(items, 1):
                    if self._batch_stop_flag:
                        break
                    u = item['url']
                    self.msgq.put(('prog2', f"[{i}/{len(items)}] "
                                            f"{item['label'] or u[:60]}", None))
                    logL('info', f"==== [{i}/{len(items)}] "
                                 f"{item['label'] or u[:80]} ====")
                    if '.m3u8' in u.lower() or DIRECT_URL_RE.search(u):
                        logL('ok', f'已是媒体直链(无需解析): {u[:90]}')
                        ok_n += 1
                        continue
                    try:
                        got = smart_resolve(u, logL, proxy, show, port,
                                            browser=browser)
                    except Exception as e:
                        got = None
                        logL('err', f'解析异常: {e!r}')
                    if got:
                        if item['label']:
                            got['title'] = item['label']
                        logL('ok', f'直链: {str(got.get("url"))[:100]}')
                        if got.get('title'):
                            logL('info', f'标题: {got["title"][:60]}')
                        ok_n += 1
                    else:
                        fail_n += 1
                        fails.append(u)
                left = len(items) - ok_n - fail_n
                msg = (f'批量抓取结束: 成功 {ok_n} · 失败 {fail_n}'
                       + (f' · 未处理 {left}' if left else '')
                       + ' — 成功项已写入抓取记录, 批量下载同页免解析')
                style = 'ok' if (fail_n == 0 and left == 0) else 'warn'
                logL(style, msg)
                if fails:
                    logL('warn', '—— 失败清单 ——')
                    for u2 in fails:
                        logL('err', f'  {u2[:95]}')
                finish(msg, style)

            # ============ 批量缩略图 ============
            def work_thumb():
                ok_n = fail_n = 0
                fails = []
                pf = {}
                pf_started = set()
                pf_lock = threading.Lock()

                def _pf_resolve(idx, plabel, pu):
                    try:
                        got = smart_resolve(pu, logL, proxy, show, port,
                                            browser=browser,
                                            force_browser=True)
                        if got and plabel:
                            got['title'] = plabel
                    except Exception as e:
                        logL('err', f'预解析异常: {e!r}')
                        got = None
                    with pf_lock:
                        pf[idx] = got

                def _pf_kick(idx, plabel, pu):
                    if idx < 1 or idx > len(items) or idx in pf_started:
                        return
                    pf_started.add(idx)
                    if '.m3u8' in pu.lower() or DIRECT_URL_RE.search(pu):
                        with pf_lock:
                            pf[idx] = {'url': pu, 'referer': '',
                                       'cookie': '', 'ua': '',
                                       'title': plabel or '',
                                       'headers': {}, 'page': ''}
                    else:
                        threading.Thread(target=_pf_resolve,
                                         args=(idx, plabel, pu),
                                         daemon=True).start()

                def _pf_wait(idx):
                    while True:
                        with pf_lock:
                            if idx in pf:
                                return pf[idx]
                        if self._batch_stop_flag:
                            return None
                        time.sleep(0.5)

                for i, item in enumerate(items, 1):
                    if self._batch_stop_flag:
                        break
                    label, u, rng = item['label'], item['url'], item['rng']
                    self.msgq.put(('prog2', f"[{i}/{len(items)}] "
                                            f"{label or u[:60]}", None))
                    logL('info', f'—— [{i}/{len(items)}] {label or u[:80]} ——')
                    r_i = None
                    if rng:
                        try:
                            _a = parse_time(rng[0]) if rng[0] else None
                            _b = parse_time(rng[1]) if rng[1] else None
                        except ValueError:
                            logL('err', '时间段格式错误, 该项按整段处理')
                            r_i = None
                        else:
                            r_i = None if (_a is None and _b is None) \
                                else (_a, _b)
                    try:
                        p = Path(u)
                        if p.exists() and p.is_file():
                            if i < len(items):
                                _pf_kick(i + 1, items[i]['label'],
                                         items[i]['url'])
                            ok = make_thumbnails_for(p, tc, logL, self.msgq,
                                                     stop_ev, t_range=r_i)
                        else:
                            _pf_kick(i, label, u)
                            got = _pf_wait(i)
                            if i < len(items):
                                _pf_kick(i + 1, items[i]['label'],
                                         items[i]['url'])
                            if not got:
                                logL('err', '解析失败, 跳过该项')
                                fail_n += 1
                                fails.append(u)
                                continue
                            ok = online_thumbs(got, label or '', outdir, tc,
                                               logL, self.msgq, stop_ev,
                                               proxy, fw=fw, fixdate=fixdate,
                                               t_range=r_i)
                        if ok:
                            ok_n += 1
                        else:
                            fail_n += 1
                            fails.append(u)
                    except Exception as e:
                        logL('err', f'失败: {e!r}')
                        fail_n += 1
                        fails.append(u)
                left = len(items) - ok_n - fail_n
                if self._batch_stop_flag:
                    msg = (f'批量缩略图已停止: 成功 {ok_n} / 失败 {fail_n}'
                           + (f' / 未处理 {left}' if left else ''))
                else:
                    msg = (f'批量缩略图完成: 成功 {ok_n}'
                           + (f' / 失败 {fail_n}' if fail_n else ''))
                style = 'ok' if fail_n == 0 else 'warn'
                logL(style, msg)
                if fails:
                    fails.sort(key=lambda x: not _is_page_url(x))
                    logL('warn', '—— 失败清单(网页链接优先) ——')
                    for u2 in fails:
                        logL('err', f'  {"[网页]" if _is_page_url(u2) else "[直链]"} '
                                    f'{u2[:95]}')
                self._remember_dir(outdir)
                finish(msg, style)

            # ============ 批量下载 ============
            used = set()

            def run_one(item, idx, total_n):
                u = item['url']
                label = item['label']
                rng = item['rng'] or ((g_start, g_end)
                                      if (g_start or g_end) else None)
                s = e = None
                if rng:
                    try:
                        s = parse_time(rng[0]) if rng[0] else None
                        e = parse_time(rng[1]) if rng[1] else None
                    except ValueError:
                        logL('err', '时间段格式错误, 该项按整段处理')
                        s = e = None
                is_direct = ('.m3u8' in u.lower() or DIRECT_URL_RE.search(u))
                got = None
                if is_direct:
                    got = {'url': u, 'referer': self.ref_var.get().strip(),
                           'cookie': self.cookie_var.get().strip(),
                           'ua': '', 'title': label or '', 'headers': {},
                           'page': ''}
                else:
                    logL('info', f'解析: {u[:70]}')
                    got = smart_resolve(u, logL, proxy, show, port,
                                        browser=browser, force_browser=True)
                    if got and label:
                        got['title'] = label
                if not got:
                    logL('err', f'解析失败, 跳过: {u[:70]}')
                    return 'fail', u
                title = (got.get('title') or '').strip()
                if not title:
                    title = direct_title(got['url']) or \
                        urlparse(got['url']).netloc.replace('.', '_')
                t = transform_title(title, fw, fixdate)
                base = safe_name(t, url=got['url'], base_dir=outdir, limit=80,
                                 filter_words=fw)
                if base in used:
                    n = 2
                    while f'{base}_{n}' in used:
                        n += 1
                    base = f'{base}_{n}'
                output = Path(outdir) / (base + '.mp4')
                if output.exists() and not (
                        Path(str(output) + '.parts')
                        / 'state.json').exists():
                    logL('info', f'文件已存在 → 跳过: {output.name}')
                    return 'skip', None
                used.add(base)
                cfg = dict(url=got['url'], output=str(output), start=s, end=e,
                           workers=workers,
                           referer=got.get('referer') or '',
                           cookie=got.get('cookie') or '',
                           extra_headers=dict(got.get('headers') or {}),
                           proxy=proxy, force_reencode=reenc, thumbs=tc,
                           keep=keep)
                jq = queue.Queue()
                job = Job(cfg, jq)
                self._batch_cur_job = job
                job.start()
                name = label or base

                def drain(j2, q2):
                    while True:
                        try:
                            m = q2.get(timeout=0.5)
                        except queue.Empty:
                            if not j2.is_alive():
                                while True:
                                    try:
                                        m = q2.get_nowait()
                                    except queue.Empty:
                                        break
                                    self._batch_fwd(m, idx, total_n, name)
                                break
                            continue
                        self._batch_fwd(m, idx, total_n, name)

                drain(job, jq)
                self._batch_cur_job = None
                st = job.finish_state
                if st == 'fail' and got.get('page') \
                        and not item.get('_retried'):
                    logL('warn', f'{name}: 疑似链接过期 → 重抓一次...')
                    item['_retried'] = True
                    got2 = smart_resolve(got['page'], logL, proxy, show,
                                         port, browser=browser,
                                         force_browser=True,
                                         use_memory=False)
                    if got2:
                        if label:
                            got2['title'] = label
                        cfg2 = dict(cfg, url=got2['url'],
                                    referer=got2.get('referer') or '',
                                    cookie=got2.get('cookie') or '',
                                    extra_headers=dict(got2.get('headers')
                                                       or {}))
                        jq2 = queue.Queue()
                        job2 = Job(cfg2, jq2)
                        self._batch_cur_job = job2
                        job2.start()
                        drain(job2, jq2)
                        self._batch_cur_job = None
                        st = job2.finish_state
                return (st if st in ('ok', 'skip', 'stop') else 'fail'), \
                    (got.get('page') or (u if not is_direct else ''))

            def work_download():
                ok_n = skip_n = fail_n = stop_n = 0
                fails = []
                for idx, item in enumerate(items, 1):
                    if self._batch_stop_flag:
                        break
                    name0 = item['label'] or item['url'][:60]
                    self.msgq.put(('bprog2', idx, len(items), name0,
                                   '准备解析...', None))
                    logL('info', f'==== [{idx}/{len(items)}] {name0} ====')
                    try:
                        r, fsrc = run_one(item, idx, len(items))
                    except Exception as ex:
                        logL('err', f'异常: {ex!r}')
                        r, fsrc = 'fail', item['url']
                    if r == 'ok':
                        ok_n += 1
                    elif r == 'skip':
                        skip_n += 1
                    elif r == 'stop':
                        stop_n += 1
                        break
                    else:
                        fail_n += 1
                        if fsrc:
                            fails.append(fsrc)
                total = len(items)
                left = total - ok_n - skip_n - fail_n - stop_n
                msg = (f'批量下载结束: 成功 {ok_n} · 跳过 {skip_n}'
                       f' · 失败 {fail_n}'
                       + (f' · 中断 {stop_n}' if stop_n else '')
                       + (f' · 未处理 {left}' if left else ''))
                style = 'ok' if (fail_n == 0 and left == 0) else 'warn'
                logL(style, msg)
                if fails:
                    fails.sort(key=lambda u: not _is_page_url(u))
                    logL('warn', '—— 失败清单(网页链接优先) ——')
                    for u in fails:
                        logL('err', f'  {"[网页]" if _is_page_url(u) else "[直链]"} '
                                    f'{u[:95]}')
                finish(msg, style)

            _workers = {'抓取': work_grab, '缩略图': work_thumb,
                        '下载': work_download}
            threading.Thread(target=_workers[m2], daemon=True).start()

        bar = ttk.Frame(win, padding=(10, 8))
        bar.pack(fill='x', side='bottom')

        def clear_cur():
            txt.delete('1.0', 'end')
            if cur['mode']:
                lists[cur['mode']] = ''

        ttk.Button(bar, text='清空', width=6,
                   command=clear_cur).pack(side='left', padx=8)
        ttk.Button(bar, text='取消', command=win.destroy).pack(side='right')
        ttk.Button(bar, text='开始', command=go).pack(side='right', padx=(8, 0))
        txt.focus_set()

    def _thumbs_only(self):
        self._batch_center('thumb')

'''

# ---------- ④ _batch_download → 任务中心包装 ----------
NEW_DL_WRAPPER = '''    def _batch_download(self):
        self._batch_center('download')

'''

# ---------- ⑤ _stop: 批量停止事件桥 ----------
STOP_OLD = '''            self._batch_stop_flag = True
            if self._batch_cur_job:
                self._batch_cur_job.stop.set()
'''
STOP_NEW = '''            self._batch_stop_flag = True
            if self._batch_cur_job:
                self._batch_cur_job.stop.set()
            if getattr(self, '_batch_stop_event', None):   # v6.1.1: 缩略图模式
                self._batch_stop_event.set()
'''

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv6.1.1: 批量任务中心(抓取/缩略图/下载三合一窗口, 清单独立\n'
           '        持久化) + 批量抓取(逐页解析写抓取记录, 下载免解析)\n'
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
    if '_link_recall' not in text:
        die('未检测到 v6.1.0(_link_recall) — 请先运行 patch_v610.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)6\.1\.0',
                       r'\g<1>6.1.1', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')6\.1\.0'",
                       r"\g<1>6.1.1'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 6.1.0)')
    print('[OK] ① 版本号 → 6.1.1')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_span(text, '    def _thumbs_only(self):',
                        '    def _append_log(self, level, msg):',
                        NEW_CENTER, '③ 任务中心+_thumbs_only包装')
    text = replace_span(text, '    def _batch_download(self):',
                        '    def _batch_fwd(self, m, idx, total, name):',
                        NEW_DL_WRAPPER, '④ _batch_download包装')
    text = replace_once(text, STOP_OLD, STOP_NEW, '⑤ _stop 停止事件桥')

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
    print('[OK] m3u8gui.py 已升级到 v6.1.1:')
    print('     · 批量任务中心: 抓取/缩略图/下载 三合一窗口')
    print('     · 批量抓取: 逐页解析 → 写抓取记录 → 下载免解析')
    print('     · 主界面两个批量按钮改为打开任务中心(预选模式)')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()