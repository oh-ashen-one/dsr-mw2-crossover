// Original, external window controls. No injection, game memory or input API.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <cwchar>

namespace {
struct Target { HWND window{}; DWORD pid{}; unsigned count{}; };
bool private_image(DWORD pid) {
    HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);
    if(!process)return false;
    wchar_t path[1024]{}; DWORD size=1024;
    bool ok=QueryFullProcessImageNameW(process,0,path,&size) &&
        (!_wcsicmp(path,L"C:\\Games\\DSR-MW2\\DarkSoulsRemastered.exe") ||
         !_wcsicmp(path,L"C:\\Program Files (x86)\\Steam\\steamapps\\common\\DARK SOULS REMASTERED\\DarkSoulsRemastered.exe"));
    CloseHandle(process); return ok;
}
BOOL CALLBACK find_window(HWND window,LPARAM parameter) {
    if(!IsWindowVisible(window)||GetWindow(window,GW_OWNER))return TRUE;
    wchar_t title[128]{}; GetWindowTextW(window,title,128);
    if(!wcsstr(title,L"DARK SOULS")||!wcsstr(title,L"REMASTERED"))return TRUE;
    DWORD pid=0; GetWindowThreadProcessId(window,&pid);
    if(private_image(pid)) {
        auto& target=*reinterpret_cast<Target*>(parameter);
        target.window=window; target.pid=pid; ++target.count;
    }
    return TRUE;
}
bool owned(const Target& target,HANDLE process) {
    DWORD pid=0; GetWindowThreadProcessId(target.window,&pid);
    return pid==target.pid && IsWindow(target.window) && WaitForSingleObject(process,0)==WAIT_TIMEOUT;
}
bool resizable(HWND window) {
    const LONG_PTR before=GetWindowLongPtrW(window,GWL_STYLE);
    const LONG_PTR after=(before|WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX)&~static_cast<LONG_PTR>(WS_POPUP);
    SetLastError(0);
    if(!SetWindowLongPtrW(window,GWL_STYLE,after)&&GetLastError())return false;
    if(!SetWindowPos(window,nullptr,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED|SWP_ASYNCWINDOWPOS)) {
        SetWindowLongPtrW(window,GWL_STYLE,before);return false;
    }
    return (GetWindowLongPtrW(window,GWL_STYLE)&WS_THICKFRAME)!=0;
}
bool resize(HWND window,int width,int height) {
    MONITORINFO monitor{}; monitor.cbSize=sizeof(monitor);
    if(!GetMonitorInfoW(MonitorFromWindow(window,MONITOR_DEFAULTTONEAREST),&monitor))return false;
    RECT border{0,0,0,0};
    if(!AdjustWindowRectEx(&border,static_cast<DWORD>(GetWindowLongPtrW(window,GWL_STYLE)),FALSE,
            static_cast<DWORD>(GetWindowLongPtrW(window,GWL_EXSTYLE))))return false;
    const int extra_w=border.right-border.left,extra_h=border.bottom-border.top;
    const int avail_w=monitor.rcWork.right-monitor.rcWork.left-64-extra_w;
    const int avail_h=monitor.rcWork.bottom-monitor.rcWork.top-64-extra_h;
    if(avail_w<640||avail_h<360)return false;
    const double scale=std::min({1.0,static_cast<double>(avail_w)/width,static_cast<double>(avail_h)/height});
    width=static_cast<int>(width*scale);height=static_cast<int>(height*scale);
    const int outer_w=width+extra_w,outer_h=height+extra_h;
    const int x=monitor.rcWork.left+(monitor.rcWork.right-monitor.rcWork.left-outer_w)/2;
    const int y=monitor.rcWork.top+(monitor.rcWork.bottom-monitor.rcWork.top-outer_h)/2;
    bool ok=SetWindowPos(window,nullptr,x,y,outer_w,outer_h,SWP_NOZORDER|SWP_NOACTIVATE|SWP_ASYNCWINDOWPOS);
    std::printf("{\"event\":\"resize_requested\",\"width\":%d,\"height\":%d,\"accepted\":%s}\n",width,height,ok?"true":"false");
    std::fflush(stdout);return ok;
}
int self_test() {
    // Hidden standard window only: no game, render device, focus, or input.
    HWND window=CreateWindowExW(0,L"STATIC",L"DSR window-controls hidden fixture",WS_CAPTION,0,0,640,360,
                              nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    if(!window)return 80;
    bool ok=resizable(window)&&resize(window,1280,720)&&!IsWindowVisible(window);
    RECT client{}; GetClientRect(window,&client);
    ok=ok&&client.right>0&&client.bottom>0;
    DestroyWindow(window);
    std::printf("{\"hidden_window_fixture\":%s,\"game_launched\":false}\n",ok?"true":"false");
    return ok?0:81;
}
}
int main(int argc,char** argv) {
    if(argc!=2)return 64;
    if(!std::strcmp(argv[1],"--self-test"))return self_test();
    if(std::strcmp(argv[1],"--watch"))return 64;
    HANDLE single=CreateMutexW(nullptr,TRUE,L"Local\\DSRMW2WindowControls");
    if(!single||GetLastError()==ERROR_ALREADY_EXISTS){if(single)CloseHandle(single);return 65;}
    Target target{};
    for(unsigned attempt=0;attempt<120;++attempt) {
        target={};EnumWindows(find_window,reinterpret_cast<LPARAM>(&target));
        if(target.count)break;
        Sleep(500);
    }
    if(target.count!=1){CloseHandle(single);return 66;}
    HANDLE process=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,target.pid);
    if(!process||!owned(target,process)||!private_image(target.pid)||!resizable(target.window)) {
        if(process)CloseHandle(process);
        CloseHandle(single);return 67;
    }
    std::printf("{\"event\":\"resizable_style_applied\",\"windows_pid\":%lu,\"gameplay_input\":false}\n",target.pid);
    std::fflush(stdout);
    bool registered[4]{};
    const UINT keys[4]={'1','2','3','M'};
    // Only observe keys registered to this helper. Never synthesize input.
    // Shortcuts exist only while the verified DSR window is foreground.
    const ULONGLONG deadline=GetTickCount64()+8ULL*60*60*1000;
    while(owned(target,process)&&GetTickCount64()<deadline) {
        const bool foreground=GetForegroundWindow()==target.window;
        for(int i=0;i<4;++i) {
            if(foreground&&!registered[i])registered[i]=RegisterHotKey(nullptr,i+1,MOD_CONTROL|MOD_ALT|MOD_NOREPEAT,keys[i])!=0;
            else if(!foreground&&registered[i]){UnregisterHotKey(nullptr,i+1);registered[i]=false;}
        }
        MSG message{};
        while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)) {
            if(message.message!=WM_HOTKEY||GetForegroundWindow()!=target.window||!owned(target,process))continue;
            if(message.wParam==4) {
                // Minimizing lets the game/Wine release its own mouse capture.
                // No cross-process ClipCursor call or cursor warping is used.
                ShowWindowAsync(target.window,SW_MINIMIZE);
                std::puts("{\"event\":\"owner_requested_minimize\"}");std::fflush(stdout);
            } else if(message.wParam>=1&&message.wParam<=3) {
                const int widths[3]={1280,1600,1920},heights[3]={720,900,1080};
                resize(target.window,widths[message.wParam-1],heights[message.wParam-1]);
            }
        }
        Sleep(100);
    }
    for(int i=0;i<4;++i)if(registered[i])UnregisterHotKey(nullptr,i+1);
    CloseHandle(process);ReleaseMutex(single);CloseHandle(single);return 0;
}
