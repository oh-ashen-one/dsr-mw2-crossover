// Original 2D view-weapon sound output. Only a verified native ammo receipt
// requests playback; this code cannot fire a weapon or alter game state.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include "shot_audio.hpp"
#include "pcm_packet.hpp"
#include "packet_buffer.hpp"
#include <array>
#include <cstdio>
#include <cstdint>
#include <cstring>
namespace {
struct Sound {dsr_mw2::PacketBuffer<unsigned char> data;dsr_mw2::PcmInfo info;bool ready=false;};
struct Voice {HWAVEOUT output=nullptr;WAVEHDR header{};};
Sound sounds[2];std::array<Voice,8> voices{};
// Rapid fire stacked up to eight full-scale 1-3 s gunshots and clipped the
// whole mix. Keep three overlapping shots (newest replaces oldest) at -6 dB.
constexpr std::size_t max_voices=3;std::array<ULONGLONG,8> started{};
SRWLOCK audio_lock=SRWLOCK_INIT;
HANDLE log_file=INVALID_HANDLE_VALUE;
void record(const char* kind,unsigned code){
    if(log_file==INVALID_HANDLE_VALUE)log_file=CreateFileW(L"C:\\Tools\\DSR-MW2\\shot-audio.jsonl",FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(log_file!=INVALID_HANDLE_VALUE){char data[160]{};const int n=std::snprintf(data,sizeof(data),"{\"kind\":\"%s\",\"code\":%u,\"ms\":%llu}\n",kind,code,GetTickCount64());
        if(n>0&&n<static_cast<int>(sizeof(data))){DWORD written=0;WriteFile(log_file,data,static_cast<DWORD>(n),&written,nullptr);}}
}
bool close(Voice& v){
    if(!v.output)return true;
    if(v.header.dwFlags&WHDR_PREPARED){
        if(!(v.header.dwFlags&WHDR_DONE)||waveOutUnprepareHeader(v.output,&v.header,sizeof(v.header))!=MMSYSERR_NOERROR)return false;
    }
    if(waveOutClose(v.output)!=MMSYSERR_NOERROR)return false;
    v={};return true;
}
}
namespace dsr_mw2 {
bool shot_audio_load(const wchar_t* file,bool sniper){
    auto& s=sounds[sniper?1:0];if(s.ready)return true;
    HANDLE f=CreateFileW(file,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(f==INVALID_HANDLE_VALUE)return false;
    LARGE_INTEGER n{};bool okay=GetFileSizeEx(f,&n)&&n.QuadPart>=44&&n.QuadPart<=8*1024*1024;
    if(okay){okay=s.data.resize(static_cast<std::size_t>(n.QuadPart));DWORD got=0;
        if(okay)okay=ReadFile(f,s.data.data(),static_cast<DWORD>(s.data.size()),&got,nullptr)&&got==s.data.size();}
    CloseHandle(f);s.ready=okay&&pcm_info(s.data.data(),s.data.size(),s.info);
    if(s.ready)for(std::uint32_t i=0;i+1<s.info.bytes;i+=2){
        std::int16_t sample;std::memcpy(&sample,s.data.data()+44+i,2);
        sample=static_cast<std::int16_t>(sample/2);std::memcpy(s.data.data()+44+i,&sample,2);
    }
    record("loaded",s.ready?(sniper?2u:1u):0u);return s.ready;
}
void shot_audio_play(bool sniper){
    AcquireSRWLockExclusive(&audio_lock);auto& s=sounds[sniper?1:0];
    if(s.ready){
        std::size_t index=max_voices;
        for(std::size_t i=0;i<max_voices;++i)if(close(voices[i])){index=i;break;}
        if(index==max_voices){
            index=0;for(std::size_t i=1;i<max_voices;++i)if(started[i]<started[index])index=i;
            waveOutReset(voices[index].output);
            if(!close(voices[index]))index=max_voices;
        }
        if(index<max_voices){
            auto& v=voices[index];
            WAVEFORMATEX format{};format.wFormatTag=WAVE_FORMAT_PCM;format.nChannels=s.info.channels;
            format.nSamplesPerSec=44100;format.wBitsPerSample=16;format.nBlockAlign=static_cast<WORD>(s.info.channels*2);
            format.nAvgBytesPerSec=format.nSamplesPerSec*format.nBlockAlign;
            auto code=waveOutOpen(&v.output,WAVE_MAPPER,&format,0,0,CALLBACK_NULL);
            if(code==MMSYSERR_NOERROR){
                v.header.lpData=reinterpret_cast<char*>(s.data.data()+44);v.header.dwBufferLength=s.info.bytes;
                code=waveOutPrepareHeader(v.output,&v.header,sizeof(v.header));
                if(code==MMSYSERR_NOERROR)code=waveOutWrite(v.output,&v.header,sizeof(v.header));
            }
            if(code!=MMSYSERR_NOERROR&&v.output){waveOutReset(v.output);close(v);}
            started[index]=GetTickCount64();
            record(code==MMSYSERR_NOERROR?(sniper?"intervention_shot":"m9_shot"):"output_failed",code);
        }
    }
    ReleaseSRWLockExclusive(&audio_lock);
}
void shot_audio_stop(){
    AcquireSRWLockExclusive(&audio_lock);
    for(auto& v:voices)if(v.output){waveOutReset(v.output);close(v);}
    ReleaseSRWLockExclusive(&audio_lock);
}
}
