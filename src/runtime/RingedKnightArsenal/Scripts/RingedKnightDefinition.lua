-- Only modifies an already deep-cloned, mod-owned DT_WeaponData row.
-- Nested structs are edited in place: no UScriptStruct CopyCompleteValue path.
local folder=assert(debug.getinfo(1,'S').source:sub(2):match('^(.*[/\\])'))
local json=dofile(folder..'dkjson.lua')
local file=assert(io.open(folder..'item-upgrades.json','rb'))
local upgrades=assert(json.decode(file:read('*a')));file:close()
local combat_file=assert(io.open(folder..'combat-profile.json','rb'))
local profile=assert(json.decode(combat_file:read('*a')));combat_file:close()
local M={}
local localized={}
local ID='RKA_RingedKnight'
local ROOT='/HuaShira/Mods/RingedKnight/'
local function asset(name)return ROOT..'UI/'..name..'.'..name end
-- Native weapon-list buttons call GetWeaponWhiteIconFindTable, then draw its
-- result as the visible icon. Despite that field name it needs the colored
-- preview; the separate bloom and upgrade textures remain their own masks.
local textures={icon=asset('T_RKA_Icon'),white=asset('T_RKA_Icon'),
    bloom=asset('T_RKA_White'),render=asset('T_RKA_Render'),upgrade=asset('T_RKA_Upgrade')}
local display_attributes={
    {name='物理攻击',value=profile.base_physical,icon=textures.bloom},
    {name='火焰攻击',value=profile.base_fire,icon='/Game/PBZContent/UI/UINew/System/Character/Texture/T_Attr_FireDmg.T_Attr_FireDmg'},
}
local moves={
    {title='环印剑术',description='初入5林的小骑士，握住它便找回了前世记忆。\n第一次轻攻击的伤害×1.5、削韧900。\n\n防御＋重攻击，投掷附绳黑火焰壶。'},
    {title='二番目の記憶',description='我想起来了，我全都想起来了\n原来...你一直与我同在...'},
    {title='',description=''},
}
local lore='空挥的环直,化成悲哀的赤红之焰,闪耀着红色光芒的环直被取消,一次又一次直到...他停止呼吸...'
local function text(value)return type(value)=='string' and value or value:ToString()end
local function write_text(owner,key,value)
    -- Native UIHelper reads Key directly; other consumers retain ValueCache.
    -- Stable own keys are resolved by LocalizationAdapter without replacing
    -- any original localization entry.
    local field=owner[key]
    if value=='' then field.Namespace='';field.Key=''
    else
        local hash=2166136261
        for i=1,#value do hash=((hash~value:byte(i))*16777619)&0xffffffff end
        local id=string.format('RKA_TXT_%08X',hash)
        assert(localized[id]==nil or localized[id]==value,'Owned localization key collision')
        localized[id]=value;field.Namespace='Default';field.Key=id
    end
    field.ValueCache=FText(value)
end
function M.lookup_text(key)return localized[key]end
function M.localization_entries()local copy={};for key,value in pairs(localized)do copy[key]=value end;return copy end
local function read_text(field)return field.ValueCache:ToString()end
local function path(value)return value:GetObjectID():GetAssetPathName():ToString()end
local function unwrap(value)
    local ok,result=pcall(function()return value:get()end)
    return ok and result or value
end
local function own_asset(value,label)
    assert(type(value)=='string' and value:sub(1,#ROOT)==ROOT and value:find('.',1,true),
        'Expected mod-owned '..label)
    return value
end
local function empty(array,label,clear)
    if #array>0 then
        -- Optional native clear performs reflected per-element destruction first.
        -- UE4SS raw Empty is supported, but has no element-destruction callback.
        if clear then clear(array,label) else array:Empty() end
    end
    assert(#array==0,'Foreign array was not cleared: '..label)
end
local function verify_materials(materials,expected,label)
    local wanted,count={},0
    for _,entry in ipairs(expected)do wanted[entry.Key]=entry.Value end
    materials:ForEach(function(key,value)
        key=text(unwrap(key));value=unwrap(value)
        assert(wanted[key]==value,'Native material cost changed: '..label..'.'..key)
        count=count+1
    end)
    assert(count==#expected,'Native material list changed: '..label)
end
local function soft_function(assets)
    if assets.soft then return assets.soft end
    local system=require('UEHelpers').GetKismetSystemLibrary()
    return function(value)
        local reference=system:Conv_SoftObjPathToSoftObjRef(system:MakeSoftObjectPath(value))
        return reference -- collapse UFunction's multiple returns before assignment
    end
end
function M.definition()
    return {id=ID,base_item='Tang',name='环印骑士剑',description=lore,
        short_introduction=lore,
        snap_soul_name='环印骑士剑',textures=textures,moves=moves,
        display_attributes=display_attributes,
        preview_canvas_fitted=true,
        upgrade_schema=upgrades.schema,base_level=1,max_level=60,
        soul_text_id=ID..'_Soul',apply_soul_row=M.apply_soul_row}
end
function M.upgrade_defs()return upgrades end
function M.apply_row(row,assets)
    assets=assert(assets,'Owned configuration assets are required')
    assert(text(row.ItemId)==ID,'Refusing metadata edits to a non-owned weapon')
    assert(#row.WeaponUpLevelDatas==#upgrades.progression,'Native upgrade schema changed')
    assert(#row.WeaponAbilityDesc==#moves,'Native move-description schema changed')
    local config=own_asset(assert(assets.config),'base configuration')
    local soul_config=own_asset(assert(assets.soul_config),'snap-soul configuration')
    assert(config~=soul_config,'Snap-soul requires a distinct mod-owned configuration')
    local soft=soft_function(assets)
    local function set(owner,key,value)owner[key]=soft(value)end
    local resolved={}
    for key,default in pairs(textures)do resolved[key]=own_asset(assets[key] or default,'UI texture')end
    local def=M.definition()
    write_text(row,'WeaponName',def.name);write_text(row,'EquipDescription',lore)
    write_text(row,'Simple',def.short_introduction);write_text(row,'ShortIntroduction',lore)
    set(row,'WeaponConfig',config)
    -- Native metadata proves WeaponMesh is an Array<SoftObjectProperty>, even
    -- when an extraction serializer flattens its single value. Never assign a
    -- scalar soft reference to this property. Native sanitize clears the array.
    if assets.weapon_mesh then
        empty(row.WeaponMesh,'WeaponMesh',assets.clear_owned_array)
        -- LuaTArray::prepare_to_handle adds a zeroed element; SoftObjectProperty
        -- then assigns a real TSoftObjectPtr. This path never copies UStructs.
        row.WeaponMesh[1]=soft(own_asset(assets.weapon_mesh,'display skeletal mesh'))
        assert(#row.WeaponMesh==1 and path(row.WeaponMesh[1])==assets.weapon_mesh,'Owned display mesh readback failed')
    elseif assets.preserve_hidden_native_mesh~=true then empty(row.WeaponMesh,'WeaponMesh',assets.clear_owned_array) end
    set(row,'Icon',resolved.icon);set(row,'White',resolved.white);set(row,'WhiteBloom',resolved.bloom)
    set(row,'RenderIcon',resolved.render);set(row,'UpgradeIconTexture',resolved.upgrade)
    set(row,'SnapSoulUpgradeIconTexture',resolved.upgrade)
    for index=1,#moves do
        local target=unwrap(row.WeaponAbilityDesc[index])
        write_text(target,'WeaponTitle',moves[index].title);write_text(target,'WeaponDesc',moves[index].description)
    end
    -- Materials, dust, location restrictions and multipliers remain native.
    -- Full custom moves are available at acquisition; Tang unlock GEs must not run.
    for index=1,#row.WeaponUpLevelDatas do
        local target=unwrap(row.WeaponUpLevelDatas[index]);local expected=upgrades.progression[index]
        assert(math.abs(target.AttackMultipliers-expected.AttackMultipliers)<0.0001,
            'Native upgrade multiplier changed at '..index)
        assert(target.ConsumeDust==expected.ConsumeDust and target.bNeedInJHSY==expected.bNeedInJHSY,
            'Native upgrade economy changed at '..index)
        verify_materials(target.Materials,expected.Materials,'upgrade '..index)
        for _,key in ipairs({'GEDatas','SnapSoulGEDatas','PersistentGEDatas','GEUIDataArray'})do
            empty(target[key],'WeaponUpLevelDatas['..index..'].'..key,assets.clear_owned_array)
        end
        local media=target.WeaponMediaData
        set(media,'MediaSource','');set(media,'DisplayTexture',resolved.render)
        set(target,'Thumbnail',resolved.icon)
    end
    local function clear_default(effect)
        set(effect,'SoftClassPtr','');write_text(effect,'WeaponTitle','');write_text(effect,'FlowLocText','')
    end
    clear_default(row.DefaultGEData);clear_default(row.DefaultSnapSoulGEData)
    for _,key in ipairs({'DefaultGEUIData'})do
        empty(row[key],key,assets.clear_owned_array)
    end
    -- Native UnifiedTextDesc renders two fallback placeholder attributes when
    -- this array is empty. Reuse the deep-cloned native structure slots instead
    -- of constructing/copying UStructs through UE4SS. The original UI multiplies
    -- these base values by WeaponUpLevelDatas[level-2].AttackMultipliers; an
    -- empty curve intentionally selects DefaultValue * the current multiplier.
    for _,key in ipairs({'UIAttributeDatas','SnapSoulUIAttributeDatas','ReincarnationUIAttributeDatas'})do
        assert(#row[key]==#display_attributes,'Native two-attribute display schema changed: '..key)
        for index,attribute in ipairs(display_attributes)do
            local entry=unwrap(row[key][index])
            set(entry,'GEIcon',attribute.icon);write_text(entry,'GEDescription',attribute.name)
            entry.DefaultValue=attribute.value;set(entry,'CurveFloat','')
        end
    end
    row.DefaultWeaponMediaDatas:ForEach(function(_,value)
        local media=unwrap(value);set(media,'MediaSource','');set(media,'DisplayTexture',resolved.render)
    end)
    local soul=row.WeaponSnapSoulData
    verify_materials(soul.Materials,upgrades.snap_soul.Materials,'snap soul')
    assert(soul.ConsumeDust==upgrades.snap_soul.ConsumeDust and soul.bNeedInJHSY==upgrades.snap_soul.bNeedInJHSY,
        'Native snap-soul economy changed')
    write_text(soul,'WeaponSnapSoulName',def.snap_soul_name)
    -- Extracted JSON does not encode whether this is FName or FString. Inspect
    -- the real getter: UE4SS NameProperty requires FName userdata specifically.
    local old_text_id=soul.SnapSoulTextID
    if type(old_text_id)=='string' then soul.SnapSoulTextID=ID..'_Soul'
    elseif old_text_id:type()=='FName' then soul.SnapSoulTextID=FName(ID..'_Soul')
    elseif old_text_id:type()=='FString' then soul.SnapSoulTextID=ID..'_Soul'
    else error('Unsupported native snap-soul text identifier type') end
    set(soul,'WeaponConfig',soul_config)
    set(soul,'WeaponIcon',resolved.icon);set(soul,'RenderIcon',resolved.render);set(soul,'WhiteIcon',resolved.white)
    set(soul.WeaponMediaData,'MediaSource','');set(soul.WeaponMediaData,'DisplayTexture',resolved.render)
    for _,key in ipairs({'GameplayEffectDatas','GEUIDataArray','PersistentGEDatas'})do
        empty(soul[key],'WeaponSnapSoulData.'..key,assets.clear_owned_array)
    end
    -- EPMTagsOnSnapSoul is a GameplayTagContainer struct. Native sanitize resets
    -- it through reflected destruction/initialization; it is not a TArray.
    row.bReloadBuffAfterSnapSoul=false
    assert(text(row.ItemId)==ID and read_text(row.WeaponName)==def.name,'Owned metadata readback failed')
    assert(path(row.WeaponConfig)==config and path(soul.WeaponConfig)==soul_config,'Owned configuration readback failed')
    return {id=ID,metadata_applied=true,upgrade_entries=#row.WeaponUpLevelDatas,
        snap_soul_variant=soul_config,original_rows_modified=false,runtime_verified=false}
end
function M.apply_soul_row(row)
    local soul_id=ID..'_Soul';local def=M.definition()
    assert(text(row.ID)==soul_id,'Refusing edits to non-owned soul text')
    assert(#row.AbilityDesc==5 and #row.UpgradeLevelDesc==6 and #row.SnapSoulDesc==0,
        'Native soul text description schema changed')
    write_text(row,'SnapSoulName',def.snap_soul_name)
    write_text(row,'EquipDescription',lore)
    write_text(row,'SimpleDesc',lore)
    for index=1,#row.AbilityDesc do
        local entry=unwrap(row.AbilityDesc[index])
        local description=moves[index] or moves[3]
        write_text(entry,'WeaponTitle',description.title)
        write_text(entry,'WeaponDesc',description.description)
    end
    for index=1,6 do
        local level=index*5;local multiplier=upgrades.progression[level-1].AttackMultipliers
        local entry=unwrap(row.UpgradeLevelDesc[index])
        write_text(entry,'WeaponTitle',tostring(level)..'级强化')
        write_text(entry,'WeaponDesc',string.format('攻击威力提高至初始的%.1f倍，全部剑盾招式继续可用。',multiplier))
    end
    assert(read_text(row.SnapSoulName)==def.snap_soul_name,'Owned soul text readback failed')
    return {id=soul_id,metadata_applied=true,ability_descriptions=5,upgrade_descriptions=6,runtime_verified=false}
end
return M
