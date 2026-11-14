"""Offline timing/safety checks only; never an in-game acceptance substitute."""
from pathlib import Path
import json,sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools/lua-python'))
from lupa.lua54 import LuaRuntime
lua=LuaRuntime(unpack_returned_tuples=True)
scripts=root/'src/runtime/RingedKnightArsenal/Scripts'
lua.globals().State=lua.execute((scripts/'CombatState.lua').read_text())
lua.globals().decode=lua.execute((scripts/'dkjson.lua').read_text()).decode
profile=lua.globals().decode((scripts/'combat-profile.json').read_text())[0]
lua.globals().P=profile
cases={
 'contacts_retain_the_clipped_source_interval_when_a_frame_skips_the_window':r"""
local s=State.new(P);local name='RKSS_Light1';local hit=P.clips[name].hits[1]
s:enter(name,true);s.time=hit.start-.01
local duration=math.min(.25,hit.finish-hit.start+.02);local events=s:step(duration,{})
local found=false
for _,event in ipairs(events)do if event.kind=='hit_window'and event.index==1 then
 found=true;assert(math.abs(event.from_time-hit.start)<1e-8)
 assert(math.abs(event.time-math.min(hit.finish,hit.start-.01+duration))<1e-8)
 assert(event.from_time<=event.time)
end end
assert(found,'Dropped the full skipped collision interval')
assert(#s:step(0,{})==0,'Zero elapsed time must not replay hit samples')
""",
 'plunge_loop_wrap_emits_separate_tail_and_head_intervals_with_one_contact_identity':r"""
local s=State.new(P);local name=P.jump.loop;local data=P.clips[name]
local old_hits=data.hits;local old_duration=data.duration
data.duration=1;data.hits={{start=0,finish=1}}
s:enter(P.jump.start,true);s:enter(name,true);s.time=.96
local hits={}
for _,e in ipairs(s:step(.1,{on_ground=false}))do if e.kind=='hit_window'then hits[#hits+1]=e end end
data.hits=old_hits;data.duration=old_duration
assert(#hits==2 and hits[1].index==hits[2].index and hits[1].plunge_serial==hits[2].plunge_serial)
assert(math.abs(hits[1].from_time-.96)<1e-8 and hits[1].time==1)
assert(hits[2].from_time==0 and math.abs(hits[2].time-.06)<1e-8)
assert(hits[2].step_offset>0,'Never sweep directly across a looping animation boundary')
""",
 'full_heavy_requires_continuous_hold_and_does_not_leak_to_next_attack':r"""
for _,stage in ipairs({1,2})do
 for _,dt in ipairs({1/30,1/60,1/120,.1})do
  for _,mode in ipairs({'hold','tap','release_repress','release_after_full'})do
   local s=State.new(P);s:start_heavy(stage,true);local hits=0
   for frame=1,400 do
    local held=mode=='hold'or mode=='release_after_full'or(mode=='release_repress'and frame~=2)
    if mode=='release_after_full'and s.heavy_charged then held=false end
    for _,e in ipairs(s:step(dt,{triangle=held}))do
     if e.kind=='hit_window'then
      hits=hits+1;assert(e.heavy_charged==(mode=='hold'or mode=='release_after_full'))
     end
    end
    if not s.clip then break end
   end
   assert(hits>0)
   s:start_heavy(stage,true);assert(not s.heavy_charged)
   s:cancel();assert(not s.heavy_charged and not s.heavy_charge_eligible)
  end
 end
end
local s=State.new(P);s:dispatch('switch_heavy')
for _=1,100 do for _,e in ipairs(s:step(1/60,{triangle=true}))do
 if e.kind=='hit_window'then assert(not e.heavy_charged)end
end end
""",
 'held_heavy_full_charge_boundary_is_1_2_seconds':r"""
assert(P.heavy.charged_damage_scale==2)
for _,stage in ipairs({1,2})do
 local s=State.new(P);s:start_heavy(stage,true)
 for _=1,71 do s:step(1/60,{triangle=true});assert(not s.heavy_charged)end
 s:step(1/60,{triangle=true});assert(s.heavy_charged)
 s:enter('RKSS_Light1');assert(not s.heavy_charged)
end
""",

 'uninterrupted_attack_keeps_active_window_and_short_recovery':"""
local s=State.new(P);s:enter('RKSS_Light1')
for i=1,48 do s:step(1/60,{});assert(s.clip=='RKSS_Light1')end
for i=1,10 do s:step(1/60,{})end
assert(s.clip==nil,'The full imported pose tail still blocks recovery')
""",
 'movement_preserves_active_window_then_takes_over_recovery':"""
local s=State.new(P);s:enter('RKSS_Light1')
for i=1,36 do s:step(1/60,{move=true});assert(s.clip=='RKSS_Light1')end
s:step(1/60,{move=true});assert(s.clip==nil)
""",
 'combo_1_2_3_2':"""
local s=State.new(P);s:step(0,{attack_pressed=true});assert(s.clip=='RKSS_Light1')
for _,nextclip in ipairs({'RKSS_Light2','RKSS_Light3','RKSS_Light2'}) do
 s:step(.1,{attack_pressed=true});for i=1,50 do if s.clip==nextclip then break end;s:step(1/60,{}) end
 assert(s.clip==nextclip,s.clip)
end
""",
 'three_rapid_distinct_light_taps_reach_third_cut':"""
local expected={'RKSS_Light1','RKSS_Light2','RKSS_Light3'}
for _,moving in ipairs({false,true})do
    local s=State.new(P)
    local played={}
    for frame=0,180 do
        local pressed=frame==0 or frame==9 or frame==18
        for _,event in ipairs(s:step(frame==0 and 0 or 1/60,{attack_pressed=pressed,move=moving}))do
            if event.kind=='play'then played[#played+1]=event.clip end
        end
    end
    assert(#played==3 and table.concat(played,',')==table.concat(expected,','))
    assert(s.clip==nil and s.pending==nil)
end
""",
 'five_light_cuts_require_pause_before_a_new_first_cut':"""
for _,moving in ipairs({false,true})do
    local s=State.new(P)
    local expected={'RKSS_Light1','RKSS_Light2','RKSS_Light3','RKSS_Light2','RKSS_Light3','RKSS_Light1'}
    local played,fifth_end,last_contact={},nil,false
    for frame=0,720 do
        local events=s:step(frame==0 and 0 or 1/120,{attack_pressed=frame%7==0,move=moving})
        if s.light_index==5 and s.light_pause_until then
            fifth_end=s.light_pause_until-P.light_chain.pause_seconds
        end
        for _,event in ipairs(events)do
            if event.kind=='play' and event.clip:match('^RKSS_Light%d$')then
                played[#played+1]=event.clip
                assert(event.light_index==(#played-1)%5+1,'Wrong light ordinal')
                if #played==6 then
                    assert(fifth_end and last_contact and s.clock+1e-6>=fifth_end+.25,'Sixth light skipped the mandatory pause')
                    assert(s.clock<fifth_end+.27,'Buffered light was delayed beyond its pause')
                end
            elseif event.kind=='hit_window'then
                assert(event.light_index==s.light_index and event.light_index>=1 and event.light_index<=5)
                if event.light_index==5 and math.abs(event.time-event.hit.finish)<1e-6 then last_contact=true end
            end
        end
        if #played==6 then break end
    end
    assert(table.concat(played,',')==table.concat(expected,','))
end
""",
 'guard_restarts_keep_burst_ordinal_and_allow_defense_during_fifth_pause':"""
local s=State.new(P)
s:step(0,{guard=true})
for ordinal=1,5 do
    local events=s:step(0,{guard=true,attack_pressed=true})
    assert(s.clip=='RKSS_Light1' and s.light_index==ordinal)
    assert(events[1].kind=='play' and events[1].light_index==ordinal)
    s:step(.1,{guard=true,guard_pressed=true})
    for _=1,90 do
        events=s:step(1/120,{guard=true})
        for _,event in ipairs(events)do
            if event.kind=='hit_window'then assert(event.light_index==ordinal)end
        end
        if s.clip=='RKSS_GuardStart'then break end
    end
    assert(s:is_guarding() and s.light_index==ordinal)
end
local paused_until=s.light_pause_until
s:step(0,{guard=true,attack_pressed=true})
assert(s:is_guarding() and s.pending=='light' and s.light_index==5)
for _=1,8 do s:step(0,{guard=true});assert(s:is_guarding())end
while s.clock+1/120+1e-6<paused_until do s:step(1/120,{guard=true});assert(s:is_guarding())end
for _=1,2 do s:step(1/120,{guard=true})end
assert(s.clip=='RKSS_Light1' and s.light_index==1)
""",
 'fifth_light_pause_keeps_heavy_and_guard_cancel_available':"""
local s=State.new(P)
s.light_index=4;s:enter('RKSS_Light3')
local contacts=0
while s.time+1e-6<P.clips.RKSS_Light3.hits[1].finish do
    for _,event in ipairs(s:step(1/120,{}))do
        if event.kind=='hit_window' and math.abs(event.time-event.hit.finish)<1e-6 then contacts=contacts+1 end
    end
end
assert(s.light_index==5 and s.light_pause_until>s.clock and contacts==1)
s:step(0,{guard=true,guard_pressed=true})
assert(s:is_guarding())
s:step(0,{triangle_pressed=true})
assert(s.clip=='RKSS_Heavy1Release' and s.light_index==5 and s.clock<s.light_pause_until)
""",
 'light_ordinal_survives_idle_grace_and_resets_on_expiry_or_cancel':"""
local s=State.new(P)
s:step(0,{attack_pressed=true})
while s.clip do s:step(1/120,{})end
s:step(.25,{})
s:step(0,{attack_pressed=true})
assert(s.clip=='RKSS_Light2' and s.light_index==2)
s:cancel()
assert(s.light_index==0 and not s.light_pause_until and not s.pending)
s:step(0,{attack_pressed=true})
assert(s.clip=='RKSS_Light1' and s.light_index==1)
while s.clip do s:step(1/120,{})end
for _=1,3 do s:step(.25,{})end
assert(s.light_index==0)
s:step(0,{attack_pressed=true})
assert(s.clip=='RKSS_Light1' and s.light_index==1)
""",
 'airborne_attack_edges_enter_real_plunge_without_changing_takeoff':"""
for _,key in ipairs({'attack_pressed','triangle_pressed'})do
    local s=State.new(P)
    s:step(.1,{airborne=true})
    assert(s.clip==nil and s.serial==0)
    local input={airborne=true,guard=true,art_pressed=true};input[key]=true
    local events=s:step(0,input)
    assert(s.clip==P.jump.start and s.time==0 and s.plunge_serial==s.serial)
    assert(#events==1 and events[1].kind=='play' and events[1].plunge_serial==s.plunge_serial)
    assert(s.focus==100 and s.pending==nil)
end
local s=State.new(P)
s:step(0,{airborne=true,on_ground=true,attack_pressed=true})
assert(s.clip==nil,'Contradictory ground input began a plunge')
""",
 'plunge_loop_waits_for_ground_and_keeps_one_air_contact_identity':"""
local s=State.new(P);s:step(0,{airborne=true,attack_pressed=true})
local serial=s.plunge_serial
local air_hits,late_hits,loop_events=0,0,0
for frame=1,960 do
    for _,event in ipairs(s:step(1/120,{airborne=true,guard=true,guard_pressed=true,
        attack_pressed=true,triangle_pressed=true,circle_pressed=true,art_pressed=true}))do
        if event.kind=='play'then
            assert(event.clip==P.jump.loop and event.loop and event.plunge_serial==serial)
            loop_events=loop_events+1
        elseif event.kind=='hit_window'then
            assert(event.hit.attack_id==2300040 and event.plunge_phase=='air' and event.plunge_serial==serial)
            assert(event.time>=0 and event.time<=P.clips[s.clip].duration and event.light_index==nil)
            air_hits=air_hits+1
            if frame>720 then late_hits=late_hits+1 end
        else assert(event.kind~='throw_bomb' and event.kind~='cancel_flame')end
    end
end
assert(s.clip==P.jump.loop and loop_events==1 and air_hits>0 and late_hits>0)
assert(s.focus==100 and s.pending==nil and not s.next_light_pending)
s:step(.25,{airborne=false,on_ground=false})
assert(s.clip==P.jump.loop,'Airborne flag loss was mistaken for confirmed ground')
""",
 'confirmed_plunge_landing_is_single_and_has_separate_contact_phase':"""
for _,ground_signal in ipairs({'on_ground','landed'})do
    local s=State.new(P);s:step(0,{airborne=true,attack_pressed=true})
    s:step(.1,{airborne=true})
    local serial=s.plunge_serial
    s.stamina=0
    local input={[ground_signal]=true}
    local events=s:step(0,input)
    assert(s.clip==P.jump.land and s.plunge_serial==serial and s.time==0)
    assert(#events==1 and events[1].kind=='play' and events[1].plunge_serial==serial)
    local land_plays,hits,finished=0,0,false
    for frame=1,360 do
        for _,event in ipairs(s:step(1/120,input))do
            if event.kind=='play' and event.clip==P.jump.land then land_plays=land_plays+1 end
            if event.kind=='hit_window'then
                assert(event.hit.attack_id==2300050 and event.plunge_phase=='land' and event.plunge_serial==serial)
                hits=hits+1
            end
        end
        if not s.clip then
            assert(frame/120+1e-6>=P.jump.land_idle_at and frame/120<P.jump.land_idle_at+.02)
            finished=true;break
        end
    end
    assert(finished and hits>0 and land_plays==0 and s.plunge_serial==nil)
end
""",
 'plunge_landing_uses_source_combo_guard_and_movement_gates':"""
for _,action in ipairs({'light','heavy','guard','move'})do
    local s=State.new(P);s:step(0,{airborne=true,attack_pressed=true});s:step(0,{on_ground=true})
    local input={on_ground=true}
    local expected,gate
    if action=='light'then input.attack_pressed=true;expected='RKSS_Light1';gate=P.clips[P.jump.land].light_combo_open
    elseif action=='heavy'then input.triangle_pressed=true;expected='RKSS_Heavy1Release';gate=P.clips[P.jump.land].heavy_combo_open
    elseif action=='guard'then input.guard=true;input.guard_pressed=true;expected='RKSS_GuardStart';gate=P.clips[P.jump.land].guard_open
    else input.move=true;gate=P.clips[P.jump.land].move_open end
    local transitioned=false
    for frame=1,360 do
        s:step(1/120,input)
        input.attack_pressed=nil;input.triangle_pressed=nil;input.guard_pressed=nil
        if s.clip~=P.jump.land then
            assert(s.clip==expected and frame/120+1e-6>=gate and frame/120<gate+.02,action..' landed before its source gate')
            transitioned=true;break
        end
    end
    assert(transitioned,action..' remained locked after landing')
end
""",
 'native_interruption_clears_every_plunge_stage_and_pending_contact':"""
for _,stage in ipairs({P.jump.start,P.jump.loop,P.jump.land})do
    local s=State.new(P);s:enter(P.jump.start);if stage~=P.jump.start then s:enter(stage,true)end
    assert(s.plunge_serial)
    s:cancel()
    assert(not s.clip and not s.plunge_serial and not s.pending)
    for _=1,240 do
        for _,event in ipairs(s:step(1/120,{airborne=true}))do assert(event.kind~='hit_window')end
    end
end
""",
 'light_buffer_stays_bounded_and_guard_clears_the_extra_press':"""
local s=State.new(P)
for frame=0,120 do
    local pressed=frame==0 or frame==4 or frame==8 or frame==12 or frame==16
    s:step(frame==0 and 0 or 1/60,{attack_pressed=pressed})
end
assert(s.serial==4 and s.clip==nil and not s.pending)
s=State.new(P)
s:step(0,{attack_pressed=true});s:step(.12,{attack_pressed=true});s:step(.12,{attack_pressed=true})
s:step(.1,{guard=true,guard_pressed=true})
for _=1,60 do
    s:step(1/60,{guard=true})
    if s.clip=='RKSS_GuardStart'then break end
end
assert(s.clip=='RKSS_GuardStart' and s.pending=='light' and not s.next_light_pending)
s:step(0,{guard=true})
assert(s.clip=='RKSS_Light1' and s.pending==nil)
""",
 'cancel_waits_for_hit_and_is_cosmetic':"""
local s=State.new(P);s:step(0,{attack_pressed=true});s:step(.25,{});s:step(.1,{guard=true,guard_pressed=true})
assert(s.clip=='RKSS_Light1');local flames=0
for i=1,18 do for _,e in ipairs(s:step(1/60,{guard=true})) do
 if e.kind=='cancel_flame' then assert(e.extra_damage==0 and e.seconds==.35);flames=flames+1;assert(s.time==0) end
end end
assert(s.clip=='RKSS_GuardStart' or s.clip=='RKSS_GuardLoop');assert(flames==1)
""",
 'later_lights_and_both_heavies_guard_cancel_after_complete_contact_then_attack_immediately':"""
for _,clip in ipairs({'RKSS_Light2','RKSS_Light3','RKSS_Heavy1Release','RKSS_Heavy2Release'})do
    for _,held in ipairs({false,true})do
        for _,next_attack in ipairs({'light','heavy'})do
            local s=State.new(P);s.stamina=0
            local stage=tonumber(clip:match('^RKSS_Heavy([12])Release$'))
            if stage then assert(s:start_heavy(stage,true))else s:enter(clip)end
            local finish,serial=s.contact_end[clip],s.serial
            local hits,last_contact={},false
            -- Buffer L1 before the strike; holding it must preserve every
            -- active sample, including the frame that crosses contact_end.
            s:step(0,{guard=true,guard_pressed=true,triangle=held})
            assert(s.clip==clip)
            local canceled,flames=false,0
            for _=1,300 do
                local old=s.time
                local events=s:step(1/120,{guard=true,triangle=held})
                for _,event in ipairs(events)do
                    if event.kind=='cancel_flame'then
                        assert(stage and event.seconds==.35 and event.extra_damage==0,
                            clip..' emitted an unexpected cancel effect or damage')
                        assert(s.clip=='RKSS_GuardStart' and s.time==0 and old+1e-6>=finish and last_contact,
                            clip..' flashed before the complete collision window')
                        flames=flames+1
                    elseif event.kind=='hit_window'then
                        assert(event.serial==serial and s.clip==clip)
                        hits[event.hit.attack_id]=true
                        if math.abs(event.time-finish)<1e-6 then last_contact=true end
                    end
                end
                if s.clip~=clip then
                    assert(s.clip=='RKSS_GuardStart' and old+1e-6>=finish and last_contact,
                        clip..' canceled before its last collision sample')
                    assert(s.time==0 and s.serial==serial+1)
                    canceled=true;break
                end
                assert(old+1e-6<finish,clip..' delayed guard after its contact ended')
            end
            assert(canceled,clip..' ignored buffered L1')
            assert(flames==(stage and 1 or 0),clip..' did not emit exactly its allowed cosmetic cancel')
            for _,hit in ipairs(P.clips[clip].hits)do assert(hits[hit.attack_id])end
            assert(#s:step(0,{guard=true,guard_pressed=true})==0,
                clip..' repeated its cancel flash/sound while already guarding')
            -- Keep L1 for Square; release it for Triangle because L1+Triangle
            -- intentionally remains the rope-bomb chord.
            local events=s:step(0,{guard=next_attack=='light',attack_pressed=next_attack=='light',
                triangle_pressed=next_attack=='heavy',triangle=next_attack=='heavy'})
            assert(s.clip==(next_attack=='light'and 'RKSS_Light1'or 'RKSS_Heavy1Release')
                and s.time==0 and s.serial==serial+2,clip..' delayed the next '..next_attack)
            assert(#events==1 and events[1].kind=='play','Cancel added an extra damage/effect event')
        end
    end
end
""",
 'cancel_preserves_same_sample_attack_and_last_contact':"""
local s=State.new(P);s:enter('RKSS_Light1')
for i=1,35 do s:step(1/60,{})end
local events=s:step(1/60,{guard=true,guard_pressed=true,attack_pressed=true})
assert(s.clip=='RKSS_Light1' and #events==1 and events[1].kind=='hit_window')
assert(math.abs(events[1].time-P.clips.RKSS_Light1.hits[1].finish)<1e-6)
events=s:step(0,{guard=true})
assert(s.clip=='RKSS_GuardStart' and #events==2 and events[2].kind=='cancel_flame')
assert(events[2].extra_damage==0)
s:step(0,{guard=true})
assert(s.clip=='RKSS_Light1' and s.time==0)
""",
 'same_sample_cancel_and_attack_at_recovery_are_both_kept':"""
local s=State.new(P);s:enter('RKSS_Light1')
for i=1,37 do s:step(1/60,{})end
s:step(0,{guard=true,guard_pressed=true,attack_pressed=true})
assert(s.clip=='RKSS_GuardStart')
s:step(0,{guard=true})
assert(s.clip=='RKSS_Light1' and s.time==0)
""",
 'moving_rope_bomb_releases_once_at_frame_32':"""
local s=State.new(P);s:step(0,{guard=true,triangle_pressed=true});assert(s.clip=='RKSS_RopeBomb')
local releases=0;local first
for i=1,100 do
    local events=s:step(1/60,{move=true})
    if i<=32 then assert(s.clip=='RKSS_RopeBomb')end
    for _,e in ipairs(events)do if e.kind=='throw_bomb'then releases=releases+1;first=first or i end end
end
assert(releases==1,releases);assert(first==32,'Release frame '..tostring(first))
assert(P.bomb.mode=='drop_at_feet')
""",
 'stamina_break_requires_release':"""
local s=State.new(P);s:enter('RKSS_GuardLoop');s:step(1/60,{guard=true,guard_cost=120})
assert(s.guard_locked and not s:is_guarding())
for i=1,90 do s:step(1/60,{guard=true}) end;assert(not s:is_guarding())
s:step(1/60,{guard=false});s:step(1/60,{guard=true,guard_pressed=true});assert(s:is_guarding())
""",
 'non_art_resource_constraints_never_go_negative':"""
local s=State.new(P);s.stamina=P.clips[P.jump.land].stamina-1;s.focus=6
local before=s.stamina
assert(not s:enter(P.jump.land))
assert(s.clip==nil and s.stamina==before and s.focus==6)
assert(s.events[1].kind=='exhausted'and s.events[1].clip==P.jump.land)
assert(s.events[1].stamina_required==P.clips[P.jump.land].stamina and s.events[1].stamina_available==before)
""",
 'queued_art_ignores_depleted_private_budgets':"""
local s=State.new(P);s:enter('RKSS_Light2');s.focus=0;s.stamina=0
s:step(1/60,{art_pressed=true})
local entered=false
for i=1,180 do
    for _,event in ipairs(s:step(1/60,{}))do
        assert(event.kind~='exhausted')
        if event.kind=='play'and event.clip==P.art.start then entered=true end
    end
end
assert(entered,'Private budget incorrectly rejected the buffered art')
""",
 'cancel_clears_future_hit_windows':"""
local s=State.new(P);s:enter('RKSS_Ember');s:cancel()
for i=1,120 do for _,e in ipairs(s:step(1/60,{})) do assert(e.kind~='hit_window') end end
""",
 'l2_plays_full_five_hit_chain_with_original_gates_and_no_private_cost':"""
local s=State.new(P);s:step(0,{art_pressed=true})
assert(s.clip=='RKSS_EmberStart' and s.focus==100 and s.stamina==100)
local elapsed,played,hits,started=0,{}, {},{}
for _=1,900 do
    elapsed=elapsed+1/120
    for _,e in ipairs(s:step(1/120,{art=true}))do
        if e.kind=='play' and e.clip:match('^RKSS_Ember')then
            played[#played+1]=e.clip;started[e.clip]=elapsed
        end
        if e.kind=='hit_window'then assert(e.light_index==nil);hits[e.hit.attack_id]=true end
    end
    assert(s.focus==100,'Art consumed an unconnected private focus pool')
end
assert(table.concat(played,',')=='RKSS_Ember,RKSS_EmberFollow1,RKSS_EmberFollow2')
assert(started.RKSS_Ember>=P.clips.RKSS_EmberStart.duration and started.RKSS_Ember<P.clips.RKSS_EmberStart.duration+.02)
for index=1,2 do
    local name,next_name=P.art.light_chain[index],P.art.light_chain[index+1]
    local delta=started[next_name]-started[name]
    assert(delta>=P.art.next_at[name] and delta<P.art.next_at[name]+.02)
end
assert(hits[2330700] and hits[2330701] and hits[2330710] and hits[2330711] and hits[2330721])
assert(not hits[2330730] and s.focus==100 and s.clip==nil)
""",
 'l2_chain_does_not_gate_or_debit_private_resource_budgets':"""
for _,resources in ipairs({{focus=0,stamina=0},{focus=20,stamina=68}})do
    local s=State.new(P);s.focus=resources.focus;s.stamina=resources.stamina
    local events=s:step(0,{art_pressed=true})
    assert(s.clip==P.art.start and s.focus==resources.focus and s.stamina==resources.stamina)
    assert(#events==1 and events[1].kind=='play')
end
""",
 'all_art_clips_ignore_reference_costs_without_adding_focus_recovery':"""
local s=State.new(P);s.focus=0;s.stamina=0
for _,name in ipairs({P.art.start,P.art.light,P.art.heavy,table.unpack(P.art.light_chain)})do
    assert(s:enter(name),name..' rejected its extracted DS3 reference cost')
    assert(s.focus==0 and s.stamina==0)
end
s:cancel()
for _=1,60 do s:step(.25,{})end
assert(s.focus==0 and s.stamina==100,'Art policy introduced a new focus regeneration mechanic')
""",
 'repeated_arts_do_not_permanently_exhaust_one_equipment_session':"""
for _,branch in ipairs({'light','heavy'})do
    local s=State.new(P);s.focus=0;s.stamina=0
    for cast=1,12 do
        local events=s:step(0,{art_pressed=branch=='light',guard=branch=='heavy',circle_pressed=branch=='heavy'})
        assert(s.clip==P.art.start,branch..' art permanently failed at cast '..cast)
        local hits,finished={},false
        for _=1,1200 do
            for _,event in ipairs(s:step(1/120,{}))do
                if event.kind=='hit_window'then hits[event.hit.attack_id]=true end
            end
            if s.clip==nil then finished=true;break end
        end
        assert(finished)
        assert(s.focus==0,'Art consumed or regenerated the private focus pool')
        if branch=='light'then
            assert(hits[2330700]and hits[2330701]and hits[2330710]and hits[2330711]and hits[2330721])
        else assert(hits[2330730]and not hits[2330700])end
        for _=1,4 do s:step(.25,{})end
    end
end
""",
 'guard_circle_plays_stance_then_original_heavy_without_repeat':"""
local s=State.new(P)
s:step(0,{circle_pressed=true});assert(s.clip==nil and s.focus==100)
s:step(0,{guard=true,guard_pressed=true});assert(s.clip=='RKSS_GuardStart')
s:step(0,{guard=true,circle_pressed=true})
assert(s.clip=='RKSS_EmberStart' and s.focus==100 and s.stamina==100)
local hits={}
for _=1,370 do
    for _,e in ipairs(s:step(1/120,{guard=true}))do
        if e.kind=='hit_window'then hits[e.hit.attack_id]=true end
    end
end
assert(hits[2330730] and not hits[2330700] and not hits[2330701] and s.focus==100)
""",
 'buffered_art_requests_survive_same_frame_guard_cancel':"""
for _,request in ipairs({'light','heavy'})do
    for _,clip in ipairs({'RKSS_Light1','RKSS_Light2','RKSS_Heavy1Release','RKSS_RopeBomb'})do
        local s=State.new(P);s:enter(clip);s:step(.1,{})
        s:step(0,{guard=true,guard_pressed=true,art_pressed=request=='light',circle_pressed=request=='heavy'})
        local entered=false
        for _=1,600 do
            s:step(1/120,{})
            if s.clip==P.art.start then entered=true;break end
        end
        assert(entered,clip..' dropped the '..request..' art request during guard cancel')
        assert(s.art_followup==(request=='light' and P.art.light or P.art.heavy))
    end
end
""",
 'queued_heavy_art_waits_for_every_light_art_strike':"""
local s=State.new(P);s:step(0,{art_pressed=true})
local hits,queued,heavy_started={},false,false
for _=1,1200 do
    local queue=s.clip==P.art.light and not queued
    if queue then queued=true end
    for _,event in ipairs(s:step(1/120,{guard=queue,circle_pressed=queue}))do
        if event.kind=='hit_window'then hits[event.hit.attack_id]=true end
        if event.kind=='play'and event.clip==P.art.start then
            assert(hits[2330700]and hits[2330701]and hits[2330710]and hits[2330711]and hits[2330721],
                'Queued art truncated the original 2+2+1 chain')
            assert(s.art_followup==P.art.heavy);heavy_started=true
        end
    end
    if heavy_started then break end
end
assert(queued and heavy_started,'Buffered L1+Circle was lost after the light art')
""",
 'complete_art_pays_once_at_actual_start_and_not_at_each_contact_or_followup':"""
for _,branch in ipairs({'light','heavy'})do
 local s=State.new(P);local paid={};local hits={}
 s.pay_art=function(sequence,followup)
  assert(not paid[sequence]);paid[sequence]=followup;return true
 end
 s:step(0,{art_pressed=branch=='light',guard=branch=='heavy',circle_pressed=branch=='heavy'})
 assert(s.clip==P.art.start and paid[s.serial]==P.art[branch])
 for _=1,1600 do
  for _,event in ipairs(s:step(1/120,{}))do
   if event.kind=='hit_window'then hits[event.serial..':'..event.index]=true end
  end
  if not s.clip then break end
 end
 local payments,contacts=0,0
 for _ in pairs(paid)do payments=payments+1 end
 for _ in pairs(hits)do contacts=contacts+1 end
 assert(payments==1 and contacts==(branch=='light'and 5 or 1)and not s.clip)
 s:step(0,{art_pressed=true});assert(s.clip==P.art.start)
 payments=0;for _ in pairs(paid)do payments=payments+1 end;assert(payments==2)
end
""",
 'unfunded_art_preserves_guard_and_can_retry_after_native_resource_refill':"""
local s=State.new(P);s:step(0,{guard=true})
local attempts=0;local balance=0;local expected=s.serial+1
s.pay_art=function(sequence)
 assert(sequence==expected);attempts=attempts+1
 if balance<1 then return false end;balance=balance-1;return true
end
local events=s:step(0,{guard=true,circle_pressed=true})
assert(s.clip=='RKSS_GuardStart'and s.serial+1==expected and not s.art_followup)
assert(#events==1 and events[1].kind=='resource_blocked'and balance==0)
balance=1;events=s:step(0,{guard=true,circle_pressed=true})
assert(s.clip==P.art.start and balance==0 and attempts==2 and #events==1)
""",
 'buffered_art_is_charged_only_after_the_previous_strike_finishes':"""
local s=State.new(P);local count=0
s.pay_art=function()count=count+1;return true end
s:step(0,{attack_pressed=true});s:step(.1,{art_pressed=true})
assert(count==0 and s.clip=='RKSS_Light1')
for _=1,200 do s:step(1/120,{});if s.clip==P.art.start then break end end
assert(s.clip==P.art.start and count==1)
s:cancel();assert(count==1,'An interruption changed the original paid cost')
""",
 'triangle_windup_uses_one_pose_clock_with_deliberate_tap_and_hold_weight':"""
local tap,hold,entry=State.new(P),State.new(P),State.new(P)
tap:step(0,{triangle_pressed=true})
hold:step(0,{triangle_pressed=true,triangle=true})
entry:step(0,{switch_heavy=true})
tap:step(.1,{})
hold:step(.1,{triangle=true})
entry:step(.1,{})
assert(math.abs(tap.time-.045)<1e-8 and math.abs(hold.time-.020)<1e-8)
assert(math.abs(entry.time-.1)<1e-8)
tap:step(.15,{})
hold:step(.15,{triangle=true})
assert(math.abs(tap.time-.1125)<1e-8 and math.abs(hold.time-.050)<1e-8)
""",
 'triangle_immediately_starts_first_release':"""
local s=State.new(P);local events=s:step(0,{triangle=true,triangle_pressed=true})
assert(s.clip=='RKSS_Heavy1Release' and s.time==0)
assert(events[1].kind=='play' and events[1].clip=='RKSS_Heavy1Release')
assert(s.stamina==100,'Ordinary swings must not consume the hidden guard budget')
local attacks={}
for i=1,150 do for _,e in ipairs(s:step(1/60,{}))do if e.kind=='hit_window'then attacks[e.hit.attack_id]=true end end end
assert(attacks[2300100] and not attacks[2300105]);assert(s.clip==nil)
""",
 'holding_triangle_keeps_normal_strike_and_never_repeats':"""
local s=State.new(P);s:step(0,{triangle=true,triangle_pressed=true});local attacks={}
for i=1,180 do for _,e in ipairs(s:step(1/60,{triangle=true}))do if e.kind=='hit_window'then attacks[e.hit.attack_id]=true end end end
assert(s.clip==nil and s.serial==2)
assert(attacks[2300100] and not attacks[2300105])
""",
 'early_heavy_buffer_chains_to_second_heavy_at_low_stamina':"""
local s=State.new(P);s.stamina=0;s:step(0,{triangle=true,triangle_pressed=true})
assert(s.clip=='RKSS_Heavy1Release')
s:step(1/60,{triangle=true,triangle_pressed=true});local reached=false
for i=1,90 do s:step(1/60,{});if s.clip=='RKSS_Heavy2Release'then reached=true;break end end
assert(reached,'Early Triangle failed to reach second heavy after the first contact window')
""",
 'late_heavy_keeps_second_stage_after_return_to_idle':"""
local s=State.new(P);s:step(0,{triangle_pressed=true})
for i=1,180 do if not s.clip then break end;s:step(1/60,{})end
assert(s.clip==nil)
s:step(0,{triangle_pressed=true})
assert(s.clip=='RKSS_Heavy2Release' and s.time==0)
""",
 'light_and_heavy_can_alternate_at_low_stamina':"""
local s=State.new(P);s.stamina=0;s:step(0,{attack_pressed=true})
assert(s.clip=='RKSS_Light1')
s:step(0,{triangle_pressed=true})
for i=1,38 do if s.clip=='RKSS_Heavy1Release'then break end;s:step(1/60,{})end
assert(s.clip=='RKSS_Heavy1Release')
s:step(0,{attack_pressed=true})
for i=1,90 do if s.clip=='RKSS_Light1'then break end;s:step(1/60,{})end
assert(s.clip=='RKSS_Light1')
""",
 'switch_attack_uses_first_heavy_and_is_not_the_bomb_combo':"""
local s=State.new(P);s:step(0,{switch_heavy=true,guard=true})
assert(s.clip=='RKSS_Heavy1Release' and s.stamina==100)
"""
}
report=[]
for name,source in cases.items():
    try:lua.execute(source);report.append({'name':name,'pass':True});print('PASS',name)
    except Exception as error:report.append({'name':name,'pass':False,'error':str(error)});print('FAIL',name,str(error))
if '--no-report' not in sys.argv[1:]:
    (root/'reports/offline-state-tests.json').write_text(json.dumps({'scope':'Lua state/timing only; not Unreal runtime','cases':report},indent=2))
raise SystemExit(any(not x['pass'] for x in report))
