"""Offline owned-row/upgrade contracts using the real extracted native data.

Mocks exercise Lua logic only; they do not prove native UI, Copy, saves or play.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/lua-python"))
from lupa import LuaRuntime


def run():
    source = ROOT / "reports/current-tang-row.json"
    raw = source.read_bytes()
    native = json.loads(raw.decode("utf-8-sig"))
    spec = importlib.util.spec_from_file_location("rka_upgrades", ROOT / "src/generate_item_upgrades.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    expected = generator.build()
    report = json.loads((ROOT / "reports/item-upgrades.json").read_text(encoding="utf-8"))
    assert report == expected
    assert (ROOT / "reports/item-upgrades.json").read_bytes() == (
        ROOT / "src/runtime/RingedKnightArsenal/Scripts/item-upgrades.json").read_bytes()
    assert len(report["progression"]) == 59
    for index, entry in enumerate(report["progression"]):
        original = native["WeaponUpLevelDatas"][index]
        for key in ("Materials", "ConsumeDust", "bNeedInJHSY", "AttackMultipliers"):
            assert entry[key] == original[key]
    assert report["snap_soul"]["Materials"] == native["WeaponSnapSoulData"]["Materials"]
    assert report["snap_soul"]["ConsumeDust"] == 5000
    lua = LuaRuntime(unpack_returned_tuples=True)
    folder = str(ROOT / "src/runtime/RingedKnightArsenal/Scripts").replace("\\", "/") + "/"
    lua.globals().scripts = folder
    lua.execute(r'''
        Definition=dofile(scripts..'RingedKnightDefinition.lua')
        Upgrade=dofile(scripts..'UpgradeAdapter.lua')
        function FText(s)
            assert(type(s)=='string');return {kind='text',value=s,ToString=function()return s end,type=function()return 'FText'end}
        end
        function FName(s)
            local value=FText(s);value.type=function()return 'FName'end;return value
        end
        function soft(s)
            assert(type(s)=='string');return {kind='soft',value=s,GetObjectID=function()
                return {GetAssetPathName=function()return FName(s)end}end}
        end
        function array(items)
            return setmetatable({}, {
                __len=function()return #items end,
                __index=function(_,key)
                    if key=='Empty'then return function()items={}end end
                    assert(type(key)=='number' and key>=1 and key<=#items,'Unsafe native array access')
                    return items[key]
                end,
                __newindex=function(_,key,value)
                    assert(type(key)=='number' and key>=1 and key<=#items+1,'Unsafe native array write')
                    assert(value.kind=='soft','Native struct arrays must be edited in place')
                    items[key]=value
                end,
            })
        end
        function struct(values)
            return setmetatable({}, {
                __index=function(_,key)assert(values[key]~=nil,'Unknown native field '..key);return values[key]end,
                __newindex=function(_,key,value)
                    assert(values[key]~=nil,'Unknown native field '..key)
                    assert(type(value)~='table' or value.kind=='text' or value.kind=='soft',
                        'Whole-struct or array replacement is forbidden')
                    values[key]=value
                end,
            })
        end
        function map(values)
            return {ForEach=function(_,fn)for _,entry in ipairs(values)do fn(entry.Key,entry.Value)end end}
        end
    ''')
    g = lua.globals()
    profile = json.loads((ROOT / 'src/runtime/RingedKnightArsenal/Scripts/combat-profile.json').read_text(encoding='utf-8'))
    display = g.Definition.definition().display_attributes
    assert display[1].value == profile['base_physical'] == 242
    assert display[2].value == profile['base_fire'] == 23
    name_hash = 2166136261
    for byte in '环印骑士剑'.encode('utf-8'):
        name_hash = ((name_hash ^ byte) * 16777619) & 0xffffffff
    g.expected_name_key = f'RKA_TXT_{name_hash:08X}'

    def convert(value, field=""):
        if isinstance(value, dict):
            if field == "WeaponMesh":
                return g.array(lua.table_from([g.soft(value["AssetPathName"])]))
            if "AssetPathName" in value:
                return g.soft(value["AssetPathName"])
            if "ValueCache" in value:
                cache = value["ValueCache"]
                return g.struct(lua.table_from({"Namespace": value.get("Namespace", ""),
                    "Key": value.get("Key", ""), "ValueCache": g.FText(
                        cache.get("LocalizedString") or cache.get("SourceString") or value.get("Key", ""))}))
            return g.struct(lua.table_from({k: convert(v, k) for k, v in value.items()}))
        if isinstance(value, list):
            if field in ("DefaultWeaponMediaDatas", "Materials"):
                return g.map(lua.table_from([lua.table_from({"Key": e["Key"], "Value": convert(e["Value"])}) for e in value]))
            return g.array(lua.table_from([convert(v) for v in value]))
        return value

    original = convert(native)
    row = convert(native)
    g.row, g.original = row, original
    lua.execute(r'''
        row.ItemId=FName('RKA_RingedKnight')
        local assets={config='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA.Weapon_RKA',
            soul_config='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_Soul.Weapon_RKA_Soul',soft=soft}
        local materials={};local soul=row.WeaponSnapSoulData
        for i=1,#row.WeaponUpLevelDatas do materials[i]=row.WeaponUpLevelDatas[i].Materials end
        local soul_materials=soul.Materials
        local result=Definition.apply_row(row,assets)
        assert(result.metadata_applied and result.upgrade_entries==59 and not result.runtime_verified)
        assert(original.ItemId=='Tang')
        assert(original.Icon.value:find('HeiShang'))
        assert(row.WeaponName.ValueCache:ToString()=='环印骑士剑')
        local function check_text(field)
            local source=field.ValueCache:ToString()
            if source==''then assert(field.Key=='' and field.Namespace=='')
            else
                assert(field.Namespace=='Default' and field.Key:match('^RKA_TXT_%x%x%x%x%x%x%x%x$'))
                assert(Definition.lookup_text(field.Key)==source)
            end
        end
        assert(row.WeaponName.Key==expected_name_key,'FNV key must hash the UTF8 source bytes')
        for _,key in ipairs({'WeaponName','EquipDescription','Simple','ShortIntroduction'})do check_text(row[key])end
        for i=1,#row.WeaponAbilityDesc do
            check_text(row.WeaponAbilityDesc[i].WeaponTitle);check_text(row.WeaponAbilityDesc[i].WeaponDesc)
        end
        check_text(soul.WeaponSnapSoulName)
        check_text(row.DefaultGEData.WeaponTitle);check_text(row.DefaultGEData.FlowLocText)
        assert(Definition.lookup_text('OriginalKey')==nil and Definition.lookup_text('RKA_TXT_DEADBEEF')==nil)
        local copy=Definition.localization_entries();copy[row.WeaponName.Key]='tampered'
        assert(Definition.lookup_text(row.WeaponName.Key)==row.WeaponName.ValueCache:ToString())
        local old_name_key=row.WeaponName.Key
        local lore='空挥的环直,化成悲哀的赤红之焰,闪耀着红色光芒的环直被取消,一次又一次直到...他停止呼吸...'
        for _,key in ipairs({'EquipDescription','Simple','ShortIntroduction'})do
            assert(row[key].ValueCache:ToString()==lore)
        end
        assert(#row.WeaponMesh==0)
        assert(row.WeaponAbilityDesc[1].WeaponTitle.ValueCache:ToString()=='环印剑术')
        assert(row.WeaponAbilityDesc[1].WeaponDesc.ValueCache:ToString()=='初入5林的小骑士，握住它便找回了前世记忆。\n第一次轻攻击的伤害×1.5、削韧900。\n\n防御＋重攻击，投掷附绳黑火焰壶。')
        assert(row.WeaponAbilityDesc[2].WeaponTitle.ValueCache:ToString()=='二番目の記憶')
        assert(row.WeaponAbilityDesc[2].WeaponDesc.ValueCache:ToString()=='我想起来了，我全都想起来了\n原来...你一直与我同在...')
        assert(row.WeaponAbilityDesc[3].WeaponTitle.ValueCache:ToString()=='')
        assert(row.WeaponAbilityDesc[3].WeaponDesc.ValueCache:ToString()=='')
        local colored_icon='/HuaShira/Mods/RingedKnight/UI/T_RKA_Icon.T_RKA_Icon'
        local bloom_mask='/HuaShira/Mods/RingedKnight/UI/T_RKA_White.T_RKA_White'
        local upgrade_mask='/HuaShira/Mods/RingedKnight/UI/T_RKA_Upgrade.T_RKA_Upgrade'
        assert(row.Icon.value==colored_icon and row.White.value==colored_icon,
            'Native GetWeaponWhiteIconFindTable must return the colored list icon')
        assert(soul.WeaponIcon.value==colored_icon and soul.WhiteIcon.value==colored_icon,
            'Snap-soul list icon must retain the same colored preview')
        assert(row.WhiteBloom.value==bloom_mask and row.UpgradeIconTexture.value==upgrade_mask
            and row.SnapSoulUpgradeIconTexture.value==upgrade_mask,
            'Visible list icon changes must not replace bloom or upgrade wipe masks')
        for _,key in ipairs({'UIAttributeDatas','SnapSoulUIAttributeDatas','ReincarnationUIAttributeDatas'})do
            assert(#row[key]==2,'Keep the native structure slots; empty arrays show fallback 50/25')
            for i,expected in ipairs({{name='物理攻击',value=242},{name='火焰攻击',value=23}})do
                local attr=row[key][i]
                assert(attr.DefaultValue==expected.value and attr.CurveFloat.value=='')
                assert(attr.GEDescription.ValueCache:ToString()==expected.name)
                check_text(attr.GEDescription)
            end
        end
        assert(original.UIAttributeDatas[1].DefaultValue==200 and original.UIAttributeDatas[2].DefaultValue==100)
        for i=1,#row.WeaponUpLevelDatas do
            local current=row.WeaponUpLevelDatas[i];local source=original.WeaponUpLevelDatas[i]
            assert(current.Materials==materials[i])
            assert(current.ConsumeDust==source.ConsumeDust and current.AttackMultipliers==source.AttackMultipliers)
            assert(current.bNeedInJHSY==source.bNeedInJHSY)
            assert(#current.GEDatas==0 and #current.PersistentGEDatas==0 and #current.SnapSoulGEDatas==0
                and #current.GEUIDataArray==0)
        end
        assert(#original.WeaponUpLevelDatas[4].GEDatas==1)
        assert(#original.WeaponUpLevelDatas[9].PersistentGEDatas==1)
        assert(soul.Materials==soul_materials and soul.ConsumeDust==5000)
        assert(soul.WeaponConfig.value==assets.soul_config)
        assert(soul.SnapSoulTextID=='RKA_RingedKnight_Soul')
        assert(#soul.GameplayEffectDatas==0 and #soul.PersistentGEDatas==0 and #soul.GEUIDataArray==0
            and #row.DefaultGEUIData==0)
        assert(soul.WeaponSnapSoulName.ValueCache:ToString()=='环印骑士剑')
        assets.weapon_mesh='/HuaShira/Mods/RingedKnight/Meshes/SK_RKA_Display.SK_RKA_Display'
        Definition.apply_row(row,assets)
        assert(row.WeaponName.Key==old_name_key,'Repeated preparation must keep stable localization keys')
        assert(#row.WeaponMesh==1 and row.WeaponMesh[1].value==assets.weapon_mesh)
        assets.weapon_mesh=nil
        soul.SnapSoulTextID=FName('old')
        Definition.apply_row(row,assets)
        assert(soul.SnapSoulTextID:type()=='FName' and soul.SnapSoulTextID:ToString()=='RKA_RingedKnight_Soul')
        local string_id=FText('old');string_id.type=function()return 'FString'end
        soul.SnapSoulTextID=string_id
        Definition.apply_row(row,assets)
        assert(soul.SnapSoulTextID=='RKA_RingedKnight_Soul')
        assert(not pcall(function()Definition.apply_row(original,assets)end))
        local own={ItemId=FName('RKA_RingedKnight'),WeaponUpLevelDatas=row.WeaponUpLevelDatas,
            WeaponAbilityDesc=row.WeaponAbilityDesc}
        local forbidden={config='/Game/Original/Tang.Tang',soul_config=assets.soul_config,soft=soft}
        assert(not pcall(function()Definition.apply_row(own,forbidden)end))
        local defs=Definition.upgrade_defs()
        assert(Upgrade.expected_multiplier(defs,1)==1 and Upgrade.expected_multiplier(defs,60)==6.9)
        assert(not pcall(function()Upgrade.expected_multiplier(defs,61)end))
        local saved_level,native_strength,native_maximum,native_found=1,1,30,true
        local backpack={}
        function backpack:GetWeaponLevel(id,normal)assert(id:ToString()=='RKA_RingedKnight' and normal);return saved_level end
        function backpack:GetWeaponMaxLevel(_,normal)assert(normal);return native_maximum end
        function backpack:GetWeaponAttackMultipliers(owner,config,out)
            assert(owner=='hero' and config=='config' and type(out)=='table')
            if native_found then out.WeaponStrengthMultiplier=native_strength end
            return native_found
        end
        assert(Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')==1)
        native_found=false
        local base,details=Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')
        assert(base==1 and details.helper_returned==false and details.source=='native-base-level-one')
        saved_level=2
        assert(not pcall(function()Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')end))
        native_found='false';saved_level=1
        assert(not pcall(function()Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')end))
        native_found=true
        local level,maximum=Upgrade.level(backpack,'RKA_RingedKnight')
        assert(level==1 and maximum==30)
        for _,cap in ipairs({30,35,40,45,50,55,60})do
            saved_level,native_maximum=cap,cap
            local current,limit=Upgrade.level(backpack,'RKA_RingedKnight')
            assert(current==cap and limit==cap)
        end
        native_maximum=30;saved_level=31
        assert(not pcall(function()Upgrade.level(backpack,'RKA_RingedKnight')end))
        saved_level=1;native_maximum=61
        assert(not pcall(function()Upgrade.level(backpack,'RKA_RingedKnight')end))
        native_maximum=0
        assert(not pcall(function()Upgrade.level(backpack,'RKA_RingedKnight')end))
        native_maximum=60
        saved_level,native_strength=60,6.9
        assert(Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')==6.9)
        native_strength=7.4 -- reported native scalar stays authoritative; no hardcoded table fallback
        assert(Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')==7.4)
        saved_level=0
        assert(not pcall(function()Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')end))
        saved_level=1;native_strength=0/0
        assert(not pcall(function()Upgrade.multiplier(backpack,'hero','config','RKA_RingedKnight')end))
        assert(not pcall(function()Upgrade.level(backpack,'Tang')end))
    ''')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(raw).hexdigest()
    checks = ["native 59-entry economy exact", "source extraction unchanged", "runtime/report JSON identical",
              "owned row guard", "in-place nested metadata", "two supplied formal sections and a cleared third native slot",
              "all original rows preserved in mock", "foreign Tang effects removed only from clone",
              "native soul cost retained and mod-owned variant required", "native scalar OutParm binding",
              "level 1 and 60 strength", "native current cycle caps 30 through 60 retained",
              "native helper false at level 1 means identity upgrade factor", "upgraded helper miss never falls back to base",
              "non-boolean helper return rejected",
              "UTF8 FNV keys resolve all item and move text while empty/original keys stay untouched",
              "localization keys are stable and exported lookup copies cannot mutate live text",
              "two existing UI structure slots carry owned physical/fire names, icons and empty curves instead of fallback 50/25",
              "display base values match the actual combat profile 242 physical and 23 fire",
              "native White and soul WhiteIcon use the colored list preview while bloom and upgrade masks remain separate",
              "level above native cap and cap outside schema rejected", "native soul multiplier authoritative", "invalid levels/NaN fail closed"]
    output = {"status": "passed_offline", "checks": checks, "game_launched": False,
              "installed": False, "native_ui_or_upgrade_runtime_verified": False}
    (ROOT / "reports/item-definition-tests.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"PASS {len(checks)} offline item/upgrade contracts; native runtime acceptance remains pending.")


if __name__ == "__main__":
    run()
