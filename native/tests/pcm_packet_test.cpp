#include "pcm_packet.hpp"
#include <fstream>
#include <iterator>
#include <vector>
#include <cassert>
int main(int argc,char** argv){
    assert(argc==3);
    for(int i=1;i<argc;++i){
        std::ifstream file(argv[i],std::ios::binary);
        std::vector<unsigned char> data{std::istreambuf_iterator<char>(file),{}};
        dsr_mw2::PcmInfo info;
        assert(dsr_mw2::pcm_info(data.data(),data.size(),info));
        assert(info.channels==2&&info.bytes==data.size()-44);
        for(unsigned at:{0u,4u,8u,12u,16u,20u,22u,24u,28u,32u,34u,36u,40u}){
            auto bad=data;bad[at]^=255;assert(!dsr_mw2::pcm_info(bad.data(),bad.size(),info));
        }
        for(unsigned size:{0u,8u,43u,44u,1024u})assert(!dsr_mw2::pcm_info(data.data(),size,info));
        data.pop_back();assert(!dsr_mw2::pcm_info(data.data(),data.size(),info));
    }
}
