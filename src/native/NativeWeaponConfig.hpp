#pragma once
// Included inside RingedKnightInventory. All mutations are confined to
// explicitly owned objects/rows. No native object or row struct is memcpy'd.
inline constexpr wchar_t config_class_path[]=L"/PBZCombatAsset/Prototypes/Config/PBZ_MainWeaponConfig.PBZ_MainWeaponConfig_C";
inline constexpr wchar_t config_base_path[]=L"/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.Weapon_RKA_RingedKnight";
inline constexpr wchar_t config_soul_path[]=L"/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight_Soul.Weapon_RKA_RingedKnight_Soul";
inline constexpr wchar_t config_template_path[]=L"/PBZCombatAsset/ActorData/Players/Hun/Weapon/Tang/Weapon_Hun_Tang.Weapon_Hun_Tang";
inline constexpr wchar_t change_armed_class_path[]=L"/PBZCombatAsset/ActorData/Players/Hun/Abilities/TangBlade/Default/GA_Hun_Tang_ChangeArmed.GA_Hun_Tang_ChangeArmed_C";
inline constexpr wchar_t switch_air_class_path[]=L"/PBZCombatAsset/Prototypes/Abilities/BP_SwitchAttack_DefaultAir.BP_SwitchAttack_DefaultAir_C";
inline constexpr wchar_t sheath_sound_key[]=L"(TagName=\"Weapon.Sound.Unarm.Tang\")";
inline constexpr wchar_t sheath_sound_path[]=L"/Game/Wwise/Events/SFX/Combat/Special/Hero_Special/Hun/Common/Wave_Stab_BaDao/ShouDao/SFX_Combat_Hun_TangBlade_ShouDao";
inline constexpr wchar_t simple_execution_class_path[]=L"/PBZCombatAsset/ActorData/Players/Hun/Abilities/TangBlade/ExE/GA_SimpleExecution_Tang.GA_SimpleExecution_Tang_C";
inline constexpr wchar_t contextual_counter_class_path[]=L"/PBZCombatAsset/ActorData/Mobs/054_ZuoShang/Ability/Abilities/GA_Hun_BDEx_ZuoShang_CA_02_Fixed.GA_Hun_BDEx_ZuoShang_CA_02_Fixed_C";
struct ReflectedValue {const FProperty* property;void* address;};
struct OwnedRowRecord {std::string id;std::uint8_t* address;bool published=false;};
inline std::vector<OwnedRowRecord> owned_rows;
inline std::vector<UObject*> owned_configs;

inline std::string metadata_utf8(std::wstring_view value) {
    if(value.empty())return {};
    require(value.size()<=4096,"owned metadata diagnostic string too long");
    const auto count=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),nullptr,0,nullptr,nullptr);
    require(count>0,"owned metadata invalid diagnostic UTF-16");std::string result(count,'\0');
    require(WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),result.data(),count,nullptr,nullptr)==count,"owned metadata diagnostic UTF-8 conversion failed");
    return result;
}

inline const FProperty* field_named(const UStruct* structure,std::wstring_view wanted,bool inherited=false) {
    std::vector<const UStruct*> seen_structs;
    do {
        require(structure&&seen_structs.size()<32&&std::find(seen_structs.begin(),seen_structs.end(),structure)==seen_structs.end(),"owned metadata cyclic superclass chain");
        seen_structs.push_back(structure);std::vector<const FField*> seen;
        for(auto* field=structure->GetChildProperties();field;field=FieldAccess::next(field)) {
            require(seen.size()<512&&std::find(seen.begin(),seen.end(),field)==seen.end(),"owned metadata cyclic field chain");seen.push_back(field);
            if(field->GetName()==wanted)return reinterpret_cast<const FProperty*>(field);
        }
        structure=inherited?structure->GetSuperStruct():nullptr;
    }while(structure);
    throw std::runtime_error("owned metadata required property missing");
}
inline void* value_address(const FProperty* property,void* container,std::size_t extent) {
    const auto offset=property->GetOffset_Internal(),size=property->GetSize(),alignment=property->GetMinAlignment();
    require(property->GetArrayDim()==1&&offset>=0&&size>0&&alignment>0&&alignment<=4096
        &&(alignment&(alignment-1))==0&&static_cast<std::size_t>(offset)+size<=extent,"owned metadata field outside container");
    auto* result=static_cast<std::byte*>(container)+offset;
    require(reinterpret_cast<std::uintptr_t>(result)%alignment==0,"owned metadata unaligned field");return result;
}
inline ReflectedValue reset_target(const UStruct* schema,void* container,std::size_t extent,std::wstring_view name,std::wstring_view kind,bool inherited=false) {
    std::wstring actual=L"<unresolved>";
    try {
        const auto* property=field_named(schema,name,inherited);actual=property_kind(property);
        require(actual==kind,"property type mismatch");
        return {property,value_address(property,container,extent)};
    }catch(const std::exception& error) {
        throw std::runtime_error("owned metadata field='"+metadata_utf8(name)+"' actual="+metadata_utf8(actual)+
            " expected="+metadata_utf8(kind)+": "+error.what());
    }
}
inline void engine_reset(const ReflectedValue& value) {
    // FProperty performs per-element destruction for arrays/maps (FText, soft
    // pointers, nested structs) and reconstructs a valid empty/default value.
    value.property->DestroyValue(value.address);value.property->InitializeValue(value.address);
}
inline void verify_struct_property(const FProperty* property,UObject* expected) {
    require(property_kind(property)==L"StructProperty","owned metadata expected struct property");
    const auto& handle=reinterpret_cast<const FStructProperty*>(property)->GetStruct();
    std::uintptr_t resolved{};std::memcpy(&resolved,&handle,sizeof(resolved));
    require(resolved==reinterpret_cast<std::uintptr_t>(expected),"owned metadata unresolved or unexpected struct handle");
}
// Reading an engine-owned FScriptArray descriptor is not copying its elements.
// Exact shape is independently asserted by the real UE 5.7 editor module.
struct ArrayView {void* data;std::int32_t count,capacity;};
static_assert(sizeof(ArrayView)==16&&alignof(ArrayView)==8);
inline std::vector<ReflectedValue> sanitize_targets(const UStruct* schema,void* row,std::size_t extent) {
    std::vector<ReflectedValue> targets;
    // Preserve only the three already-deep-cloned two-element presentation
    // arrays. Lua rewrites their text/icons/base values/curves in place before
    // publication; empty arrays trigger PBZ's placeholder 50/25 UI fallback.
    // They contain no gameplay effects. All real effect arrays remain reset.
    for(const auto* name:{L"DefaultGEUIData",L"WeaponMesh"})
        targets.push_back(reset_target(schema,row,extent,name,L"ArrayProperty"));
    targets.push_back(reset_target(schema,row,extent,L"DefaultWeaponMediaDatas",L"MapProperty"));
    const auto* upgrades=field_named(schema,L"WeaponUpLevelDatas");
    require(property_kind(upgrades)==L"ArrayProperty"&&upgrades->GetSize()==sizeof(ArrayView),"owned upgrade array ABI changed");
    auto* upgrade_schema=find_object(L"/Script/ProjectPBZ.WeaponUpLevelData");
    require(upgrade_schema->GetFullName()==L"ScriptStruct /Script/ProjectPBZ.WeaponUpLevelData","owned upgrade schema changed");
    const auto* inner=reinterpret_cast<const FArrayProperty*>(upgrades)->GetInner();verify_struct_property(inner,upgrade_schema);
    const auto* upgrade_structure=reinterpret_cast<const UStruct*>(upgrade_schema);const auto stride=upgrade_structure->GetStructureSize();
    require(stride>0&&stride<=65536&&inner->GetSize()==stride,"owned upgrade element stride changed");
    ArrayView view{};std::memcpy(&view,value_address(upgrades,row,extent),sizeof(view));
    require(view.count==59&&view.capacity>=view.count&&view.capacity<=256,"owned upgrade count differs from verified 60-level path");
    readable(view.data,static_cast<std::size_t>(stride)*view.count);
    for(int i=0;i<view.count;++i)for(const auto* name:{L"GEDatas",L"SnapSoulGEDatas",L"PersistentGEDatas",L"GEUIDataArray"})
        targets.push_back(reset_target(upgrade_structure,static_cast<std::byte*>(view.data)+i*stride,stride,name,L"ArrayProperty"));
    const auto* soul=field_named(schema,L"WeaponSnapSoulData");auto* soul_schema=find_object(L"/Script/ProjectPBZ.WeaponSnapSoulData");
    require(soul_schema->GetFullName()==L"ScriptStruct /Script/ProjectPBZ.WeaponSnapSoulData","owned soul schema changed");verify_struct_property(soul,soul_schema);
    const auto* soul_structure=reinterpret_cast<const UStruct*>(soul_schema);const auto soul_size=soul_structure->GetStructureSize();
    require(soul_size==soul->GetSize(),"owned soul size changed");auto* soul_data=value_address(soul,row,extent);
    for(const auto* name:{L"GameplayEffectDatas",L"GEUIDataArray",L"PersistentGEDatas"})
        targets.push_back(reset_target(soul_structure,soul_data,soul_size,name,L"ArrayProperty"));
    targets.push_back(reset_target(soul_structure,soul_data,soul_size,L"EPMTagsOnSnapSoul",L"StructProperty"));
    return targets;
}
// Split only the outer tuple. Nested values and quoted/escaped text are left
// byte-for-byte intact for the engine's typed ImportText implementation.
inline std::vector<std::wstring> sound_tuple(const std::wstring& text) {
    require(text.size()>=2&&text.front()==L'('&&text.back()==L')',"owned sound map tuple malformed");
    std::vector<std::wstring> parts;std::size_t begin=1;int depth=0;bool quoted=false,escaped=false;
    auto append=[&](std::size_t end) {
        auto first=begin,last=end;while(first<last&&(text[first]==L' '||text[first]==L'\t'))++first;
        while(last>first&&(text[last-1]==L' '||text[last-1]==L'\t'))--last;
        require(first<last,"owned sound map empty tuple element");parts.emplace_back(text.substr(first,last-first));
    };
    if(text.size()==2)return parts;
    for(std::size_t i=1;i+1<text.size();++i) {
        const auto c=text[i];
        if(quoted) {if(escaped)escaped=false;else if(c==L'\\')escaped=true;else if(c==L'\"')quoted=false;continue;}
        if(c==L'\"')quoted=true;
        else if(c==L'(')++depth;
        else if(c==L')'){require(depth>0,"owned sound map tuple underflow");--depth;}
        else if(c==L','&&depth==0){append(i);begin=i+1;}
    }
    require(depth==0&&!quoted&&!escaped,"owned sound map tuple unterminated");append(text.size()-1);return parts;
}
inline std::wstring select_sheath_sound(const std::wstring& text) {
    const auto entries=sound_tuple(text);require(entries.size()<=64,"owned sound map unexpectedly large");
    std::wstring selected;
    for(const auto& entry:entries) {
        const auto pair=sound_tuple(entry);require(pair.size()==2,"owned sound map pair malformed");
        if(pair[0]==sheath_sound_key) {
            require(selected.empty(),"owned sound map duplicate sheath key");
            require(pair[1].find(sheath_sound_path)!=std::wstring::npos,"owned sound map sheath event missing or changed");
            selected=L"("+entry+L")";
        }
    }
    require(!selected.empty(),"owned sound map lacks sheath key");return selected;
}
struct OwnedPropertyValue {
    const FProperty* property;void* address=nullptr;int initialized=0,stride=0;
    explicit OwnedPropertyValue(const FProperty* field,int count=1):property(field) {
        const auto size=property->GetSize(),alignment=property->GetMinAlignment();
        require(count>=1&&count<=2&&size>0&&size<=65536&&alignment>0&&alignment<=4096
            &&(alignment&(alignment-1))==0&&size%alignment==0,"owned property storage schema invalid");
        stride=size;address=_aligned_malloc(static_cast<std::size_t>(size)*count,std::max<int>(alignment,alignof(void*)));
        require(address,"owned property temporary allocation failed");
        try{for(;initialized<count;++initialized)property->InitializeValue(static_cast<std::byte*>(address)+initialized*stride);}
        catch(...){while(initialized)property->DestroyValue(static_cast<std::byte*>(address)+(--initialized)*stride);_aligned_free(address);address=nullptr;throw;}
    }
    OwnedPropertyValue(const OwnedPropertyValue&)=delete;
    OwnedPropertyValue& operator=(const OwnedPropertyValue&)=delete;
    ~OwnedPropertyValue(){if(address){while(initialized)property->DestroyValue(static_cast<std::byte*>(address)+(--initialized)*stride);_aligned_free(address);}}
};
inline std::wstring export_owned_value(const ReflectedValue& value,UObject* owner) {
    constexpr std::array params{ExpectedParameter{L"InDouble",L"DoubleProperty"},ExpectedParameter{L"ReturnValue",L"StrProperty"}};
    static const auto signature=inspect_signature(L"/Script/Engine.KismetStringLibrary:Conv_DoubleToString",params);
    ParameterFrame storage(signature);auto* address=storage.address(signature.at(L"ReturnValue"));
    require(const_cast<FProperty*>(value.property)->ExportText_Direct(*reinterpret_cast<FString*>(address),value.address,nullptr,owner,0,nullptr),
        "owned sound map export failed");
    const auto* text=reinterpret_cast<const TStringBase<wchar_t>*>(address);const auto length=text->Len();
    require(length>=2&&length<=32768,"owned sound map export length invalid");return std::wstring(**text,length);
}
inline Json config_finalize(const Json& request) {
    require(request.at("phase")=="config_finalize","owned configuration unsupported phase");
    auto* schema=find_object(config_class_path);
    require(schema->GetFullName()==std::wstring(L"BlueprintGeneratedClass ")+config_class_path,"owned configuration class changed");
    const auto* structure=reinterpret_cast<const UStruct*>(schema);const auto extent=structure->GetPropertiesSize();
    require(extent>0&&extent<=65536,"owned configuration extent changed");
    const auto path=from_utf8(request.at("path").get<std::string>());
    require(path==config_base_path||path==config_soul_path,"owned configuration path outside fixed allowlist");
    auto* config=find_object(path.c_str());
    require(!config->IsUnreachable()&&config->GetFullName()==std::wstring(L"PBZ_MainWeaponConfig_C ")+path,"owned configuration wrong class or dead object");
    const bool finalized=std::find(owned_configs.begin(),owned_configs.end(),config)!=owned_configs.end();
    auto* source_config=find_object(config_template_path);
    require(!source_config->IsUnreachable()&&source_config->GetFullName()==std::wstring(L"PBZ_MainWeaponConfig_C ")+config_template_path,
        "owned configuration native template changed");
    // This is the original equip-managed draw/sheath ability, including its
    // native armed state and UnarmCancel completion event. Preserve it even
    // when repairing an object finalized by the earlier clearing policy.
    const auto from=reset_target(structure,source_config,extent,L"Change Armed Ability",L"ClassProperty",true);
    const auto to=reset_target(structure,config,extent,L"Change Armed Ability",L"ClassProperty",true);
    require(to.property->SameType(from.property),"owned draw/sheath property schema differs");
    const auto* object_property=reinterpret_cast<const FObjectPropertyBase*>(from.property);
    auto* ability=object_property->GetObjectPropertyValue(from.address);
    require(ability&&!ability->IsUnreachable()&&ability->GetFullName()==std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+change_armed_class_path,
        "owned configuration native draw/sheath ability missing or changed");
    // The native airborne switch commits the target weapon before trying its
    // attack. Keep that entry only; Tang attack specs remain excluded below.
    const auto switch_from=reset_target(structure,source_config,extent,L"Change Weapon Abilities",L"ArrayProperty",true);
    const auto switch_to=reset_target(structure,config,extent,L"Change Weapon Abilities",L"ArrayProperty",true);
    require(switch_to.property->SameType(switch_from.property)&&switch_from.property->GetSize()==sizeof(ArrayView),
        "owned airborne switch array schema differs");
    const auto* switch_inner=reinterpret_cast<const FArrayProperty*>(switch_from.property)->GetInner();
    require(property_kind(switch_inner)==L"ClassProperty"&&switch_inner->GetArrayDim()==1&&switch_inner->GetSize()==sizeof(void*),
        "owned airborne switch element schema changed");
    const auto* switch_object=reinterpret_cast<const FObjectPropertyBase*>(switch_inner);
    auto switch_view=[](const ReflectedValue& value) {
        ArrayView view{};std::memcpy(&view,value.address,sizeof(view));
        require(view.count>=0&&view.count<=64&&view.capacity>=view.count&&view.capacity<=256,"owned airborne switch array invalid");
        if(view.count)readable(view.data,static_cast<std::size_t>(view.count)*sizeof(void*));
        return view;
    };
    const auto source_switches=switch_view(switch_from);
    require(source_switches.count==4,"owned native switch template count changed");
    void* air_source=nullptr;UObject* air_ability=nullptr;
    for(int i=0;i<source_switches.count;++i) {
        auto* element=static_cast<std::byte*>(source_switches.data)+i*sizeof(void*);
        auto* candidate=switch_object->GetObjectPropertyValue(element);
        require(candidate&&!candidate->IsUnreachable(),"owned native switch template contains invalid class");
        if(candidate->GetFullName()==std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+switch_air_class_path) {
            require(!air_source,"owned native switch template contains duplicate airborne entry");air_source=element;air_ability=candidate;
        }
    }
    require(air_source,"owned native switch template lacks airborne entry");
    const auto prior_switches=switch_view(switch_to);
    const bool switch_restored=prior_switches.count!=1||switch_object->GetObjectPropertyValue(prior_switches.data)!=air_ability;
    // Preserve only independent contextual entries: the SimpleExecution event
    // validates its payload target, and the ZuoShang counter requires an exact
    // incoming CounterAbility class. Neither restores ordinary Tang combos.
    const auto equip_from=reset_target(structure,source_config,extent,L"Equip Abilities",L"ArrayProperty",true);
    const auto equip_to=reset_target(structure,config,extent,L"Equip Abilities",L"ArrayProperty",true);
    require(equip_to.property->SameType(equip_from.property)&&equip_from.property->GetSize()==sizeof(ArrayView),
        "owned contextual equip array schema differs");
    const auto* equip_inner=reinterpret_cast<const FArrayProperty*>(equip_from.property)->GetInner();
    require(property_kind(equip_inner)==L"ClassProperty"&&equip_inner->GetArrayDim()==1&&equip_inner->GetSize()==sizeof(void*),
        "owned contextual equip element schema changed");
    const auto* equip_object=reinterpret_cast<const FObjectPropertyBase*>(equip_inner);
    const auto source_equips=switch_view(equip_from);require(source_equips.count==42,"owned equip template count changed");
    const std::array<const wchar_t*,2> contextual_paths{simple_execution_class_path,contextual_counter_class_path};
    std::array<void*,2> contextual_sources{};std::array<UObject*,2> contextual_abilities{};
    for(int i=0;i<source_equips.count;++i) {
        auto* element=static_cast<std::byte*>(source_equips.data)+i*sizeof(void*);
        auto* candidate=equip_object->GetObjectPropertyValue(element);
        require(candidate&&!candidate->IsUnreachable(),"owned equip template contains invalid class");
        for(std::size_t j=0;j<contextual_paths.size();++j)if(candidate->GetFullName()==std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+contextual_paths[j]) {
            require(!contextual_sources[j],"owned equip template contains duplicate contextual entry");
            contextual_sources[j]=element;contextual_abilities[j]=candidate;
        }
    }
    require(contextual_sources[0]&&contextual_sources[1],"owned equip template lacks contextual entry");
    OwnedPropertyValue contextual_values(equip_inner,2);
    for(std::size_t j=0;j<contextual_paths.size();++j) {
        auto* element=static_cast<std::byte*>(contextual_values.address)+j*sizeof(void*);
        equip_inner->CopyCompleteValue(element,contextual_sources[j]);
        require(equip_object->GetObjectPropertyValue(element)==contextual_abilities[j],"owned contextual temporary copy failed");
    }
    auto contextual_matches=[&](const ArrayView& view) {
        if(view.count!=2)return false;
        for(std::size_t j=0;j<contextual_paths.size();++j)
            if(equip_object->GetObjectPropertyValue(static_cast<std::byte*>(view.data)+j*sizeof(void*))!=contextual_abilities[j])return false;
        return true;
    };
    const bool contextual_restored=!contextual_matches(switch_view(equip_to));
    // Arm uses direct sound actions. Of the UnArm timeline's keys, only this
    // key exists in the Tang template. Keep its original typed value exactly;
    // ordinary Tang Stab/Wave sounds must remain absent beside the DS3 audio.
    const auto sound_from=reset_target(structure,source_config,extent,L"Sounds",L"MapProperty",true);
    const auto sound_to=reset_target(structure,config,extent,L"Sounds",L"MapProperty",true);
    require(sound_to.property->SameType(sound_from.property),"owned sheath sound map schema differs");
    const auto sound_text=select_sheath_sound(export_owned_value(sound_from,source_config));
    OwnedPropertyValue sound_value(sound_to.property);
    const auto* sound_end=sound_to.property->ImportText_Direct(sound_text.c_str(),sound_value.address,config,0,nullptr);
    require(sound_end&&*sound_end==0&&export_owned_value({sound_to.property,sound_value.address},config)==sound_text,
        "owned sheath sound temporary import/readback failed");
    const bool sound_restored=export_owned_value(sound_to,config)!=sound_text;
    // Preflight every field before any edit. Preserve equip tags and native
    // damage multiplier maps; remove Tang actions/effects. Keep the template's
    // valid paired execution abilities and display actor/socket contract:
    // the equipment lifecycle hides
    // that actor while mounting the custom models. Empty Display Data has not
    // been proven safe in PBZ's native equipment helpers.
    std::vector<ReflectedValue> targets;
    if(!finalized)for(const auto* name:{L"Equip Effects",L"Owning Effects",L"Owning Abilities",L"Equip Passive Abilities",L"Owning Passive Abilities",L"Linked Anim Layers"})
        targets.push_back(reset_target(structure,config,extent,name,L"ArrayProperty",true));
    if(!finalized)for(const auto* name:{L"Trails",L"Weapon Combos"})targets.push_back(reset_target(structure,config,extent,name,L"MapProperty",true));
    // Copy only the validated UClass property through the engine property API.
    // Never mutate the template or copy an entire native configuration object.
    const bool restored=object_property->GetObjectPropertyValue(to.address)!=ability;
    if(restored)to.property->CopyCompleteValue(to.address,from.address);
    require(object_property->GetObjectPropertyValue(to.address)==ability,"owned draw/sheath ability readback failed");
    if(switch_restored) {
        // A borrowed descriptor selects one original element. FArrayProperty
        // allocates/deep-copies the destination; this view never owns or frees
        // the template's storage and is never used to copy a native UObject.
        const ArrayView selected{air_source,1,1};
        switch_to.property->CopyCompleteValue(switch_to.address,&selected);
    }
    const auto selected_switches=switch_view(switch_to);
    require(selected_switches.count==1&&switch_object->GetObjectPropertyValue(selected_switches.data)==air_ability,
        "owned airborne switch ability readback failed");
    if(contextual_restored) {
        const ArrayView selected{contextual_values.address,2,2};equip_to.property->CopyCompleteValue(equip_to.address,&selected);
    }
    require(contextual_matches(switch_view(equip_to)),"owned contextual equip ability readback failed");
    if(sound_restored)sound_to.property->CopyCompleteValue(sound_to.address,sound_value.address);
    require(export_owned_value(sound_to,config)==sound_text,"owned sheath sound map readback failed");
    for(const auto& target:targets)engine_reset(target);
    if(!finalized)owned_configs.push_back(config);
    return Json{{"ok",true},{"phase","config_finalize"},{"owned",true},{"idempotent",finalized},{"cleared_properties",targets.size()},
        {"change_armed_preserved",true},{"change_armed_restored",restored},{"change_armed_ability",metadata_utf8(change_armed_class_path)},
        {"switch_air_preserved",true},{"switch_air_restored",switch_restored},{"switch_air_ability",metadata_utf8(switch_air_class_path)},
        {"sheath_sound_preserved",true},{"sheath_sound_restored",sound_restored},{"sheath_sound_key","Weapon.Sound.Unarm.Tang"},
        {"contextual_abilities_preserved",true},{"contextual_abilities_restored",contextual_restored},{"contextual_ability_count",2},
        {"uses_native_template",true},{"requires_hidden_native_display",true},{"runtime_verified",false}};
}
