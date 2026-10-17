#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5820.py — m3u8gui.py → v5.8.20 (年龄验证 Remember me 自动勾选)
点"我已满18"之前, 先勾选页面上的 Remember me/记住我 复选框 —
验证写入持久 Cookie 存进档案, 下次不再弹年龄门。
用法: python patch_v5820.py
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


JS_NEW = r'''_REMEMBER_JS = r"""
(function(){
  var re=/(remember|记忆|记住|recall|persist|保持)/i;
  var boxes=document.querySelectorAll('input[type=checkbox]');
  var n=0;
  for(var i=0;i<boxes.length;i++){
    var cb=boxes[i];
    if(cb.checked) continue;
    var ctx='';
    try{
      ctx=' '+(cb.id||'')+' '+(cb.name||'')+' '+(cb.className||'')+' '
          +(cb.getAttribute('aria-label')||'')+' ';
      var lb=cb.closest('label');
      if(lb) ctx+=' '+lb.textContent+' ';
      if(cb.id){
        var fl=document.querySelectorAll('label[for="'+cb.id+'"]');
        for(var j=0;j<fl.length;j++) ctx+=' '+fl[j].textContent+' ';
      }
    }catch(x){}
    if(!re.test(ctx)) continue;
    try{ cb.click(); n++; }catch(x){}
  }
  return n;
})()"""

'''

AGE_OLD = r'''    def age_click(drv):
        r = click_first(drv, AGE_XPATHS)
        if r:
            return r
        try:
            return drv.execute_script(_AGE_JS) or None
        except Exception:
            return None
'''

AGE_NEW = r'''    def age_click(drv):
        try:                            # v5.8.20: 先勾 Remember me 再确认
            n = drv.execute_script(_REMEMBER_JS)
            if n:
                log('info', '已勾选 Remember me — 年龄验证将写入档案, '
                            '下次不再弹窗')
        except Exception:
            pass
        r = click_first(drv, AGE_XPATHS)
        if r:
            return r
        try:
            return drv.execute_script(_AGE_JS) or None
        except Exception:
            return None
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_REMEMBER_JS' in text:
        print('v5.8.20 Remember me 补丁已存在, 无需重复打。')
        return
    if '_AGE_JS = r"""' not in text:
        die('未找到 _AGE_JS — 请确认是本系列的 m3u8gui.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.20', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.20'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.20')

    text = text.replace('_AGE_JS = r"""', JS_NEW + '_AGE_JS = r"""', 1)
    print('[OK] ② _REMEMBER_JS 注入脚本')
    text = replace_once(text, AGE_OLD, AGE_NEW, '③ age_click 先勾后点')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.20 (Remember me 自动勾选)')


if __name__ == '__main__':
    main()