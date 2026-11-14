"""Exercise the real runtime adapter with mocked UE objects; never in-game proof."""
from pathlib import Path
import json
import sys
import hashlib

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

scripts = root / 'src/runtime/RingedKnightArsenal/Scripts'
profile_text = (scripts / 'combat-profile.json').read_text(encoding='utf-8')
profile_data = json.loads(profile_text)
setup = r'''
local serial=0
function obj(fields)
    fields=fields or {};serial=serial+1;local address=serial
    fields.IsValid=function()return true end
    fields.GetAddress=function()return address end
    fields.IsA=fields.IsA or function(self,class)return self.actor==true and class.path=='/Script/Engine.Actor'end
    return fields
end
calls={};hook_callbacks={};unregistered={}
function record(name,value)calls[#calls+1]={name=name,value=value}end
function StaticFindObject()return obj()end
function RegisterHook(name,callback)hook_callbacks[#hook_callbacks+1]=callback;return 71,72 end
function UnregisterHook(name,pre,post)unregistered[#unregistered+1]={name,pre,post}end
function RegisterKeyBind()end
function LoopAsync()error('Arsenal must not schedule asynchronous Lua loops')end
local timer_id=0
timers={}
function LoopInGameThreadWithDelay(interval,callback)timer_id=timer_id+1;timers[timer_id]={interval=interval,callback=callback};return timer_id end
function LoopInGameThreadAfterFrames(interval,callback)assert(interval==1);return LoopInGameThreadWithDelay(interval,callback)end
function CancelDelayedAction()return true end
function ExecuteInGameThread(fn)fn()end
function FName(value)return {ToString=function()return value end,type=function()return 'FName'end}end
function FindAllOf()return {}end
function IsInGameThread()return true end
Key={F8=119}
package.preload.UEHelpers=function()return {GetKismetSystemLibrary=function()return obj()end,
 GetPlayer=function()return fixture_player end,GetPlayerController=function()return fixture_controller end}end
print=function()end
'''
fixture = r'''
r=RingedKnightArsenal
local state=dofile(script_dir..'CombatState.lua')
local json=dofile(script_dir..'dkjson.lua')
local file=assert(io.open(script_dir..'combat-profile.json','rb'))
local profile=assert(json.decode(file:read('*a')));file:close()
r.state=state.new(profile)
r.world=obj()
r.pc=obj({IsInputKeyDown=function()return false end,IsMoveInputIgnored=function(self)return self.move_lock or false end,
    SetIgnoreMoveInput=function(self,value)self.move_lock=value;record('move_lock',value)end})
local native_class=obj({GetFullName=function()
    return 'AnimBlueprintGeneratedClass /HuaShira/Characters/Hero/Hero_Hun/Animation/PBZ_ABP_Hun_Base.PBZ_ABP_Hun_Base_C'
end})
native=obj({
    GetClass=function()return native_class end,
    GetCurrentActiveMontage=function(self)return self.active end,
    Montage_Play=function(self,montage,rate,result_kind,start,stop_all)
        assert(rate==1 and result_kind==0 and start==0 and not stop_all)
        hook_callbacks[2]({get=function()return self end},{get=function()return montage end})
        self.active=montage;montage.active=true;montage.paused=false;record('play',montage)
        if fail_play then error('mock play failure')end
        return montage.length
    end,
    Montage_Pause=function(_,montage)montage.paused=true end,
    Montage_IsActive=function(_,montage)return montage.active end,
    Montage_IsPlaying=function(_,montage)return not montage.paused end,
    Montage_SetPosition=function(_,montage,position)montage.position=position;record('position',position)end,
    Montage_Stop=function(self,seconds,montage)
        if fail_restore then error('mock restore failure')end
        if self.active==montage then self.active=nil end
        montage.active=false;record('stop',{seconds=seconds,montage=montage})
    end,
})
local factory=obj({CreateSlotAnimationAsDynamicMontage_WithBlendSettings=function(_,asset,slot,blend_in)
    assert(({BoatSlot=true,LeftArmOverride=true,RightArmOverride=true})[slot:ToString()])
    local rate=math.abs(asset.RateScale)<=1e-8 and 1 or asset.RateScale
    return obj({asset=asset,slot=slot:ToString(),blend_in=blend_in.Blend.BlendTime,position=0,
        length=asset.duration/math.abs(rate),GetFullName=function()return 'AnimMontage Test.Dynamic'end,
        GetPlayLength=function(self)return self.length end,RateScale=1})
end})
local assets={}
for _,clip in pairs(profile.clips)do
    assets[clip.asset]=obj({bEnableRootMotion=false,duration=clip.duration,RateScale=1,
        GetPlayLength=function(self)return self.duration end,
        GetFullName=function()return 'AnimSequence '..clip.asset end})
end
local find_other=StaticFindObject
function StaticFindObject(path)
    if path=='/Script/Engine.Default__AnimMontage' then return factory end
    return assets[path] or find_other(path)
end
test_sequence=obj({bEnableRootMotion=false,duration=2,RateScale=1,
    GetPlayLength=function(self)return self.duration end,
    GetFullName=function()return 'AnimSequence Test.Sequence' end})
r.mesh=obj({pp=false,
    GetDisablePostProcessBlueprint=function(self)return self.pp end,
    SetDisablePostProcessBlueprint=function(self,value)self.pp=value;record('postprocess',value)end,
    PlayAnimation=function()error('Single-node playback would replace the native animation graph')end,
    GetAnimInstance=function()return native end,
    SetAnimInstanceClass=function()error('Native animation class must stay installed')end,
    K2_GetComponentToWorld=function()return {Rotation={X=0,Y=0,Z=0,W=1},Scale3D={X=1,Y=1,Z=1}}end,
    GetFullName=function()return 'Mesh Test.Mesh'end})
r.animation_blend=dofile(script_dir..'AnimationBlend.lua').new(r.mesh)
r.pawn=obj({actor=true,AttributeSetBase={Health={CurrentValue=100}},
    GetFullName=function()return 'Pawn Test.Player'end,
    GetWorld=function()return r.world end,
    K2_GetActorLocation=function()return {X=0,Y=0,Z=0}end,
    K2_SetActorLocation=function(_,position)record('displacement',position)end,
    K2_GetActorRotation=function(self)return {Pitch=0,Yaw=self.yaw or 0,Roll=0}end,
    K2_SetActorRotation=function(self,rotation)self.yaw=rotation.Yaw;record('turn',self.yaw);return true end,
    GetVelocity=function(self)return self.velocity or {X=0,Y=0,Z=0}end,
    GetActorForwardVector=function()return {X=1,Y=0,Z=0}end,
    CharacterMovement=obj({
        IsFalling=function()return falling==true end,
        IsMovingOnGround=function()return not falling end,
        StopMovementImmediately=function()end})})
r.attribute_component=obj({GetFullName=function()return 'Component Test.Attributes'end})
r.pawn.Mesh=r.mesh;r.pc.Pawn=r.pawn;fixture_player=r.pawn;fixture_controller=r.pc
r.equipment.display_slots=function()return {current=0,slots={}}end
r.sword=obj({SetVisibility=function(self,value,propagate)assert(propagate==false);self.visible=value;record('sword_visible',value)end,K2_GetComponentToWorld=function()
 return {Rotation={X=0,Y=0,Z=0,W=1},Translation={X=0,Y=0,Z=0},Scale3D={X=1,Y=1,Z=1}}
end});r.enabled=true;r.health=100
r.shield=obj({SetVisibility=function(self,value,propagate)assert(propagate==false);self.visible=value;record('shield_visible',value)end,
    K2_AttachToComponent=function(_,_,bone)record('shield_bone',bone:ToString())end,
    K2_SetRelativeTransform=function(_,transform)record('shield_transform',transform)end})
r.shield_stowed=false
r.active_item='RKA_RingedKnight';r.backpack=obj({CurrentMainWeaponID=FName(r.active_item)})
r.active_config=obj({['Change Armed Ability']=obj({path='Test.Configured.NativeChangeArmed'})})
r.weapon_component=obj({armed=true,IsArmed=function(self,tag)
    assert(tag.TagName:ToString()=='Weapon.Slot.Main');return self.armed
end})
r.guard_stamina_accounted=0
r.projectiles={};r.effects={};r.hidden={};r.owned={}
r.real_keys=r.keys
r.keys=function()return test_input or {}end
r.input_context=function(self)self.context=obj();record('rebuild_owned_input',true)end
RK_ShieldState=function()return '{"stamina_spent":0}'end
RK_CombatProtection=function(raw)
 local request=assert(json.decode(raw));record('protection',request)
 if request.phase=='prepare'then return '{"api":1,"finite_specs":true,"hp_immunity":false,"action_damage_taken_multiplier":0.2}'end
 return json.encode({api=1,active=request.active==true,hp_immunity=false,action_damage_taken_multiplier=.2})
end
RK_NativeHit=function(raw)
 local request=assert(json.decode(raw))
 if request.phase=='capabilities'then
  record('native_hit_capabilities',request)
  return json.encode({api=2,ultimate_charge_regen_tag='Damage.Attack.Attacker.UltimateChargeRegen',ultimate_charge_regen_default=0})
 end
 record('native_hit',request)
 assert(type(request.ultimate_charge_regen)=='number'and request.ultimate_charge_regen>=0)
 return '{"dispatched":true}'
end
art_balance=100;art_receipts={}
RK_ArtResource=function(raw)
 local q=assert(json.decode(raw))
 if q.phase=='capabilities'then
  return json.encode({api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1})
 end
 record('art_cost_attempt',q)
 if art_receipts[q.sequence]then return json.encode(art_receipts[q.sequence])end
 local receipt={api=1,resource='UltimateChargeCount',amount=1,session_token=q.session_token,sequence=q.sequence,before=art_balance,after=art_balance,
  paid=false,committed=false,dispatched=false,status='insufficient'}
 if art_balance>=1 then
  art_balance=art_balance-1;receipt.after=art_balance;receipt.paid=true;receipt.committed=true;receipt.dispatched=true;receipt.status='paid'
  art_receipts[q.sequence]=receipt;record('art_cost_paid',q)
 end
 return json.encode(receipt)
end
r.art_resource=dofile(script_dir..'ArtResource.lua').new(function(q)return json.decode(RK_ArtResource(json.encode(q)))end,'Test.Player')
r.state.pay_art=function(sequence)return r.art_resource:pay(sequence)end
query_calls={};query_hits={};query_actors={};query_ignore_objects={['Test.Player']=r.pawn}
function RK_NativeQuery(raw)
 local request=assert(json.decode(raw));query_calls[#query_calls+1]=request
 for _,path in ipairs(request.ignore or {})do
  local object=query_ignore_objects[path]
  if not object or not object:IsA(StaticFindObject('/Script/Engine.Actor'))then return nil,'RK native query: query ignored object is not Actor: '..path end
 end
 if request.phase=='capabilities'then return '{"api":1,"owned_parameter_frames":true,"trace":true,"trace_batch":true,"max_batch":64,"overlap":true,"blocking_hit_flags":true}'end
 if query_failure then return nil,'mock native query failed'end
 if request.phase=='trace'then return json.encode({api=1,phase='trace',owned_parameter_frames=true,hits=query_hits})end
 if request.phase=='trace_batch'then
  local results={};assert(#request.segments>0 and #request.segments<=64)
  for _,segment in ipairs(request.segments)do results[#results+1]={hits=query_hits}end
  return json.encode({api=1,phase='trace_batch',owned_parameter_frames=true,results=results})
 end
 if request.phase=='overlap'then return json.encode({api=1,phase='overlap',owned_parameter_frames=true,actors=query_actors})end
 error('Unexpected query phase')
end
function count(name)local n=0;for _,call in ipairs(calls)do if call.name==name then n=n+1 end end;return n end
function begin_pending_draw()
 draw_tags={};r.weapon_component.armed=false
 r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return draw_tags[tag.TagName:ToString()]==true end,
  TryActivateAbilityByClass=function(_,ability,allow_remote)
   assert(ability==r.active_config['Change Armed Ability']and allow_remote==true)
   record('native_draw_request',true);return true
  end})
 test_input={attack_pressed=true};r:tick(.016);test_input={}
 assert(r.pending_draw_entry and not r.state.clip and not r.playing)
 draw_tags['Ability.UpperBody.Hun.ChangeArmed']=true;r:tick(.016)
 assert(r.pending_draw_entry and r.pending_draw_entry.saw_change)
 return r.pending_draw_entry
end
'''
# Main caches Gameplay while loading, so set this method on its initial mock.
setup = setup.replace('function StaticFindObject()return obj()end',
                      'function StaticFindObject(path)return obj({path=path,GetTimeSeconds=function()return 1 end,IsGamePaused=function()return game_paused==true end,TransformDirection=function(_,basis,value)return value end,TransformLocation=function(_,basis,value)return value end})end')

cases = {
    'native_simple_execution_tag_owns_input_pose_and_shield_until_completion': r'''
local executing=true
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return executing and tag.TagName:ToString()=='Ability.Action.Hun.SimpleExecution'
end,TryActivateAbilityByClass=function()error('Simple execution must remain natively triggered')end})
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.state:enter('RKSS_Light1');r:play('RKSS_Light1');local played=count('play')
test_input={triangle_pressed=true};r:tick(.016);r:tick(.016)
assert(r.execution_active and r.shield_stowed and r.native_input_handoff)
assert(not r.state.clip and not r.playing and count('play')==played and count('remove_owned_input')==1)
executing=false;r:tick(.016)
assert(not r.execution_active and not r.shield_stowed and not r.native_input_handoff)
assert(count('rebuild_owned_input')==1 and not r.state.clip)
test_input={};r:tick(.016);assert(r.idle_playing)
''',
    'native_perfect_dodge_tag_yields_without_claiming_execution_or_stowing_shield': r'''
local dodging=true
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return dodging and tag.TagName:ToString()=='Ability.Action.Hun.PerfectDodge'
end,TryActivateAbilityByClass=function()error('Perfect dodge must remain natively triggered')end})
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.state:enter('RKSS_Light1');r:play('RKSS_Light1');local played=count('play')
test_input={triangle_pressed=true};r:tick(.016);r:tick(.016)
assert(r.native_input_handoff and not r.execution_active and not r.shield_stowed)
assert(not r.state.clip and not r.playing and count('play')==played and count('remove_owned_input')==1)
dodging=false;r:tick(.016)
assert(not r.native_input_handoff and not r.execution_active and not r.shield_stowed)
assert(count('rebuild_owned_input')==1 and not r.state.clip)
test_input={};r:tick(.016);assert(r.idle_playing)
''',
    'native_sequence_owns_input_without_a_montage_until_its_tag_ends': r'''
local sequence=true
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return sequence and tag.TagName:ToString()=='CharacterState.Native.Sequence'
end})
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
test_input={attack_pressed=true};r:tick(.016);r:tick(.016)
assert(not r.state.clip and not r.playing and r.native_input_handoff and count('play')==0)
assert(count('remove_owned_input')==1 and count('rebuild_owned_input')==0)
sequence=false;r:tick(.016)
assert(not r.native_input_handoff and not r.state.clip and count('play')==0 and count('rebuild_owned_input')==1)
test_input={};r:tick(.016)
assert(r.idle_playing and count('rebuild_owned_input')==1)
''',
    'nonpaused_interaction_advances_existing_projectiles_and_effects_without_new_combat': r'''
r.menu_blocked=function()return true end
r.keys=function()error('Interaction must not poll custom combat input')end
r.hit_window=function()error('Interaction must not start new contact windows')end
local elapsed=0
r.projectile_step=function(_,dt)elapsed=elapsed+dt;record('projectile_progress',dt)end
r.effects={{remaining=.05,object=obj({K2_DestroyComponent=function()record('expire_effect',true)end})}}
r:tick(0)
assert(elapsed==0 and r.effects[1].remaining==.05 and count('expire_effect')==0)
r:tick(.1);r:tick(.1)
assert(r.menu_suspended and math.abs(elapsed-.2)<1e-9 and count('projectile_progress')==2)
assert(#r.effects==0 and count('expire_effect')==1 and not r.state.clip and count('play')==0)
''',
    'paused_world_scheduler_suspends_without_advancing_projectiles_or_effects': r'''
game_paused=true
r.keys=function()error('Paused world must not poll custom combat input')end
r.projectile_step=function()error('Paused world must not advance thrown bombs')end
r.effects={{remaining=.05,object=obj({K2_DestroyComponent=function()error('Paused world must not age effects')end})}}
local invoked=false
for _,timer in ipairs(timers)do if timer.interval==1 then timer.callback();invoked=true;break end end
assert(invoked and r.menu_suspended and r.effects[1].remaining==.05 and not r.action_error)
assert(r.enabled and not r.state.clip and count('play')==0)
''',
    'changed_controller_possession_releases_old_combat_before_processing_input': r'''
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.state:enter('RKSS_EmberStart');r:play('RKSS_EmberStart');local played=count('play')
r.pc.Pawn=obj();r.keys=function()error('A stale pawn must not poll combat input')end
r:tick(.016)
assert(not r.enabled and not r.context and not r.playing and not r.action_protection_active and not r.move_lock)
assert(count('remove_owned_input')==1 and count('play')==played)
''',
    'same_pawn_mesh_replacement_releases_old_pose_input_and_hand_models': r'''
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.sword.K2_DestroyComponent=function()record('destroy_old_sword',true)end
r.shield.K2_DestroyComponent=function()record('destroy_old_shield',true)end
r.owned={r.sword,r.shield}
r.state:enter('RKSS_EmberStart');r:play('RKSS_EmberStart')
local old_mesh=r.mesh;local played=count('play')
local replacement=obj({GetAnimInstance=function()error('Do not touch the new native animation graph before supervisor rebuild')end})
r.pawn.Mesh=replacement;r.keys=function()error('A stale mesh must not process combat input')end
r:tick(.016)
assert(old_mesh:IsValid()and not r.enabled and not r.context and not r.playing and not r.move_lock)
assert(not old_mesh.pp and not r.action_protection_active and count('play')==played)
assert(count('remove_owned_input')==1 and count('destroy_old_sword')==1 and count('destroy_old_shield')==1)
''',
    'supervisor_waits_for_valid_replacement_mesh_and_rebuilds_only_once': r'''
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.state:enter('RKSS_EmberStart');r:play('RKSS_EmberStart')
local old_mesh=r.mesh;local weapons=r.weapon_component
local replacement=obj({GetAnimInstance=function()return native end})
r.pawn.Mesh=replacement
r.prepare_inventory=function()end;r.item_display.update=function()end
r.inventory.selection=function()return {id=r.active_item},r.backpack end
r.backpack.IsWeaponSnapSouled=function()return false end
r.equipment.configs.Weapon_RKA_RingedKnight=r.active_config
r.control_lease_guard={update=function()end,router=obj({GetActiveInputMode=function()return 1 end})}
local blocked=true;local enabled=0
r.menu_blocked=function()
 if blocked then assert(not r.enabled and not r.context and not r.playing,'Old mesh survived the menu early return')end
 return blocked
end
r.enable=function(self)
 assert(self.pawn.Mesh==replacement and replacement:IsValid()and not self.enabled)
 enabled=enabled+1;self.mesh=self.pawn.Mesh
 self.animation_blend=dofile(script_dir..'AnimationBlend.lua').new(self.mesh)
 self.weapon_component=weapons;self.enabled=true;self:input_context()
end
local supervise
for _,timer in ipairs(timers)do if timer.interval==250 then supervise=timer.callback;break end end
assert(supervise);supervise()
assert(old_mesh:IsValid()and not r.enabled and enabled==0 and count('remove_owned_input')==1)
blocked=false;r.pawn.Mesh=nil;supervise()
assert(not r.enabled and enabled==0 and not r.development_suspended,'Missing replacement must wait without an initialization failure')
r.pawn.Mesh=replacement;supervise();supervise()
assert(r.enabled and r.mesh==replacement and r.animation_blend.mesh==replacement and enabled==1)
assert(count('rebuild_owned_input')==1 and not r.development_suspended)
''',
    'unavailable_controller_possession_does_not_process_old_pawn_combat': r'''
r.pc.Pawn=nil;r.keys=function()error('Unknown possession must not poll the old pawn')end
r:tick(.016)
assert(not r.enabled and not r.playing and not r.context and not r.state.clip)
''',
    'supervisor_cleans_changed_pawn_before_a_new_owner_menu_can_block_refresh': r'''
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.state:enter('RKSS_EmberStart');r:play('RKSS_EmberStart')
local new_world=obj();local new_pawn=obj({Mesh=obj(),AttributeSetBase={Health={CurrentValue=100}},GetWorld=function()return new_world end})
local new_pc=obj({Pawn=new_pawn});local new_owner=obj()
fixture_player=new_pawn;fixture_controller=new_pc
r.prepare_inventory=function()end;r.item_display.update=function()end
r.inventory.selection=function(_,world)assert(world==new_world);return {id=r.active_item},new_owner end
r.control_lease_guard={update=function()end,router=obj({GetActiveInputMode=function()return 0 end})}
local checked=false
r.menu_blocked=function(_,pc,pawn)
 assert(pc==new_pc and pawn==new_pawn)
 assert(not r.enabled and not r.context and not r.playing,'Old owner survived until the blocked return')
 checked=true;return true
end
for _,timer in ipairs(timers)do if timer.interval==250 then timer.callback();break end end
assert(checked,'Supervisor did not reach owner/menu boundary: '..tostring(r.initialization_error))
assert(checked and not r.enabled and count('remove_owned_input')==1 and not r.action_protection_active and not r.move_lock)
assert(not r.development_suspended)
''',
    'holstered_state_releases_combat_without_restarting_idle_protection_or_move_lock': r'''
r.state:enter('RKSS_EmberStart');r:play('RKSS_EmberStart')
assert(r.action_protection_active and r.move_lock and r.playing)
local played=count('play');local before=#calls
r.weapon_component.armed=false
for i=1,4 do r:tick(.016);r:update_idle(false,.016)end
assert(r.holstered and r.holster_yield and r.native_input_handoff)
assert(not r.playing and not r.idle_playing and not r.state.clip and count('play')==played)
assert(not r.action_protection_active and not r.guard_bridge_active and not r.move_lock and not r.pc.move_lock)
assert(r.sword.visible==false and r.shield.visible==false)
for i=before+1,#calls do
 local call=calls[i]
 assert(not(call.name=='protection'and call.value.active),'Holstered state renewed action protection')
 assert(not(call.name=='move_lock'and call.value),'Holstered state reacquired the movement lock')
end
''',
    'native_change_armed_transition_yields_owned_input_once_before_armed_state_changes': r'''
local original_context=obj();r.context=original_context
r.input_subsystem=obj({RemoveMappingContext=function(_,context)
 assert(context==original_context);record('remove_owned_input',true)
end})
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return tag.TagName:ToString()=='Ability.UpperBody.Hun.ChangeArmed'
end,TryActivateAbilityByClass=function()error('Do not request draw during the original transition')end})
r:update_idle(false);local played=count('play')
test_input={attack=true,attack_pressed=true}
r:tick(.016);r:tick(.016)
assert(r.weapon_component.armed and not r.holstered and r.arm_changing and r.holster_yield)
assert(r.native_input_handoff and not r.context and count('remove_owned_input')==1)
assert(not r.playing and not r.state.clip and count('play')==played and count('rebuild_owned_input')==0)
''',
    'completed_native_draw_restores_input_once_and_discards_the_return_frame': r'''
local changing=false
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return changing and tag.TagName:ToString()=='Ability.UpperBody.Hun.ChangeArmed'
end})
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.weapon_component.armed=false;r:tick(.016)
assert(r.holstered and r.native_input_handoff and count('remove_owned_input')==1)
r.weapon_component.armed=true;changing=true;r:tick(.016)
assert(r.arm_changing and r.native_input_handoff and count('rebuild_owned_input')==0)
changing=false;test_input={attack=true,attack_pressed=true};r:tick(.016)
assert(not r.holstered and not r.holster_yield and not r.native_input_handoff)
assert(not r.state.clip and count('play')==0 and count('rebuild_owned_input')==1)
assert(r.sword.visible and r.shield.visible)
test_input={};r:tick(.016);r:tick(.016)
assert(r.idle_playing and not r.state.clip and count('rebuild_owned_input')==1)
''',
    'interaction_syncs_holstered_models_before_suspension_without_polling_or_drawing': r'''
r.weapon_component.armed=false
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function()error('Interaction must never request a draw')end})
r.equipment_visuals.update=function(_,pawn,owner,drawn,holstered)
 assert(pawn==r.pawn and owner==r.backpack and drawn and holstered)
 record('holstered_visual_sync',true)
end
r.control_lease_guard={update=function()end,interaction_active=function()
 assert(r.holstered and count('holstered_visual_sync')==1,'Models must sync before interaction early return')
 return true
end}
r.keys=function()error('Interaction must not poll custom combat inputs')end
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r:tick(.016);r:tick(.016)
assert(r.menu_suspended and r.native_input_handoff and count('remove_owned_input')==1)
assert(r.sword.visible==false and r.shield.visible==false and count('play')==0)
r:release_combat_pose()
assert(r.sword.visible==false,'A later native montage handoff must not reveal the holstered sword')
''',
    'holstered_attack_edges_request_exact_configured_native_class_and_respect_rejection': r'''
local function forbidden()error('Do not manufacture armed state or completion events')end
local accepted=true
r.weapon_component.armed=false;r.weapon_component.SetArmed=forbidden
r.pawn.SendGameplayEvent=forbidden
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 SendGameplayEvent=forbidden,HandleGameplayEvent=forbidden,AddLooseGameplayTag=forbidden,
 RemoveLooseGameplayTag=forbidden,SetLooseGameplayTagCount=forbidden,
 TryActivateAbilitiesByTag=function()error('Use the exact configured ability class, not a broad tag request')end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(allow_remote==true and ability==r.active_config['Change Armed Ability'])
  record('native_draw_request',ability);return accepted
 end})
r:tick(.016)
for _,result in ipairs({true,false})do
 accepted=result
 r.active_config['Change Armed Ability']=obj({path='Test.CurrentConfigured.NativeChangeArmed'})
 for _,edge in ipairs({'attack_pressed','triangle_pressed','art_pressed'})do
  local before=count('native_draw_request');test_input={[edge]=true};r:tick(.016)
  assert(count('native_draw_request')==before+1)
  test_input={attack=true,triangle=true,art=true};r:tick(.016)
  assert(count('native_draw_request')==before+1,'A held button must not repeat a draw request')
  assert(r.weapon_component.armed==false and r.holstered and not r.state.clip and count('play')==0)
  if result then
   assert(r.pending_draw_entry and not r.switch_entry);r.pending_draw_entry=nil
  else assert(not r.pending_draw_entry and not r.switch_entry)end
 end
end
test_input={guard_pressed=true,circle_pressed=true};r:tick(.016)
assert(count('native_draw_request')==6 and r.weapon_component.armed==false and r.holstered)
assert(r:request_native_draw({attack_pressed=true})==false,'Native rejection must be returned without a fallback')
assert(not r.state.clip and count('play')==0 and count('native_hit')==0)
''',
    'holstered_ground_triangle_accepts_original_execution_before_requesting_draw': r'''
r.weapon_component.armed=false;r.execution_component=obj();local executing=false
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return executing and tag.TagName:ToString()=='Ability.Action.Execution'
end,TryActivateAbilityByClass=function(_,ability,allow_remote)
 assert(allow_remote==true)
 if ability==r.active_config['Change Armed Ability']then error('Accepted execution must not request draw')end
 record('execution_attempt',ability.path)
 if ability.path:find('GA_PerformExecution.',1,true)then executing=true;return true end
 return false
end})
local request=r.request_native_draw;local draw_result
r.request_native_draw=function(self,input)draw_result=request(self,input);return draw_result end
test_input={triangle_pressed=true};r:tick(.016)
assert(count('execution_attempt')==3 and executing and r.execution_active and draw_result==false)
assert(not r.pending_draw_entry and not r.switch_entry and not r.state.clip and count('play')==0)
assert(r.native_input_handoff and r.shield_stowed)
r:tick(.016);assert(count('execution_attempt')==3,'Original execution ownership must prevent a duplicate request')
''',
    'holstered_ground_triangle_rejected_execution_falls_back_to_configured_native_draw': r'''
r.weapon_component.armed=false;r.execution_component=obj();local order={}
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(allow_remote==true)
  if ability==r.active_config['Change Armed Ability']then order[#order+1]='draw';return true end
  order[#order+1]=ability.path;return false
 end})
test_input={triangle_pressed=true};r:tick(.016)
assert(#order==4 and order[4]=='draw')
assert(order[1]:find('GA_PerformSpecialAttack.',1,true)and order[2]:find('GA_PerformShachiWeaponExecution.',1,true)
 and order[3]:find('GA_PerformExecution.',1,true))
assert(r.pending_draw_entry and not r.execution_active and not r.state.clip and count('play')==0)
''',
    'holstered_guard_triangle_requests_draw_without_attempting_execution': r'''
r.weapon_component.armed=false;r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(ability==r.active_config['Change Armed Ability']and allow_remote==true,'Guard combination must not execute')
  record('native_draw_request',true);return true
 end})
test_input={triangle_pressed=true,guard=true};r:tick(.016)
assert(count('native_draw_request')==1 and r.pending_draw_entry and not r.execution_active and not r.state.clip)
''',
    'holstered_air_triangle_never_attempts_ground_execution': r'''
r.weapon_component.armed=false;r.execution_component=obj();falling=true
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(ability==r.active_config['Change Armed Ability']and allow_remote==true,'Airborne triangle must not execute')
  record('native_draw_request',true);return true
 end})
test_input={triangle_pressed=true};r:tick(.016)
assert(count('native_draw_request')==1 and not r.execution_active and not r.state.clip and count('play')==0)
''',
    'holstered_native_busy_triangle_never_repeats_execution_or_draw_activation': r'''
r.weapon_component.armed=false;r.execution_component=obj();local active
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return tag.TagName:ToString()==active end,
 TryActivateAbilityByClass=function()error('Original ownership must block both execution and draw requests')end})
test_input={triangle_pressed=true}
for _,tag in ipairs({'Ability.Action.Execution','Ability.Executed','CharacterState.Native.Sequence',
 'CharacterState.FlowIdle','Ability.Action.Hun.Dash','Ability.UpperBody.Hun.ChangeArmed',
 'Ability.Action.Hun.SimpleExecution','Ability.Action.Hun.PerfectDodge'})do
 active=tag;r:tick(.016)
 assert(not r.pending_draw_entry and not r.state.clip and count('play')==0)
end
active=nil;native.active=obj();r:tick(.016)
assert(not r.pending_draw_entry and not r.state.clip and count('play')==0)
''',
    'completed_draw_reuses_switch_attack_animation_contact_windows_and_audio_inputs': r'''
local json=dofile(script_dir..'dkjson.lua')
local profile=r.state.profile
local function collect_entry(draw)
 r:release_combat_pose();r.state=dofile(script_dir..'CombatState.lua').new(profile)
 r.native_reaction=nil;r.native_input_handoff=false;r.holster_yield=false;r.holstered=false
 r.menu_suspended=false;r.discard_combat_input_once=false;r.switch_entry=nil;r.pending_draw_entry=nil
 local captured={audio={},hits={},plays={}};local capturing=false
 r.audio.advance=function(_,_,state)
  if capturing then captured.audio[#captured.audio+1]={clip=state.clip,time=state.time}end
 end
 r.hit_window=function(_,event)
  if capturing then captured.hits[#captured.hits+1]={index=event.index,time=event.time,hit=event.hit}end
 end
 if draw then
  local pending=begin_pending_draw()
  local before=count('native_draw_request')
  test_input={triangle_pressed=true};r:tick(.016);test_input={}
  assert(r.pending_draw_entry==pending and count('native_draw_request')==before)
  local foreign=obj();native.active=foreign;r.weapon_component.armed=true;r:tick(.016)
  assert(r.pending_draw_entry and not r.state.clip and not r.playing)
  draw_tags['Ability.UpperBody.Hun.ChangeArmed']=nil;r:tick(.016)
  assert(r.pending_draw_entry and native.active==foreign and not r.state.clip)
  native.active=nil;r:tick(.016)
  assert(r.pending_draw_entry and not r.native_input_handoff and not r.state.clip)
 else
  r.weapon_component.armed=true
  r.ability_system=obj({HasMatchingGameplayTag=function()return false end})
  r.switch_entry={receipt={id=r.active_item,pawn=r.pawn:GetAddress(),owner=r.backpack:GetAddress()},age=0}
 end
 capturing=true;local before=count('play');local finished=false
 for i=1,300 do
  test_input={};r:tick(1/60)
  if i==1 then assert(r.state.clip=='RKSS_Heavy1Release'and not r.pending_draw_entry and not r.switch_entry)end
  if not r.state.clip then finished=true;break end
 end
 assert(finished and #captured.hits>0 and #captured.audio>0)
 local played=0
 for _,call in ipairs(calls)do
  if call.name=='play'then
   played=played+1
   if played>before then captured.plays[#captured.plays+1]=call.value.asset:GetFullName()end
  end
 end
 return json.encode(captured)
end
local switched=collect_entry(false)
local drawn=collect_entry(true)
assert(drawn==switched,'Draw entry must use the same animation, contact windows and audio inputs as weapon switching')
assert(count('native_draw_request')==1)
''',
    'pending_draw_cancels_during_original_actions_even_before_weapon_becomes_armed': r'''
for _,tag in ipairs({'Ability.Action.Execution','Ability.Executed','CharacterState.Native.Sequence',
 'Ability.SpecialMove','Ability.Action.Hun.SpecialMove','CharacterState.AbilityState.InSpecialPerform',
 'CharacterState.FlowIdle','CharacterState.FlowIdle.CantBreak','Ability.Action.Hun.Dash',
 'Ability.Action.Hun.SimpleExecution','Ability.Action.Hun.PerfectDodge'})do
 begin_pending_draw();draw_tags[tag]=true;r:tick(.016)
 assert(not r.pending_draw_entry and not r.switch_entry,'Pending draw survived '..tag..' while holstered')
 draw_tags={};r.weapon_component.armed=true
 for i=1,4 do r:tick(.016);assert(not r.state.clip,'Cancelled draw attacked after '..tag)end
 r:release_combat_pose()
end
''',
    'pending_draw_cancels_on_interaction_and_does_not_attack_after_menu_exit': r'''
begin_pending_draw();local interacting=true
r.control_lease_guard={update=function()end,interaction_active=function()return interacting end}
r:tick(.016)
assert(r.menu_suspended and not r.pending_draw_entry and not r.switch_entry)
interacting=false;draw_tags={};r.weapon_component.armed=true
for i=1,5 do r:tick(.016);assert(not r.state.clip)end
assert(not r.menu_suspended and count('native_draw_request')==1)
''',
    'pending_draw_real_hit_cancels_without_an_owned_montage_and_other_owners_do_not': r'''
local pending=begin_pending_draw();assert(not r.playing)
local other=obj({GetOwner=function()return obj()end})
hook_callbacks[1]({get=function()return other end})
assert(r.pending_draw_entry==pending)
local own=obj({GetOwner=function()return r.pawn end})
hook_callbacks[1]({get=function()return own end})
assert(not r.pending_draw_entry and not r.switch_entry and not r.playing)
draw_tags={};r.weapon_component.armed=true
for i=1,4 do r:tick(.016);assert(not r.state.clip)end
''',
    'pending_draw_cancels_when_native_air_takes_over_before_weapon_becomes_armed': r'''
begin_pending_draw();falling=true;r:tick(.016)
assert(not r.pending_draw_entry and not r.switch_entry)
falling=false;draw_tags={};r.weapon_component.armed=true
for i=1,20 do r:tick(.016);assert(not r.state.clip)end
''',
    'pending_draw_times_out_without_late_attack_and_requires_observed_change_armed': r'''
r.weapon_component.armed=false
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,TryActivateAbilityByClass=function()return true end})
test_input={attack_pressed=true};r:tick(.016);test_input={}
assert(r.pending_draw_entry and not r.pending_draw_entry.saw_change)
r.weapon_component.armed=true
for i=1,65 do r:tick(.1);assert(not r.state.clip and not r.switch_entry)end
assert(not r.pending_draw_entry)
''',
    'pending_draw_invalidates_changed_receipt_owners_or_item_without_a_switch_entry': r'''
for _,field in ipairs({'pawn','owner','id'})do
 local pending=begin_pending_draw()
 pending.receipt[field]=field=='id'and 'OtherWeapon'or -1
 r:tick(.016);assert(not r.pending_draw_entry and not r.switch_entry)
 draw_tags={};r.weapon_component.armed=true
 for i=1,4 do r:tick(.016);assert(not r.state.clip)end
 r:release_combat_pose()
end
''',
    'native_weapon_switch_and_death_clear_pending_draw_without_attack': r'''
begin_pending_draw();r.backpack.CurrentMainWeaponID=FName('NativeOther');r:tick(.016)
assert(not r.enabled and not r.pending_draw_entry and not r.switch_entry and not r.state.clip)
r.enabled=true;r.backpack.CurrentMainWeaponID=FName(r.active_item)
r.weapon_component=obj({armed=false,IsArmed=function(self)return self.armed end})
begin_pending_draw();r.pawn.AttributeSetBase.Health.CurrentValue=0;r:tick(.016)
assert(not r.enabled and not r.pending_draw_entry and not r.switch_entry and not r.state.clip)
''',
    'holstered_draw_requests_preserve_native_execution_traversal_dialogue_and_sequence_ownership': r'''
local active
r.weapon_component.armed=false
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return tag.TagName:ToString()==active end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(ability==r.active_config['Change Armed Ability']and allow_remote==true)
  record('native_draw_request',true);return true
 end})
test_input={attack_pressed=true}
for _,tag in ipairs({'Ability.Action.Execution','Ability.Executed','CharacterState.Native.Sequence',
 'Ability.SpecialMove','Ability.Action.Hun.SpecialMove','CharacterState.AbilityState.InSpecialPerform',
 'CharacterState.FlowIdle','CharacterState.FlowIdle.CantBreak','Ability.Action.Hun.Dash',
 'Ability.Action.Hun.SimpleExecution','Ability.Action.Hun.PerfectDodge'})do
 active=tag;r:tick(.016)
 assert(count('native_draw_request')==0 and not r.state.clip and count('play')==0,tag)
end
active=nil;r:tick(.016);assert(count('native_draw_request')==1)
''',
    'holstered_draw_requests_preserve_a_foreign_montage_until_it_finishes': r'''
r.weapon_component.armed=false
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(ability==r.active_config['Change Armed Ability']and allow_remote==true)
  record('native_draw_request',true);return true
 end})
local foreign=obj();native.active=foreign;test_input={triangle_pressed=true}
r:tick(.016);r:tick(.016)
assert(native.active==foreign and count('native_draw_request')==0 and count('stop')==0)
native.active=nil;r:tick(.016);assert(count('native_draw_request')==1)
''',
    'dead_holstered_player_disables_without_querying_or_requesting_native_draw': r'''
r.pawn.AttributeSetBase.Health.CurrentValue=0
r.weapon_component.IsArmed=function()error('Death must stop before armed-state handling')end
r.ability_system=obj({TryActivateAbilityByClass=function()error('Dead player must not request draw')end})
test_input={attack_pressed=true};r:tick(.016)
assert(not r.enabled and not r.state.clip and not r.move_lock and count('play')==0)
''',
    'inactive_guard_is_submitted_once_and_active_guard_updates_facing': r'''
local calls={};local json=dofile(script_dir..'dkjson.lua')
RK_ShieldState=function(text)calls[#calls+1]=json.decode(text);return '{"stamina_spent":0}'end
r.guard_bridge_active=nil;r.guard_report=nil
for i=1,20 do r:update_guard_state(false)end
assert(#calls==1 and calls[1].active==false)
r:update_guard_state(true);r:update_guard_state(true)
assert(#calls==3 and calls[2].active and calls[3].component)
r:update_guard_state(false);r:update_guard_state(false);assert(#calls==4)
r:disable('test');assert(r.guard_bridge_active==nil)
''',
    'hit_history_prunes_finished_attacks_and_keeps_live_plunge_and_bombs': r'''
r.state.serial=9;r.state.plunge_serial=7;r.seen_serial=nil
r.projectiles={{key='bomb:3'}};r.seen={}
for i=1,1000 do r.seen['90:'..i..'/enemy']=true end
r.seen['9:1/enemy']=true;r.seen['plunge:7:air/enemy']=true
r.seen['bomb:3/enemy']=true;r.seen['bomb:30/enemy']=true
r:prune_hit_history()
local count=0;for _ in pairs(r.seen)do count=count+1 end
assert(count==3 and r.seen['9:1/enemy'] and r.seen['plunge:7:air/enemy'] and r.seen['bomb:3/enemy'])
r:prune_hit_history();assert(r.seen['9:1/enemy'])
r.state.serial=10;r.state.plunge_serial=nil;r.projectiles={};r:prune_hit_history()
assert(next(r.seen)==nil)
''',
    'air_blade_covers_all_authored_sword_contacts_with_one_shared_hit_key': r'''
local geometry=dofile(script_dir..'ArtFlameTrace.lua')
local profile=r.state.profile
local arts={};for _,n in ipairs(profile.art.light_chain)do arts[n]=true end;arts[profile.art.heavy]=true
local blade={space='sword_local_cm',base=profile.art.hit_volume.base,steel_tip=profile.art.hit_volume.steel_tip,tip_extension_cm=0,radius_cm=24}
local target=obj();local last_end,last_radius,keys,queries,forwards
r.sword.K2_GetComponentToWorld=function()error('Do not read stale rendered attachment pose for hit geometry')end
r.trace=function(_,a,b,radius)queries=queries+1;last_end=b;last_radius=radius;return {{actor=target,native_snapshot=true}}end
r.trace_batch=function(self,segments)local result={};for _,s in ipairs(segments)do result[#result+1]=self:trace(s.start,s.finish,s.radius)end;return result end
r.damage=function(_,_,_,key)keys[key]=true;forwards=forwards+1 end
local covered=0
for name,clip in pairs(profile.clips)do
 if name:match('^RKSS_Light%d$')or name:match('^RKSS_Heavy[12]Release$')or arts[name]or name==profile.jump.loop or name==profile.jump.land then
  r.state.clip=name
  for index,hit in ipairs(clip.hits)do
   keys={};queries=0;forwards=0
   r:hit_window({hit=hit,time=hit.start,serial=19,index=index,light_index=1})
   assert(queries==#hit.capsules+1 and forwards==queries,'Expected only one extra trace per contact')
   local count=0;for key in pairs(keys)do assert(key=='19:'..index);count=count+1 end;assert(count==1,'Steel and air volume must share damage key')
   local volume=arts[name]and geometry.scaled_segment(profile.art.hit_volume,profile.air_blade.art_reach_scale)or geometry.scaled_segment(blade,2)
   local dx,dy,dz=volume.finish.X-volume.start.X,volume.finish.Y-volume.start.Y,volume.finish.Z-volume.start.Z
   local expected=geometry.swept_segments(clip,hit.start,hit.start,math.sqrt(dx*dx+dy*dy+dz*dz),24,4)[1]
   for _,axis in ipairs({'X','Y','Z'})do assert(math.abs(last_end[axis]-expected.finish[axis])<1e-8)end
   assert(last_radius==24)
   covered=covered+1
  end
 end
end
assert(covered>=12)
''',

    'charged_heavy_doubles_damage_and_enemy_anger_without_changing_poise_regen_or_base_hit': r'''
local contacts=0
r.trace=function()return {{actor=obj(),native_snapshot=true}}end
r.trace_batch=function(self,segments)local result={};for _,s in ipairs(segments)do result[#result+1]=self:trace(s.start,s.finish,s.radius)end;return result end
for _,name in ipairs({'RKSS_Heavy1Release','RKSS_Heavy2Release','RKSS_Light1','RKSS_EmberHeavy'})do
 r.state.clip=name
 local hit=r.state.profile.clips[name].hits[1]
 local base_physical,base_fire=hit.physical,hit.fire
 for _,charged in ipairs({false,true})do
  r.damage=function(_,_,_,_,physical,fire,kind,poise,anger,multiplier,ultimate)
   local scale=charged and name:match('^RKSS_Heavy[12]Release$')and 2 or 1
   assert(physical==base_physical*scale and fire==base_fire*scale)
   assert(poise==hit.poise and anger==hit.anger*scale and multiplier==hit.hit_anger_multiplier and ultimate==hit.ultimate_charge_regen)
   contacts=contacts+1
  end
  r:hit_window({hit=hit,time=hit.start,serial=1,index=1,light_index=1,heavy_charged=charged})
  assert(hit.physical==base_physical and hit.fire==base_fire)
 end
end
assert(contacts>=8)
''',

    'heavy_exit_blends_longer_without_delaying_next_attack': r'''
for _,name in ipairs({'RKSS_Heavy1Release','RKSS_Heavy2Release'})do
 r.state:enter(name);r:play(name,false);r.state:cancel()
 r:update_idle(false,1/60)
 assert(r.idle_playing and r.animation_blend.montage.blend_in==.45 and not r.pc.move_lock)
 r.state:enter('RKSS_Light1');r:play('RKSS_Light1',false)
 assert(r.playing and not r.idle_playing and r.last_action_clip=='RKSS_Light1')
 r.state:enter(name);r:play(name,false);r.state:cancel()
 local montage=r.animation_blend.montage
 r:update_idle(true,1/60)
 assert(not r.playing and not r.pc.move_lock)
 local found=false
 for _,fade in ipairs(r.animation_blend.retiring or {})do
  if fade.montage==montage then assert(fade.remaining==.36);found=true end
 end
 assert(found)
end
''',

    'native_interaction_without_ui_or_flow_tags_owns_pose_until_end': r'''
local interacting=true
r.control_lease_guard={update=function()end,interaction_active=function(_,pawn)assert(pawn==r.pawn);return interacting end}
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r:play('RKSS_Light1');r.state.clip='RKSS_Light1'
r.keys=function()error('Native interaction must not poll custom combat input')end
r:tick(.016);r:tick(.016)
assert(r.menu_suspended and not r.playing and not r.state.clip and count('remove_owned_input')==1)
interacting=false;r.keys=function()return {attack_pressed=true,triangle_pressed=true}end;r:tick(.016)
assert(not r.menu_suspended and not r.state.clip and count('rebuild_owned_input')==1)
r.keys=function()return {}end;r:tick(.016);assert(r.idle_playing)
''',
    'native_traversal_and_special_performance_own_pose_without_a_montage': r'''
local active
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return tag.TagName:ToString()==active end})
for _,tag in ipairs({'Ability.SpecialMove','Ability.Action.Hun.SpecialMove','CharacterState.AbilityState.InSpecialPerform',
        'CharacterState.FlowIdle','CharacterState.FlowIdle.CantBreak'})do
 active=tag;r.native_reaction=nil;r.state:enter('RKSS_Light1');r:play('RKSS_Light1')
 test_input={attack_pressed=true,triangle_pressed=true};r:tick(.016)
 assert(r.native_input_handoff and not r.playing and not r.state.clip)
 r:tick(.016);assert(not r.playing and not r.state.clip)
 active=nil;r:tick(.016);assert(not r.native_input_handoff and not r.state.clip)
end
''',
    'tutorial_restricts_combat_once_then_resume_discards_confirmation_press': r'''
local normal=true
r.pc.PlayerInput=obj({AppliedInputContextData={ForEach=function(_,callback)
 callback({get=function()return obj({GetFullName=function()return normal and 'InputMappingContext /PBZInput/IMC_Default.IMC_Default' or 'InputMappingContext /Game/PBZContent/Input/IMC_OnlyLook.IMC_OnlyLook'end})end})
end}})
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r:play('RKSS_Light1');r.state.clip='RKSS_Light1';normal=false
r.keys=function()error('Restricted input was polled for custom combat')end
r:tick(.016);r:tick(.016)
assert(r.menu_suspended and not r.playing and not r.state.clip and count('remove_owned_input')==1)
r.keys=function()return {triangle_pressed=true}end;normal=true
r:tick(.016)
assert(not r.menu_suspended and not r.state.clip and count('rebuild_owned_input')==1)
r.keys=function()return {}end;r:tick(.016)
assert(r.idle_playing and count('rebuild_owned_input')==1)
''',
    'handoff_return_primes_held_keys_without_synthesizing_a_new_attack': r'''
r.keys=r.real_keys;r.last_keys={};r.native_input_handoff=true
r.pc.IsInputKeyDown=function(_,key)return key.KeyName:ToString()=='F'end
r.pc.WasInputKeyJustPressed=function()return false end
r.pc.GetInputAnalogKeyState=function()return 0 end
r:handoff_native_input(false)
local keys=r:keys()
assert(keys.triangle and not keys.triangle_pressed and not keys.circle_pressed)
''',
    'native_handoff_expires_cosmetic_effects_without_stopping_original_animation': r'''
local montage=obj();native.active=montage
r.effects={{remaining=.001,object=obj({K2_DestroyComponent=function()record('expire_effect',true)end})}}
r:tick(.016)
assert(#r.effects==0 and count('expire_effect')==1 and native.active==montage)
''',
    'original_execution_channels_accept_at_most_one_and_reject_to_heavy': r'''
r.execution_component=obj()
local target=nil
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function(_,ability)
  record('execution_attempt',ability.path)
  return target and ability.path:find(target..'.',1,true)~=nil or false
 end})
for _,name in ipairs({'GA_PerformSpecialAttack','GA_PerformShachiWeaponExecution','GA_PerformExecution'})do
 target=name;r.native_input_handoff=false;r.native_reaction=nil;r.execution_active=false
 local before=count('execution_attempt')
 assert(r:try_execution() and r.native_input_handoff)
 local last;for _,c in ipairs(calls)do if c.name=='execution_attempt'then last=c end end;assert(last.value:find(name..'.',1,true))
 assert(count('execution_attempt')-before<=3)
end
r.native_input_handoff=false;r.native_reaction=nil;r.execution_active=false;target=nil
local before=count('execution_attempt');assert(not r:try_execution())
assert(count('execution_attempt')-before==3 and not r.native_input_handoff)
''',
    'native_handoff_does_not_stop_an_existing_bomb_or_damage_native_montage': r'''
local montage=obj();native.active=montage
r.projectile_step=function()record('projectile_progress',true)end
r:tick(.016);r:tick(.016)
assert(count('projectile_progress')==2 and native.active==montage and r.native_input_handoff)
''',
    'restricted_native_input_modes_block_custom_polling_without_resetting_game_modes': r'''
local context_name='InputMappingContext /Game/PBZContent/Input/IMC_OnlyLook.IMC_OnlyLook'
r.pc.PlayerInput=obj({AppliedInputContextData={ForEach=function(_,callback)
 callback({get=function()return obj({GetFullName=function()return context_name end})end})
end}})
assert(r:native_input_blocked(r.pc),'OnlyLook must not allow raw combat polling')
context_name='InputMappingContext /PBZInput/IMC_Default.IMC_Default'
assert(not r:native_input_blocked(r.pc))
''',
    'native_takeover_releases_only_owned_mapping_once_and_restores_once': r'''
local executing=true
local original_context=obj();r.context=original_context
r.input_subsystem=obj({RemoveMappingContext=function(_,context)assert(context==original_context);record('remove_owned_input',true)end})
r.input_context=function(self)record('rebuild_owned_input',true);self.context=obj()end
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return executing and tag.TagName:ToString()=='Ability.Action.Execution'end,
 TryActivateAbilityByClass=function()error('Native owns follow-up input; Lua must not duplicate activation')end})
r:update_idle(false)
test_input={triangle=true,triangle_pressed=true};r:tick(.016);r:tick(.016)
assert(count('remove_owned_input')==1 and not r.context and r.native_input_handoff)
assert(not r.state.clip and not r.playing)
executing=false;r:tick(.016)
assert(count('rebuild_owned_input')==1 and not r.native_input_handoff and not r.state.clip)
test_input={};r:tick(.016)
assert(count('rebuild_owned_input')==1)
''',
    'foreign_boss_montage_keeps_original_qte_input_until_tail_finishes': r'''
local boss_montage=obj();native.active=boss_montage
r.context=obj();r.input_subsystem=obj({RemoveMappingContext=function()record('remove_owned_input',true)end})
r.input_context=function(self)record('rebuild_owned_input',true);self.context=obj()end
r.ability_system=obj({HasMatchingGameplayTag=function()return false end})
test_input={attack_pressed=true,triangle_pressed=true,circle_pressed=true};r:tick(.016)
assert(r.native_input_handoff and count('remove_owned_input')==1)
assert(native.active==boss_montage and not r.state.clip and count('play')==0)
r:tick(.016);assert(count('remove_owned_input')==1)
native.active=nil;r:tick(.016)
assert(count('rebuild_owned_input')==1 and not r.state.clip)
''',
    'hit_window_forwards_the_ultimate_coefficient_without_reusing_enemy_resource_damage': r'''
r.state.clip='RKSS_Heavy1Release'
local original=r.state.profile.clips.RKSS_Heavy1Release.hits[1]
local hit={};for key,value in pairs(original)do hit[key]=value end
hit.ultimate_charge_regen=.625;hit.anger=1.026;hit.hit_anger_multiplier=1
local target=obj({actor=true})
r.trace=function()return {{native_snapshot=true,actor=target,ImpactPoint={X=1,Y=0,Z=0},ImpactNormal={X=0,Y=0,Z=1}}}end
r.trace_batch=function(self,segments)local result={};for _,s in ipairs(segments)do result[#result+1]=self:trace(s.start,s.finish,s.radius)end;return result end
local forwards=0
r.damage=function(_,actor,snapshot,key,physical,fire,kind,poise,anger,hit_multiplier,ultimate)
 assert(actor==target and kind=='sword'and anger==1.026 and hit_multiplier==1 and ultimate==.625)
 forwards=forwards+1
end
r:hit_window({serial=1,index=1,time=hit.start,hit=hit})
assert(forwards==#hit.capsules+1)
''',
    'batch_sweep_uses_one_native_request_with_ordered_snapshots_and_shared_ignore': r'''
local snapshot={target='',point={X=1,Y=2,Z=3},normal={X=0,Y=0,Z=1},blocking=false,start_penetrating=false}
query_hits={snapshot};query_calls={}
local segments={};for i=1,64 do segments[i]={start={X=i,Y=0,Z=0},finish={X=i,Y=10,Z=0},radius=24}end
local result=r:trace_batch(segments)
assert(#query_calls==1 and query_calls[1].phase=='trace_batch'and #query_calls[1].segments==64)
assert(#query_calls[1].ignore==1 and query_calls[1].ignore[1]=='Test.Player')
assert(#result==64)
for _,hits in ipairs(result)do assert(#hits==1 and hits[1].native_snapshot and hits[1].ImpactPoint.Y==2 and not hits[1].blocking)end
assert(not pcall(function()r:trace_batch({})end))
segments[65]=segments[1];assert(not pcall(function()r:trace_batch(segments)end))
RK_NativeQuery=function()return '{"api":1,"phase":"trace_batch","owned_parameter_frames":true,"results":[]}'end
assert(not pcall(function()r:trace_batch({segments[1]})end),'Truncated native batch must fail closed')
''',
    'all_sword_windows_batch_skipped_poses_with_bounded_radius_and_one_damage_identity': r'''
local target=obj();local keys,queries
r.trace=function()return {{actor=target,native_snapshot=true}}end
r.sword.K2_GetComponentToWorld=function()error('Stale rendered sword must not drive sampled collision')end
r.trace_batch=function(_,segments)
 queries=queries+1;assert(#segments>=1 and #segments<=64)
 local result={};for _,segment in ipairs(segments)do
  assert(segment.radius>=24 and segment.radius<=48)
  result[#result+1]={{actor=target,native_snapshot=true}}
 end;return result
end
r.damage=function(_,_,_,key)keys[key]=true end
local count=0
for name,clip in pairs(r.state.profile.clips)do
 r.state.clip=name
 for index,hit in ipairs(clip.hits)do
  local first=hit.start;local finish=math.min(hit.finish,clip.duration)
  while first<finish-1e-8 do
   keys={};queries=0
   r:hit_window({hit=hit,from_time=first,time=math.min(first+.1,finish),serial=17,index=index,light_index=1})
   assert(queries==1,'Substeps must share one native request')
   local n=0;for key in pairs(keys)do assert(key=='17:'..index);n=n+1 end;assert(n==1)
   first=first+.1;count=count+1
  end
 end
end
assert(count>20 and (r.hit_sweep_budget_exhausted or 0)==0)
''',
    'mixed_hidden_display_objects_only_pass_actors_to_native_trace_ignore': r'''
local weapon=obj({actor=true,GetFullName=function()return 'WeaponActor Test.OwnWeapon'end})
local scabbard=obj({GetFullName=function()return 'SkeletalMeshComponent Test.Scabbard'end})
query_ignore_objects['Test.OwnWeapon']=weapon;query_ignore_objects['Test.Scabbard']=scabbard
r.hidden={{actor=weapon,kind='actor'},{actor=scabbard,kind='component'}}
r:trace({X=0,Y=0,Z=0},{X=10,Y=0,Z=0},2,scabbard,{weapon,scabbard,r.pawn})
local ignored=query_calls[#query_calls].ignore
assert(#ignored==2 and ignored[1]=='Test.Player'and ignored[2]=='Test.OwnWeapon')
''',
    'bomb_projectile_sweep_keeps_actor_only_ignore_with_hidden_scabbard': r'''
local weapon=obj({actor=true,GetFullName=function()return 'WeaponActor Test.OwnWeapon'end})
local scabbard=obj({GetFullName=function()return 'SkeletalMeshComponent Test.Scabbard'end})
local bomb=obj({actor=true,GetFullName=function()return 'Actor Test.Bomb'end,
 K2_SetActorLocation=function(self,value)self.position=value end,K2_DestroyActor=function()error('No ground contact supplied')end})
query_ignore_objects['Test.OwnWeapon']=weapon;query_ignore_objects['Test.Scabbard']=scabbard;query_ignore_objects['Test.Bomb']=bomb
r.hidden={{actor=weapon,kind='actor'},{actor=scabbard,kind='component'}}
r.projectiles={{actor=bomb,position={X=0,Y=0,Z=100},velocity={X=0,Y=0,Z=-180},age=0,key='bomb'}}
r:projectile_step(1/60)
assert(bomb.position.Z<100 and #r.projectiles==1)
local ignored=query_calls[#query_calls].ignore;local included={}
for _,path in ipairs(ignored)do included[path]=true end
assert(#ignored==3 and included['Test.Player']and included['Test.OwnWeapon']and included['Test.Bomb'])
assert(not included['Test.Scabbard'])
''',
    'art_and_bomb_armor_keep_hp_damage_without_cancelling_the_action': r'''
r.flame=function()return obj()end
test_input={art_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_EmberStart' and r.action_protection_active)
r.pawn.AttributeSetBase.Health.CurrentValue=75;test_input={};r:tick(.016)
assert(r.state.clip=='RKSS_EmberStart' and not r.native_reaction and r.health==75)
r.state:cancel();r:restore_animation()
assert(not r.action_protection_active)
r.attach=function()return obj({K2_DestroyComponent=function()end})end
test_input={guard=true,triangle_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_RopeBomb' and r.action_protection_active)
r.pawn.AttributeSetBase.Health.CurrentValue=50;test_input={};r:tick(.016)
assert(r.state.clip=='RKSS_RopeBomb' and not r.native_reaction and r.health==50)
r:release_combat_pose();assert(not r.action_protection_active)
''',
    'continuous_burn_damage_does_not_interrupt_complete_light_heavy_or_art_sequences': r'''
r.flame=function()return obj()end
local contacts={}
r.hit_window=function(self,event)contacts[self.state.clip]=true end
local function burn_tick(input)
 local health=r.pawn.AttributeSetBase.Health.CurrentValue-.01
 r.pawn.AttributeSetBase.Health.CurrentValue=health;test_input=input or {};r:tick(1/60)
 assert(r.enabled and not r.native_reaction and r.health==health)
end
local actions={
 {input={attack_pressed=true},clip='RKSS_Light1',contacts={'RKSS_Light1'}},
 {input={triangle_pressed=true},clip='RKSS_Heavy1Release',contacts={'RKSS_Heavy1Release'}},
 {stage=2,clip='RKSS_Heavy2Release',contacts={'RKSS_Heavy2Release'}},
 {input={art_pressed=true},clip='RKSS_EmberStart',contacts={'RKSS_Ember','RKSS_EmberFollow1','RKSS_EmberFollow2'}},
 {input={guard=true,circle_pressed=true},clip='RKSS_EmberStart',contacts={'RKSS_EmberHeavy'}},
}
for _,action in ipairs(actions)do
 r.state:cancel();r:restore_animation()
 if action.stage then r.state:start_heavy(action.stage,true);r:play(r.state.clip,false)
 else burn_tick(action.input)end
 assert(r.state.clip==action.clip)
 local completed=false
 for frame=1,900 do
  burn_tick()
  if not r.state.clip then completed=true;break end
 end
 assert(completed and not r.action_protection_active)
 for _,name in ipairs(action.contacts)do assert(contacts[name],name..' never reached its contact window')end
end
assert(r.pawn.AttributeSetBase.Health.CurrentValue<100)
''',
    'burning_can_queue_light_to_heavy_and_then_full_art_without_pose_reset': r'''
r.flame=function()return obj()end;r.hit_window=function()end
local seen={};local queued_heavy=false;local queued_art=false;local completed=false
test_input={attack_pressed=true};r:tick(1/60)
for frame=1,1000 do
 local name=r.state.clip;seen[name or 'idle']=true
 test_input={}
 if name=='RKSS_Light1'and not queued_heavy then test_input={triangle_pressed=true};queued_heavy=true
 elseif name=='RKSS_Heavy1Release'and not queued_art then test_input={art_pressed=true};queued_art=true end
 r.pawn.AttributeSetBase.Health.CurrentValue=r.pawn.AttributeSetBase.Health.CurrentValue-.01
 r:tick(1/60);assert(not r.native_reaction)
 if seen.RKSS_EmberFollow2 and not r.state.clip then completed=true;break end
end
assert(completed and seen.RKSS_Heavy1Release and seen.RKSS_Ember and seen.RKSS_EmberFollow1)
''',
    'heavy_charge_armor_covers_windup_only_and_keeps_real_hp_damage': r'''
local own=obj({GetOwner=function()return r.pawn end})
for stage=1,2 do
 for _,held in ipairs({false,true})do
 r.state:start_heavy(stage,true);r:play(r.state.clip,false)
 assert(r.action_protection_active and r:is_protected_action())
 local before=count('protection');local frames=0;local health=r.pawn.AttributeSetBase.Health.CurrentValue
 while r.state.time<r.state.profile.heavy.windup.seconds do
  hook_callbacks[1]({get=function()return own end})
  assert(r.playing and not r.native_reaction)
  r.pawn.AttributeSetBase.Health.CurrentValue=r.pawn.AttributeSetBase.Health.CurrentValue-.01
  test_input={triangle=held};r:tick(1/60);frames=frames+1
  assert(frames<300,"Heavy windup failed to finish")
  assert(r.action_protection_active==(r.state.time<r.state.profile.heavy.windup.seconds))
  assert(r.playing and not r.native_reaction)
 end
 local windup=r.state.profile.heavy.windup
 local expected=math.ceil(windup.seconds/(held and windup.held_rate or windup.tap_rate)*60-1e-6)
 -- A source-clock sum can land infinitesimally below the boundary for one frame.
 assert(frames>=expected and frames<=expected+1 and count('protection')>=before+3,
  ('stage=%d held=%s frames=%d expected=%d renewals=%d'):format(stage,tostring(held),frames,expected,count('protection')-before))
 assert(math.abs(r.pawn.AttributeSetBase.Health.CurrentValue-(health-.01*frames))<1e-6)
 hook_callbacks[1]({get=function()return own end})
 assert(r.native_reaction and not r.playing)
 r.native_reaction=nil;r.state:cancel();r:restore_animation()
 end
end
assert(r.pawn.AttributeSetBase.Health.CurrentValue<100)
r.state:start_heavy(1,false);r:play(r.state.clip,false)
assert(not r.action_protection_active) -- native switch-entry release is not a charge
''',
    'legacy_heavy_charge_armor_ends_at_authored_release_boundary': r'''
for _,stage in ipairs(r.state.profile.heavy.stages)do
 r.state:enter(stage.charge);r:play(stage.charge,false)
 assert(r.action_protection_active)
 r.state.time=stage.release_close-.001;test_input={};r:tick(1/60)
 assert(not r.action_protection_active and r.state.clip==stage.charge)
 r:release_combat_pose();assert(not r.action_protection_active)
end
''',
    'native_montage_and_death_still_override_heavy_charge_armor': r'''
r.state:start_heavy(1,true);r:play(r.state.clip,false)
assert(r.action_protection_active)
local dodge=obj()
hook_callbacks[2]({get=function()return native end},{get=function()return dodge end})
assert(r.native_reaction and not r.playing and not r.action_protection_active)
r.native_reaction=nil;r.state:start_heavy(2,true);r:play(r.state.clip,false)
assert(r.action_protection_active)
r.pawn.AttributeSetBase.Health.CurrentValue=0;test_input={};r:tick(1/60)
assert(not r.enabled and not r.playing and not r.action_protection_active and not r.move_lock)
''',
    'native_execution_and_dodge_tags_override_heavy_charge_armor': r'''
local active
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return tag.TagName:ToString()==active end})
for _,tag in ipairs({'Ability.Action.Execution','Ability.Executed','Ability.Action.Hun.Dash'})do
 r.native_reaction=nil;r.execution_active=false;r.state:start_heavy(1,true);r:play(r.state.clip,false)
 assert(r.action_protection_active)
 active=tag;test_input={attack_pressed=true};r:tick(1/60)
 assert(r.native_reaction and not r.playing and not r.state.clip and not r.action_protection_active)
 active=nil;r:release_combat_pose()
end
''',
    'plunge_preserves_native_fall_and_waits_for_actual_ground_before_recovery': r'''
r.pawn.CharacterMovement.StopMovementImmediately=function()record('stop_move',true)end
falling=true;r:tick(.016)
test_input={attack_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_PlungeStart' and not r.native_airborne)
test_input={}
for i=1,160 do r:tick(1/60)end
assert(r.state.clip=='RKSS_PlungeLoop' and r.animation_blend.loop==true)
assert(count('stop_move')==0 and count('displacement')==0)
falling=false;r:tick(.016)
assert(r.state.clip=='RKSS_PlungeLand')
for i=1,90 do r:tick(1/60)end
assert(not r.state.clip and r.idle_playing and not r.pc.move_lock)
''',
    'plunge_landing_survives_native_landing_tag_and_stale_original_jump_tag': r'''
for _,stale_jump in ipairs({false,true})do
 for _,landing_tag in ipairs({false,true})do
  r:release_combat_pose();falling=true;test_input={attack_pressed=true}
  r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
   local name=tag.TagName:ToString()
   return (name=='Ability.Action.Hun.Jump'and stale_jump)
    or(name=='CharacterState.Landing'and landing_tag)
  end})
  r:tick(1/120);test_input={};r:tick(1/120)
  assert(r.state.clip=='RKSS_PlungeStart')
  falling=false;r:tick(1/120)
  assert(r.state.clip=='RKSS_PlungeLand')
  local planted=r.animation_blend.montage;local land_contacts=0
  r.hit_window=function(_,event)
   assert(event.plunge_phase=='land');land_contacts=land_contacts+1
  end
  for _=1,300 do
   r:tick(1/120)
   if not r.state.clip then break end
   assert(r.state.clip=='RKSS_PlungeLand'and not r.native_airborne and planted.active,
    'Original native jump/landing tag interrupted the plunge impact')
  end
  assert(not r.state.clip and land_contacts>0,'Landing contact or normal recovery was lost')
  if not landing_tag then
   -- The old Jump can outlive the custom recovery for another frame. It must
   -- not restart native-air ownership while the character is on the ground.
   test_input={attack_pressed=true};r:tick(1/120)
   assert(r.state.clip=='RKSS_Light1'and not r.native_airborne,
    'Stale original Jump tag blocked the first attack after plunge recovery')
  end
 end
end
''',
    'jump_from_plunge_recovery_releases_planted_pose_before_native_takeoff': r'''
for _,age in ipairs({0,.15,.5})do
 for _,physical_takeoff in ipairs({false,true})do
  falling=false;jumping=false
  r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
   return tag.TagName:ToString()=='Ability.Action.Hun.Jump'and jumping==true
  end})
  test_input={};r:tick(0) -- Observe the old Jump tag off before the fresh edge.
  assert(r.state:enter('RKSS_PlungeStart',true))
  assert(r.state:enter('RKSS_PlungeLand',true));assert(r:play(r.state.clip,false))
  r.state.time=age;r.state.pending='light';r.state.next_light_pending=true;r.state.guard_buffer=true
  local planted=r.animation_blend.montage;local contacts=count('native_hit')
  jumping=true;falling=physical_takeoff;test_input={attack_pressed=true}
  r:tick(1/120)
  assert(r.native_airborne and not r.state.clip and not r.state.plunge_serial)
  assert(not r.state.pending and not r.state.next_light_pending and not r.state.guard_buffer)
  assert(not r.playing and not r.idle_playing and not r.mesh.pp and not r.pc.move_lock)
  assert(not planted.active and count('native_hit')==contacts,'Jump retained a plunge contact')
  -- Native takeoff owns both the pose and movement until a fresh attack edge.
  test_input={};falling=true;jumping=false;r:tick(1/120)
  assert(r.native_airborne and not r.state.clip and count('native_hit')==contacts)
  test_input={attack_pressed=true};r:tick(1/120)
  assert(r.state.clip=='RKSS_PlungeStart'and not r.native_airborne)
  r:release_combat_pose();falling=false;jumping=false
 end
end
''',
    'plunge_recovery_ignores_descending_ground_seam_but_yields_to_rising_takeoff': r'''
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 local name=tag.TagName:ToString()
 return name=='Ability.Action.Hun.Jump'or name=='CharacterState.Landing'
end})
assert(r.state:enter('RKSS_PlungeStart',true));falling=true;test_input={};r:tick(0)
assert(r.state:enter('RKSS_PlungeLand',true));assert(r:play(r.state.clip,false))
for _,z in ipairs({0,-120})do
 r.pawn.velocity={X=0,Y=0,Z=z};r:tick(1/120)
 assert(r.state.clip=='RKSS_PlungeLand'and not r.native_airborne and r.playing,
  'A descending ground seam was mistaken for a fresh jump')
end
r.pawn.velocity={X=0,Y=0,Z=120};r:tick(1/120)
assert(not r.state.clip and not r.playing and r.native_airborne and not r.pc.move_lock,
 'A real upward takeoff retained the planted-sword recovery')
''',
    'native_jump_tag_does_not_interrupt_the_descending_plunge': r'''
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return tag.TagName:ToString()=='Ability.Action.Hun.Jump'
end})
falling=true;test_input={attack_pressed=true};r:tick(1/120)
assert(r.state.clip=='RKSS_PlungeStart'and not r.native_airborne)
test_input={}
for _=1,200 do r:tick(1/120)end
assert(r.state.clip=='RKSS_PlungeLoop'and not r.native_airborne and r.playing)
''',
    'full_ember_keeps_shield_on_back_until_fifth_contact_then_restores_hand': r'''
local contacts={}
r.hit_window=function(_,event)contacts[event.serial..':'..event.index]=event.hit.attack_id end
r.flame=function()return obj()end
test_input={art_pressed=true};r:tick(.016)
assert(r.shield_stowed)
local plays=count('shield_bone')
test_input={}
for i=1,400 do
 r:tick(1/60)
 if not r.state.clip then break end
 assert(r.shield_stowed)
end
local count_hits=0;for _ in pairs(contacts)do count_hits=count_hits+1 end
assert(count_hits==5 and not r.shield_stowed and count('shield_bone')==plays+1)
''',
    'art_interrupt_returns_shield_to_left_hand': r'''
r:play('RKSS_EmberStart',false);assert(r.shield_stowed)
r:begin_native_reaction();assert(not r.shield_stowed and not r.playing)
''',
    'light_damage_uses_burst_index_even_when_guard_restarts_first_source_clip': r'''
r.state.clip='RKSS_Light1'
r.trace=function()return {{actor=obj(),native_snapshot=true}}end
local damage
r.damage=function(_,_,_,_,physical,fire,kind,poise,anger,multiplier)damage={physical,fire,poise,anger,multiplier}end
local hit=r.state.profile.clips.RKSS_Light1.hits[1]
for index=1,5 do
 r:hit_window({hit=hit,time=hit.start,serial=index,index=1,light_index=index})
 if index==1 then assert(damage[1]==363 and damage[2]==34.5 and damage[3]==900)
 else assert(damage[1]==242 and damage[2]==23 and damage[3]==100)end
 assert(damage[4]==4.59 and damage[5]==.05)
end
''',
    'native_execution_tags_own_pose_and_clear_queued_attacks_until_completion': r'''
local executing=true
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return executing and tag.TagName:ToString()=='Ability.Action.Execution'
end})
r:play('RKSS_Light1',false);r.state.clip='RKSS_Light1'
test_input={attack_pressed=true};r:tick(.016)
assert(r.execution_active and r.shield_stowed and not r.state.clip and not r.state.pending)
test_input={};r:tick(.016)
assert(r.execution_active and not r.playing)
executing=false;r:tick(.016)
assert(not r.execution_active and not r.shield_stowed)
''',
    'eligible_triangle_uses_original_execution_ability_with_native_target_checks': r'''
r.execution_component=obj({CanPerformExecution=function(_,channel,target)
 error('Target and out-argument handling belong to the original ability')
end,PerformExecution=function()error('Original actor-state wrapper must handle execution')end})
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function(_,ability,remote)assert(ability:IsValid() and remote);record('native_execution',true);return true end})
test_input={triangle_pressed=true};r:tick(.016)
assert(count('native_execution')==1 and r.execution_active and not r.state.clip and r.shield_stowed)
''',
    'triangle_remains_heavy_when_no_native_execution_target_is_available': r'''
r.execution_component=obj({CanPerformExecution=function(_,_,target)assert(type(target)=='table');return false end})
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function()return false end})
test_input={triangle_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_Heavy1Release' and not r.execution_active)
''',
    'active_native_execution_returns_followup_input_to_original_buffer_without_replaying_pose': r'''
local execution_montage=obj()
r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return tag.TagName:ToString()=='Ability.Action.Execution'
end,TryActivateAbilityByClass=function(_,ability,remote)
 assert(ability.path=='/PBZCombatAsset/Prototypes/Abilities/GA_PerformExecution.GA_PerformExecution_C' and remote)
 record('native_execution',true);return true
end})
r:update_idle(false);native.active=execution_montage
local before=count('play')
test_input={triangle=true,triangle_pressed=true};r:tick(.016)
assert(count('native_execution')==0 and r.native_input_handoff,'Original input buffer must own follow-up edges')
assert(r.execution_active and r.native_reaction and not r.playing and not r.state.clip and not r.state.pending)
assert(native.active==execution_montage and count('play')==before)
for i=1,20 do test_input={triangle=true};r:tick(.016)end
assert(count('native_execution')==0,'Lua duplicated the original follow-up request')
test_input={};r:tick(.016)
test_input={triangle=true,triangle_pressed=true};r:tick(.016)
assert(count('native_execution')==0 and r.native_input_handoff and native.active==execution_montage and count('play')==before)
''',
    'rejected_execution_followup_keeps_native_pose_and_never_falls_through_to_heavy': r'''
local execution_montage=obj()
r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return tag.TagName:ToString()=='Ability.Action.Execution'
end,TryActivateAbilityByClass=function()record('native_execution_rejected',true);return false end})
r:update_idle(false);native.active=execution_montage
local before=count('play')
for i=1,2 do
 test_input={triangle=true,triangle_pressed=true};r:tick(.016)
 assert(count('native_execution_rejected')==0 and r.native_input_handoff,'Native buffer owns rejection and window validation')
 assert(r.execution_active and r.native_reaction and not r.playing and not r.state.clip and not r.state.pending)
 assert(native.active==execution_montage and count('play')==before)
 test_input={};r:tick(.016)
end
''',
    'active_execution_followup_defers_airborne_and_nonwalking_validation_to_native': r'''
local mode={};local execution_montage=obj()
r.execution_component=obj()
r.pawn.CharacterMovement.IsFalling=function()return mode.falling==true end
r.pawn.CharacterMovement.IsMovingOnGround=function()return false end
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 local name=tag.TagName:ToString()
 return name=='Ability.Action.Execution' or (mode.jump and name=='Ability.Action.Hun.Jump') or false
end,TryActivateAbilityByClass=function(_,ability,remote)
 assert(ability.path=='/PBZCombatAsset/Prototypes/Abilities/GA_PerformExecution.GA_PerformExecution_C' and remote)
 record('native_execution_air',true);return false
end})
for i,value in ipairs({{falling=true},{jump=true}})do
 mode=value;r:release_combat_pose();r.native_reaction=nil;r.execution_active=false;r.native_airborne=false
 native.active=execution_montage
 test_input={triangle=true,triangle_pressed=true};r:tick(.016)
 assert(count('native_execution_air')==0 and r.native_input_handoff,'Airborne execution must retain original input routing')
 assert(r.execution_active and r.native_reaction and not r.playing and not r.state.clip and not r.state.pending)
 assert(native.active==execution_montage)
 test_input={triangle=true};r:tick(.016)
 assert(count('native_execution_air')==0,'Lua repeated an airborne native input')
end
''',
    'ordinary_airborne_triangle_remains_plunge_without_native_execution_request': r'''
falling=true;r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function()return false end,
 TryActivateAbilityByClass=function()error('Ordinary airborne input was forwarded as an execution')end})
test_input={triangle=true,triangle_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_PlungeStart' and not r.execution_active)
''',
    'execution_followup_never_forwards_while_hit_dodging_or_being_executed': r'''
local tags={}
r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)return tags[tag.TagName:ToString()]==true end,
 TryActivateAbilityByClass=function()error('Blocked native reaction forwarded an execution input')end})
for _,active in ipairs({{},
 {['Ability.Executed']=true},
 {['Ability.Action.Execution']=true,['Ability.Executed']=true},
 {['Ability.Action.Execution']=true,['Ability.Action.Hun.Dash']=true}})do
 r:release_combat_pose();r.native_reaction=nil;r.execution_active=false;tags=active
 local reaction_montage=obj();native.active=reaction_montage
 test_input={triangle=true,triangle_pressed=true};r:tick(.016)
 assert(r.native_reaction and not r.playing and not r.state.clip and not r.state.pending)
 assert(native.active==reaction_montage)
end
''',
    'execution_tag_end_does_not_forward_during_native_montage_tail': r'''
local executing=true;local execution_montage=obj()
r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return executing and tag.TagName:ToString()=='Ability.Action.Execution'
end,TryActivateAbilityByClass=function()error('Execution tail was mistaken for a live follow-up window')end})
native.active=execution_montage;test_input={};r:tick(.016)
assert(r.execution_active)
executing=false;test_input={triangle=true,triangle_pressed=true};r:tick(.016)
assert(r.execution_active and r.native_reaction and not r.playing and not r.state.clip)
assert(native.active==execution_montage)
''',
    'guard_triangle_stays_bomb_outside_execution_and_does_not_forward_inside_execution': r'''
local executing=false
r.attach=function()return obj({K2_DestroyComponent=function()end})end
r.execution_component=obj()
r.ability_system=obj({HasMatchingGameplayTag=function(_,tag)
 return executing and tag.TagName:ToString()=='Ability.Action.Execution'
end,TryActivateAbilityByClass=function()error('Guard plus triangle forwarded an execution input')end})
test_input={guard=true,triangle=true,triangle_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_RopeBomb' and not r.execution_active)
executing=true;local execution_montage=obj();native.active=execution_montage
test_input={guard=true,triangle=true,triangle_pressed=true};r:tick(.016)
assert(r.execution_active and not r.playing and not r.state.clip and native.active==execution_montage)
''',
    'trace_uses_owned_json_without_remote_out_arrays': r'''
local hit={target='',point={X=1,Y=2,Z=3},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}
query_hits={hit}
local hits=r:trace({X=0,Y=0,Z=0},{X=10,Y=0,Z=0},2)
assert(#query_calls==1 and query_calls[1].phase=='trace' and query_calls[1].pawn=='Test.Player')
assert(query_calls[1].ignore[1]=='Test.Player' and query_calls[1].radius==2)
assert(#hits==1 and hits[1].native_snapshot and not hits[1].actor and hits[1].blocking and not hits[1].start_penetrating)
hit.point.X=99;assert(hits[1].ImpactPoint.X==1)
''',
    'native_query_error_does_not_return_partial_hits': r'''
query_failure=true
assert(not pcall(r.trace,r,{X=0,Y=0,Z=0},{X=10,Y=0,Z=0},2))
assert(#query_calls==1)
''',
    'ready_inventory_rechecks_lifetime_without_replaying_animation': r'''
r.inventory_ready=true
r.lifetime={check=function()record('lifetime_check',true);return {strong_references_verified=true}end}
r.combat_assets={check=function()record('asset_lifetime_check',true)end,retain=function(_,_,asset)return asset end}
r:play('RKSS_Light1',false)
local before=count('play');r:prepare_inventory();r:prepare_inventory()
assert(count('lifetime_check')==2 and count('asset_lifetime_check')==2 and count('play')==before and r.playing)
''',
    'ready_inventory_propagates_stale_lifetime_failure_to_caller': r'''
r.inventory_ready=true
r.lifetime={check=function()error('mock stale lifetime holder')end}
local ok,why=pcall(r.prepare_inventory,r)
assert(not ok and tostring(why):find('mock stale lifetime holder',1,true))
assert(count('play')==0)
''',
    'action_has_one_manual_clock_and_idle_crossfades': r'''
r:play('RKSS_Light1',false)
local attack=r.animation_blend.montage
assert(attack.paused and attack.position==0 and r.mesh.pp)
r.state.clip='RKSS_Light1';r.state.time=.4;r:root_motion()
assert(attack.paused and attack.position==.4)
r.state.clip=nil;r.idle_playing=false;r:update_idle(false)
local idle=r.animation_blend.montage
assert(idle.paused and r.idle_playing and r.mesh.pp and idle.blend_in==.28)
assert(not attack.active and attack.position==.4)
local fade
for _,call in ipairs(calls)do if call.name=='stop'then fade=call.value end end
assert(fade.montage==attack and fade.seconds==.28)
r:update_idle(false,.1);assert(idle.position==.1)
r:update_idle(true);assert(not r.playing and r.mesh.pp)
r.animation_blend:update(.17);assert(not r.mesh.pp)
''',
    'run_brakes_in_native_graph_before_longer_standing_blend': r'''
r:update_idle(false)
r:update_idle(true,.016)
local plays=count('play')
r.pawn.velocity={X=100,Y=100,Z=0}
r:update_idle(false,.25)
assert(not r.playing and count('play')==plays)
r.pawn.velocity={X=0,Y=0,Z=0}
r:update_idle(false,.12)
assert(not r.playing)
r:update_idle(true,.016)
r:update_idle(false,.12)
assert(not r.playing)
r:update_idle(false,.09)
assert(r.idle_playing and r.animation_blend.montage.blend_in==.32 and not r.pc.move_lock)
''',
    'attack_can_interrupt_stop_and_standing_blend': r'''
r:update_idle(true,.016)
r:update_idle(false,.05)
assert(not r.playing)
test_input={attack_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_Light1' and r.animation_blend.montage.blend_in==.09)
r.state.clip=nil;r:update_idle(false,.016)
assert(r.idle_playing and r.animation_blend.montage.blend_in==.28)
test_input={triangle_pressed=true};r:tick(.016)
assert(r.state.clip=='RKSS_Heavy1Release' and r.animation_blend.montage.blend_in==.09)
''',
    'action_recovery_into_movement_fades_without_relocking_input': r'''
r.hit_window=function()end
test_input={attack_pressed=true};r:tick(.016)
local attack=r.animation_blend.montage
test_input={move=true};r:tick(.25);r:tick(.25);r:tick(.11)
assert(r.state.clip=='RKSS_Light1')
r:tick(.016)
assert(not r.state.clip and not r.playing and not r.pc.move_lock)
local fade=r.animation_blend.retiring[1]
assert(fade.montage==attack and fade.remaining==.24)
''',
    'physical_fall_stops_idle_and_defers_untagged_landing': r'''
r:update_idle(false)
assert(r.idle_playing and r.mesh.pp)
falling=true;r:tick(.016)
assert(r.native_airborne and not r.idle_playing and not r.mesh.pp)
test_input={};r:tick(.016)
assert(r.state.clip==nil and r.state.pending==nil)
test_input={}
falling=false;r:tick(.016)
r:tick(.1);r:tick(.1)
assert(not r.idle_playing and not r.native_reaction)
r:tick(.06)
assert(r.idle_playing and not r.state.clip)
''',
    'guard_and_bomb_keep_original_movement_and_skip_manual_root_motion': r'''
r.pawn.CharacterMovement.MaxWalkSpeed=500
r.pawn.CharacterMovement.StopMovementImmediately=function()record('stop_move',true)end
assert(r:play('RKSS_Light1',false) and r.pc.move_lock)
r.attach=function()return obj({K2_DestroyComponent=function()end})end
for _,name in ipairs({'RKSS_GuardStart','RKSS_GuardLoop','RKSS_GuardEnd','RKSS_RopeBomb'})do
 r.state.clip=name;r.state.time=.2
 assert(r:play(name,name=='RKSS_GuardLoop') and not r.pc.move_lock)
 local expected=name=='RKSS_RopeBomb' and 'RightArmOverride' or 'LeftArmOverride'
 assert(r.animation_blend.montage.slot==expected and r:root_motion({aim_yaw=90},.2))
 assert(not r.move_lock and count('displacement')==0 and count('turn')==0)
end
assert(count('stop_move')==1 and r.pawn.CharacterMovement.MaxWalkSpeed==500)
''',
    'bomb_from_right_hand_lands_behind_stationary_and_moving_hero': r'''
local center={X=600,Y=-200,Z=98}
r.pawn.K2_GetActorLocation=function()return center end
r.pawn.CapsuleComponent=obj({GetScaledCapsuleHalfHeight=function()return 98 end})
local origin,forward,spawned,impact
r.pawn.GetActorForwardVector=function()return forward end
r.mesh.GetSocketLocation=function(_,socket)assert(socket:ToString()=='hand_r');return origin end
local mesh=obj({SetStaticMesh=function()end,SetCollisionEnabled=function(_,mode)assert(mode==0)end})
r.world.SpawnActor=function(_,_,position)
    spawned=position
    return obj({AddComponentByClass=function()return mesh end,
        K2_SetActorLocation=function()end,K2_DestroyActor=function()end})
end
r.audio.play=function()end
r.explode=function(_,point)impact=point end
r.trace=function(_,start,finish,radius)
    if finish.Z>radius then return {} end
    local alpha=(start.Z-radius)/(start.Z-finish.Z)
    local point={X=start.X+(finish.X-start.X)*alpha,Y=start.Y+(finish.Y-start.Y)*alpha,Z=0}
    return {{blocking=true,start_penetrating=false,ImpactPoint=point,ImpactNormal={X=0,Y=0,Z=1}}}
end
for _,case in ipairs({{1,0,0,0,75},{0,1,120,450,92},{0,1,-90,-360,105}})do
    local x,y,vx,vy,z=table.unpack(case)
    forward={X=x,Y=y,Z=0}
    r.pawn.velocity={X=vx,Y=vy,Z=0}
    origin={X=center.X+32*x-38*y,Y=center.Y+32*y+38*x,Z=z}
    impact=nil;r:throw_bomb(1)
    assert(spawned.X==origin.X and spawned.Y==origin.Y and spawned.Z==origin.Z)
    local elapsed=0
    for _=1,36 do
        elapsed=elapsed+1/60;r:projectile_step(1/60)
        if impact then break end
    end
    assert(impact and #r.projectiles==0)
    local dx,dy=impact.X-center.X-vx*elapsed,impact.Y-center.Y-vy*elapsed
    local rear=-(dx*x+dy*y)
    assert(rear>=35 and rear<=65 and math.abs(-dx*y+dy*x)<10 and impact.Z==0)
end
''',
    'light_heavy_and_full_arts_steer_relative_to_camera_and_rotate_root_deltas': r'''
local motion=dofile(script_dir..'CombatMotion.lua')
assert(motion.aim_yaw(.02,0,65)==nil and motion.aim_yaw(1,0,45)==135)
assert(motion.approach_yaw(170,-170,1/60)==182)
local function displacement()
 for i=#calls,1,-1 do if calls[i].name=='displacement'then return calls[i].value end end
end
for _,name in ipairs({'RKSS_Light1','RKSS_Heavy1Release','RKSS_Ember',
    'RKSS_EmberFollow1','RKSS_EmberFollow2','RKSS_EmberHeavy'})do
 r.pawn.yaw=0;r.state.clip=name;r.state.time=.4
 assert(r:play(name,false) and r:root_motion({},.15))
 local baseline=displacement()
 assert(r:play(name,false) and r:root_motion({aim_yaw=90},.15) and r.pawn.yaw==90)
 local steered=displacement()
 assert(math.abs(baseline.X)+math.abs(baseline.Y)>.01)
 assert(math.abs(steered.X+baseline.Y)<.00001 and math.abs(steered.Y-baseline.X)<.00001)
end
assert(motion.can_steer('RKSS_EmberStart'))
assert(not motion.can_steer('RKSS_PlungeLoop') and not motion.can_steer('RKSS_RopeBomb'))
''',
    'postprocess_restores_exact_original_false_and_true': r'''
for _,original in ipairs({false,true})do
 r.mesh.pp=original;r:custom_animation(test_sequence,false,2)
 r:custom_animation(test_sequence,true,2,nil,.28) -- clip transitions must not overwrite cache
 r:restore_animation();assert(r.mesh.pp==original and r.animation_blend.postprocess_previous==nil)
end
''',
    'failed_play_is_owned_and_can_be_cleaned': r'''
fail_play=true;local ok=pcall(r.custom_animation,r,test_sequence,false,true,2)
assert(not ok and not r.playing and not r.mesh.pp)
fail_play=false;r:disable('test cleanup')
assert(not r.mesh.pp and not r.playing and r.animation_blend.postprocess_previous==nil)
''',
    'failed_native_restore_still_restores_postprocess_and_movement': r'''
r:custom_animation(test_sequence,false,2);r:lock_movement(true)
fail_restore=true;assert(not pcall(r.restore_animation,r))
assert(not r.playing and not r.mesh.pp and not r.move_lock)
''',
    'native_pre_hook_restores_before_original_and_filters_other_owners': r'''
r:play('RKSS_Light1',false)
local other=obj({GetOwner=function()return obj()end})
hook_callbacks[1]({get=function()return other end})
assert(r.playing and not r.native_reaction)
local own=obj({GetOwner=function()return r.pawn end})
hook_callbacks[1]({get=function()return own end})
assert(not r.playing and r.native_reaction and r.state.clip==nil)
assert(count('stop')==1 and not r.mesh.pp and not r.move_lock)
''',
    'native_montage_pre_hook_yields_before_dodge_but_ignores_owned_and_other_actors': r'''
r:update_idle(false)
assert(r.playing and not r.native_reaction)
r.state:enter('RKSS_Light1');r:play('RKSS_Light1',false)
assert(r.playing and not r.native_reaction)
local dodge=obj()
hook_callbacks[2]({get=function()return obj()end},{get=function()return dodge end})
assert(r.playing and not r.native_reaction)
hook_callbacks[2]({get=function()return native end},{get=function()return dodge end})
assert(not r.playing and not r.mesh.pp and not r.move_lock and r.native_reaction)
native.active=dodge;r:tick(1/60)
assert(r.native_reaction.saw_montage and native.active==dodge)
native.active=nil;r:tick(1/60)
assert(not r.native_input_handoff and not r.state.clip)
r:tick(1/60)
assert(r.idle_playing and not r.native_reaction)
''',
    'native_direct_montage_cancels_pending_hit_and_hands_back_to_dodge': r'''
r.state:enter('RKSS_Light1');r:play('RKSS_Light1',false);r.state.time=.465
local dodge=obj();native.active=dodge
r.hit_window=function()error('Cancelled attack emitted a hit')end
r:tick(1/60)
assert(native.active==dodge and r.native_reaction.saw_montage and r.state.clip==nil)
assert(not r.playing and not r.mesh.pp and not r.move_lock)
''',
    'real_hit_hook_with_health_loss_does_not_overwrite_native_with_idle_same_tick': r'''
r:play('RKSS_Light1',false)
r.state:enter('RKSS_Light1');r.pawn.AttributeSetBase.Health.CurrentValue=90
local own=obj({GetOwner=function()return r.pawn end})
hook_callbacks[1]({get=function()return own end})
local before=count('play');r:tick(1/60)
assert(r.native_reaction and not r.playing and count('play')==before)
assert(r.state.clip==nil and not r.mesh.pp)
''',
    'hit_during_custom_idle_also_hands_back_to_native': r'''
r:update_idle(false);r.pawn.AttributeSetBase.Health.CurrentValue=90
local own=obj({GetOwner=function()return r.pawn end})
hook_callbacks[1]({get=function()return own end})
local before=count('play');r:tick(1/60)
assert(r.native_reaction and not r.idle_playing and count('play')==before)
''',
    'montage_holds_reaction_through_end_then_allows_idle': r'''
r:update_idle(false);r:begin_native_reaction();native.active=obj()
for i=1,4 do r:tick(1/60);assert(r.native_reaction and not r.playing)end
native.active=nil;r:tick(1/60)
assert(not r.native_input_handoff and not r.state.clip)
r:tick(1/60)
assert(not r.native_reaction and r.idle_playing and r.animation_blend.montage.paused)
''',
    'no_montage_requires_release_and_fresh_command_with_no_timeout': r'''
r:update_idle(false);r:begin_native_reaction()
for i=1,600 do
 test_input={attack=true,attack_pressed=i==1};r:tick(1/60)
 assert(r.native_reaction and not r.playing)
end
test_input={move=true};r:tick(1/60);assert(r.native_reaction and not r.move_lock)
test_input={attack=true,attack_pressed=true};r:tick(1/60)
assert(not r.native_reaction and r.state.clip=='RKSS_Light1' and r.animation_blend.montage.paused)
''',
    'first_sample_cannot_end_reaction_before_native_function_runs': r'''
r:begin_native_reaction()
assert(r:native_reaction_busy({attack_pressed=true}))
assert(r:native_reaction_busy({attack=true}))
''',
    'unavailable_native_instance_is_not_treated_as_montage_completion': r'''
r:begin_native_reaction();native.active=obj()
assert(r:native_reaction_busy({}))
r.mesh.GetAnimInstance=function()return nil end
assert(r:native_reaction_busy({}) and r.native_reaction)
r.mesh.GetAnimInstance=function()return native end;native.active=nil
assert(not r:native_reaction_busy({}) and not r.native_reaction)
''',
    'guard_contract_remains_owned_and_disable_clears_reaction': r'''
r.state:enter('RKSS_GuardLoop');r:play('RKSS_GuardLoop',true)
local own=obj({GetOwner=function()return r.pawn end})
hook_callbacks[1]({get=function()return own end})
assert(r.playing and not r.native_reaction and r.state:is_guarding())
r:begin_native_reaction();r:disable('test')
assert(not r.native_reaction and not r.mesh.pp and not r.playing)
''',
    'reload_unregisters_all_hook_ids_and_old_callback_is_inert': r'''
local previous=r;local callback=hook_callbacks[1]
previous.enabled=false
dofile(script_dir..'main.lua')
assert(#unregistered==3)
local names={}
for _,entry in ipairs(unregistered)do
 assert(entry[2]==71 and entry[3]==72);names[entry[1]]=true
end
assert(names['/Script/SGameCombatSystem.HitreactComponent:PlayHitreact'])
assert(names['/Script/Engine.AnimInstance:Montage_Play'])
assert(names['/Script/ProjectPBZ.PBZBackPackSubsystem:InitWeaponList'])
previous.enabled=true;previous.playing=true
callback({get=function()error('stale callback accessed context')end})
assert(RingedKnightArsenal.hitreact_hook and RingedKnightArsenal.inventory_init_hook and RingedKnightArsenal.native_montage_hook)
assert(not previous.hitreact_hook and not previous.inventory_init_hook and not previous.native_montage_hook)
''',
}

results = []
for name, body in cases.items():
    print('RUN', name, flush=True)
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().script_dir = scripts.as_posix() + '/'
    try:
        # Parse the unchanged 1.5 MB fixture once in Python. Each case receives
        # an independent Lua table; all other dkjson operations stay real.
        lua.globals().fixture_profile_text = profile_text
        lua.globals().fixture_profile = lua.table_from(profile_data, recursive=True)
        lua.execute("""
local original_dofile=dofile
function dofile(path)
 local result=original_dofile(path)
 if path:match('dkjson%.lua$')then
  local decode=result.decode
  result.decode=function(text,...)if text==fixture_profile_text then return fixture_profile end;return decode(text,...)end
 end
 return result
end
""")
        lua.execute(setup)
        lua.execute("dofile(script_dir..'main.lua')")
        lua.execute(fixture)
        lua.execute(body)
        results.append({'name': name, 'pass': True})
        print('PASS', name)
    except Exception as error:
        results.append({'name': name, 'pass': False, 'error': str(error)})
        print('FAIL', name, error)

(root / 'reports/offline-runtime-adapter-tests.json').write_text(json.dumps({
    'scope': 'Real main.lua under Lua 5.4 with mocked UE APIs; no Unreal/gameplay/visual proof',
    'main_sha256': hashlib.sha256((scripts / 'main.lua').read_bytes()).hexdigest(),
    'cases': results,
}, indent=2), encoding='utf-8')
raise SystemExit(any(not case['pass'] for case in results))
