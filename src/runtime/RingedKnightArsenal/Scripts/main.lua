local folder=debug.getinfo(1,'S').source:sub(2):match('^(.*[/\\])')
assert(folder,'Cannot locate mod scripts')
if _G.RingedKnightArsenal then
    if _G.RingedKnightArsenal.enabled then _G.RingedKnightArsenal:disable('development reload') end
    if _G.RingedKnightArsenal.dispose_hooks then _G.RingedKnightArsenal:dispose_hooks() end
end
_G.RK_RuntimeGeneration=(_G.RK_RuntimeGeneration or 0)+1
local generation=_G.RK_RuntimeGeneration
local Config=dofile(folder..'Config.lua');local State=dofile(folder..'CombatState.lua');local json=dofile(folder..'dkjson.lua')
local AnimationBlend=dofile(folder..'AnimationBlend.lua')
local ActionDamageReduction=dofile(folder..'ActionDamageReduction.lua')
local IDLE_BLEND_IN=.16
local IDLE_FROM_ACTION_BLEND=.28
local HEAVY_TO_IDLE_BLEND=.45
local HEAVY_TO_MOVEMENT_BLEND=.36
local IDLE_FROM_MOVEMENT_BLEND=.32
local ACTION_TO_MOVEMENT_BLEND=.24
local IDLE_MAX_PLANAR_SPEED=25
local NATIVE_STOP_GRACE=.20
local file=assert(io.open(folder..'combat-profile.json','rb'));local Profile=assert(json.decode(file:read('*a')));file:close()
local art_clips={[Profile.art.start]=true,[Profile.art.heavy]=true,[Profile.art.light]=true}
for _,name in ipairs(Profile.art.light_chain or {})do art_clips[name]=true end
local H=dofile(folder..'PlayerContext.lua').new((require('UEHelpers')));local System=H.GetKismetSystemLibrary()
local Math=StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
local Gameplay=StaticFindObject('/Script/Engine.Default__GameplayStatics')
local NativeFaction=StaticFindObject('/Script/SGameCombatSystem.Default__FactionUtils')
local runtime={enabled=false,projectiles={},effects={},hidden={},seen={},last_keys={},ticks=0,hits=0,throws=0,cancels=0,scheduler_handles={},
    art_test_free=Config.testing_free_art==true}
_G.RingedKnightArsenal=runtime
local function log(message) print('[RingedKnightArsenal] '..message..'\n') end
local function valid(object)return object and object:IsValid() end
local function same(a,b)return valid(a) and valid(b) and a:GetAddress()==b:GetAddress() end
local asset_cache={}
local function load_asset(path)
    local object=asset_cache[path]
    if not valid(object) then
        object=StaticFindObject(path)
        if not valid(object) then
            local reference=System:Conv_SoftObjPathToSoftObjRef(System:MakeSoftObjectPath(path))
            object=System:LoadAsset_Blocking(reference)
        end
        assert(valid(object),'Asset path failed to load: '..path)
    end
    if path:find('/HuaShira/Mods/RingedKnight/Animations/',1,true)==1 then
        assert(object:GetFullName()=='AnimSequence '..path,
            'Animation asset identity mismatch: requested='..path..' actual='..object:GetFullName())
    end
    if runtime.combat_assets then runtime.combat_assets:retain(path,object) end
    asset_cache[path]=object
    return object
end
local function unwrap(value)
    local ok,v=pcall(function()return value:get()end);return ok and v or value
end
local function path(object)return assert(object:GetFullName():match('^[^ ]+ (.+)$'))end
local function vec(v)return {X=v.X,Y=v.Y,Z=v.Z}end
local function arrayvec(v)return {X=v[1],Y=v[2],Z=v[3]}end
local function add(a,b,scale)return {X=a.X+b.X*(scale or 1),Y=a.Y+b.Y*(scale or 1),Z=a.Z+b.Z*(scale or 1)}end
local function subtract(a,b)return {X=a.X-b.X,Y=a.Y-b.Y,Z=a.Z-b.Z}end
local function identity()return {Rotation={X=0,Y=0,Z=0,W=1},Translation={X=0,Y=0,Z=0},Scale3D={X=1,Y=1,Z=1}}end
local function component(actor,class)
    local list=actor:K2_GetComponentsByClass(StaticFindObject(class));return #list==1 and unwrap(list[1]) or nil
end
local function invoke(fn,request)
    assert(type(fn)=='function','Native bridge unavailable')
    local raw,why=fn(json.encode(request));assert(raw,why);local value,_,err=json.decode(raw);assert(value,err);return value
end
local Definition=dofile(folder..'RingedKnightDefinition.lua')
local Upgrade=dofile(folder..'UpgradeAdapter.lua')
local registry=dofile(folder..'WeaponRegistry.lua').new()
registry:add(Definition.definition())
local Equipment=dofile(folder..'EquipmentAdapter.lua')
local EquipmentVisuals=dofile(folder..'EquipmentVisuals.lua')
local Inventory=dofile(folder..'NativeInventory.lua')
local Keeper=dofile(folder..'LifetimeKeeper.lua')
local CombatAssets=dofile(folder..'CombatAssets.lua')
local ArtResource=dofile(folder..'ArtResource.lua')
local ItemDisplay=dofile(folder..'ItemDisplayAdapter.lua')
local Localization=dofile(folder..'LocalizationAdapter.lua')
local BladeFlame=dofile(folder..'BladeFlame.lua')
local ArtFlameTrace=dofile(folder..'ArtFlameTrace.lua')
local art_hit_volume=ArtFlameTrace.scaled_segment(Profile.art.hit_volume,Profile.air_blade.art_reach_scale)
local sword_hit_volume=ArtFlameTrace.scaled_segment({space='sword_local_cm',
    base=Profile.art.hit_volume.base,steel_tip=Profile.art.hit_volume.steel_tip,
    tip_extension_cm=0,radius_cm=Profile.air_blade.radius_cm},Profile.air_blade.normal_reach_scale)
local BombLanding=dofile(folder..'BombLanding.lua')
local CombatMotion=dofile(folder..'CombatMotion.lua')
local WeaponAudio=dofile(folder..'WeaponAudio.lua')
local WeaponSwitch=dofile(folder..'WeaponSwitch.lua')
runtime.registry=registry
runtime.item_display=ItemDisplay.new(registry)
runtime.localization=Localization.new(Definition.lookup_text)
runtime.audio=WeaponAudio.new(load_asset,Profile,log,dofile(folder..'RingedKnightAudio.lua'))
runtime.equipment=Equipment.new(load_asset,registry,function(request)return invoke(RK_NativeInventory,request)end)
runtime.equipment_visuals=EquipmentVisuals.new(load_asset,runtime.equipment,registry,Config.assets.sword)
runtime.inventory=Inventory.new(load_asset,registry,function(request)return invoke(RK_NativeInventory,request)end,function(row,spec)
    runtime.equipment:sanitize(spec.id)
    Definition.apply_row(row,runtime.item_assets)
end)
function runtime:prepare_inventory()
    if self.inventory_ready then self.lifetime:check();self.combat_assets:check();return end
    assert(type(RK_HostCompatible)=='function' and RK_HostCompatible(),'Pinned native bridge unavailable')
    assert(not self.localization_error and self.localization_schema,'Owned text localization hook unavailable')
    self.item_assets=self.equipment:prepare()
    self.lifetime=self.lifetime or Keeper.new(load_asset,self.equipment.configs.Weapon_RKA_RingedKnight:GetOuter())
    self.lifetime:prepare()
    self.combat_assets=self.combat_assets or CombatAssets.new(self.equipment.configs.Weapon_RKA_RingedKnight:GetOuter())
    self.combat_assets:prepare()
    for asset_path,object in pairs(asset_cache)do self.combat_assets:retain(asset_path,object)end
    self.item_assets.weapon_mesh='/HuaShira/Mods/RingedKnight/Meshes/SK_RKA_Display.SK_RKA_Display'
    assert(type(self.inventory.register_soul)=='function','Independent soul text registration unavailable')
    self.inventory:register_soul('RKA_RingedKnight')
    for _,id in ipairs(registry.order)do self.inventory:register(id)end
    self.inventory_ready=true;log('Independent native item metadata/configurations ready before acquisition')
end
function runtime:acquire(owner,id)
    assert(self.inventory_ready and registry:get(id),'Register independent item before acquiring')
    if not owner:HasWeapon(FName(id),true) then owner:AddWeaponItem(FName(id),true,true,false,false) end
    assert(owner:HasWeapon(FName(id),true),'Native independent acquisition failed')
    return {id=id,acquired=true,selected=false}
end
function runtime:native_input_blocked(pc)
    -- Respect the mappings chosen by NBInput (tutorial, sequence, travel, UI).
    -- Never reset its modes or remove another system's input lease.
    local ok,blocked=pcall(function()
        if not valid(pc.PlayerInput) then return false end
        local normal=false
        pc.PlayerInput.AppliedInputContextData:ForEach(function(key)
            local context=unwrap(key)
            if valid(context) and context:GetFullName()=='InputMappingContext /PBZInput/IMC_Default.IMC_Default' then normal=true end
        end)
        return not normal
    end)
    if not ok and not self.input_mode_warning then
        self.input_mode_warning=true;log('Native mapping inspection unavailable: '..tostring(blocked))
    end
    return ok and blocked or false
end
function runtime:menu_blocked(pc,pawn)
    if self.control_lease_guard then
        self.control_lease_guard:update(pc,pawn)
        if self.control_lease_guard:interaction_active(pawn) then return true end
    end
    if not valid(pc) or Gameplay:IsGamePaused(pawn) then return true end
    if self:native_input_blocked(pc) then return true end
    local player=pc.Player
    local router=self.control_lease_guard and self.control_lease_guard.router or self.menu_router
    if not valid(router) or not same(router:GetOuter(),player) then
        router=nil
        for _,candidate in ipairs(FindAllOf('PBZUIActionRouterBase') or {})do
            if valid(candidate) and not candidate:GetFullName():find('Default__',1,true) and same(candidate:GetOuter(),player) then
                router=candidate;break
            end
        end
    end
    self.menu_router=router
    -- Read the current native mode on every call; cache only its owning object.
    if valid(router) and router:GetActiveInputMode()==0 then return true end
    return pc.bShowMouseCursor or pc:IsInputKeyDown({KeyName=FName('Escape')}) or pc:IsInputKeyDown({KeyName=FName('Gamepad_Special_Right')})
end
runtime.weapon_switch=WeaponSwitch.new(runtime.equipment,registry,function()
    if not runtime.inventory_ready or runtime.development_suspended then return end
    local pawn,pc=H.GetPlayer(),H.GetPlayerController()
    if not valid(pawn)or not valid(pc)or runtime:menu_blocked(pc,pawn)then return end
    local attributes=pawn.AttributeSetBase
    if not valid(attributes)or attributes.Health.CurrentValue<=0 then return end
    local _,owner=runtime.inventory:selection(pawn:GetWorld())
    if valid(owner)then return pawn,owner,pc end
end,log)
local function destroy(object)
    if valid(object) then object:K2_DestroyComponent(object) end
end
local hit_actor
function runtime:notify(message)
    log(message)
    if valid(self.pawn) then System:PrintString(self.pawn,message,true,false,{R=1,G=.55,B=.15,A=1},4,FName('RingedKnightStatus')) end
end
function runtime:input_context()
    self.input_subsystem=FindFirstOf('EnhancedInputLocalPlayerSubsystem');assert(valid(self.input_subsystem),'Enhanced Input subsystem unavailable')
    self.context=StaticConstructObject(StaticFindObject('/Script/EnhancedInput.InputMappingContext'),self.pc)
    assert(valid(self.context),'Input context allocation failed')
    local action=StaticConstructObject(StaticFindObject('/Script/EnhancedInput.InputAction'),self.context);assert(valid(action))
    action.bConsumeInput=true;action.bConsumesActionAndAxisMappings=true
    local chord=Config.art_chord
    self.art_chord_ready=false
    local ok,guard_action,chord_action=pcall(function()
        local action_class=StaticFindObject('/Script/EnhancedInput.InputAction')
        local trigger_class=StaticFindObject('/Script/EnhancedInput.InputTriggerChordAction')
        assert(valid(trigger_class),'Engine chord trigger unavailable')
        local guard=StaticConstructObject(action_class,self.context)
        local combined=StaticConstructObject(action_class,self.context)
        assert(valid(guard) and valid(combined),'Chord input allocation failed')
        guard.bConsumeInput=true;guard.bConsumesActionAndAxisMappings=true
        combined.bConsumeInput=true
        local trigger=StaticConstructObject(trigger_class,combined)
        assert(valid(trigger),'Chord trigger allocation failed')
        trigger.ChordAction=guard
        combined.Triggers={trigger}
        return guard,combined
    end)
    local mapped={}
    if ok then
        self.context:MapKey(guard_action,{KeyName=FName(chord.guard)})
        self.context:MapKey(chord_action,{KeyName=FName(chord.attack)})
        mapped[chord.guard]=true
        self.art_chord_ready=true
    else
        log('Art heavy input: '..tostring(guard_action))
    end
    for _,keys in pairs(Config.keys) do for _,key in ipairs(keys) do
        if not mapped[key] then self.context:MapKey(action,{KeyName=FName(key)});mapped[key]=true end
    end end
    -- Consume only our combat keys. Original movement, camera, UI and mapping
    -- contexts are retained; removing this owned context restores their keys.
    self.input_subsystem:AddMappingContext(self.context,10000,{bIgnoreAllPressedKeysUntilRelease=false,bForceImmediately=true,bNotifyUserSettings=false})
end
function runtime:mount(object,attachment)
    object:K2_AttachToComponent(self.mesh,FName(attachment.bone),0,0,0,false)
    local q=attachment.q
    object:K2_SetRelativeTransform({Rotation={X=q[1],Y=q[2],Z=q[3],W=q[4]},Translation=arrayvec(attachment.t),Scale3D=attachment.s and arrayvec(attachment.s) or {X=1,Y=1,Z=1}},false,{},true)
end
function runtime:update_shield(stowed)
    if not valid(self.shield) or (self.shield_stowed==true)==stowed then return end
    self:mount(self.shield,assert(stowed and Profile.attachments.back or Profile.attachments.l,'Shield mount unavailable'))
    self.shield_stowed=stowed
end
function runtime:attach(mesh_asset,attachment)
    local object=self.pawn:AddComponentByClass(StaticFindObject('/Script/Engine.StaticMeshComponent'),true,identity(),false)
    assert(valid(object),'Static mesh component allocation failed')
    self.owned=self.owned or {};self.owned[#self.owned+1]=object
    local asset=load_asset(mesh_asset)
    assert(object:SetStaticMesh(asset),'Mesh assignment failed: '..mesh_asset)
    object:SetCollisionEnabled(0)
    self:mount(object,attachment)
    object:SetVisibility(true,false);return object
end
function runtime:update_equipment_visuals(pawn,owner,drawn)
    self.equipment_visuals:update(pawn,owner,drawn,self.enabled and same(pawn,self.pawn) and self.holstered==true)
    self.hidden=self.equipment_visuals.hidden
end
function runtime:hide_native_weapons()
    self:update_equipment_visuals(self.pawn,self.backpack,true)
end
-- Native weapon ownership and drawn state are independent. Keep the original
-- ChangeArmed ability/timeline in charge of its tags and completion events.
function runtime:sync_armed_state()
    assert(valid(self.weapon_component),'Native armed-state component unavailable')
    local armed=self.weapon_component:IsArmed({TagName=FName('Weapon.Slot.Main')})
    assert(type(armed)=='boolean','Native armed-state contract changed')
    local changing=valid(self.ability_system) and self.ability_system:HasMatchingGameplayTag({TagName=FName('Ability.UpperBody.Hun.ChangeArmed')})
    local yield=not armed or changing
    if yield and not self.holster_yield then
        self:release_combat_pose();self:update_guard_state(false)
        self:handoff_native_input(true)
    end
    local visual_changed=self.holstered~=(not armed)
    self.holstered=not armed;self.arm_changing=changing;self.holster_yield=yield
    if self.pending_draw_entry and changing then self.pending_draw_entry.saw_change=true end
    if visual_changed then
        if valid(self.sword)then self.sword:SetVisibility(armed,false)end
        if valid(self.shield)then self.shield:SetVisibility(armed,false)end
        self:hide_native_weapons()
    end
    return yield
end
function runtime:request_native_draw(input)
    -- The custom weapon has no vanilla attack abilities. A fresh attack while
    -- sheathed asks the ORIGINAL draw ability; never set tags or fake UnarmCancel.
    if not self.holstered or self.arm_changing or self.pending_draw_entry then return false end
    if not (input.attack_pressed or input.triangle_pressed or input.art_pressed)then return false end
    if self:native_special_active() or self:native_dodge_active() or self.animation_blend:native_active() then return false end
    for _,tag in ipairs({'Ability.Action.Execution','Ability.Action.Hun.SimpleExecution','Ability.Executed','CharacterState.Native.Sequence'})do
        if self.ability_system:HasMatchingGameplayTag({TagName=FName(tag)})then return false end
    end
    -- Native input is already handed back while sheathed, but a direct draw
    -- request must still give the original contextual execution wrappers first
    -- refusal before ChangeArmed can cancel an Ability.Action channel.
    if input.triangle_pressed and not input.guard and self.pawn.CharacterMovement:IsMovingOnGround()
        and self:try_execution() then return false end
    local ability=self.active_config['Change Armed Ability']
    assert(valid(ability),'Native draw ability unavailable')
    local accepted=self.ability_system:TryActivateAbilityByClass(ability,true)
    if accepted then
        self.pending_draw_entry={age=0,saw_change=false,receipt={id=self.active_item,
            pawn=self.pawn:GetAddress(),owner=self.backpack:GetAddress()}}
        log('DRAW accepted; queued switch attack')
    end
    return accepted
end
function runtime:update_draw_entry(dt,ready)
    local entry=self.pending_draw_entry
    if not entry then return end
    entry.age=entry.age+dt
    local receipt=entry.receipt
    if entry.age>6 or receipt.id~=self.active_item or not valid(self.pawn) or not valid(self.backpack)
        or receipt.pawn~=self.pawn:GetAddress() or receipt.owner~=self.backpack:GetAddress() then
        self.pending_draw_entry=nil;return
    end
    if self:native_special_active() or self:native_dodge_active() or self.pawn.CharacterMovement:IsFalling() then
        self.pending_draw_entry=nil;return
    end
    for _,tag in ipairs({'Ability.Action.Execution','Ability.Action.Hun.SimpleExecution','Ability.Executed','CharacterState.Native.Sequence'})do
        if self.ability_system:HasMatchingGameplayTag({TagName=FName(tag)})then
            self.pending_draw_entry=nil;return
        end
    end
    if ready and entry.saw_change and not self.holstered and not self.arm_changing
        and not self.native_input_handoff and not self.menu_suspended then
        -- Identical entry to a native weapon-switch receipt: same animation,
        -- damage windows, flame, audio and follow-up/cancel rules.
        self.switch_entry={receipt=receipt,age=0}
        self.pending_draw_entry=nil
        log('DRAW complete; switch attack ready')
    end
end
function runtime:cancel_draw_on_hit()
    self.pending_draw_entry=nil
end
function runtime:lock_movement(lock,preserve_velocity)
    if not valid(self.pc) then return end
    if lock and not self.move_lock and not self.pc:IsMoveInputIgnored() then
        self.pc:SetIgnoreMoveInput(true);self.move_lock=true
        if not preserve_velocity and valid(self.pawn.CharacterMovement) then self.pawn.CharacterMovement:StopMovementImmediately() end
    elseif not lock and self.move_lock then self.pc:SetIgnoreMoveInput(false);self.move_lock=false end
end
function runtime:clear_art_flame()
    if valid(self.art_flame) then pcall(destroy,self.art_flame) end
    self.art_flame=nil
    self.art_flame_started=false
end

function runtime:is_protected_action(name)
    local state=self.state
    name=name or (state and state.clip)
    if art_clips[name]==true or name=='RKSS_RopeBomb' then return true end
    if not state or state.clip~=name then return false end
    for _,stage in ipairs(Profile.heavy.stages)do
        -- Normal heavies slow the Release clip's anticipation on the source
        -- clock. Switch-entry releases explicitly have no charge windup.
        if name==stage.release then
            return state.heavy_windup==true and state.time<Profile.heavy.windup.seconds
        elseif name==stage.charge then
            -- Legacy Charge clips retain their authored charge-release gate;
            -- neither their strike nor their recovery receives this armor.
            return state.time<stage.release_close
        end
    end
    return false
end
function runtime:update_action_protection(active,dt)
    self.protection_renew_in=math.max(0,(self.protection_renew_in or 0)-(dt or 0))
    if not active and not self.action_protection_active then return end
    if active and self.action_protection_active and self.protection_renew_in>0 then return end
    local receipt=invoke(RK_CombatProtection,{active=active,pawn=active and path(self.pawn) or nil,lease='RK-Arsenal-action'})
    assert(receipt.active==active and receipt.hp_immunity==false and receipt.action_damage_taken_multiplier==.2,'Native action protection was not confirmed')
    self.action_protection_active=active
    self.protection_renew_in=active and .1 or 0
end
function runtime:update_guard_state(active)
    -- A released lease cannot block new hits. Only active guarding needs fresh
    -- facing and counters every frame; transitions/disable still reach native.
    if not active and self.guard_bridge_active==false and self.guard_report then return self.guard_report end
    local request={active=active,lease='RK-Arsenal'}
    if active then
        local facing=self.pawn:GetActorForwardVector()
        request.component=path(self.attribute_component);request.x=facing.X;request.y=facing.Y
    end
    local receipt=invoke(RK_ShieldState,request)
    self.guard_bridge_active=active;self.guard_report=receipt
    return receipt
end
function runtime:prune_hit_history()
    local serial=self.state and self.state.serial
    if serial==self.seen_serial then return end
    self.seen_serial=serial
    local prefixes={tostring(serial)..':'}
    if self.state and self.state.plunge_serial then prefixes[#prefixes+1]='plunge:'..self.state.plunge_serial..':' end
    for _,p in ipairs(self.projectiles)do prefixes[#prefixes+1]=p.key..'/' end
    for key in pairs(self.seen)do
        local keep=false
        for _,prefix in ipairs(prefixes)do if key:sub(1,#prefix)==prefix then keep=true;break end end
        if not keep then self.seen[key]=nil end
    end
end
function runtime:restore_animation(blend_out)
    self:clear_art_flame()
    self:update_action_protection(false)
    self:update_shield(false)
    local ok,err=pcall(function()
        if self.animation_blend then self.animation_blend:stop(blend_out) end
    end)
    self.playing=false;self.idle_playing=false;self.last_action_clip=nil;self.motion_basis=nil;self.motion_start_yaw=nil;self.motion_previous={X=0,Y=0,Z=0};self:lock_movement(false)
    self.native_stop_time=nil
    if not ok then error(err) end
end
function runtime:custom_animation(asset,loop,duration,slot,blend_in,requested_path)
    local accepted=self.animation_blend:play(asset,duration,loop,blend_in,slot,requested_path)
    if not accepted then return false end
    self.playing=true
    return true
end
function runtime:update_idle(moving,dt)
    if self.holster_yield or self.holstered then return end
    if self.state.clip or self.native_reaction then return end
    if not moving then
        local velocity=self.pawn:GetVelocity()
        moving=velocity.X*velocity.X+velocity.Y*velocity.Y>IDLE_MAX_PLANAR_SPEED*IDLE_MAX_PLANAR_SPEED
    end
    local heavy_exit=self.last_action_clip=='RKSS_Heavy1Release' or self.last_action_clip=='RKSS_Heavy2Release'
    if moving then
        if self.playing then
            self:restore_animation(self.idle_playing and AnimationBlend.move_blend_out or (heavy_exit and HEAVY_TO_MOVEMENT_BLEND or ACTION_TO_MOVEMENT_BLEND))
        end
        self.native_stop_time=NATIVE_STOP_GRACE
    elseif not self.idle_playing then
        local blend_in=IDLE_BLEND_IN
        if self.playing then
            blend_in=heavy_exit and HEAVY_TO_IDLE_BLEND or IDLE_FROM_ACTION_BLEND
        elseif self.native_stop_time then
            -- Leave the native locomotion graph in control while it finishes braking.
            self.native_stop_time=self.native_stop_time-(dt or 0)
            if self.native_stop_time>0 then return end
            blend_in=IDLE_FROM_MOVEMENT_BLEND
        end
        self.native_stop_time=nil
        local idle=Profile.clips.RKSS_Idle
        if not self:custom_animation(load_asset(idle.asset),true,idle.duration,nil,blend_in,idle.asset) then
            self:begin_native_reaction(true)
            return
        end
        self.idle_playing=true;self:lock_movement(false)
    elseif dt and not self.animation_blend:advance_idle(dt) then
        self:begin_native_reaction()
    end
end
function runtime:release_combat_pose()
    self.state:cancel()
    self:restore_animation(0)
    self:close_held_bomb()
end

function runtime:native_jump_tag()
    return valid(self.ability_system) and self.ability_system:HasMatchingGameplayTag({TagName=FName('Ability.Action.Hun.Jump')})or false
end
function runtime:yield_to_native_air(dt,observed_jump)
    local movement=self.pawn.CharacterMovement
    if not valid(movement) then return false end
    local in_air=movement:IsFalling()
    local landing=false
    if valid(self.ability_system) then
        if observed_jump==nil then observed_jump=self:native_jump_tag()end
        in_air=in_air or observed_jump
        landing=self.ability_system:HasMatchingGameplayTag({TagName=FName('CharacterState.Landing')})
    end
    if in_air then
        if not self.native_airborne then
            self.native_airborne=true
            self.native_landing_time=0
            self:release_combat_pose()
        end
        return true
    end
    if self.native_airborne then
        if not movement:IsMovingOnGround() then return true end
        self.native_airborne=false
        self.native_landing_time=CombatMotion.native_landing_grace
    else
        self.native_landing_time=math.max(0,(self.native_landing_time or 0)-dt)
    end
    if landing and (self.playing or self.state.clip) then self:release_combat_pose() end
    return landing or self.native_landing_time>0
end

function runtime:begin_native_reaction(saw_montage)
    if self.native_reaction then return end
    self:release_combat_pose()
    self.native_reaction={frames=0,released=false,saw_montage=saw_montage==true}
end
function runtime:abort_action(reason)
    self.pending_draw_entry=nil
    local message=tostring(reason)
    local ok,why=pcall(self.begin_native_reaction,self)
    if not ok then self:suspend_initialization(message..'; action cleanup failed: '..tostring(why));return end
    self.switch_entry=nil
    self.action_error=message
    if self.last_action_error~=message then
        self.last_action_error=message
        log('Action interrupted; '..message)
    end
end
function runtime:native_dodge_active()
    if not valid(self.ability_system) or self.dodge_tag_failed then return false end
    local ok,active=pcall(function()return self.ability_system:HasMatchingGameplayTag({TagName=FName('Ability.Action.Hun.Dash')})end)
    if not ok then self.dodge_tag_failed=true;log('Native dodge tag unavailable: '..tostring(active));return false end
    return active==true
end
function runtime:native_special_active()
    if not valid(self.ability_system) then return false end
    -- Verified native traversal, special-performance and narrative ownership tags.
    -- DialogueGraphNew uses FlowIdle before dialogue UI/montage ownership exists.
    -- Some of these use a state machine or sequence rather than a montage.
    for _,tag in ipairs({'Ability.SpecialMove','Ability.Action.Hun.SpecialMove','CharacterState.AbilityState.InSpecialPerform',
        'CharacterState.FlowIdle','CharacterState.FlowIdle.CantBreak','CharacterState.Native.Sequence',
        'Ability.Action.Hun.PerfectDodge'}) do
        if self.ability_system:HasMatchingGameplayTag({TagName=FName(tag)}) then return true end
    end
    return false
end
function runtime:update_native_execution()
    local executing,executed=false,false
    if valid(self.ability_system) then
        executing=self.ability_system:HasMatchingGameplayTag({TagName=FName('Ability.Action.Execution')})
            or self.ability_system:HasMatchingGameplayTag({TagName=FName('Ability.Action.Hun.SimpleExecution')})
        executed=self.ability_system:HasMatchingGameplayTag({TagName=FName('Ability.Executed')})
    end
    if executing or executed then
        self.pending_draw_entry=nil
        if not self.execution_active then self:begin_native_reaction() end
        self.execution_active=true
        self:update_shield(true)
        -- Only the active performer may request another native target. Being
        -- executed and a finished execution's montage tail keep owning the pose.
        return true,executing and not executed
    end
    if self.execution_active then
        if self.animation_blend:native_active() then return true,false end
        self.execution_active=false
        self:update_shield(false)
    end
    return false,false
end
function runtime:handoff_native_input(active)
    if active then
        if self.native_input_handoff then return end
        if valid(self.input_subsystem) and valid(self.context) then
            self.input_subsystem:RemoveMappingContext(self.context,{bForceImmediately=true,bNotifyUserSettings=false})
        end
        self.context=nil;self.native_input_handoff=true;self.switch_entry=nil
    elseif self.native_input_handoff then
        self.native_input_handoff=false
        if not self.menu_suspended then self:input_context() end
        -- The return frame is discarded by tick. Do not replay a QTE press as
        -- a sword command or manufacture a fresh edge from a held button.
        self.last_keys={};self:keys()
    end
end
function runtime:try_execution()
    local execution=self.execution_component
    if not valid(execution) or not valid(self.ability_system) then return false end
    -- All three original wrappers inherit IA_AttackH_Press. The narrower
    -- contextual channels get first refusal before ordinary execution.
    -- Never call PerformExecution directly or grant an unavailable ability.
    local accepted=false
    for _,name in ipairs({'GA_PerformSpecialAttack','GA_PerformShachiWeaponExecution','GA_PerformExecution'}) do
        local ability=StaticFindObject('/PBZCombatAsset/Prototypes/Abilities/'..name..'.'..name..'_C')
        if valid(ability) and self.ability_system:TryActivateAbilityByClass(ability,true) then
            accepted=true;break
        end
    end
    if not accepted then return false end
    self:begin_native_reaction(true)
    self.execution_active=true;self.switch_entry=nil
    self:handoff_native_input(true)
    self:update_shield(true)
    return true
end
function runtime:native_reaction_busy(input)
    local reaction=self.native_reaction;if not reaction then return false end
    reaction.frames=reaction.frames+1
    local held=input.attack or input.triangle or input.guard or input.art
    local pressed=input.attack_pressed or input.triangle_pressed or input.guard_pressed or input.art_pressed
    if not held and not pressed then reaction.released=true end
    local busy=self.animation_blend:native_active()
    if busy or self:native_dodge_active() then reaction.saw_montage=true;return true end
    -- The pre-hook runs before the native function starts its reaction. Never
    -- restore custom idle on that first sample, even if no montage exists yet.
    if reaction.frames==1 then return true end
    if busy==false and (reaction.saw_montage or (reaction.released and pressed)) then
        self.native_reaction=nil;return false
    end
    -- State-machine reactions have no known reflected completion flag. Leave
    -- their native pose/movement intact until keys release and a fresh command.
    return true
end
function runtime:dispose_hooks()
    self:stop_scheduler()
    if self.control_lease_guard then self.control_lease_guard:dispose() end
    if self.localization then self.localization:dispose() end
    if self.weapon_switch then self.weapon_switch:dispose() end
    if self.item_display then
        local display=self.item_display
        if IsInGameThread() then display:dispose()
        else ExecuteInGameThread(function()display:dispose()end) end
    end
    if self.equipment_visuals then
        local visuals=self.equipment_visuals
        if IsInGameThread()then visuals:clear()
        else ExecuteInGameThread(function()visuals:clear()end)end
    end
    if self.inventory_init_hook then
        UnregisterHook(self.inventory_init_hook.name,self.inventory_init_hook.pre,self.inventory_init_hook.post)
        self.inventory_init_hook=nil
    end
    if self.hitreact_hook then
        UnregisterHook(self.hitreact_hook.name,self.hitreact_hook.pre,self.hitreact_hook.post)
        self.hitreact_hook=nil
    end
    if self.native_montage_hook then
        UnregisterHook(self.native_montage_hook.name,self.native_montage_hook.pre,self.native_montage_hook.post)
        self.native_montage_hook=nil
    end
end
function runtime:stop_scheduler()
    self.scheduler_stopped=true
    self.suspend_requested=false
    local handles=self.scheduler_handles;self.scheduler_handles={}
    for _,handle in ipairs(handles)do
        local ok,why=pcall(CancelDelayedAction,handle)
        if not ok then log('Cannot cancel game-thread timer: '..tostring(why)) end
    end
end
function runtime:close_held_bomb()
    destroy(self.held_bomb);self.held_bomb=nil
    if valid(self.sword) then self.sword:SetVisibility(self.holstered~=true,false) end
end
function runtime:suspend_menu()
    self.pending_draw_entry=nil
    self.switch_entry=nil
    if self.menu_suspended then return end
    self.menu_suspended=true
    if self.state then self.state:cancel() end
    self:restore_animation();self:close_held_bomb()
    self:update_guard_state(false)
    if valid(self.input_subsystem) and valid(self.context) then
        self.input_subsystem:RemoveMappingContext(self.context,{bForceImmediately=true,bNotifyUserSettings=false})
    end
    self.context=nil;self.last_keys={}
end
function runtime:resume_menu()
    if not self.menu_suspended then return end
    if not self.native_input_handoff and not self.holster_yield then self:input_context() end
    self.menu_suspended=false;self.last_keys={};self:keys()
    self.discard_combat_input_once=true
    self.last_game_time=Gameplay:GetTimeSeconds(self.pawn)
    self.health=self.pawn.AttributeSetBase.Health.CurrentValue
end
function runtime:disable(reason)
    self.pending_draw_entry=nil
    self.holstered=nil;self.holster_yield=nil;self.arm_changing=nil;self.weapon_component=nil
    local had_combat_state=self.enabled or self.state~=nil
    self.enabled=false
    self.switch_entry=nil
    self.menu_suspended=false
    self.native_input_handoff=false
    self.discard_combat_input_once=false
    self.native_reaction=nil
    self.execution_active=false
    self.native_airborne=false;self.native_landing_time=0
    self.last_native_jump_tag=nil
    self.plunge_consumed_jump_tag=false
    self.art_resource=nil
    if had_combat_state and type(RK_ShieldState)=='function' then pcall(invoke,RK_ShieldState,{active=false,lease='RK-Arsenal'}) end
    self.guard_bridge_active=nil;self.seen_serial=nil
    if had_combat_state and type(RK_CombatProtection)=='function' then pcall(invoke,RK_CombatProtection,{phase='cleanup'}) end
    self.action_protection_active=false;self.protection_renew_in=0
    pcall(self.restore_animation,self)
    -- Earlier cleanup (for example the native protection lease) may fail;
    -- still stop only our montage and release the input movement lock.
    if self.animation_blend then pcall(self.animation_blend.stop,self.animation_blend,0)end
    pcall(self.lock_movement,self,false);pcall(self.close_held_bomb,self)
    if valid(self.input_subsystem) and valid(self.context) then
        pcall(function()self.input_subsystem:RemoveMappingContext(self.context,{bForceImmediately=true,bNotifyUserSettings=false})end)
    end
    if self.equipment_visuals then pcall(self.equipment_visuals.clear,self.equipment_visuals)end
    for _,object in ipairs(self.owned or {}) do pcall(destroy,object) end
    for _,effect in ipairs(self.effects) do pcall(destroy,effect.object) end
    for _,projectile in ipairs(self.projectiles) do if valid(projectile.actor) then pcall(function()projectile.actor:K2_DestroyActor()end) end end
    self.owned={};self.effects={};self.projectiles={};self.hidden={};self.seen={};self.context=nil
    log('Disabled: '..tostring(reason or 'user'))
end
function runtime:suspend_initialization(reason)
    if self.development_suspended and self.initialization_error then return end
    self.development_suspended=true
    self.initialization_error=tostring(reason)
    self.inventory_error=self.initialization_error
    local ok,why=pcall(self.disable,self,'initialization failure')
    local cleanup=ok and '' or ('; cleanup failed: '..tostring(why))
    log('initialization suspended; '..self.initialization_error..cleanup)
end
function runtime:enable()
    if self.enabled then return end
    assert(not self.development_suspended,'Initialization is suspended; explicitly resume with F8 before retrying')
    self.initialization_error=nil;self.inventory_error=nil
    local ok,err=xpcall(function()
        if self.context or (self.owned and #self.owned>0) then self:disable('cleanup partial activation') end
        assert(type(RK_HostCompatible)=='function' and RK_HostCompatible(),'Native bridge or pinned game/loader version unavailable')
        assert(self.hitreact_hook,'Native hit-reaction pre-hook unavailable')
        local query=invoke(RK_NativeQuery,{phase='capabilities'})
        assert(query.api==1 and query.owned_parameter_frames and query.trace and query.overlap and query.blocking_hit_flags
            and query.trace_batch and query.max_batch>=64,'Owned native spatial query bridge unavailable')
        local hit_contract=invoke(RK_NativeHit,{phase='capabilities'})
        assert(hit_contract.api==2 and hit_contract.ultimate_charge_regen_tag=='Damage.Attack.Attacker.UltimateChargeRegen'
            and hit_contract.ultimate_charge_regen_default==0,'Native ultimate charge damage contract unavailable')
        self.pc=H.GetPlayerController();self.pawn=H.GetPlayer();assert(valid(self.pc) and valid(self.pawn),'Load the designated test save first')
        assert(self.inventory_ready,'Independent item registration is not ready')
        local spec,backpack=self.inventory:selection(self.pawn:GetWorld())
        assert(spec,'Select the independent Ringed Knight weapon in native equipment first')
        self.active_item=spec.id;self.backpack=backpack
        self.active_config=self.equipment.configs[backpack:IsWeaponSnapSouled(FName(spec.id),true) and 'Weapon_RKA_RingedKnight_Soul' or 'Weapon_RKA_RingedKnight']
        Math=StaticFindObject('/Script/Engine.Default__KismetMathLibrary');Gameplay=StaticFindObject('/Script/Engine.Default__GameplayStatics')
        assert(valid(Math) and valid(Gameplay),'Engine libraries unavailable')
        self.mesh=self.pawn.Mesh;assert(valid(self.mesh))
        self.animation_blend=AnimationBlend.new(self.mesh)
        assert(self.animation_blend:native_instance(),'Native hero animation instance unavailable')
        self.world=self.pawn:GetWorld();self.state=State.new(Profile);self.last_keys={};self.seen={};self.motion_previous={X=0,Y=0,Z=0};self.native_reaction=nil
        local cost=assert(Profile.art.cost,'Native art cost policy required')
        assert(cost.resource=='UltimateChargeCount'and cost.amount==1 and cost.per_sequence==true,'Unsupported native art cost policy')
        self.art_resource=ArtResource.new(function(request)return invoke(RK_ArtResource,request)end,path(self.pawn))
        self.state.pay_art=function(sequence)
            if self.art_test_free then
                self.last_art_cost={status='testing_free',resource='UltimateChargeCount',amount=0,sequence=sequence}
                log('ART_COST testing_free UltimateChargeCount unchanged')
                return true
            end
            local paid,receipt=self.art_resource:pay(sequence)
            self.last_art_cost=receipt
            log('ART_COST '..receipt.status..' UltimateChargeCount '..tostring(receipt.before)..' -> '..tostring(receipt.after))
            return paid
        end
        self.health=self.pawn.AttributeSetBase.Health.CurrentValue
        self.ability_system=nil;self.dodge_tag_failed=false
        for _,candidate in ipairs(FindAllOf('PBZAbilitySystemComponent')or{})do
            if valid(candidate)and not candidate:GetFullName():find('Default__',1,true)and same(candidate:GetOwner(),self.pawn)then
                self.ability_system=candidate;break
            end
        end
        self.weapon_component=component(self.pawn,'/Script/SGameCombatSystem.CharacterWeaponsComponent');assert(valid(self.weapon_component),'Native weapon component unavailable')
        self.holstered=nil;self.holster_yield=nil;self.arm_changing=nil
        self.last_native_jump_tag=self:native_jump_tag()
        self.plunge_consumed_jump_tag=false
        self.attribute_component=component(self.pawn,'/Script/SGameAttributes.AttributeComponent');assert(valid(self.attribute_component))
        self.execution_component=component(self.pawn,'/Script/SGameExecution.ExecutionComponent')
        local protection=invoke(RK_CombatProtection,{phase='prepare'})
        assert(protection.api==1 and protection.finite_specs and protection.hp_immunity==false and protection.action_damage_taken_multiplier==.2,'Native protection capability unavailable')
        self.action_damage_reduction=ActionDamageReduction.prepare(self.equipment.configs.Weapon_RKA_RingedKnight:GetOuter())
        self:input_context();self:hide_native_weapons()
        self.sword=self:attach(Config.assets.sword,Profile.attachments.r);self.shield=self:attach(Config.assets.shield,Profile.attachments.l)
        self.shield_stowed=false
        self.last_game_time=Gameplay:GetTimeSeconds(self.pawn);self.guard_report=nil
        local receipt=invoke(RK_ShieldState,{active=false,lease='RK-Arsenal'})
        self.guard_bridge_active=false;self.guard_report=receipt;self.seen_serial=nil
        self.guard_stamina_accounted=receipt.stamina_spent or 0
        self.audio:reset(receipt.blocked);self.audio:prepare()
        self.enabled=true
        if not self:sync_armed_state() and not self:yield_to_native_air(0) then self:update_idle(false) end
        self:notify('Ringed Knight Arsenal ON | Square: light, Triangle: heavy, L1: guard, L2: Ember light, L1+Circle: Ember heavy, L1+Triangle: rope bomb | F8: restore')
    end,debug.traceback)
    if not ok then self:suspend_initialization(err);error(err,0) end
end
function runtime:key(keys)
    for _,key in ipairs(keys) do if self.pc:IsInputKeyDown({KeyName=FName(key)}) then return true end end
    return false
end
function runtime:key_pressed(keys)
    for _,key in ipairs(keys) do if self.pc:WasInputKeyJustPressed({KeyName=FName(key)}) then return true end end
    return false
end
function runtime:keys()
    local input={}
    for name,keys in pairs(Config.keys) do
        local down=self:key(keys);input[name]=down
        input[name..'_pressed']=(down and not self.last_keys[name]) or self:key_pressed(keys)
        self.last_keys[name]=down
    end
    local chord=Config.art_chord
    local circle=self:key({chord.attack})
    input.circle_pressed=self.art_chord_ready and self:key({chord.guard})
        and ((circle and not self.last_keys.circle) or self:key_pressed({chord.attack}))
    self.last_keys.circle=circle
    local right=self.pc:GetInputAnalogKeyState({KeyName=FName('Gamepad_LeftX')})
        +(self:key({'D'})and 1 or 0)-(self:key({'A'})and 1 or 0)
    local forward=self.pc:GetInputAnalogKeyState({KeyName=FName('Gamepad_LeftY')})
        +(self:key({'W'})and 1 or 0)-(self:key({'S'})and 1 or 0)
    input.move=right*right+forward*forward>=CombatMotion.deadzone*CombatMotion.deadzone
    if input.move then input.aim_yaw=CombatMotion.aim_yaw(right,forward,self.pc:GetControlRotation().Yaw)end
    return input
end
function runtime:play(name,loop)
    if self.action_failures and self.action_failures[name] then
        self:begin_native_reaction()
        return false
    end
    self:close_held_bomb();self.motion_previous={X=0,Y=0,Z=0};self.idle_playing=false
    self.native_stop_time=nil
    if name==Profile.art.start or not art_clips[name] then self:clear_art_flame() end
    -- Start from a fixed basis. Only intentional actor heading changes steer
    -- the source displacement, never accumulated camera/mesh feedback.
    local basis=self.mesh:K2_GetComponentToWorld();local rotation=basis.Rotation
    self.motion_basis={Rotation={X=rotation.X,Y=rotation.Y,Z=rotation.Z,W=rotation.W},Translation={X=0,Y=0,Z=0},Scale3D=vec(basis.Scale3D)}
    self.motion_start_yaw=CombatMotion.can_steer(name)and self.pawn:K2_GetActorRotation().Yaw or nil
    local clip=assert(Profile.clips[name])
    local ok,accepted=xpcall(function()
        local asset=load_asset(clip.asset)
        return self:custom_animation(asset,loop,clip.duration,CombatMotion.slot(name),nil,clip.asset)
    end,debug.traceback)
    if not ok then
        self.action_failures=self.action_failures or {}
        self.action_failures[name]=tostring(accepted)
        error('Animation action rejected: '..name..'; '..tostring(accepted),0)
    end
    if not accepted then return false end
    self.last_action_clip=name
    self:update_action_protection(self:is_protected_action(name),0)
    self:update_shield(art_clips[name]==true)
    self:lock_movement(not CombatMotion.is_mobile(name),CombatMotion.is_plunge(name))
    if name=='RKSS_RopeBomb' then
        self.sword:SetVisibility(false,false)
        self.held_bomb=self:attach(Config.assets.bomb,{bone='hand_r',t={0,0,0},q={0,0,0,1}})
    end
    return true
end
local function sample(points,time,fps)
    local frame=math.max(0,math.min(#points-1,time*fps));local lo=math.floor(frame)+1;local hi=math.min(#points,lo+1);local fraction=frame%1
    local a,b=points[lo],points[hi];return {X=a[1]+(b[1]-a[1])*fraction,Y=a[2]+(b[2]-a[2])*fraction,Z=a[3]+(b[3]-a[3])*fraction}
end
function runtime:root_motion(input,dt)
    local name=self.state.clip;if not name then return true end
    local clip=Profile.clips[name];local time=name=='RKSS_GuardLoop' and self.state.time%clip.duration or self.state.time
    if not self.animation_blend:seek(time) then
        self:begin_native_reaction()
        return false
    end
    if CombatMotion.is_mobile(name) or CombatMotion.is_plunge(name)then return true end
    local yaw_delta=0
    if self.motion_start_yaw then
        local current=self.pawn:K2_GetActorRotation();local yaw=current.Yaw
        if input and input.aim_yaw and dt and dt>0 then
            local next_yaw=CombatMotion.approach_yaw(yaw,input.aim_yaw,dt)
            if math.abs(next_yaw-yaw)>.01 then
                self.pawn:K2_SetActorRotation({Pitch=current.Pitch,Yaw=next_yaw,Roll=current.Roll},false)
                yaw=self.pawn:K2_GetActorRotation().Yaw
            end
        end
        yaw_delta=yaw-self.motion_start_yaw
    end
    local displacement=sample(clip.root_motion,time,clip.fps);local delta=subtract(displacement,self.motion_previous)
    self.motion_previous=displacement
    local direction=CombatMotion.rotate_yaw(Math:TransformDirection(self.motion_basis or self.mesh:K2_GetComponentToWorld(),delta),yaw_delta)
    direction.Z=0;local position=add(vec(self.pawn:K2_GetActorLocation()),direction)
    self.pawn:K2_SetActorLocation(position,true,{},false)
    return true
end
function runtime:effect(asset,location,attached,scale,seconds,placement)
    local library=StaticFindObject('/Script/Niagara.Default__NiagaraFunctionLibrary');local system=load_asset(asset)
    if not valid(library) or not valid(system) then log('Native VFX unavailable: '..asset);return end
    local object
    if attached then
        local rotation=placement and placement.rotation or {Pitch=0,Yaw=0,Roll=0}
        object=library:SpawnSystemAttached(system,attached,FName('None'),location,rotation,0,true,placement==nil,0,false)
        if valid(object) then
            local ok,why=pcall(function()
                object:SetRelativeScale3D({X=scale,Y=scale,Z=scale})
                if placement then
                    for _,name in ipairs(placement.disabled_emitters)do object:SetEmitterEnable(FName(name),false)end
                    object:Activate(true)
                end
            end)
            if not ok then pcall(destroy,object);log('Attached effect setup failed: '..tostring(why));return end
        end
    else object=library:SpawnSystemAtLocation(self.pawn,system,location,{Pitch=0,Yaw=0,Roll=0},{X=scale,Y=scale,Z=scale},true,true,0,false) end
    if valid(object) then self.effects[#self.effects+1]={object=object,remaining=seconds} end
    return object
end
function runtime:flame(seconds,quiet)
    -- Cosmetic only. This path never calls damage or modifies attack numbers.
    if not quiet then self.audio:fire(self.pawn) end
    return self:effect(Config.vfx.flame,BladeFlame.location,self.sword,BladeFlame.scale,seconds,BladeFlame)
end
local function trace_ignore(self,ignored,extra)
    local ignore,seen={},{}
    local actor_class=StaticFindObject('/Script/Engine.Actor')
    assert(valid(actor_class),'Native trace Actor class unavailable')
    local function add_ignored(actor)
        if not valid(actor)or not actor:IsA(actor_class)then return end
        local key=path(actor);if not seen[key]then seen[key]=true;ignore[#ignore+1]=key end
    end
    add_ignored(self.pawn);add_ignored(ignored)
    for _,entry in ipairs(self.hidden) do add_ignored(entry.actor) end
    for _,actor in ipairs(extra or {})do add_ignored(actor)end
    return ignore
end
local function trace_hits(values,actors)
    assert(type(values)=='table','Native trace hits missing')
    local hits={}
    for _,hit in ipairs(values)do
        assert(type(hit.target)=='string' and type(hit.point)=='table' and type(hit.normal)=='table' and
            type(hit.blocking)=='boolean' and type(hit.start_penetrating)=='boolean','Native trace result mismatch')
        local actor=actors and actors[hit.target] or nil
        if not valid(actor)then actor=hit.target~='' and StaticFindObject(hit.target) or nil end
        if actors and valid(actor)then actors[hit.target]=actor end
        hits[#hits+1]={native_snapshot=true,actor=valid(actor) and actor or nil,ImpactPoint=vec(hit.point),ImpactNormal=vec(hit.normal),
            blocking=hit.blocking,start_penetrating=hit.start_penetrating}
    end
    return hits
end
function runtime:trace(start,finish,radius,ignored,extra)
    local reply=invoke(RK_NativeQuery,{phase='trace',pawn=path(self.pawn),start=vec(start),finish=vec(finish),radius=radius,
        ignore=trace_ignore(self,ignored,extra)})
    assert(reply.api==1 and reply.phase=='trace' and reply.owned_parameter_frames,'Native trace reply mismatch')
    return trace_hits(reply.hits)
end
function runtime:trace_batch(segments)
    assert(#segments>=1 and #segments<=64,'Sword sweep query budget exceeded')
    local reply=invoke(RK_NativeQuery,{phase='trace_batch',pawn=path(self.pawn),segments=segments,ignore=trace_ignore(self)})
    assert(reply.api==1 and reply.phase=='trace_batch' and reply.owned_parameter_frames
        and type(reply.results)=='table' and #reply.results==#segments,'Native trace batch reply mismatch')
    local results,actors={},{}
    for index,result in ipairs(reply.results)do results[index]=trace_hits(result.hits,actors)end
    return results
end
function runtime:explode(location,key,ignored)
    self.audio:play('explosion',self.pawn,location)
    self:effect(Config.vfx.explosion,location,nil,.35,3)
    local center=add(location,{X=0,Y=0,Z=20})
    local reply=invoke(RK_NativeQuery,{phase='overlap',pawn=path(self.pawn),center=center,radius=Profile.bomb.radius_cm,ignore={path(self.pawn)}})
    assert(reply.api==1 and reply.phase=='overlap' and reply.owned_parameter_frames and type(reply.actors)=='table','Native overlap reply mismatch')
    for _,value in ipairs(reply.actors) do
        assert(type(value)=='string' and value~='','Native overlap target mismatch')
        local target=StaticFindObject(value)
        if valid(target) then
            local target_position=vec(target:K2_GetActorLocation());local obstruction=self:trace(center,target_position,1,ignored)
            local hit=#obstruction>0 and unwrap(obstruction[1]) or {ImpactPoint=target_position,ImpactNormal={X=0,Y=0,Z=1}}
            if #obstruction==0 or same(hit_actor(hit),target) then
                self:damage(target,hit,key,Profile.bomb.physical,Profile.bomb.fire,'explosion',
                    Profile.bomb.poise,Profile.bomb.anger,Profile.bomb.hit_anger_multiplier,Profile.bomb.ultimate_charge_regen)
            end
        end
    end
end
hit_actor=function(hit)
    assert(hit.native_snapshot,'Trace hit is not an owned native snapshot')
    return valid(hit.actor) and hit.actor or nil
end
function runtime:damage(target,hit,key,physical,fire,kind,poise,anger,hit_anger_multiplier,ultimate_charge_regen)
    if not valid(target) or same(target,self.pawn) or not target:IsA(StaticFindObject('/Script/ProjectPBZ.PBZCharacter')) or not target.bCanBeDamaged then return end
    local target_path=path(target);key=key..'/'..target_path
    if self.seen[key] then return end
    if not valid(NativeFaction) then NativeFaction=StaticFindObject('/Script/SGameCombatSystem.Default__FactionUtils') end
    assert(valid(NativeFaction),'Faction library unavailable')
    if NativeFaction:GetFactionRelation(self.pawn,target)~=2 then return end
    local attributes=target.AttributeSetBase;if not valid(attributes) or attributes.Health.CurrentValue<=0 then return end
    local damage_component=component(target,'/Script/SGameAttributes.AttributeComponent');if not valid(damage_component) then return end
    local reaction=component(target,'/Script/SGameCombatSystem.HitreactComponent')
    local attack=self.pawn.AttributeSetBase.Attack.CurrentValue;assert(attack>0,'Player attack snapshot unavailable')
    local strength,level=Upgrade.multiplier(self.backpack,self.pawn,self.active_config,self.active_item)
    physical=physical*strength;fire=fire*strength
    self.upgrade_status=level;self.upgrade_status.multiplier=strength
    local source=StaticConstructObject(StaticFindObject('/Script/SGameCombatSystem.DamageSource_GameplayEffect'),self.pawn);assert(valid(source))
    local direction=subtract(vec(target:K2_GetActorLocation()),vec(self.pawn:K2_GetActorLocation()))
    local length=math.sqrt(direction.X^2+direction.Y^2+direction.Z^2);if length<.001 then return end
    direction={X=direction.X/length,Y=direction.Y/length,Z=direction.Z/length}
    local request={phase='damage',kind=kind or 'sword',pawn=path(self.pawn),target=target_path,source=path(source),component=path(damage_component),
        reaction=valid(reaction) and path(reaction) or nil,coefficient=physical/attack,fire=fire/attack,poise=poise,
        anger=anger,hit_anger_multiplier=hit_anger_multiplier,ultimate_charge_regen=ultimate_charge_regen or 0,
        ultimate_charge_diagnostics=(ultimate_charge_regen or 0)>0 and not self.ultimate_probe_done,
        location=vec(hit.ImpactPoint),direction=direction,normal=vec(hit.ImpactNormal)}
    self.seen[key]=true -- A dispatched contact is never replayed after an FX/readback error.
    local before=attributes.Health.CurrentValue
    local shield_ok,shield_before=pcall(function()return attributes.Shield.CurrentValue end)
    local receipt=invoke(RK_NativeHit,request)
    if request.ultimate_charge_diagnostics then self.ultimate_probe_done=true end
    local after=attributes.Health.CurrentValue
    local shield_after_ok,shield_after=pcall(function()return attributes.Shield.CurrentValue end)
    local accepted=after<before or (shield_ok and shield_after_ok and shield_after<shield_before)
    self.last_hit={target=target_path,before=before,after=after,accepted=accepted,dispatched=receipt.dispatched,
        physical=physical,fire=fire,poise=poise,anger=receipt.anger,native_shachi=receipt.native_shachi,
        ultimate_charge_regen=receipt.ultimate_charge_regen,native_ultimate_charge=receipt.native_ultimate_charge}
    if accepted then self.hits=self.hits+1 end
    if after<before and request.kind=='sword' then
        local clip=self.state.clip
        local cue='hit_heavy'
        if clip=='RKSS_Heavy1Release' then cue='hit_thrust'
        elseif art_clips[clip] then cue='hit_light' end
        self.audio:play(cue,self.pawn,request.location)
    end
    log('HIT '..key..' physical='..physical..' fire='..fire..' poise='..tostring(poise or 0)..' HP '..before..' -> '..after)
    if receipt.native_shachi and receipt.native_shachi.supported and receipt.native_shachi.after then
        log('SHACHI '..target_path..' '..receipt.native_shachi.before..' -> '..receipt.native_shachi.after)
    end
    if request.ultimate_charge_diagnostics then log('ULTIMATE '..json.encode(receipt.native_ultimate_charge or {})) end
    if accepted and after>0 and valid(reaction) then request.phase='feedback';invoke(RK_NativeHit,request) end
end
function runtime:hit_window(event)
    local clip=Profile.clips[self.state.clip];if not clip then return end
    local physical,fire,poise=event.hit.physical,event.hit.fire,event.hit.poise
    local anger=event.hit.anger
    if self.state.clip:match('^RKSS_Light%d$') then
        local chain=Profile.light_chain
        local first=(event.light_index or self.state.light_index or 1)==1
        local baked_scale=self.state.clip=='RKSS_Light1' and Profile.first_light_damage_scale or 1
        local scale=(first and chain.damage_first or chain.damage_follow)/baked_scale
        physical,fire=physical*scale,fire*scale
        poise=chain.poise_base*(first and chain.poise_first or chain.poise_follow)
        anger=chain.anger_damage
    end
    if self.state.clip:match('^RKSS_Heavy[12]Release$') and event.heavy_charged==true then
        local scale=Profile.heavy.charged_damage_scale
        physical,fire=physical*scale,fire*scale
        anger=anger and anger*scale
    end
    local transform=self.mesh:K2_GetComponentToWorld()
    -- Snapshot one world basis. Transform all baked samples in Lua instead of
    -- dispatching two reflected TransformLocation calls for every substep.
    local origin=vec(Math:TransformLocation(transform,{X=0,Y=0,Z=0}))
    local bx=subtract(Math:TransformLocation(transform,{X=1,Y=0,Z=0}),origin)
    local by=subtract(Math:TransformLocation(transform,{X=0,Y=1,Z=0}),origin)
    local bz=subtract(Math:TransformLocation(transform,{X=0,Y=0,Z=1}),origin)
    local function world_point(p)
        return {X=origin.X+bx.X*p.X+by.X*p.Y+bz.X*p.Z,
            Y=origin.Y+bx.Y*p.X+by.Y*p.Y+bz.Y*p.Z,Z=origin.Z+bx.Z*p.X+by.Z*p.Y+bz.Z*p.Z}
    end
    local key=event.plunge_serial and ('plunge:'..event.plunge_serial..':'..event.plunge_phase)
        or (event.serial..':'..event.index)
    local function strike(a,b,radius)
        for _,value in ipairs(self:trace(a,b,radius)) do
            local hit=unwrap(value)
            self:damage(hit_actor(hit),hit,key,physical,fire,'sword',poise,anger,event.hit.hit_anger_multiplier,event.hit.ultimate_charge_regen)
        end
    end
    for _,capsule in ipairs(event.hit.capsules) do
        local a=sample(clip.dummy_tracks[tostring(capsule.a)],event.time,clip.fps)
        local b=sample(clip.dummy_tracks[tostring(capsule.b)],event.time,clip.fps)
        a=world_point(a);b=world_point(b)
        strike(a,b,capsule.radius_cm)
    end
    -- Use the same baked animation clock as the original contacts. A live
    -- attachment transform may still contain the previous evaluated bone pose.
    -- Conservative swept samples cover skipped poses without extra damage.
    if valid(self.sword) then
        local volume=art_clips[self.state.clip] and art_hit_volume or sword_hit_volume
        local dx,dy,dz=volume.finish.X-volume.start.X,volume.finish.Y-volume.start.Y,volume.finish.Z-volume.start.Z
        local segments,why=ArtFlameTrace.swept_segments(clip,event.from_time or event.time,event.time,
            math.sqrt(dx*dx+dy*dy+dz*dz),volume.radius_cm,64)
        if not segments then
            assert(why=='sweep_budget_exhausted','Unexpected sword sweep failure')
            self.hit_sweep_budget_exhausted=(self.hit_sweep_budget_exhausted or 0)+1
            if self.hit_sweep_budget_exhausted==1 then log('Sword sweep budget exceeded; retaining current pose without oversized volume')end
            segments=assert(ArtFlameTrace.swept_segments(clip,event.time,event.time,
                math.sqrt(dx*dx+dy*dy+dz*dz),volume.radius_cm,1))
        end
        local queries={}
        for _,segment in ipairs(segments)do
            queries[#queries+1]={start=world_point(segment.start),finish=world_point(segment.finish),radius=segment.radius_cm}
        end
        for _,hits in ipairs(self:trace_batch(queries))do
            for _,hit in ipairs(hits)do
                self:damage(hit_actor(hit),hit,key,physical,fire,'sword',poise,anger,event.hit.hit_anger_multiplier,event.hit.ultimate_charge_regen)
            end
        end
    end
end
function runtime:throw_bomb(serial)
    -- Source action a000_050130: release at frame 32, aimed just behind the feet.
    local origin=vec(self.mesh:GetSocketLocation(FName('hand_r')))
    local feet=vec(self.pawn:K2_GetActorLocation())
    feet.Z=feet.Z-self.pawn.CapsuleComponent:GetScaledCapsuleHalfHeight()
    local velocity=BombLanding.launch_velocity(origin,feet,self.pawn:GetActorForwardVector(),
        self.pawn:GetVelocity(),Profile.bomb)
    self:close_held_bomb()
    local actor=self.world:SpawnActor(StaticFindObject('/Script/Engine.Actor'),origin,{Pitch=0,Yaw=0,Roll=0});assert(valid(actor))
    local object=actor:AddComponentByClass(StaticFindObject('/Script/Engine.StaticMeshComponent'),false,identity(),false);assert(valid(object))
    local bomb_asset=load_asset(Config.assets.bomb)
    object:SetStaticMesh(bomb_asset);object:SetCollisionEnabled(0)
    self.projectiles[#self.projectiles+1]={actor=actor,position=origin,velocity=velocity,age=0,key='bomb:'..serial}
    self.audio:play('throw',self.pawn,origin)
    self.throws=self.throws+1;log('ROPE_BOMB aimed behind feet; serial='..serial)
end
function runtime:ignore_bomb_contact(actor)
    local character=StaticFindObject('/Script/ProjectPBZ.PBZCharacter')
    local pending,seen={actor},{}
    for _=1,16 do
        local value=table.remove(pending);if not value then break end
        if valid(value)and not seen[value:GetAddress()]then
            seen[value:GetAddress()]=true
            if same(value,self.pawn)or (valid(character)and value:IsA(character))then return true end
            local parent=value:GetAttachParentActor();if valid(parent)then pending[#pending+1]=parent end
            local owner=value:GetOwner();if valid(owner)then pending[#pending+1]=owner end
        end
    end
    return false
end
function runtime:projectile_step(dt)
    for i=#self.projectiles,1,-1 do
        local p=self.projectiles[i]
        if not valid(p.actor) then table.remove(self.projectiles,i)
        else
            local status,location=BombLanding.advance(p,dt,Profile.bomb.gravity_cm,
                function(start,finish,radius,extra)return self:trace(start,finish,radius,p.actor,extra)end,
                function(actor)return self:ignore_bomb_contact(actor)end)
            if status=='land' or status=='expire' then
                if status=='land'then self:explode(location,p.key,p.actor)end
                p.actor:K2_DestroyActor();table.remove(self.projectiles,i)
            else p.actor:K2_SetActorLocation(location,false,{},false)end
        end
    end
end
function runtime:advance_world_effects(dt)
    self:prune_hit_history()
    if dt>0 then self:projectile_step(dt)end
    for i=#self.effects,1,-1 do
        local effect=self.effects[i];effect.remaining=effect.remaining-dt
        if effect.remaining<=0 or not valid(effect.object) then pcall(destroy,effect.object);table.remove(self.effects,i) end
    end
end
function runtime:tick(dt)
    if not self.enabled then return end
    if not valid(self.pawn) or not valid(self.mesh) or not valid(self.world) or not same(self.pawn:GetWorld(),self.world) then self:disable('world changed');return end
    if not same(self.mesh,self.pawn.Mesh) then self:disable('character mesh changed');return end
    if not valid(self.pc) then self:disable('controller unloaded');return end
    local controlled_pawn=self.pc.Pawn
    if not valid(controlled_pawn) or not same(controlled_pawn,self.pawn) then self:disable('controller pawn changed');return end
    if not valid(self.backpack) or self.backpack.CurrentMainWeaponID:ToString()~=self.active_item then self:disable('native weapon changed');return end
    if self.pawn.AttributeSetBase.Health.CurrentValue<=0 then self:disable('player died');return end
    local armed_busy=self:sync_armed_state()
    self:update_draw_entry(dt,false)
    if self:menu_blocked(self.pc,self.pawn) then
        self:suspend_menu()
        -- Dialogue can own input while the world keeps running. Already-thrown
        -- bombs and temporary effects retain their world clock through it.
        self:advance_world_effects(dt)
        return
    end
    self:resume_menu()
    if armed_busy then
        self.animation_blend:update(dt)
        self:request_native_draw(self:keys())
        self.health=self.pawn.AttributeSetBase.Health.CurrentValue
        self:advance_world_effects(dt);return
    end
    if self.pawn.AttributeSetBase.Health.CurrentValue<=0 then self:disable('player died');return end
    self.animation_blend:update(dt)
    local health=self.pawn.AttributeSetBase.Health.CurrentValue
    local execution_busy=self:update_native_execution()
    local foreign_montage=self.animation_blend:native_active()
    if execution_busy or foreign_montage or self:native_dodge_active() or self:native_special_active() then
        if execution_busy or self:native_dodge_active() or self:native_special_active() then self.pending_draw_entry=nil end
        -- The original ability input buffer must receive ALL real QTE/chain
        -- input, not just an emulated Triangle activation on one channel.
        if not self.native_reaction then self:begin_native_reaction(true) end
        if foreign_montage then self.native_reaction.saw_montage=true end
        self:handoff_native_input(true)
        self:keys();self.health=health
        self:update_action_protection(false)
        self:update_guard_state(false)
        self:advance_world_effects(dt)
        return
    elseif self.native_input_handoff then
        self:handoff_native_input(false)
        self.native_reaction=nil;self.health=health
        self:advance_world_effects(dt)
        return
    end
    if self.discard_combat_input_once then
        self.discard_combat_input_once=false;self:keys()
        self:advance_world_effects(dt)
        return
    end
    local input=self:keys()
    self:update_action_protection(self:is_protected_action(),dt)
    input.airborne=self.pawn.CharacterMovement:IsFalling()
    input.on_ground=self.pawn.CharacterMovement:IsMovingOnGround()
    -- Track the original Jump tag through every phase. A true tag left over
    -- from the first jump, or Landing itself, must not cancel the impact.
    local native_jump=self:native_jump_tag()
    local jump_started=native_jump and self.last_native_jump_tag==false
    self.last_native_jump_tag=native_jump
    if not native_jump then self.plunge_consumed_jump_tag=false end
    local plunge_landing=Profile.jump and self.state.clip==Profile.jump.land
    local plunge=CombatMotion.is_plunge(self.state.clip)
        or (input.airborne and (input.attack_pressed or input.triangle_pressed))
    local air_busy=false
    if plunge then
        self.native_airborne=false;self.native_landing_time=0
        if plunge_landing and (jump_started or (input.airborne and not input.on_ground and self.pawn:GetVelocity().Z>1)) then
            self.plunge_consumed_jump_tag=false
            air_busy=self:yield_to_native_air(dt,native_jump)
        elseif native_jump then
            -- Consume the old jump until its tag clears, including the first
            -- grounded frame after the custom recovery naturally finishes.
            self.plunge_consumed_jump_tag=true
        end
    else air_busy=self:yield_to_native_air(dt,native_jump and not self.plunge_consumed_jump_tag) end
    local spent=self.guard_report and self.guard_report.stamina_spent or self.guard_stamina_accounted
    input.guard_cost=math.max(0,spent-self.guard_stamina_accounted);self.guard_stamina_accounted=spent
    if self.guard_report and self.guard_report.guard_broken then
        input.guard_cost=math.max(input.guard_cost,self.state.stamina)
    end
    if not self.native_reaction and (self.animation_blend:native_active() or self:native_dodge_active()) then
        -- Native C++ montage starts can bypass the reflected Montage_Play hook.
        self:begin_native_reaction(true)
    end
    -- Health loss alone is not a hit reaction: burn/poison ticks may reduce HP
    -- without taking ownership of the pose. Real reactions still yield via
    -- PlayHitreact, foreign native montages, or the native dodge tag above.
    self.health=health
    local reaction_busy=self:native_reaction_busy(input) or air_busy or execution_busy
    if input.triangle_pressed and not input.guard then
        if input.on_ground and not reaction_busy and self:try_execution() then
            reaction_busy=true
        end
    end
    if reaction_busy then self.pending_draw_entry=nil else self:update_draw_entry(0,true) end
    local entry=self.switch_entry
    if entry then
        entry.age=entry.age+dt
        local receipt=entry.receipt
        if entry.age>1 or receipt.id~=self.active_item or receipt.pawn~=self.pawn:GetAddress()or receipt.owner~=self.backpack:GetAddress()then
            self.switch_entry=nil
        elseif not reaction_busy and not self.state.clip then
            input.switch_heavy=true;self.switch_entry=nil
        end
    end
    local events=reaction_busy and {} or self.state:step(dt,input)
    for _,event in ipairs(events) do
        if event.kind=='play' and not self:play(event.clip,event.loop) then
            self:begin_native_reaction(true)
            break
        elseif event.kind=='restore' then
            -- Keep the outgoing pose until idle crossfades or locomotion takes over.
            self:close_held_bomb();self:lock_movement(false);self:clear_art_flame();self:update_shield(false)
            self:update_action_protection(false)
        end
    end
    -- State time can cross a charge boundary this tick. Remove its finite
    -- native armor now instead of letting it cover the following strike.
    self:update_action_protection(self:is_protected_action(),0)
    if not reaction_busy and not self.native_reaction and self:root_motion(input,dt) then
        self:update_idle(input.move,dt)
        self.audio:advance(self.pawn,self.state)
        for _,event in ipairs(events) do
            if event.kind=='cancel_flame' then self.cancels=self.cancels+1;self:flame(event.seconds);log('CANCEL cosmetic flame; extra_damage=0')
            elseif event.kind=='throw_bomb' then self:throw_bomb(event.serial)
            elseif event.kind=='hit_window' then self:hit_window(event) end
        end
    end
    self:update_guard_state(self.state:is_guarding())
    local guard_failures=self.guard_report.guard_failures or 0
    if guard_failures>(self.guard_failures or 0) then
        log('GUARD failure: '..tostring(self.guard_report.last_error))
    end
    self.guard_failures=guard_failures
    self.audio:guard(self.pawn,self.guard_report.blocked)
    if self.state.clip==Profile.art.start and self.state.time>=Profile.art.flame_at and not self.art_flame_started then
        self.art_flame_started=true
        local light_duration=0
        for _,name in ipairs(Profile.art.light_chain or {Profile.art.light})do
            light_duration=light_duration+Profile.clips[name].duration
        end
        local lifetime=Profile.clips[Profile.art.start].duration+math.max(light_duration,Profile.clips[Profile.art.heavy].duration)
        self.art_flame=self:flame(lifetime,true)
    end
    if self.state.clip=='RKSS_RopeBomb' and self.state.time>=1.1333333 and valid(self.sword) then self.sword:SetVisibility(true,false) end
    self:advance_world_effects(dt)
    self.ticks=self.ticks+1
end
-- Register on the loader's main Lua state, never from ExecuteInGameThread.
-- For native UFunctions the first callback executes before the original call.
local hitreact_name='/Script/SGameCombatSystem.HitreactComponent:PlayHitreact'
local hook_ok,pre,post=pcall(RegisterHook,hitreact_name,function(context)
    if generation~=_G.RK_RuntimeGeneration or not runtime.enabled then return end
    local reaction=unwrap(context)
    if not valid(reaction) or not same(reaction:GetOwner(),runtime.pawn) or runtime.state:is_guarding()
        or runtime.action_protection_active then return end
    runtime:cancel_draw_on_hit()
    if not runtime.playing then return end
    local ok,err=xpcall(function()runtime:begin_native_reaction()end,debug.traceback)
    if not ok then runtime:abort_action(err) end
end)
if hook_ok then runtime.hitreact_hook={name=hitreact_name,pre=pre,post=post}
else log('Hit-reaction hook unavailable: '..tostring(pre)) end
local montage_name='/Script/Engine.AnimInstance:Montage_Play'
local montage_ok,montage_pre,montage_post=pcall(RegisterHook,montage_name,function(context,montage_parameter)
    if generation~=_G.RK_RuntimeGeneration or not runtime.enabled or not runtime.playing then return end
    local blend=runtime.animation_blend
    if not blend or not same(unwrap(context),blend:native_instance()) then return end
    local montage=unwrap(montage_parameter)
    if not valid(montage) or blend:owns(montage) then return end
    local ok,err=xpcall(function()runtime:begin_native_reaction()end,debug.traceback)
    if not ok then runtime:abort_action(err) end
end)
if montage_ok then runtime.native_montage_hook={name=montage_name,pre=montage_pre,post=montage_post}
else log('Native montage pre-hook unavailable: '..tostring(montage_pre)) end
local NativeControlLease=dofile(folder..'NativeControlLease.lua')
runtime.control_lease_guard=NativeControlLease.new(function()
    if runtime.enabled then runtime:suspend_menu();return true end
    return false
end,log,function()return runtime.ability_system end)
local lease_ok,lease_why=pcall(function()runtime.control_lease_guard:register()end)
if not lease_ok then runtime.control_lease_guard.disabled=true;log('Native menu compatibility unavailable: '..tostring(lease_why))end
local localization_ok,localization_why=pcall(function()runtime.localization_schema=runtime.localization:register()end)
if not localization_ok then runtime.localization_error=tostring(localization_why);log('Localization unavailable: '..tostring(localization_why)) end
local switch_ok,switch_why=pcall(function()runtime.weapon_switch:register()end)
if not switch_ok then log('Native switch repair unavailable: '..tostring(switch_why)) end
local init_name='/Script/ProjectPBZ.PBZBackPackSubsystem:InitWeaponList'
local init_ok,init_pre,init_post=pcall(RegisterHook,init_name,function()
    if generation~=_G.RK_RuntimeGeneration or runtime.development_suspended then return end
    local ok,err=xpcall(function()runtime:prepare_inventory()end,debug.traceback)
    if not ok then
        runtime:suspend_initialization(err)
    end
end)
if init_ok then runtime.inventory_init_hook={name=init_name,pre=init_pre,post=init_post}
else log('Inventory init hook unavailable: '..tostring(init_pre)) end
RegisterKeyBind(Key.F8,function()
    if generation~=_G.RK_RuntimeGeneration or runtime.scheduler_stopped then return end
    -- The key callback never queues a closure onto the live hook stack.
    runtime.suspend_requested=not runtime.suspend_requested
end)
assert(type(LoopInGameThreadWithDelay)=='function' and type(LoopInGameThreadAfterFrames)=='function' and
    type(CancelDelayedAction)=='function','Pinned game-thread timer API unavailable')
local function game_loop(interval,callback,per_frame)
    -- Unlike LoopAsync, these callbacks execute directly on the game thread.
    -- The pinned loader ignores their return value; cancel the actual handle.
    local schedule=per_frame and LoopInGameThreadAfterFrames or LoopInGameThreadWithDelay
    local ok,handle=pcall(schedule,interval,function()
        if runtime.scheduler_stopped then return end
        if generation~=_G.RK_RuntimeGeneration then runtime:stop_scheduler();return end
        assert(IsInGameThread(),'Owned scheduler callback ran off game thread')
        callback()
    end)
    if not ok or math.type(handle)~='integer' then
        runtime:stop_scheduler();error('Cannot register game-thread timer: '..tostring(handle))
    end
    runtime.scheduler_handles[#runtime.scheduler_handles+1]=handle
end
game_loop(250,function()
    if runtime.development_suspended then return end
    local ok,err=xpcall(function()
        runtime:prepare_inventory()
        local pawn=H.GetPlayer()
        if not valid(pawn) then
            if runtime.enabled then runtime:disable('pawn unloaded')end
            runtime:update_equipment_visuals(nil,nil,false);return
        end
        if not valid(pawn.Mesh) then
            if runtime.enabled then runtime:disable('character mesh unloaded')end
            runtime:update_equipment_visuals(nil,nil,false);return
        end
        if runtime.control_lease_guard then runtime.control_lease_guard:update(H.GetPlayerController(),pawn) end
        local display_pc=H.GetPlayerController()
        local display_router=runtime.control_lease_guard and runtime.control_lease_guard.router
        local ui_active=not valid(display_pc)or not valid(display_router)or Gameplay:IsGamePaused(pawn)
            or display_pc.bShowMouseCursor or display_router:GetActiveInputMode()==0
        runtime.item_display:update(ui_active)
        local spec,owner=runtime.inventory:selection(pawn:GetWorld())
        if Config.auto_grant and valid(owner) then runtime:acquire(owner,'RKA_RingedKnight') end
        if not spec then
            if runtime.enabled then runtime:disable('original weapon selected') end
            runtime:update_equipment_visuals(pawn,owner,false)
            runtime.menu_suspended=false;return
        end
        local pc=H.GetPlayerController()
        if runtime.enabled and (not same(runtime.pawn,pawn) or not same(runtime.world,pawn:GetWorld()) or not same(runtime.mesh,pawn.Mesh)
            or not same(runtime.pc,pc) or not same(runtime.backpack,owner) or runtime.active_item~=spec.id) then
            runtime:disable('equipment owner changed')
        end
        if runtime.enabled then runtime:sync_armed_state()end
        local blocked=runtime:menu_blocked(pc,pawn) or pawn.AttributeSetBase.Health.CurrentValue<=0
        if blocked then if runtime.enabled then runtime:suspend_menu() end;return end
        if not runtime.enabled and not runtime.development_suspended then runtime:enable()end
        if runtime.enabled then
            runtime:resume_menu();runtime:hide_native_weapons()
            runtime.active_config=runtime.equipment.configs[owner:IsWeaponSnapSouled(FName(spec.id),true) and 'Weapon_RKA_RingedKnight_Soul' or 'Weapon_RKA_RingedKnight']
        end
    end,debug.traceback)
    if not ok then
        runtime:suspend_initialization(err)
    end
end)
game_loop(1,function()
    local ok,err=xpcall(function()
        if runtime.suspend_requested then
            runtime.suspend_requested=false
            runtime.development_suspended=not runtime.development_suspended
            if not runtime.development_suspended then
                runtime.initialization_error=nil;runtime.inventory_error=nil;runtime.action_failures=nil
            end
            if runtime.enabled or runtime.development_suspended then runtime:disable('development suspend') end
        end
        if runtime.inventory_ready and not runtime.development_suspended and runtime.weapon_switch.ready then
            local pc=H.GetPlayerController()
            if valid(pc)then
                local receipt=runtime.weapon_switch:poll(Gameplay:GetRealTimeSeconds(pc))
                if receipt then
                    if not runtime.enabled then runtime:enable()end
                    runtime.switch_entry={receipt=receipt,age=0}
                end
            end
        end
        if not runtime.enabled then return end
        if not valid(runtime.pawn) then runtime:disable('pawn unloaded');return end
        if Gameplay:IsGamePaused(runtime.pawn) then runtime:suspend_menu();return end
        local now=Gameplay:GetTimeSeconds(runtime.pawn)
        local dt=now-(runtime.last_game_time or now);runtime.last_game_time=now
        -- A zero world delta during hit stop still accepts input edges.
        runtime:tick(math.max(0,math.min(dt,.1)))
    end,debug.traceback)
    if not ok then
        if runtime.enabled then runtime:abort_action(err)
        else runtime:suspend_initialization(err) end
    end
end,true)
log('Independent equipment supervisor loaded. F8 is development suspension only; native item selection controls combat.')
