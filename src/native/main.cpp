#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <filesystem>
#include <fstream>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <regex>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>
#include <Windows.h>
#include <xaudio2.h>
#include <bcrypt.h>
#include <malloc.h>
#include <Mod/CppUserModBase.hpp>
#include <LuaMadeSimple/LuaMadeSimple.hpp>
#include "native_api.hpp"
#include "GuardMapMath.hpp"
#include "InventoryRowName.hpp"
#include "ProcessValidationCache.hpp"
#include "../../references/pbz-mc/third_party/nlohmann-json-3.11.3/json.hpp"
#include "../../references/pbz-mc/third_party/minhook-1.3.4/include/MinHook.h"
namespace {
using namespace RC::Unreal;
using RC::LuaMadeSimple::Lua;
constexpr size_t input_limit=65536;
constexpr size_t output_limit=262144;
#include "Reflection.hpp"

std::array<unsigned char,32> file_hash(HMODULE module) {
    std::array<wchar_t,32768> path{};
    require(GetModuleFileNameW(module,path.data(),static_cast<DWORD>(path.size()))>0,"Module path unavailable");
    std::ifstream input(path.data(),std::ios::binary);Sha256 hash;std::array<unsigned char,65536> buffer{};
    while(input.read(reinterpret_cast<char*>(buffer.data()),buffer.size())||input.gcount()>0)
        hash.update(buffer.data(),static_cast<ULONG>(input.gcount()));
    require(input.eof()&&!input.bad(),"Module hash read failed");return hash.finish();
}
void verify_pinned_abi() {
    static RingedKnightProcessValidation::OnceResult<bool> validated;
    (void)validated.get([]{
        const auto dll=GetModuleHandleW(L"UE4SS.dll");require(dll!=nullptr,"UE4SS is not loaded");
        constexpr std::array<unsigned char,32> expected{0xe1,0xfb,0x9a,0x7e,0x1d,0x86,0x8a,0xfe,0xf6,0xa0,0x91,0xc2,0x01,0x2e,0x71,0x1c,0x3e,0xc4,0x7f,0x05,0xd1,0x00,0xba,0x37,0xf9,0x63,0x1a,0x4f,0x75,0xf3,0x1d,0xf2};
        require(file_hash(dll)==expected,"Unsupported UE4SS binary; expected 1195-g1ceefac8");
        const auto same=[dll](const char* a,const char* b){const auto p=GetProcAddress(dll,a);return p&&p==GetProcAddress(dll,b);};
        require(same("?GetCharTArray@FString@Unreal@RC@@QEBAAEBV?$TArray@_WV?$TSizedDefaultAllocator@$0CA@@Unreal@RC@@@23@XZ","?GetCharArray@?$TStringBase@_W@Unreal@RC@@QEBAAEBV?$TArray@_WV?$TSizedDefaultAllocator@$0CA@@Unreal@RC@@@23@XZ"),"FString view ABI differs");
        return true;
    });
}
const std::array<unsigned char,32>& process_executable_hash() {
    static RingedKnightProcessValidation::OnceResult<std::array<unsigned char,32>> digest;
    return digest.get([]{return file_hash(nullptr);});
}
#include "NativeProtection.hpp"
#include "ShieldGate.hpp"
#include "NativeHit.hpp"
#include "NativeArtResource.hpp"
#include "NativeInventory.hpp"
#include "NativeSpatialQuery.hpp"
#include "NativeAudio.hpp"

int lua_hit(const Lua& lua) {
    try {verify_pinned_abi();return RingedKnightHit::lua_hit(lua);}
    catch(const std::exception& error){lua.set_nil();lua.set_string(error.what());return 2;}
}
int lua_art_resource(const Lua& lua) {
    try {verify_pinned_abi();return RingedKnightArtResource::lua_spend(lua);}
    catch(const std::exception& error){lua.set_nil();lua.set_string(error.what());return 2;}
}
int lua_guard(const Lua& lua) {
    try {verify_pinned_abi();return ShieldGate::lua_set(lua);}
    catch(const std::exception& error){ShieldGate::clear();lua.set_nil();lua.set_string(error.what());return 2;}
}
int lua_inventory(const Lua& lua) {
    try {verify_pinned_abi();return RingedKnightInventory::lua_inventory(lua);}
    catch(const std::exception& error){lua.set_nil();lua.set_string(error.what());return 2;}
}
int lua_query(const Lua& lua) {
    try {verify_pinned_abi();return RingedKnightQuery::lua_query(lua);}
    catch(const std::exception& error){lua.set_nil();lua.set_string(error.what());return 2;}
}
int lua_compatible(const Lua& lua) {
    try {
        verify_pinned_abi();
        constexpr std::array<unsigned char,32> expected{0x7b,0x4f,0xcd,0x28,0x6a,0x35,0x07,0x80,0xfa,0xf0,0x82,0x4d,0x73,0xaa,0x15,0x0b,0x21,0xcb,0xf1,0xbc,0xcd,0xe8,0x83,0xe6,0xa9,0x63,0x86,0xcb,0xe0,0x99,0x73,0xb4};
        constexpr std::array<unsigned char,32> november4{0x44,0x15,0x93,0x3c,0xe3,0x34,0x76,0xf1,0x4c,0x83,0x7a,0xbb,0x61,0xa1,0xb6,0x0a,0xf8,0xb7,0x8c,0xd8,0x17,0x83,0x89,0x65,0x01,0x91,0x3a,0x7a,0xac,0x69,0xe4,0x23};
        const auto& hash=process_executable_hash();lua.set_bool(hash==expected||hash==november4);return 1;
    } catch(...) {lua.set_bool(false);return 1;}
}
class RingedKnightBridge final:public RC::CppUserModBase {
public:
    RingedKnightBridge() {
        ModName=L"RingedKnightNative";ModVersion=L"0.1.0-dev";
        ModDescription=L"Transient sword damage and directional shield guard bridge";
        ModAuthors=L"Ringed Knight Arsenal; PBZMC contributors (adapted portions)";
        ModIntendedSDKVersion=L"3.0.1-1195-g1ceefac8";
        register_on_lua_start([](RC::CppUserModBase*,RC::CStringView name,Lua&,Lua& main,Lua&,Lua*) {
            const std::wstring_view mod(name.data,name.size);
            if(mod!=L"RingedKnightArsenal"&&mod!=L"RingedKnightProbe")return;
            main.register_function("RK_HostCompatible",&lua_compatible);
            main.register_function("RK_NativeHit",&lua_hit);
            main.register_function("RK_ArtResource",&lua_art_resource);
            main.register_function("RK_ShieldState",&lua_guard);
            main.register_function("RK_CombatProtection",&RingedKnightProtection::lua_set);
            main.register_function("RK_NativeInventory",&lua_inventory);
            main.register_function("RK_NativeQuery",&lua_query);
            main.register_function("RK_PlayPcm",&NativeAudio::lua_play);
        });
        register_on_lua_stop([](RC::CppUserModBase*,RC::CStringView name,Lua&,Lua&,Lua&,Lua*) {
            if(std::wstring_view(name.data,name.size)==L"RingedKnightArsenal"){
                ShieldGate::clear();RingedKnightProtection::forget();NativeAudio::shutdown();
            }
        });
    }
    ~RingedKnightBridge() override {ShieldGate::clear();RingedKnightProtection::forget();NativeAudio::shutdown();}
};
}
extern "C" __declspec(dllexport) RC::CppUserModBase* start_mod(){return new RingedKnightBridge;}
extern "C" __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod){delete mod;}
