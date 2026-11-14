"""Compile the actual config_finalize body against recording reflection doubles.

This exercises the production mutation/repair boundary, not the game ABI.
Run after build_native.ps1 in its MSVC environment; outputs stay in build/native.
"""
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/native/NativeWeaponConfig.hpp').read_text(encoding='utf-8')
constants = '\n'.join(re.findall(r'inline constexpr wchar_t (?:config_\w+|change_armed_class_path|switch_air_class_path|sheath_sound_\w+|simple_execution_class_path|contextual_counter_class_path)\[\]=[^;]+;', source))
helpers = source[source.index('inline std::vector<std::wstring> sound_tuple('):source.index('inline std::wstring export_owned_value(')]
start = source.index('inline Json config_finalize(')
body = source[start:]
assert body.rstrip().endswith('}')

template = json.loads((ROOT / 'extract/vanilla-balance/ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Players/Hun/Weapon/Tang/Weapon_Hun_Tang.json').read_text(encoding='utf-8'))
native_reference = next(o['Properties']['Change Armed Ability'] for o in template if 'Change Armed Ability' in o.get('Properties', {}))
assert native_reference['ObjectName'] == "LegoAbilityBlueprintGeneratedClass'GA_Hun_Tang_ChangeArmed_C'"
assert native_reference['ObjectPath'].endswith('/GA_Hun_Tang_ChangeArmed.18')
native_switches = next(o['Properties']['Change Weapon Abilities'] for o in template if 'Change Weapon Abilities' in o.get('Properties', {}))
assert len(native_switches) == 4
assert sum(o['ObjectName'] == "LegoAbilityBlueprintGeneratedClass'BP_SwitchAttack_DefaultAir_C'" for o in native_switches) == 1
audit = ROOT / 'extract/compatibility-audit-0915/ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/Prototypes/Abilities'
air = json.loads((audit / 'BP_SwitchAttack_DefaultAir.json').read_text(encoding='utf-8'))
assert not any('ScriptBytecode' in o for o in air)
air_defaults = next(o['Properties'] for o in air if o['Name'].startswith('Default__'))
assert air_defaults['Ability Tag']['TagName'] == 'Ability.Action.Hun.Heavy.AirAtk01'
switch = json.loads((audit / 'BP_SwitchAttack_Default.json').read_text(encoding='utf-8'))
graph = next(o['ScriptBytecode'] for o in switch if o['Name'] == 'ExecuteUbergraph_BP_SwitchAttack_Default')
graph_text = json.dumps(graph)
assert graph_text.index('Change Weapon By Ability') < graph_text.index('ForceActivateExternalActionAbilityByTag')
forced = next(o for o in graph if 'ForceActivateExternalActionAbilityByTag' in json.dumps(o))
after_forced = graph[graph.index(forced) + 1]
assert after_forced['Token'] == 'EX_JumpIfNot'
exit_statement = next(o for o in graph if o['StatementIndex'] == after_forced['CodeOffset'])
assert exit_statement['Function'] == 'K2_EndAbility'
sounds = next(o['Properties']['Sounds'] for o in template if 'Sounds' in o.get('Properties', {}))
holster = json.loads((ROOT / 'extract/flower-097/ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Players/Hun/Abilities/TangBlade/Default/GA_Hun_Tang_ChangeArmed.json').read_text(encoding='utf-8'))
timeline = {o['Name']: o['Properties'] for o in holster if o['Type'] == 'LGATimeline'}
actions = {o['Name']: o.get('Properties', {}) for o in holster}
assert all('GAA_PBZWeaponSound' not in a['Action']['ObjectName'] for a in timeline['Arm']['Actions'])
unarm_keys = {actions[a['Action']['ObjectName'].split('.')[-1].rstrip("'")]['Sound Tag']['TagName'] for a in timeline['UnArm']['Actions'] if 'GAA_PBZWeaponSound' in a['Action']['ObjectName']}
assert unarm_keys & {s['Key']['TagName'] for s in sounds} == {'Weapon.Sound.Unarm.Tang'}
sound_entry = next(s for s in sounds if s['Key']['TagName'] == 'Weapon.Sound.Unarm.Tang')
sound_event = next(v for v in sound_entry['Value'].values() if isinstance(v, dict) and 'ObjectPath' in v)
assert sound_event['ObjectPath'].endswith('/ShouDao/SFX_Combat_Hun_TangBlade_ShouDao.0')
equips = next(o['Properties']['Equip Abilities'] for o in template if 'Equip Abilities' in o.get('Properties', {}))
assert len(equips) == 42
for expected in ['GA_SimpleExecution_Tang_C', 'GA_Hun_BDEx_ZuoShang_CA_02_Fixed_C']:
    assert sum(o['ObjectName'] == f"LegoAbilityBlueprintGeneratedClass'{expected}'" for o in equips) == 1
simple = json.loads((audit / 'Base/GA_SimpleExecution_Base.json').read_text(encoding='utf-8'))
simple_defaults = next(o['Properties'] for o in simple if o['Name'].startswith('Default__'))
assert simple_defaults['AbilityTags'] == simple_defaults['ActivationOwnedTags'] == ['Ability.Action.Hun.SimpleExecution']
assert simple_defaults['AbilityTriggers'] == [{'TriggerTag': {'TagName': 'GameplayEvent.Ability.Action.SimpleExecution.Activate'}, 'TriggerSource': 'EGameplayAbilityTriggerSource::GameplayEvent'}]
event_gate = json.dumps(next(o['ScriptBytecode'] for o in simple if o['Name'] == 'K2_ShouldAbilityRespondToEvent'))
assert all(token in event_gate for token in ['Payload', 'Target', 'GetValidTimelines', 'Map_IsNotEmpty'])
counter_root = ROOT / 'extract/compatibility-audit-0915/ProjectPBZ/Plugins/Secret/PBZDeflectSystem/Content/Abilities'
counter = json.loads((counter_root / 'BP_Hun_PerfectDodge_ExecutionBase.json').read_text(encoding='utf-8'))
counter_gate = next(o['ScriptBytecode'] for o in counter if o['Name'] == 'Get Valid Perfect Dodge Timelines')
assert all(token in json.dumps(counter_gate) for token in ['Counter Ability', 'EqualEqual_ClassClass', 'GetObjectClass'])
counter_branch = next(s for s in counter_gate if s['Token'] == 'EX_JumpIfNot')
assert next(s for s in counter_gate if s['StatementIndex'] == counter_branch['CodeOffset'])['Token'] == 'EX_Return'
counter_parent = json.loads((counter_root / 'BP_PlayerPerfectDodge_Base.json').read_text(encoding='utf-8'))
counter_defaults = next(o['Properties'] for o in counter_parent if o['Name'].startswith('Default__'))
assert counter_defaults['AbilityTags'] == counter_defaults['ActivationOwnedTags'] == ['Ability.Action.Hun.PerfectDodge']
assert 'Get Valid Perfect Dodge Timelines' in json.dumps(next(o['ScriptBytecode'] for o in counter_parent if o['Name'] == 'K2_CanActivateAbility'))

preamble = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <iostream>
#include <map>
#include <malloc.h>
#include <new>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include "../../references/pbz-mc/third_party/nlohmann-json-3.11.3/json.hpp"
using Json=nlohmann::json;
struct ArrayView {void* data=nullptr;std::int32_t count=0,capacity=0;};
struct UObject {std::wstring name;bool dead=false;UObject* ability=nullptr;ArrayView switches,equips;std::wstring sounds=L"()";std::wstring GetFullName()const{return name;}bool IsUnreachable(){return dead;}};
struct UStruct:UObject {int GetPropertiesSize()const{return 1024;}};
static int copies=0,switch_copies=0,resets=0;static bool break_copy=false,break_switch_copy=false,bad_schema=false,bad_field=false,bad_switch_inner=false;
static int sound_copies=0,sound_initialized=0,sound_destroyed=0;static bool break_sound_copy=false,bad_sound_import=false,bad_sound_readback=false;
static int equip_copies=0,equip_initialized=0,equip_destroyed=0;static bool break_equip_copy=false,break_equip_value_copy=false,bad_equip_inner=false;
static std::vector<std::wstring> reset_names;
struct FProperty {
 bool array=false,map=false,equip=false;
 bool SameType(const FProperty*)const{return !bad_schema;}
 int GetSize()const{return map?sizeof(std::wstring):(array?sizeof(ArrayView):sizeof(void*));}
 int GetMinAlignment()const{return alignof(void*);}
 void InitializeValue(void* p)const{if(equip){*static_cast<UObject**>(p)=nullptr;++equip_initialized;return;}assert(map);new(p)std::wstring;++sound_initialized;}
 void DestroyValue(void* p)const{if(equip){++equip_destroyed;return;}assert(map);using W=std::wstring;static_cast<W*>(p)->~W();++sound_destroyed;}
 const wchar_t* ImportText_Direct(const wchar_t* text,void* p,UObject*,int,void*)const{
  assert(map);if(bad_sound_import)return nullptr;*static_cast<std::wstring*>(p)=bad_sound_readback?L"()":text;return text+wcslen(text);
 }
 int GetArrayDim()const{return 1;}
 void CopyCompleteValue(void* to,const void* from)const{
  if(map){++sound_copies;if(!break_sound_copy)*static_cast<std::wstring*>(to)=*static_cast<const std::wstring*>(from);return;}
  if(equip&&!array){if(!break_equip_value_copy)*static_cast<UObject**>(to)=*static_cast<UObject*const*>(from);return;}
  if(!array){++copies;if(!break_copy)*static_cast<UObject**>(to)=*static_cast<UObject*const*>(from);return;}
  if(equip){++equip_copies;if(break_equip_copy)return;}else{++switch_copies;if(break_switch_copy)return;}
  auto& target=*static_cast<ArrayView*>(to);const auto& source=*static_cast<const ArrayView*>(from);
  auto* data=new UObject*[source.count];std::copy_n(static_cast<UObject**>(source.data),source.count,data);
  delete[] static_cast<UObject**>(target.data);target={data,source.count,source.count};
 }
};
struct FObjectPropertyBase:FProperty {UObject* GetObjectPropertyValue(const void* p)const{return *static_cast<UObject*const*>(p);}};
struct ReflectedValue {const FProperty* property;void* address;};
static FObjectPropertyBase property;
static FObjectPropertyBase equip_property;
struct FArrayProperty:FProperty {FArrayProperty(bool contextual=false){array=true;equip=contextual;}const FProperty* GetInner()const{return equip?&equip_property:&property;}};
static FArrayProperty array_property;
static FArrayProperty equip_array_property(true);
struct FMapProperty:FProperty{FMapProperty(){map=true;}};
static FMapProperty map_property;
static std::map<std::wstring,UObject*> objects;
static std::vector<UObject*> owned_configs;
static void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
static UObject* find_object(const wchar_t* path){return objects.at(path);}
static std::wstring from_utf8(const std::string& s){return {s.begin(),s.end()};}
static std::string metadata_utf8(std::wstring_view s){return {s.begin(),s.end()};}
static std::wstring property_kind(const FProperty* p){return (p==&equip_property?bad_equip_inner:bad_switch_inner)?L"ObjectProperty":L"ClassProperty";}
static void readable(const void* data,std::size_t size){require(data&&size>0,"unreadable fake array");}
static ReflectedValue reset_target(const UStruct*,void* container,std::size_t,std::wstring_view name,std::wstring_view kind,bool inherited){
 assert(inherited);require(!bad_field,"simulated missing metadata");
 if(name==L"Change Armed Ability"){assert(kind==L"ClassProperty");return {&property,&static_cast<UObject*>(container)->ability};}
 if(name==L"Change Weapon Abilities"){assert(kind==L"ArrayProperty");return {&array_property,&static_cast<UObject*>(container)->switches};}
 if(name==L"Sounds"){assert(kind==L"MapProperty");return {&map_property,&static_cast<UObject*>(container)->sounds};}
 if(name==L"Equip Abilities"){assert(kind==L"ArrayProperty");return {&equip_array_property,&static_cast<UObject*>(container)->equips};}
 assert(kind==L"ArrayProperty"||kind==L"MapProperty");reset_names.emplace_back(name);return {&property,nullptr};
}
static void engine_reset(const ReflectedValue& target){assert(!target.address);++resets;}
static void set_switches(UObject& object,std::initializer_list<UObject*> values){
 delete[] static_cast<UObject**>(object.switches.data);auto* data=new UObject*[values.size()];std::copy(values.begin(),values.end(),data);
 object.switches={data,static_cast<int>(values.size()),static_cast<int>(values.size())};
}
static UObject* only_switch(const UObject& object){assert(object.switches.count==1);return *static_cast<UObject**>(object.switches.data);}
static void set_equips(UObject& object,const std::vector<UObject*>& values){
 delete[] static_cast<UObject**>(object.equips.data);auto* data=new UObject*[values.size()];std::copy(values.begin(),values.end(),data);
 object.equips={data,static_cast<int>(values.size()),static_cast<int>(values.size())};
}
static bool contextual_pair(const UObject& object,UObject* simple,UObject* counter){return object.equips.count==2&&static_cast<UObject**>(object.equips.data)[0]==simple&&static_cast<UObject**>(object.equips.data)[1]==counter;}
static std::wstring export_owned_value(const ReflectedValue& value,UObject*){return *static_cast<const std::wstring*>(value.address);}
'''
tests = r'''
int main(){
 equip_property.equip=true;
 UStruct schema;schema.name=std::wstring(L"BlueprintGeneratedClass ")+config_class_path;
 UObject ability;ability.name=std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+change_armed_class_path;
 UObject native;native.name=std::wstring(L"PBZ_MainWeaponConfig_C ")+config_template_path;native.ability=&ability;
 UObject base;base.name=std::wstring(L"PBZ_MainWeaponConfig_C ")+config_base_path;base.ability=&ability;
 UObject soul;soul.name=std::wstring(L"PBZ_MainWeaponConfig_C ")+config_soul_path;
 UObject air,normal,dash,tang;air.name=std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+switch_air_class_path;
 normal.name=L"Native Normal";dash.name=L"Native Dash";tang.name=L"Tang switch attack";
 set_switches(native,{&normal,&air,&dash,&tang});set_switches(base,{&normal,&air,&dash,&tang});
 const auto sheath_pair=std::wstring(L"(")+sheath_sound_key+L", (Sound=AkAudioEvent'\""+sheath_sound_path+L".SFX_Combat_Hun_TangBlade_ShouDao\"',Nested=((Text=\"escaped \\\" comma, (value)\"))))";
 const auto selected_sound=L"("+sheath_pair+L")";
 const auto original_sounds=std::wstring(L"(((TagName=\"Weapon.Sound.Wave.Light\"), (Sound=Swing)),")+sheath_pair+L")";
 native.sounds=original_sounds;base.sounds=original_sounds;
 UObject simple,counter;simple.name=std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+simple_execution_class_path;
 counter.name=std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+contextual_counter_class_path;
 std::vector<UObject*> original_equips(42,&tang);original_equips[28]=&simple;original_equips[37]=&counter;
 set_equips(native,original_equips);set_equips(base,original_equips);
 objects={{config_class_path,&schema},{config_template_path,&native},{config_base_path,&base},{config_soul_path,&soul}};
 auto request=[](const wchar_t* path){return Json{{"phase","config_finalize"},{"path",metadata_utf8(path)}};};
 auto fails=[](auto fn){try{fn();}catch(const std::exception&){return;}assert(false&&"Expected rejection");};
 // Real UE-exported map fixture proves outer pair syntax independently of
 // CUE JSON. The sound values below are synthetic stress data; exact live
 // Sounds ExportText formatting remains a runtime validation boundary.
 const auto ue_map_parts=sound_tuple(L__UE_GUARD_MAP__);
 assert(ue_map_parts.size()==3&&sound_tuple(ue_map_parts[0])[0]==L"(TagName=\"Damage.Attack.Target.PhysicalDamage\")");
 assert(select_sheath_sound(original_sounds)==selected_sound);
 fails([&]{select_sheath_sound(L"()");});
 fails([&]{select_sheath_sound(L"("+sheath_pair+L","+sheath_pair+L")");});
 fails([&]{sound_tuple(L"((TagName=\"unterminated))");});
 fails([&]{sound_tuple(L"(()))");});
 fails([&]{sound_tuple(L"(a,)");});
 auto first=config_finalize(request(config_base_path));
 assert(first["change_armed_preserved"]&& !first["change_armed_restored"]&&first["cleared_properties"]==8);
 assert(first["switch_air_preserved"]&&first["switch_air_restored"]&&only_switch(base)==&air&&switch_copies==1);
 assert(first["sheath_sound_preserved"]&&first["sheath_sound_restored"]&&base.sounds==selected_sound&&native.sounds==original_sounds&&sound_copies==1);
 assert(first["contextual_abilities_preserved"]&&first["contextual_abilities_restored"]&&first["contextual_ability_count"]==2);
 assert(contextual_pair(base,&simple,&counter)&&equip_copies==1&&native.equips.count==42);
 assert(native.switches.count==4&&static_cast<UObject**>(native.switches.data)[0]==&normal);
 assert(base.ability==&ability&&native.ability==&ability&&copies==0&&resets==8&&owned_configs.size()==1);
 assert(std::find(reset_names.begin(),reset_names.end(),L"Change Armed Ability")==reset_names.end());
 assert(std::find(reset_names.begin(),reset_names.end(),L"Change Weapon Abilities")==reset_names.end());
 assert(std::find(reset_names.begin(),reset_names.end(),L"Sounds")==reset_names.end());
 assert(std::find(reset_names.begin(),reset_names.end(),L"Equip Abilities")==reset_names.end());
 auto second=config_finalize(request(config_soul_path));
 assert(second["change_armed_restored"]&&soul.ability==&ability&&copies==1&&resets==16&&owned_configs.size()==2);
 assert(second["switch_air_restored"]&&only_switch(soul)==&air&&switch_copies==2);
 assert(second["sheath_sound_restored"]&&soul.sounds==selected_sound&&sound_copies==2);
 assert(second["contextual_abilities_restored"]&&contextual_pair(soul,&simple,&counter)&&equip_copies==2);
 base.ability=nullptr;auto repaired=config_finalize(request(config_base_path));
 assert(repaired["idempotent"]&&repaired["change_armed_restored"]&&repaired["cleared_properties"]==0);
 assert(base.ability==&ability&&copies==2&&resets==16&&owned_configs.size()==2);
 auto repeated=config_finalize(request(config_base_path));
 assert(!repeated["sheath_sound_restored"]&&sound_copies==2);
 assert(!repeated["contextual_abilities_restored"]&&equip_copies==2);
 assert(repeated["idempotent"]&&!repeated["change_armed_restored"]&&!repeated["switch_air_restored"]&&copies==2&&resets==16&&switch_copies==2);
 set_switches(base,{});auto repaired_air=config_finalize(request(config_base_path));
 assert(repaired_air["idempotent"]&&repaired_air["switch_air_restored"]&&only_switch(base)==&air&&switch_copies==3);
 set_switches(base,{&normal,&air});config_finalize(request(config_base_path));
 assert(only_switch(base)==&air&&switch_copies==4);
 auto invalid_air=[&]{const auto before_copies=copies,before_switch=switch_copies;fails([&]{config_finalize(request(config_base_path));});assert(copies==before_copies&&switch_copies==before_switch&&only_switch(base)==&air);};
 set_switches(native,{&normal,&dash,&tang});invalid_air();
 set_switches(native,{&normal,&air,&air,&tang});invalid_air();
 set_switches(native,{&normal,&dash,&tang,&normal});invalid_air();
 set_switches(native,{&normal,&air,&dash,&tang});air.dead=true;invalid_air();air.dead=false;
 bad_switch_inner=true;invalid_air();bad_switch_inner=false;
 set_switches(base,{});break_switch_copy=true;
 fails([&]{config_finalize(request(config_base_path));});assert(base.switches.count==0&&switch_copies==5);break_switch_copy=false;
 config_finalize(request(config_base_path));assert(only_switch(base)==&air&&switch_copies==6);
 set_equips(base,{});auto repaired_equips=config_finalize(request(config_base_path));
 assert(repaired_equips["idempotent"]&&repaired_equips["contextual_abilities_restored"]&&contextual_pair(base,&simple,&counter)&&equip_copies==3);
 set_equips(base,original_equips);config_finalize(request(config_base_path));assert(contextual_pair(base,&simple,&counter)&&equip_copies==4);
 auto invalid_equips=[&]{const auto c=copies,a=switch_copies,e=equip_copies,s=sound_copies;fails([&]{config_finalize(request(config_base_path));});assert(copies==c&&switch_copies==a&&equip_copies==e&&sound_copies==s&&contextual_pair(base,&simple,&counter));};
 auto changed_equips=original_equips;changed_equips[28]=&tang;set_equips(native,changed_equips);invalid_equips();
 changed_equips=original_equips;changed_equips[37]=&tang;set_equips(native,changed_equips);invalid_equips();
 changed_equips=original_equips;changed_equips[0]=&simple;set_equips(native,changed_equips);invalid_equips();
 set_equips(native,original_equips);counter.dead=true;invalid_equips();counter.dead=false;
 bad_equip_inner=true;invalid_equips();bad_equip_inner=false;
 break_equip_value_copy=true;invalid_equips();break_equip_value_copy=false;
 set_equips(base,{});break_equip_copy=true;fails([&]{config_finalize(request(config_base_path));});assert(base.equips.count==0&&equip_copies==5);break_equip_copy=false;
 config_finalize(request(config_base_path));assert(contextual_pair(base,&simple,&counter)&&equip_copies==6);
 base.sounds=L"()";auto repaired_sound=config_finalize(request(config_base_path));
 assert(repaired_sound["idempotent"]&&repaired_sound["sheath_sound_restored"]&&base.sounds==selected_sound&&sound_copies==3);
 base.sounds=original_sounds;config_finalize(request(config_base_path));assert(base.sounds==selected_sound&&sound_copies==4);
 auto invalid_sound=[&]{const auto before_copies=copies,before_switch=switch_copies,before_sound=sound_copies;fails([&]{config_finalize(request(config_base_path));});assert(copies==before_copies&&switch_copies==before_switch&&sound_copies==before_sound&&base.sounds==selected_sound);};
 native.sounds=L"()";invalid_sound();native.sounds=L"("+sheath_pair+L","+sheath_pair+L")";invalid_sound();
 native.sounds=L"(((TagName=\"Weapon.Sound.Unarm.Tang\"), (Sound=None)))";invalid_sound();native.sounds=original_sounds;
 bad_sound_import=true;invalid_sound();bad_sound_import=false;
 bad_sound_readback=true;invalid_sound();bad_sound_readback=false;
 base.sounds=L"()";break_sound_copy=true;fails([&]{config_finalize(request(config_base_path));});
 assert(base.sounds==L"()"&&sound_copies==5);break_sound_copy=false;
 config_finalize(request(config_base_path));assert(base.sounds==selected_sound&&sound_copies==6&&native.sounds==original_sounds);
 native.ability=nullptr;base.ability=nullptr;
 fails([&]{config_finalize(request(config_base_path));});assert(copies==2&&resets==16&&!base.ability);
 native.ability=&ability;ability.dead=true;
 fails([&]{config_finalize(request(config_base_path));});assert(copies==2&&resets==16);ability.dead=false;
 ability.name=L"BlueprintGeneratedClass Other";
 fails([&]{config_finalize(request(config_base_path));});assert(copies==2&&resets==16);
 ability.name=std::wstring(L"LegoAbilityBlueprintGeneratedClass ")+change_armed_class_path;
 bad_schema=true;fails([&]{config_finalize(request(config_base_path));});assert(copies==2&&resets==16);bad_schema=false;
 bad_field=true;fails([&]{config_finalize(request(config_base_path));});assert(copies==2&&resets==16);bad_field=false;
 fails([&]{config_finalize(request(config_template_path));});assert(copies==2&&resets==16&&native.ability==&ability);
 break_copy=true;fails([&]{config_finalize(request(config_base_path));});assert(copies==3&&resets==16&&!base.ability);break_copy=false;
 config_finalize(request(config_base_path));assert(base.ability==&ability&&native.ability==&ability&&resets==16);
 assert(native.switches.count==4&&only_switch(base)==&air&&only_switch(soul)==&air);
 assert(native.sounds==original_sounds&&base.sounds==selected_sound&&soul.sounds==selected_sound);
 assert(native.equips.count==42&&std::equal(original_equips.begin(),original_equips.end(),static_cast<UObject**>(native.equips.data)));
 assert(contextual_pair(base,&simple,&counter)&&contextual_pair(soul,&simple,&counter)&&equip_initialized==equip_destroyed);
 assert(sound_initialized==sound_destroyed);
 std::cout<<"PASS actual config_finalize: base/soul, repeat repairs, preserved template, Air-only switch, two contextual specs only, sheath sound only, missing/duplicate/dead/schema/import/copy rejection and balanced native temporary lifetimes\n";
}
'''
out = ROOT / 'build/native'
tests = tests.replace('__UE_GUARD_MAP__', json.dumps((ROOT / 'reports/ue-native-guard-map.txt').read_text(encoding='utf-8').strip()))
generated = out / 'test_weapon_config_generated.cpp'
generated.write_text(preamble + constants + '\n' + helpers + body + tests, encoding='utf-8')
subprocess.run(['cl', '/nologo', '/std:c++latest', '/MD', '/O2', '/EHsc', '/utf-8', '/Fo' + str(out / 'test_weapon_config.obj'), '/Fe' + str(out / 'test_weapon_config.exe'), str(generated)], check=True, cwd=ROOT)
subprocess.run([str(out / 'test_weapon_config.exe')], check=True, cwd=ROOT)
print('PASS original exported Tang Change Armed Ability reference; mocked reflection is not live ABI proof')
