-- UE4SS 1195 AddRow cannot copy UE5.7 native structs. The dedicated bridge
-- uses WeaponData's real Copy handler and transfers its owned initialized row.
-- No equipment grant or save operation is performed by registration.
local M={};M.__index=M
local table_path='/Game/PBZContent/DataTable/UI/DT_WeaponData.DT_WeaponData'
local soul_table_path='/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText'
local function text(value)return type(value)=='string' and value or value:ToString()end
local function soft_path(value)return value:GetObjectID():GetAssetPathName():ToString()end
local function fingerprint(row)return {id=text(row.ItemId),config=soft_path(row.WeaponConfig)}end
-- invoke(request) must decode RK_NativeInventory's JSON reply and raise on its
-- nil,error return. Keeping encoding at the caller reuses the main dispatcher.
function M.new(loader,registry,invoke,prepare_row)return setmetatable({load=loader,registry=registry,invoke=invoke,prepare_row=prepare_row,owned={}},M)end
function M:register(id)
    assert(IsInGameThread(),'Native inventory registration requires game thread')
    local spec=assert(self.registry:get(id),'Unknown independent weapon')
    local data=self.load(table_path);assert(data:GetRowStruct():GetFullName()=='ScriptStruct /Script/ProjectPBZ.WeaponData','Weapon row schema changed')
    if self.owned[id] then return self.owned[id] end
    local before,base,base_name,count={},nil,nil,0
    data:ForEachRow(function(name,row)
        assert(name~=id,'Independent weapon ID already exists in native table: '..id)
        count=count+1;before[name]=fingerprint(row)
        if text(row.ItemId)==spec.base_item then assert(not base,'Ambiguous base item');base=row;base_name=text(name) end
    end)
    assert(base and count>0 and count<256,'Native weapon table unavailable')
    assert(type(self.invoke)=='function','Native inventory deep-copy bridge was not supplied')
    assert(type(self.prepare_row)=='function','Owned metadata preparation callback is required')
    local cloned=assert(self.invoke({phase='clone',id=id,base_row=base_name,base_item=spec.base_item}),'Native row clone failed')
    assert(cloned.ok and cloned.deep_copy and cloned.id==id,'Native row clone reply mismatch')
    local ok,value=xpcall(function()
        local row=assert(data:FindRow(id),'New weapon row missing')
        row.ItemId=FName(id)
        self.prepare_row(row,spec)
        assert(text(row.ItemId)==id and row.WeaponName.ValueCache:ToString()==spec.name,'Independent weapon row readback failed')
        local after_count=0
        data:ForEachRow(function(name,current)
            after_count=after_count+1
            if name~=id then
                local old=assert(before[name],'Unexpected native row mutation')
                local now=fingerprint(current);assert(old.id==now.id and old.config==now.config,'Original weapon changed: '..name)
            end
        end)
        assert(after_count==count+1,'Native row count changed unexpectedly')
        return {table=data,id=id,original_rows=count,rows_after=after_count,granted=false,selected=false}
    end,debug.traceback)
    if not ok then
        local rolled,rollback_error=pcall(function()
            local reply=self.invoke({phase='row_rollback',id=id})
            assert(reply.ok and reply.removed and reply.id==id,'Owned weapon rollback reply mismatch')
        end)
        error(value..(rolled and '\nOwn weapon row rolled back.' or '\nOwn weapon rollback failed: '..tostring(rollback_error)))
    end
    -- Publication is deliberately outside metadata rollback: once a native
    -- cache retains this pointer, failure must retain the row until exit.
    -- Every metadata/original-row check above has already completed.
    local published=assert(self.invoke({phase='publish',id=id}),'Native owned-row publication failed')
    assert(published.ok and published.id==id and published.published and published.cache_pointer_verified,
        'Native owned-row publication readback failed')
    value.published=true;value.publication=published
    self.owned[id]=value;return value
end
-- Prepare the separate soul UI table before publishing the weapon row. Its row
-- key and ID are independent of the original HeiMoShang text. Native clone owns
-- all arrays/FText through the schema's real UE5.7 Copy handler.
function M:register_soul(id)
    assert(IsInGameThread(),'Soul text registration requires game thread')
    local spec=assert(self.registry:get(id),'Unknown independent weapon')
    local soul_id=assert(spec.soul_text_id,'Independent soul text ID is required')
    assert(soul_id=='RKA_RingedKnight_Soul' and type(spec.apply_soul_row)=='function','Unsupported soul text definition')
    self.soul_owned=self.soul_owned or {}
    if self.soul_owned[soul_id]then return self.soul_owned[soul_id]end
    assert(type(self.invoke)=='function','Native inventory deep-copy bridge was not supplied')
    local data=self.load(soul_table_path)
    assert(data:GetRowStruct():GetFullName()=='ScriptStruct /Script/ProjectPBZ.WeaponSnapSoulTextData','Soul text row schema changed')
    local function prose(field)return text(field.Namespace)..'\0'..text(field.Key)..'\0'..field.ValueCache:ToString()end
    local function snapshot(row)
        local result={id=text(row.ID),name=prose(row.SnapSoulName),description=prose(row.EquipDescription),simple=prose(row.SimpleDesc)}
        for _,key in ipairs({'AbilityDesc','SnapSoulDesc','UpgradeLevelDesc'})do
            result[key]={}
            for index=1,#row[key]do
                local entry=row[key][index]
                result[key][index]=prose(entry.WeaponTitle)..'\0'..prose(entry.WeaponDesc)
            end
        end
        return result
    end
    local function equal(a,b)
        if type(a)~=type(b)then return false end
        if type(a)~='table'then return a==b end
        for key,value in pairs(a)do if not equal(value,b[key])then return false end end
        for key in pairs(b)do if a[key]==nil then return false end end
        return true
    end
    local before,count,base_name={},0,nil
    data:ForEachRow(function(name,row)
        name=text(name);assert(name~=soul_id,'Independent soul text ID already exists')
        before[name]=snapshot(row);count=count+1
        if text(row.ID)=='HeiMoShang'then
            assert(not base_name,'Ambiguous native soul source ID');base_name=name
        end
    end)
    assert(base_name and count>0 and count<256,'Native soul source row unavailable')
    local cloned=assert(self.invoke({phase='soul_clone',id=soul_id,base_row=base_name}),'Native soul clone failed')
    assert(cloned.ok and cloned.deep_copy and cloned.id==soul_id,'Native soul clone reply mismatch')
    local ok,result=xpcall(function()
        local row=assert(data:FindRow(soul_id),'Independent soul text row missing')
        assert(text(row.ID)==soul_id,'Native soul clone ID mismatch')
        local metadata=spec.apply_soul_row(row)
        assert(metadata.metadata_applied and metadata.id==soul_id,'Owned soul metadata readback failed')
        local after_count=0
        data:ForEachRow(function(name,current)
            name=text(name);after_count=after_count+1
            if name~=soul_id then assert(before[name] and equal(before[name],snapshot(current)),'Original soul text changed: '..name)end
        end)
        assert(after_count==count+1,'Soul text table row count changed unexpectedly')
        return {table=data,id=soul_id,original_rows=count,rows_after=after_count,metadata_applied=true,runtime_verified=false}
    end,debug.traceback)
    if not ok then
        local rolled,error_message=pcall(function()
            local reply=self.invoke({phase='soul_rollback',id=soul_id})
            assert(reply.ok and reply.removed,'Soul rollback reply mismatch')
        end)
        error(result..(rolled and '\nOwn soul row rolled back.' or '\nOwn soul rollback failed: '..tostring(error_message)))
    end
    self.soul_owned[soul_id]=result;return result
end
function M:selection(world)
    if not world or not world:IsValid() then self.selection_owner=nil;return end
    local owner=self.selection_owner
    if owner and owner:IsValid() then
        local outer=owner:GetOuter()
        if outer:IsValid() and outer:GetAddress()==world:GetAddress() then
            -- Current weapon ID is never cached: native switches remain immediate.
            return self.registry:get(text(owner.CurrentMainWeaponID)),owner
        end
    end
    self.selection_owner=nil
    for _,candidate in ipairs(FindAllOf('PBZBackPackSubsystem') or {}) do
        if candidate:IsValid() and not candidate:GetFullName():find('Default__',1,true) then
            local outer=candidate:GetOuter()
            if outer:IsValid() and outer:GetAddress()==world:GetAddress() then
                self.selection_owner=candidate
                return self.registry:get(text(candidate.CurrentMainWeaponID)),candidate
            end
        end
    end
end
-- Removal is allowed only after the caller has unequipped/removed this ID from
-- the backpack. Do not erase a referenced row while native UI/equipment use it.
function M:remove_unreferenced(id,is_referenced)
    local entry=self.owned[id];if not entry then return end
    assert(not is_referenced(id),'Cannot remove a referenced independent weapon')
    assert(not entry.published,'Native cache retains the published row; remove the mod after closing the game')
    local reply=self.invoke({phase='row_rollback',id=id})
    assert(reply.ok and reply.removed and reply.id==id,'Owned weapon removal reply mismatch')
    self.owned[id]=nil
end
return M
