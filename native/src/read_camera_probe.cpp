// Original single-sample private camera diagnostic, read-only. Reuses the
// existing exact image pin/RemoteReader; no input, hooks or write permission.
#define main unused_equipment_probe_main
#include "read_only_probe.cpp"
#undef main
#include <cmath>
int main(){
    SetPriorityClass(GetCurrentProcess(),BELOW_NORMAL_PRIORITY_CLASS);
    HANDLE list=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(list==INVALID_HANDLE_VALUE)return 65;
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);DWORD pid=0;unsigned count=0;
    for(BOOL ok=Process32FirstW(list,&entry);ok;ok=Process32NextW(list,&entry)){
        if(!_wcsicmp(entry.szExeFile,L"DarkSoulsRemastered.exe")){pid=entry.th32ProcessID;++count;}}
    CloseHandle(list);if(count!=1){std::printf("{\"error\":\"expected_one_private_game\",\"count\":%u}\n",count);return 66;}
    HANDLE game=OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION|SYNCHRONIZE,FALSE,pid);
    if(!game){std::printf("{\"error\":\"readonly_open_failed\",\"code\":%lu}\n",GetLastError());return 67;}
    wchar_t path[1024]{};DWORD length=1024;
    if(!QueryFullProcessImageNameW(game,0,path,&length)||!pinned_image(path)){CloseHandle(game);return 68;}
    HANDLE modules=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid);
    MODULEENTRY32W module{};module.dwSize=sizeof(module);dsr_mw2::Address base=0;
    if(modules!=INVALID_HANDLE_VALUE){
        for(BOOL ok=Module32FirstW(modules,&module);ok;ok=Module32NextW(modules,&module))
            if(!_wcsicmp(module.szModule,L"DarkSoulsRemastered.exe"))base=reinterpret_cast<dsr_mw2::Address>(module.modBaseAddr);
        CloseHandle(modules);}
    RemoteReader reader(game);std::array<unsigned char,7> got{};
    const std::array<unsigned char,7> world{0x48,0x8b,0x05,0x23,0x38,0x4b,0x01};
    if(!base||!reader.get(base,0x7c4626,got)||got!=world){CloseHandle(game);return 69;}

    dsr_mw2::Snapshot s;
    dsr_mw2::Address bullet=0,chr=0,camera=0,vtable=0;
    std::array<float,3> fov{};std::array<float,3> zoom_fov{};
    bool okay=dsr_mw2::observe(reader,base,s)==dsr_mw2::ReadStatus::ok&&s.hp&&dsr_mw2::is_m9(s.right_weapon)&&
        reader.get(base,0x1c7a488,bullet)&&reader.get(bullet,0x60,chr)&&reader.get(chr,0x68,camera)&&
        reader.get(camera,0,vtable)&&vtable==base+0x12ee118&&reader.get(camera,0x50,fov)&&reader.get(camera,0x134,zoom_fov);
    for(float value:fov)okay=okay&&std::isfinite(value);
    for(float value:zoom_fov)okay=okay&&std::isfinite(value);
    if(okay)std::printf("{\"read_only\":true,\"windows_pid\":%lu,\"camera_50_58\":[%.9g,%.9g,%.9g],\"zoom_endpoints_134_13c\":[%.9g,%.9g,%.9g]}\n",pid,
        static_cast<double>(fov[0]),static_cast<double>(fov[1]),static_cast<double>(fov[2]),
        static_cast<double>(zoom_fov[0]),static_cast<double>(zoom_fov[1]),static_cast<double>(zoom_fov[2]));
    CloseHandle(game);return okay?0:70;
}
