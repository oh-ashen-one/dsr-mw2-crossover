// Original pure intent state; no native calls or memory access.
#pragma once
namespace dsr_mw2 {
class M9AimLatch {
public:
    bool desired(bool safe,bool allowed,bool held,bool native_request,bool owned,bool resumable,bool native_bit){
        if(!held)armed=true;
        if(!safe||!resumable||!held)resume=false;
        else if(owned)resume=true;
        const bool result=safe&&allowed&&held&&(owned||(armed&&(native_request||resume)&&!native_bit));
        if(!safe||(!allowed&&!resume))armed=false;
        return result;
    }
    void reset(){armed=false;resume=false;}
private:
    bool armed=false,resume=false;
};
}
