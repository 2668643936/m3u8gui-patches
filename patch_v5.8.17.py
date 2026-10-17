#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5817.py — m3u8gui.py → v5.8.17 (输出目录持久化 + 驱动诊断)
  ① last_outdir 持久化: 下载/缩略图完成时记住真实输出目录(跨会话)
  ② 启动时"保存为"默认指向上次输出目录 → 不再随启动方式漂移
  ③ 「最近输出」无本会话记录时, 打开历史输出目录
  ④ 启动浏览器时打印实际使用的驱动路径(打包版排障用)
用法: python patch_v5817.py
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


A_OLD = r'''        self.out_var = tk.StringVar(value='video.mp4')
'''
A_NEW = r'''        _lod = s.get('last_outdir')                 # v5.8.17
        self.out_var = tk.StringVar(
            value=(str(Path(_lod) / 'video.mp4') if _lod else 'video.mp4'))
'''

B_OLD = r'''    def _open_last(self):
        p = getattr(self, '_last_output', None)
        if not p or not Path(p).exists():
            messagebox.showinfo('提示', '本次运行还没有完成的下载。')
            return
        d = Path(p).resolve().parent
'''
B_NEW = r'''    def _remember_dir(self, d):
        """v5.8.17: 记住最近输出目录(持久化, 跨会话)"""
        try:
            d = str(Path(d).resolve())
            if d and self.settings.get('last_outdir') != d:
                self.settings['last_outdir'] = d
                save_settings(self.settings)
        except Exception:
            pass

    def _open_last(self):
        p = getattr(self, '_last_output', None)
        d = None
        if p and Path(p).exists():
            d = Path(p).resolve().parent
        elif self.settings.get('last_outdir') \
                and Path(self.settings['last_outdir']).is_dir():
            d = Path(self.settings['last_outdir'])
        if d is None:
            messagebox.showinfo('提示', '本会话没有完成的下载, 也没有'
                               '历史输出目录记录。')
            return
'''

C_OLD = r'''            if ok and '下载完成: ' in text:
                try:
                    self._last_output = text.split('下载完成: ', 1)[1].strip()
                except Exception:
                    pass
'''
C_NEW = r'''            if ok and '下载完成: ' in text:
                try:
                    self._last_output = text.split('下载完成: ', 1)[1].strip()
                    self._remember_dir(str(Path(self._last_output).parent))
                except Exception:
                    pass
'''

D_OLD = r'''                ok = online_thumbs(got, name_hint, outdir, tc, logM,
                                   self.msgq, stop, proxy, fw=fw,
                                   fixdate=fixdate)
                logM('缩略图完成' if ok else '缩略图未完成', 'ok' if ok else 'warn')
'''
D_NEW = r'''                ok = online_thumbs(got, name_hint, outdir, tc, logM,
                                   self.msgq, stop, proxy, fw=fw,
                                   fixdate=fixdate)
                if ok:
                    self._remember_dir(outdir)      # v5.8.17
                logM('缩略图完成' if ok else '缩略图未完成', 'ok' if ok else 'warn')
'''

E_OLD = r'''                    for u in fails:
                        logM(f'  {"[网页]" if _is_page_url(u) else "[直链]"} '
                             f'{u[:95]}', 'err')
                self.msgq.put(('thumbs_done',))
'''
E_NEW = r'''                    for u in fails:
                        logM(f'  {"[网页]" if _is_page_url(u) else "[直链]"} '
                             f'{u[:95]}', 'err')
                self._remember_dir(outdir)          # v5.8.17
                self.msgq.put(('thumbs_done',))
'''

F_OLD = r'''    for attempt in range(4):
        try:
            drv = _mk_driver(o)
            break
'''
F_NEW = r'''    for attempt in range(4):
        try:
            drv = _mk_driver(o)
            try:
                log('info', f'[诊断] 驱动: {drv.service.path}')
            except Exception:
                pass
            break
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'last_outdir' in text:
        print('v5.8.17 输出记忆补丁已存在, 无需重复打。')
        return

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.17', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.17'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.17')

    text = replace_once(text, A_OLD, A_NEW, '② 启动默认输出目录')
    text = replace_once(text, B_OLD, B_NEW, '③ _remember_dir+最近输出')
    text = replace_once(text, C_OLD, C_NEW, '④ 下载完成记目录')
    text = replace_once(text, D_OLD, D_NEW, '⑤ 单张缩略图记目录')
    text = replace_once(text, E_OLD, E_NEW, '⑥ 批量缩略图记目录')
    text = replace_once(text, F_OLD, F_NEW, '⑦ 驱动路径诊断日志')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.17 (输出目录记忆+驱动诊断)')


if __name__ == '__main__':
    main()