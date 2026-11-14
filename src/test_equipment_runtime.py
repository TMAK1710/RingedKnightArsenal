"""Run the real main.lua and all equipment modules against strict native-shaped mocks.

Exercises entry-point wiring and bridge requests, using extracted native rows.
This cannot prove Unreal reflection, UI, native Copy ownership, saves or gameplay.
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/runtime/RingedKnightArsenal/Scripts'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

weapon_source = ROOT / 'reports/current-tang-row.json'
soul_source = ROOT / 'extract/pbz-current/ProjectPBZ/Content/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.json'
weapon_native = json.loads(weapon_source.read_text(encoding='utf-8-sig'))
soul_native = json.loads(soul_source.read_text(encoding='utf-8-sig'))[0]['Rows']
profile_text = (SCRIPTS / 'combat-profile.json').read_text(encoding='utf-8')
profile = json.loads(profile_text)
animation_lengths = {clip['asset']: clip['duration'] for clip in profile['clips'].values()}

SETUP = r'''
serial=0;calls={};hooks={};post_hooks={};loops={};keybinds={};objects={};keys_down={};keys_pressed={};native_query_objects={}
loop_actions={}
paused=false;now=0;compatible=true;game_thread=true
function record(name,value)calls[#calls+1]={name=name,value=value}end
function count(name)local n=0;for _,c in ipairs(calls)do if c.name==name then n=n+1 end end;return n end
function last(name)for i=#calls,1,-1 do if calls[i].name==name then return calls[i].value end end end
function obj(kind,path,fields)
 serial=serial+1;local address=serial;fields=fields or {}
 fields.IsValid=function(self)return not self.destroyed end
 fields.GetAddress=function()return address end
 fields.GetFullName=function()return (kind or 'Object')..' '..(path or ('Test.Object'..address))end
 fields.IsA=fields.IsA or function(_,class)
  return (kind=='WeaponActor'or kind=='PBZCharacter'or kind=='Actor')and class.path=='/Script/Engine.Actor'
   or kind and kind:find('Component',1,true)and class.path=='/Script/Engine.SceneComponent'
 end
 fields.path=path
 native_query_objects[path or ('Test.Object'..address)]=fields
 return fields
end
invalid={IsValid=function()return false end}
function FText(s)
 assert(type(s)=='string');return {kind='text',value=s,ToString=function()return s end,type=function()return 'FText'end}
end
function FName(s)local n=FText(s);n.type=function()return 'FName'end;return n end
function text(v)return type(v)=='string' and v or v:ToString()end
function soft(s)return {kind='soft',value=s,GetObjectID=function()return {GetAssetPathName=function()return FName(s)end}end}end
function array(items)
 return setmetatable({}, {
  __len=function()return #items end,
  __index=function(_,key)
   if key=='Empty'then return function()items={}end end
   assert(type(key)=='number' and key>=1 and key<=#items,'Unsafe native array access '..tostring(key));return items[key]
  end,
  __newindex=function(_,key,value)
   assert(type(key)=='number' and key>=1 and key<=#items+1,'Unsafe native array write')
   assert(value.kind=='soft','Whole native struct array replacement');items[key]=value
  end})
end
function object_array(items)
 return setmetatable({}, {
  __len=function()return #items end,
  __index=function(_,key)
   assert(type(key)=='number' and key>=1 and key<=#items,'Unsafe strong object array access');return items[key]
  end,
  __newindex=function(_,key,value)
   assert(type(key)=='number' and key>=1 and key<=#items+1,'Unsafe strong object array write')
   assert(type(value)=='table' and value.IsValid and value:IsValid(),'Strong array requires real object')
   items[key]=value;record('strong_reference',{index=key,object=value})
  end})
end
function struct(values)
 return setmetatable({}, {
  __index=function(_,key)assert(values[key]~=nil,'Unknown native field '..key);return values[key]end,
  __newindex=function(_,key,value)
   assert(values[key]~=nil,'Unknown native field '..key)
   assert(type(value)~='table' or value.kind=='text' or value.kind=='soft','Whole native struct replacement')
   values[key]=value
  end})
end
function map(values)return {ForEach=function(_,fn)for _,entry in ipairs(values)do fn(entry.Key,entry.Value)end end}end
function IsInGameThread()return game_thread end
function on_game_thread(fn)
 local before=game_thread;game_thread=true;local ok,why=pcall(fn);game_thread=before
 if not ok then error(why)end
end
function ExecuteInGameThread(fn)record('one_shot_game_thread',true);on_game_thread(fn)end
function RegisterHook(name,callback,post_callback)
 if name=='/Script/ProjectPBZ.PBZBlueprintFunctionLibrary:MakeTextByKey' then
  assert(not game_thread,'Localization must register on the loader main Lua state')
  assert(type(post_callback)=='function','Native localization needs a post-return callback')
 end
 local id=#calls+100;hooks[name]=callback;post_hooks[name]=post_callback;record('hook',name);return id,id+1
end
function UnregisterHook(name,pre,post)record('unregister',{name=name,pre=pre,post=post})end
function RegisterKeyBind(key,callback)keybinds[key]=callback end
function LoopAsync()error('Arsenal must not schedule asynchronous Lua loops')end
function LoopInGameThreadWithDelay(interval,callback)
 assert(math.type(interval)=='integer' and type(callback)=='function')
 local handle=#loop_actions+1;local entry={interval=interval,callback=callback,active=true}
 loop_actions[handle]=entry
 loops[interval]=function()if entry.active then on_game_thread(entry.callback)end end
 record('schedule_loop',handle);return handle
end
function LoopInGameThreadAfterFrames(interval,callback)
 assert(interval==1);local id=LoopInGameThreadWithDelay(interval,callback);loop_actions[id].per_frame=true;return id
end
function CancelDelayedAction(handle)
 local entry=assert(loop_actions[handle],'Unknown timer handle')
 if not entry.active then return false end
 entry.active=false;record('cancel_loop',handle);return true
end
function CreateInvalidObject()return invalid end
Key={F8=119}
function RK_HostCompatible()return compatible end

world=obj('World','Test.World')
anim_class=obj('AnimBlueprintGeneratedClass','/HuaShira/Characters/Hero/Hero_Hun/Animation/PBZ_ABP_Hun_Base.PBZ_ABP_Hun_Base_C')
native_anim=obj('AnimInstance','Test.NativeAnim',{
 GetClass=function()return anim_class end,GetCurrentActiveMontage=function(self)return self.active end,
 Montage_Play=function(self,montage,rate,result_kind,start,stop_all)
  assert(rate==1 and result_kind==0 and start==0 and stop_all==false)
  local hook=hooks['/Script/Engine.AnimInstance:Montage_Play']
  if hook then hook(self,montage)end
  montage.active=true;montage.paused=false;self.active=montage;record('play',montage)
  return self.play_length_override or montage.length
 end,
 Montage_Pause=function(_,montage)montage.paused=true end,
 Montage_IsActive=function(_,montage)return montage.active end,
 Montage_IsPlaying=function(_,montage)return not montage.paused end,
 Montage_SetPosition=function(_,montage,position)montage.position=position end,
 Montage_Stop=function(self,seconds,montage)
  assert(montage);montage.active=false;montage.fade_out=seconds
  if self.active==montage then self.active=nil end
 end,
})
mesh=obj('SkeletalMeshComponent','Test.Player.Mesh',{AnimClass=anim_class,pp=false,
 GetSocketBoneName=function(_,socket)assert(text(socket)=='Pt_TangBlade_Back_Socket');return FName('spine_03')end,
 GetParentBone=function()return FName('spine_02')end,
 GetSocketTransform=function(_,socket,space)
  assert(space==2);local back=text(socket)=='Pt_TangBlade_Back_Socket'
  return {Rotation={X=0,Y=0,Z=0,W=1},Translation={X=0,Y=back and -25 or 0,Z=back and 15 or 0},Scale3D={X=1,Y=1,Z=1}}
 end,
 GetDisablePostProcessBlueprint=function(self)return self.pp end,
 SetDisablePostProcessBlueprint=function(self,v)self.pp=v;record('postprocess',v)end,
 PlayAnimation=function()error('Single-node playback would replace the native animation graph')end,
 GetAnimInstance=function()return native_anim end,
 SetAnimInstanceClass=function()error('Native animation class must stay installed')end,
 K2_GetComponentToWorld=function()return {Rotation={X=0,Y=0,Z=0,W=1},Translation={X=0,Y=0,Z=0},Scale3D={X=1,Y=1,Z=1}}end})
pc=obj('PlayerController','Test.Controller',{bShowMouseCursor=false,move_lock=false,
 IsInputKeyDown=function(_,key)return keys_down[text(key.KeyName)] or false end,
 WasInputKeyJustPressed=function(_,key)return keys_pressed[text(key.KeyName)] or false end,
 GetInputAnalogKeyState=function()return 0 end,
 IsMoveInputIgnored=function(self)return self.move_lock end,
 SetIgnoreMoveInput=function(self,v)self.move_lock=v;record('move_lock',v)end})
pc.Player=obj('LocalPlayer','Test.LocalPlayer')
input_mode=1
ui_router=obj('PBZUIActionRouterBase','Test.UIRouter',{
 GetOuter=function()return pc.Player end,GetActiveInputMode=function()return input_mode end})
ui_routers={ui_router}
attribute_component=obj('AttributeComponent','Test.Player.Attributes')
native_weapon=obj('WeaponActor','Test.NativeWeapon',{bHidden=false,
 SetActorHiddenInGame=function(self,v)self.bHidden=v;record('native_hidden',v)end})
attached_native={native_weapon}
function make_component()
 return obj('StaticMeshComponent',nil,{
  SetStaticMesh=function(self,asset)self.asset=asset;record('set_mesh',asset.path);return true end,
  SetCollisionEnabled=function()end,K2_AttachToComponent=function(self,parent,bone)self.parent=parent;self.bone=text(bone)end,
  K2_SetRelativeTransform=function(self,value)self.transform=value end,SetVisibility=function(self,value)self.visible=value end,
  K2_GetComponentToWorld=function()return {Rotation={X=0,Y=0,Z=0,W=1},Translation={X=0,Y=0,Z=0},Scale3D={X=1,Y=1,Z=1}}end,
  K2_DestroyComponent=function(self)self.destroyed=true;record('destroy_component',self)end})
end
pawn=obj('PBZCharacter','Test.Player',{
 Mesh=mesh,AttributeSetBase=obj('Attributes','Test.Player.AttributeSet',{Health={CurrentValue=100},Attack={CurrentValue=200}}),
 GetWorld=function()return world end,
 GetAttachedActors=function(_,out)for i,v in ipairs(attached_native)do out[i]=v end end,
 K2_GetComponentsByClass=function(_,class)
  if class.path=='/Script/SGameAttributes.AttributeComponent'then return {attribute_component}end
  if class.path=='/Script/SGameCombatSystem.CharacterWeaponsComponent'then return {weapon_component}end
  return {}
 end,
 K2_GetActorLocation=function()return {X=0,Y=0,Z=0}end,
 K2_GetActorRotation=function(self)return {Pitch=0,Yaw=self.yaw or 0,Roll=0}end,
    K2_SetActorRotation=function(self,rotation)self.yaw=rotation.Yaw;record('turn',self.yaw);return true end,
    GetVelocity=function()return {X=0,Y=0,Z=0}end,
 K2_SetActorLocation=function()end,GetActorForwardVector=function()return {X=1,Y=0,Z=0}end,
 AddComponentByClass=function()record('attach',true);return make_component()end,
 CharacterMovement=obj('Movement','Test.Movement',{
  IsFalling=function()return falling==true end,IsMovingOnGround=function()return not falling end,
  StopMovementImmediately=function()record('stop_move',true)end})})
pc.Pawn=pawn
backpack=obj('PBZBackPackSubsystem','Test.Backpack',{
 CurrentMainWeaponID=FName('Tang'),ids={'Tang','Other'},index=0,owned={Tang=true,Other=true},
 saved_level=1,saved_max=30,saved_strength=1,souled=false,
 GetOuter=function()return world end,
 HasWeapon=function(self,id,normal)assert(normal);return self.owned[text(id)] or false end,
 AddWeaponItem=function(self,id,normal,push,load,auto)
  assert(normal and push and not load and not auto);self.owned[text(id)]=true;record('grant',text(id))
 end,
 IsWeaponSnapSouled=function(self,id,normal)assert(text(id)=='RKA_RingedKnight' and normal);return self.souled end,
 GetWeaponLevel=function(self,id,normal)assert(text(id)=='RKA_RingedKnight' and normal);return self.saved_level end,
 GetWeaponMaxLevel=function(self,id,normal)assert(text(id)=='RKA_RingedKnight' and normal);return self.saved_max end,
 GetWeaponAttackMultipliers=function(self,owner,config,out)
  assert(owner==pawn and type(out)=='table');out.WeaponStrengthMultiplier=self.saved_strength
  record('strength_query',config.path);return true
 end})
function choose(id)backpack.CurrentMainWeaponID=FName(id);backpack.ids[1]=id;backpack.owned[id]=true end
function backpack:GetEquipmentNormalWeapons()
 local values={};for i,id in ipairs(self.ids)do values[i]=FName(id)end;return values
end
function backpack:GetCurrentMainWeaponIndex()return self.index end
other_native_weapon=obj('WeaponActor','Test.OtherNativeWeapon',{bHidden=false,writes=0,
 SetActorHiddenInGame=function(self,value)self.bHidden=value;self.writes=self.writes+1 end})
rka_native_actors={native_weapon}
rka_native_scabbards={}
weapon_component=obj('CharacterWeaponsComponent','Test.Player.Weapons',{
 armed=true,
 GetOwner=function()return pawn end,
 IsArmed=function(self,tag)assert(text(tag.TagName)=='Weapon.Slot.Main');return self.armed end,
 GetCurrentWeaponIndex=function()return backpack.index end,
 RuntimeWeaponData={ForEach=function(_,callback)
  local values={}
  for i,id in ipairs(backpack.ids)do
   local own=id=='RKA_RingedKnight'
   local config=own and RingedKnightArsenal.equipment.configs[backpack.souled and 'Weapon_RKA_RingedKnight_Soul'or 'Weapon_RKA_RingedKnight']or objects[template_path]
   values[i]={WeaponConfig=config,WeaponActors=i==1 and rka_native_actors or {other_native_weapon},Scabbards=own and rka_native_scabbards or {}}
  end
  callback({TagName=FName('Weapon.Slot.Main')},{Weapons=values})
 end}})
input_subsystem=obj('EnhancedInputSubsystem','Test.Input',{
 AddMappingContext=function()record('input_add',true)end,
 RemoveMappingContext=function()record('input_remove',true)end})
function FindFirstOf(name)assert(name=='EnhancedInputLocalPlayerSubsystem');return input_subsystem end
function FindAllOf(name)
 if name=='PBZBackPackSubsystem'then return {backpack}end
 if name=='W_pickupgear_C'then return {}end
 if name=='PBZAbilitySystemComponent'then return {pawn_ability_system}end
 if name=='CharacterWeaponsComponent'then return {weapon_component}end
 assert(name=='PBZUIActionRouterBase','Unexpected FindAllOf class '..tostring(name));return ui_routers
end
pawn_ability_system=obj('PBZAbilitySystemComponent','Test.Hun.AbilitySystem',{
 GetOwner=function()return pawn end,
 HasMatchingGameplayTag=function(_,tag)
  local value=text(tag.TagName)
  if value=='Ability.Action.Hun.Jump'then return jumping==true end
  if value=='CharacterState.Landing'then return landing==true end
  if value=='Ability.Action.Execution' or value=='Ability.Executed' or value=='Ability.UpperBody.Hun.ChangeArmed'
   or value=='Ability.Action.Hun.SimpleExecution' or value=='Ability.Action.Hun.PerfectDodge'
   or value=='CharacterState.ChangingArmed' or value=='CharacterState.Native.Sequence'
   or value=='CharacterState.FlowIdle' or value=='CharacterState.FlowIdle.CantBreak'then return false end
  if value=='Ability.SpecialMove' or value=='Ability.Action.Hun.SpecialMove' or value=='CharacterState.AbilityState.InSpecialPerform'then return false end
  assert(value=='Ability.Action.Hun.Dash');return dash_active==true
 end,
 TryActivateAbilityByClass=function(_,ability,allow_remote)
  assert(ability==template['Change Armed Ability'] and allow_remote)
  record('native_draw',ability);return true
 end})
package.preload.UEHelpers=function()return {
 GetPlayer=function()return pawn end,GetPlayerController=function()return pc end,
 GetKismetSystemLibrary=function()return system end}end

system=obj('KismetSystemLibrary','Test.System',{
 MakeSoftObjectPath=function(_,s)return s end,
 Conv_SoftObjPathToSoftObjRef=function(_,s)return soft(s),false end,
 LoadAsset_Blocking=function(_,s)return StaticFindObject(s.value)end,
 PrintString=function()end,
 SphereTraceMulti=function()error('Remote out-array trace must never be used')end,
 SphereOverlapActors=function()error('Remote out-array overlap must never be used')end})
gameplay=obj('GameplayStatics','Test.Gameplay',{
 IsGamePaused=function()return paused end,GetTimeSeconds=function()return now end})
mathlib=obj('KismetMathLibrary','Test.Math',{
 MakeRelativeTransform=function(_,first,second)
  return {Rotation=first.Rotation,Translation={X=first.Translation.X-second.Translation.X,Y=first.Translation.Y-second.Translation.Y,
   Z=first.Translation.Z-second.Translation.Z},Scale3D={X=1,Y=1,Z=1}}
 end,
 TransformDirection=function(_,basis,v)return v end,TransformLocation=function(_,basis,v)return v end})
faction=obj('FactionUtils','Test.Faction',{GetFactionRelation=function()return 2 end})
function make_effect()
 return obj('NiagaraComponent',nil,{SetRelativeScale3D=function()end,
 SetEmitterEnable=function(_,name,enabled)assert(not enabled);record('disabled_flame_emitter',text(name))end,
 Activate=function(_,reset)assert(reset);record('activate_flame',true)end,
 K2_DestroyComponent=function(self)self.destroyed=true;record('destroy_effect',true)end})
end
niagara=obj('NiagaraLibrary','Test.Niagara',{
 SpawnSystemAttached=function()record('flame',true);return make_effect()end,
 SpawnSystemAtLocation=function()record('explosion',true);return make_effect()end})
package_class=obj('Class','/Script/CoreUObject.Package')
config_class=obj('BlueprintGeneratedClass','/PBZCombatAsset/Prototypes/Config/PBZ_MainWeaponConfig.PBZ_MainWeaponConfig_C')
template_path='/PBZCombatAsset/ActorData/Players/Hun/Weapon/Tang/Weapon_Hun_Tang.Weapon_Hun_Tang'
native_draw_ability=obj('LegoAbilityBlueprintGeneratedClass',
 '/PBZCombatAsset/ActorData/Players/Hun/Abilities/TangBlade/Default/GA_Hun_Tang_ChangeArmed.GA_Hun_Tang_ChangeArmed_C')
template=obj('PBZ_MainWeaponConfig_C',template_path,{GetClass=function()return config_class end,
 ['Change Armed Ability']=native_draw_ability})
objects[template_path]=template
local reduction_root='/PBZCombatAsset/ActorData/Players/Hun/ShaqiWeapon/HuoLiuXing/UpgradeData/GE_ShachiWeapon_HuoLiuXing_Defence'
reduction_class=obj('BlueprintGeneratedClass',reduction_root..'.GE_ShachiWeapon_HuoLiuXing_Defence_C')
function make_damage_reduction(outer,path)
 local modifiers={}
 for _,name in ipairs({'TakenReductionMultiplier_Physical','TakenReductionMultiplier_Elemental'})do
  modifiers[#modifiers+1]={Attribute={AttributeName=name},ModifierMagnitude={ScalableFloatMagnitude={Value=.75}}}
 end
 return obj('GameplayEffect',path,{GetOuter=function()return outer end,Modifiers=modifiers,
  DurationPolicy=1,DurationMagnitude={MagnitudeCalculationType=0,ScalableFloatMagnitude={Value=0}}})
end
objects[reduction_class.path]=reduction_class
objects[reduction_root..'.Default__GE_ShachiWeapon_HuoLiuXing_Defence_C']=make_damage_reduction(nil,
 reduction_root..'.Default__GE_ShachiWeapon_HuoLiuXing_Defence_C')
objects['/Script/CoreUObject.Package']=package_class
objects['/Script/Engine.Default__KismetMathLibrary']=mathlib
objects['/Script/Engine.Default__GameplayStatics']=gameplay
objects['/Script/SGameCombatSystem.Default__FactionUtils']=faction
objects['/Script/Niagara.Default__NiagaraFunctionLibrary']=niagara
objects['/Script/Engine.Default__AnimMontage']=obj('AnimMontage','Test.MontageFactory',{
 CreateSlotAnimationAsDynamicMontage_WithBlendSettings=function(_,asset,slot,blend_in)
  assert(({BoatSlot=true,LeftArmOverride=true,RightArmOverride=true})[text(slot)])
  local rate=math.abs(asset.RateScale)<=1e-8 and 1 or asset.RateScale
  return obj('AnimMontage',nil,{asset=asset,slot=text(slot),blend_in=blend_in.Blend.BlendTime,position=0,
   length=asset.duration/math.abs(rate)})
 end})
for asset,duration in pairs(animation_lengths)do
 objects[asset]=obj('AnimSequence',asset,{bEnableRootMotion=false,duration=duration,RateScale=1,
  GetPlayLength=function(self)return self.duration end})
end
local localization_path='/Script/ProjectPBZ.PBZBlueprintFunctionLibrary:MakeTextByKey'
objects[localization_path]=obj('Function',localization_path,{
 ForEachProperty=function(_,fn)
  for _,field in ipairs({'StrProperty '..localization_path..':Key','TextProperty '..localization_path..':ReturnValue'})do
   fn({GetFullName=function()return field end})
  end
 end})
function StaticFindObject(path)
 assert(not path:find('/HuaShira/Mods/RingedKnight/Data/',1,true) or path:find('.',1,true),
  'UE4SS GetPackageNameFromLongName rejects bare package paths')
 if objects[path]then return objects[path]end
 if path:find('/HuaShira/Mods/RingedKnight/Data/',1,true)==1 then return invalid end
 objects[path]=obj('Class',path);return objects[path]
end
function StaticConstructObject(class,outer,name,flags,internal,a,b,source)
 if class==package_class then
  assert(outer==invalid and flags==0x41 and internal==0x40000000 and not a and not b and not source)
  local p=text(name);objects[p]=obj('Package',p);record('construct_package',p);return objects[p]
 elseif class==config_class then
  assert(source==template and flags==0x41 and internal==0x40000000 and not a and not b)
  local p=outer.path..'.'..text(name)
  objects[p]=obj('PBZ_MainWeaponConfig_C',p,{GetOuter=function()return outer end,
   ['Change Armed Ability']=source['Change Armed Ability']})
  record('construct_config',p);return objects[p]
 elseif class==reduction_class then
  assert(text(name)=='RKA_ActionDamageReduction' and flags==0xC1 and internal==0x40000000)
  local p=outer.path..'.'..text(name);objects[p]=make_damage_reduction(outer,p)
  record('construct_damage_reduction',p);return objects[p]
 elseif class.path=='/Script/Engine.ObjectLibrary' then
  assert(outer:GetFullName()=='Package /HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight')
  assert((text(name)=='RKA_ItemTables' or text(name)=='RKA_CombatAssets') and flags==0xC1 and internal==0x40000000 and not a and not b and source==nil)
  local p=outer.path..'.'..text(name)
  assert(not objects[p],'Duplicate ObjectLibrary construction')
  objects[p]=obj('ObjectLibrary',p,{GetOuter=function()return outer end,
   Objects=object_array({}),WeakObjects={},bUseWeakReferences=true,bHasBlueprintClasses=true})
  record(text(name)=='RKA_ItemTables'and 'construct_holder'or 'construct_combat_holder',p);return objects[p]
 elseif class.path=='/Script/EnhancedInput.InputMappingContext' then
  return obj('InputMappingContext',nil,{MapKey=function(_,action,key)record('mapkey',{action=action,key=text(key.KeyName)})end})
 elseif class.path=='/Script/EnhancedInput.InputAction' then return obj('InputAction')
 elseif class.path=='/Script/EnhancedInput.InputTriggerChordAction' then return obj('InputTriggerChordAction')
 elseif class.path=='/Script/SGameCombatSystem.DamageSource_GameplayEffect' then return obj('DamageSource','Test.DamageSource')
 end
 error('Unexpected native construction: '..tostring(class.path))
end
target_attributes=obj('Attributes','Test.Target.Attributes',{Health={CurrentValue=1000},Shield={CurrentValue=0}})
target_component=obj('AttributeComponent','Test.Target.DamageComponent')
target_reaction=obj('HitreactComponent','Test.Target.Reaction')
target=obj('PBZCharacter','Test.Target',{bCanBeDamaged=true,AttributeSetBase=target_attributes,
 IsA=function()return true end,K2_GetActorLocation=function()return {X=100,Y=0,Z=0}end,
 K2_GetComponentsByClass=function(_,class)
  return {class.path=='/Script/SGameAttributes.AttributeComponent' and target_component or target_reaction}
 end})
print=function()end
'''

BRIDGE = r'''
json=dofile(script_dir..'dkjson.lua')
function table_object(schema,rows)
 local path=schema=='WeaponData' and '/Game/PBZContent/DataTable/UI/DT_WeaponData.DT_WeaponData'
  or '/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText'
 return obj('DataTable',path,{
  GetRowStruct=function()return obj('ScriptStruct','/Script/ProjectPBZ.'..schema)end,
  ForEachRow=function(_,fn)for k,v in pairs(rows)do fn(k,v)end end,
  FindRow=function(_,id)return rows[text(id)]end,
  RemoveRow=function(_,id)rows[text(id)]=nil end})
end
weapon_data=table_object('WeaponData',weapon_rows)
soul_data=table_object('WeaponSnapSoulTextData',soul_rows)
objects['/Game/PBZContent/DataTable/UI/DT_WeaponData.DT_WeaponData']=weapon_data
objects['/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText']=soul_data
function RK_NativeInventory(raw)
 local request=assert(json.decode(raw));local phase=request.phase;record(phase,request)
 if phase=='clone' or phase=='soul_clone' then
  local keeper=RingedKnightArsenal.lifetime
  assert(keeper and keeper.prepared and keeper.holder.bUseWeakReferences==false)
  assert(#keeper.holder.Objects==2 and #keeper.holder.WeakObjects==0,'Cloning before strong table lifetime preparation')
  assert(keeper.holder.Objects[1]==weapon_data and keeper.holder.Objects[2]==soul_data)
 end
 if phase=='config_finalize'then return json.encode({ok=true,owned=true,phase=phase})
 elseif phase=='sanitize'then return json.encode({ok=true,id=request.id,economy_preserved=true,upgrade_entries=59})
 elseif phase=='publish'then
  local row=assert(weapon_rows[request.id]);assert(request.id=='RKA_RingedKnight' and text(row.ItemId)==request.id)
  assert(row.WeaponName.Key:match('^RKA_TXT_%x%x%x%x%x%x%x%x$') and row.WeaponName.ValueCache:ToString()=='环印骑士剑')
  return json.encode({ok=true,id=request.id,published=true,cache_pointer_verified=true})
 elseif phase=='clone'then
  assert(request.base_row=='黑伤' and request.base_item=='Tang' and not weapon_rows[request.id])
  weapon_rows[request.id]=weapon_factory();return json.encode({ok=true,id=request.id,deep_copy=true})
 elseif phase=='soul_clone'then
  assert(request.base_row=='heimoshang' and not soul_rows[request.id])
  soul_rows[request.id]=soul_factory();soul_rows[request.id].ID=FName(request.id)
  return json.encode({ok=true,id=request.id,deep_copy=true})
 elseif phase=='soul_rollback'then soul_rows[request.id]=nil;return json.encode({ok=true,removed=true})
 end
 error('Unexpected inventory bridge request '..phase)
end
function RK_ShieldState(raw)local request=assert(json.decode(raw));record('shield',request);return '{"stamina_spent":0}'end
function RK_CombatProtection(raw)
 local request=assert(json.decode(raw));record('protection',request)
 if request.phase=='prepare'then return '{"api":1,"finite_specs":true,"hp_immunity":false,"action_damage_taken_multiplier":0.2}'end
 return json.encode({api=1,active=request.active==true,hp_immunity=false,action_damage_taken_multiplier=.2})
end
function RK_NativeHit(raw)
 local request=assert(json.decode(raw))
 if request.phase=='capabilities'then
  record('native_hit_capabilities',request)
  return json.encode(damage_capabilities or {api=2,ultimate_charge_regen_tag='Damage.Attack.Attacker.UltimateChargeRegen',ultimate_charge_regen_default=0})
 end
 record('native_hit',request)
 assert(type(request.ultimate_charge_regen)=='number'and request.ultimate_charge_regen>=0,'Native Ultimate regeneration must be explicit and nonnegative')
 assert(type(request.ultimate_charge_diagnostics)=='boolean','Ultimate diagnostics must be explicit')
 if request.phase=='damage'and request.ultimate_charge_diagnostics then record('ultimate_diagnostic',request)end
 if request.phase=='damage'then target_attributes.Health.CurrentValue=target_attributes.Health.CurrentValue-10 end
 return json.encode({dispatched=true,ultimate_charge_regen=request.ultimate_charge_regen})
end
art_balance=100;art_receipts={};art_session=0
function RK_ArtResource(raw)
 local q=assert(json.decode(raw))
 if q.phase=='capabilities'then
  art_session=art_session+1;record('art_cost_capabilities',q)
  return json.encode(art_cost_capabilities or {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=art_session})
 end
 record('art_cost_attempt',q)
 local key=q.session_token..':'..q.sequence
 if art_receipts[key]then return json.encode(art_receipts[key])end
 local receipt={api=1,resource='UltimateChargeCount',amount=1,session_token=q.session_token,sequence=q.sequence,before=art_balance,after=art_balance,
  paid=false,committed=false,dispatched=false,status='insufficient'}
 if art_balance>=1 then
  art_balance=art_balance-1;receipt.after=art_balance;receipt.paid=true;receipt.committed=true;receipt.dispatched=true;receipt.status='paid'
  art_receipts[key]=receipt;record('art_cost_paid',q)
 end
 return json.encode(receipt)
end
query_hits={};query_actors={}
function RK_NativeQuery(raw)
 local request=assert(json.decode(raw));record('native_query',request)
 for _,path in ipairs(request.ignore or {})do
  local object=native_query_objects[path]
  if not object or not object:IsA(StaticFindObject('/Script/Engine.Actor'))then return nil,'RK native query: query ignored object is not Actor: '..path end
 end
 if request.phase=='capabilities'then return '{"api":1,"owned_parameter_frames":true,"trace":true,"trace_batch":true,"max_batch":64,"overlap":true,"blocking_hit_flags":true}'end
 if request.phase=='trace'then return json.encode({api=1,phase='trace',owned_parameter_frames=true,hits=query_hits})end
 if request.phase=='trace_batch'then
  assert(type(request.segments)=='table'and #request.segments>0 and #request.segments<=64,'Native batch size contract')
  local results={}
  for index,segment in ipairs(request.segments)do
   assert(type(segment.start)=='table'and type(segment.finish)=='table'and type(segment.radius)=='number')
   results[index]={hits=query_hits}
  end
  return json.encode({api=1,phase='trace_batch',owned_parameter_frames=true,results=results})
 end
 if request.phase=='overlap'then return json.encode({api=1,phase='overlap',owned_parameter_frames=true,actors=query_actors})end
 error('Unexpected query request')
end
function init()
 hooks['/Script/ProjectPBZ.PBZBackPackSubsystem:InitWeaponList']()
 assert(RingedKnightArsenal.inventory_ready,RingedKnightArsenal.inventory_error)
end
function supervise()
 assert(loops[250]()==nil,'Pinned game-thread loop ignores callback returns')
 assert(not RingedKnightArsenal.inventory_error,RingedKnightArsenal.inventory_error)
end
function enable_own()
 init();choose('RKA_RingedKnight');supervise()
 assert(RingedKnightArsenal.enabled,'Supervisor did not activate selected independent weapon')
 return RingedKnightArsenal
end
'''

CASES = {
    'native_damage_capabilities_are_checked_separately_from_dispatched_hits': r'''
local r=enable_own()
assert(r.enabled and count('native_hit_capabilities')==1 and count('native_hit')==0)
''',
    'old_damage_api_cannot_activate_ultimate_regeneration_combat': r'''
damage_capabilities={api=1,ultimate_charge_regen_tag='Damage.Attack.Attacker.UltimateChargeRegen',ultimate_charge_regen_default=0}
init();choose('RKA_RingedKnight');loops[250]()
local r=RingedKnightArsenal
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(count('native_hit_capabilities')==1 and count('native_hit')==0 and count('attach')==0 and count('input_add')==0)
''',
    'spirit_shadow_tag_cannot_substitute_for_the_confirmed_ultimate_resource': r'''
damage_capabilities={api=2,ultimate_charge_regen_tag='Damage.Attack.Attacker.SpiritShadowChargeRegen',ultimate_charge_regen_default=0}
init();choose('RKA_RingedKnight');loops[250]()
local r=RingedKnightArsenal
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(count('native_hit_capabilities')==1 and count('native_hit')==0 and count('attach')==0 and count('input_add')==0)
''',
    'native_damage_nonzero_regen_default_cannot_activate_combat': r'''
damage_capabilities={api=2,ultimate_charge_regen_tag='Damage.Attack.Attacker.UltimateChargeRegen',ultimate_charge_regen_default=.25}
init();choose('RKA_RingedKnight');loops[250]()
local r=RingedKnightArsenal
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(count('native_hit_capabilities')==1 and count('native_hit')==0 and count('attach')==0 and count('input_add')==0)
''',
    'ordinary_contact_forwards_ultimate_regen_only_on_hit_and_once_per_target_contact': r'''
local r=enable_own();objects['Test.Target']=target
for _,name in ipairs({'RKSS_Light1','RKSS_Light2','RKSS_Light3','RKSS_Heavy1Release','RKSS_Heavy1Charge',
 'RKSS_Heavy2Release','RKSS_Heavy2Charge','RKSS_PlungeStart','RKSS_PlungeLoop','RKSS_PlungeLand'})do
 for _,hit in ipairs(r.state.profile.clips[name].hits)do assert(hit.ultimate_charge_regen==1,'Original ordinary-step Ultimate budget changed: '..name)end
end
assert(r.state:enter('RKSS_Light1',true));assert(r:play('RKSS_Light1',false))
local hit=r.state.profile.clips.RKSS_Light1.hits[1]
assert(hit.ultimate_charge_regen==1)
local event={serial=r.state.serial,index=1,time=hit.start,hit=hit,light_index=1}
query_hits={};r:hit_window(event)
assert(count('native_hit')==0 and target_attributes.Health.CurrentValue==1000 and count('ultimate_diagnostic')==0 and not r.ultimate_probe_done)
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
r:hit_window(event);r:hit_window(event)
assert(count('native_hit')==2 and count('strength_query')==1 and target_attributes.Health.CurrentValue==990)
local damage_count=0
for _,call in ipairs(calls)do
 if call.name=='native_hit'then
  assert(call.value.ultimate_charge_regen==hit.ultimate_charge_regen)
  if call.value.phase=='damage'then damage_count=damage_count+1 end
 end
end
assert(damage_count==1)
assert(count('ultimate_diagnostic')==1 and r.ultimate_probe_done)
''',
    'heavy_native_upgrade_scales_damage_without_scaling_ultimate_regen': r'''
local r=enable_own();objects['Test.Target']=target
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
for index,strength in ipairs({1.1,3.9})do
 backpack.saved_level=index==1 and 2 or 30;backpack.saved_strength=strength
 assert(r.state:enter('RKSS_Heavy1Release',true));assert(r:play('RKSS_Heavy1Release',false))
 local hit=r.state.profile.clips.RKSS_Heavy1Release.hits[1]
 assert(hit.ultimate_charge_regen==1)
 local event={serial=r.state.serial,index=1,time=hit.start,hit=hit}
 r:hit_window(event);r:hit_window(event)
 local request=last('native_hit')
 assert(math.abs(request.coefficient-hit.physical*strength/200)<1e-8)
 assert(math.abs(request.fire-hit.fire*strength/200)<1e-8)
 assert(request.ultimate_charge_regen==hit.ultimate_charge_regen)
 assert(count('native_hit')==index*2 and count('strength_query')==index)
end
assert(count('ultimate_diagnostic')==1 and r.ultimate_probe_done)
''',
    'failed_positive_damage_receipt_does_not_consume_the_one_time_ultimate_probe': r'''
local r=enable_own();objects['Test.Target']=target
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
assert(r.state:enter('RKSS_Heavy1Release',true));assert(r:play('RKSS_Heavy1Release',false))
local hit=r.state.profile.clips.RKSS_Heavy1Release.hits[1]
local native=RK_NativeHit
RK_NativeHit=function(raw)return nil,'mock damage receipt failure'end
assert(not pcall(r.hit_window,r,{serial=r.state.serial,index=1,time=hit.start,hit=hit}))
assert(not r.ultimate_probe_done and count('ultimate_diagnostic')==0)
RK_NativeHit=native
assert(r.state:enter('RKSS_Heavy1Release',true));assert(r:play('RKSS_Heavy1Release',false))
r:hit_window({serial=r.state.serial,index=1,time=hit.start,hit=hit})
assert(r.ultimate_probe_done and count('ultimate_diagnostic')==1)
''',
    'all_ember_contacts_bombs_and_unspecified_damage_explicitly_disable_ultimate_regen': r'''
local r=enable_own();objects['Test.Target']=target
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
local hits=0
for _,name in ipairs({'RKSS_Ember','RKSS_EmberFollow1','RKSS_EmberFollow2','RKSS_EmberHeavy'})do
 assert(r.state:enter(name,true));assert(r:play(name,false))
 for index,hit in ipairs(r.state.profile.clips[name].hits)do
  assert(hit.ultimate_charge_regen==0,'Ember must not refill Ultimate: '..name)
  r:hit_window({serial=r.state.serial,index=index,time=hit.start,hit=hit});hits=hits+1
  assert(last('native_hit').ultimate_charge_regen==0)
 end
end
assert(count('native_hit')==hits*2)
query_actors={'Test.Target'};query_hits={}
r:explode({X=0,Y=0,Z=0},'ultimate-zero-bomb')
assert(last('native_hit').kind=='explosion'and last('native_hit').ultimate_charge_regen==0)
r:damage(target,{ImpactPoint={X=100,Y=0,Z=0},ImpactNormal={X=0,Y=0,Z=1}},'ultimate-default-zero',100,10,'sword',100)
assert(last('native_hit').ultimate_charge_regen==0)
assert(count('ultimate_diagnostic')==0 and not r.ultimate_probe_done)
''',
    'real_scabbard_hidden_component_cannot_abort_a_complete_light_attack': r'''
init();choose('RKA_RingedKnight')
local scabbard=obj('SkeletalMeshComponent','Test.Player.Scabbard',{bHiddenInGame=false,
 SetHiddenInGame=function(self,value,propagate)assert(not propagate);self.bHiddenInGame=value end})
rka_native_scabbards[1]=scabbard;supervise()
local r=RingedKnightArsenal
assert(#r.hidden==2 and native_weapon.bHidden and scabbard.bHiddenInGame)
objects['Test.Target']=target
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
for frame=1,180 do
 keys_down.LeftMouseButton=frame==1;keys_pressed.LeftMouseButton=frame==1
 now=now+1/60;loops[1]()
end
assert(not r.action_error,'Complete light attack was aborted: '..tostring(r.action_error))
assert(r.enabled and not r.development_suspended and not r.native_reaction)
assert(not r.action_failures and r.state.clip==nil and r.idle_playing)
assert(r.hits==1 and count('native_hit')==2 and target_attributes.Health.CurrentValue==990)
local traces=0
for _,call in ipairs(calls)do
 if call.name=='native_query'and call.value.phase=='trace'then
  traces=traces+1;local ignored=call.value.ignore
  assert(#ignored==2 and ignored[1]=='Test.Player'and ignored[2]=='Test.NativeWeapon')
 end
end
assert(traces>0)
''',
    'bomb_ground_sweep_ignores_actor_proxy_and_projectile_but_never_scabbard_component': r'''
init();choose('RKA_RingedKnight')
local scabbard=obj('SkeletalMeshComponent','Test.Player.Scabbard',{bHiddenInGame=false,
 SetHiddenInGame=function(self,value)self.bHiddenInGame=value end})
rka_native_scabbards[1]=scabbard;supervise();local r=RingedKnightArsenal
assert(#r.hidden==2 and scabbard.bHiddenInGame)
local bomb=obj('Actor','Test.RopeBomb',{K2_SetActorLocation=function(self,position)self.position=position end,
 K2_DestroyActor=function(self)self.destroyed=true end})
r.projectiles={{actor=bomb,position={X=0,Y=0,Z=100},velocity={X=0,Y=0,Z=-180},age=0,key='bomb-component-regression'}}
query_hits={};r:projectile_step(1/60)
assert(#r.projectiles==1 and bomb.position.Z<100 and not r.action_error)
local request=last('native_query');assert(request.phase=='trace'and #request.ignore==3)
local included={};for _,path in ipairs(request.ignore)do included[path]=true end
assert(included['Test.Player']and included['Test.NativeWeapon']and included['Test.RopeBomb'])
assert(not included['Test.Player.Scabbard'])
''',
    'plunge_air_and_landing_each_damage_the_same_target_once': r'''
local r=enable_own()
objects['Test.Target']=target
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
r.keys=function()return plunge_input or {}end
falling=true;r:tick(.016)
plunge_input={attack_pressed=true};r:tick(.016)
plunge_input={}
for i=1,150 do r:tick(1/60)end
assert(r.state.clip=='RKSS_PlungeLoop' and r.hits==1)
falling=false;r:tick(.016)
for i=1,30 do r:tick(1/60)end
assert(r.state.clip=='RKSS_PlungeLand' and r.hits==2)
''',
    'stationary_jump_yields_on_native_tags_and_resumes_after_landing': r'''
local r=enable_own()
assert(r.idle_playing and mesh.pp)
local idle=r.animation_blend.montage
jumping=true;r:tick(.016)
assert(r.native_airborne and idle.fade_out==0 and not mesh.pp and not r.idle_playing and not r.native_reaction)
jumping=false;falling=true
r:tick(.016);assert(not r.idle_playing and not r.state.clip)
falling=false;landing=true
r:tick(.016);r:tick(.1);r:tick(.1);r:tick(.1)
assert(not r.idle_playing and not pc.move_lock)
landing=false;r:tick(.016)
assert(r.idle_playing and not r.native_airborne)
''',
    'native_dodge_tag_yields_even_before_its_montage_is_visible': r'''
local r=enable_own()
r.state:enter('RKSS_Light1');assert(r:play('RKSS_Light1',false))
dash_active=true;r:tick(.016)
assert(r.native_reaction and not r.state.clip and not r.playing)
r:tick(.016);assert(r.native_reaction and not r.idle_playing)
dash_active=false;r:tick(.016);assert(not r.native_reaction and not r.native_input_handoff and not r.state.clip)
r:tick(.016);assert(r.idle_playing)
''',
    'circle_is_owned_only_by_the_guard_chord_and_triggers_once': r'''
local r=enable_own()
local mappings={}
for _,call in ipairs(calls)do
    if call.name=='mapkey'then
        assert(not mappings[call.value.key]);mappings[call.value.key]=call.value.action
    end
end
local chord=mappings.Gamepad_FaceButton_Right
assert(chord.Triggers[1].ChordAction==mappings.Gamepad_LeftShoulder and chord.bConsumeInput)
keys_down.Gamepad_FaceButton_Right=true
assert(not r:keys().circle_pressed)
keys_down.Gamepad_LeftShoulder=true
assert(not r:keys().circle_pressed)
keys_down.Gamepad_FaceButton_Right=false;r:keys()
keys_down.Gamepad_FaceButton_Right=true;r:tick(.016)
assert(r.state.clip=='RKSS_EmberStart' and r.state.art_followup=='RKSS_EmberHeavy')
assert(not r:keys().circle_pressed)
''',
    'three_rapid_square_edges_select_three_distinct_light_montages': r'''
local r=enable_own()
local last_serial=r.state.serial
local sequence={}
for frame=0,130 do
    keys_down.Gamepad_FaceButton_Left=frame==0 or frame==9 or frame==18
    r:tick(1/60)
    if r.state.serial~=last_serial and r.state.clip then
        local montage=r.animation_blend.montage
        assert(montage and montage.asset.path:find(r.state.clip,1,true))
        sequence[#sequence+1]=r.state.clip
    end
    last_serial=r.state.serial
end
assert(table.concat(sequence,',')=='RKSS_Light1,RKSS_Light2,RKSS_Light3')
''',
    'confirmed_switch_entry_uses_one_direct_heavy': r'''
local r=enable_own()
r.switch_entry={age=0,receipt={id='RKA_RingedKnight',pawn=pawn:GetAddress(),owner=backpack:GetAddress()}}
r:tick(.016);assert(r.state.clip=='RKSS_Heavy1Release' and not r.switch_entry)
local serial=r.state.serial
r:tick(.016);assert(r.state.serial==serial and r.state.stamina==100)
''',
 'native_scheduler_preserves_intervals_order_and_deduplicates_commands': r'''
assert(#loop_actions==3 and loop_actions[1].interval==250 and loop_actions[2].interval==1 and loop_actions[2].per_frame and loop_actions[3].interval==500)
local old_open,old_load=io.open,loadfile;local request='000352';local command_calls=0
io.open=function(path,mode)
 assert(path:find('/private/runtime-commands/runtime_request.txt',1,true) and mode=='r')
 return {read=function()return request end,close=function()end}
end
loadfile=function(path)
 assert(path:find('/private/runtime-commands/000352.lua',1,true))
 return function()assert(IsInGameThread());command_calls=command_calls+1 end
end
game_thread=false
loops[500]();loops[500]();request='invalid';loops[500]()
assert(command_calls==1 and not IsInGameThread() and count('one_shot_game_thread')==0)
io.open,loadfile=old_open,old_load
''',
 'saved_slot_reload_rejects_probe_context_before_file_or_native_access': r'''
local chunk=assert(loadfile(script_dir..'../../../reload_saved_test_slot.lua'))
local r=RingedKnightArsenal;local old_open=io.open;local reads=0
io.open=function()reads=reads+1;error('Wrong context must not access reports')end
RingedKnightArsenal=nil
local ok,why=pcall(chunk)
assert(not ok and why:find('runtime_request.txt',1,true) and why:find('RingedKnightProbe',1,true))
assert(reads==0 and count('clone')==0 and count('native_hit')==0)
RingedKnightArsenal=r;io.open=old_open
''',
 'saved_slot_reload_requires_ready_arsenal_before_existing_preflight': r'''
local chunk=assert(loadfile(script_dir..'../../../reload_saved_test_slot.lua'))
local r=RingedKnightArsenal;local old_open=io.open;local reads=0
io.open=function(path,mode)
 reads=reads+1
 assert(path:find('/reports/runtime-complete-item-preflight.json',1,true) and mode=='rb')
 return {read=function()return '{"ok":false}'end,close=function()end}
end
local ok,why=pcall(chunk)
assert(not ok and why:find('inventory is not ready',1,true) and reads==0)
r.inventory_ready=true
game_thread=false
ok,why=pcall(chunk)
assert(not ok and why:find('Arsenal game-thread queue',1,true) and reads==0)
game_thread=true
ok,why=pcall(chunk)
assert(not ok and not why:find('Lua context',1,true) and not why:find('inventory is not ready',1,true))
assert(reads==1 and count('clone')==0 and count('native_hit')==0)
io.open=old_open
''',
 'scheduler_disposal_cancels_all_handles_and_stale_callbacks_are_inert': r'''
local r=RingedKnightArsenal;local callbacks={loop_actions[1].callback,loop_actions[2].callback,loop_actions[3].callback}
local stale_key=keybinds[Key.F8]
r:dispose_hooks();r:stop_scheduler()
assert(r.scheduler_stopped and #r.scheduler_handles==0 and count('cancel_loop')==3)
assert(not loop_actions[1].active and not loop_actions[2].active and not loop_actions[3].active)
for _,callback in ipairs(callbacks)do on_game_thread(callback)end
stale_key();assert(not r.suspend_requested and count('clone')==0 and count('cancel_loop')==3)
''',
 'retired_generation_cancels_timers_before_any_native_work': r'''
local r=RingedKnightArsenal;RK_RuntimeGeneration=RK_RuntimeGeneration+1
loops[250]();loops[1]();loops[500]();keybinds[Key.F8]()
assert(r.scheduler_stopped and not r.suspend_requested and count('cancel_loop')==3 and count('clone')==0)
''',
 'native_overlap_keeps_line_of_sight_and_damage_deduplication': r'''
local r=enable_own();objects['Test.Target']=target
query_actors={'Test.Target'}
query_hits={{target='Test.Wall',point={X=50,Y=0,Z=0},normal={X=-1,Y=0,Z=0},blocking=true,start_penetrating=false}}
r:explode({X=0,Y=0,Z=0},'blocked')
assert(count('native_hit')==0 and target_attributes.Health.CurrentValue==1000)
query_hits={}
r:explode({X=0,Y=0,Z=0},'clear')
assert(count('native_hit')==2 and target_attributes.Health.CurrentValue==990)
r:explode({X=0,Y=0,Z=0},'clear')
assert(count('native_hit')==2 and target_attributes.Health.CurrentValue==990)
local overlaps=0
for _,call in ipairs(calls)do
 if call.name=='native_query'and call.value.phase=='overlap'then
  overlaps=overlaps+1
  assert(call.value.radius==280 and call.value.center.Z==20,'Native bomb overlap did not use the enlarged visual-fit radius')
 end
end
assert(overlaps==3)
''',
 'owned_query_failure_blocks_activation_before_equipment_visuals': r'''
init();choose('RKA_RingedKnight')
RK_NativeQuery=function()return nil,'query schema changed'end
local r=RingedKnightArsenal
assert(not pcall(r.enable,r))
assert(not r.enabled and count('set_mesh')==0 and count('input_add')==0)
''',
 'failed_initialization_stops_supervisor_and_requires_explicit_F8_resume': r'''
init();choose('RKA_RingedKnight')
local r=RingedKnightArsenal
local host,protection=RK_HostCompatible,RK_CombatProtection
local attempts,prepares,messages=0,0,{}
RK_HostCompatible=function()attempts=attempts+1;return host()end
RK_CombatProtection=function(raw)
 local request=assert(json.decode(raw))
 if request.phase=='prepare'then
  prepares=prepares+1
  return nil,'protection original effect class unavailable'
 end
 return protection(raw)
end
print=function(message)messages[#messages+1]=tostring(message)end
loops[250]()
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(r.initialization_error:find('original effect class unavailable',1,true))
assert(attempts==1 and prepares==1 and count('attach')==0 and count('input_add')==0)
local display,prepare,selection=r.item_display.update,r.prepare_inventory,r.inventory.selection
local suspended_work=0
r.item_display.update=function(...)suspended_work=suspended_work+1;return display(...)end
r.prepare_inventory=function(...)suspended_work=suspended_work+1;return prepare(...)end
r.inventory.selection=function(...)suspended_work=suspended_work+1;return selection(...)end
for i=1,12 do loops[250]()end
hooks['/Script/ProjectPBZ.PBZBackPackSubsystem:InitWeaponList']()
choose('Tang');loops[250]();choose('RKA_RingedKnight');loops[250]()
assert(suspended_work==0 and attempts==1 and prepares==1)
assert(not pcall(r.enable,r) and attempts==1)
local failure_logs=0
for _,message in ipairs(messages)do
 if message:find('initialization suspended;',1,true)then failure_logs=failure_logs+1 end
end
assert(failure_logs==1 and not native_weapon.bHidden and r.context==nil and #r.owned==0)
RK_CombatProtection=protection
keybinds[Key.F8]();loops[1]();loops[250]()
assert(r.enabled and not r.development_suspended and not r.initialization_error and not r.inventory_error)
assert(attempts==2 and count('input_add')==1)
choose('Tang');supervise();assert(not r.enabled and not r.development_suspended)
choose('RKA_RingedKnight');supervise();assert(r.enabled and attempts==3)
''',
 'partial_initialization_restores_only_its_input_hidden_actors_and_components': r'''
init();choose('RKA_RingedKnight')
local r=RingedKnightArsenal;local attach=r.attach
local foreign=make_component()
local already_hidden=obj('WeaponActor','Test.AlreadyHiddenWeapon',{bHidden=true,
 SetActorHiddenInGame=function(self,value)self.bHidden=value end})
attached_native={native_weapon,already_hidden}
local own_context
input_subsystem.AddMappingContext=function(_,context)own_context=context;record('input_add',context)end
input_subsystem.RemoveMappingContext=function(_,context)
 assert(context==own_context,'Cleanup removed an unrelated input context')
 record('input_remove',context)
end
r.attach=function(self,...)
 local object=attach(self,...)
 error('mock failure after creating the first owned mesh')
end
loops[250]()
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(count('attach')==1 and count('destroy_component')==1 and not foreign.destroyed)
assert(count('input_add')==1 and count('input_remove')==1 and r.context==nil)
assert(not native_weapon.bHidden and already_hidden.bHidden and #r.hidden==0 and #r.owned==0)
for i=1,8 do loops[250]()end
assert(count('attach')==1 and count('input_add')==1 and count('input_remove')==1)
''',
 'post_enable_side_effect_failure_cleans_idle_and_does_not_auto_reenable': r'''
init();choose('RKA_RingedKnight')
local r=RingedKnightArsenal;local notices=0
r.notify=function(self)
 notices=notices+1
 assert(self.enabled and self.playing and mesh.pp)
 error('mock initialization notification failure')
end
loops[250]()
assert(not r.enabled and not r.playing and not mesh.pp and not native_weapon.bHidden)
assert(r.development_suspended and r.initialization_error and r.context==nil and #r.owned==0)
assert(count('destroy_component')==2 and count('input_add')==1 and count('input_remove')==1)
for i=1,8 do loops[250]();loops[1]()end
assert(notices==1 and count('attach')==2 and count('input_add')==1 and count('input_remove')==1)
''',
 'runtime_animation_failure_aborts_and_quarantines_only_the_action_without_stopping_switching': r'''
local r=enable_own();local context=r.context
native_anim.play_length_override=99
keys_down.LeftMouseButton=true;keys_pressed.LeftMouseButton=true
now=now+.016;loops[1]()
assert(r.enabled and not r.development_suspended and not r.initialization_error and not r.inventory_error)
assert(r.native_reaction and not r.playing and not mesh.pp and r.context==context and #r.owned==2)
assert(native_weapon.bHidden and count('input_add')==1 and count('input_remove')==0)
assert(r.action_error:find('RKSS_Light1',1,true) and r.action_error:find('returned=99',1,true))
assert(r.action_failures.RKSS_Light1)
local plays=count('play')
native_anim.play_length_override=nil
for i=1,12 do now=now+.016;loops[1]()end
assert(count('play')==plays)
keys_down.LeftMouseButton=nil;keys_pressed.LeftMouseButton=nil
now=now+.016;loops[1]()
keys_down.LeftMouseButton=true;keys_pressed.LeftMouseButton=true
now=now+.016;loops[1]()
assert(count('play')==plays and r.native_reaction,'Quarantined action must not retry its native montage')
keys_down.LeftMouseButton=nil;keys_pressed.LeftMouseButton=nil
choose('Tang');supervise()
assert(not r.enabled and not r.development_suspended and not native_weapon.bHidden)
local recovered_pawn,recovered_owner=r.weapon_switch.resolve()
assert(recovered_pawn==pawn and recovered_owner==backpack,'Action fault must not disable native switch recovery')
choose('RKA_RingedKnight');supervise()
assert(r.enabled and not r.development_suspended and r.context~=context)
''',
 'cached_animation_identity_is_checked_against_the_requested_clip': r'''
local r=enable_own()
assert(r:play('RKSS_Light1',false))
local asset=objects['/HuaShira/Mods/RingedKnight/Animations/A_RKSS_Light1.A_RKSS_Light1']
asset.GetFullName=function()return 'AnimSequence Test.WrongCachedAsset'end
local plays=count('play')
local ok,why=pcall(r.play,r,'RKSS_Light1',false)
assert(not ok and why:find('Animation asset identity mismatch',1,true))
assert(why:find('requested=/HuaShira/Mods/RingedKnight/Animations/A_RKSS_Light1.A_RKSS_Light1',1,true))
assert(why:find('actual=AnimSequence Test.WrongCachedAsset',1,true))
assert(count('play')==plays and r.action_failures.RKSS_Light1)
''',
 'failed_action_cleanup_escalates_to_initialization_stop': r'''
local r=enable_own()
r.begin_native_reaction=function()error('mock native action cleanup failure')end
r:abort_action('mock action failure')
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(r.initialization_error:find('action cleanup failed',1,true))
assert(not native_weapon.bHidden and r.context==nil and #r.owned==0)
''',
 'own_localization_is_registered_before_inventory_and_resolves_real_definition_keys': r'''
local path='/Script/ProjectPBZ.PBZBlueprintFunctionLibrary:MakeTextByKey'
local r=RingedKnightArsenal
assert(r.localization_schema.verified and not r.localization_error and type(post_hooks[path])=='function')
assert(count('clone')==0)
init()
local name=weapon_rows.RKA_RingedKnight.WeaponName
assert(name.Namespace=='Default' and name.Key:match('^RKA_TXT_%x%x%x%x%x%x%x%x$'))
local remote=function(value)return {get=function()return value end}end
local native=FText('native original')
local replaced=post_hooks[path](remote({}),remote(native),remote(name.Key))
assert(replaced:type()=='FText' and replaced:ToString()==name.ValueCache:ToString())
assert(post_hooks[path](remote({}),remote(native),remote('OriginalKey'))==nil)
assert(post_hooks[path](remote({}),remote(native),remote('RKA_TXT_DEADBEEF'))==nil)
local saved=post_hooks[path];r:dispose_hooks()
assert(saved(remote({}),remote(native),remote(name.Key))==nil)
''',
 'init_hook_registers_once_and_never_grants_or_edits_originals': r'''
assert(not RingedKnightArsenal.inventory_ready and count('clone')==0)
init();init();supervise();supervise()
assert(count('construct_config')==2 and count('construct_package')==2)
assert(count('config_finalize')==2 and count('clone')==1 and count('soul_clone')==1 and count('sanitize')==1)
assert(count('grant')==0 and count('attach')==0 and not RingedKnightArsenal.enabled)
assert(text(weapon_rows['黑伤'].ItemId)=='Tang' and weapon_rows['黑伤'].Icon.value:find('HeiShang'))
assert(text(soul_rows.heimoshang.ID)=='HeiMoShang')
assert(weapon_rows.RKA_RingedKnight.WeaponMesh[1].value:find('SK_RKA_Display',1,true))
''',
 'one_lifetime_holder_with_exactly_two_tables_precedes_all_native_cloning': r'''
init();init();supervise()
local r=RingedKnightArsenal;local keeper=r.lifetime;local holder=keeper.holder
assert(count('construct_holder')==1 and count('construct_combat_holder')==1)
assert(holder:GetFullName()=='ObjectLibrary /HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.RKA_ItemTables')
assert(holder:GetOuter()==r.equipment.configs.Weapon_RKA_RingedKnight:GetOuter())
assert(holder.bUseWeakReferences==false and #holder.WeakObjects==0 and #holder.Objects==2)
assert(holder.Objects[1]==weapon_data and holder.Objects[2]==soul_data)
local holder_index,second_reference,first_clone
for i,call in ipairs(calls)do
 if call.name=='construct_holder'then holder_index=i end
 if call.name=='strong_reference' and call.value.index==2 and call.value.object==soul_data then second_reference=i end
 if (call.name=='clone' or call.name=='soul_clone') and not first_clone then first_clone=i end
end
assert(holder_index<second_reference and second_reference<first_clone)
local actual=keeper.check;local checks=0
keeper.check=function(self)checks=checks+1;return actual(self)end
r:prepare_inventory();supervise();assert(checks==2)
assert(count('construct_holder')==1 and count('clone')==1 and count('soul_clone')==1)
''',
 'stale_lifetime_holder_prevents_activation_and_recloning': r'''
init();local r=RingedKnightArsenal;r.lifetime.holder.destroyed=true;choose('RKA_RingedKnight')
loops[250]()
assert(r.inventory_error and not r.enabled and count('attach')==0)
assert(count('clone')==1 and count('soul_clone')==1 and count('construct_holder')==1)
''',
 'combat_asset_holder_retains_cached_animations_without_expanding_the_item_table_holder': r'''
local r=enable_own();local holder=r.combat_assets.holder
assert(count('construct_combat_holder')==1 and #r.lifetime.holder.Objects==2)
assert(holder:GetFullName()=='ObjectLibrary /HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight.RKA_CombatAssets')
assert(holder.bUseWeakReferences==false and #holder.WeakObjects==0)
local idle_found=false
for i=1,#holder.Objects do
 if holder.Objects[i]:GetFullName():find('/Animations/A_RKSS_Idle.A_RKSS_Idle',1,true)then idle_found=true end
end
assert(idle_found,'Loaded idle animation must be held through a real engine ObjectProperty')
assert(r:play('RKSS_Light1',false))
local references=#holder.Objects;local writes=count('strong_reference')
for i=1,12 do assert(r:play('RKSS_Light1',false))end
r:prepare_inventory()
assert(#holder.Objects==references and count('strong_reference')==writes and #r.lifetime.holder.Objects==2)
assert(r.combat_assets:check().asset_count==references)
''',
 'stale_combat_asset_holder_stops_supervisor_without_native_reinitialization': r'''
local r=enable_own();r.combat_assets.holder.destroyed=true
loops[250]()
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(r.initialization_error:find('Combat asset lifetime holder unavailable',1,true))
assert(r.context==nil and #r.owned==0 and not native_weapon.bHidden)
local roots=count('construct_combat_holder');local clones=count('clone')
for i=1,12 do loops[250]()end
assert(count('construct_combat_holder')==roots and count('clone')==clones)
''',
 'ordinary_tick_failure_aborts_owned_action_and_keeps_native_switch_supervision': r'''
local r=enable_own();assert(r:play('RKSS_Light1',false))
local montage=r.animation_blend.montage;local context=r.context
local tick=r.tick
r.tick=function()error('mock one-frame action callback failure')end
now=now+.016;loops[1]();r.tick=tick
assert(r.enabled and not r.development_suspended and r.native_reaction and r.context==context)
assert(montage.fade_out==0 and not mesh.pp and not pc.move_lock and not r.state.clip)
choose('Tang');supervise();assert(not r.enabled and not r.development_suspended)
choose('RKA_RingedKnight');supervise();assert(r.enabled)
''',
 'cleanup_failure_still_stops_owned_montage_when_protection_release_throws': r'''
local r=enable_own();assert(r:play('RKSS_EmberStart',false))
local montage=r.animation_blend.montage;local protection=RK_CombatProtection
RK_CombatProtection=function(raw)
 local request=assert(json.decode(raw))
 if request.active==false then return nil,'mock protection release failure'end
 return protection(raw)
end
r:abort_action('mock interrupted action')
assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(montage.fade_out==0 and not mesh.pp and not pc.move_lock and r.context==nil)
assert(not native_weapon.bHidden and #r.owned==0)
''',
 'lifetime_holder_failure_disables_already_active_combat': r'''
local r=enable_own();r.lifetime.holder.destroyed=true
loops[250]()
assert(r.inventory_error and not r.enabled,'Lifetime failure must disable already active combat')
assert(r.context==nil and #r.owned==0 and not native_weapon.bHidden)
''',
 'replacement_lifetime_table_disables_already_active_combat': r'''
local r=enable_own();local old=r.lifetime.holder.Objects[1]
r.lifetime.holder.Objects[1]=obj('DataTable',old.path)
loops[250]()
assert(r.inventory_error and not r.enabled,'Lifetime table replacement must disable already active combat')
assert(r.context==nil and #r.owned==0 and count('clone')==1 and count('soul_clone')==1)
''',
 'original_weapon_cannot_activate_custom_combat': r'''
init();local r=RingedKnightArsenal
local ok,why=pcall(r.enable,r);assert(not ok and tostring(why):find('Select the independent',1,true))
loops[250]();assert(not r.enabled and r.development_suspended and r.initialization_error)
assert(count('attach')==0 and count('input_add')==0)
assert(text(backpack.CurrentMainWeaponID)=='Tang' and count('grant')==0)
''',
 'preexisting_owned_config_objects_reuse_real_outer_without_bare_lookup': r'''
local adapter=RingedKnightArsenal.equipment;adapter:prepare()
assert(count('construct_package')==2 and count('construct_config')==2)
local Equipment=dofile(script_dir..'EquipmentAdapter.lua')
local reused=Equipment.new(function(path)return objects[path]end,RingedKnightArsenal.registry,function(req)
 return assert(json.decode(RK_NativeInventory(json.encode(req))))
end)
reused:prepare()
assert(count('construct_package')==2 and count('construct_config')==2)
for name,config in pairs(reused.configs)do assert(reused.packages[name]==config:GetOuter())end
''',
 'F8_only_suspends_and_cannot_skin_or_select_an_original': r'''
local r=RingedKnightArsenal
game_thread=false;keybinds[Key.F8]()
assert(r.suspend_requested and not r.development_suspended and not r.enabled and count('one_shot_game_thread')==0)
loops[1]();assert(r.development_suspended and not r.enabled and not IsInGameThread())
supervise();keybinds[Key.F8]();loops[1]();supervise()
assert(not r.development_suspended and not r.enabled)
assert(count('attach')==0 and count('input_add')==0 and count('grant')==0)
assert(text(backpack.CurrentMainWeaponID)=='Tang' and backpack.ids[1]=='Tang')
''',
 'own_ID_selection_activates_once_without_F8_or_slot_replacement': r'''
local r=enable_own();supervise();supervise()
assert(r.active_item=='RKA_RingedKnight' and count('attach')==2 and count('input_add')==1)
assert(r.active_config==r.equipment.configs.Weapon_RKA_RingedKnight)
assert(backpack.ids[1]=='RKA_RingedKnight' and backpack.ids[2]=='Other' and count('grant')==0)
assert(native_weapon.bHidden and mesh.pp and r.animation_blend.montage.paused)
''',
 'pause_suspends_combat_preserves_own_display_and_resumes_without_respawn': r'''
local r=enable_own();r.state:enter('RKSS_Light1');r:play('RKSS_Light1',false);r:flame(.4)
local projectile=obj('Actor','Test.Projectile',{K2_DestroyActor=function(self)self.destroyed=true;record('destroy_projectile',true)end})
r.projectiles[1]={actor=projectile};assert(pc.move_lock and #r.effects==1)
paused=true;loops[1]();supervise()
assert(r.enabled and r.menu_suspended and not mesh.pp and not pc.move_lock)
assert(#r.owned==2 and #r.effects==1 and #r.projectiles==1 and #r.hidden==1 and r.context==nil)
assert(native_weapon.bHidden and count('input_remove')==1 and count('destroy_component')==0)
assert(count('destroy_projectile')==0 and count('destroy_effect')==0 and not r.state.clip)
assert(count('native_hit')==0)
paused=false;supervise();assert(r.enabled and not r.menu_suspended and count('attach')==2 and count('input_add')==2)
choose('Tang');supervise()
assert(not r.enabled and #r.effects==0 and #r.projectiles==0 and not native_weapon.bHidden)
assert(count('destroy_projectile')==1 and count('destroy_effect')==1)
''',
 'switch_to_original_cleans_and_stays_off_without_touching_slots': r'''
local r=enable_own();choose('Tang');supervise();supervise()
assert(not r.enabled and not native_weapon.bHidden and not mesh.pp)
assert(count('input_remove')==1 and count('destroy_component')==2)
assert(backpack.ids[1]=='Tang' and backpack.ids[2]=='Other' and count('grant')==0)
''',
 'tick_detects_native_ID_change_before_next_supervisor_or_contact': r'''
local r=enable_own();r.state:enter('RKSS_Light1');r:play('RKSS_Light1',false)
local plays=count('play');choose('Tang');r:tick(1/60)
assert(not r.enabled and count('play')==plays and count('native_hit')==0)
assert(#r.owned==0 and not native_weapon.bHidden and not mesh.pp and not pc.move_lock)
''',
 'router_Menu_blocks_initial_activation_while_Game_and_All_allow_it': r'''
init();choose('RKA_RingedKnight');input_mode=0;supervise()
local r=RingedKnightArsenal;assert(not paused and not pc.bShowMouseCursor)
assert(not r.enabled and count('attach')==0 and count('input_add')==0)
input_mode=1;supervise();assert(r.enabled and count('attach')==2)
input_mode=0;r:tick(1/60)
assert(r.enabled and r.menu_suspended and r.context==nil and not mesh.pp and native_weapon.bHidden)
local ticks=r.ticks;loops[250]();assert(r.menu_suspended and r.ticks==ticks)
input_mode=2;supervise();assert(r.enabled and not r.menu_suspended and r.context and count('attach')==2)
''',
 'foreign_player_and_class_default_menu_routers_are_ignored': r'''
local foreign=obj('LocalPlayer','Test.OtherPlayer')
local other=obj('PBZUIActionRouterBase','Test.OtherRouter',{
 GetOuter=function()return foreign end,GetActiveInputMode=function()return 0 end})
local cdo=obj('PBZUIActionRouterBase','Test.Default__UIRouter',{
 GetOuter=function()return pc.Player end,GetActiveInputMode=function()return 0 end})
ui_routers={other,cdo,ui_router};input_mode=1
local r=enable_own();assert(not r.menu_suspended and count('attach')==2)
''',
 'native_slot_hiding_does_not_claim_already_hidden_or_other_slot_actors': r'''
local r=enable_own();supervise();supervise();assert(#r.hidden==1)
local already_hidden=obj('WeaponActor','Test.NativeWeapon2',{bHidden=true,
 SetActorHiddenInGame=function(self,v)self.bHidden=v end})
rka_native_actors[2]=already_hidden;supervise();supervise()
assert(#r.hidden==1 and native_weapon.bHidden and already_hidden.bHidden)
assert(not other_native_weapon.bHidden and other_native_weapon.writes==0)
choose('Tang');supervise()
assert(not native_weapon.bHidden and already_hidden.bHidden and #r.hidden==0)
''',
 'actual_two_slot_switch_keeps_original_in_hand_and_only_custom_sword_on_back': r'''
local r=enable_own();local hand_sword,hand_shield=r.sword,r.shield
backpack.index=1;backpack.CurrentMainWeaponID=FName('Other');supervise()
assert(not r.enabled and not r.development_suspended)
assert(hand_sword.destroyed and hand_shield.destroyed and r.context==nil and not mesh.pp)
local back=r.equipment_visuals.back
assert(back and back.visible and back.asset.path:find('SM_RingedKnightStraightSword',1,true))
assert(back.parent==mesh and back.bone=='spine_03')
local q=back.transform.Rotation
assert(math.abs(q.X*q.X+q.Y*q.Y+q.Z*q.Z+q.W*q.W-1)<1e-6)
assert(native_weapon.bHidden and not other_native_weapon.bHidden and other_native_weapon.writes==0)
local count_before=count('attach');supervise();supervise();assert(count('attach')==count_before)
backpack.index=0;backpack.CurrentMainWeaponID=FName('RKA_RingedKnight');supervise()
assert(r.enabled and back.destroyed and not r.equipment_visuals.back)
assert(not other_native_weapon.bHidden and other_native_weapon.writes==0 and native_weapon.bHidden)
''',
 'unequipping_inactive_custom_slot_removes_back_and_restores_its_proxy_only': r'''
local r=enable_own();backpack.index=1;backpack.CurrentMainWeaponID=FName('Other');supervise()
local back=r.equipment_visuals.back;assert(back and native_weapon.bHidden)
backpack.ids[1]='Tang';supervise()
assert(back.destroyed and not r.equipment_visuals.back and not native_weapon.bHidden)
assert(not other_native_weapon.bHidden and other_native_weapon.writes==0)
''',
 'passive_back_sword_is_removed_when_pawn_unloads_or_runtime_is_disposed': r'''
local r=enable_own();backpack.index=1;backpack.CurrentMainWeaponID=FName('Other');supervise()
local first=r.equipment_visuals.back;pawn.destroyed=true;supervise()
assert(first.destroyed and not r.equipment_visuals.back and not native_weapon.bHidden)
pawn.destroyed=false;supervise();local second=r.equipment_visuals.back;assert(second)
r:dispose_hooks();assert(second.destroyed and not r.equipment_visuals.back and not native_weapon.bHidden)
''',
 'F8_suspension_also_cleans_passive_back_sword_after_switching_to_original': r'''
local r=enable_own();backpack.index=1;backpack.CurrentMainWeaponID=FName('Other');supervise()
local back=r.equipment_visuals.back;assert(back and not r.enabled and native_weapon.bHidden)
keybinds[Key.F8]();loops[1]();supervise()
assert(r.development_suspended and back.destroyed and not r.equipment_visuals.back and not native_weapon.bHidden)
assert(not other_native_weapon.bHidden and other_native_weapon.writes==0)
''',
 'F8_suspend_does_not_reenable_selected_item_until_released': r'''
local r=enable_own();keybinds[Key.F8]();assert(r.enabled and r.suspend_requested)
loops[1]();supervise()
assert(r.development_suspended and not r.enabled and count('input_remove')==1)
keybinds[Key.F8]();loops[1]();supervise();assert(not r.development_suspended and r.enabled)
assert(count('attach')==4 and text(backpack.CurrentMainWeaponID)=='RKA_RingedKnight')
''',
 'physical_and_fire_both_use_live_native_upgrade_out_parameter_once': r'''
local r=enable_own();backpack.saved_level=16;backpack.saved_strength=2.5
local hit={ImpactPoint={X=100,Y=0,Z=0},ImpactNormal={X=0,Y=0,Z=1}}
r:damage(target,hit,'first',105,10,'sword')
assert(r.last_hit.physical==262.5 and r.last_hit.fire==25)
assert(r.upgrade_status.level==16 and r.upgrade_status.max_level==30 and r.upgrade_status.multiplier==2.5)
local req=last('native_hit');assert(req.phase=='feedback' and req.coefficient==262.5/200 and req.fire==25/200)
assert(count('strength_query')==1 and count('native_hit')==2)
r:damage(target,hit,'first',105,10,'sword');assert(count('strength_query')==1 and count('native_hit')==2)
backpack.saved_level=20;backpack.saved_strength=2.9;r:damage(target,hit,'second',105,10,'sword')
assert(math.abs(r.last_hit.physical-304.5)<1e-8 and r.last_hit.fire==29 and count('strength_query')==2)
assert(pawn.AttributeSetBase.Attack.CurrentValue==200)
''',
 'first_light_applies_its_damage_and_poise_once_on_the_real_hit_path': r'''
local r=enable_own();backpack.saved_level=2;backpack.saved_strength=1.1
objects['Test.Target']=target
r.audio.play=function(_,role) if role:match('^hit_') then record('flesh_sound',role) end end
local function strike(name)
    r.state:enter(name);assert(r:play(name,false))
    r.state.time=r.state.profile.clips[name].hits[1].start-.001
    r:tick(.016)
end
strike('RKSS_Light1')
assert(count('flesh_sound')==0 and count('native_hit')==0)
r.state:cancel() -- Begin a separate burst after the whiff-only audio check.
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
strike('RKSS_Light1')
local first=assert(last('native_hit'))
strike('RKSS_Light2')
local second=assert(last('native_hit'))
assert(count('flesh_sound')==2 and last('flesh_sound')=='hit_heavy')
assert(math.abs(first.coefficient-363*1.1/200)<1e-8 and math.abs(first.fire-34.5*1.1/200)<1e-8)
assert(math.abs(second.coefficient-242*1.1/200)<1e-8 and math.abs(second.fire-23*1.1/200)<1e-8)
assert(first.poise==900 and second.poise==100)
assert(first.anger==4.59 and second.anger==4.59 and first.hit_anger_multiplier==.05)
assert(count('strength_query')==2 and count('native_hit')==4)
''',
 'soul_selection_uses_own_soul_config_for_native_upgrade_query': r'''
backpack.souled=true;local r=enable_own();backpack.saved_level=5;backpack.saved_strength=1.4
assert(r.active_config==r.equipment.configs.Weapon_RKA_RingedKnight_Soul)
r:damage(target,{ImpactPoint={X=100,Y=0,Z=0},ImpactNormal={X=0,Y=0,Z=1}},'soul',100,20,'sword')
assert(last('strength_query')==r.active_config.path)
assert(r.last_hit.physical==140 and r.last_hit.fire==28)
''',
 'heavy_damage_and_poise_upgrade_once_at_original_contacts_with_native_resource_values': r'''
local r=enable_own();backpack.saved_level=5;backpack.saved_strength=1.4
objects['Test.Target']=target
query_hits={{target='Test.Target',point={X=100,Y=0,Z=0},normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
-- Hold Triangle for the legacy charged variants without introducing a fresh
-- input edge/queued attack; this regression exercises real state contact events.
r.keys=function()return {triangle=true}end
local cases={
 {'RKSS_Heavy1Release',574.266,54.579,900,.3,.4,2.0666653315226235,5.13},
 {'RKSS_Heavy1Charge',813.12,77.28,900,1.2,1.3,2.9666646321614585,5.13},
 {'RKSS_Heavy2Release',382.844,36.386,150,.26666668,.36666667,1.7999989191691081,7.695},
 {'RKSS_Heavy2Charge',542.08,51.52,150,1.5,1.6,3.366664250691732,7.695},
}
for index,case in ipairs(cases)do
 local name,physical,fire,poise,start,finish,duration,anger=table.unpack(case)
 assert(r.state:enter(name,true));assert(r:play(name,false))
 local clip=r.state.profile.clips[name];local hit=clip.hits[1]
 assert(#clip.hits==1 and math.abs(hit.start-start)<1e-8 and math.abs(hit.finish-finish)<1e-8)
 assert(math.abs(clip.duration-duration)<1e-8 and math.abs(hit.anger-anger)<1e-8 and hit.hit_anger_multiplier==1)
 r.state.time=start-.01;r:tick(.005)
 assert(count('native_hit')==(index-1)*2 and count('strength_query')==index-1,'Heavy hit fired before its original contact')
 r:tick(.01)
 local receipt=assert(last('native_hit'))
 assert(math.abs(receipt.coefficient-physical*1.4/200)<1e-8)
 assert(math.abs(receipt.fire-fire*1.4/200)<1e-8 and receipt.poise==poise)
 assert(math.abs(receipt.anger-anger)<1e-8 and receipt.hit_anger_multiplier==1)
 r:tick(.005) -- Same target, same contact and both capsules must not rescale/replay.
 assert(count('native_hit')==index*2 and count('strength_query')==index)
end
assert(r.hits==4 and target_attributes.Health.CurrentValue==960)
assert(r.enabled and not r.action_error and not r.development_suspended)
''',
 'art_native_capability_mismatch_stops_before_input_or_mesh_mutations': r'''
local cases={
 {api=0,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1},
 {api=1,resource='UltimateCharge',amount=1,once_per_action=true,session_token=1},
 {api=1,resource='UltimateChargeCount',amount=2,once_per_action=true,session_token=1},
 {api=1,resource='UltimateChargeCount',amount=1,once_per_action=false,session_token=1},
 {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=0},
}
init();choose('RKA_RingedKnight');local r=RingedKnightArsenal
for _,bad in ipairs(cases)do
 art_cost_capabilities=bad;r.development_suspended=false
 local ok=pcall(r.enable,r)
 assert(not ok and not r.enabled and count('attach')==0 and count('input_add')==0 and count('native_hidden')==0)
end
''',
 'user_requested_free_art_testing_does_not_debit_or_require_native_ultimate_stock': r'''
local r=enable_own();assert(r.art_test_free==true)
r.flame=function()return obj('NiagaraComponent',nil,{Deactivate=function()end,K2_DestroyComponent=function()end})end
r.keys=function()return art_input or {}end
r.hit_window=function(_,event)record('art_contact',event.hit.attack_id)end
art_balance=0
for _,branch in ipairs({'light','heavy'})do
 art_input={art_pressed=branch=='light',guard=branch=='heavy',circle_pressed=branch=='heavy'}
 r:tick(1/120)
 assert(r.state.clip==r.state.profile.art.start and art_balance==0)
 assert(r.last_art_cost.status=='testing_free'and r.last_art_cost.amount==0)
 local before=count('art_contact');art_input={}
 for _=1,1600 do r:tick(1/120);if not r.state.clip then break end end
 assert(not r.state.clip and count('art_contact')>before)
 assert(count('art_cost_attempt')==0 and count('art_cost_paid')==0 and art_balance==0)
end
''',
 'full_art_branches_debit_one_native_ultimate_charge_and_unfunded_cast_can_retry': r'''
local r=enable_own();r.art_test_free=false
r.flame=function()return obj('NiagaraComponent',nil,{Deactivate=function()end,K2_DestroyComponent=function()end})end
r.keys=function()return art_input or {}end
r.hit_window=function(_,event)record('art_contact',event.hit.attack_id)end
for index,branch in ipairs({'light','heavy'})do
 art_balance=1
 art_input={art_pressed=branch=='light',guard=branch=='heavy',circle_pressed=branch=='heavy'}
 r:tick(1/120)
 assert(r.state.clip==r.state.profile.art.start and art_balance==0 and count('art_cost_paid')==index)
 local before=count('art_contact');art_input={}
 for _=1,1600 do r:tick(1/120);if not r.state.clip then break end end
 assert(not r.state.clip and count('art_contact')>before and count('art_cost_paid')==index)
end
local contacts=count('art_contact');art_input={art_pressed=true};r:tick(1/120)
assert(not r.state.clip and art_balance==0 and count('art_cost_paid')==2 and count('art_contact')==contacts)
local denied_sequence=r.last_art_cost.sequence
art_balance=1;r:tick(1/120)
assert(r.state.clip==r.state.profile.art.start and r.last_art_cost.sequence==denied_sequence and art_balance==0 and count('art_cost_paid')==3)
r:release_combat_pose();art_input={attack_pressed=true};r:tick(1/120)
assert(r.state.clip=='RKSS_Light1'and count('art_cost_paid')==3)
''',
 'art_flame_extension_uses_baked_mesh_sweeps_not_stale_sword_and_deduplicates_contacts': r'''
local r=enable_own();objects['Test.Target']=target
local geometry=dofile(script_dir..'ArtFlameTrace.lua')
local math_library=StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
local mesh_basis={Rotation={X=0,Y=0,Z=math.sqrt(.5),W=math.sqrt(.5)},
 Translation={X=1000,Y=50,Z=20},Scale3D={X=1,Y=1,Z=1}}
local function world(v)return {X=1000-v.Y,Y=50+v.X,Z=20+v.Z}end
math_library.TransformLocation=function(_,basis,v)
 assert(basis==mesh_basis,'Expected current character mesh basis')
 return world(v)
end
r.mesh.K2_GetComponentToWorld=function()return mesh_basis end
r.sword.K2_GetComponentToWorld=function()
 error('Attached sword transform is stale and must not be read for hit detection')
end
local expected,expected_point,expected_art
local art_queries,normal_queries=0,0
local function expect_sweep(event,is_art)
 local p=r.state.profile;local clip=p.clips[r.state.clip]
 assert(clip.blade_tracks and #clip.blade_tracks.base==clip.frames)
 local volume=geometry.scaled_segment(is_art and p.art.hit_volume or {
  space='sword_local_cm',base=p.art.hit_volume.base,steel_tip=p.art.hit_volume.steel_tip,
  tip_extension_cm=0,radius_cm=p.air_blade.radius_cm},
  is_art and p.air_blade.art_reach_scale or p.air_blade.normal_reach_scale)
 local a,b=volume.start,volume.finish
 local length=math.sqrt((b.X-a.X)^2+(b.Y-a.Y)^2+(b.Z-a.Z)^2)
 local segments=assert(geometry.swept_segments(clip,event.from_time or event.time,event.time,length,volume.radius_cm,64))
 expected={};expected_art=is_art
 for _,segment in ipairs(segments)do
  expected[#expected+1]={start=world(segment.start),finish=world(segment.finish),radius=segment.radius_cm}
 end
 -- Return a contact near the extended tip, well beyond the physical steel.
 local first=expected[1]
 expected_point={X=first.start.X+.85*(first.finish.X-first.start.X),
  Y=first.start.Y+.85*(first.finish.Y-first.start.Y),Z=first.start.Z+.85*(first.finish.Z-first.start.Z)}
 return length
end
local original_query=RK_NativeQuery;local overlap=false
RK_NativeQuery=function(raw)
 local q=assert(json.decode(raw))
 if q.phase=='trace'then
  query_hits=overlap and {{target='Test.Target',point=expected_point,normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}or {}
 elseif q.phase=='trace_batch'then
  assert(expected and #q.segments==#expected,'Baked sweep batch size mismatch')
  for i,segment in ipairs(q.segments)do
   for _,field in ipairs({'start','finish'})do
    for _,axis in ipairs({'X','Y','Z'})do
     assert(math.abs(segment[field][axis]-expected[i][field][axis])<1e-7,
      'Native batch does not match baked blade track in current mesh basis: '..field..'.'..axis)
    end
   end
   assert(math.abs(segment.radius-expected[i].radius)<1e-8,'Swept capsule radius mismatch')
  end
  if expected_art then art_queries=art_queries+1 else normal_queries=normal_queries+1 end
  query_hits={{target='Test.Target',point=expected_point,normal={X=0,Y=0,Z=1},blocking=true,start_penetrating=false}}
 end
 return original_query(raw)
end
assert(r.state:enter('RKSS_Ember',true));assert(r:play(r.state.clip,false))
local hits=r.state.profile.clips.RKSS_Ember.hits
local first={hit=hits[1],from_time=hits[1].start,time=hits[1].start+.02,serial=r.state.serial,index=1}
local art_reach=expect_sweep(first,true)
r:hit_window(first)
assert(r.hits==1 and count('native_hit')==2 and art_queries==1,'Flame-only batch contact failed')
local receipt=last('native_hit')
assert(math.abs(receipt.coefficient-hits[1].physical/200)<1e-8 and receipt.anger==hits[1].anger)
overlap=true;r:hit_window(first)
assert(r.hits==1 and count('native_hit')==2,'Steel/flame overlap or later frame duplicated damage')
local second={hit=hits[2],time=hits[2].start,serial=r.state.serial,index=2}
expect_sweep(second,true);r:hit_window(second)
assert(r.hits==2 and count('native_hit')==4,'Next art contact was incorrectly deduplicated')
local before=art_queries
assert(r.state:enter('RKSS_Light1',true))
local ordinary={hit=r.state.profile.clips.RKSS_Light1.hits[1],time=.5,serial=r.state.serial,index=1}
local normal_reach=expect_sweep(ordinary,false);r:hit_window(ordinary)
assert(normal_reach<art_reach and art_queries==before and normal_queries==1,'Ordinary swing did not use its own shorter air-blade volume')
''',
 'soul_state_change_refreshes_config_without_respawning_equipment': r'''
local r=enable_own();assert(r.active_config==r.equipment.configs.Weapon_RKA_RingedKnight)
backpack.souled=true;supervise()
assert(r.active_config==r.equipment.configs.Weapon_RKA_RingedKnight_Soul and count('attach')==2 and count('input_add')==1)
backpack.souled=false;supervise();assert(r.active_config==r.equipment.configs.Weapon_RKA_RingedKnight)
''',
 'invalid_native_upgrade_snapshot_cannot_dispatch_unscaled_damage': r'''
local r=enable_own();backpack.saved_level=0
local ok=pcall(r.damage,r,target,{ImpactPoint={X=100,Y=0,Z=0},ImpactNormal={X=0,Y=0,Z=1}},'bad-level',105,10,'sword')
assert(not ok and count('native_hit')==0 and count('strength_query')==0 and target_attributes.Health.CurrentValue==1000)
''',
 'actual_first_light_guard_cancel_keeps_flame_cosmetic_at_upgraded_level': r'''
local r=enable_own();backpack.saved_level=30;backpack.saved_strength=3.9
r.state:enter('RKSS_Light1');r:play('RKSS_Light1',false)
r.state.time=r.state.contact_end.RKSS_Light1
keys_down.RightMouseButton=true;keys_pressed.RightMouseButton=true
r:tick(.001)
assert(r.cancels==1 and r.state:is_guarding() and count('flame')==1)
assert(count('native_hit')==0 and count('strength_query')==0 and #r.effects==1)
assert(target_attributes.Health.CurrentValue==1000)
''',
 'incompatible_bridge_fails_closed_before_config_row_or_visual_mutation': r'''
compatible=false;hooks['/Script/ProjectPBZ.PBZBackPackSubsystem:InitWeaponList']()
local r=RingedKnightArsenal
assert(not r.inventory_ready and r.inventory_error and not r.enabled)
assert(count('construct_config')==0 and count('clone')==0 and count('attach')==0 and count('grant')==0)
''',
}


def new_runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.script_dir = SCRIPTS.as_posix() + '/'
    g.animation_lengths = lua.table_from(animation_lengths)
    # Decode this unchanged 1.5 MB fixture once; each case still owns an
    # independent Lua table and all non-profile JSON uses the real decoder.
    g.fixture_profile_text = profile_text
    g.fixture_profile = lua.table_from(profile, recursive=True)
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
    lua.execute(SETUP)

    def convert(value, field=''):
        if isinstance(value, dict):
            if field == 'WeaponMesh':
                return g.array(lua.table_from([g.soft(value['AssetPathName'])]))
            if 'AssetPathName' in value:
                return g.soft(value['AssetPathName'])
            if 'ValueCache' in value:
                cache = value['ValueCache']
                return g.struct(lua.table_from({'Namespace': value.get('Namespace', ''), 'Key': value.get('Key', ''),
                    'ValueCache': g.FText(cache.get('LocalizedString') or cache.get('SourceString') or value.get('Key', ''))}))
            return g.struct(lua.table_from({k: convert(v, k) for k, v in value.items()}))
        if isinstance(value, list):
            if field in ('DefaultWeaponMediaDatas', 'Materials'):
                return g.map(lua.table_from([lua.table_from({'Key': e['Key'], 'Value': convert(e['Value'])}) for e in value]))
            return g.array(lua.table_from([convert(v) for v in value]))
        return value

    g.weapon_factory = lambda: convert(weapon_native)
    g.soul_factory = lambda: convert(soul_native['heimoshang'])
    other = convert(weapon_native)
    other.ItemId = g.FName('Other')
    g.weapon_rows = lua.table_from({'黑伤': convert(weapon_native), 'Other': other})
    g.soul_rows = lua.table_from({k: convert(v) for k, v in soul_native.items()})
    lua.execute(BRIDGE)
    lua.execute("game_thread=false;dofile(script_dir..'main.lua');game_thread=true")
    return lua


results = []
main_start_sha256 = hashlib.sha256((SCRIPTS / 'main.lua').read_bytes()).hexdigest()
for name, case in CASES.items():
    print('RUN', name, flush=True)
    try:
        runtime = new_runtime()
        runtime.execute(case)
        results.append({'name': name, 'pass': True})
        print('PASS', name)
    except Exception as error:
        results.append({'name': name, 'pass': False, 'error': str(error)})
        print('FAIL', name, error)

main_end_sha256 = hashlib.sha256((SCRIPTS / 'main.lua').read_bytes()).hexdigest()
(ROOT / 'reports/offline-equipment-runtime-tests.json').write_text(json.dumps({
    'scope': 'Real main.lua + Definition/Equipment/Inventory/Upgrade modules under Lua 5.4; mocked UE/native bridge only.',
    'native_runtime_verified': False,
    'main_sha256': main_start_sha256,
    'main_end_sha256': main_end_sha256,
    'main_unchanged_during_run': main_start_sha256 == main_end_sha256,
    'combat_profile_sha256': hashlib.sha256((SCRIPTS / 'combat-profile.json').read_bytes()).hexdigest(),
    'module_sha256': {name: hashlib.sha256((SCRIPTS / name).read_bytes()).hexdigest()
        for name in ['main.lua', 'LifetimeKeeper.lua', 'CombatAssets.lua', 'EquipmentVisuals.lua', 'ItemDisplayAdapter.lua', 'LocalizationAdapter.lua', 'EquipmentAdapter.lua', 'NativeInventory.lua',
                     'RingedKnightDefinition.lua', 'UpgradeAdapter.lua', 'CombatState.lua', 'AnimationBlend.lua', 'WeaponAudio.lua',
                     'RingedKnightAudio.lua', 'BladeFlame.lua', 'BombLanding.lua', 'WeaponSwitch.lua']},
    'fixture_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [weapon_source, soul_source]},
    'cases': results,
}, ensure_ascii=False, indent=2), encoding='utf-8')
raise SystemExit(any(not case['pass'] for case in results) or main_start_sha256 != main_end_sha256)
