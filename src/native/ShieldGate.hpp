// Adapted from fjdsjd/pbz-mc, PolyForm Noncommercial 1.0.0.
// Required Notice: Copyright (c) 2026 桃天帝不差
// Required Notice: 黑神话：史蒂夫 — 作者 / B站：桃天帝不差
#pragma once
#include "GuardContact.hpp"
// The pinned native AttributeComponent::TakeDamage entry, before calculation,
// HP modification and DamageTaken dispatch. Updated-build offline ABI proof:
// reports/new-build-damage-registration.json (CL-302256_JKS-17280).
// No FFrame/Blueprint exec hook, global invulnerability or post-damage healing.
#pragma once

namespace ShieldGate {
struct Vector { double x,y,z; };
using Damage = void(*)(UObject*,const void*,const void*,const Vector*,const void*,const void*,const void*,UObject*,const Vector*,const Vector*,void*);
inline Damage original{};
inline std::mutex mutex;
inline UObject* owner{};
inline std::wstring owner_name;
inline std::string lease;
inline double facing_x{},facing_y{};
inline bool active{};
inline ULONGLONG heartbeat{};
inline DWORD game_thread{};
inline const FProperty* final_map{};
inline std::atomic_uint64_t blocked{},passed{},block_sounds{},sound_failures{};
inline std::atomic<double> stamina_spent{0};
inline std::atomic_uint64_t resource_depleted{},guard_failures{};
inline std::string last_error;
inline thread_local bool settling_guard{};
#include "GuardEnergy.hpp"

inline void clear() noexcept { std::lock_guard lock(mutex);active=false;owner=nullptr;owner_name.clear();lease.clear(); }

inline void intercept(UObject* component,const void* source,const void* cause,const Vector* hit,const void* body,
    const void* attributes,const void* attack,UObject* calculator,const Vector* direction,const Vector* sweep,void* result) {
    bool block=false;
    {
        std::lock_guard lock(mutex);

        DWORD foreground_pid{};GetWindowThreadProcessId(GetForegroundWindow(),&foreground_pid);
        if(active && !settling_guard && component==owner && GetCurrentThreadId()==game_thread && GetTickCount64()-heartbeat<=250
            && foreground_pid==GetCurrentProcessId() && source && result && direction) {
            // PBZ supplies travel direction, so a frontal strike points against
            // the player's look vector. Vertical/environmental damage has no
            // horizontal incoming direction and is deliberately not blocked.
            block=RingedKnightGuardContact::frontal(direction->x,direction->y,direction->z,facing_x,facing_y)
                && !component->IsUnreachable() && component->GetFullName()==owner_name;
        }
    }
    if(block && cause) {
        const auto tag=reinterpret_cast<const FName*>(cause)->ToString();
        if(tag==L"Damage.Cause.MCFall"||tag==L"Damage.Cause.MCFlyIntoWall")block=false;
    }
    if(block) {
        try {
            // Enemy AttackData/custom calculators need not interpret our old
            // pre-scaled map as intended. A real frontal block returns an empty
            // constructed out map before HP/poise/damage delegates run.
            // Fixed native Energy is charged through PBZ's reflected API.
            struct Scope {Scope(){settling_guard=true;}~Scope(){settling_guard=false;}} scope;
            if(Energy::debit()) {
                // Damage and hit-reaction are separate native routes. Cover
                // only a successful frontal contact with the original finite
                // IgnoreHit/IgnoreBreak specs; never grant holding-wide armor.
                try{RingedKnightProtection::guard_contact(Energy::pawn_bound);}
                catch(const std::exception& error){++guard_failures;std::lock_guard lock(mutex);last_error=error.what();}
                final_map->DestroyValue(result);final_map->InitializeValue(result);
                ++blocked;stamina_spent.fetch_add(Energy::contact_cost);return;
            }
            ++resource_depleted; // No free block when native killing energy is empty.
        }catch(const std::exception& error){
            clear();++guard_failures;
            std::lock_guard lock(mutex);last_error=error.what();
        }
    }
    ++passed;

    original(component,source,cause,hit,body,attributes,attack,calculator,direction,sweep,result);
}

inline void install() {
    static std::once_flag once;
    std::call_once(once,[] {
        verify_pinned_abi();
        auto* base=reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
        constexpr std::array<unsigned char,32> previous_build{0x7b,0x4f,0xcd,0x28,0x6a,0x35,0x07,0x80,0xfa,0xf0,0x82,0x4d,0x73,0xaa,0x15,0x0b,
            0x21,0xcb,0xf1,0xbc,0xcd,0xe8,0x83,0xe6,0xa9,0x63,0x86,0xcb,0xe0,0x99,0x73,0xb4};
        constexpr std::array<unsigned char,32> current_build{0x44,0x15,0x93,0x3c,0xe3,0x34,0x76,0xf1,0x4c,0x83,0x7a,0xbb,0x61,0xa1,0xb6,0x0a,
            0xf8,0xb7,0x8c,0xd8,0x17,0x83,0x89,0x65,0x01,0x91,0x3a,0x7a,0xac,0x69,0xe4,0x23};
        const auto& executable_hash=process_executable_hash();
        const std::uintptr_t native_rva=executable_hash==previous_build?0x5da3d70:
            executable_hash==current_build?0x5decb30:0;
        require(native_rva!=0,"shield unsupported PBZ executable");
        constexpr std::array<ExpectedParameter,10> expected_parameters{{
             {L"DamageSource",L"InterfaceProperty"},{L"DamageCause",L"StructProperty"},{L"HitLocation",L"StructProperty"},
             {L"HitBody",L"StructProperty"},{L"AttackerAttributes",L"MapProperty"},{L"AttackData",L"MapProperty"},
             {L"CustomCalculator",L"ObjectProperty"},{L"AttackDirection",L"StructProperty"},{L"SweepDirection",L"StructProperty"},
             {L"FinalDamageData",L"MapProperty"}}};
        const auto schema=inspect_signature(L"/Script/SGameAttributes.AttributeComponent:TakeDamage",expected_parameters);
        require(schema.size==360 && schema.at(L"AttackDirection").offset==232 && schema.at(L"FinalDamageData").offset==280,
            "shield damage ABI changed");
        final_map=schema.at(L"FinalDamageData").property;
        const auto init=MH_Initialize();require(init==MH_OK||init==MH_ERROR_ALREADY_INITIALIZED,"shield hook initialize");
        auto* address=base+native_rva;
        // Preserve the verified unmodified function entry before MinHook owns it.
        constexpr unsigned char prefix[]{0x40,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,
            0x48,0x8d,0xac,0x24,0x10,0xfd,0xff,0xff};
        require(std::memcmp(address,prefix,sizeof(prefix))==0,"shield entry differs from ABI proof");
        auto created=MH_CreateHook(address,reinterpret_cast<void*>(&intercept),reinterpret_cast<void**>(&original));
        if(created==MH_ERROR_MEMORY_ALLOC)
            created=MH_CreatePBZDamageHook(address,reinterpret_cast<void*>(&intercept),reinterpret_cast<void**>(&original));
        if(created!=MH_OK)throw std::runtime_error(std::string("shield hook create: ")+MH_StatusToString(created));
        HMODULE pinned{};
        require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&intercept),&pinned)!=FALSE,"shield callback pin");
        require(MH_EnableHook(address)==MH_OK,"shield hook enable");
    });
}

inline std::string set(const std::string& input) {
    using Json=nlohmann::json;
    require(input.size()<=8192,"shield input too large");const auto data=Json::parse(input);
    require(IsInGameThread(),"shield state requires game thread");
    require(data.is_object()&&data.contains("active")&&data["active"].is_boolean(),"shield state schema");
    if(data.value("prepare",false)){install();Energy::schemas();}
    if(!data["active"].get<bool>()){
        std::lock_guard lock(mutex);
        if(data.value("lease",std::string{})==lease){active=false;owner=nullptr;owner_name.clear();lease.clear();}
        return Json{{"active",active},{"blocked",blocked.load()},{"passed",passed.load()},{"stamina_spent",stamina_spent.load()},
            {"energy_spent",Energy::spent.load()},{"energy_cost_per_damage_call",Energy::contact_cost},
            {"resource_depleted",resource_depleted.load()},{"guard_failures",guard_failures.load()},{"last_error",last_error},
            {"energy_before",Energy::last_before.load()},{"energy_after",Energy::last_after.load()},
            {"mode","forward_full_block"},{"block_sounds",block_sounds.load()},{"sound_failures",sound_failures.load()}}.dump();
    }
    install();
    const auto path=from_utf8(data.at("component").get<std::string>());
    const double x=data.at("x").get<double>(),y=data.at("y").get<double>();
    const auto token=data.at("lease").get<std::string>();require(!token.empty()&&token.size()<=128,"shield lease required");
    require(std::isfinite(x)&&std::isfinite(y)&&std::abs(x*x+y*y-1)<.001,"shield invalid view vector");
    auto* component=find_object(path.c_str());
    const auto name=component->GetFullName();
    require(name.starts_with(L"AttributeComponent ")&&!component->IsUnreachable(),"shield requires live AttributeComponent");
    // Missing/unresolved Energy is a visible capability failure, not an
    // invitation to guess a property, silently block for free or mutate HP.
    Energy::bind(component);
    const auto energy=Energy::read();
    std::lock_guard lock(mutex);
    owner=component;owner_name=name;lease=token;facing_x=x;facing_y=y;game_thread=GetCurrentThreadId();heartbeat=GetTickCount64();active=RingedKnightGuardContact::can_pay(energy);
    return Json{{"active",active},{"blocked",blocked.load()},{"passed",passed.load()},{"stamina_spent",stamina_spent.load()},
        {"energy_spent",Energy::spent.load()},{"energy_cost_per_damage_call",Energy::contact_cost},
        {"energy_attribute",Energy::attribute_path},
        {"resource_depleted",resource_depleted.load()},{"guard_failures",guard_failures.load()},{"last_error",last_error},
        {"energy_before",Energy::last_before.load()},{"energy_after",Energy::last_after.load()},
        {"energy_current",energy},{"guard_broken",energy<Energy::contact_cost},
        {"mode","forward_full_block"},{"block_sounds",block_sounds.load()},{"sound_failures",sound_failures.load()}}.dump();
}
inline int lua_set(const Lua& lua) {
    try {
        require(lua.get_stack_size()==1&&lua.is_string(1),"usage: RK_ShieldState(json)");
        lua.set_string(set(std::string(lua.get_string(1))));lua.set_nil();
    } catch(const std::exception& error){clear();lua.set_nil();lua.set_string(std::string("RK shield: ")+error.what());}
    return 2;
}


}
