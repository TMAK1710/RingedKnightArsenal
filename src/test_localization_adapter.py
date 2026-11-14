"""Offline native-hook argument/FText/lifecycle contracts; no UI acceptance claim."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/runtime/RingedKnightArsenal/Scripts/LocalizationAdapter.lua'
sys.path.insert(0,str(ROOT/'tools/lua-python'))
from lupa.lua54 import LuaRuntime


class NativeFlowParameter:
    """Python objects appear as userdata to Lua, unlike the table fixtures."""

    def __init__(self, parameter_type, key):
        self.parameter_type = parameter_type
        self.value = type('NativeFlowLocText', (), {'Key': key})()

    def type(self):
        return self.parameter_type

    def get(self):
        return self.value


SETUP=r'''
PATH='/Script/ProjectPBZ.PBZBlueprintFunctionLibrary:MakeTextByKey'
schema={'StrProperty '..PATH..':Key','TextProperty '..PATH..':ReturnValue'}
registrations={};removals={};made_texts=0;lookup_calls=0;mapping={RKA_Name='环印骑士剑',RKA_Empty=''}
function FText(source)
 assert(type(source)=='string');made_texts=made_texts+1
 return {type=function()return 'FText'end,ToString=function()return source end}
end
function remote(value)return {get=function()return value end}end
function StaticFindObject(path)
 if path==FLOW_PATH and flow_schema then
  return {IsValid=function()return true end,GetFullName=function()return 'Function '..path end,
   ForEachProperty=function(_,each)for _,value in ipairs(flow_schema)do local field=value;each({GetFullName=function()return field end})end end}
 end
 assert(path==PATH)
 return {IsValid=function()return not missing end,GetFullName=function()return 'Function '..PATH end,
  ForEachProperty=function(_,fn)for _,field in ipairs(schema)do
   local name=field;fn({GetFullName=function()return name end})
  end end}
end
function RegisterHook(path,pre,post)
 assert((path==PATH or path==WIDGET_PATH or path==FLOW_PATH) and type(pre)=='function' and type(post)=='function')
 local n=#registrations;registrations[n+1]={path=path,pre=pre,post=post}
 return 71+n*2,72+n*2
end
function UnregisterHook(path,pre,post)
 removals[#removals+1]={path=path,pre=pre,post=post}
 if fail_unregister then error('mock unregister failure')end
end
function lookup(key)lookup_calls=lookup_calls+1;return mapping[key]end
function call(hook,key)
 local original=FText('native:'..key)
 assert(hook.pre(remote({}),remote(key))==nil)
 local replaced=hook.post(remote({}),remote(original),remote(key))
 return replaced or original
end
function widget_fixture()
 WIDGET_PATH='/Script/ActualWidgetModule.PBZCommonLocText:SetTextByLocKey'
 SETTEXT_PATH='/Script/ActualBaseModule.NativeTextBase:SetText'
 widget_key_schema={'StrProperty '..WIDGET_PATH..':LocKey'}
 settext_schema={'TextProperty '..SETTEXT_PATH..':InText'}
 FORMAT_PATH='/Script/ActualWidgetModule.PBZCommonLocText:SetPBZFormatText'
 format_schema={'TextProperty '..FORMAT_PATH..':InText'}
 local function fn(path,fields)
  return {IsValid=function()return true end,GetFullName=function()return 'Function '..path end,
   GetFName=function()return {ToString=function()return path:match(':([^:]+)$')end}end,
   ForEachProperty=function(_,each)for _,value in ipairs(fields)do local field=value;each({GetFullName=function()return field end})end end}
 end
 local base={IsValid=function()return true end,ForEachFunction=function(_,each)each(fn(SETTEXT_PATH,settext_schema))end,
  GetSuperStruct=function()return nil end}
 local class={IsValid=function()return not widget_class_missing end,
  GetFullName=function()return 'Class /Script/ActualWidgetModule.PBZCommonLocText'end,
  GetFName=function()return {ToString=function()return 'PBZCommonLocText'end}end,
  ForEachFunction=function(_,each)each(fn(WIDGET_PATH,widget_key_schema));if not missing_format then each(fn(FORMAT_PATH,format_schema))end end,
  GetSuperStruct=function()return base end}
 FindObject=function(kind,name)assert(kind=='Class' and name=='PBZCommonLocText');return class end
 widget={writes=0,plain_writes=0,format_writes=0,IsValid=function()return not widget_invalid end,SetText=function(self,value)
  assert(value:type()=='FText');if widget_write_error then error('mock setter error')end
  self.writes=self.writes+1;self.plain_writes=self.plain_writes+1;self.value=value:ToString()
 end,SetPBZFormatText=function(self,value)
  assert(value:type()=='FText');if widget_write_error then error('mock setter error')end
  self.writes=self.writes+1;self.format_writes=self.format_writes+1;self.value=value:ToString()
 end}
end
function flow_fixture()
 FLOW_PATH='/Script/ProjectPBZ.EventPipelineManager:Conv_LocTextToText'
 flow_schema={'StructProperty '..FLOW_PATH..':InLocText','TextProperty '..FLOW_PATH..':ReturnValue'}
end
function call_flow(hook,key)
 local original=FText('native-flow:'..key)
 local field=setmetatable({Key=key},{__index=function(_,name)error('Converter must not inspect '..name)end})
 local replaced=hook.post(remote({}),remote(original),remote(field))
 return replaced or original
end
function call_widget(hook,key,has_return)
 widget.value='native:'..key
 local context=remote(widget)
 local result
 if has_return then result=hook.post(context,remote(false),remote(key))
 else result=hook.post(context,remote(key))end
 assert(result==nil,'Native setter return must be preserved')
 return widget.value
end
'''
CASES={
 'construction_does_not_register_until_explicit_main_state_call':r'''
local a=Adapter.new(lookup);assert(#registrations==0 and not a.active)
local s=a:register();assert(s.verified and s.input_count==1 and s.text_return_count==1)
assert(s.input_type=='StrProperty' and #registrations==1 and a.active)
''',
 'post_hook_reads_key_after_original_return_and_returns_FText':r'''
local a=Adapter.new(lookup);a:register();local value=call(registrations[1],'RKA_Name')
assert(value:type()=='FText' and value:ToString()=='环印骑士剑' and a.hits==1)
''',
 'original_and_unknown_keys_keep_native_return':r'''
local a=Adapter.new(lookup);a:register()
assert(call(registrations[1],'Weapon_001'):ToString()=='native:Weapon_001' and lookup_calls==0)
assert(call(registrations[1],'RKA_Unknown'):ToString()=='native:RKA_Unknown' and a.hits==0)
''',
 'NameProperty_input_and_FName_wrapper_are_supported':r'''
schema[1]='NameProperty '..PATH..':Key';local a=Adapter.new(lookup);a:register()
local name={ToString=function()return 'RKA_Name'end}
local value=registrations[1].post(remote({}),remote(FText('original')),remote(name))
assert(value:ToString()=='环印骑士剑')
''',
 'mapped_empty_text_is_an_explicit_FText_override':r'''
local a=Adapter.new(lookup);a:register();assert(call(registrations[1],'RKA_Empty'):ToString()=='')
''',
 'all_text_categories_share_key_lookup':r'''
for _,category in ipairs({'Name','EquipDescription','Simple','ShortIntroduction','SoulName','SoulDescription','SoulSimple','Move1Title','Move1Desc','Move2Title','Move2Desc','Move3Title','Move3Desc','Upgrade1','Upgrade30','Upgrade60'})do
 mapping['RKA_'..category]='源文:'..category
end
local a=Adapter.new(lookup);a:register()
for key,value in pairs(mapping)do assert(call(registrations[1],key):ToString()==value)end
''',
 'duplicate_registration_is_idempotent':r'''
local a=Adapter.new(lookup);local first=a:register();assert(a:register()==first and #registrations==1)
''',
 'dispose_unregisters_both_ids_and_makes_saved_callback_inert':r'''
local a=Adapter.new(lookup);a:register();local saved=registrations[1].post
a:dispose();assert(not a.active and #removals==1)
assert(removals[1].path==PATH and removals[1].pre==71 and removals[1].post==72)
assert(saved(remote({}),remote(FText('native')),remote('RKA_Name'))==nil)
a:dispose();assert(#removals==1)
''',
 'reregister_keeps_old_generation_callback_inert':r'''
local a=Adapter.new(lookup);a:register();local old=registrations[1].post
a:dispose();a:register()
assert(#registrations==2 and old(remote({}),remote(FText('native')),remote('RKA_Name'))==nil)
assert(call(registrations[2],'RKA_Name'):ToString()=='环印骑士剑')
''',
 'source_change_invalidates_cached_FText':r'''
local a=Adapter.new(lookup);a:register();local one=call(registrations[1],'RKA_Name')
local two=call(registrations[1],'RKA_Name');assert(one==two)
mapping.RKA_Name='已更新源文';local three=call(registrations[1],'RKA_Name')
assert(three~=one and three:ToString()=='已更新源文')
''',
 'mismatched_return_schema_fails_before_registering':r'''
schema[2]='StrProperty '..PATH..':ReturnValue';local a=Adapter.new(lookup)
assert(not pcall(a.register,a) and #registrations==0 and not a.active)
''',
 'extra_or_unsupported_input_fails_before_registering':r'''
schema[3]='BoolProperty '..PATH..':Extra';local a=Adapter.new(lookup)
assert(not pcall(a.register,a) and #registrations==0)
''',
 'missing_function_or_main_state_hook_api_fails_closed':r'''
missing=true;local a=Adapter.new(lookup);assert(not pcall(a.register,a) and #registrations==0)
missing=false;RegisterHook=nil;assert(not pcall(a.register,a) and not a.active)
''',
 'non_string_lookup_cannot_override_return':r'''
mapping.RKA_Name={bad=true};local a=Adapter.new(lookup);a:register()
assert(not pcall(call,registrations[1],'RKA_Name') and a.hits==0)
''',
 'unregister_failure_still_makes_callback_inert':r'''
local a=Adapter.new(lookup);a:register();fail_unregister=true
assert(not pcall(a.dispose,a) and not a.active)
assert(registrations[1].post(remote({}),remote(FText('native')),remote('RKA_Name'))==nil)
''',
 'optional_widget_owner_and_inherited_SetText_are_discovered_from_real_UClass':r'''
widget_fixture();local a=Adapter.new(lookup);local schema=a:register()
assert(schema.widget.verified and #registrations==2)
assert(schema.widget.key.path==WIDGET_PATH and schema.widget.set_text.path==SETTEXT_PATH)
assert(call_widget(registrations[2],'RKA_Name',false)=='环印骑士剑')
assert(widget.writes==1 and a.widget_hits==1 and not a.widget_error)
''',
 'void_widget_post_hook_reads_key_immediately_after_context':r'''
widget_fixture();local a=Adapter.new(lookup);a:register()
local hook=registrations[2]
assert(call_widget(hook,'RKA_Name',false)=='环印骑士剑')
assert(call_widget(hook,'Weapon_001',false)=='native:Weapon_001')
assert(call_widget(hook,'RKA_Unknown',false)=='native:RKA_Unknown' and widget.writes==1)
''',
 'boolean_return_widget_hook_reads_key_after_original_return_and_keeps_result':r'''
widget_fixture();widget_key_schema[2]='BoolProperty '..WIDGET_PATH..':ReturnValue'
local a=Adapter.new(lookup);local schema=a:register()
assert(schema.widget.verified and schema.widget.key.return_count==1)
assert(call_widget(registrations[2],'RKA_Name',true)=='环印骑士剑' and a.widget_hits==1)
''',
 'widget_NameProperty_accepts_FName_key_and_source_updates_invalidate_cache':r'''
widget_fixture();widget_key_schema[1]='NameProperty '..WIDGET_PATH..':LocKey'
local a=Adapter.new(lookup);a:register()
local key={ToString=function()return 'RKA_Name'end}
registrations[2].post(remote(widget),remote(key));assert(widget.value=='环印骑士剑')
mapping.RKA_Name='简介更新';registrations[2].post(remote(widget),remote(key))
assert(widget.value=='简介更新' and widget.writes==2)
''',
 'unexpected_optional_widget_schema_does_not_block_main_text_hook':r'''
widget_fixture();widget_key_schema[2]='BoolProperty '..WIDGET_PATH..':Extra'
local a=Adapter.new(lookup);local schema=a:register()
assert(not schema.widget.verified and a.widget_error and #registrations==1 and a.active)
assert(call(registrations[1],'RKA_Name'):ToString()=='环印骑士剑')
''',
 'missing_optional_UClass_or_wrong_SetText_schema_never_registers_widget_hook':r'''
widget_fixture();widget_class_missing=true;local a=Adapter.new(lookup);a:register()
assert(a.active and not a.widget_schema and #registrations==1)
a:dispose();widget_class_missing=false;settext_schema[1]='StrProperty '..SETTEXT_PATH..':InText'
a:register();assert(a.active and not a.widget_schema and #registrations==2)
''',
 'widget_invalid_context_or_SetText_failure_is_reported_without_throwing':r'''
widget_fixture();local a=Adapter.new(lookup);a:register();widget_invalid=true
assert(call_widget(registrations[2],'RKA_Name',false)=='native:RKA_Name')
assert(a.widget_error and a.widget_hits==0)
widget_invalid=false;widget_write_error=true
assert(call_widget(registrations[2],'RKA_Name',false)=='native:RKA_Name' and a.widget_hits==0)
''',
 'dispose_removes_both_hooks_and_invalidates_saved_widget_callback_generation':r'''
widget_fixture();local a=Adapter.new(lookup);a:register();local old=registrations[2].post
local result=a:dispose();assert(result.unregistered_count==2 and #removals==2)
assert(old(remote(widget),remote('RKA_Name'))==nil and widget.writes==0)
a:register();assert(#registrations==4)
assert(old(remote(widget),remote('RKA_Name'))==nil and widget.writes==0)
assert(call_widget(registrations[4],'RKA_Name',false)=='环印骑士剑')
''',
 'dispose_attempts_every_hook_even_if_native_removal_raises':r'''
widget_fixture();local a=Adapter.new(lookup);a:register();fail_unregister=true
assert(not pcall(a.dispose,a) and not a.active and #removals==2)
assert(registrations[2].post(remote(widget),remote('RKA_Name'))==nil and widget.writes==0)
''',
 'actual_PBZ_formatter_is_preferred_over_inherited_TextBlock_setter':r'''
widget_fixture();local a=Adapter.new(lookup);local schema=a:register()
assert(schema.widget.format_text.verified and schema.widget.format_text.path==FORMAT_PATH)
assert(call_widget(registrations[2],'RKA_Name',false)=='环印骑士剑')
assert(widget.format_writes==1 and widget.plain_writes==0 and a.widget_calls==1)
''',
 'unavailable_optional_formatter_retains_validated_plain_setter_fallback':r'''
widget_fixture();missing_format=true;local a=Adapter.new(lookup);a:register()
assert(call_widget(registrations[2],'RKA_Name',false)=='环印骑士剑')
assert(widget.plain_writes==1 and widget.format_writes==0)
''',
 'FlowLocText_converter_reads_only_own_scalar_key_and_overrides_FText_return':r'''
flow_fixture();local a=Adapter.new(lookup);local schema=a:register()
assert(schema.flow.verified and #registrations==2)
assert(call_flow(registrations[2],'RKA_Name'):ToString()=='环印骑士剑')
assert(a.flow_hits==1 and a.flow_calls==1)
''',
 'FlowLocText_unwraps_pinned_local_and_remote_userdata_parameter_types':r'''
flow_fixture();local a=Adapter.new(lookup);a:register()
local post=registrations[2].post
for _,kind in ipairs({'LocalUnrealParam','RemoteUnrealParam'})do
 local parameter=native_flow_parameter(kind,'RKA_Name')
 assert(type(parameter)=='userdata' and parameter:type()==kind)
 assert(post(remote({}),remote(FText('native')),parameter):ToString()=='环印骑士剑')
end
assert(a.flow_hits==2)
''',
 'FlowLocText_original_and_unknown_keys_preserve_native_return':r'''
flow_fixture();local a=Adapter.new(lookup);a:register()
assert(call_flow(registrations[2],'Original_Key'):ToString()=='native-flow:Original_Key')
assert(call_flow(registrations[2],'RKA_Unknown'):ToString()=='native-flow:RKA_Unknown')
assert(a.flow_hits==0 and a.flow_calls==2)
''',
 'FlowLocText_optional_schema_mismatch_never_blocks_primary_hook':r'''
flow_fixture();flow_schema[1]='StrProperty '..FLOW_PATH..':InLocText'
local a=Adapter.new(lookup);local schema=a:register()
assert(a.active and not schema.flow.verified and a.flow_error and #registrations==1)
assert(call(registrations[1],'RKA_Name'):ToString()=='环印骑士剑')
''',
 'all_three_hook_lifetimes_are_disposed_and_converter_saved_callback_is_inert':r'''
widget_fixture();flow_fixture();local a=Adapter.new(lookup);a:register()
assert(#registrations==3);local old=registrations[3].post
local result=a:dispose();assert(result.unregistered_count==3 and #removals==3)
assert(old(remote({}),remote(FText('native')),remote({Key='RKA_Name'}))==nil)
assert(a.flow_hits==0)
a:register();assert(#registrations==6 and call_flow(registrations[6],'RKA_Name'):ToString()=='环印骑士剑')
''',
 'converter_does_not_retain_native_struct_parameter':r'''
flow_fixture();local a=Adapter.new(lookup);a:register()
local weak=setmetatable({},{__mode='k'})
do local field={Key='RKA_Name'};weak[field]=true
 assert(registrations[2].post(remote({}),remote(FText('native')),remote(field)):ToString()=='环印骑士剑')
end
collectgarbage('collect');assert(next(weak)==nil)
''',
}
results=[]
for name,body in CASES.items():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().native_flow_parameter=NativeFlowParameter
    lua.globals().Adapter=lua.execute(SOURCE.read_text(encoding='utf-8'))
    try:
        lua.execute(SETUP);lua.execute(body);results.append({'name':name,'pass':True});print('PASS',name)
    except Exception as error:
        results.append({'name':name,'pass':False,'error':str(error)});print('FAIL',name,error)
(ROOT/'reports/localization-adapter-tests.json').write_text(json.dumps({
 'scope':'Real Lua adapter with pinned UE4SS native post-hook argument order, mocked UFunction/FText; actual game schema and visible UI not yet verified.',
 'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'native_schema_verified':False,
 'runtime_hook_return_verified':False,'runtime_ui_text_verified':False,'cases':results},indent=2),encoding='utf-8')
raise SystemExit(any(not c['pass'] for c in results))
