// Original five-second console-only controller forwarding diagnostic.
// No game launch/attachment, input synthesis, vibration or configuration write.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xinput.h>
#include <cstdio>
#include <cstring>
#include <cwchar>

template<typename T>T proc(HMODULE module,const char* name){
    const auto p=GetProcAddress(module,name);T result{};
    static_assert(sizeof(p)==sizeof(result));std::memcpy(&result,&p,sizeof(p));return result;
}
void module_path(const char* role,HMODULE module){
    wchar_t path[1024]{};GetModuleFileNameW(module,path,1024);
    for(auto& c:path)if(c==L'\\')c=L'/';
    std::printf("{\"kind\":\"module\",\"role\":\"%s\",\"path\":\"%ls\"}\n",role,path);
}
int main(){
    char value[128]{};GetEnvironmentVariableA("WINEDLLOVERRIDES",value,128);
    if(std::strcmp(value,"xinput1_3=n,b")){std::printf("{\"error\":\"expected_scoped_override_absent\"}\n");return 64;}
    HMODULE trial=LoadLibraryW(L"C:\\Games\\DSR-MW2\\xinput1_3.dll");
    HMODULE system=LoadLibraryW(L"C:\\windows\\system32\\xinput1_4.dll");
    if(!trial||!system){std::printf("{\"error\":\"module_load\",\"code\":%lu}\n",GetLastError());return 65;}
    module_path("trial",trial);module_path("system14",system);
    const auto explicit_backend=LoadLibraryW(L"C:\\Games\\DSR-MW2\\xinput1_3_backend.dll");
    if(!explicit_backend){std::printf("{\"error\":\"backend_load\",\"code\":%lu}\n",GetLastError());return 67;}
    module_path("explicit_backend",explicit_backend);
    using State=DWORD(WINAPI*)(DWORD,XINPUT_STATE*);
    using Caps=DWORD(WINAPI*)(DWORD,DWORD,XINPUT_CAPABILITIES*);
    const auto get=proc<State>(trial,"XInputGetState");const auto compare=proc<State>(system,"XInputGetState");
    const auto caps=proc<Caps>(trial,"XInputGetCapabilities");
    if(!get||!compare||!caps){
        std::printf("{\"error\":\"export_missing\",\"get\":%s,\"compare\":%s,\"caps\":%s}\n",
                    get?"true":"false",compare?"true":"false",caps?"true":"false");return 66;}
    bool connected=false;
    for(unsigned sample=0;sample<10;++sample){
        for(DWORD slot=0;slot<4;++slot){
            XINPUT_STATE a{},b{};XINPUT_CAPABILITIES c{};
            const auto x=get(slot,&a),y=compare(slot,&b),z=caps(slot,0,&c);
            if(!slot&&x==0)connected=true;
            std::printf("{\"kind\":\"sample\",\"sample\":%u,\"slot\":%lu,\"trial\":%lu,\"system14\":%lu,\"caps\":%lu}\n",sample,slot,x,y,z);
        }
        std::fflush(stdout);Sleep(500);
    }
    HMODULE backend=GetModuleHandleW(L"xinput1_3_backend.dll");
    if(backend)module_path("backend",backend);
    std::printf("{\"finished\":true,\"trial_slot0_connected\":%s}\n",connected?"true":"false");
    FreeLibrary(system);FreeLibrary(trial);return 0;
}
