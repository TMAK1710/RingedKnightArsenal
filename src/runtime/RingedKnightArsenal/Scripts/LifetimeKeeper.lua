-- Hold the two inventory DataTables through real engine UPROPERTY references.
-- The native constructor registers this new holder in UE5.7's dirty-root list;
-- UE4SS's legacy SetRootSet wrapper only changes a bit and is not used here.
local M={};M.__index=M
local OUTER='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight'
local NAME='RKA_ItemTables'
local PATH=OUTER..'.'..NAME
local TABLES={
    '/Game/PBZContent/DataTable/UI/DT_WeaponData.DT_WeaponData',
    '/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText',
}
local function valid(value)return value and value:IsValid()==true end
local function same(a,b)return valid(a) and valid(b) and a:GetAddress()==b:GetAddress()end
local function unwrap(value)
    local ok,result=pcall(function()return value:get()end)
    return ok and result or value
end
function M.new(loader,outer)
    assert(type(loader)=='function' and valid(outer),'Inventory lifetime loader/outer required')
    assert(outer:GetFullName()=='Package '..OUTER,'Inventory lifetime outer is not the owned base configuration package')
    return setmetatable({load=loader,outer=outer,prepared=false},M)
end
function M:check()
    assert(IsInGameThread(),'Inventory lifetime check requires game thread')
    assert(self.prepared and valid(self.holder),'Inventory lifetime holder unavailable')
    assert(self.holder:GetFullName()=='ObjectLibrary '..PATH,'Inventory lifetime holder identity changed')
    assert(same(self.holder:GetOuter(),self.outer),'Inventory lifetime holder outer changed')
    assert(self.holder.bUseWeakReferences==false and #self.holder.WeakObjects==0,'Inventory lifetime holder must use strong references')
    assert(#self.holder.Objects==2,'Inventory lifetime strong-reference count changed')
    local addresses={}
    for index,path in ipairs(TABLES)do
        local table=unwrap(self.holder.Objects[index])
        assert(valid(table) and table:GetFullName()=='DataTable '..path,'Inventory lifetime table reference invalid')
        assert(same(table,self.tables[index]),'Inventory lifetime table address changed')
        assert(same(table,self.load(path)),'Inventory lifetime reloaded table is a different object')
        addresses[index]=table:GetAddress()
    end
    return {holder_path=PATH,holder_address=self.holder:GetAddress(),table_addresses=addresses,
        strong_references_verified=true,constructor_root_requested=true,runtime_gc_verified=false}
end
function M:prepare()
    assert(IsInGameThread(),'Inventory lifetime preparation requires game thread')
    if self.prepared then return self:check()end
    local class=StaticFindObject('/Script/Engine.ObjectLibrary')
    assert(valid(class) and class:GetFullName()=='Class /Script/Engine.ObjectLibrary','Native ObjectLibrary class unavailable')
    local holder=StaticFindObject(PATH)
    if not valid(holder)then
        -- RF_Public|RF_Transient|RF_MarkAsRootSet plus internal RootSet enter
        -- actual engine allocation/root registration, not a loader flag patch.
        holder=StaticConstructObject(class,self.outer,FName(NAME),0xC1,0x40000000,false,false)
    end
    assert(valid(holder) and holder:GetFullName()=='ObjectLibrary '..PATH,'Inventory lifetime holder construction failed')
    assert(same(holder:GetOuter(),self.outer),'Inventory lifetime holder was constructed under the wrong outer')
    holder.bUseWeakReferences=false;holder.bHasBlueprintClasses=false
    assert(#holder.WeakObjects==0,'Inventory lifetime holder contains unexpected weak references')
    local tables={self.load(TABLES[1]),self.load(TABLES[2])}
    assert(#holder.Objects==0 or #holder.Objects==2,'Inventory lifetime holder contains unexpected objects')
    if #holder.Objects==0 then
        for index,path in ipairs(TABLES)do
            assert(valid(tables[index]) and tables[index]:GetFullName()=='DataTable '..path,'Inventory lifetime table load failed')
            -- Array<ObjectProperty>, so assigning actual UObject userdata uses
            -- the real reflected object field; no native UStruct is copied.
            holder.Objects[index]=tables[index]
        end
    end
    self.holder=holder;self.tables=tables;self.prepared=true
    return self:check()
end
M.holder_path=PATH
M.table_paths=TABLES
return M
