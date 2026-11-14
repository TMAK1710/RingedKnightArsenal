"""Offline pickup leaf-image fit/restore contracts, not a game visual test."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/runtime/RingedKnightArsenal/Scripts/ItemDisplayAdapter.lua'
sys.path.insert(0,str(ROOT/'tools/lua-python'))
from lupa.lua54 import LuaRuntime

SETUP=r'''
serial=0;game_thread=true;widgets={};calls={}
function IsInGameThread()return game_thread end
function FName(s)return {ToString=function()return s end}end
function obj(fields)
 serial=serial+1;local address=serial;fields=fields or {}
 fields.IsValid=function(self)return not self.destroyed end;fields.GetAddress=function()return address end
 return fields
end
function image()
 return obj({RenderTransform={Scale={X=1.2,Y=.8}},RenderTransformPivot={X=.1,Y=.9},
  SetRenderScale=function(self,v)
   assert(not self.destroyed);self.RenderTransform.Scale={X=v.X,Y=v.Y};calls[#calls+1]='scale'
  end,
  SetRenderTransformPivot=function(self,v)
   assert(not self.destroyed);self.RenderTransformPivot={X=v.X,Y=v.Y};calls[#calls+1]='pivot'
  end})
end
function widget(id,full)
 return obj({['Item ID']=FName(id),BigIcon2=image(),
  GetFullName=function()return full or 'W_pickupgear_C Test.Popup'end})
end
function FindAllOf(name)if name=='W_ButtonBase_Weapon_C'then return {}end;assert(name=='W_pickupgear_C');return widgets end
registry={get=function(_,id)return id=='RKA_RingedKnight' and {id=id} or nil end}
function original(i)
 return i.RenderTransform.Scale.X==1.2 and i.RenderTransform.Scale.Y==.8
  and i.RenderTransformPivot.X==.1 and i.RenderTransformPivot.Y==.9
end
function fitted(i)
 return i.RenderTransform.Scale.X==.4 and i.RenderTransform.Scale.Y==.4
  and i.RenderTransformPivot.X==.5 and i.RenderTransformPivot.Y==.5
end
'''
CASES={
 'fitted_previews_and_closed_upgrade_need_no_global_scan':r'''
registry.entries={RKA_RingedKnight={preview_canvas_fitted=true}}
FindAllOf=function()error('No UI scan expected during gameplay')end
local a=Adapter.new(registry);local status=a:update(false)
assert(status.applied==0 and status.tracked==0)
''',
 'future_unfitted_weapon_still_updates_pickup':r'''
registry.entries={RKA_RingedKnight={preview_canvas_fitted=false}}
widgets={widget('RKA_RingedKnight')}
local a=Adapter.new(registry);a:update(false);assert(fitted(widgets[1].BigIcon2))
''',
 'unknown_or_original_item_has_no_writes':r'''
local a=Adapter.new(registry);widgets={widget('Tang'),widget('Unknown')}
local status=a:update();assert(#calls==0 and status.applied==0 and status.tracked==0)
assert(original(widgets[1].BigIcon2) and original(widgets[2].BigIcon2))
''',
 'own_item_changes_only_leaf_scale_and_pivot':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight')}
local status=a:update();assert(fitted(widgets[1].BigIcon2) and status.applied==1 and status.tracked==1)
''',
 'fitted_canvas_skips_extra_pickup_scale_and_restores_any_old_transform':r'''
local definition={id='RKA_RingedKnight'}
registry.get=function(_,id)if id==definition.id then return definition end end
local a=Adapter.new(registry);widgets={widget(definition.id)}
a:update();assert(fitted(widgets[1].BigIcon2))
definition.preview_canvas_fitted=true
local status=a:update()
assert(status.applied==0 and status.restored==1 and original(widgets[1].BigIcon2))
local before=#calls
a:update();assert(#calls==before and original(widgets[1].BigIcon2))
''',
 'repeated_update_preserves_original_restore_snapshot':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight')}
a:update();a:update();a:update();local status=a:dispose()
assert(status.restored==1 and status.tracked==0 and original(widgets[1].BigIcon2))
''',
 'same_widget_reused_for_native_ID_restores_original_transform':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight')};a:update()
widgets[1]['Item ID']=FName('Tang');local status=a:update()
assert(original(widgets[1].BigIcon2) and status.restored==1 and status.tracked==0)
local before=#calls;a:update();assert(#calls==before)
''',
 'same_widget_replacing_image_restores_old_and_fits_new_leaf':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight')};a:update()
local old=widgets[1].BigIcon2;widgets[1].BigIcon2=image();local status=a:update()
assert(original(old) and fitted(widgets[1].BigIcon2) and status.restored==1 and status.tracked==1)
''',
 'invalid_image_is_removed_without_calling_invalid_UObject':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight')};a:update()
widgets[1].BigIcon2.destroyed=true;local before=#calls;local status=a:update()
assert(status.tracked==0 and #calls==before);a:dispose();assert(#calls==before)
''',
 'invalid_or_unlisted_widget_is_cleaned_and_remaining_valid_image_restored':r'''
local a=Adapter.new(registry);local w=widget('RKA_RingedKnight');widgets={w};a:update()
w.destroyed=true;local status=a:update();assert(status.tracked==0 and original(w.BigIcon2))
w=widget('RKA_RingedKnight');widgets={w};a:update();widgets={};status=a:update()
assert(status.tracked==0 and original(w.BigIcon2))
''',
 'class_default_widget_is_never_modified':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight','W_pickupgear_C Test.Default__Popup')}
assert(a:update().tracked==0 and #calls==0)
''',
 'update_and_dispose_require_game_thread':r'''
local a=Adapter.new(registry);widgets={widget('RKA_RingedKnight')};game_thread=false
assert(not pcall(a.update,a) and #calls==0)
game_thread=true;a:update();game_thread=false
assert(not pcall(a.dispose,a) and fitted(widgets[1].BigIcon2))
game_thread=true;a:dispose();assert(original(widgets[1].BigIcon2))
''',
}
results=[]
for name,body in CASES.items():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().Adapter=lua.execute(SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP);lua.execute(body);results.append({'name':name,'pass':True});print('PASS',name)
    except Exception as error:
        results.append({'name':name,'pass':False,'error':str(error)});print('FAIL',name,error)
(ROOT/'reports/item-display-adapter-tests.json').write_text(json.dumps({
 'scope':'Real ItemDisplayAdapter under Lua 5.4, mocked UI objects; no in-game visual acceptance.',
 'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'runtime_visual_verified':False,'cases':results},indent=2),encoding='utf-8')
raise SystemExit(any(not c['pass'] for c in results))
