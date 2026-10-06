#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <d3dcompiler.h>
#include <cstdio>
#include "viewmodel_packet.hpp"
#include "viewmodel_renderer.hpp"

namespace {
using namespace dsr_mw2;
SRWLOCK state_lock=SRWLOCK_INIT,render_lock=SRWLOCK_INIT;
VmState state{};VmPacket packet;
std::uint64_t shot=0;bool last=false,loaded=false,stopped=false;
volatile LONG64 healthy=0,rendered_player=0;
template<class T>void release(T*& v){if(v)v->Release();v=nullptr;}
ID3D11Device* device=nullptr;ID3D11DeviceContext* immediate=nullptr;ID3D11DeviceContext* deferred=nullptr;
ID3D11VertexShader* vs=nullptr;ID3D11PixelShader* ps=nullptr;ID3D11InputLayout* layout=nullptr;
ID3D11Buffer* vertices=nullptr;ID3D11Buffer* constants=nullptr;
ID3D11SamplerState* sampler=nullptr;ID3D11RasterizerState* raster=nullptr;
ID3D11DepthStencilState* depth=nullptr;ID3D11BlendState* blend=nullptr;
ID3D11Texture2D* own_depth=nullptr;ID3D11DepthStencilView* depth_view=nullptr;
unsigned depth_width=0,depth_height=0,depth_samples=0;
std::array<ID3D11ShaderResourceView*,8> textures{};
HANDLE log_file=INVALID_HANDLE_VALUE;unsigned long long draws=0;
void event(const char* message,long value){
    if(log_file==INVALID_HANDLE_VALUE)log_file=CreateFileW(L"C:\\Tools\\DSR-MW2\\viewmodel-v1.jsonl",FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(log_file!=INVALID_HANDLE_VALUE){char line[256]{};const int n=std::snprintf(line,sizeof(line),"{\"kind\":\"%s\",\"value\":%ld,\"ms\":%llu}\n",message,value,GetTickCount64());
        if(n>0&&n<static_cast<int>(sizeof(line))){DWORD count=0;WriteFile(log_file,line,static_cast<DWORD>(n),&count,nullptr);}}
}
void destroy(){
    InterlockedExchange64(&healthy,0);InterlockedExchange64(&rendered_player,0);
    for(auto*& t:textures)release(t);
    release(depth_view);release(own_depth);depth_width=depth_height=depth_samples=0;
    release(blend);release(depth);release(raster);release(sampler);release(constants);release(vertices);
    release(layout);release(ps);release(vs);release(deferred);release(immediate);release(device);
}
// Own depth and deferred context: never clear DSR depth or leave pipeline
// bindings behind. ExecuteCommandList(TRUE) restores the immediate context.
constexpr char shader[]=R"(
cbuffer Pose : register(b0) {float4 bone[228];float4 projection;};
struct Input {float3 p:POSITION;float3 n:NORMAL;float2 uv:TEXCOORD0;uint4 j:BLENDINDICES;float4 w:BLENDWEIGHT;};
struct Output {float4 p:SV_POSITION;float3 n:NORMAL;float2 uv:TEXCOORD0;};
Output vertex(Input a){
 float3 p=0,n=0;
 [unroll]for(uint i=0;i<4;i++){uint b=a.j[i]*3;float4 v=float4(a.p,1);float4 normal=float4(a.n,0);
 p+=float3(dot(bone[b],v),dot(bone[b+1],v),dot(bone[b+2],v))*a.w[i];
 n+=float3(dot(bone[b],normal),dot(bone[b+1],normal),dot(bone[b+2],normal))*a.w[i];}
 float3 camera=float3(-p.y,p.z-60,p.x);
 Output o;o.p=float4(camera.x*projection.x,camera.y*projection.y,camera.z*projection.z+projection.w,camera.z);
 o.n=normalize(n);o.uv=a.uv;return o;
}
Texture2D diffuse:register(t0);SamplerState filtering:register(s0);
float4 pixel(Output a):SV_TARGET {
 float4 c=diffuse.Sample(filtering,a.uv);clip(c.a-.25);
 float lighting=.45+.55*saturate(dot(normalize(a.n),normalize(float3(-.3,-.4,1))));
 return float4(c.rgb*lighting,1);
}
)";
bool initialize(IDXGISwapChain* chain){
    ID3D11Device* current=nullptr;
    if(FAILED(chain->GetDevice(__uuidof(ID3D11Device),reinterpret_cast<void**>(&current))))return false;
    if(current==device){current->Release();return true;}
    destroy();device=current;device->GetImmediateContext(&immediate);
    if(!immediate||FAILED(device->CreateDeferredContext(0,&deferred)))return false;
    ID3DBlob* vertex=nullptr;ID3DBlob* pixel=nullptr;ID3DBlob* errors=nullptr;
    HRESULT h=D3DCompile(shader,sizeof(shader)-1,"dsr-mw2-original-viewmodel",nullptr,nullptr,"vertex","vs_5_0",D3DCOMPILE_ENABLE_STRICTNESS,0,&vertex,&errors);
    release(errors);if(FAILED(h)){event("vertex_compile_failed",h);return false;}
    h=D3DCompile(shader,sizeof(shader)-1,"dsr-mw2-original-viewmodel",nullptr,nullptr,"pixel","ps_5_0",D3DCOMPILE_ENABLE_STRICTNESS,0,&pixel,&errors);
    release(errors);if(FAILED(h)){release(vertex);event("pixel_compile_failed",h);return false;}
    h=device->CreateVertexShader(vertex->GetBufferPointer(),vertex->GetBufferSize(),nullptr,&vs);
    if(SUCCEEDED(h))h=device->CreatePixelShader(pixel->GetBufferPointer(),pixel->GetBufferSize(),nullptr,&ps);
    const D3D11_INPUT_ELEMENT_DESC attributes[]={
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"NORMAL",0,DXGI_FORMAT_R32G32B32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"BLENDINDICES",0,DXGI_FORMAT_R16G16B16A16_UINT,0,32,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"BLENDWEIGHT",0,DXGI_FORMAT_R32G32B32A32_FLOAT,0,40,D3D11_INPUT_PER_VERTEX_DATA,0}};
    if(SUCCEEDED(h))h=device->CreateInputLayout(attributes,5,vertex->GetBufferPointer(),vertex->GetBufferSize(),&layout);
    release(vertex);release(pixel);if(FAILED(h))return false;
    D3D11_BUFFER_DESC vb{};vb.ByteWidth=static_cast<UINT>(packet.vertices.size()*sizeof(VmVertex));vb.Usage=D3D11_USAGE_IMMUTABLE;vb.BindFlags=D3D11_BIND_VERTEX_BUFFER;
    D3D11_SUBRESOURCE_DATA initial{};initial.pSysMem=packet.vertices.data();
    if(FAILED(device->CreateBuffer(&vb,&initial,&vertices)))return false;
    D3D11_BUFFER_DESC cb{};cb.ByteWidth=76*48+16;cb.Usage=D3D11_USAGE_DEFAULT;cb.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    if(FAILED(device->CreateBuffer(&cb,nullptr,&constants)))return false;
    unsigned texture_index=0;
    for(const auto& t:packet.textures){
        D3D11_TEXTURE2D_DESC desc{};desc.Width=t.width;desc.Height=t.height;desc.MipLevels=1;desc.ArraySize=1;
        desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA data{};data.pSysMem=t.rgba.data();data.SysMemPitch=t.width*4;
        ID3D11Texture2D* image=nullptr;ID3D11ShaderResourceView* view=nullptr;
        h=device->CreateTexture2D(&desc,&data,&image);if(SUCCEEDED(h))h=device->CreateShaderResourceView(image,nullptr,&view);
        release(image);if(FAILED(h))return false;textures[texture_index++]=view;
    }
    D3D11_SAMPLER_DESC s{};s.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;s.AddressU=s.AddressV=s.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;s.MaxLOD=D3D11_FLOAT32_MAX;s.ComparisonFunc=D3D11_COMPARISON_ALWAYS;
    D3D11_RASTERIZER_DESC r{};r.FillMode=D3D11_FILL_SOLID;r.CullMode=D3D11_CULL_NONE;r.DepthClipEnable=TRUE;
    D3D11_DEPTH_STENCIL_DESC d{};d.DepthEnable=TRUE;d.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ALL;d.DepthFunc=D3D11_COMPARISON_LESS_EQUAL;
    D3D11_BLEND_DESC b{};b.RenderTarget[0].RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;
    if(FAILED(device->CreateSamplerState(&s,&sampler))||FAILED(device->CreateRasterizerState(&r,&raster))||
       FAILED(device->CreateDepthStencilState(&d,&depth))||FAILED(device->CreateBlendState(&b,&blend)))return false;
    event("device_initialized",1);return true;
}
}
namespace dsr_mw2 {
bool vm_load(const wchar_t* file){
    if(loaded)return true;
    HANDLE input=CreateFileW(file,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(input==INVALID_HANDLE_VALUE)return false;
    LARGE_INTEGER size{};bool okay=GetFileSizeEx(input,&size)&&size.QuadPart>0&&size.QuadPart<=32*1024*1024;
    PacketBuffer<unsigned char> bytes;if(okay){okay=bytes.resize(static_cast<std::size_t>(size.QuadPart));DWORD n=0;if(okay)okay=ReadFile(input,bytes.data(),static_cast<DWORD>(bytes.size()),&n,nullptr)&&n==bytes.size();}
    CloseHandle(input);loaded=okay&&packet.parse(bytes);event("packet_loaded",loaded?1:0);return loaded;
}
void vm_publish(const VmState& s){AcquireSRWLockExclusive(&state_lock);if(s.player!=state.player||s.weapon!=state.weapon||!s.visible)shot=0;state=s;ReleaseSRWLockExclusive(&state_lock);}
void vm_native_shot(bool last_round){AcquireSRWLockExclusive(&state_lock);shot=GetTickCount64();last=last_round;ReleaseSRWLockExclusive(&state_lock);}
bool vm_visible(std::uint64_t player){const auto t=static_cast<std::uint64_t>(InterlockedCompareExchange64(&healthy,0,0));
    return t&&GetTickCount64()-t<150&&static_cast<std::uint64_t>(InterlockedCompareExchange64(&rendered_player,0,0))==player;}
void vm_render(void* swap_chain){
    if(!loaded||!swap_chain||!TryAcquireSRWLockExclusive(&render_lock))return;
    VmState s;std::uint64_t fired=0;bool empty=false;
    AcquireSRWLockShared(&state_lock);s=state;fired=shot;empty=last;ReleaseSRWLockShared(&state_lock);
    const auto now=GetTickCount64();DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
    if(stopped||!s.visible||!s.player||!s.stamp||now-s.stamp>150||foreground!=GetCurrentProcessId()){
        InterlockedExchange64(&healthy,0);ReleaseSRWLockExclusive(&render_lock);return;}
    auto* chain=static_cast<IDXGISwapChain*>(swap_chain);
    ID3D11Texture2D* back=nullptr;ID3D11RenderTargetView* target=nullptr;
    ID3D11CommandList* list=nullptr;HRESULT h=E_FAIL;
    if(initialize(chain)&&SUCCEEDED(chain->GetBuffer(0,__uuidof(ID3D11Texture2D),reinterpret_cast<void**>(&back)))){
        D3D11_TEXTURE2D_DESC description{};back->GetDesc(&description);
        h=device->CreateRenderTargetView(back,nullptr,&target);
        if(depth_width!=description.Width||depth_height!=description.Height||depth_samples!=description.SampleDesc.Count){
            release(depth_view);release(own_depth);
            D3D11_TEXTURE2D_DESC dd=description;dd.Format=DXGI_FORMAT_D24_UNORM_S8_UINT;dd.MipLevels=1;dd.ArraySize=1;dd.Usage=D3D11_USAGE_DEFAULT;dd.BindFlags=D3D11_BIND_DEPTH_STENCIL;dd.CPUAccessFlags=dd.MiscFlags=0;
            if(SUCCEEDED(h))h=device->CreateTexture2D(&dd,nullptr,&own_depth);
            if(SUCCEEDED(h))h=device->CreateDepthStencilView(own_depth,nullptr,&depth_view);
            if(SUCCEEDED(h)){depth_width=description.Width;depth_height=description.Height;depth_samples=description.SampleDesc.Count;}
        }
        if(SUCCEEDED(h)&&description.Width&&description.Height){
            struct Constants {std::array<VmMatrix,76> bones;float projection[4];} c{};
            unsigned clip=0;float seconds=0,ads=1;
            if(s.animation==465501||s.animation==465502){clip=s.animation==465501?4u:3u;seconds=std::max(0.f,s.elapsed);ads=0;}
            else if(fired&&now>=fired&&now-fired<(empty?234u:467u)){clip=empty?2u:1u;seconds=static_cast<float>(now-fired)/1000.f;}
            if(packet.pose(clip,seconds,ads,c.bones)){
                const float y=1.f/std::tan(50.f*3.14159265359f/360.f),near_clip=.05f,far_clip=512.f;
                c.projection[0]=y*static_cast<float>(description.Height)/static_cast<float>(description.Width);c.projection[1]=y;c.projection[2]=far_clip/(far_clip-near_clip);c.projection[3]=-near_clip*far_clip/(far_clip-near_clip);
                deferred->ClearState();deferred->UpdateSubresource(constants,0,nullptr,&c,0,0);
                deferred->OMSetRenderTargets(1,&target,depth_view);deferred->ClearDepthStencilView(depth_view,D3D11_CLEAR_DEPTH,1,0);
                deferred->OMSetDepthStencilState(depth,0);const float factor[4]={};deferred->OMSetBlendState(blend,factor,0xffffffff);
                const D3D11_VIEWPORT viewport={0,0,static_cast<float>(description.Width),static_cast<float>(description.Height),0,1};deferred->RSSetViewports(1,&viewport);deferred->RSSetState(raster);
                const UINT stride=sizeof(VmVertex),offset=0;deferred->IASetVertexBuffers(0,1,&vertices,&stride,&offset);deferred->IASetInputLayout(layout);deferred->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
                deferred->VSSetShader(vs,nullptr,0);deferred->VSSetConstantBuffers(0,1,&constants);deferred->PSSetShader(ps,nullptr,0);deferred->PSSetSamplers(0,1,&sampler);
                for(const auto& draw:packet.draws){if(draw.suppressor&&s.weapon!=9100000)continue;
                    deferred->PSSetShaderResources(0,1,&textures[draw.texture]);deferred->Draw(draw.count,draw.first);}
                h=deferred->FinishCommandList(FALSE,&list);
                if(SUCCEEDED(h)){immediate->ExecuteCommandList(list,TRUE);InterlockedExchange64(&healthy,static_cast<LONG64>(now));InterlockedExchange64(&rendered_player,static_cast<LONG64>(s.player));++draws;
                    if(draws==1||draws%600==0)event("viewmodel_frames",static_cast<long>(draws));}
            }else h=E_INVALIDARG;
        }
    }
    // No back-buffer references survive Present/ResizeBuffers.
    if(deferred)deferred->ClearState();
    release(list);release(target);release(back);
    if(FAILED(h)){event("render_failed",h);destroy();stopped=true;}
    ReleaseSRWLockExclusive(&render_lock);
}
void vm_stop(){AcquireSRWLockExclusive(&render_lock);stopped=true;destroy();ReleaseSRWLockExclusive(&render_lock);}
}

#ifdef DSR_MW2_SHADER_CHECK
// Original console harness: compiler calls only. No device/window/swap chain,
// game process, input, account state, save data or renderer lease is involved.
int main(){
    for(const auto& entry:std::array<std::array<const char*,2>,2>{{{"vertex","vs_5_0"},{"pixel","ps_5_0"}}}){
        ID3DBlob* bytecode=nullptr;ID3DBlob* errors=nullptr;
        const HRESULT status=D3DCompile(shader,sizeof(shader)-1,"original-viewmodel-check",nullptr,nullptr,entry[0],entry[1],D3DCOMPILE_ENABLE_STRICTNESS,0,&bytecode,&errors);
        if(errors){std::printf("%.*s\n",static_cast<int>(std::min<std::size_t>(errors->GetBufferSize(),4096)),static_cast<const char*>(errors->GetBufferPointer()));}
        std::printf("{\"stage\":\"%s\",\"hresult\":%ld,\"bytecode_bytes\":%llu,\"game_launched\":false,\"device_created\":false}\n",entry[0],status,bytecode?static_cast<unsigned long long>(bytecode->GetBufferSize()):0);
        release(errors);release(bytecode);if(FAILED(status))return 1;
    }
    return 0;
}
#endif
