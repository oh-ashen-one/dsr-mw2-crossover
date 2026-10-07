"""Bounded input only for the explicitly authorized disposable validation bank."""
import argparse
import ctypes
import time
from dsr_mw2.launch import game_processes
from tools.inspect_dsr_window import windows
from dsr_mw2.validation_session import require_active

KEYS={'w':13,'a':0,'s':1,'d':2,'e':14,'q':12,'r':15,'f':3,'g':5,'b':11,'x':7,'enter':36,'escape':53,
      'space':49,'tab':48,'left':123,'right':124,'down':125,'up':126,'shift':56,'ctrl':59}


def foreground_pid():
    carbon=ctypes.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
    class Serial(ctypes.Structure):
        _fields_=[('high',ctypes.c_uint32),('low',ctypes.c_uint32)]
    carbon.GetFrontProcess.argtypes=[ctypes.POINTER(Serial)]
    carbon.GetFrontProcess.restype=ctypes.c_int32
    carbon.GetProcessPID.argtypes=[ctypes.POINTER(Serial),ctypes.POINTER(ctypes.c_int32)]
    carbon.GetProcessPID.restype=ctypes.c_int32
    serial=Serial();pid=ctypes.c_int32()
    if carbon.GetFrontProcess(ctypes.byref(serial)) or carbon.GetProcessPID(ctypes.byref(serial),ctypes.byref(pid)):
        raise ValueError('Cannot verify actual foreground process')
    return pid.value


def main():
    require_active()  # Refuses the owner's ordinary stock/M9 sessions.
    _historical_input_main()


def _historical_input_main():
    """Own-game, foreground/window checks still apply after save isolation."""
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind',choices=('focus','look','key','test-name','reload-interrupt','five-shots','aim-five-shots','aim-shot','aim-move','aim-move-fire','aim-move-reload','aim-reload','aim-reload-interrupt','left-click','right-click'))
    p.add_argument('--key',choices=KEYS)
    p.add_argument('--x',type=float);p.add_argument('--y',type=float)
    p.add_argument('--keep-pointer',action='store_true',help='Use current cursor position without generating relative camera motion')
    p.add_argument('--seconds',type=float,default=.10)
    p.add_argument('--dx',type=int,default=0);p.add_argument('--dy',type=int,default=0)
    a=p.parse_args()
    if not .03<=a.seconds<=3:raise ValueError('Input must be bounded to .03..3 seconds')
    if abs(a.dx)>200 or abs(a.dy)>100 or (a.kind!='look' and (a.dx or a.dy)):
        raise ValueError('Only bounded explicit look deltas are supported')
    if a.kind in ('aim-move','aim-move-fire','aim-move-reload') and a.key not in (None,'w','a','s','d'):
        raise ValueError('Aimed movement requires one of WASD')
    games=game_processes()
    if len(games)!=1:raise ValueError('Expected exactly one task-owned native game')
    pid=games[0]
    # Layer-0 app windows only: system overlays such as the Dock's transparent
    # full-screen layer-20 window do not intercept clicks over the game.
    visible=[w for w in windows() if w.get('kCGWindowAlpha',0)>0 and w.get('kCGWindowLayer',0)==0 and w.get('kCGWindowBounds',{}).get('Width',0)>100]
    target=next(w for w in visible if w.get('kCGWindowOwnerPID')==pid and w.get('kCGWindowName')=='DARK SOULS™: REMASTERED')
    b=target['kCGWindowBounds']
    cg=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cg.CGPreflightPostEventAccess.restype=ctypes.c_bool
    if not cg.CGPreflightPostEventAccess():raise ValueError('Existing input permission absent; no prompt requested')
    class Point(ctypes.Structure):_fields_=[('x',ctypes.c_double),('y',ctypes.c_double)]
    cg.CGEventCreateMouseEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint32,Point,ctypes.c_uint32]
    cg.CGEventCreateMouseEvent.restype=ctypes.c_void_p
    cg.CGEventCreateKeyboardEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint16,ctypes.c_bool]
    cg.CGEventCreateKeyboardEvent.restype=ctypes.c_void_p
    cg.CGEventPost.argtypes=[ctypes.c_uint32,ctypes.c_void_p];cf.CFRelease.argtypes=[ctypes.c_void_p]
    cg.CGEventPostToPid.argtypes=[ctypes.c_int32,ctypes.c_void_p]
    cg.CGEventCreate.argtypes=[ctypes.c_void_p];cg.CGEventCreate.restype=ctypes.c_void_p
    cg.CGEventGetLocation.argtypes=[ctypes.c_void_p];cg.CGEventGetLocation.restype=Point
    def post(e,targeted=False):
        if not e:raise ValueError('Native input event allocation failed')
        if targeted:cg.CGEventPostToPid(pid,e)
        else:cg.CGEventPost(0,e)
        cf.CFRelease(e)
    if a.kind=='look':
        if foreground_pid()!=pid or a.x is not None or a.y is not None or a.keep_pointer or a.seconds!=.10:
            raise ValueError('Look requires owned foreground and explicit bounded deltas only')
        event=cg.CGEventCreate(None)
        if not event:raise ValueError('Cannot read cursor for bounded look')
        try:origin=cg.CGEventGetLocation(event)
        finally:cf.CFRelease(event)
        x,y=origin.x+a.dx,origin.y+a.dy
        if not b['X']<=x<b['X']+b['Width'] or not b['Y']<=y<b['Y']+b['Height']:
            raise ValueError('Look would leave the owned window')
        hits=[w for w in visible if (r:=w['kCGWindowBounds'])['X']<=x<r['X']+r['Width'] and r['Y']<=y<r['Y']+r['Height']]
        if not hits or hits[0]['kCGWindowOwnerPID']!=pid:raise ValueError('Another window covers look destination')
        # CoreGraphics SDK CGEventTypes.h: mouse delta X/Y are fields4/5.
        cg.CGEventSetIntegerValueField.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64]
        event=cg.CGEventCreateMouseEvent(None,5,Point(x,y),0)
        if not event:raise ValueError('Cannot allocate bounded look event')
        cg.CGEventSetIntegerValueField(event,4,a.dx);cg.CGEventSetIntegerValueField(event,5,a.dy)
        post(event);time.sleep(.10)
        print({'owned_game_pid':pid,'kind':'look','dx':a.dx,'dy':a.dy});return
    if a.kind in ('key','test-name','reload-interrupt'):
        if foreground_pid()!=pid or (a.kind=='key' and a.key is None):
            raise ValueError('Native game must be foreground before keyboard input')
        # This fixed non-secret character name cannot paste credentials/commands.
        sequence=([KEYS[a.key]] if a.kind=='key' else [KEYS['r'],KEYS['space']]
                  if a.kind=='reload-interrupt' else [2,1,15,17,14,1,17]) # dsrtest
        if a.kind=='reload-interrupt' and a.seconds!=.10:
            raise ValueError('Reload interruption has fixed bounded timing')
        for index,code in enumerate(sequence):
            if foreground_pid()!=pid:raise ValueError('Foreground ownership changed')
            post(cg.CGEventCreateKeyboardEvent(None,code,True),True)
            try:time.sleep(a.seconds)
            finally:post(cg.CGEventCreateKeyboardEvent(None,code,False),True)
            time.sleep(.25 if a.kind=='reload-interrupt' and index==0 else .05)
    else:
        if a.kind=='focus' and target.get('kCGWindowLayer')!=0:
            raise ValueError('Title-bar focus is only valid for the windowed native game')
        x,y=(200.,10.) if a.kind=='focus' else (a.x,a.y)
        if a.keep_pointer:
            if a.kind=='focus' or a.x is not None or a.y is not None or foreground_pid()!=pid:
                raise ValueError('Keep-pointer requires owned foreground mouse action and no coordinates')
            event=cg.CGEventCreate(None)
            if not event:raise ValueError('Cannot read current cursor location')
            try:point=cg.CGEventGetLocation(event)
            finally:cf.CFRelease(event)
            x,y=point.x-b['X'],point.y-b['Y']
        if x is None or y is None or not 0<=x<b['Width'] or not 0<=y<b['Height']:
            raise ValueError('Click must be within the observed native window')
        x+=b['X'];y+=b['Y']
        hits=[w for w in visible if (r:=w['kCGWindowBounds'])['X']<=x<r['X']+r['Width'] and r['Y']<=y<r['Y']+r['Height']]
        if not hits or hits[0]['kCGWindowOwnerPID']!=pid:raise ValueError('Another window covers the click')
        button=1 if a.kind=='right-click' else 0
        down,up=(3,4) if button else (1,2)
        if not a.keep_pointer:post(cg.CGEventCreateMouseEvent(None,5,Point(x,y),button));time.sleep(.05)
        sequence=a.kind in ('five-shots','aim-five-shots')
        scenario=a.kind in ('aim-shot','aim-move','aim-move-fire','aim-move-reload','aim-reload','aim-reload-interrupt')
        if (sequence or scenario) and a.seconds!=.10:
            raise ValueError('Scenario tests have fixed bounded timing')
        aiming=a.kind=='aim-five-shots' or scenario
        def key(code,seconds):
            if foreground_pid()!=pid:raise ValueError('Foreground ownership changed during aim scenario')
            post(cg.CGEventCreateKeyboardEvent(None,KEYS[code],True),True)
            try:time.sleep(seconds)
            finally:post(cg.CGEventCreateKeyboardEvent(None,KEYS[code],False),True)
        try:
            if aiming:
                if foreground_pid()!=pid:raise ValueError('Foreground ownership changed before aim')
                post(cg.CGEventCreateMouseEvent(None,3,Point(x,y),1));time.sleep(.35)
            if scenario:
                if a.kind=='aim-shot':
                    # One stationary shot, keeping aim for the bounded recoil
                    # return observation. No invented shot or native writer.
                    time.sleep(.65)
                    if foreground_pid()!=pid:raise ValueError('Foreground ownership changed before stationary shot')
                    post(cg.CGEventCreateMouseEvent(None,1,Point(x,y),0))
                    try:time.sleep(.1)
                    finally:post(cg.CGEventCreateMouseEvent(None,2,Point(x,y),0))
                    time.sleep(2.5)
                elif a.kind=='aim-move':key(a.key or 'w',.4);time.sleep(1.)
                elif a.kind=='aim-move-fire':
                    if foreground_pid()!=pid:raise ValueError('Foreground ownership changed before moving shot')
                    code=KEYS[a.key or 'w']
                    post(cg.CGEventCreateKeyboardEvent(None,code,True),True)
                    try:
                        time.sleep(.2)
                        if foreground_pid()!=pid:raise ValueError('Foreground ownership changed during moving shot')
                        post(cg.CGEventCreateMouseEvent(None,1,Point(x,y),0))
                        try:time.sleep(.1)
                        finally:post(cg.CGEventCreateMouseEvent(None,2,Point(x,y),0))
                        time.sleep(.4)
                    finally:post(cg.CGEventCreateKeyboardEvent(None,code,False),True)
                    time.sleep(.7)
                elif a.kind=='aim-move-reload':
                    if foreground_pid()!=pid:raise ValueError('Foreground ownership changed before moving reload')
                    code=KEYS[a.key or 's']
                    post(cg.CGEventCreateKeyboardEvent(None,code,True),True)
                    try:
                        time.sleep(.2);key('r',.1);time.sleep(1.95)
                    finally:post(cg.CGEventCreateKeyboardEvent(None,code,False),True)
                    time.sleep(.7)
                else:
                    key('r',.1)
                    if a.kind=='aim-reload-interrupt':time.sleep(.25);key('space',.1);time.sleep(.7)
                    else:time.sleep(1.95)
            for _ in range(0 if scenario else 5 if sequence else 1):
                if sequence and foreground_pid()!=pid:
                    raise ValueError('Foreground ownership changed during shot sequence')
                post(cg.CGEventCreateMouseEvent(None,down,Point(x,y),button))
                try:time.sleep(a.seconds)
                finally:post(cg.CGEventCreateMouseEvent(None,up,Point(x,y),button))
                if sequence:time.sleep(.05)
            if aiming:time.sleep(.5)
        finally:
            if aiming:post(cg.CGEventCreateMouseEvent(None,4,Point(x,y),1))
    print({'owned_game_pid':pid,'kind':a.kind,'seconds':a.seconds})


if __name__=='__main__':main()
