#pragma once
// Included in RingedKnightInventory after the rooted-table holder verifier.
// Fixed CL-302256 publication into PBZ's shared typed WeaponData cache. Uses
// the game's own ForEachRow callback; never writes TMap/TArray backing bytes.
using WeaponCacheGetter=void*(*)();
using WeaponCacheLookup=std::uint8_t*(*)(void*,std::uint64_t);
using WeaponCacheRowCallback=void(*)(void*,std::uint64_t,const std::uint8_t*);
inline constexpr std::uintptr_t weapon_cache_rva=0xe097b80;
inline constexpr std::uintptr_t weapon_cache_getter_rva=0x698fce0;
inline constexpr std::uintptr_t weapon_cache_lookup_rva=0x6670c40;
inline constexpr std::uintptr_t weapon_cache_callback_rva=0x665e210;
inline constexpr std::uintptr_t weapon_cache_loader_rva=0x699b0a0;
inline constexpr std::uintptr_t weapon_cache_vtable_rva=0xc24f8f8;
template<std::size_t N> inline void cache_code(HMODULE image,std::uintptr_t rva,const unsigned char(&expected)[N]) {
    const auto* address=reinterpret_cast<const unsigned char*>(image)+rva;
    readable(address,N,image,true);require(std::memcmp(address,expected,N)==0,"inventory publish native entry differs from fixed build proof");
}
inline Json publish_owned_row(UObject* table,const UStruct* structure,const FProperty* item,const std::string& id,OwnedRowRecord& ownership) {
    require(IsInGameThread(),"inventory publish requires game thread");
    // Other inventory phases support an older build, but these three native
    // addresses are enabled only for the exact executable inspected here.
    constexpr std::array<unsigned char,32> expected_host{0x44,0x15,0x93,0x3c,0xe3,0x34,0x76,0xf1,0x4c,0x83,0x7a,0xbb,0x61,0xa1,0xb6,0x0a,0xf8,0xb7,0x8c,0xd8,0x17,0x83,0x89,0x65,0x01,0x91,0x3a,0x7a,0xac,0x69,0xe4,0x23};
    static std::once_flag host_once;std::call_once(host_once,[&]{require(file_hash(nullptr)==expected_host,"inventory publish unsupported executable; no cache mutation performed");});
    const auto image=GetModuleHandleW(nullptr);
    constexpr unsigned char getter_prefix[]{0x48,0x83,0xec,0x28,0x8b,0x0d,0x06,0x1c,0x86,0x07,0x65,0x48,0x8b,0x04,0x25,0x58,0x00,0x00,0x00,0xba,0xec,0x1b,0x00,0x00,0x48,0x8b,0x04,0xc8,0x8b,0x04,0x02,0x39};
    constexpr unsigned char lookup_prefix[]{0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48,0x83,0xec,0x20,0x48,0x8b,0xf9,0x48,0x8b,0xda,0x48,0x83,0xc1,0x68,0xe8,0xe2,0x4b,0x00,0xfb,0x84,0xc0};
    constexpr unsigned char callback_prefix[]{0x4c,0x8b,0xdc,0x49,0x89,0x5b,0x10,0x57,0x48,0x83,0xec,0x30,0x49,0x8d,0x40,0x08,0x4d,0x89,0x43,0x18,0x48,0x8b,0xd9,0x49,0x89,0x43,0xe8,0x48,0x8b,0x09,0x49,0x8d};
    cache_code(image,weapon_cache_getter_rva,getter_prefix);cache_code(image,weapon_cache_lookup_rva,lookup_prefix);cache_code(image,weapon_cache_callback_rva,callback_prefix);
    require(item->GetOffset_Internal()==8&&item->GetSize()==8&&property_kind(item)==L"NameProperty","inventory publish ItemId layout differs from callback row+8");
    verify_table_holder(table,HeldTableKind::Weapon);readable(ownership.address,structure->GetStructureSize());
    require(reinterpret_cast<const FName*>(ownership.address+8)->ToString()==from_utf8(id),"inventory publish requires finalized owned ItemId");
    NameValue key(item,table,id);
    const auto get=reinterpret_cast<WeaponCacheGetter>(reinterpret_cast<std::uintptr_t>(image)+weapon_cache_getter_rva);
    const auto lookup=reinterpret_cast<WeaponCacheLookup>(reinterpret_cast<std::uintptr_t>(image)+weapon_cache_lookup_rva);
    const auto callback=reinterpret_cast<WeaponCacheRowCallback>(reinterpret_cast<std::uintptr_t>(image)+weapon_cache_callback_rva);
    void* cache=get();require(cache==reinterpret_cast<const std::byte*>(image)+weapon_cache_rva,"inventory publish unexpected cache address");readable(cache,0x88,image);
    void* vtable{};std::memcpy(&vtable,cache,sizeof(vtable));
    require(vtable==reinterpret_cast<const std::byte*>(image)+weapon_cache_vtable_rva,"inventory publish unexpected cache vtable");readable(vtable,sizeof(void*),image);
    void* loader{};std::memcpy(&loader,vtable,sizeof(loader));
    require(loader==reinterpret_cast<const std::byte*>(image)+weapon_cache_loader_rva,"inventory publish unexpected cache loader");readable(loader,1,image,true);
    // Lookup runs the ordinary native loader if this cache has not yet warmed.
    // If it warmed before registration, only this new owned row is appended.
    auto* existing=lookup(cache,key.value());
    require(reinterpret_cast<const FWeakObjectPtr*>(static_cast<const std::byte*>(cache)+0x68)->Get()==table,"inventory publish cache does not retain this exact table");
    require(!existing||existing==ownership.address,"inventory publish ID already maps to a different row");
    if(existing){ownership.published=true;return Json{{"ok",true},{"phase","publish"},{"id",id},{"published",true},{"already_cached",true},{"cache_pointer_verified",true},{"runtime_verified",false}};}
    ArrayView before{};std::memcpy(&before,static_cast<const std::byte*>(cache)+0x58,sizeof(before));
    require(before.count>=0&&before.count<=512&&before.capacity>=before.count&&before.capacity<=4096,"inventory publish cache row-array extent changed");
    std::vector<const std::uint8_t*> originals;originals.reserve(before.count);
    std::vector<std::uint64_t> original_keys;original_keys.reserve(before.count);
    if(before.count)readable(before.data,static_cast<std::size_t>(before.count)*sizeof(void*));
    for(int i=0;i<before.count;++i){
        const std::uint8_t* pointer{};std::memcpy(&pointer,static_cast<const std::byte*>(before.data)+i*sizeof(void*),sizeof(pointer));
        require(pointer!=ownership.address,"inventory publish detected row cached before finalized ItemId");
        readable(pointer,structure->GetStructureSize());std::uint64_t original_key{};std::memcpy(&original_key,pointer+8,sizeof(original_key));
        require(lookup(cache,original_key)==pointer,"inventory publish existing cache key/pointer mismatch");
        originals.push_back(pointer);original_keys.push_back(original_key);
    }
    // From this point rollback must not destroy the table row: the engine can
    // retain its pointer even if a later verification/JSON allocation fails.
    ownership.published=true;void* context=cache;
    callback(&context,key.value(),ownership.address);
    require(lookup(cache,key.value())==ownership.address,"inventory publish native cache pointer readback failed; owned row retained");
    ArrayView after{};std::memcpy(&after,static_cast<const std::byte*>(cache)+0x58,sizeof(after));
    require(after.count==before.count+1&&after.capacity>=after.count&&after.capacity<=4096,"inventory publish native row-array count changed unexpectedly");
    readable(after.data,static_cast<std::size_t>(after.count)*sizeof(void*));
    for(std::size_t i=0;i<originals.size();++i){const std::uint8_t* pointer{};std::memcpy(&pointer,static_cast<const std::byte*>(after.data)+i*sizeof(void*),sizeof(pointer));require(pointer==originals[i]&&lookup(cache,original_keys[i])==pointer,"inventory publish changed an original cached row key/pointer");}
    const std::uint8_t* appended{};std::memcpy(&appended,static_cast<const std::byte*>(after.data)+before.count*sizeof(void*),sizeof(appended));
    require(appended==ownership.address,"inventory publish native callback appended an unexpected row");
    return Json{{"ok",true},{"phase","publish"},{"id",id},{"published",true},{"already_cached",false},{"cache_pointer_verified",true},{"original_cache_rows",before.count},{"cache_rows_after",after.count},{"original_cache_rows_preserved",true},{"runtime_verified",false}};
}
