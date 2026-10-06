"""Read/capture only windows belonging to this task's verified native game PID."""
import ctypes
import json
import plistlib
import subprocess
from dsr_mw2.launch import WORKSPACE, game_processes


def windows():
    cg=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cg.CGWindowListCopyWindowInfo.argtypes=[ctypes.c_uint32,ctypes.c_uint32]
    cg.CGWindowListCopyWindowInfo.restype=ctypes.c_void_p
    cf.CFPropertyListCreateData.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_long,ctypes.c_ulong,ctypes.c_void_p]
    cf.CFPropertyListCreateData.restype=ctypes.c_void_p
    cf.CFDataGetLength.argtypes=[ctypes.c_void_p];cf.CFDataGetLength.restype=ctypes.c_long
    cf.CFDataGetBytePtr.argtypes=[ctypes.c_void_p];cf.CFDataGetBytePtr.restype=ctypes.c_void_p
    cf.CFRelease.argtypes=[ctypes.c_void_p]
    array=cg.CGWindowListCopyWindowInfo(1,0)
    try:
        data=cf.CFPropertyListCreateData(None,array,100,0,None)
        try:return plistlib.loads(ctypes.string_at(cf.CFDataGetBytePtr(data),cf.CFDataGetLength(data)))
        finally:cf.CFRelease(data)
    finally:cf.CFRelease(array)


def main():
    cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
    if not cg.CGPreflightScreenCaptureAccess():
        raise RuntimeError('Existing screen capture permission is absent; no prompt requested')
    owned=set(game_processes())
    records=[]
    for w in windows():
        if w.get('kCGWindowOwnerPID') not in owned:continue
        records.append({k:w.get(k) for k in ('kCGWindowOwnerPID','kCGWindowNumber','kCGWindowOwnerName','kCGWindowName','kCGWindowBounds')})
        if w.get('kCGWindowName')=='DARK SOULS™: REMASTERED' and w.get('kCGWindowBounds',{}).get('Width',0)>100:
            path=WORKSPACE/'tooling-local/launch'/('dsr-window-'+str(w['kCGWindowNumber'])+'.png')
            subprocess.run(['/usr/sbin/screencapture','-x','-o','-l',str(w['kCGWindowNumber']),str(path)],check=True,timeout=8)
            records[-1]['capture']=str(path)
    print(json.dumps({'owned_native_pids':sorted(owned),'windows':records},indent=2))


if __name__=='__main__':main()
