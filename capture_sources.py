"""List visible Windows capture targets without injecting into any process."""
import ctypes
from ctypes import wintypes
import os


def windows():
    if os.name!='nt':return []
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    rows=[]
    @callback_type
    def visit(handle,unused):
        if not user.IsWindowVisible(handle):return True
        title=ctypes.create_unicode_buffer(1024);user.GetWindowTextW(handle,title,len(title))
        rect=wintypes.RECT();user.GetClientRect(handle,ctypes.byref(rect))
        if not title.value or rect.right<100 or rect.bottom<100:return True
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        process=kernel.OpenProcess(0x1000,False,pid.value)
        if not process:return True
        try:
            name=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(name))
            if not kernel.QueryFullProcessImageNameW(process,0,name,ctypes.byref(size)):return True
            executable=os.path.basename(name.value)
        finally:kernel.CloseHandle(process)
        rows.append({'handle':int(handle),'pid':pid.value,'process':executable,'title':title.value})
        return True
    user.EnumWindows(visit,0)
    return sorted(rows,key=lambda row:(row['process'].lower(),row['title'].lower()))


def select(body,available=None):
    mode=body.get('mode')
    if mode not in ('paste','obs','window'):raise ValueError('Choose Paste text, OBS projector, or Game window.')
    result={'capture_mode':mode,'window_handle':0,'window_pid':0,'window_title':''}
    if mode=='window':
        rows=windows() if available is None else available
        row=next((row for row in rows if row['handle']==body.get('handle') and row['pid']==body.get('pid')),None)
        if row is None:raise ValueError('That window closed. Refresh the list and select it again.')
        result.update(window_handle=row['handle'],window_pid=row['pid'],window_title=row['title'])
    return result
