"""Offline control-flow contracts only; does not run Unreal construction/equip."""
from pathlib import Path
import json
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools/lua-python'))
from lupa import LuaRuntime
lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().Equipment = lua.execute((root / 'src/runtime/RingedKnightArsenal/Scripts/EquipmentAdapter.lua').read_text(encoding='utf-8'))
lua.execute(r'''
function IsInGameThread()return true end
function FName(s)return {ToString=function()return s end,type=function()return 'FName'end}end
local original={native=true}
local class={IsValid=function()return true end,GetFullName=function()return 'BlueprintGeneratedClass /PBZCombatAsset/Prototypes/Config/PBZ_MainWeaponConfig.PBZ_MainWeaponConfig_C'end}
local package_class={IsValid=function()return true end,kind='Package'}
local invalid={IsValid=function()return false end}
function CreateInvalidObject()return invalid end
local objects,constructs={},{}
local fail_config_once=false
function StaticFindObject(path)
    assert(not path:find('/HuaShira/Mods/RingedKnight/Data/',1,true) or path:find('.',1,true),
        'UE4SS GetPackageNameFromLongName rejects bare package paths')
    if path=='/Script/CoreUObject.Package'then return package_class end;return objects[path] or invalid
end
local template={IsValid=function()return true end,GetClass=function()return class end,
    GetFullName=function()return 'PBZ_MainWeaponConfig_C /PBZCombatAsset/ActorData/Players/Hun/Weapon/Tang/Weapon_Hun_Tang.Weapon_Hun_Tang'end}
function StaticConstructObject(c,outer,n,flags,internal,a,b,t)
    assert(flags==0x41 and internal==0x40000000 and a==false and b==false)
    local text=n:ToString()
    local key,kind
    if c==package_class then assert(outer==invalid and t==nil);key=text;kind='Package'
    else
        assert(c==class and t==template)
        if fail_config_once then fail_config_once=false;error('mock construction failure after package allocation')end
        key=outer.path..'.'..text;kind='PBZ_MainWeaponConfig_C'
    end
    local result={path=key,IsValid=function()return true end,GetFullName=function()return kind..' '..key end,
        GetOuter=function()return outer end}
    objects[key]=result;constructs[#constructs+1]=result;return result
end
local registry={get=function(_,id)return id=='RKA_RingedKnight' and {} or nil end}
local calls={}
local function bridge(request)
    calls[#calls+1]=request
    if request.phase=='config_finalize'then return {ok=true,owned=true,phase=request.phase}end
    assert(request.phase=='sanitize' and request.id=='RKA_RingedKnight')
    return {ok=true,id=request.id,economy_preserved=true,upgrade_entries=59}
end
local adapter=Equipment.new(function()return template end,registry,bridge)
assert(not pcall(function()adapter:sanitize('RKA_RingedKnight')end))
local assets=adapter:prepare()
assert(assets.config~=assets.soul_config and assets.requires_prepare_before_load and #constructs==4 and #calls==2)
assert(adapter:prepare()==assets and #constructs==4 and template~=constructs[2] and original.native)
adapter:sanitize('RKA_RingedKnight')
assert(not pcall(function()adapter:sanitize('Tang')end))
local owner={ids={'Tang','Other'},index=1,CurrentMainWeaponID=FName('Other')}
function owner:GetEquipmentNormalWeapons()local values={};for i,v in ipairs(self.ids)do values[i]=FName(v)end;return values end
function owner:GetCurrentMainWeaponIndex()return self.index end
function owner:GetAddress()return 1234 end
function owner:HasWeapon(id,normal)assert(normal);return id:ToString()~='Missing'end
function owner:ReplaceWeaponByIndex(id,slot)self.ids[slot+1]=id:ToString()end
function owner:SetCurrentWeaponByIndex(slot,normal)assert(normal);self.index=slot;self.CurrentMainWeaponID=FName(self.ids[slot+1])end
local chosen=adapter:select(owner,'RKA_RingedKnight',0)
assert(chosen.selected and owner.ids[1]=='RKA_RingedKnight' and owner.ids[2]=='Other')
adapter:restore(owner,chosen.snapshot)
assert(owner.ids[1]=='Tang' and owner.ids[2]=='Other' and owner.index==1)
assert(not pcall(function()adapter:select(owner,'Tang',0)end))
assert(not pcall(function()adapter:select(owner,'RKA_RingedKnight',2)end))
local normal_set=owner.SetCurrentWeaponByIndex
function owner:SetCurrentWeaponByIndex(slot,normal)
    normal_set(self,slot,normal)
    if self.ids[slot+1]=='RKA_RingedKnight'then self.CurrentMainWeaponID=FName('Tang')end
end
assert(not pcall(function()adapter:select(owner,'RKA_RingedKnight',0)end))
assert(owner.ids[1]=='Tang' and owner.ids[2]=='Other' and owner.index==1)
-- A fresh adapter must recover real config outers, never search a bare package.
local before_constructs=#constructs
local reused=Equipment.new(function()return template end,registry,bridge)
local reused_assets=reused:prepare()
assert(#constructs==before_constructs and reused_assets.config==assets.config)
for name,config in pairs(reused.configs)do assert(reused.packages[name]==config:GetOuter())end
-- A package created before a config construction failure remains available on
-- that adapter's retry, even though no config exists to expose its GetOuter.
objects={};constructs={};fail_config_once=true
local retry=Equipment.new(function()return template end,registry,bridge)
assert(not pcall(retry.prepare,retry) and #constructs==1 and not retry.prepared)
local first_package=constructs[1]
retry:prepare()
assert(retry.prepared and #constructs==4 and constructs[1]==first_package)
assert(retry.packages.Weapon_RKA_RingedKnight==first_package)
''')
report = {'offline_contracts_passed': ['engine_template_parameter_8', 'two_unique_owned_paths', 'rooted_owned_package_lifetime', 'prepare_idempotence', 'sanitize_requires_prepare_and_registry', 'id_based_selection', 'original_slot_restore', 'native_slot_bounds', 'selection_readback_rejection_and_rollback', 'reject_bare_package_object_lookup', 'existing_config_outer_reuse', 'failed_config_constructor_reuses_cached_package'], 'native_runtime_verified': False}
(root / 'reports/equipment-adapter-tests.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print('PASS 12 equipment adapter contracts; Unreal object construction, native UI and save/load remain unverified.')
