#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5826.py — m3u8gui.py → v5.8.26 (证书错误站全链路放行)
现象: 站点证书不受信(ERR_CERT_AUTHORITY_INVALID 等) → 浏览器停在
     "您的连接不是私密连接"墙; HTTP 层(静态挖掘/下载)TLS 握手抛错。
修复:
  ① 浏览器: --ignore-certificate-errors (拦截页不再出现)
  ② HTTP: http_get / sniff / 下载会话 / 本地代理 / yt-dlp 全部
     verify=False / --no-check-certificates
  ③ 压掉 requests 的 InsecureRequestWarning 噪音
说明: verify=False = 放弃中间人检测, 专用抓取档案场景可接受。
用法: python patch_v5826.py
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


A1_OLD = """try:
    import requests
except ImportError:
    requests = None
"""
A1_NEW = """try:
    import requests
except ImportError:
    requests = None
try:                                    # v5.8.26: verify=False 的告警噪音
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass
"""

A2_OLD = """def http_get(url, headers, timeout=20, proxy=None, stream=False):
    if HAS_CFFI:
        return cffi_requests.get(url, headers=headers, timeout=timeout,
                                 impersonate='chrome', stream=stream,
                                 proxies=_proxies_for(proxy))
    return requests.get(url, headers=headers, timeout=timeout, stream=stream,
                        proxies=_proxies_for(proxy))
"""
A2_NEW = """def http_get(url, headers, timeout=20, proxy=None, stream=False):
    if HAS_CFFI:
        return cffi_requests.get(url, headers=headers, timeout=timeout,
                                 impersonate='chrome', stream=stream,
                                 verify=False, proxies=_proxies_for(proxy))
    return requests.get(url, headers=headers, timeout=timeout, stream=stream,
                        verify=False, proxies=_proxies_for(proxy))
"""

A3_OLD = r'''            if HAS_CFFI:
                r = cffi_requests.get(url, headers=hd, timeout=15,
                                      impersonate='chrome',
                                      proxies=_proxies_for(proxy), stream=True)
            else:
                r = requests.get(url, headers=hd, timeout=15,
                                  proxies=_proxies_for(proxy), stream=True)
'''
A3_NEW = r'''            if HAS_CFFI:
                r = cffi_requests.get(url, headers=hd, timeout=15,
                                      impersonate='chrome', verify=False,
                                      proxies=_proxies_for(proxy), stream=True)
            else:
                r = requests.get(url, headers=hd, timeout=15, verify=False,
                                  proxies=_proxies_for(proxy), stream=True)
'''

A4_OLD = r'''    def _mk_session(self):
        if HAS_CFFI:
            s = cffi_requests.Session(impersonate='chrome')
        else:
            s = requests.Session()
'''
A4_NEW = r'''    def _mk_session(self):
        if HAS_CFFI:
            s = cffi_requests.Session(impersonate='chrome', verify=False)
        else:
            s = requests.Session()
            s.verify = False
'''

A5_OLD = r'''            if HAS_CFFI:
                r = cffi_requests.get(self.UP_URL, headers=hd,
                                      stream=True, timeout=120,
                                      impersonate='chrome',
                                      proxies=_proxies_for(None))
            if r is None or r.status_code >= 400:
                if r is not None:
                    r.close()
                r = requests.get(self.UP_URL, headers=hd, stream=True,
                                 timeout=120, proxies=_proxies_for(None))
'''
A5_NEW = r'''            if HAS_CFFI:
                r = cffi_requests.get(self.UP_URL, headers=hd,
                                      stream=True, timeout=120,
                                      impersonate='chrome', verify=False,
                                      proxies=_proxies_for(None))
            if r is None or r.status_code >= 400:
                if r is not None:
                    r.close()
                r = requests.get(self.UP_URL, headers=hd, stream=True,
                                 verify=False, timeout=120,
                                 proxies=_proxies_for(None))
'''

A6_OLD = "    cmd = [exe, '-J', '--no-playlist', '--skip-download', '-f', 'b']\n"
A6_NEW = ("    cmd = [exe, '-J', '--no-playlist', '--skip-download', '-f', 'b',\n"
          "           '--no-check-certificates']\n")

A7_OLD = "        o.add_argument(f'--user-data-dir={APP_DIR / prof_name}')\n"
A7_NEW = """        o.add_argument(f'--user-data-dir={APP_DIR / prof_name}')
        # v5.8.26: 证书错误站不再弹"您的连接不是私密连接"墙
        o.add_argument('--ignore-certificate-errors')
"""


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if 'ignore-certificate-errors' in text:
        print('v5.8.26 证书补丁已存在, 无需重复打。')
        return

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.26', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.26'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.26')

    text = replace_once(text, A1_OLD, A1_NEW, '② 压掉 TLS 告警噪音')
    text = replace_once(text, A2_OLD, A2_NEW, '③ http_get 放行')
    text = replace_once(text, A3_OLD, A3_NEW, '④ sniff 验证放行')
    text = replace_once(text, A4_OLD, A4_NEW, '⑤ 下载会话放行')
    text = replace_once(text, A5_OLD, A5_NEW, '⑥ 本地代理放行')
    text = replace_once(text, A6_OLD, A6_NEW, '⑦ yt-dlp 放行')
    text = replace_once(text, A7_OLD, A7_NEW, '⑧ 浏览器拦截页放行')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.26 (证书错误站全链路放行)')


if __name__ == '__main__':
    main()