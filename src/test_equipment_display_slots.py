"""Verify real EquipmentAdapter resolves owned native display actors by slot/config."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/runtime/RingedKnightArsenal/Scripts/EquipmentAdapter.lua'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

SETUP = r'''
serial=0;thread=true;finds=0
function obj(fields)
 serial=serial+1;local address=serial;fields=fields or {}
 fields.IsValid=function(self)return not self.destroyed end;fields.GetAddress=function()return address end
 return fields
end
function FName(value)return {ToString=function()return value end,type=function()return 'FName'end}end
function IsInGameThread()return thread end
pawn=obj();base=obj();soul=obj();stock_config=obj();custom_actor=obj();scabbard=obj();stock_actor=obj();foreign_actor=obj()
owner=obj({ids={'RKA','Tang'},index=0,CurrentMainWeaponID=FName('RKA')})
owner.GetEquipmentNormalWeapons=function(self)return {FName(self.ids[1]),FName(self.ids[2])}end
owner.GetCurrentMainWeaponIndex=function(self)return self.index end
data={Weapons={{WeaponConfig=base,WeaponActors={custom_actor},Scabbards={scabbard}},
 {WeaponConfig=stock_config,WeaponActors={stock_actor},Scabbards={}}}}
component=obj({GetOwner=function()return pawn end,
 GetCurrentWeaponIndex=function(_,_,pending)return pending and (pending_index or owner.index)or owner.index end,
 RuntimeWeaponData={ForEach=function(_,callback)
  callback({TagName=FName('Weapon.Slot.Sub')},{Weapons={{WeaponConfig=base,WeaponActors={foreign_actor},Scabbards={}}}})
  callback({TagName=FName('Weapon.Slot.Main')},data)
 end}})
components={component}
local component_class=obj()
function StaticFindObject(path)assert(path=='/Script/SGameCombatSystem.CharacterWeaponsComponent');return component_class end
pawn.K2_GetComponentsByClass=function(_,class)assert(class==component_class);finds=finds+1;return components end
function FindAllOf()error('Display lookup must not scan the world')end
a=Equipment.new(function()end,{get=function(_,id)return id=='RKA'and {}or nil end},function()end)
a.configs={Weapon_RKA_RingedKnight=base,Weapon_RKA_RingedKnight_Soul=soul}
'''

CASES = {
    'execution_leaves_empty_third_slot_without_losing_verified_custom_display': r'''
data.Weapons[3]={WeaponConfig=nil,WeaponActors={},Scabbards={}}
local result=a:display_slots(pawn,owner)
assert(not result.pending and #result.slots==2 and result.slots[1].verified)
assert(result.slots[1].actors[1]==custom_actor and result.slots[1].actors[2]==scabbard)
''',
    'populated_execution_slots_are_not_mapped_or_hidden_as_equipped_weapons': r'''
data.Weapons[3]={WeaponConfig=base,WeaponActors={foreign_actor},Scabbards={}}
local result=a:display_slots(pawn,owner)
assert(not result.pending and #result.slots==2 and #result.slots[1].actors==2)
for _,slot in ipairs(result.slots)do for _,actor in ipairs(slot.actors)do assert(actor~=foreign_actor)end end
''',
    'native_execution_slot_current_index_does_not_resolve_as_equipped_slot': r'''
data.Weapons[3]={WeaponConfig=base,WeaponActors={foreign_actor},Scabbards={}}
component.GetCurrentWeaponIndex=function()return 2 end
local result=a:display_slots(pawn,owner)
assert(result.pending and #result.slots==2 and result.slots[1].verified)
assert(result.slots[1].actors[1]==custom_actor)
for _,slot in ipairs(result.slots)do for _,actor in ipairs(slot.actors)do assert(actor~=foreign_actor)end end
''',
    'unexpectedly_large_native_slot_array_stays_unresolved': r'''
for i=3,17 do data.Weapons[i]={}end
assert(a:display_slots(pawn,owner).pending)
''',
    'returns_only_the_custom_slots_weapon_and_scabbard_actors': r'''
local result=a:display_slots(pawn,owner)
assert(result.current==0 and #result.slots==2)
assert(result.slots[1].verified and #result.slots[1].actors==2)
assert(result.slots[1].actors[1]==custom_actor and result.slots[1].actors[2]==scabbard)
assert(result.slots[2].id=='Tang'and #result.slots[2].actors==0)
''',
    'custom_ID_in_the_second_slot_reads_native_index_plus_one': r'''
owner.ids={'Tang','RKA'};owner.index=0;owner.CurrentMainWeaponID=FName('Tang')
data.Weapons[1],data.Weapons[2]=data.Weapons[2],data.Weapons[1]
local result=a:display_slots(pawn,owner)
assert(#result.slots[1].actors==0 and result.slots[2].actors[1]==custom_actor and result.slots[2].index==1)
''',
    'native_config_mismatch_is_unverified_instead_of_hiding_the_stale_original': r'''
data.Weapons[1].WeaponConfig=stock_config
local result=a:display_slots(pawn,owner)
assert(not result.slots[1].verified and #result.slots[1].actors==0)
''',
    'native_soul_config_is_accepted_at_the_owned_address': r'''
data.Weapons[1].WeaponConfig=soul
local result=a:display_slots(pawn,owner);assert(result.slots[1].verified and #result.slots[1].actors==2)
''',
    'identical_named_but_distinct_config_is_not_owned': r'''
local impostor=obj();impostor.GetFullName=function()return 'PBZ_MainWeaponConfig_C Own'end
base.GetFullName=impostor.GetFullName;data.Weapons[1].WeaponConfig=impostor
local result=a:display_slots(pawn,owner);assert(not result.slots[1].verified and #result.slots[1].actors==0)
''',
    'another_lua_wrapper_at_the_same_native_address_is_owned': r'''
data.Weapons[1].WeaponConfig={IsValid=base.IsValid,GetAddress=base.GetAddress}
assert(a:display_slots(pawn,owner).slots[1].verified)
''',
    'remote_property_wrappers_are_unwrapped_at_each_boundary': r'''
local function remote(value)return {get=function()return value end}end
data.Weapons[1]=remote({WeaponConfig=remote(base),WeaponActors={remote(custom_actor)},Scabbards={remote(scabbard)}})
component.RuntimeWeaponData.ForEach=function(_,callback)callback(remote({TagName=FName('Weapon.Slot.Main')}),remote(data))end
local result=a:display_slots(pawn,owner);assert(result.slots[1].verified and result.slots[1].actors[2]==scabbard)
''',
    'foreign_character_components_are_ignored': r'''
components={obj({GetOwner=function()return obj()end}),component}
assert(a:display_slots(pawn,owner).slots[1].actors[1]==custom_actor)
''',
    'missing_component_yields_empty_pending_but_uncommitted_index_retains_verified_slots': r'''
components={};local result=a:display_slots(pawn,owner);assert(result.pending and #result.slots==0)
components={component};pending_index=1;result=a:display_slots(pawn,owner)
assert(result.pending and #result.slots==2 and result.slots[1].verified and result.slots[1].actors[1]==custom_actor)
''',
    'pending_current_index_keeps_config_checks_and_rejects_actor_reuse': r'''
component.GetCurrentWeaponIndex=function()return 1 end
local result=a:display_slots(pawn,owner)
assert(result.pending and result.slots[1].verified and result.slots[1].actors[1]==custom_actor)
data.Weapons[1].WeaponConfig=stock_config
result=a:display_slots(pawn,owner)
assert(result.pending and not result.slots[1].verified and #result.slots[1].actors==0)
''',
    'pending_lookup_does_not_reuse_previous_owners_or_slot_identities': r'''
pending_index=1;local before=a:display_slots(pawn,owner)
assert(before.pending and before.slots[1].verified)
owner=obj({GetEquipmentNormalWeapons=function()return {FName('Tang'),FName('RKA')}end,
 GetCurrentMainWeaponIndex=function()return 0 end,CurrentMainWeaponID=FName('Tang')})
data.Weapons[1].WeaponConfig=stock_config;data.Weapons[2].WeaponConfig=base
data.Weapons[2].WeaponActors={foreign_actor};component.GetCurrentWeaponIndex=function()return 1 end
local after=a:display_slots(pawn,owner)
assert(after.pending and after.slots[1].id=='Tang'and #after.slots[1].actors==0)
assert(after.slots[2].verified and after.slots[2].actors[1]==foreign_actor)
''',
    'pending_index_with_empty_native_other_slot_never_claims_foreign_actors': r'''
owner.ids[2]='None';data.Weapons[2]={WeaponConfig=nil,WeaponActors={},Scabbards={}}
pending_index=1;local result=a:display_slots(pawn,owner)
assert(result.pending and #result.slots==2 and result.slots[1].verified)
assert(result.slots[2].id=='None'and #result.slots[2].actors==0)
''',
    'inconsistent_equipped_ID_or_native_array_yields_pending': r'''
owner.CurrentMainWeaponID=FName('Tang');assert(a:display_slots(pawn,owner).pending)
owner.CurrentMainWeaponID=FName('RKA');data.Weapons[2]=nil;assert(a:display_slots(pawn,owner).pending)
''',
    'without_any_custom_ID_no_native_display_lookup_is_needed': r'''
owner.ids={'Tang','Other'};owner.CurrentMainWeaponID=FName('Tang')
local result=a:display_slots(pawn,owner);assert(#result.slots==0 and finds==0)
''',
    'destroyed_native_display_actors_are_not_returned': r'''
custom_actor.destroyed=true;local result=a:display_slots(pawn,owner)
assert(#result.slots[1].actors==1 and result.slots[1].actors[1]==scabbard)
''',
    'off_thread_lookup_is_rejected_before_native_access': r'''
thread=false;assert(not pcall(a.display_slots,a,pawn,owner)and finds==0)
''',
}

results = []
for name, body in CASES.items():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().Equipment = lua.execute(SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP)
        lua.execute(body)
        results.append({'name': name, 'pass': True})
        print('PASS', name)
    except Exception as error:
        results.append({'name': name, 'pass': False, 'error': str(error)})
        print('FAIL', name, error)

(ROOT / 'reports/offline-equipment-display-slots-tests.json').write_text(json.dumps({
    'scope': 'Real EquipmentAdapter.lua with RuntimeWeaponData and InterfaceProperty-shaped mocks; no engine/equipment runtime proof.',
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'runtime_verified': False, 'cases': results,
}, indent=2), encoding='utf-8')
raise SystemExit(any(not case['pass'] for case in results))
