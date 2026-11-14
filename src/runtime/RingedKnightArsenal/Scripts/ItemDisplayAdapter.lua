-- Native pickup uses ScaleToFitY under IconSizeBox2's 960px height and scale 2.
-- Only fit preview textures that have not already been fitted to the canvas.
-- All native/unknown item IDs retain their original image transform.
local M={};M.__index=M
local SCALE=.4
local UPGRADE_CLASS='WidgetBlueprintGeneratedClass /Game/PBZContent/UI/UINew/System/Upgrade/W_UpgradeActivatableWidget_V1.W_UpgradeActivatableWidget_V1_C'
local NORMAL_TEXT_CLASS='WidgetBlueprintGeneratedClass /Game/PBZContent/UI/UINew/HUD/W_WeaponNormalText.W_WeaponNormalText_C'
local function valid(object)return object and object:IsValid()==true end
local function same(a,b)return valid(a) and valid(b) and a:GetAddress()==b:GetAddress()end
local function vec(value)return {X=value.X,Y=value.Y}end
local function text(value)return type(value)=='string' and value or value:ToString()end
local function restore(entry)
    if valid(entry.image)then
        entry.image:SetRenderScale(entry.scale)
        entry.image:SetRenderTransformPivot(entry.pivot)
        return true
    end
    return false
end
local function unwrap(value)
    local ok,result=pcall(function()return value:get()end);return ok and result or value
end
local function upgrade_owner(object)
    for _=1,32 do
        if not valid(object)then return nil end
        local class=object:GetClass()
        if valid(class)and class:GetFullName()==UPGRADE_CLASS then return object end
        object=object:GetOuter()
    end
end
local function members(box)
    local result={};local entries=box:GetAllEntries()
    for index=1,#entries do
        local entry=unwrap(entries[index])
        if valid(entry)then result[entry:GetAddress()]=entry end
    end
    return result
end
local function owned_text(entry)
    return valid(entry.widget)and valid(entry.widget.TitleText)and valid(entry.widget.DescText)
        and entry.widget.TitleText:GetText():ToString()==entry.title
        and entry.widget.DescText:GetText():ToString()==entry.description
end
local function remove_upgrade(entry)
    if not valid(entry.box)then return 0 end
    local active=members(entry.box);local removed=0
    for _,text_entry in ipairs(entry.texts)do
        -- DynamicEntryBox pools widgets. A recycled pointer with somebody else's
        -- text is no longer ours and must never be removed from a native view.
        if valid(text_entry.widget)and active[text_entry.widget:GetAddress()]and owned_text(text_entry)then
            entry.box:RemoveEntry(text_entry.widget);removed=removed+1
        end
    end
    return removed
end
local function sections(definition)
    local result={}
    if definition.description and definition.description~=''then
        result[#result+1]={title='',description=definition.description}
    end
    for _,move in ipairs(definition.moves or {})do
        if move.title~=''or move.description~=''then result[#result+1]={title=move.title,description=move.description}end
    end
    local values={};for _,section in ipairs(result)do values[#values+1]=section.title..'\0'..section.description end
    return result,table.concat(values,'\0')
end
function M.new(registry)
    assert(type(registry)=='table' and type(registry.get)=='function','Item display requires own weapon registry')
    return setmetatable({registry=registry,entries={},upgrade_entries={}},M)
end
function M:update_upgrade()
    assert(IsInGameThread(),'Upgrade item display requires game thread')
    local seen,added,removed={},0,0
    for _,button in ipairs(FindAllOf('W_ButtonBase_Weapon_C')or{})do
        if valid(button)and not button:GetFullName():find('Default__',1,true)and button:GetSelected()==true then
            local id=text(button.WeaponID);local definition=self.registry:get(id)
            local owner=definition and upgrade_owner(button)
            if valid(owner)and owner:IsActivated()and owner:IsVisible()then
                local detail=owner.W_UnifiedTextDescription_Weapon
                local list=valid(detail)and detail.W_WeaponDetailList
                local box=valid(list)and list.DynamicEntryBox
                if valid(box)then
                    local address=box:GetAddress();seen[address]=true
                    local content,key=sections(definition);local entry=self.upgrade_entries[address]
                    local active=members(box);local intact=entry and same(entry.owner,owner)and entry.id==id and entry.key==key
                    if intact then
                        for _,current in ipairs(entry.texts)do
                            if not valid(current.widget)or not active[current.widget:GetAddress()]or not owned_text(current)then intact=false;break end
                        end
                        intact=intact and #entry.texts==#content
                    end
                    if not intact then
                        if entry then removed=removed+remove_upgrade(entry)end
                        entry={box=box,owner=owner,id=id,key=key,texts={}};self.upgrade_entries[address]=entry
                        local class=list.NormalTextClass
                        assert(valid(class)and class:GetFullName()==NORMAL_TEXT_CLASS,'Unexpected native weapon normal-text class')
                        for _,section in ipairs(content)do
                            local widget=box:BP_CreateEntryOfClass(class)
                            assert(valid(widget),'Owned upgrade text entry creation failed')
                            local ok,why=pcall(function()
                                -- Real W_WeaponNormalText.InitText takes exactly
                                -- (FText TitleText, FText DescText). Its title
                                -- widget already owns the native #E3BF73 gold.
                                widget:InitText(FText(section.title),FText(section.description))
                                widget.TitleText:SetVisibility(section.title==''and 1 or 4)
                            end)
                            if not ok then pcall(box.RemoveEntry,box,widget);error(why)end
                            entry.texts[#entry.texts+1]={widget=widget,title=section.title,description=section.description};added=added+1
                        end
                    end
                end
            end
        end
    end
    for address,entry in pairs(self.upgrade_entries)do
        if not seen[address]then removed=removed+remove_upgrade(entry);self.upgrade_entries[address]=nil end
    end
    return {added=added,removed=removed}
end
function M:update(allow_upgrade)
    assert(IsInGameThread(),'Item display updates require game thread')
    local seen,applied,restored={},{},0
    -- Pre-fitted previews need no pickup transform work. Keep the legacy path
    -- for future registered weapons and for entries whose transforms we own.
    local needs_pickup=next(self.entries)~=nil or type(self.registry.entries)~='table'
    for _,definition in pairs(self.registry.entries or {})do
        if definition.preview_canvas_fitted~=true then needs_pickup=true;break end
    end
    for _,widget in ipairs(needs_pickup and (FindAllOf('W_pickupgear_C')or{})or{})do
        if valid(widget) and not widget:GetFullName():find('Default__',1,true)then
            local address=widget:GetAddress();seen[address]=true
            local image=widget.BigIcon2
            local entry=self.entries[address]
            local definition=self.registry:get(text(widget['Item ID']))
            local needs_fit=definition~=nil and definition.preview_canvas_fitted~=true
            if entry and (not needs_fit or not same(entry.image,image))then
                if restore(entry)then restored=restored+1 end
                self.entries[address]=nil;entry=nil
            end
            if needs_fit and valid(image)then
                if not entry then
                    entry={image=image,widget=widget,scale=vec(image.RenderTransform.Scale),pivot=vec(image.RenderTransformPivot)}
                    self.entries[address]=entry
                end
                image:SetRenderTransformPivot({X=.5,Y=.5})
                image:SetRenderScale({X=SCALE,Y=SCALE})
                applied[#applied+1]=address
            end
        end
    end
    local tracked=0
    for address,entry in pairs(self.entries)do
        if not seen[address] or not valid(entry.widget) or not valid(entry.image)then
            if restore(entry)then restored=restored+1 end
            self.entries[address]=nil
        else tracked=tracked+1 end
    end
    -- Called by the existing 250ms supervisor. Stable upgrade content gets no
    -- writes; only selection/native Reset/close rebuilds or removes our entries.
    -- A stale optional UI object must not suspend combat or equipment routing.
    local ok,upgrade=true,{added=0,removed=0}
    if allow_upgrade~=false then ok,upgrade=pcall(self.update_upgrade,self)
    else
        for address,entry in pairs(self.upgrade_entries)do
            pcall(remove_upgrade,entry);self.upgrade_entries[address]=nil
        end
    end
    self.upgrade_error=not ok and tostring(upgrade)or nil
    return {applied=#applied,restored=restored,tracked=tracked,scale=SCALE,
        upgrade=ok and upgrade or {error=self.upgrade_error}}
end
function M:dispose()
    assert(IsInGameThread(),'Item display cleanup requires game thread')
    local restored=0
    for address,entry in pairs(self.entries)do
        if restore(entry)then restored=restored+1 end
        self.entries[address]=nil
    end
    for address,entry in pairs(self.upgrade_entries)do
        pcall(remove_upgrade,entry);self.upgrade_entries[address]=nil
    end
    return {restored=restored,tracked=0}
end
return M
