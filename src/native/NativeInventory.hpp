#pragma once
// UE 5.7 introduced nonvirtual ICppStructOps and an optional function table.
// Loader 1195's CopyScriptStruct/AddRow wrappers still use the old Copy slot.
// Use the real, typed native Copy handler, then transfer the constructed row
// to the loader's map-only AddRowInternal. No row bytes are shallow-copied.
namespace RingedKnightInventory {
using Json=nlohmann::json;
inline constexpr wchar_t table_path[]=L"/Game/PBZContent/DataTable/UI/DT_WeaponData.DT_WeaponData";
inline constexpr wchar_t struct_path[]=L"/Script/ProjectPBZ.WeaponData";
inline constexpr std::uint32_t copy_flag=1u<<10;
inline constexpr std::size_t fake_header_size=24;
using CopyHandler=bool(*)(void*,const void*,std::int32_t);
// The shipping FName is a trivial eight-byte value; Win64 passes it in RDX.
// Its shape is checked against the actual ItemId NameProperty before use.
using FindRow=std::uint8_t*(*)(const UObject*,std::uint64_t);
using AddRow=void(*)(UObject*,std::uint64_t,std::uint8_t*);
using RemoveRow=void(*)(UObject*,std::uint64_t);

inline void readable(const void* address,std::size_t size,HMODULE image=nullptr,bool executable=false) {
    require(address&&size>0&&size<=(1u<<20),"inventory invalid memory extent");
    MEMORY_BASIC_INFORMATION region{};
    require(VirtualQuery(address,&region,sizeof(region))==sizeof(region)&&region.State==MEM_COMMIT
        &&!(region.Protect&(PAGE_NOACCESS|PAGE_GUARD)),"inventory unreadable native memory");
    const auto start=reinterpret_cast<std::uintptr_t>(address),base=reinterpret_cast<std::uintptr_t>(region.BaseAddress);
    require(start>=base&&size<=region.RegionSize&&start-base<=region.RegionSize-size,"inventory native memory crosses region");
    if(image)require(region.Type==MEM_IMAGE&&region.AllocationBase==image,"inventory native pointer outside pinned image");
    if(executable)require((region.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))!=0,"inventory Copy handler not executable");
}
template<class T> inline T exported(const char* symbol) {
    const auto result=GetProcAddress(GetModuleHandleW(L"UE4SS.dll"),symbol);
    require(result!=nullptr,"inventory required loader export absent");return reinterpret_cast<T>(result);
}
inline void verify_host() {
    static std::once_flag once;std::call_once(once,[]{
        // Exact files verified offline. This bridge contains no game RVA.
        constexpr std::array<unsigned char,32> original{0x7b,0x4f,0xcd,0x28,0x6a,0x35,0x07,0x80,0xfa,0xf0,0x82,0x4d,0x73,0xaa,0x15,0x0b,0x21,0xcb,0xf1,0xbc,0xcd,0xe8,0x83,0xe6,0xa9,0x63,0x86,0xcb,0xe0,0x99,0x73,0xb4};
        constexpr std::array<unsigned char,32> november4{0x44,0x15,0x93,0x3c,0xe3,0x34,0x76,0xf1,0x4c,0x83,0x7a,0xbb,0x61,0xa1,0xb6,0x0a,0xf8,0xb7,0x8c,0xd8,0x17,0x83,0x89,0x65,0x01,0x91,0x3a,0x7a,0xac,0x69,0xe4,0x23};
        const auto hash=file_hash(nullptr);require(hash==original||hash==november4,"inventory unsupported PBZ executable");
    });
}
inline CopyHandler copy_handler(const UScriptStruct::ICppStructOps* ops) {
    require(ops!=nullptr,"inventory row has no native struct operations");
    const void* header=ops->GetFakeVPtr();const auto image=GetModuleHandleW(nullptr);
    readable(header,fake_header_size,image);
    std::uint32_t flags{};std::memcpy(&flags,header,sizeof(flags));
    require((flags&copy_flag)!=0&&(flags&1u)!=0&&(flags&~((1u<<25)-1))==0,"inventory unsupported UE5.7 struct operations");
    unsigned index=0;for(auto bits=flags&(copy_flag-1);bits;bits&=bits-1)++index;
    const auto* slot=static_cast<const std::byte*>(header)+fake_header_size+index*sizeof(void*);
    readable(slot,sizeof(CopyHandler),image);CopyHandler copy{};std::memcpy(&copy,slot,sizeof(copy));
    readable(reinterpret_cast<const void*>(copy),1,image,true);return copy;
}
struct NameValue {
    const FProperty* property{};alignas(8) std::array<std::byte,8> bytes{};
    NameValue(const FProperty* prop,UObject* context,const std::string& value):property(prop) {
        require(property_kind(prop)==L"NameProperty"&&prop->GetSize()==8&&prop->GetArrayDim()==1&&prop->GetMinAlignment()>0&&prop->GetMinAlignment()<=8,"inventory FName ABI changed");
        const auto wide=from_utf8(value);
        prop->InitializeValue(bytes.data());
        try {require(prop->ImportText_Direct(wide.c_str(),bytes.data(),context,0,nullptr)&&reinterpret_cast<const FName*>(bytes.data())->ToString()==wide,"inventory FName import failed");}
        catch(...) {prop->DestroyValue(bytes.data());throw;}
    }
    ~NameValue(){property->DestroyValue(bytes.data());}
    std::uint64_t value()const{std::uint64_t result{};std::memcpy(&result,bytes.data(),8);return result;}
    NameValue(const NameValue&)=delete;
};
struct OwnedRow {
    const UStruct* structure{};void* data{};bool initialized=false;
    ~OwnedRow(){if(data){if(initialized)structure->DestroyStruct(data,1);FMemory::Free(data);}}
    void release(){data=nullptr;}
};
#include "NativeWeaponConfig.hpp"
inline constexpr wchar_t soul_text_table_path[]=L"/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText";
inline constexpr wchar_t soul_text_struct_path[]=L"/Script/ProjectPBZ.WeaponSnapSoulTextData";
inline constexpr wchar_t table_holder_class_path[]=L"/Script/Engine.ObjectLibrary";
inline constexpr wchar_t table_holder_path[]=L"/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.RKA_ItemTables";
enum class HeldTableKind : std::size_t {Weapon=0,SoulText=1};
inline void verify_table_holder(UObject* table,HeldTableKind kind) {
    require(IsInGameThread()&&table&&!table->IsUnreachable(),"inventory table is invalid during holder check");
    auto* schema=find_object(table_holder_class_path);
    require(schema->GetFullName()==std::wstring(L"Class ")+table_holder_class_path,"inventory ObjectLibrary schema changed");
    auto* holder=find_object(table_holder_path);
    // The holder is created through the real engine StaticConstructObject root
    // path. This only verifies its flag; it never uses UE4SS's legacy flag writer,
    // which misses UE5.7's dirty-root registration and was proven insufficient.
    require(!holder->IsUnreachable()&&holder->IsRootSet()&&holder->GetFullName()==std::wstring(L"ObjectLibrary ")+table_holder_path,
        "inventory requires its constructor-rooted ObjectLibrary holder");
    const auto* structure=reinterpret_cast<const UStruct*>(schema);const auto extent=structure->GetPropertiesSize();
    require(extent>0&&extent<=65536,"inventory ObjectLibrary extent changed");
    const auto* weak_mode=field_named(structure,L"bUseWeakReferences");
    require(property_kind(weak_mode)==L"BoolProperty","inventory ObjectLibrary weak mode type changed");
    require(!const_cast<FBoolProperty*>(reinterpret_cast<const FBoolProperty*>(weak_mode))->GetPropertyValue(value_address(weak_mode,holder,extent)),
        "inventory ObjectLibrary uses weak references");
    const auto* objects=field_named(structure,L"Objects");
    require(property_kind(objects)==L"ArrayProperty"&&objects->GetSize()==sizeof(ArrayView),"inventory ObjectLibrary Objects array changed");
    const auto* inner=reinterpret_cast<const FArrayProperty*>(objects)->GetInner();
    require(property_kind(inner)==L"ObjectProperty"&&inner->GetArrayDim()==1&&inner->GetSize()==sizeof(UObject*)&&inner->GetMinAlignment()>0&&inner->GetMinAlignment()<=alignof(UObject*),
        "inventory ObjectLibrary requires a strong ObjectProperty array");
    ArrayView view{};std::memcpy(&view,value_address(objects,holder,extent),sizeof(view));
    require(view.count==2&&view.capacity>=2&&view.capacity<=256,"inventory ObjectLibrary strong-reference count changed");
    readable(view.data,sizeof(UObject*)*2);
    const std::array<const wchar_t*,2> paths{table_path,soul_text_table_path};
    for(std::size_t index=0;index<2;++index) {
        auto* value=reinterpret_cast<const FObjectPropertyBase*>(inner)->GetObjectPropertyValue(static_cast<const std::byte*>(view.data)+index*sizeof(UObject*));
        require(value&&!value->IsUnreachable()&&value->GetFullName()==std::wstring(L"DataTable ")+paths[index],"inventory ObjectLibrary holds an invalid or unexpected table");
        if(index==static_cast<std::size_t>(kind))require(value==table,"inventory ObjectLibrary does not retain this exact table");
    }
    const auto* weak_objects=field_named(structure,L"WeakObjects");
    require(property_kind(weak_objects)==L"ArrayProperty"&&weak_objects->GetSize()==sizeof(ArrayView),"inventory ObjectLibrary WeakObjects type changed");
    ArrayView weak{};std::memcpy(&weak,value_address(weak_objects,holder,extent),sizeof(weak));
    require(weak.count==0&&weak.capacity>=0&&weak.capacity<=256,"inventory ObjectLibrary unexpectedly retains weak objects");
}
#include "NativeWeaponPublish.hpp"
inline std::vector<OwnedRowRecord> owned_soul_text_rows;
inline std::wstring identifier_text(const FProperty* property,const void* address) {
    const auto kind=property_kind(property);
    if(kind==L"NameProperty") {
        require(property->GetSize()==8,"soul text FName size changed");
        return reinterpret_cast<const FName*>(address)->ToString();
    }
    require(kind==L"StrProperty","soul text identifier must be FName or FString");
    const auto* string=reinterpret_cast<const TStringBase<wchar_t>*>(address);
    const auto length=string->Len();require(length>=0&&length<=96,"soul text identifier length changed");
    const auto* characters=**string;readable(characters,(static_cast<std::size_t>(length)+1)*sizeof(wchar_t));
    return std::wstring(characters,length);
}
inline Json soul_text_operation(const Json& request) {
    const auto phase=request.at("phase").get<std::string>();
    require(phase=="soul_clone"||phase=="soul_rollback","soul text unsupported phase");
    const auto id=request.at("id").get<std::string>();
    require(id=="RKA_RingedKnight_Soul","soul text destination outside fixed allowlist");
    auto* table=find_object(soul_text_table_path);
    require(!table->IsUnreachable()&&table->GetFullName()==std::wstring(L"DataTable ")+soul_text_table_path,"soul text table invalid");
    auto* schema=find_object(soul_text_struct_path);
    require(schema->GetFullName()==std::wstring(L"ScriptStruct ")+soul_text_struct_path,"soul text row schema changed");
    const auto* row_property=class_property(L"/Script/Engine.DataTable",L"RowStruct");
    require(property_kind(row_property)==L"ObjectProperty"&&row_property->GetArrayDim()==1,"soul text RowStruct property changed");
    const auto* actual=reinterpret_cast<const FObjectPropertyBase*>(row_property)->GetObjectPropertyValue(reinterpret_cast<const std::byte*>(table)+row_property->GetOffset_Internal());
    require(actual==schema,"soul text table RowStruct mismatch");
    const auto* structure=reinterpret_cast<const UStruct*>(schema);
    const auto* ops=reinterpret_cast<const UScriptStruct*>(schema)->GetCppStructOps();
    const auto size=structure->GetStructureSize(),alignment=static_cast<int>(structure->GetMinAlignment());
    require(ops&&size>0&&size<=65536&&alignment>0&&alignment<=4096&&(alignment&(alignment-1))==0&&ops->GetSize()==size&&ops->GetAlignment()==alignment,"soul text row size/alignment differs");
    const auto copy=copy_handler(ops);
    const auto* identity=field_named(structure,L"ID");
    require(property_kind(identity)==L"NameProperty","soul text ID property type changed");
    auto* flow_schema=find_object(L"/Script/ProjectPBZ.FlowLocText");
    require(flow_schema->GetFullName()==L"ScriptStruct /Script/ProjectPBZ.FlowLocText","soul text FlowLocText schema changed");
    for(const auto* field:{L"SnapSoulName",L"EquipDescription",L"SimpleDesc"})
        verify_struct_property(field_named(structure,field),flow_schema);
    // Row-map keys always use the engine's FName ABI independently of whether
    // this schema's own ID member is an FString or FName.
    auto* weapon_schema=find_object(struct_path);
    require(weapon_schema->GetFullName()==std::wstring(L"ScriptStruct ")+struct_path,"soul text key schema changed");
    const auto* name_property=field_named(reinterpret_cast<const UStruct*>(weapon_schema),L"ItemId",true);
    NameValue destination_name(name_property,table,id);
    const auto find=exported<FindRow>("?FindRowUnchecked@UDataTable@Unreal@RC@@QEBAPEAEVFName@23@@Z");
    const auto remove=exported<RemoveRow>("?RemoveRow@UDataTable@Unreal@RC@@QEAAXVFName@23@@Z");
    if(phase=="soul_rollback") {
        const auto found=std::find_if(owned_soul_text_rows.begin(),owned_soul_text_rows.end(),[&](const auto& entry){return entry.id==id;});
        require(found!=owned_soul_text_rows.end(),"soul rollback requires a row created by this bridge");
        require(find(table,destination_name.value())==found->address,"soul text owned row no longer present");
        remove(table,destination_name.value());require(find(table,destination_name.value())==nullptr,"soul text rollback failed");
        owned_soul_text_rows.erase(found);
        return Json{{"ok",true},{"phase",phase},{"id",id},{"removed",true},{"original_rows_modified",false}};
    }
    const auto requested_source=request.at("base_row").get<std::string>();
    // Current runtime proves the FName display spelling is HeiMoShang. CUE's
    // serializer emits heimoshang; accept that known artifact only, and always
    // construct the engine FName using its actual canonical spelling so the
    // strict NameValue readback does not mistake display casing for another ID.
    require(requested_source=="HeiMoShang"||requested_source=="heimoshang","soul text source outside fixed allowlist");
    NameValue source_name(name_property,table,"HeiMoShang");
    require(find(table,destination_name.value())==nullptr,"soul text destination row already exists");
    auto* source=find(table,source_name.value());readable(source,size);
    require(identifier_text(identity,value_address(identity,source,size))==L"HeiMoShang","soul text source ID mismatch");
    for(const auto& [field,count]:std::array<std::pair<const wchar_t*,int>,3>{{{L"AbilityDesc",5},{L"SnapSoulDesc",0},{L"UpgradeLevelDesc",6}}}) {
        const auto* property=field_named(structure,field);
        require(property_kind(property)==L"ArrayProperty"&&property->GetSize()==sizeof(ArrayView),"soul text description array changed");
        const auto* inner=reinterpret_cast<const FArrayProperty*>(property)->GetInner();
        auto* description_schema=find_object(L"/Script/ProjectPBZ.WeaponAbilityDescEntry");
        require(description_schema->GetFullName()==L"ScriptStruct /Script/ProjectPBZ.WeaponAbilityDescEntry","soul text description schema changed");
        verify_struct_property(inner,description_schema);
        const auto* description_structure=reinterpret_cast<const UStruct*>(description_schema);
        require(inner->GetSize()==description_structure->GetStructureSize()&&inner->GetSize()>0&&inner->GetSize()<=4096,"soul text description element changed");
        verify_struct_property(field_named(description_structure,L"WeaponTitle"),flow_schema);
        verify_struct_property(field_named(description_structure,L"WeaponDesc"),flow_schema);
        ArrayView view{};std::memcpy(&view,value_address(property,source,size),sizeof(view));
        require(view.count==count&&view.capacity>=count&&view.capacity<=256,"soul text description slot count changed");
        if(count)readable(view.data,static_cast<std::size_t>(inner->GetSize())*count);
    }
    OwnedRow row{structure,FMemory::Malloc(size,alignment)};require(row.data,"soul text engine allocation failed");
    structure->InitializeStruct(row.data,1);row.initialized=true;
    require(copy(row.data,source,1),"soul text native struct Copy returned false");
    auto* id_address=value_address(identity,row.data,size);const auto wide=from_utf8(id);
    require(identity->ImportText_Direct(wide.c_str(),id_address,table,0,nullptr)&&identifier_text(identity,id_address)==wide,"soul text owned ID import failed");
    const auto add=exported<AddRow>("?AddRowInternal@UDataTable@Unreal@RC@@IEAAXVFName@23@PEAE@Z");
    auto* inserted=static_cast<std::uint8_t*>(row.data);
    verify_table_holder(table,HeldTableKind::SoulText);
    OwnedRowRecord ownership{id,inserted};owned_soul_text_rows.reserve(owned_soul_text_rows.size()+1);
    try {
        add(table,destination_name.value(),inserted);
        require(find(table,destination_name.value())==inserted,"soul text row insertion failed");
        verify_table_holder(table,HeldTableKind::SoulText);
    }
    catch(...) {if(find(table,destination_name.value())==inserted){row.release();remove(table,destination_name.value());}throw;}
    row.release();
    owned_soul_text_rows.erase(std::remove_if(owned_soul_text_rows.begin(),owned_soul_text_rows.end(),[&](const auto& entry){return entry.id==id;}),owned_soul_text_rows.end());
    owned_soul_text_rows.push_back(std::move(ownership));
    return Json{{"ok",true},{"phase",phase},{"id",id},{"base_row","HeiMoShang"},{"requested_base_row",requested_source},{"deep_copy",true},{"row_size",size},{"retained_by_holder",true},{"holder_path","/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.RKA_ItemTables"},{"table_lifetime","process"},{"granted",false},{"selected",false},{"original_rows_modified",false}};
}
inline std::string run(const std::string& input) {
    require(IsInGameThread()&&input.size()<=4096,"inventory requires bounded game-thread JSON");
    verify_host();const auto request=Json::parse(input);const auto phase=request.at("phase").get<std::string>();
    if(phase=="config_finalize")return config_finalize(request).dump();
    if(phase=="soul_clone"||phase=="soul_rollback")return soul_text_operation(request).dump();
    require(phase=="capabilities"||phase=="clone"||phase=="sanitize"||phase=="publish"||phase=="row_rollback","inventory unsupported phase");
    auto* table=find_object(table_path);require(table->GetFullName()==std::wstring(L"DataTable ")+table_path&&!table->IsUnreachable(),"inventory table invalid");
    auto* schema=find_object(struct_path);require(schema->GetFullName()==std::wstring(L"ScriptStruct ")+struct_path,"inventory row schema changed");
    const auto* row_property=class_property(L"/Script/Engine.DataTable",L"RowStruct");
    require(property_kind(row_property)==L"ObjectProperty"&&row_property->GetArrayDim()==1,"inventory RowStruct property changed");
    const auto* actual=reinterpret_cast<const FObjectPropertyBase*>(row_property)->GetObjectPropertyValue(reinterpret_cast<const std::byte*>(table)+row_property->GetOffset_Internal());
    require(actual==schema,"inventory table does not use WeaponData");
    const auto* structure=reinterpret_cast<const UStruct*>(schema);
    const auto* ops=reinterpret_cast<const UScriptStruct*>(schema)->GetCppStructOps();
    const auto size=structure->GetStructureSize(),alignment=static_cast<int>(structure->GetMinAlignment());
    require(ops&&size>0&&size<=65536&&alignment>0&&alignment<=4096&&(alignment&(alignment-1))==0&&ops->GetSize()==size&&ops->GetAlignment()==alignment,"inventory native row size/alignment differs");
    const auto copy=copy_handler(ops);
    // ItemId is declared by ItemDataBase, WeaponData's reflected superclass.
    // ChildProperties alone does not promise to include inherited fields.
    const auto* item=field_named(structure,L"ItemId",true);
    require(item->GetOffset_Internal()>=0&&item->GetOffset_Internal()+item->GetSize()<=size,"inventory ItemId outside row");
    if(phase=="capabilities")return Json{{"ok",true},{"phase",phase},{"row_size",size},{"row_alignment",alignment},{"copy","UE5.7-native-FakeVTable"},{"insertion","AddRowInternal-owned"},{"sanitize","FProperty-DestroyValue-InitializeValue"},{"config_finalize",true},{"soul_text",true},{"row_rollback",true},{"publish",true},{"publish_host","CL-302256_JKS-17280"},{"owned_table_lifetime","constructor-rooted-ObjectLibrary-strong-reference"}}.dump();
    if(phase=="publish") {
        const auto id=request.at("id").get<std::string>();
        require(std::regex_match(id,std::regex("RKA_[A-Za-z0-9_]{1,80}")),"inventory invalid publish identifier");
        const auto found=std::find_if(owned_rows.begin(),owned_rows.end(),[&](const auto& entry){return entry.id==id;});
        require(found!=owned_rows.end(),"inventory publish requires a row created by this bridge");
        NameValue name(item,table,id);const auto find=exported<FindRow>("?FindRowUnchecked@UDataTable@Unreal@RC@@QEBAPEAEVFName@23@@Z");
        require(find(table,name.value())==found->address,"inventory publish owned row no longer present");
        return publish_owned_row(table,structure,item,id,*found).dump();
    }
    if(phase=="row_rollback") {
        const auto id=request.at("id").get<std::string>();
        require(std::regex_match(id,std::regex("RKA_[A-Za-z0-9_]{1,80}")),"inventory invalid owned rollback identifier");
        const auto found=std::find_if(owned_rows.begin(),owned_rows.end(),[&](const auto& entry){return entry.id==id;});
        require(found!=owned_rows.end(),"inventory rollback requires a row created by this bridge");
        require(!found->published,"inventory cannot remove a row published into the native cache; retain until process exit");
        NameValue name(item,table,id);
        const auto find=exported<FindRow>("?FindRowUnchecked@UDataTable@Unreal@RC@@QEBAPEAEVFName@23@@Z");
        const auto remove=exported<RemoveRow>("?RemoveRow@UDataTable@Unreal@RC@@QEAAXVFName@23@@Z");
        require(find(table,name.value())==found->address,"inventory rollback owned row no longer present");
        remove(table,name.value());require(find(table,name.value())==nullptr,"inventory owned row removal failed");
        owned_rows.erase(found);
        return Json{{"ok",true},{"phase",phase},{"id",id},{"removed",true},{"original_rows_modified",false}}.dump();
    }
    if(phase=="sanitize") {
        const auto id=request.at("id").get<std::string>();
        require(std::regex_match(id,std::regex("RKA_[A-Za-z0-9_]{1,80}")),"inventory invalid owned row identifier");
        const auto found=std::find_if(owned_rows.begin(),owned_rows.end(),[&](const auto& entry){return entry.id==id;});
        require(found!=owned_rows.end(),"inventory sanitize requires a row created by this bridge");
        require(!found->published,"inventory cannot sanitize a published native row");
        NameValue name(item,table,id);const auto find=exported<FindRow>("?FindRowUnchecked@UDataTable@Unreal@RC@@QEBAPEAEVFName@23@@Z");
        auto* data=find(table,name.value());require(data&&data==found->address,"inventory owned row no longer present");
        readable(data,size);const auto targets=sanitize_targets(structure,data,size);
        for(const auto& target:targets)engine_reset(target);
        return Json{{"ok",true},{"phase",phase},{"id",id},{"cleared_properties",targets.size()},{"upgrade_entries",59},{"economy_preserved",true},{"original_rows_modified",false},{"runtime_verified",false}}.dump();
    }
    const auto id=request.at("id").get<std::string>(),base=request.at("base_row").get<std::string>(),base_item=request.at("base_item").get<std::string>();
    require(std::regex_match(id,std::regex("RKA_[A-Za-z0-9_]{1,80}"))&&base.size()<=384&&::RingedKnightInventory::valid_source_row_name(from_utf8(base))&&base_item.size()<=96,"inventory invalid row identifiers");
    NameValue destination_name(item,table,id),source_name(item,table,base);
    const auto find=exported<FindRow>("?FindRowUnchecked@UDataTable@Unreal@RC@@QEBAPEAEVFName@23@@Z");
    const auto add=exported<AddRow>("?AddRowInternal@UDataTable@Unreal@RC@@IEAAXVFName@23@PEAE@Z");
    const auto remove=exported<RemoveRow>("?RemoveRow@UDataTable@Unreal@RC@@QEAAXVFName@23@@Z");
    require(find(table,destination_name.value())==nullptr,"inventory destination row already exists");
    auto* source=find(table,source_name.value());readable(source,size);
    require(reinterpret_cast<const FName*>(source+item->GetOffset_Internal())->ToString()==from_utf8(base_item),"inventory source ItemId mismatch");
    OwnedRow row{structure,FMemory::Malloc(size,alignment)};require(row.data!=nullptr,"inventory engine allocation failed");
    structure->InitializeStruct(row.data,1);row.initialized=true;
    require(copy(row.data,source,1),"inventory native struct Copy returned false");
    require(reinterpret_cast<const FName*>(static_cast<const std::byte*>(row.data)+item->GetOffset_Internal())->ToString()==from_utf8(base_item),"inventory copied ItemId mismatch");
    // AddRowInternal only adds the already-owned row to the map. Its public
    // AddRow overload would re-enter the incompatible loader Copy wrapper.
    auto* inserted=static_cast<std::uint8_t*>(row.data);
    verify_table_holder(table,HeldTableKind::Weapon);
    OwnedRowRecord ownership{id,inserted};owned_rows.reserve(owned_rows.size()+1);
    try {
        add(table,destination_name.value(),inserted);
        require(find(table,destination_name.value())==inserted,"inventory row insertion failed");
        verify_table_holder(table,HeldTableKind::Weapon);
    }
    catch(...) {if(find(table,destination_name.value())==inserted){row.release();remove(table,destination_name.value());}throw;}
    row.release();
    owned_rows.erase(std::remove_if(owned_rows.begin(),owned_rows.end(),[&](const auto& entry){return entry.id==id;}),owned_rows.end());
    owned_rows.push_back(std::move(ownership));
    return Json{{"ok",true},{"phase",phase},{"id",id},{"base_row",base},{"row_size",size},{"deep_copy",true},{"retained_by_holder",true},{"holder_path","/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.RKA_ItemTables"},{"table_lifetime","process"},{"granted",false},{"selected",false}}.dump();
}
inline int lua_inventory(const Lua& lua) {
    try {require(lua.get_stack_size()==1&&lua.is_string(1),"usage: RK_NativeInventory(json)");lua.set_string(run(std::string(lua.get_string(1))));lua.set_nil();}
    catch(const std::exception& error){lua.set_nil();lua.set_string(std::string("RK native inventory: ")+error.what());}return 2;
}
}
