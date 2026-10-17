#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v5827.py — m3u8gui.py → v5.8.27 (拖到底式滑块自动完成)
  拖到底式("按住滑块拖至最右"): 检测拖柄+轨道 → 分步拟人拖拽。
  拼图/旋转式: 只检测并提示"换可见窗口人工通过", 绝不自动碰
  (防失败计数触发封锁)。
用法: python patch_v5827.py   (需已打 v5.8.14 — import random)
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


SLIDER_JS = r'''_SLIDER_JS = r"""
(function(){
  var hintRe=/(按住滑块|拖动滑块|拖拽滑块|滑动验证|拖动验证|旋转验证|拖至最右|拖到最右)/;
  var els=document.querySelectorAll('div,span,p,b,section');
  var hint=null,hintTxt='';
  for(var i=0;i<els.length;i++){
    var e=els[i];
    var t=(e.textContent||'').trim();
    if(!t||t.length>80) continue;
    if(!hintRe.test(t)) continue;
    var r=e.getBoundingClientRect();
    if(r.width<80) continue;
    hint=e; hintTxt=t; break;
  }
  if(!hint) return null;
  var scope=hint;
  for(var k=0;k<6&&scope.parentElement;k++){
    scope=scope.parentElement;
    var kids=scope.querySelectorAll('*');
    var best=null;
    for(var j=0;j<kids.length;j++){
      var c=kids[j];
      var cr=c.getBoundingClientRect();
      if(cr.width<25||cr.width>95||cr.height<20||cr.height>95) continue;
      var st; try{ st=getComputedStyle(c);}catch(x){ continue;}
      if(!/grab|move|pointer/i.test(st.cursor||'')) continue;
      best=c; break;
    }
    if(best){
      var br=best.getBoundingClientRect();
      var tr=null;
      var p=best.parentElement;
      for(var m=0;m<4&&p;m++){
        var pr=p.getBoundingClientRect();
        if(pr.width>=140&&pr.height>=25&&pr.height<=130){ tr=pr; break; }
        p=p.parentElement;
      }
      var dist=tr?Math.round(tr.right-(br.left+br.width/2))+4:260;
      return [best,dist,hintTxt.slice(0,40)];
    }
  }
  return [null,0,hintTxt.slice(0,40)];
})()"""

'''

TRY_SLIDER = r'''    def try_slider(drv):
        """v5.8.27: 拖到底式滑块自动完成; 拼图/旋转式只提示不处理"""
        try:
            res = drv.execute_script(_SLIDER_JS)
        except Exception:
            return None
        if not res:
            return None
        handle, dist, hint = res[0], res[1] or 0, str(res[2] or '')
        if not re.search(r'最右|右侧|右端', hint):
            if not getattr(try_slider, '_warned', False):
                try_slider._warned = True
                log('warn', f'检测到滑块验证("{hint[:24]}") — 拼图/旋转式'
                            '不自动处理, 建议换「可见窗口」人工通过一次')
            return None
        if handle is None or dist < 50:
            return None
        try:
            ac = ActionChains(drv)
            ac.move_to_element(handle)
            ac.click_and_hold(handle)
            moved = 0
            while moved < dist:
                step = min(random.randint(18, 45), dist - moved)
                ac.move_by_offset(step, random.randint(-2, 2))
                moved += step
                ac.pause(random.uniform(0.03, 0.09))
            ac.release()
            ac.perform()
        except Exception:
            return None
        time.sleep(1.2)
        try:
            again = drv.execute_script(_SLIDER_JS)
            if again and again[0] is not None:
                return None
        except Exception:
            pass
        return f'拖动{dist}px'

    def age_click(drv):
        try:                            # v5.8.20: 先勾 Remember me 再确认
'''

AGE_HEAD_OLD = r'''    def age_click(drv):
        try:                            # v5.8.20: 先勾 Remember me 再确认
'''
AGE_HEAD_NEW = TRY_SLIDER

ROUND_OLD = r'''                    got = visit_frames(drv, age_click)
                    if got:
                        log('ok', f'已点击年龄确认 ({got})')
'''
ROUND_NEW = r'''                    got = visit_frames(drv, try_slider)
                    if got:
                        log('ok', f'已自动完成滑动验证 ({got})')
                        time.sleep(1.5)
                    got = visit_frames(drv, age_click)
                    if got:
                        log('ok', f'已点击年龄确认 ({got})')
'''

RECLICK_OLD = r'''                            last_click = time.time()
                            c = visit_frames(drv, age_click)
'''
RECLICK_NEW = r'''                            last_click = time.time()
                            c = visit_frames(drv, try_slider)
                            if c:
                                log('ok', f'补试滑动验证 ({c})')
                                time.sleep(1.0)
                            c = visit_frames(drv, age_click)
'''


def main():
    if not SRC.exists():
        die(f'找不到 {SRC} — 请放到 m3u8gui.py 同目录运行')
    text = SRC.read_text(encoding='utf-8-sig')

    if '_SLIDER_JS' in text:
        print('v5.8.27 滑块补丁已存在, 无需重复打。')
        return
    if 'import random' not in text:
        die('未检测到 v5.8.14 的 import random — 请先打 patch_v5814.py')

    text, n1 = re.subn(r'(m3u8gui\.py v)5\.8\.[\d.]+',
                       r'\g<1>5.8.27', text, count=1)
    text, n2 = re.subn(r"(__version__ = ')5\.8\.[\d.]+'",
                       r"\g<1>5.8.27'", text, count=1)
    if n1 != 1 or n2 != 1:
        die('版本号定位失败, 请确认文件版本')
    print('[OK] ① 版本号 → 5.8.27')

    text = text.replace('_AGE_JS = r"""', SLIDER_JS + '_AGE_JS = r"""', 1)
    print('[OK] ② 滑块检测 JS')
    text = replace_once(text, AGE_HEAD_OLD, AGE_HEAD_NEW,
                        '③ try_slider 函数')
    text = replace_once(text, ROUND_OLD, ROUND_NEW, '④ 轮次先试滑块')
    text = replace_once(text, RECLICK_OLD, RECLICK_NEW, '⑤ 周期补试滑块')

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
    print('[OK] m3u8gui.py 已升级到 v5.8.27 (拖到底式滑块自动完成)')


if __name__ == '__main__':
    main()