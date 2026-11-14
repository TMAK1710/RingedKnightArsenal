-- Separate native configurations and ID-based equipment routing. Prepare this
-- before native save/load or inventory initialization can resolve the new ID.
-- Construction uses UE4SS 1195's real engine Template parameter (#8), never
-- Lua field copying, AddRow CopyCompleteValue, or mutation of the Tang asset.
local M={};M.__index=M
local ROOT='/HuaShira/Mods/RingedKnight/Data/'
local BASE='Weapon_RKA_RingedKnight'
local SOUL=BASE..'_Soul'
local TEMPLATE='/PBZCombatAsset/ActorData/Players/Hun/Weapon/Tang/Weapon_Hun_Tang.Weapon_Hun_Tang'
local CLASS='/PBZCombatAsset/Prototypes/Config/PBZ_MainWeaponConfig.PBZ_MainWeaponConfig_C'
local function path(name)return ROOT..name..'.'..name end
local function valid(value)return value and value:IsValid() end
local function same(a,b)return valid(a)and valid(b)and a:GetAddress()==b:GetAddress()end
local function unwrap(value)
    local ok,result=pcall(function()return value:get()end)
    return ok and result or value
end
local function name(value)
    value=unwrap(value)
    if type(value)=='string'then return value end
    assert(value and value.type and value:type()=='FName','Equipment API no longer returns FName IDs')
    return value:ToString()
end
function M.new(loader,registry,invoke)
    assert(type(loader)=='function' and type(invoke)=='function','Equipment loader/native bridge required')
    return setmetatable({load=loader,registry=registry,invoke=invoke,configs={},prepared=false},M)
end
function M:prepare()
    assert(IsInGameThread(),'Equipment preparation requires game thread')
    if self.prepared then return self.assets end
    local template=self.load(TEMPLATE)
    assert(valid(template) and template:GetFullName()=='PBZ_MainWeaponConfig_C '..TEMPLATE,'Native weapon template changed')
    local class=template:GetClass()
    assert(valid(class) and class:GetFullName()=='BlueprintGeneratedClass '..CLASS,'Native weapon config class changed')
    local package_class=StaticFindObject('/Script/CoreUObject.Package')
    assert(valid(package_class),'Native UPackage class unavailable')
    self.packages=self.packages or {}
    for _,asset in ipairs({BASE,SOUL})do
        local package_path=ROOT..asset
        -- UE4SS's object-path parser requires Package.Object, so a bare long
        -- package name throws. Recover an existing config's actual outer or
        -- retain the package constructed during a partially failed prepare.
        local config=StaticFindObject(path(asset))
        local package=valid(config) and config:GetOuter() or self.packages[asset]
        if not valid(package)then
            -- RootSet is unchanged in the verified UE5.7 ObjectMacros.h. It
            -- keeps only these two small mod packages/configs alive until exit.
            package=StaticConstructObject(package_class,CreateInvalidObject(),FName(package_path),0x41,0x40000000,false,false)
        end
        assert(valid(package) and package:GetFullName()=='Package '..package_path,'Owned package construction failed')
        self.packages[asset]=package
        if not valid(config)then
            config=StaticConstructObject(class,package,FName(asset),0x41,0x40000000,false,false,template)
        end
        assert(valid(config) and config:GetFullName()=='PBZ_MainWeaponConfig_C '..path(asset),'Owned weapon template construction failed')
        local result=assert(self.invoke({phase='config_finalize',path=path(asset)}),'Owned config finalization failed')
        assert(result.ok and result.owned and result.phase=='config_finalize','Owned config reply mismatch')
        self.configs[asset]=config
    end
    self.assets={config=path(BASE),soul_config=path(SOUL),runtime_config_objects=true,
        runtime_verified=false,requires_prepare_before_load=true,requires_hidden_native_display=true}
    self.prepared=true
    return self.assets
end
function M:sanitize(id)
    assert(IsInGameThread() and self.prepared,'Prepare owned configs before registering metadata')
    assert(self.registry:get(id),'Unknown independent weapon ID')
    local result=assert(self.invoke({phase='sanitize',id=id}),'Owned row sanitization failed')
    assert(result.ok and result.id==id and result.economy_preserved and result.upgrade_entries==59,'Owned sanitization contract changed')
    return result
end
function M:slots(owner)
    local values=owner:GetEquipmentNormalWeapons()
    assert(values and #values>0 and #values<=16,'Native equipped-ID list unavailable')
    local result={}
    for index=1,#values do result[index]=name(values[index]) end
    return result
end
function M:snapshot(owner)
    local index=owner:GetCurrentMainWeaponIndex()
    assert(type(index)=='number' and index%1==0,'Native current slot index changed')
    return {slots=self:slots(owner),current=index,owner=owner:GetAddress()}
end
function M:display_slots(pawn,owner)
    assert(IsInGameThread(),'Equipment display lookup requires game thread')
    local snapshot=self:snapshot(owner)
    local result={current=snapshot.current,slots={}}
    local has_custom=false
    for _,id in ipairs(snapshot.slots)do has_custom=has_custom or self.registry:get(id)~=nil end
    if not has_custom then return result end
    if #snapshot.slots~=2 or snapshot.current<0 or snapshot.current>=2
        or name(owner.CurrentMainWeaponID)~=snapshot.slots[snapshot.current+1]then
        result.pending=true;return result
    end
    local weapons
    -- Read fresh components from this character, not every character in the world.
    local component_class=StaticFindObject('/Script/SGameCombatSystem.CharacterWeaponsComponent')
    assert(valid(component_class),'Native weapon component class unavailable')
    local candidates=pawn:K2_GetComponentsByClass(component_class)
    for index=1,#candidates do
        local candidate=unwrap(candidates[index])
        if valid(candidate)and same(candidate:GetOwner(),pawn)then
            assert(not weapons,'Ambiguous native weapon display component');weapons=candidate
        end
    end
    if not valid(weapons)then result.pending=true;return result end
    local main_tag={TagName=FName('Weapon.Slot.Main')}
    if weapons:GetCurrentWeaponIndex(main_tag,false)~=snapshot.current
        or weapons:GetCurrentWeaponIndex(main_tag,true)~=snapshot.current then
        -- Current/pending index changes are not a loss of per-slot ownership.
        -- Continue validating each equipped slot's exact owned config below;
        -- consumers must not restore an owned proxy just because switching or
        -- execution is still changing the native current index. The pending
        -- flag remains true, and trailing native execution slots stay excluded.
        result.pending=true
    end
    local main
    weapons.RuntimeWeaponData:ForEach(function(slot,value)
        if name(unwrap(slot).TagName)=='Weapon.Slot.Main'then
            assert(not main,'Ambiguous native main weapon display slot');main=unwrap(value)
        end
    end)
    -- Native executions may append a temporary weapon slot and leave it empty
    -- afterward. Only the equipped prefix belongs to our ID mapping; trailing
    -- execution slots must neither invalidate that prefix nor be hidden by us.
    if not main or #main.Weapons<#snapshot.slots or #main.Weapons>16 then result.pending=true;return result end
    for index,id in ipairs(snapshot.slots)do
        local actors={};local verified=true
        if self.registry:get(id)then
            local data=unwrap(main.Weapons[index])
            -- UE4SS's InterfaceProperty getter returns the underlying UObject.
            -- Reject stale slot contents during native replacement rather than
            -- hiding a different weapon which still occupies this index.
            local config=unwrap(data.WeaponConfig)
            verified=same(config,self.configs[BASE])or same(config,self.configs[SOUL])
            if verified then
                for _,field in ipairs({'WeaponActors','Scabbards'})do
                    local values=data[field]
                    assert(#values<=16,'Unexpected native weapon display actor count')
                    for actor_index=1,#values do
                        local actor=unwrap(values[actor_index])
                        if valid(actor)then actors[#actors+1]=actor end
                    end
                end
            end
        end
        result.slots[#result.slots+1]={index=index-1,id=id,actors=actors,verified=verified}
    end
    return result
end
function M:select(owner,id,slot)
    assert(IsInGameThread() and self.prepared,'Equipment selection requires prepared game-thread adapter')
    assert(self.registry:get(id),'Refusing selection of an unregistered custom weapon')
    assert(owner:HasWeapon(FName(id),true),'Independent weapon has not been acquired')
    local before=self:snapshot(owner)
    assert(type(slot)=='number' and slot%1==0 and slot>=0 and slot<#before.slots,'Invalid native zero-based equipment slot')
    -- Current-executable disassembly confirms ReplaceWeaponByIndex writes the
    -- given FName, then the equipment chain takes its ID from the slot array.
    -- OnEquipmentWeapon's tag classifies the slot; it is not a unique item ID.
    local ok,message=xpcall(function()
        owner:ReplaceWeaponByIndex(FName(id),slot)
        owner:SetCurrentWeaponByIndex(slot,true)
        local after=self:slots(owner)
        assert(after[slot+1]==id and name(owner.CurrentMainWeaponID)==id and owner:GetCurrentMainWeaponIndex()==slot,
            'Native ID-based equipment readback failed; independent selection not accepted')
    end,debug.traceback)
    if not ok then
        local restored,restore_error=pcall(function()
            owner:ReplaceWeaponByIndex(FName(before.slots[slot+1]),slot)
            if before.current>=0 and before.current<#before.slots then owner:SetCurrentWeaponByIndex(before.current,true)end
        end)
        error(message..(restored and '\nOriginal slot restored.' or '\nRestoration failed: '..tostring(restore_error)))
    end
    return {id=id,slot=slot,snapshot=before,selected=true,runtime_verified=false}
end
function M:restore(owner,snapshot)
    assert(IsInGameThread() and owner:GetAddress()==snapshot.owner,'Equipment restoration owner changed')
    local current=self:slots(owner)
    assert(#current==#snapshot.slots,'Equipment slot layout changed')
    for index,id in ipairs(current)do
        if self.registry:get(id)then
            local previous=snapshot.slots[index]
            assert(previous~='' and owner:HasWeapon(FName(previous),true),'Previous equipment no longer owned')
            owner:ReplaceWeaponByIndex(FName(previous),index-1)
        end
    end
    if snapshot.current>=0 and snapshot.current<#current then owner:SetCurrentWeaponByIndex(snapshot.current,true)end
    local after=self:slots(owner)
    for index,id in ipairs(after)do assert(not self.registry:get(id),'Custom equipment still referenced after restoration at '..index)end
    return {restored=true,runtime_verified=false}
end
return M
