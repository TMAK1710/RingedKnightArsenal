-- Reconcile a specifically observed menu-owned OnlyLook lease after its UI ends.
-- Never reset NBInput, cancel a flow, or remove another owner's/newer lease.
local M={};M.__index=M
local ONLY_LOOK='InputType.OnlyLook'
local PREFIX='/Script/ProjectPBZ.EventPipelineManager:'
local NATIVE_OWNERSHIP_TAGS={
 'Ability.UpperBody.Hun.ChangeArmed','CharacterState.ChangingArmed',
 'CharacterState.FlowIdle','CharacterState.FlowIdle.CantBreak','CharacterState.Native.Sequence',
 'Ability.Action.Execution','Ability.Action.Hun.SimpleExecution','Ability.Executed',
 'Ability.Action.Hun.PerfectDodge','Ability.SpecialMove','Ability.Action.Hun.SpecialMove',
 'CharacterState.AbilityState.InSpecialPerform','Ability.Action.Hun.Dash',
 'CharacterState.Space.Air','CharacterState.Stand.Break',
}
local function valid(o)return o and o:IsValid()==true end
local function same(a,b)return valid(a)and valid(b)and a:GetAddress()==b:GetAddress()end
local function un(v)local ok,x=pcall(function()return v:get()end);return ok and x or v end
local function str(v)return type(v)=='string'and v or v:ToString()end
function M.new(release,log,get_ability_system)
 return setmetatable({release=release,log=log,get_ability_system=get_ability_system,quiet=.6},M)
end
function M:native_ability_busy(pawn)
 -- A disabled/uninitialized custom weapon must not prevent native lease recovery.
 -- Resolve only this pawn's ASC; missing or changing ownership stays busy and is
 -- retried on later snapshots instead of permanently disabling the safeguard.
 local ok,busy=pcall(function()
  local asc=self.get_ability_system and self.get_ability_system()
  if not valid(asc)or not same(asc:GetOwner(),pawn)then asc=self.ability_system_cache end
  if not valid(asc)or not same(asc:GetOwner(),pawn)then
   self.ability_system_cache=nil;asc=nil
   local class=StaticFindObject('/Script/GameplayAbilities.AbilitySystemComponent')
   if not valid(class)then return true end
   local candidates=pawn:K2_GetComponentsByClass(class)
   for index=1,#candidates do
    local candidate=un(candidates[index])
    if valid(candidate)and same(candidate:GetOwner(),pawn)then
     if asc then return true end
     asc=candidate
    end
   end
  end
  if not valid(asc)then return true end
  self.ability_system_cache=asc
  for _,tag in ipairs(NATIVE_OWNERSHIP_TAGS)do
   if asc:HasMatchingGameplayTag({TagName=FName(tag)})then return true end
  end
  return false
 end)
 return not ok or busy
end
-- Pure decision boundary, tested separately from engine reflection.
function M:observe(s,now)
 if self.identity~=s.identity then
  self.identity=s.identity;self.ticket=nil;self.ui_seen=false;self.closed_at=nil;self.exit_claimed=false
 end
 if self.ticket and self.ticket.interaction_exit then
  local t=self.ticket
  -- This proven exit is a single exact lease, not permission to adopt a later
  -- flow/serial even if another UI appears while the original action finishes.
  if not s.onlylook or t.owner~=s.owner or t.serial~=s.serial then
   self.ticket=nil;self.ui_seen=false;return
  end
  if s.ui or s.busy then t.quiet_since=nil;return end
  if not t.quiet_since then t.quiet_since=now;return end
  if now-t.quiet_since<self.quiet then return end
  self.ticket=nil;self.ui_seen=false;return t
 end
 if s.ui then
  self.ui_seen=true;self.closed_at=nil;self.exit_claimed=false
  self.ticket=s.onlylook and {owner=s.owner,serial=s.serial,quiet_since=nil}or nil
  return
 end
 if self.ui_seen and not self.closed_at then self.closed_at=now end
 if not s.onlylook then
  self.ticket=nil
  if self.closed_at and now-self.closed_at>.35 then self.ui_seen=false end
  return
 end
 -- PBZ also registers OnlyLook on the menu EXIT edge to hand control back
 -- to the bell/interaction. Accept only the first lease in this bounded edge,
 -- never an unrelated restriction appearing later during gameplay.
 if not self.ticket and self.ui_seen and not self.exit_claimed
   and self.closed_at and now-self.closed_at<=.35 then
  self.ticket={owner=s.owner,serial=s.serial,quiet_since=nil};self.exit_claimed=true
 end
 local t=self.ticket
 if not t then return end
 if t.owner~=s.owner or t.serial~=s.serial then self.ticket=nil;self.ui_seen=false;return end
 if s.busy then t.quiet_since=nil;return end
 if not t.quiet_since then t.quiet_since=now;return end
 if now-t.quiet_since<self.quiet then return end
 self.ticket=nil;self.ui_seen=false -- one attempt, including native rejection
 return t
end
function M:bind(pawn,pc)
 if same(pawn,self.pawn)and same(pc,self.pc)then return end
 self.pawn,self.pc=pawn,pc;self.input,self.interact,self.router=nil,nil,nil
 self.ticket=nil;self.last_poll=nil;self.interaction_watch=nil;self.ability_system_cache=nil
 for _,spec in ipairs({{'PBZNBInputComponent','input'},{'PBZInteractComponent','interact'}})do
  for _,o in ipairs(FindAllOf(spec[1])or{})do
   if valid(o)and not o:GetFullName():find('Default__',1,true)and same(o:GetOwner(),pawn)then self[spec[2]]=o;break end
  end
 end
 for _,o in ipairs(FindAllOf('PBZUIActionRouterBase')or{})do
  if valid(o)and not o:GetFullName():find('Default__',1,true)and same(o:GetOuter(),pc.Player)then self.router=o;break end
 end
end
function M:snapshot(pc,pawn)
 self:bind(pawn,pc)
 assert(valid(self.input)and valid(self.interact)and valid(self.router),'Native control components unavailable')
 local world=pawn:GetWorld()
 local gameplay=StaticFindObject('/Script/Engine.Default__GameplayStatics')
 local s={identity=tostring(pawn:GetAddress())..':'..tostring(world:GetAddress()),
  ui=gameplay:IsGamePaused(pawn)or pc.bShowMouseCursor or self.router:GetActiveInputMode()==0}
 local flow
 self.input.InputTagContainer:ForEach(function(k,v)
  local owner,tag=un(k),un(v)
  if str(tag.TagName)==ONLY_LOOK and valid(owner)and owner:GetFullName():match('^EventPipelineManager ')and same(owner:GetOuter(),world)then
   assert(not flow,'Ambiguous OnlyLook owner');flow=owner
  end
 end)
 if not flow then return s end
 s.onlylook=true;s.owner=flow:GetAddress();s.serial=flow:GetLastRegisteredInputTypeSerial();s.flow=flow
 local function visible(widget)return valid(widget)and widget:IsVisible()and widget:IsInViewport()end
 s.busy=valid(self.interact:GetInteractingActor())or valid(self.interact.FadeInteractActor)
  or self.interact:HasValidLevelSequencePlayer()or valid(flow:GetCurrentAffectFlowNode())
  or valid(flow.CurrentDialogueActor)or visible(flow.DialogueWidget)or visible(flow.SequenceBlackScreenWidget)
  or not flow.LoadComplete or not flow.StreamComplete or str(flow.FlowPlaySeqID)~=''
 if not s.busy then
  local mesh=pawn.Mesh;local instance=valid(mesh)and mesh:GetAnimInstance()
  if valid(instance)and valid(instance:GetCurrentActiveMontage())then s.busy=true end
 end
 if not s.busy then s.busy=self:native_ability_busy(pawn)end
 return s
end
function M:interaction_active(pawn)
 -- Cache is bound to the current player by update/snapshot. Query only the
 -- original interaction owner, not nearby prompts or arbitrary flow assets.
 if not same(pawn,self.pawn)or not valid(self.interact)then return false end
 return valid(self.interact:GetInteractingActor())or valid(self.interact.FadeInteractActor)
  or self.interact:HasValidLevelSequencePlayer()
end
-- A native flow can finish its dialogue while its UnarmCancel listener is
-- stranded. Recovery requires positive completion evidence, not a timeout alone.
function M:observe_completed_interaction(s,now)
 local w=self.interaction_watch
 if not w then return false end
 if not s.same_interaction then self.interaction_watch=nil;return false end
 if not s.completed or s.busy or not s.waiting then w.quiet_since=nil;return false end
 if w.serial~=s.serial or w.flow_owner~=s.flow_owner or w.task_address~=s.task_address then
  w.serial=s.serial;w.flow_owner=s.flow_owner;w.task_address=s.task_address;w.quiet_since=now;return false
 end
 if not w.quiet_since then w.quiet_since=now;return false end
 if now-w.quiet_since<1 then return false end
 self.interaction_watch=nil -- one attempt per observed native interaction
 return true
end
local function nodes_complete(nodes)
 for i=1,#nodes do local n=un(nodes[i]);if not valid(n)or not n:IsExecuteDone()then return false end end
 return true
end
function M:recover_completed_interaction(s,now)
 local w=self.interaction_watch
 if not w then return end
 local actor=valid(self.interact)and self.interact:GetInteractingActor()
 if not same(actor,w.actor)or not same(self.pawn,w.pawn)then self.interaction_watch=nil;return end
 local base=StaticFindObject('/Game/PBZContent/Blueprint/FlowGraph/FlowActor/BP_FlowInteractActor.BP_FlowInteractActor_C')
 if not valid(base)or not actor:IsA(base)then self.interaction_watch=nil;return end
 local flow=s.flow;local fc=actor.BP_PBZFlowComponent;local task=actor['Change Arm Async Action']
 if not valid(flow)or not valid(fc)then w.quiet_since=nil;return end
 local subtitle=fc.CurrentSubtitle
 local completed=valid(subtitle)and subtitle:IsExecuteDone()and #fc.CurrentChoiceNode==0
  and #fc.CurrentExecuteNode>0 and nodes_complete(fc.CurrentExecuteNode)and not fc:GetBranchLock()
 local function visible(widget)return valid(widget)and widget:IsVisible()and widget:IsInViewport()end
 -- A completed subtitle cached from an earlier visit is not evidence that
 -- THIS interaction finished. Observe narrative ownership before its exit.
 if (valid(subtitle)and not subtitle:IsExecuteDone())or #fc.CurrentChoiceNode>0
  or not nodes_complete(fc.CurrentExecuteNode)or fc:GetBranchLock()
  or valid(flow:GetCurrentAffectFlowNode())or visible(flow.DialogueWidget)then w.narrative_seen=true end
 completed=completed and w.narrative_seen==true
 local instance=self.pawn.Mesh:GetAnimInstance()
 local busy=s.ui or valid(actor['Move To Async Task'])or valid(self.interact.FadeInteractActor)
  or self.interact:HasValidLevelSequencePlayer()or valid(flow:GetCurrentAffectFlowNode())
  or visible(flow.DialogueWidget)or visible(flow.SequenceBlackScreenWidget)
  or not flow.LoadComplete or not flow.StreamComplete or str(flow.FlowPlaySeqID)~=''
  or (valid(instance)and valid(instance:GetCurrentActiveMontage()))
 busy=busy or self:native_ability_busy(self.pawn)
 -- Check world sequences only at a stable, otherwise-ready release boundary.
 -- Keep the watch while a sequence owns control so its end can be observed.
 if completed and not busy and s.onlylook and valid(task)
  and w.serial==s.serial and w.flow_owner==flow:GetAddress()and w.task_address==task:GetAddress()
  and w.quiet_since and now-w.quiet_since>=1 then busy=self:sequence_busy(self.pawn:GetWorld())end
 local ready=self:observe_completed_interaction({same_interaction=true,completed=completed,busy=busy,
  waiting=s.onlylook and valid(task),serial=s.serial,flow_owner=flow:GetAddress(),
  task_address=valid(task)and task:GetAddress()or nil},now)
 if not ready then return end
 -- Recheck exact ownership immediately before native exit. Never complete or
 -- skip a quest node, synthesize UnarmCancel, or reset the global input system.
 assert(same(self.interact:GetInteractingActor(),actor)and same(actor['Change Arm Async Action'],task)
  and flow:GetLastRegisteredInputTypeSerial()==s.serial,'Interaction changed before recovery')
 task:EndAction();actor['Change Arm Async Action']=nil;actor:ReadyToEndInteract()
 local after=self:snapshot(self.pc,self.pawn)
 local released=false
 -- EndInteract can synchronously register a new OnlyLook on its exit edge.
 -- Capture that exact serial after the original exit; do not reuse the old one.
 local deferred=false
 if not valid(self.interact:GetInteractingActor())and after.onlylook and same(after.flow,flow)
  and after.identity==s.identity and after.serial~=s.serial then
  self.identity=after.identity;self.ticket=nil;self.ui_seen=false;self.closed_at=nil;self.exit_claimed=true
  if not after.ui and not after.busy and not self:sequence_busy(self.pawn:GetWorld())then
   released=flow:UnRegisterInputTypeIfUnchanged({TagName=FName(ONLY_LOOK)},after.serial)
  else
   self.ticket={owner=after.owner,serial=after.serial,quiet_since=nil,interaction_exit=true}
   deferred=true
  end
 end
 self.last_interaction_recovery={actor=actor:GetFullName(),serial_before=s.serial,
  serial_after=after.serial,released=released,deferred=deferred,ended=not valid(self.interact:GetInteractingActor())}
 if self.log then self.log('Completed native interaction recovered: '..actor:GetFullName()..' released='..tostring(released))end
end
function M:register_interaction()
 if self.interaction_hook then return end
 local path='/Script/ProjectPBZ.PBZInteractComponent:DoInteract'
 local fn=StaticFindObject(path)
 assert(valid(fn)and fn:GetFullName()=='Function '..path,'Native interaction API changed')
 local pre,post=RegisterHook(path,function(context,target)
  if self.disposed then return end
  local component,actor=un(context),un(target)
  if not valid(component)or not valid(actor)or not same(component:GetOwner(),self.pawn)then return end
  -- Native BP_FlowInteractActor may request ChangeArmed before any dialogue
  -- tag/UI is present. Release our sampled montage BEFORE that native request.
  local ok,why=pcall(self.release)
  if ok and why==true then self.interaction_watch={actor=actor,pawn=self.pawn}end
  if not ok and self.log then self.log('Native interaction handoff failed: '..tostring(why))end
 end)
 self.interaction_hook={path=path,pre=pre,post=post}
end
function M:sequence_busy(world)
 -- Only inspect sequence players at a pending release boundary, never per frame.
 for _,o in ipairs(FindAllOf('LevelSequencePlayer')or{})do
  if valid(o)and not o:GetFullName():find('Default__',1,true)and same(o:GetWorld(),world)
    and (o:IsPlaying()or o:IsPaused())then return true end
 end
 return false
end
function M:update(pc,pawn)
 if self.disabled or not valid(pc)or not valid(pawn)then return end
 local ok,why=pcall(function()
  local gameplay=StaticFindObject('/Script/Engine.Default__GameplayStatics')
  local now=gameplay:GetRealTimeSeconds(pawn)
  if self.last_poll and now-self.last_poll<.2 and same(self.pawn,pawn)then return end
  self.last_poll=now
  local s=self:snapshot(pc,pawn)
  if self.interaction_watch then
   self:recover_completed_interaction(s,now)
   s=self:snapshot(pc,pawn)
  end
  -- Defer consuming the exact menu ticket until world sequences also finish.
  -- No global sequence scan without a stable ticket ready for release.
  local pending=self.ticket
  if pending and self.identity==s.identity and not s.ui and not s.busy and s.onlylook
   and pending.owner==s.owner and pending.serial==s.serial and pending.quiet_since
   and now-pending.quiet_since>=self.quiet then s.busy=self:sequence_busy(pawn:GetWorld())end
  local ticket=self:observe(s,now)
  if not ticket then return end
  -- Native serial comparison prevents a nested/newer flow lease from being released.
  local removed=s.flow:UnRegisterInputTypeIfUnchanged({TagName=FName(ONLY_LOOK)},ticket.serial)
  self.last_result={owner=ticket.owner,serial=ticket.serial,removed=removed}
  if self.log then self.log('Native menu lease: serial='..ticket.serial..' released='..tostring(removed))end
 end)
 if not ok then
  self.ticket=nil;self.disabled=true
  if self.log then self.log('Native menu lease safeguard disabled: '..tostring(why))end
 end
end
-- Capture actual UI state at native call boundaries as well as the periodic
-- poll. A menu can open/close between polls (or while world timers are paused).
-- Never infer ownership of an arbitrary later OnlyLook from an old menu.
function M:observe_native_edge(before,after,now)
 if not before or not after or before.identity~=after.identity then return end
 if before.ui and not after.ui and after.onlylook then
  if before.onlylook and before.owner~=after.owner then
   self.ticket=nil;self.ui_seen=false;return
  end
  -- The native call itself can close UI and replace its same-owner lease.
  -- Associate the actual post-call serial with this observed UI boundary.
  local edge={};for k,v in pairs(after)do edge[k]=v end;edge.ui=true
  self:observe(edge,now);self:observe(after,now);return
 end
 if before.ui then self:observe(before,now)end
 if after.ui or before.ui then self:observe(after,now)end
end
function M:capture_edge()
 local s=self:snapshot(self.pc,self.pawn)
 local now=StaticFindObject('/Script/Engine.Default__GameplayStatics'):GetRealTimeSeconds(self.pawn)
 return s,now
end
function M:register_pause()
 local path='/Script/Engine.GameplayStatics:SetGamePaused'
 local fn=StaticFindObject(path)
 assert(valid(fn)and fn:GetFullName()=='Function '..path,'Native pause API changed')
 local frames={}
 local pre,post=RegisterHook(path,function(context,world_context)
  local frame={};frames[#frames+1]=frame
  if self.disposed or not valid(self.pawn)or not valid(self.pc)then return end
  local obj=un(world_context)
  local ok,matched=pcall(function()return valid(obj)and same(obj:GetWorld(),self.pawn:GetWorld())end)
  if not ok or not matched then return end
  local success,before=pcall(function()return self:capture_edge()end)
  if success then frame.before=before end
 end,function()
  local frame=table.remove(frames)
  if self.disposed or not frame or not frame.before then return end
  local ok,err=pcall(function()
   local after,now=self:capture_edge();self:observe_native_edge(frame.before,after,now)
  end)
  if not ok and self.log then self.log('Native pause observation failed: '..tostring(err))end
 end)
 self.pause_hook={path=path,pre=pre,post=post}
end
function M:register()
 local path=PREFIX..'RegisterInputType'
 for _,name in ipairs({'RegisterInputType','GetLastRegisteredInputTypeSerial','UnRegisterInputTypeIfUnchanged'})do
  local f=StaticFindObject(PREFIX..name)
  assert(valid(f)and f:GetFullName()=='Function '..PREFIX..name,'Native lease API changed')
 end
 local frames={}
 local pre,post=RegisterHook(path,function(context,tag)
  local frame={};frames[#frames+1]=frame
  if self.disposed then return end
  local owner=un(context);local value=un(tag)
  if not valid(owner)or not valid(self.pawn)or not same(owner:GetOuter(),self.pawn:GetWorld())then return end
  local observed,before=pcall(function()return self:capture_edge()end)
  if observed then frame.before=before end
  local name=str(value.TagName)
  if name==ONLY_LOOK or name=='InputType.DisableAll'or name=='InputType.InLoading'or name=='InputType.FlowMove'or name=='InputType.QTE'then
   -- Release only this mod's pose, input context and movement lease before native takeover.
   local ok,why=pcall(self.release)
   if not ok and self.log then self.log('Native takeover cleanup failed: '..tostring(why))end
  end
 end,function()
  local frame=table.remove(frames)
  if self.disposed or not frame or not frame.before then return end
  local ok,err=pcall(function()
   local after,now=self:capture_edge();self:observe_native_edge(frame.before,after,now)
  end)
  if not ok and self.log then self.log('Native input observation failed: '..tostring(err))end
 end)
 self.hook={path=path,pre=pre,post=post}
 self:register_interaction()
 self:register_pause()
end
function M:dispose()
 self.disposed=true;self.ticket=nil;self.interaction_watch=nil
 if self.pause_hook then UnregisterHook(self.pause_hook.path,self.pause_hook.pre,self.pause_hook.post);self.pause_hook=nil end
 if self.interaction_hook then UnregisterHook(self.interaction_hook.path,self.interaction_hook.pre,self.interaction_hook.post);self.interaction_hook=nil end
 if self.hook then UnregisterHook(self.hook.path,self.hook.pre,self.hook.post);self.hook=nil end
end
return M
