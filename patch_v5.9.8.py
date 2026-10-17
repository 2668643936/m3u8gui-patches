#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v598.py — m3u8gui.py v5.9.7 → v5.9.8 (被动嗅探增强)

背景: 纯被动在 camhive.net 这类站抓不到任何东西, 原因有二:
  ① 可见性: 浏览器插件用 webRequest API(浏览器进程级, 能看到所有
     iframe 包括跨进程的); 本工具走 chromedriver 的 CDP performance
     日志, 只挂在主页面目标上 — Chrome 站点隔离把跨域 iframe 播放器
     (vidara.so)放进独立进程, 其请求在日志里完全不可见
  ② 时机: 工具每 4 秒切进 iframe 读它的资源表(try_dom_harvest),
     整个观察期一无所获 — 该播放器在等一次"播放点击"才请求视频流

本补丁:
  ① 全帧媒体钩子: XHR/fetch/video.src 包装器注入所有同进程帧,
     媒体 URL 发出请求那一刻即经 postMessage 汇总到主帧, 轮询读取
  ② 被动兜底: 静默期落空且有 iframe → 直接打开 iframe 地址再监听
     35s(仍不点击; 部分嵌入播放器直开即自动起播)
  ③ 失败诊断升级: 明确提示"播放器在等点击, 换智能/可见窗口"
  ④ Referer 跟随实际命中页(iframe 直开命中时不再回填原页面)

依赖: 需先打 v5.9.6(_res_try_cache) 与 v5.9.7(_po.with_name)
用法: python patch_v598.py
"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')

PATCH_TOKENS = ('__m3u8gui_hook', '被动·iframe直开', '_MEDIA_HOOK_JS')


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


# ---------- ③ 媒体钩子 JS 常量 ----------
H1_OLD = r'''def _kill_profile_zombies(log=None, prof='chrome_profile'):'''
H1_NEW = r'''_MEDIA_HOOK_JS = r"""
(function(){
  try{
    if(window.__m3u8gui_hook) return;
    window.__m3u8gui_hook = 1;
    var RE=/\.(m3u8|mp4|webm|flv)(?:[?#]|$)/i, seen={};
    function rep(u){
      try{
        if(!u||typeof u!=='string') return;
        if(u.indexOf('//')!==0 && u.indexOf('http')!==0) return;
        if(u.indexOf('//')===0) u='https:'+u;
        if(!RE.test(u)) return;
        if(seen[u]) return;
        seen[u]=1;
        var f='';
        try{ f=(location.href||'').slice(0,150); }catch(e){}
        window.top.postMessage({__m3u8gui:1,u:u,f:f},'*');
      }catch(e){}
    }
    if(window.top===window){
      window.__m3u8gui_media=window.__m3u8gui_media||[];
      window.addEventListener('message',function(ev){
        try{
          var d=ev.data||{};
          if(d&&d.__m3u8gui&&d.u){
            window.__m3u8gui_media.push(d.u+'\t'+(d.f||''));
            if(window.__m3u8gui_media.length>300)
              window.__m3u8gui_media.shift();
          }
        }catch(e){}
      });
    }
    try{
      var _xo=XMLHttpRequest.prototype.open;
      XMLHttpRequest.prototype.open=function(m,u){
        try{ rep(typeof u==='string'?u:String(u||'')); }catch(e){}
        return _xo.apply(this,arguments);
      };
    }catch(e){}
    try{
      var _fo=window.fetch;
      if(_fo) window.fetch=function(i){
        try{ rep(typeof i==='string'?i:(i&&i.url)||''); }catch(e){}
        return _fo.apply(this,arguments);
      };
    }catch(e){}
    try{
      var _ds=Object.getOwnPropertyDescriptor(
        HTMLMediaElement.prototype,'src');
      if(_ds&&_ds.set){
        Object.defineProperty(HTMLMediaElement.prototype,'src',{
          set:function(v){try{rep(v);}catch(e){}return _ds.set.call(this,v);},
          get:_ds.get, configurable:true});
      }
    }catch(e){}
  }catch(e){}
})()"""


def _kill_profile_zombies(log=None, prof='chrome_profile'):'''

# ---------- ④ 注入(首屏加载前, 对之后所有导航生效) ----------
H2_OLD = r'''    try:
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': AD_BLOCK_PATTERNS})
    except Exception:
        pass
'''
H2_NEW = r'''    # v5.9.8: 全帧媒体钩子 — 包装 XHR/fetch/video.src, 媒体 URL 命中即
    # 经 postMessage 汇总到主帧。CDP 性能日志看不到跨进程 iframe(OOPIF)
    # 的请求, 此钩子补同进程缺口; OOPIF 由"被动·iframe直开"兜底。
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                            {'source': _MEDIA_HOOK_JS,
                             'runForSubFrames': True})
    except Exception:
        try:
            drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                                {'source': _MEDIA_HOOK_JS})
        except Exception:
            pass
    try:
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': AD_BLOCK_PATTERNS})
    except Exception:
        pass
'''

# ---------- ⑤ hook_poll 轮询函数 ----------
H3_OLD = r'''    def try_dom_harvest(drv):
        d = visit_frames(drv, harvest_dom)
'''
H3_NEW = r'''    def hook_poll():
        """v5.9.8: 读取全帧媒体钩子汇总(当前页主帧 __m3u8gui_media)"""
        try:
            rows = drv.execute_script(
                'return (window.__m3u8gui_media||[]).join("\\n")') or ''
        except Exception:
            return
        for ln in str(rows).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            u, _, frm = ln.partition('\t')
            u = u.strip()
            if not u.startswith('http'):
                continue
            ul = u.lower()
            if '.m3u8' in ul:
                if u not in all_m3u8_seen:
                    all_m3u8_seen.add(u)
                    consider_m3u8(u, '钩子@' + (frm or '?')[:40])
            elif (('.mp4' in ul or '.webm' in ul or '.flv' in ul)
                  and u not in mp4_cands and not AD_URL_RE.search(u)):
                mp4_cands[u] = 200

    def try_dom_harvest(drv):
        d = visit_frames(drv, harvest_dom)
'''

# ---------- ⑥ 静默期主循环挂钩子 ----------
H4_OLD = r'''        while time.time() - t0 < max(45, obs_limit) \
                or (shield_active() and time.time() - t0 < 45):
            seen0 = {}
            pump_logs(drv, seen0)
            for u, s in seen0.items():
                if s == 200 and u not in all_m3u8_seen:
                    all_m3u8_seen.add(u)
                    consider_m3u8(u, '静默期')
'''
H4_NEW = r'''        while time.time() - t0 < max(45, obs_limit) \
                or (shield_active() and time.time() - t0 < 45):
            seen0 = {}
            pump_logs(drv, seen0)
            hook_poll()      # v5.9.8: 全帧媒体钩子轮询
            for u, s in seen0.items():
                if s == 200 and u not in all_m3u8_seen:
                    all_m3u8_seen.add(u)
                    consider_m3u8(u, '静默期')
'''

# ---------- ⑦ 盾牌等待循环挂钩子 ----------
H5_OLD = r'''                        tw = time.time() + 45
                        while time.time() < tw and not pending:
                            seen0 = {}
                            pump_logs(drv, seen0)
'''
H5_NEW = r'''                        tw = time.time() + 45
                        while time.time() < tw and not pending:
                            seen0 = {}
                            pump_logs(drv, seen0)
                            hook_poll()
'''

# ---------- ⑧ 观察期轮挂钩子 ----------
H6_OLD = r'''                    while time.time() < t_end:
                        seen_round = {}
                        pump_logs(drv, seen_round)
'''
H6_NEW = r'''                    while time.time() < t_end:
                        seen_round = {}
                        pump_logs(drv, seen_round)
                        hook_poll()
'''

# ---------- ⑨ 被动兜底: iframe 直开(仍不点击) ----------
H7_OLD = r'''        if passive and not (pending or file_hit[0]):
            log('info', '[纯被动] 静默期未截获 — 被动模式不做点击/导航')
        elif not (pending or file_hit[0]):
'''
H7_NEW = r'''        if passive and not (pending or file_hit[0]):
            # v5.9.8: 被动兜底 — CDP 性能日志看不到跨进程 iframe(OOPIF)
            # 的网络请求(外站播放器全在其中)。静默期落空且有 iframe 时,
            # 直接打开 iframe 地址再监听一轮 — 仍是"不点击", 只是换了
            # 入口页; 播放器变主帧后其请求全部可见。
            if not iframes:
                try:
                    _l = drv.execute_script(
                        "return [].slice.call(document.querySelectorAll"
                        "('iframe')).map(function(f){return f.src||''})"
                        ".filter(function(s){return s.indexOf('http')===0})")
                    iframes = [u for u in (_l or [])
                               if 'challenge' not in u.lower()
                               and 'shield' not in u.lower()][:4]
                except Exception:
                    pass
            log('info', '[纯被动] 静默期未截获 — 被动模式不点击。'
                        + (f'发现 {len(iframes)} 个 iframe → 逐个直接打开'
                           '其地址继续监听(仍不点击)'
                           if iframes else '页面也没有可跟进的 iframe'))
            for _pt in iframes:
                if pending or file_hit[0]:
                    break
                log('info', f'[被动·iframe直开] {_pt[:70]}')
                try:
                    drv.get(_pt)
                except Exception:
                    pass
                time.sleep(2)
                _tpe = time.time() + 35
                while time.time() < _tpe and not (pending or file_hit[0]):
                    _seen_p = {}
                    pump_logs(drv, _seen_p)
                    hook_poll()
                    for u, s in _seen_p.items():
                        if s >= 200 and u not in all_m3u8_seen:
                            all_m3u8_seen.add(u)
                            consider_m3u8(u, '被动·iframe')
                    if pending and hit_at[0] is None:
                        hit_at[0] = time.time() - t0
                    if not (pending or file_hit[0]):
                        if try_dom_harvest(drv) and hit_at[0] is None:
                            hit_at[0] = time.time() - t0
                    sweep_popups()
                    time.sleep(1.2)
                if pending or file_hit[0]:
                    log('ok', '被动兜底: iframe 直开后截获媒体地址')
                    break
        elif not (pending or file_hit[0]):
'''

# ---------- ⑩ 收尾总账挂钩子 ----------
H8_OLD = r'''        if not pending and not file_hit[0]:
            try:
                res = drv.execute_script(
                    "return performance.getEntriesByType('resource')"
'''
H8_NEW = r'''        if not pending and not file_hit[0]:
            hook_poll()      # v5.9.8: 收尾前钩子最后补收一轮
            try:
                res = drv.execute_script(
                    "return performance.getEntriesByType('resource')"
'''

# ---------- ⑪ 失败诊断升级 ----------
H9_OLD = r'''        if not media:
            log('err', '未截获可用的 m3u8。诊断信息 ↓')
            log('info', '现场快照 → ' + (snapshot(drv)[:600] or '(空)'))
'''
H9_NEW = r'''        if not media:
            log('err', '未截获可用的 m3u8。诊断信息 ↓')
            log('info', '现场快照 → ' + (snapshot(drv)[:600] or '(空)'))
            if passive and iframes:
                log('info', '被动提示: iframe 直开后仍无流请求 — 播放器'
                            '多半在等一次"播放点击"才请求视频, 纯被动'
                            '拿不到这类站。请换「智能」策略或「可见窗口」')
'''

# ---------- ⑫ Referer 跟随实际命中页 ----------
H10_OLD = r'''            return None
        return media, page_url, cookie, ua, title
'''
H10_NEW = r'''            return None
        _cur = drv_current_url()
        if isinstance(_cur, str) and _cur.startswith('http') \
                and _cur != page_url:
            # v5.9.8: 在 iframe 直开页命中时, Referer 采用实际命中页
            log('info', f'媒体在 {urlparse(_cur).netloc} 页命中 → '
                        'Referer 采用该页地址')
            return media, _cur, cookie, ua, title
        return media, page_url, cookie, ua, title
'''

# ---------- ② 文件头更新日志 ----------
DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv5.9.8: 被动嗅探增强 — 全帧媒体钩子(XHR/fetch/video.src) /\n'
           '        被动兜底iframe直开 / Referer跟随实际命中页\n'
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
    if '_res_try_cache' not in text:
        die('未检测到 v5.9.6(_res_try_cache) — 请先运行 patch_v596.py')
    if '_po.with_name' not in text:
        die('未检测到 v5.9.7(_po.with_name) — 请先运行 patch_v597.py')

    print(f'[i] 源文件: {SRC}')
    print(f'[i] 行尾: {"CRLF(将保持)" if had_crlf else "LF"} · '
          f'BOM: {"有" if has_bom else "无"}')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.[89][\d.]*',
                       r'\g<1>5.9.8', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.[89][\d.]*'",
                       r"\g<1>5.9.8'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 5.8/5.9 系列)')
    print('[OK] ① 版本号 → 5.9.8')

    text = replace_once(text, DOC_OLD, DOC_NEW, '② 文件头更新日志')
    text = replace_once(text, H1_OLD, H1_NEW, '③ 媒体钩子 JS 常量')
    text = replace_once(text, H2_OLD, H2_NEW, '④ 钩子注入(首屏前)')
    text = replace_once(text, H3_OLD, H3_NEW, '⑤ hook_poll 轮询函数')
    text = replace_once(text, H4_OLD, H4_NEW, '⑥ 静默期主循环挂钩')
    text = replace_once(text, H5_OLD, H5_NEW, '⑦ 盾牌等待循环挂钩')
    text = replace_once(text, H6_OLD, H6_NEW, '⑧ 观察期轮挂钩')
    text = replace_once(text, H7_OLD, H7_NEW, '⑨ 被动兜底 iframe 直开')
    text = replace_once(text, H8_OLD, H8_NEW, '⑩ 收尾总账挂钩')
    text = replace_once(text, H9_OLD, H9_NEW, '⑪ 失败诊断升级')
    text = replace_once(text, H10_OLD, H10_NEW, '⑫ Referer 跟随命中页')

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
    print('[OK] m3u8gui.py 已升级到 v5.9.8:')
    print('     · 全帧媒体钩子(同进程帧媒体请求即刻可见)')
    print('     · 被动兜底: 静默期落空 → iframe 地址直开再监听(仍不点击)')
    print('     · 失败诊断: 明确区分"播放器等点击"类站点')
    print('     · Referer 跟随实际命中页')
    print()
    print('建议验证: python -m py_compile m3u8gui.py')


if __name__ == '__main__':
    main()