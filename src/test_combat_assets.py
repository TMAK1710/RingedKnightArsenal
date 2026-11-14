"""Real CombatAssets.lua under strict UE-shaped mocks; never Unreal GC proof."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/runtime/RingedKnightArsenal/Scripts/CombatAssets.lua'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

SETUP = r'''
serial=0;game_thread=true;writes=0;constructs=0;objects={}
OUTER='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight'
PATH=OUTER..'.RKA_CombatAssets'
function object(kind,path,owner)
 serial=serial+1;local address=serial
 return {IsValid=function(self)return not self.destroyed end,
 GetAddress=function()return address end,GetFullName=function()return kind..' '..path end,
 GetOuter=function()return owner end,
 SetRootSet=function()error('Legacy root bit setter is forbidden')end}
end
function array(values)
 return setmetatable({}, {__len=function()return #values end,
 __index=function(_,i)assert(type(i)=='number'and i>=1 and i<=#values);return values[i]end,
 __newindex=function(_,i,value)
  assert(type(i)=='number'and i>=1 and i<=#values+1)
  assert(value.IsValid and value:IsValid(),'Strong object fields require valid UObject')
  values[i]=value;writes=writes+1
 end})
end
function FName(value)return {ToString=function()return value end}end
function IsInGameThread()return game_thread end
invalid={IsValid=function()return false end}
outer=object('Package',OUTER)
class=object('Class','/Script/Engine.ObjectLibrary')
objects['/Script/Engine.ObjectLibrary']=class
function holder(owner,items,weak,path)
 local value=object('ObjectLibrary',path or PATH,owner or outer)
 value.Objects=array(items or {});value.WeakObjects=weak or {}
 value.bUseWeakReferences=true;value.bHasBlueprintClasses=true
 return value
end
function StaticFindObject(path)
 assert(path==PATH or path=='/Script/Engine.ObjectLibrary')
 return objects[path]or invalid
end
function StaticConstructObject(c,owner,name,flags,internal,a,b,template)
 assert(c==class and owner==outer and name:ToString()=='RKA_CombatAssets')
 assert(flags==0xC1 and internal==0x40000000 and not a and not b and template==nil)
 assert(not objects[PATH],'Duplicate root construction')
 constructs=constructs+1;objects[PATH]=holder();return objects[PATH]
end
function keeper()return Keeper.new(outer)end
function asset(name)return object('AnimSequence','/HuaShira/Mods/RingedKnight/Animations/'..name..'.'..name)end
function asset_path(value)return value:GetFullName():match('^[^ ]+ (.+)$')end
function retain(k,value)return k:retain(asset_path(value),value)end
'''

CASES = {
    'requires_owned_configuration_package': r'''
assert(not pcall(Keeper.new,object('Package','/Game/Original')))
''',
    'constructs_independent_strong_constructor_root_holder': r'''
local k=keeper();local result=k:prepare()
assert(constructs==1 and writes==0 and k.holder:GetFullName()=='ObjectLibrary '..PATH)
assert(k.holder:GetOuter()==outer and not k.holder.bUseWeakReferences and not k.holder.bHasBlueprintClasses)
assert(#k.holder.WeakObjects==0 and result.asset_count==0)
assert(result.constructor_root_requested and result.strong_references_verified and not result.runtime_gc_verified)
''',
    'retains_animations_and_native_vfx_as_actual_object_properties': r'''
local k=keeper();k:prepare();local first=asset('A_First')
local effect=object('NiagaraSystem','/PBZVFXPack/VFX/Test.Test')
assert(retain(k,first)==first and retain(k,effect)==effect)
assert(#k.holder.Objects==2 and k.holder.Objects[1]==first and k.holder.Objects[2]==effect)
assert(k:check().asset_count==2 and writes==2)
''',
    'repeated_load_and_prepare_do_not_append_or_construct_again': r'''
local k=keeper();k:prepare();local first=asset('A_First')
for i=1,12 do retain(k,first);k:prepare()end
assert(constructs==1 and writes==1 and #k.holder.Objects==1)
''',
    'accepts_new_lua_wrappers_for_the_same_native_address': r'''
local k=keeper();k:prepare();local first=asset('A_First');retain(k,first)
local wrapper={IsValid=first.IsValid,GetAddress=first.GetAddress,GetFullName=first.GetFullName}
assert(retain(k,wrapper)==wrapper and writes==1)
k.holder.Objects=setmetatable({}, {__len=function()return 1 end,
 __index=function()return {get=function()return first end}end})
assert(k:check().asset_count==1 and retain(k,wrapper)==wrapper)
''',
    'source_reload_adopts_existing_holder_without_clearing_live_assets': r'''
local first=asset('A_First');local k=keeper();k:prepare();retain(k,first)
local fresh=keeper();fresh:prepare();retain(fresh,first)
assert(constructs==1 and writes==1 and fresh.holder==k.holder and fresh:check().asset_count==1)
''',
    'requested_path_mismatch_is_rejected_before_assignment': r'''
local k=keeper();k:prepare();local first=asset('A_First')
local ok,why=pcall(k.retain,k,'/Game/Wrong.Wrong',first)
assert(not ok and why:find('requested=/Game/Wrong.Wrong',1,true)and why:find('actual=AnimSequence ',1,true))
assert(writes==0)
''',
    'same_path_new_native_address_is_rejected_without_replacing_old_reference': r'''
local k=keeper();k:prepare();local first=asset('A_First');retain(k,first)
assert(not pcall(retain,k,asset('A_First'))and writes==1 and k.holder.Objects[1]==first)
''',
    'same_native_address_cannot_be_registered_under_another_path': r'''
local k=keeper();k:prepare();local first=asset('A_First');retain(k,first)
local alias=asset('A_Alias');alias.GetAddress=first.GetAddress
assert(not pcall(retain,k,alias)and writes==1)
''',
    'bounded_process_cache_rejects_the_257th_asset': r'''
local k=keeper();k:prepare()
for i=1,256 do retain(k,asset('A_'..i))end
assert(k:check().asset_count==256)
local ok,why=pcall(retain,k,asset('A_Overflow'))
assert(not ok and why:find('limit exceeded',1,true)and writes==256)
''',
    'all_object_access_requires_the_game_thread': r'''
local k=keeper();game_thread=false;assert(not pcall(k.prepare,k)and constructs==0)
game_thread=true;k:prepare();game_thread=false
assert(not pcall(k.check,k)and not pcall(retain,k,asset('A_First'))and writes==0)
''',
    'wrong_engine_class_outer_and_weak_references_are_rejected': r'''
objects['/Script/Engine.ObjectLibrary']=object('BlueprintGeneratedClass','/Script/Engine.ObjectLibrary')
assert(not pcall(function()keeper():prepare()end)and constructs==0)
objects['/Script/Engine.ObjectLibrary']=class
objects[PATH]=holder(object('Package',OUTER))
assert(not pcall(function()keeper():prepare()end))
objects[PATH]=holder(outer,{}, {asset('A_First')})
assert(not pcall(function()keeper():prepare()end)and writes==0)
''',
    'invalid_or_replaced_references_fail_check_instead_of_reloading': r'''
local k=keeper();k:prepare();local first=asset('A_First');retain(k,first)
first.destroyed=true;assert(not pcall(k.check,k))
first.destroyed=false;k.holder.Objects[1]=asset('A_First')
assert(not pcall(k.check,k)and not pcall(retain,k,first)and constructs==1)
''',
    'stale_holder_and_post_prepare_weak_mode_fail_closed': r'''
local k=keeper();k:prepare();k.holder.destroyed=true
assert(not pcall(k.check,k)and not pcall(k.prepare,k)and constructs==1)
k.holder.destroyed=false;k.holder.bUseWeakReferences=true
assert(not pcall(k.check,k)and not pcall(retain,k,asset('A_First')))
''',
    'unexpected_array_append_is_detected': r'''
local k=keeper();k:prepare();k.holder.Objects[1]=asset('A_Foreign')
assert(not pcall(k.check,k)and not pcall(retain,k,asset('A_First')))
''',
    'existing_duplicate_references_are_rejected_during_adoption': r'''
local first=asset('A_First');objects[PATH]=holder(outer,{first,first})
assert(not pcall(function()keeper():prepare()end)and constructs==0 and writes==0)
''',
}

results = []
for name, body in CASES.items():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().Keeper = lua.execute(SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP)
        lua.execute(body)
        results.append({'name': name, 'pass': True})
        print('PASS', name)
    except Exception as error:
        results.append({'name': name, 'pass': False, 'error': str(error)})
        print('FAIL', name, error)

(ROOT / 'reports/offline-combat-assets-tests.json').write_text(json.dumps({
    'scope': 'Real CombatAssets.lua in Lua 5.4 with strict UObject and ObjectLibrary mocks; no live engine or GC execution.',
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'runtime_gc_verified': False, 'cases': results,
}, indent=2), encoding='utf-8')
raise SystemExit(any(not case['pass'] for case in results))
