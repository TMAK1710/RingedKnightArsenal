"""Owned upgrade-page prose under strict UI mocks; no live UI acceptance."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/runtime/RingedKnightArsenal/Scripts'
SOURCE = SCRIPTS / 'ItemDisplayAdapter.lua'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

EXTRACT = ROOT / 'extract/upgrade-ui-feedback-20261106/ProjectPBZ/Content'
button_path = EXTRACT / 'PBZContent/UI/UINew/Hud/W_ButtonBase_Weapon.json'
normal_path = EXTRACT / 'PBZContent/UI/UINew/Hud/W_WeaponNormalText.json'
normal = json.loads(normal_path.read_text(encoding='utf-8'))
init = next(item for item in normal if item.get('Type') == 'Function' and item.get('Name') == 'InitText')
assert [(field['Name'], field['Type']) for field in init['ChildProperties']] == [
    ('TitleText', 'TextProperty'), ('DescText', 'TextProperty')]
title = next(item for item in normal if item.get('Name') == 'TitleText')
assert title['Properties']['SavedColorAndOpacity']['SpecifiedColor']['Hex'] == 'E3BF73'
button = json.loads(button_path.read_text(encoding='utf-8'))
init_button = next(item for item in button if item.get('Type') == 'Function' and item.get('Name') == 'InitMainWeapon')
assert 'PBZBackPackSubsystem:GetWeaponWhiteIconFindTable' in json.dumps(init_button)
upgrade_js = EXTRACT / 'JavaScript/UI/Widget/Foundation/UnifiedTextDesc_Weapon.js'
detail_js = EXTRACT / 'JavaScript/UI/Widget/Foundation/WeaponDetailList.js'
assert 'list.refreshAdvancedUpgrade(this.currentWeaponID' in upgrade_js.read_text(encoding='utf-8')
assert 'const geDataList = upLevelData.GEDatas ? Array.from(upLevelData.GEDatas) : [];' in detail_js.read_text(encoding='utf-8')

SETUP = r'''
serial=0;game_thread=true;buttons={};calls={create=0,init=0,remove=0,visibility=0}
function IsInGameThread()return game_thread end
function FText(value)return {ToString=function()return value end}end
function FName(value)return FText(value)end
function obj(fields)
 serial=serial+1;local address=serial;fields=fields or {}
 fields.IsValid=function(self)return not self.destroyed end
 fields.GetAddress=function()return address end
 fields.GetFullName=fields.GetFullName or function()return 'Object Test.Object'end
 fields.GetClass=function(self)return self.class end
 fields.GetOuter=function(self)return self.outer end
 return fields
end
function text_widget()
 return obj({value='',GetText=function(self)return FText(self.value)end,
  SetVisibility=function(self,value)self.visibility=value;calls.visibility=calls.visibility+1 end})
end
normal_class=obj({GetFullName=function()return 'WidgetBlueprintGeneratedClass /Game/PBZContent/UI/UINew/HUD/W_WeaponNormalText.W_WeaponNormalText_C'end})
upgrade_class=obj({GetFullName=function()return 'WidgetBlueprintGeneratedClass /Game/PBZContent/UI/UINew/System/Upgrade/W_UpgradeActivatableWidget_V1.W_UpgradeActivatableWidget_V1_C'end})
other_class=obj({GetFullName=function()return 'WidgetBlueprintGeneratedClass /Game/Other.Other_C'end})
function make_box()
 return obj({entries={},GetAllEntries=function(self)
   if self.fail_read then error('stale optional UI entries')end
   return self.entries
  end,
  BP_CreateEntryOfClass=function(self,class)
   assert(class==normal_class,'Use the real normal-text class, not an upgrade effect/locked entry')
   local widget=obj({TitleText=text_widget(),DescText=text_widget(),
    InitText=function(self,title,description)
     calls.init=calls.init+1
     if self.fail_init then error('optional InitText failure')end
     self.TitleText.value=title:ToString();self.DescText.value=description:ToString()
    end})
   widget.fail_init=self.fail_init
   self.entries[#self.entries+1]=widget;calls.create=calls.create+1;return widget
  end,
  RemoveEntry=function(self,widget)
   for i=#self.entries,1,-1 do if self.entries[i]==widget then table.remove(self.entries,i);calls.remove=calls.remove+1;return end end
   error('Attempt to remove a foreign or non-member widget')
  end})
end
function fixture(id)
 local box=make_box();local list=obj({DynamicEntryBox=box,NormalTextClass=normal_class})
 local owner=obj({class=upgrade_class,activated=true,visible=true,
  W_UnifiedTextDescription_Weapon=obj({W_WeaponDetailList=list}),
  IsActivated=function(self)return self.activated end,IsVisible=function(self)return self.visible end})
 local tree=obj({outer=owner,class=other_class})
 local button=obj({outer=tree,class=other_class,WeaponID=FName(id or 'RKA_RingedKnight'),selected=true,
  GetSelected=function(self)return self.selected end})
 buttons={button};return Adapter.new(registry),owner,box,button,list
end
function FindAllOf(name)
 if name=='W_pickupgear_C'then return {}end
 assert(name=='W_ButtonBase_Weapon_C');return buttons
end
definition=Definition.definition()
registry={get=function(_,id)return id==definition.id and definition or nil end}
function complete(box)
 assert(#box.entries==3)
 assert(box.entries[1].TitleText.value=='' and box.entries[1].DescText.value==definition.description)
 assert(box.entries[1].TitleText.visibility==1)
 for i=1,2 do
  assert(box.entries[i+1].TitleText.value==definition.moves[i].title)
  assert(box.entries[i+1].DescText.value==definition.moves[i].description)
  assert(box.entries[i+1].TitleText.visibility==4)
 end
end
'''
CASES = {
    'gameplay_gate_cleans_owned_prose_and_reopening_restores_it': r'''
local a,owner,box=fixture();local foreign=obj();box.entries={foreign};a:update(true)
assert(#box.entries==4)
a:update(false);assert(#box.entries==1 and box.entries[1]==foreign and calls.remove==3)
a:update(false);assert(calls.remove==3)
box.entries={};a:update(true);complete(box)
''',
    'complete_formal_lore_and_two_gold_title_sections': r'''
local a,owner,box=fixture();local status=a:update()
complete(box);assert(status.upgrade.added==3 and calls.init==3 and not a.upgrade_error)
assert(box.entries[2].TitleText.value=='环印剑术' and box.entries[3].TitleText.value=='二番目の記憶')
assert(box.entries[2].DescText.value:find('第一次轻攻击的伤害×1.5、削韧900。',1,true))
''',
    'stable_updates_write_nothing_and_do_not_append': r'''
local a,owner,box=fixture();a:update()
for i=1,20 do local status=a:update();assert(status.upgrade.added==0 and status.upgrade.removed==0)end
complete(box);assert(calls.create==3 and calls.init==3 and calls.remove==0 and calls.visibility==3)
''',
    'native_reset_rebuilds_once_without_resetting_the_container': r'''
local a,owner,box=fixture();a:update();box.entries={}
local status=a:update();complete(box);assert(status.upgrade.added==3 and calls.create==6 and calls.init==6)
a:update();assert(calls.create==6 and calls.init==6 and calls.remove==0)
''',
    'original_weapon_has_no_ui_writes': r'''
local a,owner,box=fixture('Tang');local foreign=obj();box.entries={foreign}
for i=1,4 do assert(a:update().upgrade.added==0)end
assert(#box.entries==1 and box.entries[1]==foreign)
assert(calls.create==0 and calls.init==0 and calls.remove==0 and calls.visibility==0)
''',
    'switch_to_original_removes_only_owned_entries': r'''
local a,owner,box,button=fixture();local foreign=obj();box.entries={foreign};a:update()
assert(#box.entries==4);button.WeaponID=FName('Tang')
local status=a:update();assert(status.upgrade.removed==3 and #box.entries==1 and box.entries[1]==foreign)
a:update();assert(calls.remove==3 and calls.init==3)
''',
    'closing_or_hiding_upgrade_page_cleans_owned_entries': r'''
local a,owner,box=fixture();a:update();owner.activated=false
assert(a:update().upgrade.removed==3 and #box.entries==0)
a:update();assert(calls.remove==3 and calls.create==3)
owner.activated=true;a:update();complete(box)
owner.visible=false;assert(a:update().upgrade.removed==3 and #box.entries==0)
''',
    'outside_upgrade_or_unselected_owned_button_has_no_writes': r'''
local a,owner,box,button=fixture();owner.class=other_class
a:update();assert(calls.create==0)
owner.class=upgrade_class;button.selected=false;a:update();assert(calls.create==0)
''',
    'duplicate_selected_references_do_not_duplicate_prose': r'''
local a,owner,box,button=fixture();buttons={button,button};a:update();complete(box)
assert(calls.create==3 and calls.init==3)
''',
    'pooled_pointer_reused_for_foreign_text_is_not_removed': r'''
local a,owner,box,button=fixture();a:update();local reused=box.entries[1]
reused.TitleText.value='native';reused.DescText.value='native description'
box.entries={reused};button.WeaponID=FName('Tang');a:update()
assert(#box.entries==1 and box.entries[1]==reused and calls.remove==0)
''',
    'destroyed_userwidgets_and_optional_backend_errors_do_not_escape': r'''
local a,owner,box=fixture();a:update();box.fail_read=true
local ok,status=pcall(a.update,a);assert(ok and status.upgrade.error and a.upgrade_error)
box.fail_read=false;box.destroyed=true
ok,status=pcall(a.update,a);assert(ok and not a.upgrade_error)
local b,owner2,box2=fixture();box2.fail_init=true
ok,status=pcall(b.update,b);assert(ok and status.upgrade.error and #box2.entries==0)
box2.fail_init=false;b:update();complete(box2)
''',
    'dispose_removes_only_owned_entries_and_tolerates_dead_backend': r'''
local a,owner,box=fixture();local foreign=obj();box.entries={foreign};a:update();a:dispose()
assert(#box.entries==1 and box.entries[1]==foreign and calls.remove==3)
local b,owner2,box2=fixture();b:update();box2.fail_read=true
assert(pcall(b.dispose,b))
''',
    'off_thread_updates_never_touch_ui': r'''
local a=fixture();game_thread=false
assert(not pcall(a.update,a) and calls.create==0 and calls.init==0)
assert(not pcall(a.update_upgrade,a))
''',
}
results = []
for name, body in CASES.items():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().scripts = SCRIPTS.as_posix() + '/'
    lua.execute("Definition=dofile(scripts..'RingedKnightDefinition.lua')")
    lua.globals().Adapter = lua.execute(SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP)
        lua.execute(body)
        results.append({'name': name, 'pass': True})
        print('PASS', name)
    except Exception as error:
        results.append({'name': name, 'pass': False, 'error': str(error)})
        print('FAIL', name, error)
(ROOT / 'reports/upgrade-item-display-tests.json').write_text(json.dumps({
    'scope': 'Real Definition/ItemDisplayAdapter in Lua 5.4 with UI mocks; extracted current InitText, title color and list-icon getter contracts.',
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'evidence_sha256': {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (button_path, normal_path, upgrade_js, detail_js)},
    'runtime_visual_verified': False, 'game_launched': False, 'installation_modified': False,
    'cases': results,
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
raise SystemExit(any(not case['pass'] for case in results))
