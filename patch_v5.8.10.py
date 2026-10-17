#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5810.py — m3u8gui.py → v5.8.10 (浏览器自愈链补漏)
  ① 启动重试链认不出 "renderer/disconnected" 断连 → 7秒硬失败
  ② 会话中途 InvalidSessionId(空消息)分类走错 + 无重启重试
修复:
  ① 启动重试条件加入 renderer / disconnected
  ② 中途失效 → 清残留 → 自动重启浏览器再试一次(含盾牌分支)
  ③ 异常分类用 str(e)+类名, 空消息也能识别
用法: python patch_v5810.py
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


COND_OLD = r'''            if not ('DevToolsActivePort' in es or 'crashed' in es
                    or 'InvalidSessionId' in es or 'SessionNotCreated' in es
                    or 'target frame detached' in es.lower()):
'''

COND_NEW = r'''            if not ('DevToolsActivePort' in es or 'crashed' in es
                    or 'InvalidSessionId' in es or 'SessionNotCreated' in es
                    or 'target frame detached' in es.lower()
                    or 'renderer' in es.lower()
                    or 'disconnected' in es.lower()):
'''

EXC_OLD = r'''            except Exception as e:
                estr = str(e)
                if 'InvalidSessionId' in estr or 'SessionNotCreated' in estr:
                    log('err', f'浏览器会话异常(环境问题, 不记忆失败): '
                               f'{estr[:100]}')
                else:
                    log('err', f'浏览器抓取失败: {e!r}')
'''

EXC_NEW = r'''            except Exception as e:
                estr = str(e) + ' ' + type(e).__name__
                if not ('InvalidSessionId' in estr
                        or 'SessionNotCreated' in estr
                        or 'renderer' in estr.lower()
                        or 'disconnected' in estr.lower()):
                    log('err', f'浏览器抓取失败: {e!r}')
                else:
                    # v5.8.10: 会话中途失效(残留进程/崩溃) →
                    # 清残留 → 重启浏览器自动再试一次
                    log('warn', '浏览器会话中途失效 → 清理残留进程后'
                                '重启浏览器再试一次...')
                    try:
                        _kill_profile_zombies(
                            None, prof=('edge_profile' if browser == 'edge'
                                        else 'chrome_profile'))
                    except Exception:
                        pass
                    time.sleep(3)
                    try:
                        res = browser_auto_extract(page, log, show, port,
                                                   proxy, browser=browser)
                        if res:
                            _clear_fail(page, 'browser')
                            media, referer, cookie, ua, title = res
                            got = {'url': media, 'referer': referer or page,
                                   'cookie': cookie or '', 'ua': ua or '',
                                   'title': title or '', 'headers': {},
                                   'page': page}
                        elif dom:
                            _record_fail(page, 'browser')
                            log('info', f'{dom}: 浏览器抓取未找到, '
                                        '已记录(7天内跳过)')
                    except ShieldBlockedError as e2:
                        if dom:
                            _record_fail(page, 'browser')
                            _mark_shield(page)
                        log('err', f'{e2}\n→ 该站盾牌拦无头模式。到「设置」'
                                   '里把抓取模式换成「可见窗口」(或「接管」)'
                                   '后重试。')
                    except Exception as e2:
                        log('err', f'重启浏览器后仍失败: {e2!r}')
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '重启浏览器后仍失败' in text:
        print('v5.8.10 自愈补丁已存在, 无需重复打。')
        return
    if "'DevToolsActivePort' in es" not in text:
        die('未找到启动重试链 — 请确认是本系列的 m3u8gui.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.10', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.10'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.10')

    text = replace_once(text, COND_OLD, COND_NEW,
                        '② 启动重试链认 renderer/disconnected')
    text = replace_once(text, EXC_OLD, EXC_NEW,
                        '③ 中途失效自动重启重试')

    try:
        compile(text, str(SRC), 'exec')
    except SyntaxError as e:
        die(f'补丁后语法校验失败: {e} — 原文件未改动')

    bak = SRC.with_name(SRC.name + '.bak')
    k = 1
    while bak.exists():
        k += 1
        bak = SRC.with_name(f'{SRC.name}.bak{k}')
    shutil.copy2(SRC, bak)
    SRC.write_text(text, encoding='utf-8')
    print()
    print(f'[OK] 原文件已备份 → {bak.name}')
    print('[OK] m3u8gui.py 已升级到 v5.8.10 (自愈链补漏)')


if __name__ == '__main__':
    main()