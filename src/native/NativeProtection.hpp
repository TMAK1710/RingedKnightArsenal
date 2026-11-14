// Original hit-reaction effects plus owned finite physical/elemental reduction.
// No invulnerability effect, no loose permanent tag and no raw handle layout.
#pragma once
#include "ProtectionLeaseStorage.hpp"
#include "ProtectionStringPolicy.hpp"
namespace RingedKnightProtection {
using Json=nlohmann::json;
inline constexpr float action_duration=.25f,block_duration=.15f;
inline constexpr ULONGLONG refresh_ms=100;
inline constexpr std::array<const wchar_t*,2> definitions{
    L"/PBZCombatAsset/Prototypes/GameplayEffects/GE_IgnoreHit.GE_IgnoreHit_C",
    L"/PBZCombatAsset/Prototypes/GameplayEffects/GE_IgnoreBreak.GE_IgnoreBreak_C"};
inline constexpr const wchar_t* reduction_source=L"/PBZCombatAsset/ActorData/Players/Hun/ShaqiWeapon/HuoLiuXing/UpgradeData/GE_ShachiWeapon_HuoLiuXing_Defence.GE_ShachiWeapon_HuoLiuXing_Defence_C";
inline constexpr const wchar_t* reduction_owned=L"/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.RKA_ActionDamageReduction";
inline std::unique_ptr<Signature> make_owned_spec;
inline std::atomic_uint64_t applications{},removals{},failures{};
inline std::string last_error;
inline std::unique_ptr<Signature> make_path,convert_path,load_class,asc_get,make_spec,set_duration,apply_spec,remove_effect,total_duration,string_buffer;

inline void schemas() {
    if(make_path)return;
    constexpr std::array path_params{ExpectedParameter{L"PathString",L"StrProperty"},ExpectedParameter{L"ReturnValue",L"StructProperty"}};
    constexpr std::array convert_params{ExpectedParameter{L"SoftClassPath",L"StructProperty"},ExpectedParameter{L"ReturnValue",L"SoftClassProperty"}};
    constexpr std::array load_params{ExpectedParameter{L"AssetClass",L"SoftClassProperty"},ExpectedParameter{L"ReturnValue",L"ClassProperty"}};
    constexpr std::array asc_params{ExpectedParameter{L"Actor",L"ObjectProperty"},ExpectedParameter{L"ReturnValue",L"ObjectProperty"}};
    constexpr std::array spec_params{ExpectedParameter{L"GameplayEffectClass",L"ClassProperty"},ExpectedParameter{L"Level",L"FloatProperty"},
        ExpectedParameter{L"Context",L"StructProperty"},ExpectedParameter{L"ReturnValue",L"StructProperty"}};
    constexpr std::array duration_params{ExpectedParameter{L"SpecHandle",L"StructProperty"},ExpectedParameter{L"Duration",L"FloatProperty"},ExpectedParameter{L"ReturnValue",L"StructProperty"}};
    constexpr std::array apply_params{ExpectedParameter{L"SpecHandle",L"StructProperty"},ExpectedParameter{L"ReturnValue",L"StructProperty"}};
    constexpr std::array remove_params{ExpectedParameter{L"Handle",L"StructProperty"},ExpectedParameter{L"StacksToRemove",L"IntProperty"},ExpectedParameter{L"ReturnValue",L"BoolProperty"}};
    constexpr std::array total_params{ExpectedParameter{L"ActiveHandle",L"StructProperty"},ExpectedParameter{L"ReturnValue",L"FloatProperty"}};
    constexpr std::array string_params{ExpectedParameter{L"InDouble",L"DoubleProperty"},ExpectedParameter{L"ReturnValue",L"StrProperty"}};
    auto p=std::make_unique<Signature>(inspect_signature(L"/Script/Engine.KismetSystemLibrary:MakeSoftClassPath",path_params));
    auto c=std::make_unique<Signature>(inspect_signature(L"/Script/Engine.KismetSystemLibrary:Conv_SoftClassPathToSoftClassRef",convert_params));
    auto l=std::make_unique<Signature>(inspect_signature(L"/Script/Engine.KismetSystemLibrary:LoadClassAsset_Blocking",load_params));
    auto a=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:GetAbilitySystemComponent",asc_params));
    auto m=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemComponent:MakeOutgoingSpec",spec_params));
    auto d=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:SetDuration",duration_params));
    auto app=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemComponent:BP_ApplyGameplayEffectSpecToSelf",apply_params));
    auto rem=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemComponent:RemoveActiveGameplayEffect",remove_params));
    auto total=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:GetActiveGameplayEffectTotalDuration",total_params));
    auto s=std::make_unique<Signature>(inspect_signature(L"/Script/Engine.KismetStringLibrary:Conv_DoubleToString",string_params));
    require(p->at(L"ReturnValue").property->SameType(c->at(L"SoftClassPath").property)
        &&c->at(L"ReturnValue").property->SameType(l->at(L"AssetClass").property),"protection soft-class schemas differ");
    require(m->at(L"ReturnValue").property->SameType(d->at(L"SpecHandle").property)
        &&d->at(L"ReturnValue").property->SameType(app->at(L"SpecHandle").property),"protection spec schemas differ");
    require(app->at(L"ReturnValue").property->SameType(rem->at(L"Handle").property)
        &&app->at(L"ReturnValue").property->SameType(total->at(L"ActiveHandle").property),"protection active-handle schemas differ");
    constexpr std::array owned_params{ExpectedParameter{L"InGameplayEffect",L"ObjectProperty"},ExpectedParameter{L"InInstigator",L"ObjectProperty"},
        ExpectedParameter{L"InEffectCauser",L"ObjectProperty"},ExpectedParameter{L"InLevel",L"FloatProperty"},ExpectedParameter{L"ReturnValue",L"StructProperty"}};
    auto owned=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:MakeSpecHandle",owned_params));
    require(owned->at(L"ReturnValue").property->SameType(d->at(L"SpecHandle").property),"owned reduction spec schema differs");
    make_owned_spec=std::move(owned);
    // Publish the fully validated metadata set atomically with respect to the
    // game-thread caller; no engine-owned ParameterFrames persist.
    convert_path=std::move(c);load_class=std::move(l);asc_get=std::move(a);make_spec=std::move(m);set_duration=std::move(d);
    apply_spec=std::move(app);remove_effect=std::move(rem);total_duration=std::move(total);string_buffer=std::move(s);make_path=std::move(p);
}
inline UObject* library(){return find_object(L"/Script/GameplayAbilities.Default__AbilitySystemBlueprintLibrary");}
inline std::wstring object_path(UObject* object) {
    const auto full=object->GetFullName();const auto space=full.find(L' ');
    require(space!=std::wstring::npos,"protection object path unavailable");return full.substr(space+1);
}
inline void copy(const Signature& target,ParameterFrame& target_frame,const wchar_t* target_name,
    const Signature& source,const ParameterFrame& source_frame,const wchar_t* source_name) {
    const auto& to=target.at(target_name);const auto& from=source.at(source_name);
    require(to.property->SameType(from.property),"protection parameter copy type mismatch");
    to.property->CopyCompleteValue(target_frame.address(to),source_frame.address(from));
}
inline std::wstring export_value(const Parameter& parameter,const void* value,UObject* owner) {
    ParameterFrame storage(*string_buffer);auto* address=storage.address(string_buffer->at(L"ReturnValue"));
    require(const_cast<FProperty*>(parameter.property)->ExportText_Direct(*reinterpret_cast<FString*>(address),value,nullptr,owner,0,nullptr),"protection handle export failed");
    const auto* text=reinterpret_cast<const TStringBase<wchar_t>*>(address);const auto length=text->Len();
    require(length>0&&length<4096,"protection handle export length");return std::wstring(**text,length);
}
inline void import_value(const Parameter& parameter,void* address,UObject* owner,const std::wstring& value) {
    const auto* end=parameter.property->ImportText_Direct(value.c_str(),address,owner,0,nullptr);
    require(end&&*end==0,"protection handle import failed");
}
inline UObject* load_definition(const wchar_t* path) {
    auto* existing=FUObjectHashTables::StaticFindObjectByPath(nullptr,path,false,true);
    if(existing&&!existing->IsUnreachable()&&existing->GetFullName()==L"BlueprintGeneratedClass "+std::wstring(path))return existing;
    ParameterFrame p(*make_path),c(*convert_path),l(*load_class);
    const auto input=RingedKnightProtectionStrings::plain_fstring_input(path);
    import_value(make_path->at(L"PathString"),p.address(make_path->at(L"PathString")),nullptr,input);
    const auto* input_string=reinterpret_cast<const TStringBase<wchar_t>*>(p.address(make_path->at(L"PathString")));
    const auto input_length=input_string->Len();require(input_length>=0&&input_length<4096,"protection PathString length invalid");
    const std::wstring imported_input(**input_string,input_length);
    if(!RingedKnightProtectionStrings::path_roundtrip(path,imported_input))throw std::runtime_error(
        "protection PathString roundtrip failed before load: requested="+native_diagnostic_text(path)
        +"; actual="+native_diagnostic_text(imported_input));
    auto* system=find_object(L"/Script/Engine.Default__KismetSystemLibrary");
    system->ProcessEvent(make_path->function,p.data());copy(*convert_path,c,L"SoftClassPath",*make_path,p,L"ReturnValue");
    system->ProcessEvent(convert_path->function,c.data());copy(*load_class,l,L"AssetClass",*convert_path,c,L"ReturnValue");
    system->ProcessEvent(load_class->function,l.data());UObject* definition{};
    std::memcpy(&definition,l.address(load_class->at(L"ReturnValue")),sizeof(definition));
    const bool unreachable=definition&&definition->IsUnreachable();
    const auto actual=definition&&!unreachable?definition->GetFullName():std::wstring{};
    if(!definition||unreachable||actual!=L"BlueprintGeneratedClass "+std::wstring(path))throw std::runtime_error(
        "protection original effect class unavailable: requested="+native_diagnostic_text(path)
        +"; actual="+(actual.empty()?std::string(definition?"<unreachable>":"<null>"):native_diagnostic_text(actual))
        +"; imported_PathString="+native_diagnostic_text(imported_input)
        +"; unreachable="+(unreachable?"true":"false"));
    return definition;
}
inline UObject* actor_asc(UObject* pawn) {
    require(pawn&&!pawn->IsUnreachable(),"protection pawn retired");
    ParameterFrame frame(*asc_get);std::memcpy(frame.address(asc_get->at(L"Actor")),&pawn,sizeof(pawn));
    library()->ProcessEvent(asc_get->function,frame.data());UObject* asc{};
    std::memcpy(&asc,frame.address(asc_get->at(L"ReturnValue")),sizeof(asc));
    require(asc&&!asc->IsUnreachable(),"protection ability system unavailable");return asc;
}
inline void remove_handles(Lease& lease) noexcept {
    if(lease.handles.empty())return;
    if(IsInGameThread()) {
        try {
            auto* asc=find_object(lease.asc.c_str());
            if(!asc->IsUnreachable())for(const auto& text:lease.handles) {
                ParameterFrame frame(*remove_effect);import_value(remove_effect->at(L"Handle"),frame.address(remove_effect->at(L"Handle")),asc,text);
                const std::int32_t all=-1;std::memcpy(frame.address(remove_effect->at(L"StacksToRemove")),&all,sizeof(all));
                asc->ProcessEvent(remove_effect->function,frame.data());++removals;
            }
        }catch(const std::exception& error){++failures;last_error=error.what();}
    }
    // Missing/stale owner or non-game-thread shutdown: specs independently
    // expire on their engine timers. Never dereference a cached raw UObject.
    lease.handles.clear();lease.refreshed=0;
}
inline std::wstring apply(UObject* asc,const wchar_t* definition_path,float seconds) {
    auto* definition=load_definition(definition_path);
    ParameterFrame make(*make_spec),duration(*set_duration),applied(*apply_spec),total(*total_duration);
    std::memcpy(make.address(make_spec->at(L"GameplayEffectClass")),&definition,sizeof(definition));
    const float level=1;std::memcpy(make.address(make_spec->at(L"Level")),&level,sizeof(level));
    // MakeOutgoingSpec supplies its native MakeEffectContext for an empty one.
    asc->ProcessEvent(make_spec->function,make.data());copy(*set_duration,duration,L"SpecHandle",*make_spec,make,L"ReturnValue");
    std::memcpy(duration.address(set_duration->at(L"Duration")),&seconds,sizeof(seconds));
    library()->ProcessEvent(set_duration->function,duration.data());copy(*apply_spec,applied,L"SpecHandle",*set_duration,duration,L"ReturnValue");
    asc->ProcessEvent(apply_spec->function,applied.data());copy(*total_duration,total,L"ActiveHandle",*apply_spec,applied,L"ReturnValue");
    const auto text=export_value(apply_spec->at(L"ReturnValue"),applied.address(apply_spec->at(L"ReturnValue")),asc);
    library()->ProcessEvent(total_duration->function,total.data());float actual{};
    std::memcpy(&actual,total.address(total_duration->at(L"ReturnValue")),sizeof(actual));
    if(!(std::isfinite(actual)&&actual>0&&actual<=seconds+.01f)) {
        Lease rejected;rejected.asc=object_path(asc);rejected.handles.push_back(text);remove_handles(rejected);
        throw std::runtime_error("protection native spec failed finite duration check");
    }
    ++applications;return text;
}
inline std::wstring apply_reduction(UObject* asc,UObject* pawn,float seconds) {
    auto* effect=find_object(reduction_owned);
    require(!effect->IsUnreachable()&&effect->IsRootSet(),"owned reduction effect is not rooted");
    require(effect->GetFullName()==L"GE_ShachiWeapon_HuoLiuXing_Defence_C "+std::wstring(reduction_owned),"owned reduction identity differs");
    ParameterFrame make(*make_owned_spec),duration(*set_duration),applied(*apply_spec),total(*total_duration);
    std::memcpy(make.address(make_owned_spec->at(L"InGameplayEffect")),&effect,sizeof(effect));
    std::memcpy(make.address(make_owned_spec->at(L"InInstigator")),&pawn,sizeof(pawn));
    std::memcpy(make.address(make_owned_spec->at(L"InEffectCauser")),&pawn,sizeof(pawn));
    const float level=1;std::memcpy(make.address(make_owned_spec->at(L"InLevel")),&level,sizeof(level));
    library()->ProcessEvent(make_owned_spec->function,make.data());
    copy(*set_duration,duration,L"SpecHandle",*make_owned_spec,make,L"ReturnValue");
    std::memcpy(duration.address(set_duration->at(L"Duration")),&seconds,sizeof(seconds));
    library()->ProcessEvent(set_duration->function,duration.data());copy(*apply_spec,applied,L"SpecHandle",*set_duration,duration,L"ReturnValue");
    asc->ProcessEvent(apply_spec->function,applied.data());copy(*total_duration,total,L"ActiveHandle",*apply_spec,applied,L"ReturnValue");
    const auto text=export_value(apply_spec->at(L"ReturnValue"),applied.address(apply_spec->at(L"ReturnValue")),asc);
    library()->ProcessEvent(total_duration->function,total.data());float actual{};
    std::memcpy(&actual,total.address(total_duration->at(L"ReturnValue")),sizeof(actual));
    if(!(std::isfinite(actual)&&actual>0&&actual<=seconds+.01f)) {
        Lease rejected;rejected.asc=object_path(asc);rejected.handles.push_back(text);remove_handles(rejected);
        throw std::runtime_error("owned damage reduction is not finite");
    }
    ++applications;return text;
}
inline void refresh(Lease& lease,UObject* pawn,const std::string& token,float duration,bool force) {
    schemas();const auto path=object_path(pawn);const auto now=GetTickCount64();
    if(lease.pawn==path&&lease.token==token&&!force&&!lease.handles.empty()&&now-lease.refreshed<refresh_ms)return;
    auto* asc=actor_asc(pawn);Lease next;next.pawn=path;next.asc=object_path(asc);next.token=token;next.refreshed=now;
    try{
        for(const auto* definition:definitions)next.handles.push_back(apply(asc,definition,duration));
        if(&lease==&action)next.handles.push_back(apply_reduction(asc,pawn,duration));
    }
    catch(...){remove_handles(next);throw;}
    remove_handles(lease);lease=std::move(next);
}
inline void guard_contact(UObject* pawn) {
    std::lock_guard lock(lease_mutex);
    refresh(block,pawn,"RK-Arsenal-block",block_duration,true);
}
inline void cleanup() {
    require(IsInGameThread(),"protection cleanup requires game thread");
    std::lock_guard lock(lease_mutex);remove_handles(action);remove_handles(block);forget();
}
inline std::string run(const std::string& input) {
    require(IsInGameThread()&&input.size()<=8192,"protection requires bounded game-thread JSON");
    const auto data=Json::parse(input);require(data.is_object(),"protection schema");
    std::lock_guard lock(lease_mutex);
    const auto phase=data.value("phase",std::string{});
    schemas();
    if(phase=="capabilities"||phase=="prepare") {
        if(phase=="prepare"){for(const auto* definition:definitions)load_definition(definition);load_definition(reduction_source);}
        return Json{{"api",1},{"finite_specs",true},{"hp_immunity",false},{"action_duration",action_duration},
            {"block_duration",block_duration},{"refresh_ms",refresh_ms},{"action_damage_taken_multiplier",.2}}.dump();
    }
    if(phase=="cleanup") {cleanup();return Json{{"api",1},{"active",false},{"guard_handles",0}}.dump();}
    require(data.contains("active")&&data["active"].is_boolean(),"protection active flag required");
    const auto token=data.at("lease").get<std::string>();require(!token.empty()&&token.size()<=128,"protection lease required");
    if(!data["active"].get<bool>()) {
        if(action.token==token){remove_handles(action);action=Lease{};}
    } else {
        const auto pawn_path=from_utf8(data.at("pawn").get<std::string>());auto* pawn=find_object(pawn_path.c_str());
        refresh(action,pawn,token,action_duration,false);
    }
    return Json{{"api",1},{"active",!action.handles.empty()},{"handles",action.handles.size()},
        {"guard_handles",block.handles.size()},{"applications",applications.load()},{"removals",removals.load()},
        {"failures",failures.load()},{"last_error",last_error},{"hp_immunity",false},{"action_damage_taken_multiplier",.2}}.dump();
}
inline int lua_set(const Lua& lua) {
    try{verify_pinned_abi();require(lua.get_stack_size()==1&&lua.is_string(1),"usage: RK_CombatProtection(json)");lua.set_string(run(std::string(lua.get_string(1))));lua.set_nil();}
    catch(const std::exception& error){
        std::lock_guard lock(lease_mutex);++failures;last_error=error.what();
        if(IsInGameThread()){remove_handles(action);action=Lease{};}else forget();
        lua.set_nil();lua.set_string(std::string("RK protection: ")+error.what());
    }
    return 2;
}
}
