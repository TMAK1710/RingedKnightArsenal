"""Native soul-text registration contracts using the current seven-row extract.

Tests Lua behavior and real schema shapes; does not execute engine Copy or UI.
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/lua-python"))
from lupa import LuaRuntime

SOURCE = ROOT / "extract/pbz-current/ProjectPBZ/Content/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.json"
raw = SOURCE.read_bytes()
native = json.loads(raw.decode("utf-8-sig"))[0]
assert native["Properties"]["RowStruct"]["ObjectName"] == "Class'WeaponSnapSoulTextData'"
assert len(native["Rows"]) == 7
assert native["Rows"]["heimoshang"]["ID"] == "HeiMoShang"
lua = LuaRuntime(unpack_returned_tuples=True)
g = lua.globals()
g.scripts = str(ROOT / "src/runtime/RingedKnightArsenal/Scripts").replace("\\", "/") + "/"
lua.execute(r'''
    Definition=dofile(scripts..'RingedKnightDefinition.lua')
    Inventory=dofile(scripts..'NativeInventory.lua')
    function IsInGameThread()return true end
    function FText(value)
        assert(type(value)=='string');return {kind='FText',ToString=function()return value end}
    end
    function FName(value)
        assert(type(value)=='string');return {kind='FName',ToString=function()return value end,type=function()return 'FName'end}
    end
    function struct(values)
        return setmetatable({}, {
            __index=function(_,key)assert(values[key]~=nil,'Unknown native soul field '..key);return values[key]end,
            __newindex=function(_,key,value)
                local previous=values[key];assert(previous~=nil,'Unknown native soul field '..key)
                if type(previous)=='table' and not rawget(previous,'kind')then
                    error('Whole FlowLocText/native struct assignment is forbidden')
                end
                values[key]=value
            end,
        })
    end
    function array(values)
        return setmetatable({}, {
            __len=function()return #values end,
            __index=function(_,index)
                assert(type(index)=='number' and index>=1 and index<=#values,'Unsafe native soul array access')
                return values[index]
            end,
            __newindex=function()error('Soul struct arrays must retain initialized slots')end,
        })
    end
''')


def convert(value, field=""):
    if isinstance(value, dict):
        if "ValueCache" in value:
            return g.struct(lua.table_from({"Namespace": value.get("Namespace", ""),
                "Key": value.get("Key", ""), "ValueCache": g.FText(value.get("Key", ""))}))
        return g.struct(lua.table_from({key: convert(item, key) for key, item in value.items()}))
    if isinstance(value, list):
        return g.array(lua.table_from([convert(item) for item in value]))
    if field == "ID":
        return g.FName(value)
    return value


g.clone_source = lambda: convert(native["Rows"]["heimoshang"])
g.original_rows = lambda: lua.table_from({key: convert(value) for key, value in native["Rows"].items()})
lua.execute(r'''
    local SOUL='RKA_RingedKnight_Soul'
    local function setup(source_key)
        source_key=source_key or 'HeiMoShang'
        local rows=original_rows();local data={};local calls={clone=0,rollback=0}
        local source=rows.heimoshang;rows.heimoshang=nil;rows[source_key]=source
        function data:GetRowStruct()return {GetFullName=function()return 'ScriptStruct /Script/ProjectPBZ.WeaponSnapSoulTextData'end}end
        function data:ForEachRow(fn)for key,row in pairs(rows)do fn(FName(key),row)end end
        function data:FindRow(id)return rows[id]end
        local definition=Definition.definition()
        local registry={get=function(_,id)if id=='RKA_RingedKnight'then return definition end end}
        local function invoke(request)
            assert(request.id==SOUL)
            if request.phase=='soul_clone'then
                calls.clone=calls.clone+1;calls.source_key=request.base_row
                assert(request.base_row==source_key and not rows[SOUL])
                rows[SOUL]=clone_source();rows[SOUL].ID=FName(SOUL)
                return {ok=true,deep_copy=true,id=SOUL}
            elseif request.phase=='soul_rollback'then
                calls.rollback=calls.rollback+1;assert(rows[SOUL]);rows[SOUL]=nil
                return {ok=true,removed=true,id=SOUL}
            end
            error('Unexpected native bridge phase')
        end
        local function loader(path)
            assert(path=='/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText')
            return data
        end
        return Inventory.new(loader,registry,invoke,function()error('Weapon callback not used by soul registration')end),rows,definition,calls
    end
    do
        local inventory,rows,definition,calls=setup()
        local result=inventory:register_soul('RKA_RingedKnight')
        assert(result.original_rows==7 and result.rows_after==8 and result.metadata_applied and not result.runtime_verified)
        assert(calls.clone==1 and calls.rollback==0)
        local row=rows[SOUL]
        exported_soul_row=row
        assert(row.ID:ToString()==SOUL)
        assert(row.SnapSoulName.ValueCache:ToString()=='环印骑士剑')
        local function assert_owned_text(field)
            local value=field.ValueCache:ToString()
            if value==''then assert(field.Namespace=='' and field.Key=='')
            else
                assert(field.Namespace=='Default' and field.Key:match('^RKA_TXT_%x%x%x%x%x%x%x%x$'))
                assert(Definition.lookup_text(field.Key)==value)
            end
        end
        assert_owned_text(row.SnapSoulName)
        local lore='空挥的环直,化成悲哀的赤红之焰,闪耀着红色光芒的环直被取消,一次又一次直到...他停止呼吸...'
        assert(row.EquipDescription.ValueCache:ToString()==lore)
        assert(row.SimpleDesc.ValueCache:ToString()==lore)
        assert(#row.AbilityDesc==5 and #row.UpgradeLevelDesc==6 and #row.SnapSoulDesc==0)
        assert(row.AbilityDesc[1].WeaponTitle.ValueCache:ToString()=='环印剑术')
        assert(row.AbilityDesc[1].WeaponDesc.ValueCache:ToString()=='初入5林的小骑士，握住它便找回了前世记忆。\n第一次轻攻击的伤害×1.5、削韧900。\n\n防御＋重攻击，投掷附绳黑火焰壶。')
        assert(row.AbilityDesc[2].WeaponTitle.ValueCache:ToString()=='二番目の記憶')
        assert(row.AbilityDesc[2].WeaponDesc.ValueCache:ToString()=='我想起来了，我全都想起来了\n原来...你一直与我同在...')
        for index=1,5 do
            assert_owned_text(row.AbilityDesc[index].WeaponTitle)
            assert_owned_text(row.AbilityDesc[index].WeaponDesc)
            if index>2 then
                assert(row.AbilityDesc[index].WeaponTitle.ValueCache:ToString()=='')
                assert(row.AbilityDesc[index].WeaponDesc.ValueCache:ToString()=='')
            end
        end
        for index=1,6 do
            assert(row.UpgradeLevelDesc[index].WeaponTitle.ValueCache:ToString()==tostring(index*5)..'级强化')
            assert(row.UpgradeLevelDesc[index].WeaponDesc.ValueCache:ToString():find('全部剑盾招式继续可用'))
        end
        assert(calls.source_key=='HeiMoShang')
        assert(rows.HeiMoShang.ID:ToString()=='HeiMoShang')
        assert(rows.HeiMoShang.EquipDescription.Namespace=='Default' and rows.HeiMoShang.EquipDescription.Key=='WeaponDes_005')
        assert(rows.HeiMoShang.UpgradeLevelDesc[1].WeaponDesc.Key=='Weapon_Function_005_5')
        assert(inventory:register_soul('RKA_RingedKnight')==result and calls.clone==1)
    end
    do
        local inventory,rows,definition,calls=setup()
        definition.apply_soul_row=function()error('Forced soul metadata failure')end
        assert(not pcall(function()inventory:register_soul('RKA_RingedKnight')end))
        assert(not rows[SOUL] and calls.clone==1 and calls.rollback==1 and rows.HeiMoShang.ID:ToString()=='HeiMoShang')
    end
    do
        local inventory,rows,definition,calls=setup()
        rows[SOUL]=clone_source() -- an unowned existing row must never be replaced
        assert(not pcall(function()inventory:register_soul('RKA_RingedKnight')end))
        assert(rows[SOUL] and calls.clone==0 and calls.rollback==0)
    end
    do
        local inventory,rows,definition,calls=setup()
        definition.apply_soul_row=function(row)row.SnapSoulName=FText('unsafe')end
        assert(not pcall(function()inventory:register_soul('RKA_RingedKnight')end))
        assert(not rows[SOUL] and calls.rollback==1)
    end
    do
        local inventory,rows,definition,calls=setup('heimoshang')
        assert(inventory:register_soul('RKA_RingedKnight').metadata_applied)
        assert(calls.source_key=='heimoshang' and rows.heimoshang.ID:ToString()=='HeiMoShang')
    end
''')
assert SOURCE.read_bytes() == raw
own = g.exported_soul_row


def prose(field):
    return {"Namespace": field.Namespace, "Key": field.Key, "ValueCache": field.ValueCache.ToString()}


snapshot = {"row_key": "RKA_RingedKnight_Soul", "ID": own.ID.ToString()}
for key in ("SnapSoulName", "EquipDescription", "SimpleDesc"):
    snapshot[key] = prose(own[key])
for key in ("AbilityDesc", "SnapSoulDesc", "UpgradeLevelDesc"):
    snapshot[key] = [{"WeaponTitle": prose(own[key][index].WeaponTitle),
                      "WeaponDesc": prose(own[key][index].WeaponDesc)} for index in range(1, len(own[key])+1)]
(ROOT / "reports/item-soul-text.json").write_text(json.dumps({
    "status": "implemented_offline_native_runtime_pending", "source_row": "HeiMoShang", "cue_export_source_row": "heimoshang", "source_ID": "HeiMoShang",
    "source_table": "/Game/PBZContent/DataTable/UI/DT_WeaponSnapSoulText.DT_WeaponSnapSoulText",
    "source_rows": 7, "source_sha256": hashlib.sha256(raw).hexdigest(),
    "schema": "/Script/ProjectPBZ.WeaponSnapSoulTextData",
    "native_copy": "Real UE5.7 CppStructOps Copy handler; fail closed if absent; AddRowInternal transfers initialized owned row",
    "description_types": "FlowLocText structs with Namespace/Key strings and FText ValueCache; edited field by field",
    "native_phases": ["soul_clone", "soul_rollback", "row_rollback"],
    "registration": "NativeInventory:register_soul(RKA_RingedKnight) before publishing the main item row",
    "own_row_from_actual_lua_definition": snapshot,
    "original_rows_modified": False, "game_launched": False, "save_modified": False,
    "pending": ["Real native CppStructOps Copy and DataTable lifetime", "Soul UI lookup/display/refresh",
                "Upgrade/soul resource consumption and restrictions", "Save/load and uninstall acceptance"]
}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
checks = ["current seven-row schema fixture", "actual runtime source key HeiMoShang", "CUE lowercase key compatibility",
          "independent FName soul ID", "deep-clone bridge contract",
          "FlowLocText edited in place", "two supplied formal sections and three cleared native slots", "six truthful strength milestones",
          "all original rows and localization keys preserved", "idempotent soul registration",
          "metadata failure rolls back only own row", "unowned existing destination rejected",
          "whole-struct text assignment rejected", "source extraction unchanged"]
report = {"status": "passed_offline", "source": str(SOURCE), "source_sha256": hashlib.sha256(raw).hexdigest(),
          "checks": checks, "native_copy_executed": False, "game_launched": False,
          "native_ui_or_save_load_verified": False}
(ROOT / "reports/item-soul-text-tests.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(f"PASS {len(checks)} offline soul-text contracts; native Copy/UI/save-load acceptance remains pending.")
