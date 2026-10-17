#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v600.py — m3u8gui.py v5.9.11 → v6.0.0

  ① 插件嗅探桥: 自动发现档案内嗅探扩展(猫抓等, 自动排除广告拦截类),
     开其 options 后台标签, 轮询 chrome.storage.local 全量 dump + 页面
     文本, 正则抽 m3u8/mp4 喂现有验证链。OOPIF/任何帧发出的请求插件
     全可见 — 补 CDP 性能日志的跨进程盲区。未装嗅探扩展时静默跳过。
     接管模式/临时档案不启用桥。
  ② 数据目录: 设置新增「数据目录」— chrome_profile/edge_profile、
     ffmpeg/ffprobe/yt-dlp/chromedriver、seg_cache、解析记忆 全部
     改放/改查该目录(查找顺序 PATH→数据目录→程序旁)。打包重铸清空
     文件夹不再丢档案/工具/插件/记忆。settings.json 仍在程序旁作引导。
  ③ 弹窗清理(sweep_popups)顺带驱动桥轮询(6s节流), 收尾总账前再补收
     一轮。

依赖: 需已打 v5.9.7(_po.with_name)、v5.9.9(_same_old)、v5.9.11
     (_TIME_SEP_TRANS)。与 598/5910 锚点无冲突, 建议全套齐备。
用法: python patch_v600.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('_init_data_dir', '_sniffer_exts', 'ext_poll', 'datadir_var')


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


# ---------- ③ 数据目录: 引导初始化(挂在 CACHE_DIR 定义处) ----------
P1_OLD = '''CACHE_DIR = APP_DIR / 'seg_cache'
CACHE_TTL = 36 * 3600
CACHE_MAX = 500 * 1048576
'''
P1_NEW = '''_DATA_DIR = None


def _init_data_dir():
    """v6.0.0: 启动时读设置里的 data_dir — 档案/工具/缓存/解析记忆的
    实际存放处。settings.json 仍留在程序旁作引导文件。"""
    global _DATA_DIR, CACHE_DIR
    try:
        d = (load_settings().get('data_dir') or '').strip()
    except Exception:
        d = ''
    if d and Path(d).is_dir():
        _DATA_DIR = Path(d)
        try:                       # 旧解析记忆自动迁移到数据目录
            _om = APP_DIR / 'resolve_memory.json'
            _nm = _DATA_DIR / 'resolve_memory.json'
            if _om.exists() and not _nm.exists():
                _om.replace(_nm)
        except Exception:
            pass
    CACHE_DIR = _data_dir() / 'seg_cache'


_init_data_dir()

CACHE_TTL = 36 * 3600
CACHE_MAX = 500 * 1048576
'''

# ---------- ③ _data_dir 访问器(插在 _find_tool 前) ----------
P2_OLD = '''def _find_tool(name):'''
P2_NEW = '''_DATA_DIR = None


def _data_dir():
    """v6.0.0: 外部数据目录(设置→数据目录); 未设置时= APP_DIR"""
    return _DATA_DIR if _DATA_DIR is not None else APP_DIR


def _find_ytdlp():
    p = shutil.which('yt-dlp')
    if p:
        return p
    for base in (_data_dir(), APP_DIR):
        c = Path(base) / 'yt-dlp.exe'
        if c.exists():
            return str(c)
    return None


def _find_tool(name):'''

# ---------- ③ _find_tool 体: PATH → 数据目录 → 程序旁 ----------
P3_OLD = '''    p = shutil.which(name)
    if p:
        return p
    local = APP_DIR / f'{name}.exe'
    return str(local) if local.exists() else None
'''
P3_NEW = '''    p = shutil.which(name)
    if p:
        return p
    for base in (_data_dir(), APP_DIR):
        local = Path(base) / f'{name}.exe'
        if local.exists():
            return str(local)
    return None
'''

# ---------- ③ 解析记忆位置 ----------
P4_OLD = '''def _memory_file():
    return APP_DIR / 'resolve_memory.json'
'''
P4_NEW = '''def _memory_file():
    return _data_dir() / 'resolve_memory.json'
'''

# ---------- ③ yt-dlp 两处 ----------
P5_OLD = '''def ytdlp_resolve(page_url, log, proxy=None):
    exe = shutil.which('yt-dlp') or str(APP_DIR / 'yt-dlp.exe')
    if not Path(exe).exists():
        return None
'''
P5_NEW = '''def ytdlp_resolve(page_url, log, proxy=None):
    exe = _find_ytdlp()
    if not exe:
        return None
'''
P6_OLD = '''    ytdlp_exe = shutil.which('yt-dlp') or str(APP_DIR / 'yt-dlp.exe')
    ytdlp_ok = Path(ytdlp_exe).exists()
'''
P6_NEW = '''    ytdlp_ok = bool(_find_ytdlp())
'''

# ---------- ③ 驱动与档案路径 ----------
P7_OLD = '''    if bname == 'edge' and not attached:
        drv_path = APP_DIR / 'msedgedriver.exe'
    else:
        drv_path = APP_DIR / 'chromedriver.exe'
'''
P7_NEW = '''    if bname == 'edge' and not attached:
        drv_path = _data_dir() / 'msedgedriver.exe'
        if not drv_path.exists():
            drv_path = APP_DIR / 'msedgedriver.exe'
    else:
        drv_path = _data_dir() / 'chromedriver.exe'
        if not drv_path.exists():
            drv_path = APP_DIR / 'chromedriver.exe'
'''
P8_OLD = '''        o.add_argument(f'--user-data-dir={APP_DIR / prof_name}')'''
P8_NEW = '''        o.add_argument(f'--user-data-dir={_data_dir() / prof_name}')'''

# ---------- ① 嗅探扩展枚举 ----------
P9_OLD = '''def browser_auto_extract(page_url, log, show_browser=False, chrome_port=None,'''
P9_NEW = '''_SNIFFER_SKIP_IDS = {
    'cjpalhdlnbpafiamejdnhcphjbkeiagm',   # uBlock Origin
    'ddkjiahejlhfcafbddmgiahcphecmpfh',   # uBlock Origin Lite
    'gighmmpiobklfepjocnamgkkbiglidom',   # AdBlock
    'cfhdojbkjhnklbpkdaibdccddilifddb',   # Adblock Plus
}


def _sniffer_exts(profile_dir):
    """v6.0.0: 枚举档案里已装的嗅探类扩展(带 webRequest/DNR 权限),
    返回 [(ext_id, 页面路径, 名称)] — 页面在 options/popup 里挑磁盘上
    真实存在的。广告拦截类被排除(存储里没有媒体列表, 不浪费轮询)。"""
    base = Path(profile_dir) / 'Default' / 'Extensions'
    out = []
    if not base.is_dir():
        return out
    for idir in sorted(base.iterdir()):
        if not idir.is_dir() or idir.name in _SNIFFER_SKIP_IDS:
            continue
        vers = sorted((v for v in idir.iterdir() if v.is_dir()),
                      key=lambda p: p.name)
        if not vers:
            continue
        vdir = vers[-1]
        try:
            m = json.loads((vdir / 'manifest.json').read_text(
                encoding='utf-8-sig'))
        except Exception:
            continue
        perms = set(m.get('permissions') or [])
        perms |= set(m.get('host_permissions') or [])
        if not (perms & {'webRequest', 'webRequestBlocking',
                         'declarativeNetRequest',
                         'declarativeNetRequestWithHostAccess'}):
            continue
        name = m.get('name') or ''
        if '__MSG_' not in name and re.search(
                r'ublock|adblock|ad ?block', name, re.I):
            continue
        cands = [m.get('options_page'),
                 (m.get('options_ui') or {}).get('page'),
                 (m.get('action') or {}).get('default_popup'),
                 (m.get('browser_action') or {}).get('default_popup')]
        page = next((c for c in cands if c and (vdir / c).exists()), None)
        if not page:
            continue
        out.append((idir.name, page, name[:24]))
    return out


def browser_auto_extract(page_url, log, show_browser=False, chrome_port=None,'''

# ---------- ① 桥初始化(Network 拦截配置之后) ----------
P10_OLD = '''    try:
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': AD_BLOCK_PATTERNS})
    except Exception:
        pass
'''
P10_NEW = '''    try:
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': AD_BLOCK_PATTERNS})
    except Exception:
        pass

    # v6.0.0: 插件嗅探桥 — 档案里装了嗅探扩展(猫抓等)时, 开其 options
    # 后台标签, 轮询 chrome.storage 全量 dump + 页面文本抽媒体地址。
    # 插件挂在浏览器进程上, OOPIF/任何帧的请求全可见, 补 CDP 盲区。
    _ext = {'tabs': []}
    if not attached and not used_temp_profile:
        try:
            _sn = _sniffer_exts(_data_dir() / prof_name)
            if _sn:
                try:
                    drv.set_script_timeout(8)
                except Exception:
                    pass
                for _eid, _pg, _nm in _sn:
                    try:
                        _before = set(drv.window_handles)
                        _tid = drv.execute_cdp_cmd(
                            'Target.createTarget',
                            {'url': f'chrome-extension://{_eid}/{_pg}',
                             'newWindow': False}).get('targetId')
                        _new = set(drv.window_handles) - _before
                        if _tid and _new:
                            _ext['tabs'].append((_tid, _new.pop(), _nm))
                    except Exception:
                        continue
                if _ext['tabs']:
                    try:               # 窗口守卫/弹窗清理别关桥页
                        baseline.update(drv.window_handles)
                    except Exception:
                        pass
                    log('info', '插件嗅探桥: '
                        + '、'.join(n for _t, _w, n in _ext['tabs'])
                        + f' — 后台标签轮询({len(_ext["tabs"])}个)')
        except Exception:
            pass
'''

# ---------- ① 轮询挂到 sweep_popups(所有循环都调用它) ----------
P11_OLD = '''        if n:
            popups_closed += n
'''
P11_NEW = '''        if n:
            popups_closed += n
        try:
            ext_poll()      # v6.0.0: 插件嗅探桥与弹窗清理同节奏轮询
        except Exception:
            pass
'''

# ---------- ① ext_poll 定义(插在 obs_dom 前, 5910 的 cred_rescue 之后) ----------
P12_OLD = '''    obs_dom = _domain_of(page_url)'''
P12_NEW = '''    _ext_t = [0.0]

    def ext_poll():
        """v6.0.0: 插件嗅探桥轮询 — 切到扩展 options 页, dump
        chrome.storage.local 全量 + 页面可见文本, 正则抽媒体地址喂
        验证链。节流 6s; 桥页被关则移除; 用完切回原句柄。"""
        if not _ext.get('tabs') or time.time() - _ext_t[0] < 6:
            return
        _ext_t[0] = time.time()
        keep = None
        try:
            keep = drv.current_window_handle
        except Exception:
            pass
        try:
            for tid, wh, ename in list(_ext['tabs']):
                if wh not in drv.window_handles:
                    _ext['tabs'].remove((tid, wh, ename))
                    continue
                try:
                    drv.switch_to.window(wh)
                except Exception:
                    continue
                blob = ''
                try:
                    blob = drv.execute_async_script(
                        'var cb=arguments[arguments.length-1];'
                        'try{chrome.storage.local.get(null,'
                        'function(d){cb(JSON.stringify(d))});}'
                        'catch(e){cb("");}') or ''
                except Exception:
                    blob = ''
                try:
                    blob += '\\n' + (drv.find_element(
                        'tag name', 'body').text or '')
                except Exception:
                    pass
                blob = (blob or '')[:400000]
                for u in re.findall(
                        r'https?://[^\\s"\\'\\\\<>]+?\\.(?:m3u8|mp4|webm|flv)'
                        r'(?:\\?[^\\s"\\'\\\\<>]*)?', blob, re.I):
                    u = u.replace('\\/', '/')
                    if '.m3u8' in u.lower():
                        if u not in all_m3u8_seen:
                            all_m3u8_seen.add(u)
                            consider_m3u8(u, f'插件桥·{ename}')
                    elif u not in mp4_cands and not AD_URL_RE.search(u):
                        mp4_cands[u] = 200
        finally:
            try:
                if keep:
                    drv.switch_to.window(keep)
            except Exception:
                pass

    obs_dom = _domain_of(page_url)'''

# ---------- ① 收尾总账补收 ----------
P13_OLD = '''                        consider_m3u8(u, '总账')
            except Exception:
                pass
'''
P13_NEW = '''                        consider_m3u8(u, '总账')
            except Exception:
                pass
            try:
                ext_poll()      # v6.0.0: 收尾前插件桥最后补收
            except Exception:
                pass
'''

# ---------- ① 关桥页 ----------
P14_OLD = '''    finally:
        try:
            guard_run.clear()          # v5.8.4: 停掉窗口守卫线程
        except Exception:
            pass
'''
P14_NEW = '''    finally:
        for tid, _wh, _n in _ext.get('tabs', []):
            try:
                drv.execute_cdp_cmd('Target.closeTarget', {'targetId': tid})
            except Exception:
                pass
        try:
            guard_run.clear()          # v5.8.4: 停掉窗口守卫线程
        except Exception:
            pass
'''

# ---------- ② 设置变量/持久化/UI/即时生效 ----------
P15_OLD = '''        self.outdir_var = tk.StringVar(value=_dft)
'''
P15_NEW = '''        self.outdir_var = tk.StringVar(value=_dft)
        self.datadir_var = tk.StringVar(value=s.get('data_dir') or '')
'''
P16_OLD = '''                out_dir=self.outdir_var.get().strip(),
                loop_mode=self.loop_var.get(),
'''
P16_NEW = '''                out_dir=self.outdir_var.get().strip(),
                data_dir=self.datadir_var.get().strip(),
                loop_mode=self.loop_var.get(),
'''
P17_OLD = '''        ttk.Label(df, text='(设定后所有输出默认进这里; 留空=跟随上次输出目录)',
                  foreground='#888888').pack(anchor='w')
'''
P17_NEW = '''        ttk.Label(df, text='(设定后所有输出默认进这里; 留空=跟随上次输出目录)',
                  foreground='#888888').pack(anchor='w')
        row = ttk.Frame(df); row.pack(fill='x', pady=2)
        ttk.Label(row, text='数据目录:', width=10).pack(side='left')
        ttk.Entry(row, textvariable=self.datadir_var).pack(
            side='left', fill='x', expand=True)

        def _brw_data():
            d = filedialog.askdirectory(parent=win)
            if d:
                self.datadir_var.set(d)

        ttk.Button(row, text='浏览...', width=8,
                   command=_brw_data).pack(side='left', padx=(6, 0))
        ttk.Label(df, text='(v6: chrome_profile/edge_profile、ffmpeg/ffprobe/'
                    'yt-dlp、seg_cache缓存、解析记忆都改放这里 — '
                    '打包清空文件夹不再丢; 换目录后旧文件夹需手动移过去)',
                  foreground='#888888').pack(anchor='w')
'''
P18_OLD = '''                if _follow and not _has_parts:
                    self.out_var.set(str(Path(od) / _po.name))
            self._save_settings()
            win.destroy()
'''
P18_NEW = '''                if _follow and not _has_parts:
                    self.out_var.set(str(Path(od) / _po.name))
            self._save_settings()
            _init_data_dir()      # v6.0.0: 数据目录改动立即生效
            win.destroy()
'''

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv6.0.0: 插件嗅探桥(自动发现嗅探扩展, storage全量dump+文本兜底,\n'
           '        喂现有验证链) / 数据目录(档案/工具/缓存/记忆外置,\n'
           '        打包重铸不再丢; 工具查找 PATH→数据目录→程序旁)\n'
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
    for dep, who in (('_po.with_name', 'v5.9.7'),
                     ('_same_old', 'v5.9.9'),
                     ('_TIME_SEP_TRANS', 'v5.9.11')):
        if dep not in text:
            die(f'未检测到 {who}({dep}) — 请先按顺序补齐')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>6.0.0', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>6.0.0'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 6.0.0')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, P1_OLD, P1_NEW, '③ 数据目录初始化')
    text = replace_once(text, P2_OLD, P2_NEW, '④ _data_dir + _find_ytdlp')
    text = replace_once(text, P3_OLD, P3_NEW, '⑤ _find_tool 三级查找')
    text = replace_once(text, P4_OLD, P4_NEW, '⑥ 解析记忆位置')
    text = replace_once(text, P5_OLD, P5_NEW, '⑦ ytdlp_resolve 查找')
    text = replace_once(text, P6_OLD, P6_NEW, '⑧ smart_resolve ytdlp 检查')
    text = replace_once(text, P7_OLD, P7_NEW, '⑨ 驱动路径三级查找')
    text = replace_once(text, P8_OLD, P8_NEW, '⑩ 档案路径→数据目录')
    text = replace_once(text, P9_OLD, P9_NEW, '⑪ 嗅探扩展枚举')
    text = replace_once(text, P10_OLD, P10_NEW, '⑫ 桥初始化(开桥页)')
    text = replace_once(text, P11_OLD, P11_NEW, '⑬ sweep_popups 挂轮询')
    text = replace_once(text, P12_OLD, P12_NEW, '⑭ ext_poll 定义')
    text = replace_once(text, P13_OLD, P13_NEW, '⑮ 收尾总账补收')
    text = replace_once(text, P14_OLD, P14_NEW, '⑯ 关桥页')
    text = replace_once(text, P15_OLD, P15_NEW, '⑰ 设置变量')
    text = replace_once(text, P16_OLD, P16_NEW, '⑱ 设置持久化')
    text = replace_once(text, P17_OLD, P17_NEW, '⑲ 设置UI数据目录行')
    text = replace_once(text, P18_OLD, P18_NEW, '⑳ 保存后立即生效')

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
    print('[OK] m3u8gui.py 已升级到 v6.0.0:')
    print('     · 插件嗅探桥: 猫抓等嗅探扩展的捕获 → 自动喂验证链')
    print('     · 数据目录: 档案/工具/缓存/记忆外置, 打包清空不再丢')
    print()
    print('后续: 设置→数据目录 填入外部目录; 给 chrome_profile 装猫抓')
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()