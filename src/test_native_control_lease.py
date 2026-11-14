from pathlib import Path
import sys,json
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/lua-python'))
from lupa.lua54 import LuaRuntime
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().module_path=(root/'src/runtime/RingedKnightArsenal/Scripts/NativeControlLease.lua').as_posix()
lua.execute("M=dofile(module_path)")
cases={
'only_observed_menu_can_release':'''g=M.new();assert(not g:observe({identity='p',onlylook=true,owner=1,serial=2},0));assert(not g:observe({identity='p',onlylook=true,owner=1,serial=2},30))''',
'closed_menu_quiet_then_one_release':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;assert(not g:observe(s,1));assert(not g:observe(s,1.5));local t=g:observe(s,1.7);assert(t.serial==2);assert(not g:observe(s,10))''',
'open_ui_never_release':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};for i=0,50 do assert(not g:observe(s,i))end''',
'newer_lease_preserved':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;g:observe(s,1);s.serial=3;assert(not g:observe(s,5));assert(not g.ticket)''',
'foreign_owner_preserved':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;s.owner=3;assert(not g:observe(s,10));assert(not g.ticket)''',
'world_or_pawn_change_discards':'''g=M.new();s={identity='p1',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;s.identity='p2';assert(not g:observe(s,10));assert(not g.ticket)''',
'native_interaction_animation_dialogue_loading_prevents_release':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;s.busy=true;for i=1,30 do assert(not g:observe(s,i))end;s.busy=false;assert(not g:observe(s,31));assert(g:observe(s,32).serial==2)''',
'native_normal_return_clears_ticket':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;s.onlylook=false;assert(not g:observe(s,10));assert(not g.ticket)''',
'nested_menu_stays_native':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.serial=3;g:observe(s,5);s.ui=false;assert(not g:observe(s,6));assert(g:observe(s,7).serial==3)''',
'reopened_menu_resets_quiet':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;g:observe(s,1);s.ui=true;g:observe(s,2);s.ui=false;assert(not g:observe(s,10));assert(g:observe(s,11))''',
'new_input_mode_never_cleared':'''g=M.new();s={identity='p',onlylook=true,owner=1,serial=2,ui=true};g:observe(s,0);s.ui=false;s.onlylook=false;g:observe(s,1);s.onlylook=true;s.serial=4;assert(not g:observe(s,99))'''
}
cases.update({
'menu_exit_creates_onlylook_after_ui_was_unrestricted':'''g=M.new();s={identity='p',ui=true};g:observe(s,0);s.ui=false;s.onlylook=true;s.owner=1;s.serial=29;assert(not g:observe(s,5));assert(g:observe(s,5.7).serial==29)''',
'exit_edge_can_arrive_one_poll_after_ui_closes':'''g=M.new();s={identity='p',ui=true};g:observe(s,0);s.ui=false;g:observe(s,1);s.onlylook=true;s.owner=1;s.serial=29;assert(not g:observe(s,1.2));assert(g:observe(s,2).serial==29)''',
'unrelated_later_onlylook_after_menu_is_not_released':'''g=M.new();s={identity='p',ui=true};g:observe(s,0);s.ui=false;g:observe(s,1);s.onlylook=true;s.owner=1;s.serial=29;assert(not g:observe(s,2));assert(not g:observe(s,5));assert(not g.ticket)''',
'exit_cutscene_remains_in_control':'''g=M.new();s={identity='p',ui=true};g:observe(s,0);s.ui=false;s.onlylook=true;s.owner=1;s.serial=29;s.busy=true;for i=1,10 do assert(not g:observe(s,i))end;s.serial=30;s.busy=false;assert(not g:observe(s,11));assert(not g:observe(s,15))'''
})
cases.update({
'pre_interaction_release_precedes_native_holster_and_filters_other_owners': r'''
local serial=0
local function obj(t)serial=serial+1;local id=serial;t=t or {};t.IsValid=function()return true end;t.GetAddress=function()return id end;return t end
local pawn,target,other=obj(),obj(),obj();local callbacks={};local removed={};local order={}
StaticFindObject=function(path)return obj({GetFullName=function()return 'Function '..path end})end
RegisterHook=function(path,fn)callbacks[path]=fn;return 41,42 end
UnregisterHook=function(path,a,b)assert(a==41 and b==42);removed[path]=true end
g=M.new(function()order[#order+1]='release';return true end);g.pawn=pawn;g:register_interaction();g:register_interaction()
local path='/Script/ProjectPBZ.PBZInteractComponent:DoInteract'
local c=obj({GetOwner=function()return pawn end});callbacks[path]({get=function()return c end},{get=function()return target end});order[#order+1]='native_holster'
assert(order[1]=='release'and order[2]=='native_holster');assert(g.interaction_watch.actor==target and g.interaction_watch.pawn==pawn)
callbacks[path](obj({GetOwner=function()return other end}),target);assert(#order==2)
g:dispose();assert(removed[path]and not g.interaction_hook and not g.interaction_watch)
callbacks[path](c,target);assert(#order==2)
''',
'whole_interaction_ownership_does_not_confuse_nearby_prompts_with_active_interaction': r'''
local function obj(id,t)t=t or {};t.IsValid=function()return true end;t.GetAddress=function()return id end;return t end
local pawn,other=obj(1),obj(2);local actor=nil;local seq=false
g=M.new();g.pawn=pawn;g.interact=obj(3,{GetInteractingActor=function()return actor end,HasValidLevelSequencePlayer=function()return seq end,CurrentInteractActor=obj(4)})
assert(not g:interaction_active(pawn));actor=obj(5);assert(g:interaction_active(pawn));assert(not g:interaction_active(other))
actor=nil;g.interact.FadeInteractActor=obj(6);assert(g:interaction_active(pawn));g.interact.FadeInteractActor=nil;seq=true;assert(g:interaction_active(pawn));seq=false;assert(not g:interaction_active(pawn))
'''
})

cases.update({
'completed_wait_needs_stable_positive_evidence_and_runs_once': '''g=M.new();g.interaction_watch={};s={same_interaction=true,completed=true,waiting=true,serial=17,flow_owner=1,task_address=2};assert(not g:observe_completed_interaction(s,0));assert(not g:observe_completed_interaction(s,.8));assert(g:observe_completed_interaction(s,1.1));assert(not g:observe_completed_interaction(s,20))''',
'completion_timeout_never_skips_unfinished_content': '''g=M.new();g.interaction_watch={};s={same_interaction=true,completed=false,waiting=true,serial=17,flow_owner=1,task_address=2};for i=0,100 do assert(not g:observe_completed_interaction(s,i))end''',
'new_task_or_input_serial_restarts_completion_grace': '''g=M.new();g.interaction_watch={};s={same_interaction=true,completed=true,waiting=true,serial=17,flow_owner=1,task_address=2};g:observe_completed_interaction(s,0);s.serial=18;assert(not g:observe_completed_interaction(s,2));s.task_address=3;assert(not g:observe_completed_interaction(s,4));assert(not g:observe_completed_interaction(s,4.5));assert(g:observe_completed_interaction(s,5.1))''',
'busy_animation_dialogue_sequence_resets_completion_grace': '''g=M.new();g.interaction_watch={};s={same_interaction=true,completed=true,waiting=true,serial=17,flow_owner=1,task_address=2};g:observe_completed_interaction(s,0);s.busy=true;assert(not g:observe_completed_interaction(s,3));s.busy=false;assert(not g:observe_completed_interaction(s,4));assert(g:observe_completed_interaction(s,5.1))''',
'no_observed_interaction_never_recovers_and_owner_change_discards': '''g=M.new();s={same_interaction=true,completed=true,waiting=true};assert(not g:observe_completed_interaction(s,100));g.interaction_watch={};s.same_interaction=false;assert(not g:observe_completed_interaction(s,101));assert(not g.interaction_watch)''',
})

fixture=r'''
local id=0
local function obj(t)id=id+1;local address=id;t=t or {};t.IsValid=function()return true end;t.GetAddress=function()return address end;return t end
FName=function(x)return x end
local done=true;local busy=false;local seq=false;local has_choice=false;local subtitle_done=true;local endcount=0;local removed=0;local ended=false;local serial=17
local now=0;local on_end;local native_tags={};local local_abilities={}
local task=obj({EndAction=function()endcount=endcount+1 end})
local inst=obj({GetCurrentActiveMontage=function()if busy then return obj()end end})
local world=obj()
local pawn=obj({GetWorld=function()return world end,Mesh=obj({GetAnimInstance=function()return inst end}),K2_GetComponentsByClass=function()return local_abilities end})
local flow=obj({LoadComplete=true,StreamComplete=true,FlowPlaySeqID='',GetCurrentAffectFlowNode=function()end,GetLastRegisteredInputTypeSerial=function()return serial end,UnRegisterInputTypeIfUnchanged=function(self,tag,t)assert(tag.TagName=='InputType.OnlyLook' and t==19);removed=removed+1;return true end})
local fc=obj({CurrentSubtitle=obj({IsExecuteDone=function()return subtitle_done end}),CurrentChoiceNode={},CurrentExecuteNode={obj({IsExecuteDone=function()return done end})},GetBranchLock=function()return false end})
local actor=obj({IsA=function()return true end,GetFullName=function()return 'ObservedFlowActor' end,BP_PBZFlowComponent=fc,['Change Arm Async Action']=task,ReadyToEndInteract=function()assert(endcount==1);ended=true;serial=19;if on_end then on_end()end end})
local asc_owner=pawn;local asc_present=true
local asc=obj({GetOwner=function()return asc_owner end,HasMatchingGameplayTag=function(_,tag)return native_tags[tag.TagName]==true end})
StaticFindObject=function()return obj({GetRealTimeSeconds=function()return now end})end
local g=M.new(nil,nil,function()if asc_present then return asc end end);g.pawn=pawn;g.pc=obj();g.interaction_watch={actor=actor,pawn=pawn};g.interact=obj({GetInteractingActor=function()if not ended then return actor end end,HasValidLevelSequencePlayer=function()return false end})
g.sequence_busy=function()return seq end
g.snapshot=function()return {identity='p',owner=flow:GetAddress(),onlylook=true,flow=flow,serial=serial,ui=false,busy=busy or g:native_ability_busy(pawn)}end
local s={identity='p',owner=flow:GetAddress(),flow=flow,onlylook=true,serial=17,ui=false}
'''
cases['native_completed_wait_uses_original_exit_and_new_exact_serial']=fixture+r'''
subtitle_done=false;g:recover_completed_interaction(s,-1);subtitle_done=true;g:recover_completed_interaction(s,0);assert(endcount==0);g:recover_completed_interaction(s,1.1);assert(endcount==1 and ended and removed==1);assert(g.last_interaction_recovery.serial_before==17 and g.last_interaction_recovery.serial_after==19);g:recover_completed_interaction(s,2);assert(endcount==1)
'''
cases['native_completed_wait_survives_sequence_and_restarts_quiet']=fixture+r'''
local scans=0;g.sequence_busy=function()scans=scans+1;return seq end
g.interaction_watch.narrative_seen=true;seq=true
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,.5);assert(scans==0)
g:recover_completed_interaction(s,1.1)
assert(scans==1 and g.interaction_watch and not g.interaction_watch.quiet_since and endcount==0)
seq=false;g:recover_completed_interaction(s,2);g:recover_completed_interaction(s,2.5)
assert(scans==1 and endcount==0)
g:recover_completed_interaction(s,3.1)
assert(scans==3 and endcount==1 and ended and removed==1 and not g.interaction_watch)
g:recover_completed_interaction(s,5);assert(scans==3 and endcount==1)
'''
cases['menu_ticket_survives_sequence_and_only_scans_at_release_boundary']=r'''
local id=0
local function obj(t)id=id+1;local address=id;t=t or {};t.IsValid=function()return true end;t.GetAddress=function()return address end;return t end
FName=function(x)return x end
local now=0;local scans=0;local removed=0;local seq=true
local world=obj();local pawn=obj({GetWorld=function()return world end});local pc=obj()
local flow=obj({UnRegisterInputTypeIfUnchanged=function(_,tag,serial)
 assert(tag.TagName=='InputType.OnlyLook' and serial==3);removed=removed+1;return true end})
local gameplay=obj({GetRealTimeSeconds=function()return now end})
StaticFindObject=function(path)assert(path=='/Script/Engine.Default__GameplayStatics');return gameplay end
local g=M.new();g.pawn=pawn
local s={identity='p',ui=true,onlylook=true,owner=flow:GetAddress(),serial=3,flow=flow}
g.snapshot=function()s.busy=false;return s end
g.sequence_busy=function(_,w)assert(w==world);scans=scans+1;return seq end
g:update(pc,pawn);now=.5;g:update(pc,pawn);assert(scans==0)
s.ui=false;now=1;g:update(pc,pawn);assert(scans==0)
now=1.7;g:update(pc,pawn)
assert(not g.disabled and scans==1 and g.ticket and not g.ticket.quiet_since and removed==0)
seq=false;now=2;g:update(pc,pawn);now=2.5;g:update(pc,pawn)
assert(scans==1 and removed==0)
now=2.7;g:update(pc,pawn)
assert(scans==2 and removed==1 and not g.ticket)
now=4;g:update(pc,pawn);assert(scans==2 and removed==1)
'''
for gate,mutation in {'stale_subtitle_from_previous_visit':'g.interaction_watch.narrative_seen=nil','unfinished_node':'done=false','unfinished_subtitle':'subtitle_done=false','choice':'fc.CurrentChoiceNode={obj()}','montage':'busy=true','sequence':'seq=true','ui':'s.ui=true','missing_wait':"actor['Change Arm Async Action']=nil",'missing_completion':'fc.CurrentSubtitle=nil','active_arm_ability':'asc.HasMatchingGameplayTag=function()return true end','loading':'flow.LoadComplete=false','move_task':"actor['Move To Async Task']=obj()"}.items():
 cases['native_recovery_preserves_'+gate]=fixture+'g.interaction_watch.narrative_seen=true;'+mutation+''';g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,2);assert(endcount==0 and removed==0 and not ended)'''

for tag in ('Ability.Action.Hun.SimpleExecution','Ability.Action.Hun.PerfectDodge'):
 cases['native_recovery_preserves_'+tag]=fixture+f'''
g.interaction_watch.narrative_seen=true;native_tags['{tag}']=true
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,2)
assert(endcount==0 and removed==0 and not ended)
native_tags['{tag}']=nil;g:recover_completed_interaction(s,3);g:recover_completed_interaction(s,4.1)
assert(endcount==1 and removed==1 and ended)
'''

edge_fixture=r'''
local id=0
local function obj(t)id=id+1;local address=id;t=t or {};t.IsValid=function()return true end;t.GetAddress=function()return address end;return t end
local function wrap(x)return {get=function()return x end}end
FName=function(x)return x end
local now=0;local paused=false;local ui=false;local leases={};local released=0;local unregistered=0
local callbacks={};local disposed={};local order={};local logs={};local scans=0
local world=obj();local active_world=world;local foreign_world=obj()
local instance=obj({GetCurrentActiveMontage=function()end})
local pawn=obj({GetWorld=function()return active_world end,Mesh=obj({GetAnimInstance=function()return instance end})})
local native_tags={};local asc_owner=pawn;local asc_present=true;local local_abilities={};local local_queries=0
local asc=obj({GetOwner=function()return asc_owner end,HasMatchingGameplayTag=function(_,tag)return native_tags[tag.TagName]==true end})
pawn.K2_GetComponentsByClass=function(_,class)local_queries=local_queries+1;return local_abilities end
local pc=obj({Player=obj(),bShowMouseCursor=false})
local input=obj({InputTagContainer={ForEach=function(_,fn)for _,owner in ipairs(leases)do fn(wrap(owner),wrap({TagName='InputType.OnlyLook'}))end end}})
local interact=obj({GetInteractingActor=function()end,HasValidLevelSequencePlayer=function()return false end})
local router=obj({GetActiveInputMode=function()return ui and 0 or 1 end})
local function newflow(outer)
 return obj({serial=0,LoadComplete=true,StreamComplete=true,FlowPlaySeqID='',
  GetFullName=function()return 'EventPipelineManager Test' end,GetOuter=function()return outer end,
  GetCurrentAffectFlowNode=function()end,GetLastRegisteredInputTypeSerial=function(self)return self.serial end,
  UnRegisterInputTypeIfUnchanged=function(self,tag,serial)
   assert(tag.TagName=='InputType.OnlyLook' and self.serial==serial)
   unregistered=unregistered+1;for i=#leases,1,-1 do if leases[i]==self then table.remove(leases,i)end end;return true end})
end
local owner=newflow(world);local other_owner=newflow(world);local foreign_owner=newflow(foreign_world)
local gameplay=obj({IsGamePaused=function()return paused end,GetRealTimeSeconds=function()return now end})
StaticFindObject=function(path)
 if path=='/Script/Engine.Default__GameplayStatics'then return gameplay end
 return obj({GetFullName=function()return 'Function '..path end})
end
FindAllOf=function(class)assert(class=='LevelSequencePlayer');scans=scans+1;return {}end
RegisterHook=function(path,pre,post)
 assert(not callbacks[path]);local handles={#order+41,#order+42};order[#order+1]='register:'..path
 callbacks[path]={pre=pre,post=post,handles=handles};return handles[1],handles[2]
end
UnregisterHook=function(path,pre,post)
 assert(callbacks[path].handles[1]==pre and callbacks[path].handles[2]==post and not disposed[path]);disposed[path]=true
end
local g=M.new(function()released=released+1;order[#order+1]='release';return true end,function(message)logs[#logs+1]=message end,
 function()if asc_present then return asc end end)
g.pawn=pawn;g.pc=pc;g.input=input;g.interact=interact;g.router=router;g:register()
local input_path='/Script/ProjectPBZ.EventPipelineManager:RegisterInputType'
local pause_path='/Script/Engine.GameplayStatics:SetGamePaused'
local interaction_path='/Script/ProjectPBZ.PBZInteractComponent:DoInteract'
local function input_call(source,operation)
 callbacks[input_path].pre(wrap(source),wrap({TagName='InputType.OnlyLook'}));operation();callbacks[input_path].post()
end
local function pause_call(context,operation)
 callbacks[pause_path].pre(wrap(gameplay),wrap(context));operation();callbacks[pause_path].post()
end
'''
cases.update({
'input_post_captures_native_serial_without_polling_open_ui':edge_fixture+r'''
ui=true;owner.serial=7;leases={owner}
input_call(owner,function()assert(released==1);order[#order+1]='native';owner.serial=19 end)
assert(g.ticket and g.ticket.serial==19 and g.ticket.owner==owner:GetAddress() and not g.last_poll)
assert(order[#order-1]=='release' and order[#order]=='native' and unregistered==0)
ui=false;now=1;g:update(pc,pawn);now=1.7;g:update(pc,pawn)
assert(unregistered==1 and g.last_result.serial==19 and #leases==0)
''',
'input_closing_ui_records_same_owner_new_post_serial':edge_fixture+r'''
ui=true;owner.serial=7;leases={owner}
input_call(owner,function()ui=false;owner.serial=19 end)
assert(g.ticket and g.ticket.serial==19 and g.ticket.owner==owner:GetAddress(),'same-owner UI exit must retain the actual post serial')
now=1;g:update(pc,pawn);assert(unregistered==1 and g.last_result.serial==19)
''',
'native_edge_preserves_changed_owner_at_ui_exit':edge_fixture+r'''
ui=true;owner.serial=7;leases={owner}
input_call(owner,function()ui=false;other_owner.serial=19;leases={other_owner}end)
assert(not g.ticket and unregistered==0)
now=1;g:update(pc,pawn);assert(unregistered==0)
''',
'input_post_unknown_onlylook_without_ui_is_not_captured':edge_fixture+r'''
input_call(owner,function()owner.serial=19;leases={owner}end)
assert(released==1 and not g.ticket and not g.ui_seen and unregistered==0)
now=1;g:update(pc,pawn);now=2;g:update(pc,pawn);assert(unregistered==0)
''',
'native_edge_new_world_between_pre_and_post_is_not_captured':edge_fixture+r'''
ui=true
input_call(owner,function()active_world=foreign_world;ui=false;foreign_owner.serial=19;leases={foreign_owner}end)
assert(not g.ticket and not g.ui_seen and unregistered==0)
now=1;g:update(pc,pawn);assert(unregistered==0)
''',
'input_foreign_world_event_is_ignored':edge_fixture+r'''
ui=true
input_call(foreign_owner,function()foreign_owner.serial=19;leases={foreign_owner}end)
assert(released==0 and not g.ticket and not g.ui_seen and unregistered==0)
''',
'ambiguous_onlylook_owners_never_create_ticket':edge_fixture+r'''
ui=true;owner.serial=7;other_owner.serial=11;leases={owner,other_owner}
input_call(owner,function()owner.serial=19 end)
assert(released==1 and not g.ticket and unregistered==0)
now=1;g:update(pc,pawn);assert(g.disabled and not g.ticket and unregistered==0)
''',
'pause_pre_post_observes_short_ui_without_periodic_poll':edge_fixture+r'''
pause_call(pawn,function()paused=true end)
assert(g.ui_seen and not g.last_poll and unregistered==0 and released==0)
now=.05;pause_call(pawn,function()paused=false;owner.serial=23;leases={owner}end)
assert(g.ticket and g.ticket.serial==23 and not g.last_poll and released==0)
now=.7;g:update(pc,pawn)
assert(unregistered==1 and g.last_result.serial==23)
''',
'nested_foreign_pause_frames_do_not_steal_current_world_ui':edge_fixture+r'''
local foreign_context=obj({GetWorld=function()return foreign_world end})
pause_call(pawn,function()
 pause_call(foreign_context,function()end)
 paused=true
end)
assert(g.ui_seen and not g.ticket and released==0)
now=.05;pause_call(pawn,function()paused=false;owner.serial=23;leases={owner}end)
assert(g.ticket and g.ticket.serial==23)
''',
'dispose_unregisters_all_native_edge_hooks_and_ignores_callbacks':edge_fixture+r'''
g:dispose()
assert(disposed[input_path] and disposed[pause_path] and disposed[interaction_path])
assert(not g.hook and not g.pause_hook and not g.interaction_hook)
ui=true;input_call(owner,function()owner.serial=19;leases={owner}end)
pause_call(pawn,function()paused=true end)
assert(released==0 and not g.ticket and unregistered==0)
'''
})

for tag in ('Ability.UpperBody.Hun.ChangeArmed','CharacterState.ChangingArmed','CharacterState.FlowIdle',
            'CharacterState.FlowIdle.CantBreak','CharacterState.Native.Sequence','Ability.Action.Execution',
            'Ability.Executed','Ability.SpecialMove','Ability.Action.Hun.SpecialMove',
            'CharacterState.AbilityState.InSpecialPerform','Ability.Action.Hun.Dash',
            'CharacterState.Space.Air','CharacterState.Stand.Break',
            'Ability.Action.Hun.SimpleExecution','Ability.Action.Hun.PerfectDodge'):
 cases['menu_ticket_preserves_native_tag_without_montage_'+tag]=edge_fixture+f'''
ui=true;owner.serial=7;leases={{owner}};g:update(pc,pawn)
ui=false;native_tags['{tag}']=true;now=1;g:update(pc,pawn);now=4;g:update(pc,pawn)
assert(not g.disabled and g.ticket and not g.ticket.quiet_since and unregistered==0)
native_tags['{tag}']=nil;now=5;g:update(pc,pawn);now=5.7;g:update(pc,pawn)
assert(unregistered==1 and not g.ticket and g.last_result.owner==owner:GetAddress()and g.last_result.serial==7)
'''

cases.update({
 'missing_asc_preserves_ticket_then_recovers_through_actor_local_lookup':edge_fixture+r'''
asc_present=false;ui=true;owner.serial=7;leases={owner};g:update(pc,pawn)
ui=false;now=1;g:update(pc,pawn);now=3;g:update(pc,pawn)
assert(g.ticket and not g.disabled and unregistered==0 and local_queries>0)
local_abilities={asc};now=4;g:update(pc,pawn);local queried=local_queries
now=4.7;g:update(pc,pawn)
assert(unregistered==1 and not g.disabled and local_queries==queried,'Owned ASC should be cached after recovery')
''',
 'stale_asc_owner_never_clears_current_pawn_ticket_and_can_recover':edge_fixture+r'''
asc_owner=obj();local_abilities={asc};ui=true;owner.serial=7;leases={owner};g:update(pc,pawn)
ui=false;now=1;g:update(pc,pawn);now=3;g:update(pc,pawn)
assert(g.ticket and not g.disabled and unregistered==0)
asc_owner=pawn;now=4;g:update(pc,pawn);now=4.7;g:update(pc,pawn)
assert(unregistered==1 and not g.disabled)
''',
 'ambiguous_actor_local_asc_preserves_ticket_until_unambiguous':edge_fixture+r'''
asc_present=false;local_abilities={asc,obj({GetOwner=function()return pawn end})}
ui=true;owner.serial=7;leases={owner};g:update(pc,pawn);ui=false;now=1;g:update(pc,pawn);now=3;g:update(pc,pawn)
assert(unregistered==0 and g.ticket and not g.disabled)
local_abilities={asc};now=4;g:update(pc,pawn);now=4.7;g:update(pc,pawn);assert(unregistered==1)
''',
 'completed_interaction_old_asc_owner_preserves_the_original_wait':fixture+r'''
asc_owner=obj();local_abilities={asc};g.interaction_watch.narrative_seen=true
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,3)
assert(endcount==0 and removed==0 and g.interaction_watch and not g.disabled)
asc_owner=pawn;g:recover_completed_interaction(s,4);g:recover_completed_interaction(s,5.1)
assert(endcount==1 and removed==1)
''',
 'completed_interaction_missing_asc_can_recover_from_same_pawn_without_custom_enable':fixture+r'''
asc_present=false;g.interaction_watch.narrative_seen=true
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,3)
assert(endcount==0 and removed==0 and g.interaction_watch and not g.disabled)
local_abilities={asc};g:recover_completed_interaction(s,4);g:recover_completed_interaction(s,5.1)
assert(endcount==1 and removed==1)
''',
 'interaction_exit_new_native_tag_retains_exact_ticket_until_original_action_finishes':fixture+r'''
g.interaction_watch.narrative_seen=true
on_end=function()native_tags['CharacterState.Native.Sequence']=true end
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,1.1)
assert(endcount==1 and ended and removed==0 and not g.interaction_watch)
assert(g.ticket and g.ticket.interaction_exit and g.ticket.owner==flow:GetAddress()and g.ticket.serial==19)
assert(g.last_interaction_recovery.deferred and not g.last_interaction_recovery.released)
now=2;g:update(g.pc,pawn);now=4;g:update(g.pc,pawn)
assert(removed==0 and g.ticket and not g.disabled)
native_tags={};now=5;g:update(g.pc,pawn);now=5.7;g:update(g.pc,pawn)
assert(removed==1 and not g.ticket and g.last_result.serial==19 and endcount==1)
''',
 'interaction_exit_new_world_sequence_defers_the_exact_exit_ticket':fixture+r'''
g.interaction_watch.narrative_seen=true;on_end=function()seq=true end
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,1.1)
assert(endcount==1 and removed==0 and g.ticket and g.ticket.interaction_exit)
now=2;g:update(g.pc,pawn);now=2.7;g:update(g.pc,pawn);assert(removed==0 and g.ticket)
seq=false;now=3;g:update(g.pc,pawn);now=3.7;g:update(g.pc,pawn)
assert(removed==1 and not g.ticket)
''',
 'interaction_exit_ticket_never_adopts_a_newer_same_flow_serial':fixture+r'''
g.interaction_watch.narrative_seen=true;on_end=function()native_tags['CharacterState.ChangingArmed']=true end
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,1.1)
assert(g.ticket and g.ticket.serial==19 and removed==0)
serial=20;now=2;g:update(g.pc,pawn);assert(not g.ticket and removed==0)
native_tags={};now=3;g:update(g.pc,pawn);now=4;g:update(g.pc,pawn);assert(removed==0)
''',
 'interaction_exit_ticket_never_adopts_another_flow_owner':fixture+r'''
g.interaction_watch.narrative_seen=true;on_end=function()native_tags['CharacterState.ChangingArmed']=true end
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,1.1)
assert(g.ticket and removed==0)
local other=obj();g.snapshot=function()return {identity='p',onlylook=true,owner=other:GetAddress(),flow=other,serial=19,ui=false,busy=false}end
now=2;g:update(g.pc,pawn);now=3;g:update(g.pc,pawn);assert(not g.ticket and removed==0 and not g.disabled)
''',
 'interaction_exit_does_not_claim_an_unchanged_old_serial':fixture+r'''
g.interaction_watch.narrative_seen=true;on_end=function()serial=17 end
g:recover_completed_interaction(s,0);g:recover_completed_interaction(s,1.1)
assert(endcount==1 and removed==0 and not g.ticket)
''',
})

results=[]
for name,body in cases.items():
 try:lua.execute(body);results.append({'name':name,'pass':True});print('PASS',name)
 except Exception as e:results.append({'name':name,'pass':False,'error':str(e)});print('FAIL',name,str(e))
(root/'reports/offline-native-control-094-tests.json').write_text(json.dumps({'scope':'Lua decision tests; native interaction acceptance is separate','cases':results},indent=2),encoding='utf8')
raise SystemExit(any(not x['pass'] for x in results))
