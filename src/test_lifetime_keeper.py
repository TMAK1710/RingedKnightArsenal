"""Offline real LifetimeKeeper contracts; no claim of Unreal GC validation."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/runtime/RingedKnightArsenal/Scripts/LifetimeKeeper.lua'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

SETUP = r'''
serial=0;game_thread=true;constructed={};objects={};writes=0
OUTER='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight'
PATH=OUTER..'.RKA_ItemTables'
TABLES={
 '/Game/PBZContent/DataTable/UI/DT_WeaponData.DT_WeaponData',
 '/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText'}
function obj(kind,path,outer)
 serial=serial+1;local address=serial
 return {path=path,IsValid=function(self)return not self.destroyed end,
 GetAddress=function()return address end,GetOuter=function()return outer end,
 GetFullName=function()return kind..' '..path end,
 SetRootSet=function()error('Legacy SetRootSet must never be used')end,
 AddToRoot=function()error('Legacy wrapper must never be used')end}
end
function object_array(items)
 return setmetatable({}, {
 __len=function()return #items end,
 __index=function(_,index)assert(type(index)=='number' and index>=1 and index<=#items);return items[index]end,
 __newindex=function(_,index,value)
  assert(type(index)=='number' and index>=1 and index<=#items+1)
  assert(type(value)=='table' and value.IsValid and value:IsValid(),'ObjectProperty requires actual valid UObject')
  items[index]=value;writes=writes+1
 end})
end
function FName(s)return {ToString=function()return s end}end
function IsInGameThread()return game_thread end
invalid={IsValid=function()return false end}
outer=obj('Package',OUTER)
class=obj('Class','/Script/Engine.ObjectLibrary')
objects['/Script/Engine.ObjectLibrary']=class
tables={obj('DataTable',TABLES[1]),obj('DataTable',TABLES[2])}
loads={[TABLES[1]]=tables[1],[TABLES[2]]=tables[2]}
function load(path)assert(loads[path],'Unexpected lifetime asset load '..path);return loads[path]end
function StaticFindObject(path)
 assert(path=='/Script/Engine.ObjectLibrary' or path==PATH,'Unexpected holder lookup '..path)
 return objects[path] or invalid
end
function holder(p,owner,items,weak)
 local value=obj('ObjectLibrary',p,owner)
 value.Objects=object_array(items or {});value.WeakObjects=weak or {}
 value.bUseWeakReferences=true;value.bHasBlueprintClasses=true
 return value
end
function StaticConstructObject(c,owner,name,flags,internal,a,b,template)
 assert(c==class and owner==outer and name:ToString()=='RKA_ItemTables')
 assert(flags==0xC1 and internal==0x40000000 and a==false and b==false and template==nil)
 assert(not objects[PATH],'Holder must be constructed only once')
 local value=holder(PATH,owner)
 objects[PATH]=value;constructed[#constructed+1]=value;return value
end
function keeper()return Keeper.new(load,outer)end
'''

CASES = {
 'constructor_requires_owned_base_config_package': r'''
assert(not pcall(Keeper.new,load,obj('Package','/Game/Original/Tang')))
assert(not pcall(Keeper.new,false,outer))
''',
 'constructs_single_root_requested_holder_with_only_two_strong_tables': r'''
local k=keeper();local status=k:prepare()
assert(#constructed==1 and writes==2 and k.prepared)
assert(k.holder:GetFullName()=='ObjectLibrary '..PATH and k.holder:GetOuter()==outer)
assert(not k.holder.bUseWeakReferences and not k.holder.bHasBlueprintClasses and #k.holder.WeakObjects==0)
assert(#k.holder.Objects==2 and k.holder.Objects[1]==tables[1] and k.holder.Objects[2]==tables[2])
assert(status.strong_references_verified and status.constructor_root_requested and not status.runtime_gc_verified)
''',
 'prepare_and_check_are_idempotent_without_new_roots_or_array_writes': r'''
local k=keeper();local first=k:prepare();local second=k:prepare();k:check()
assert(#constructed==1 and writes==2 and first.holder_address==second.holder_address)
''',
 'fresh_keeper_reuses_existing_correct_holder_and_tables': r'''
local old=keeper();old:prepare();local new=keeper();new:prepare()
assert(new.holder==old.holder and #constructed==1 and writes==2)
''',
 'requires_game_thread_for_prepare_and_check': r'''
local k=keeper();game_thread=false;assert(not pcall(k.prepare,k) and #constructed==0)
game_thread=true;k:prepare();game_thread=false;assert(not pcall(k.check,k))
''',
 'rejects_wrong_ObjectLibrary_class_fullname': r'''
objects['/Script/Engine.ObjectLibrary']=obj('BlueprintGeneratedClass','/Script/Engine.ObjectLibrary')
local k=keeper();assert(not pcall(k.prepare,k) and #constructed==0)
''',
 'rejects_wrong_holder_outer': r'''
objects[PATH]=holder(PATH,obj('Package',OUTER))
local k=keeper();assert(not pcall(k.prepare,k) and writes==0)
''',
 'rejects_preexisting_unexpected_object_count': r'''
objects[PATH]=holder(PATH,outer,{tables[1]})
local k=keeper();assert(not pcall(k.prepare,k) and writes==0)
''',
 'rejects_any_weak_object_before_cloning_can_proceed': r'''
objects[PATH]=holder(PATH,outer,{}, {tables[1]})
local k=keeper();assert(not pcall(k.prepare,k) and writes==0)
''',
 'rejects_wrong_DataTable_identity': r'''
loads[TABLES[2]]=obj('DataTable','/Game/Unrelated.Unrelated')
local k=keeper();assert(not pcall(k.prepare,k))
''',
 'rejects_invalidated_holder_without_constructing_replacement': r'''
local k=keeper();k:prepare();k.holder.destroyed=true
assert(not pcall(k.check,k) and not pcall(k.prepare,k) and #constructed==1)
''',
 'rejects_invalidated_table': r'''
local k=keeper();k:prepare();tables[1].destroyed=true;assert(not pcall(k.check,k))
''',
 'rejects_replaced_holder_table_even_with_identical_fullname': r'''
local k=keeper();k:prepare();k.holder.Objects[1]=obj('DataTable',TABLES[1]);assert(not pcall(k.check,k))
''',
 'rejects_reloaded_table_at_different_native_address': r'''
local k=keeper();k:prepare();loads[TABLES[2]]=obj('DataTable',TABLES[2]);assert(not pcall(k.check,k))
''',
 'rejects_weak_reference_mode_enabled_after_prepare': r'''
local k=keeper();k:prepare();k.holder.bUseWeakReferences=true;assert(not pcall(k.check,k))
''',
 'rejects_additional_object_after_prepare': r'''
local k=keeper();k:prepare();k.holder.Objects[3]=outer;assert(not pcall(k.check,k))
''',
 'accepts_UE4SS_object_pointer_wrappers_when_addresses_are_unchanged': r'''
local k=keeper();k:prepare()
local first,second=tables[1],tables[2]
local values={{get=function()return first end},{get=function()return second end}}
k.holder.Objects=setmetatable({}, {__len=function()return 2 end,__index=function(_,i)return values[i]end})
assert(k:check().strong_references_verified)
''',
}

results=[]
for name,body in CASES.items():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().Keeper=lua.execute(SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP)
        lua.execute(body)
        results.append({'name':name,'pass':True});print('PASS',name)
    except Exception as error:
        results.append({'name':name,'pass':False,'error':str(error)});print('FAIL',name,error)

(ROOT/'reports/offline-lifetime-keeper-tests.json').write_text(json.dumps({
    'scope':'Real LifetimeKeeper.lua under Lua 5.4 with strict native-shaped object mocks; not an Unreal GC test.',
    'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'runtime_gc_verified':False,'cases':results},indent=2),encoding='utf-8')
raise SystemExit(any(not c['pass'] for c in results))
