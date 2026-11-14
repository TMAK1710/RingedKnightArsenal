-- Process-lifetime strong references for assets used by combat. Lua userdata is
-- not a UE GC root. Keep this independent of RKA_ItemTables' exact two entries.
local M={};M.__index=M
local OUTER='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight'
local NAME='RKA_CombatAssets'
local PATH=OUTER..'.'..NAME
local MAX_ASSETS=256
local function valid(value)return value and value:IsValid()==true end
local function same(a,b)return valid(a)and valid(b)and a:GetAddress()==b:GetAddress()end
local function unwrap(value)
    local ok,result=pcall(function()return value:get()end)
    return ok and result or value
end
local function identity(value)
    assert(valid(value),'Combat asset reference is invalid')
    local full=value:GetFullName()
    local path=full:match('^[^ ]+ (/.+)$')
    assert(path,'Combat asset has an invalid identity: '..tostring(full))
    return path,full
end
function M.new(outer)
    assert(valid(outer)and outer:GetFullName()=='Package '..OUTER,'Combat asset holder requires the owned base configuration package')
    return setmetatable({outer=outer,entries={},indices={},addresses={}},M)
end
function M:check()
    assert(IsInGameThread(),'Combat asset lifetime check requires game thread')
    assert(self.prepared and valid(self.holder),'Combat asset lifetime holder unavailable')
    assert(self.holder:GetFullName()=='ObjectLibrary '..PATH and same(self.holder:GetOuter(),self.outer),'Combat asset lifetime holder identity changed')
    assert(self.holder.bUseWeakReferences==false and #self.holder.WeakObjects==0,'Combat asset lifetime holder must use strong references')
    assert(#self.entries<=MAX_ASSETS and #self.holder.Objects==#self.entries,'Combat asset lifetime reference count changed')
    for index,entry in ipairs(self.entries)do
        local object=unwrap(self.holder.Objects[index])
        local _,full=identity(object)
        assert(full==entry.full and object:GetAddress()==entry.address,'Combat asset lifetime reference changed: '..entry.path)
    end
    return {holder_path=PATH,holder_address=self.holder:GetAddress(),asset_count=#self.entries,
        strong_references_verified=true,constructor_root_requested=true,runtime_gc_verified=false}
end
function M:prepare()
    assert(IsInGameThread(),'Combat asset lifetime preparation requires game thread')
    if self.prepared then return self:check()end
    local class=StaticFindObject('/Script/Engine.ObjectLibrary')
    assert(valid(class)and class:GetFullName()=='Class /Script/Engine.ObjectLibrary','Native ObjectLibrary class unavailable')
    local holder=StaticFindObject(PATH)
    if not valid(holder)then
        holder=StaticConstructObject(class,self.outer,FName(NAME),0xC1,0x40000000,false,false)
    end
    assert(valid(holder)and holder:GetFullName()=='ObjectLibrary '..PATH and same(holder:GetOuter(),self.outer),'Combat asset lifetime holder construction failed')
    assert(#holder.WeakObjects==0 and #holder.Objects<=MAX_ASSETS,'Combat asset lifetime holder contains unexpected references')
    holder.bUseWeakReferences=false;holder.bHasBlueprintClasses=false
    -- A source reload adopts the existing process-lifetime holder without
    -- clearing objects still referenced by live montages/components.
    for index=1,#holder.Objects do
        local object=unwrap(holder.Objects[index])
        local path,full=identity(object);local address=object:GetAddress()
        assert(not self.indices[path]and not self.addresses[address],'Combat asset lifetime holder contains duplicate references')
        self.entries[index]={path=path,full=full,address=address}
        self.indices[path]=index;self.addresses[address]=path
    end
    self.holder=holder;self.prepared=true
    return self:check()
end
function M:retain(path,object)
    assert(IsInGameThread(),'Combat asset retention requires game thread')
    assert(self.prepared and valid(self.holder),'Combat asset lifetime holder unavailable')
    assert(self.holder:GetFullName()=='ObjectLibrary '..PATH and same(self.holder:GetOuter(),self.outer),
        'Combat asset lifetime holder identity changed')
    assert(self.holder.bUseWeakReferences==false and #self.holder.WeakObjects==0 and #self.holder.Objects==#self.entries,
        'Combat asset lifetime reference storage changed')
    local actual,full=identity(object)
    assert(actual==path,'Combat asset identity mismatch: requested='..tostring(path)..' actual='..full)
    local index=self.indices[path]
    if index then
        local entry=self.entries[index]
        assert(entry.address==object:GetAddress()and entry.full==full and same(unwrap(self.holder.Objects[index]),object),
            'Combat asset native identity changed: requested='..path..' actual='..full)
        return object
    end
    assert(not self.addresses[object:GetAddress()],'Combat asset address is already registered under another path')
    assert(#self.entries<MAX_ASSETS,'Combat asset lifetime limit exceeded')
    index=#self.entries+1
    self.holder.Objects[index]=object
    assert(same(unwrap(self.holder.Objects[index]),object),'Combat asset strong reference assignment failed: '..path)
    self.entries[index]={path=path,full=full,address=object:GetAddress()}
    self.indices[path]=index;self.addresses[object:GetAddress()]=path
    return object
end
M.holder_path=PATH
M.max_assets=MAX_ASSETS
return M
