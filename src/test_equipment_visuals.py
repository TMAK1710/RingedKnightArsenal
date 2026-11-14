"""Native slot-owned hiding and independent back sword lifecycle under mocks."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/runtime/RingedKnightArsenal/Scripts/EquipmentVisuals.lua'
ADAPTER_SOURCE = SOURCE.with_name('EquipmentAdapter.lua')
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

SETUP = r'''
serial=0;thread=true;created={};loads={}
function obj(fields)
 serial=serial+1;local address=serial;fields=fields or {}
 fields.IsValid=function(self)return not self.destroyed end
 fields.GetAddress=function()return address end
 return fields
end
function actor(hidden)
 return obj({bHidden=hidden,writes=0,IsA=function(_,class)return class.path=='/Script/Engine.Actor'end,
 SetActorHiddenInGame=function(self,value)self.bHidden=value;self.writes=self.writes+1 end})
end
function FName(value)return value end
function IsInGameThread()return thread end
function StaticFindObject(path)
 assert(path=='/Script/Engine.StaticMeshComponent'or path=='/Script/Engine.Actor'or path=='/Script/Engine.SceneComponent')
 return obj({path=path})
end
world=obj();mesh=obj();owner=obj()
function pawn_object()
 return obj({Mesh=mesh,GetWorld=function()return world end,
 AddComponentByClass=function()
  local component=obj({SetStaticMesh=function(self,asset)self.asset=asset;return not fail_mesh end,
   SetCollisionEnabled=function(_,value)assert(value==0)end,
   K2_AttachToComponent=function(self,parent,bone)self.parent=parent;self.bone=bone end,
   K2_SetRelativeTransform=function(self,value)self.transform=value end,
   SetVisibility=function(self,value)self.visible=value end,
   K2_DestroyComponent=function(self)self.destroyed=true end})
  created[#created+1]=component;return component
 end})
end
pawn=pawn_object();proxy=actor(false);stock=actor(false)
display={current=0,slots={{index=0,id='RKA',actors={proxy}},{index=1,id='Tang',actors={stock}}}}
equipment={display_slots=function(_,p,o)assert(p==pawn and o==owner);return display end}
registry={get=function(_,id)return id=='RKA' end}
mount={bone='spine_03',t={1,-20,3},q={0,0,0,1}}
function make()
 return Visuals.new(function(path)loads[#loads+1]=path;return obj({path=path})end,
 equipment,registry,'/Mod/SM_Sword.SM_Sword',mount)
end
v=make()
'''

CASES = {
    'active_custom_slot_hides_only_its_proxy_and_keeps_other_weapon_untouched': r'''
v:update(pawn,owner,true)
assert(proxy.bHidden and not stock.bHidden and stock.writes==0 and #v.hidden==1 and #created==0)
''',
    'holstered_active_custom_slot_has_one_back_sword_with_its_native_proxy_hidden': r'''
v:update(pawn,owner,false,true)
assert(proxy.bHidden and not stock.bHidden and stock.writes==0 and #v.hidden==1 and #created==1)
assert(v.back.asset.path=='/Mod/SM_Sword.SM_Sword'and v.back.parent==mesh and v.back.bone=='spine_03')
assert(v.back.visible and #loads==1)
for i=1,12 do v:update(pawn,owner,false,true)end
assert(#created==1 and #loads==1 and proxy.bHidden)
''',
    'native_show_while_active_custom_slot_is_holstered_only_rehides_its_proxy': r'''
v:update(pawn,owner,false,true);local back=v.back
proxy.bHidden=false;v:update(pawn,owner,false,true)
assert(proxy.bHidden and #v.hidden==1 and v.back==back and not back.destroyed)
assert(not stock.bHidden and stock.writes==0 and #created==1)
''',
    'drawing_active_custom_slot_clears_back_sword_and_keeps_native_proxy_hidden': r'''
v:update(pawn,owner,false,true);local back=v.back
v:update(pawn,owner,true,false)
assert(back.destroyed and not v.back and proxy.bHidden and #v.hidden==1)
assert(not stock.bHidden and stock.writes==0 and #created==1)
''',
    'active_holstered_flag_does_not_replace_or_hide_original_weapon_slots': r'''
display.slots={{index=0,id='Tang',actors={stock}},{index=1,id='Other',actors={proxy}}}
v:update(pawn,owner,false,true)
assert(not stock.bHidden and stock.writes==0 and not proxy.bHidden and proxy.writes==0)
assert(not v.back and #v.hidden==0 and #created==0 and #loads==0)
''',
    'native_pre_hidden_actor_is_not_owned_or_restored_by_the_mod': r'''
proxy.bHidden=true;stock.bHidden=true;v:update(pawn,owner,true);v:clear()
assert(proxy.bHidden and stock.bHidden and proxy.writes==0 and stock.writes==0 and #v.hidden==0)
''',
    'native_switch_unhides_the_previous_back_weapon_without_an_old_snapshot_rehiding_it': r'''
stock.bHidden=true;v:update(pawn,owner,true)
stock.bHidden=false;display.current=1;v:update(pawn,owner,false)
assert(not stock.bHidden and stock.writes==0 and proxy.bHidden and v.back)
v:clear();assert(not stock.bHidden and stock.writes==0)
''',
    'inactive_custom_slot_has_one_spine_attached_sword_and_no_shield': r'''
display.current=1;v:update(pawn,owner,false)
assert(proxy.bHidden and not stock.bHidden and stock.writes==0 and #created==1)
assert(v.back.asset.path=='/Mod/SM_Sword.SM_Sword'and v.back.parent==mesh and v.back.bone=='spine_03')
assert(v.back.transform.Translation.Y==-20 and v.back.visible and #loads==1)
for i=1,12 do v:update(pawn,owner,false)end
assert(#created==1 and #loads==1)
''',
    'switch_back_removes_back_sword_without_hiding_current_original_weapon': r'''
display.current=1;v:update(pawn,owner,false);local back=v.back
display.current=0;v:update(pawn,owner,true)
assert(back.destroyed and not v.back and proxy.bHidden and not stock.bHidden and stock.writes==0)
''',
    'unequipping_custom_ID_restores_only_mod_changed_flags_and_removes_back': r'''
display.current=1;v:update(pawn,owner,false);local back=v.back
display.slots[1]={index=0,id='Other',actors={proxy}};v:update(pawn,owner,false)
assert(not proxy.bHidden and not stock.bHidden and stock.writes==0 and #v.hidden==0 and back.destroyed)
''',
    'native_actor_reuse_as_an_original_slot_does_not_keep_it_hidden': r'''
v:update(pawn,owner,true)
display.slots={{index=0,id='Tang',actors={proxy}},{index=1,id='RKA',actors={stock}}}
v:update(pawn,owner,false)
assert(not proxy.bHidden and stock.bHidden and #v.hidden==1 and v.hidden[1].actor==stock)
''',
    'repeated_native_show_only_rehides_the_verified_custom_proxy': r'''
v:update(pawn,owner,true);proxy.bHidden=false;v:update(pawn,owner,true)
assert(proxy.bHidden and #v.hidden==1 and stock.writes==0)
''',
    'custom_ID_in_either_native_index_has_the_same_behavior': r'''
display.slots={{index=0,id='Tang',actors={stock}},{index=1,id='RKA',actors={proxy}}}
v:update(pawn,owner,false)
assert(proxy.bHidden and not stock.bHidden and v.back and #created==1)
display.current=1;v:update(pawn,owner,true);assert(not v.back and created[1].destroyed)
''',
    'disabled_custom_combat_allows_the_selected_native_fallback_to_show': r'''
v:update(pawn,owner,true);v:update(pawn,owner,false)
assert(not proxy.bHidden and not stock.bHidden and #v.hidden==0 and not v.back)
''',
    'pawn_and_world_changes_destroy_old_back_and_rebuild_once': r'''
display.current=1;v:update(pawn,owner,false);local first=v.back
pawn=pawn_object();v:update(pawn,owner,false)
assert(first.destroyed and v.back~=first and #created==2)
local second=v.back;world=obj();v:update(pawn,owner,false)
assert(second.destroyed and #created==3)
''',
    'same_pawn_mesh_replacement_rebuilds_back_on_the_new_mesh_once': r'''
display.current=1;v:update(pawn,owner,false);local first=v.back;local old_mesh=mesh
mesh=obj();pawn.Mesh=mesh;v:update(pawn,owner,false)
assert(first.destroyed and v.back~=first and v.back.parent==mesh and v.back.parent~=old_mesh)
assert(#created==2 and proxy.bHidden and not stock.bHidden and stock.writes==0)
for i=1,10 do v:update(pawn,owner,false)end
assert(#created==2 and v.mesh==mesh)
''',
    'pending_index_keeps_only_freshly_verified_custom_slot_hidden': r'''
v:update(pawn,owner,true);local writes=proxy.writes
display.pending=true;display.slots[1].verified=true
v:update(pawn,owner,true)
assert(proxy.bHidden and #v.hidden==1 and proxy.writes==writes)
assert(not stock.bHidden and stock.writes==0 and not v.back)
display.pending=nil;v:update(pawn,owner,true)
assert(proxy.bHidden and #v.hidden==1 and proxy.writes==writes)
''',
    'pending_index_retains_back_only_when_its_custom_slot_is_freshly_verified': r'''
display.current=1;v:update(pawn,owner,false);local back=v.back
display.pending=true;display.slots[1].verified=true;v:update(pawn,owner,false)
assert(v.back==back and not back.destroyed and proxy.bHidden and not stock.bHidden)
display.slots[1].verified=false;display.slots[1].actors={};v:update(pawn,owner,false)
assert(back.destroyed and not v.back and not proxy.bHidden and #v.hidden==0)
''',
    'pending_config_reuse_or_unresolved_identity_never_reuses_old_hide_ownership': r'''
v:update(pawn,owner,true);display.pending=true
display.slots[1].verified=false;display.slots[1].actors={};v:update(pawn,owner,true)
assert(not proxy.bHidden and #v.hidden==0 and not stock.bHidden)
display.slots[1].verified=true;display.slots[1].actors={proxy};v:update(pawn,owner,true)
assert(proxy.bHidden)
display.slots={};v:update(pawn,owner,true)
assert(not proxy.bHidden and #v.hidden==0 and not stock.bHidden)
''',
    'real_adapter_pending_index_preserves_owned_proxy_and_restores_reused_original': r'''
local base,soul,stock_config=obj(),obj(),obj()
owner.GetEquipmentNormalWeapons=function()return {'RKA','Tang'}end
owner.GetCurrentMainWeaponIndex=function()return 0 end
owner.CurrentMainWeaponID='RKA'
local data={Weapons={{WeaponConfig=base,WeaponActors={proxy},Scabbards={}},
 {WeaponConfig=stock_config,WeaponActors={stock},Scabbards={}}}}
local component=obj({GetOwner=function()return pawn end,
 GetCurrentWeaponIndex=function(_,_,pending)return pending and (pending_index or 0)or 0 end,
 RuntimeWeaponData={ForEach=function(_,callback)callback({TagName='Weapon.Slot.Main'},data)end}})
pawn.K2_GetComponentsByClass=function()return {component}end
local find=StaticFindObject
function StaticFindObject(path)
 if path=='/Script/SGameCombatSystem.CharacterWeaponsComponent'then return obj()end
 return find(path)
end
v.equipment=Equipment.new(function()end,registry,function()end)
v.equipment.configs={Weapon_RKA_RingedKnight=base,Weapon_RKA_RingedKnight_Soul=soul}
v:update(pawn,owner,true);assert(proxy.bHidden and not stock.bHidden)
pending_index=1;local pending=v.equipment:display_slots(pawn,owner)
assert(pending.pending and pending.slots[1].verified)
v:update(pawn,owner,true)
assert(proxy.bHidden and #v.hidden==1 and not stock.bHidden and stock.writes==0)
data.Weapons[1].WeaponConfig=stock_config;v:update(pawn,owner,true)
assert(not proxy.bHidden and #v.hidden==0 and not stock.bHidden and stock.writes==0)
''',
    'invalid_pawn_and_explicit_clear_restore_owned_state': r'''
display.current=1;v:update(pawn,owner,false);local back=v.back
pawn.destroyed=true;v:update(pawn,owner,false)
assert(back.destroyed and not proxy.bHidden and not v.back and #v.hidden==0)
v:clear();assert(not stock.bHidden and stock.writes==0)
''',
    'partial_mesh_failure_can_be_cleared_without_orphaning_a_component': r'''
display.current=1;fail_mesh=true;assert(not pcall(v.update,v,pawn,owner,false))
assert(v.back and #created==1);v:clear()
assert(created[1].destroyed and not proxy.bHidden and not stock.bHidden)
''',
    'off_thread_updates_are_rejected_before_mutation': r'''
thread=false;assert(not pcall(v.update,v,pawn,owner,true))
assert(proxy.writes==0 and stock.writes==0 and #created==0)
''',
    'component_cleanup_failure_still_releases_owned_native_hidden_flags': r'''
display.current=1;v:update(pawn,owner,false)
v.back.K2_DestroyComponent=function()error('mock component cleanup failure')end
assert(not pcall(v.clear,v))
assert(not proxy.bHidden and not stock.bHidden and #v.hidden==0)
''',
    'native_scabbard_components_use_their_own_hidden_flag_without_hiding_the_character': r'''
local component=obj({bHiddenInGame=false,IsA=function(_,class)return class.path=='/Script/Engine.SceneComponent'end,
 SetHiddenInGame=function(self,value,propagate)assert(propagate==false);self.bHiddenInGame=value end})
display.slots[1].actors[2]=component;v:update(pawn,owner,true)
assert(proxy.bHidden and component.bHiddenInGame and not stock.bHidden)
v:clear();assert(not proxy.bHidden and not component.bHiddenInGame and stock.writes==0)
''',
    'native_back_socket_roll_lays_blade_flat_without_turning_its_tip_or_detaching_from_spine': r'''
v.back_mount=nil;display.current=1
local parents={Pt_TangBlade_Back='Pt_TangBladeScabbard_Back',Pt_TangBladeScabbard_Back='Pt_weapon_back_root',Pt_weapon_back_root='spine_05'}
mesh.GetSocketBoneName=function(_,socket)assert(socket=='Pt_TangBlade_Back_Socket');return {ToString=function()return 'Pt_TangBlade_Back'end}end
mesh.GetParentBone=function(_,bone)return {ToString=function()return assert(parents[bone])end}end
mesh.GetSocketTransform=function(_,socket,space)assert(space==2);return {socket=socket}end
local find=StaticFindObject
function StaticFindObject(path)
 if path=='/Script/Engine.Default__KismetMathLibrary'then
  return obj({MakeRelativeTransform=function(_,socket,spine)
   assert(socket.socket=='Pt_TangBlade_Back_Socket'and spine.socket=='spine_05')
   -- Native Tang+Z points down in this spine-space fixture.
   return {Rotation={X=0,Y=1,Z=0,W=0},Translation={X=2,Y=-18,Z=9},Scale3D={X=1.2,Y=.8,Z=.9}}
  end})
 end
 return find(path)
end
v:update(pawn,owner,false)
local back,tf=v.back,v.back.transform
assert(back.bone=='spine_05'and back.parent==mesh and back.asset.path=='/Mod/SM_Sword.SM_Sword'and #loads==1)
assert(tf.Translation.X==2 and tf.Translation.Y==-18 and tf.Translation.Z==9)
assert(tf.Scale3D.X==1.2 and tf.Scale3D.Y==.8 and tf.Scale3D.Z==.9)
local function rotate(q,v)
 local x,y,z,w=q.X,q.Y,q.Z,q.W
 local tx,ty,tz=2*(y*v[3]-z*v[2]),2*(z*v[1]-x*v[3]),2*(x*v[2]-y*v[1])
 return {v[1]+w*tx+y*tz-z*ty,v[2]+w*ty+z*tx-x*tz,v[3]+w*tz+x*ty-y*tx}
end
local q=tf.Rotation
assert(math.abs(q.X*q.X+q.Y*q.Y+q.Z*q.Z+q.W*q.W-1)<1e-9)
local before={X=0,Y=0,Z=-1,W=0} -- Original nativeY180 * localX180.
local tip_before,tip_after=rotate(before,{0,0,-1}),rotate(q,{0,0,-1})
for i=1,3 do assert(math.abs(tip_after[i]-tip_before[i])<1e-9,'Roll changed the sword length axis')end
assert(math.abs(tip_after[1])<1e-9 and math.abs(tip_after[2])<1e-9 and math.abs(tip_after[3]+1)<1e-9,
 'The sword tip must remain down, not sideways')
local normal_before,normal_after=rotate(before,{0,1,0}),rotate(q,{0,1,0})
assert(math.abs(normal_before[1]*normal_after[1]+normal_before[2]*normal_after[2]+normal_before[3]*normal_after[3])<1e-9,
 'The blade plane did not roll by90 degrees')
assert(math.abs(normal_after[1]-1)<1e-9 and math.abs(normal_after[2])<1e-9 and math.abs(normal_after[3])<1e-9)
mesh.pose='moved';v:update(pawn,owner,false)
assert(v.back==back and back.parent==mesh and back.bone=='spine_05'and #created==1,
 'A parent-bone pose change must keep the existing sword attached to the spine')
''',
}

results = []
for name, body in CASES.items():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().Visuals = lua.execute(SOURCE.read_text(encoding='utf-8'))
    lua.globals().Equipment = lua.execute(ADAPTER_SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP)
        lua.execute(body)
        results.append({'name': name, 'pass': True})
        print('PASS', name)
    except Exception as error:
        results.append({'name': name, 'pass': False, 'error': str(error)})
        print('FAIL', name, error)

(ROOT / 'reports/offline-equipment-visuals-tests.json').write_text(json.dumps({
    'scope': 'Real EquipmentVisuals.lua with verified slot resolver boundary mocked; no game or visual acceptance.',
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'adapter_sha256': hashlib.sha256(ADAPTER_SOURCE.read_bytes()).hexdigest(),
    'runtime_verified': False, 'cases': results,
}, indent=2), encoding='utf-8')
raise SystemExit(any(not case['pass'] for case in results))
