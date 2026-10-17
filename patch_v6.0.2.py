#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hotfix_v602.py — v6.0.x → v6.0.2 (插件桥诊断强化)
① _sniffer_exts 全程打日志(扫描路径/每个扩展判定结论)
② 扫描 Default + 全部 Profile* 子目录(扩展可能不在 Default)
③ 开桥页后等句柄最长3s(修 window_handles 竞态: 标签开了却没注册)
④ 未发现嗅探扩展时也打一行, 不再无声跳过
兼容 6.0.0 / 6.0.1。用法: python hotfix_v602.py"""

import re
import shutil
import sys
from pathlib import Path

SRC = (Path(sys.argv[1]) if len(sys.argv) > 1
       else Path(__file__).parent / 'm3u8gui.py')


def die(msg):
    print('[x] ' + msg)
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


NEW_FN = '''def _sniffer_exts(profile_dir, log=None):
    """v6.0.2: 枚举档案内嗅探扩展 — 扫 Default 与全部 Profile* 子目录,
    每个候选给出判定日志(权限/黑名单/页面), 排障不再黑箱。"""
    out = []
    pdir = Path(profile_dir)
    if not pdir.is_dir():
        if log:
            log('info', f'[插件桥] 档案目录不存在: {pdir}')
        return out
    bases = [pdir / 'Default'] + sorted(
        [d for d in pdir.iterdir()
         if d.is_dir() and d.name.lower().startswith('profile')])
    hit_dirs = [b for b in bases if (b / 'Extensions').is_dir()]
    if log:
        log('info', f'[插件桥] 扫描 {pdir}')
        log('info', '[插件桥] Extensions 目录: '
            + ('; '.join(b.name for b in hit_dirs)
               or '一个都没有(该档案没装任何扩展!)'))
    seen_ids = set()
    for base in hit_dirs:
        for idir in sorted((base / 'Extensions').iterdir()):
            if not idir.is_dir() or idir.name in _SNIFFER_SKIP_IDS:
                continue
            if idir.name in seen_ids:
                continue
            vers = sorted((v for v in idir.iterdir() if v.is_dir()),
                          key=lambda p: p.name)
            if not vers:
                continue
            vdir = vers[-1]
            try:
                m = json.loads((vdir / 'manifest.json').read_text(
                    encoding='utf-8-sig'))
            except Exception as e:
                if log:
                    log('info', f'[插件桥] {idir.name[:12]}… manifest '
                                f'读取失败: {e}')
                continue
            perms = set(m.get('permissions') or [])
            perms |= set(m.get('host_permissions') or [])
            need = {'webRequest', 'webRequestBlocking',
                    'declarativeNetRequest',
                    'declarativeNetRequestWithHostAccess'}
            name = m.get('name') or ''
            shown = name[:20] or idir.name[:12] + '…'
            if not (perms & need):
                if log:
                    log('info', f'[插件桥] {shown} 无嗅探类权限 → 跳过')
                continue
            if '__MSG_' not in name and re.search(
                    r'ublock|adblock|ad ?block|adguard|ghostery|privacy',
                    name, re.I):
                if log:
                    log('info', f'[插件桥] {shown} 是拦截类扩展 → 跳过')
                continue
            cands = [m.get('options_page'),
                     (m.get('options_ui') or {}).get('page'),
                     (m.get('action') or {}).get('default_popup'),
                     (m.get('browser_action') or {}).get('default_popup')]
            page = next((c for c in cands if c and (vdir / c).exists()),
                        None)
            if not page:
                if log:
                    log('info', f'[插件桥] {shown} 无可用页面(候选: '
                                f'{cands}) → 跳过')
                continue
            seen_ids.add(idir.name)
            if log:
                log('info', f'[插件桥] 发现嗅探扩展: {shown} '
                            f'({idir.name[:12]}…/{page}) @ {base.name}')
            out.append((idir.name, page, name[:24]))
    return out


'''

NEW_BRIDGE = '''    _ext = {'tabs': []}
    if not attached and not used_temp_profile:
        _bridge_prof = _data_dir() / prof_name
        try:
            _sn = _sniffer_exts(_bridge_prof, log)      # v6.0.2: 全程日志
        except Exception as _e:
            _sn = []
            log('warn', f'[插件桥] 扩展枚举异常: {_e!r}')
        if not _sn:
            log('info', '[插件桥] 未发现嗅探扩展 — 跳过'
                        '(装猫抓等嗅探插件后重试)')
        else:
            try:
                drv.set_script_timeout(8)
            except Exception:
                pass
            for _eid, _pg, _nm in _sn:
                _tid = None
                try:
                    _tid = drv.execute_cdp_cmd(
                        'Target.createTarget',
                        {'url': f'chrome-extension://{_eid}/{_pg}',
                         'newWindow': False}).get('targetId')
                except Exception as _e:
                    log('warn', f'[插件桥] 开 {_nm} 桥页失败: {_e!r}')
                    continue
                _wh = None
                _t0b = time.time()     # v6.0.2: 等句柄出现(修竞态)
                while time.time() - _t0b < 3 and not _wh:
                    try:
                        for _h in drv.window_handles:
                            if _h not in baseline:
                                _wh = _h
                                break
                    except Exception:
                        pass
                    if not _wh:
                        time.sleep(0.25)
                if _wh:
                    _ext['tabs'].append((_tid, _wh, _nm))
                    try:               # 窗口守卫/弹窗清理别关桥页
                        baseline.add(_wh)
                    except Exception:
                        pass
                    log('info', f'[插件桥] 桥页已开: {_nm}')
                else:
                    log('warn', f'[插件桥] {_nm} 页已创建但 3s 内'
                                '拿不到句柄 — 本轮不轮询该页')
            if _ext['tabs']:
                log('ok', '插件嗅探桥就绪: '
                    + '、'.join(n for _t, _w, n in _ext['tabs'])
                    + f' — 轮询 {len(_ext["tabs"])} 个桥页')


'''

DOC_OLD = '\nv5.8.1:\n'
DOC_NEW = ('\nv6.0.2: 插件桥诊断强化(全程日志+全Profile子目录扫描+句柄竞态修复)\n'
           'v5.8.1:\n')


def main():
    if not SRC.exists():
        die('找不到 ' + str(SRC))
    raw = SRC.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    crlf = '\r\n' in text
    if crlf:
        text = text.replace('\r\n', '\n')

    if '检查档案' in text:
        print('[i] v6.0.2 已打, 无需重复。')
        return
    if '_sniffer_exts' not in text:
        die('未检测到 v6.0.0(_sniffer_exts) — 请先运行 patch_v600.py')

    text = replace_span(text, 'def _sniffer_exts(profile_dir):',
                        'def browser_auto_extract(page_url, log, '
                        'show_browser=False, chrome_port=None,',
                        NEW_FN, '① 枚举函数: 全日志+多Profile扫描')
    text = replace_span(text, "    _ext = {'tabs': []}",
                        '    def drv_current_url():',
                        NEW_BRIDGE, '② 桥初始化: 喇叭化+竞态修复')
    text = replace_once(text, DOC_OLD, DOC_NEW, '③ 文件头更新日志')

    text, n1 = re.subn(r'(m3u8gui\.py v)6\.0\.[01]', r'\g<1>6.0.2',
                       text, count=1)
    text, n2 = re.subn(r"(__version__ = ')6\.0\.[01]'", r"\g<1>6.0.2'",
                       text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败(应为 6.0.0 或 6.0.1)')
    print('[OK] ④ 版本号 → 6.0.2')

    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'语法校验失败: {e} — 未改动')
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
    print(f'[OK] v6.0.2 完成(备份 → {bak.name})')


def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        die(f'{name}: 锚点匹配 {n} 处')
    print(f'[OK] {name}')
    return text.replace(old, new, 1)


if __name__ == '__main__':
    main()