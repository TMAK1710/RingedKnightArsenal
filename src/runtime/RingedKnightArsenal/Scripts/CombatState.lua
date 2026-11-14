-- The action clock preserves source strike windows. Player commands replace
-- recovery instead of waiting for the tail of the imported pose clip.
local M={};M.__index=M
local RECOVERY_TAIL=.32
local COMBO_GRACE=.60

local function family(name)
    if not name then return end
    if name:match('^RKSS_Light%d$')then return 'light'end
    if name:match('^RKSS_Heavy[12]Release$')then return 'heavy'end
end

function M.new(profile)
    local contact_end,art_clips={},{}
    if profile.art then
        for _,name in ipairs({profile.art.start,profile.art.light,profile.art.heavy})do art_clips[name]=true end
        for _,name in ipairs(profile.art.light_chain or {})do art_clips[name]=true end
    end
    for name,data in pairs(profile.clips)do
        local finish=0
        for _,hit in ipairs(data.hits)do finish=math.max(finish,hit.finish)end
        contact_end[name]=finish
    end
    return setmetatable({profile=profile,contact_end=contact_end,art_clips=art_clips,time=0,stamina=100,focus=100,serial=0,
        release_fired=false,guard_locked=false,events={},clock=0,light_index=0},M)
end

function M:emit(kind,data)data=data or {};data.kind=kind;self.events[#self.events+1]=data end

function M:spend(name)
    if not name then return true end
    local clip=assert(self.profile.clips[name],'Unknown combat clip: '..name)
    -- Extracted DS3 art costs are reference data, not PBZ attributes. This
    -- weapon has no private art budget; native action priorities still gate it.
    if self.art_clips[name]then return true end
    -- Normal swings share the guard budget without consuming it.
    local stamina=family(name) and 0 or clip.stamina
    local focus=clip.focus or 0
    if stamina>self.stamina or focus>self.focus then
        self:emit('exhausted',{clip=name,stamina_required=stamina,stamina_available=self.stamina,
            focus_required=focus,focus_available=self.focus});return false
    end
    self.stamina=self.stamina-stamina
    self.focus=self.focus-focus
    return true
end

function M:enter(name,prepaid)
    if name then assert(self.profile.clips[name],'Unknown combat clip: '..name)end
    local light=family(name)=='light'
    if light and not self:light_ready()then return false end
    if not prepaid and not self:spend(name) then return false end
    if family(self.clip)=='light' and not light then self.light_until=self.clock+COMBO_GRACE end
    if light then
        local limit=self.profile.light_chain and self.profile.light_chain.max_hits or 5
        if self.light_index>=limit then self.light_index=0;self.light_pause_until=nil end
        self.light_index=self.light_index+1
        self.light_until=nil
    end
    self.clip=name;self.time=0;self.serial=self.serial+1
    local jump=self.profile.jump
    if jump and name==jump.start then self.plunge_serial=self.serial
    elseif not self:is_plunging()then self.plunge_serial=nil end
    self.guard_buffer=false;self.release_fired=false
    self.heavy_windup=false;self.heavy_charge_eligible=false;self.heavy_charged=false;self.art_followup=nil
    self:emit(name and 'play' or 'restore',{clip=name,serial=self.serial,
        loop=name=='RKSS_GuardLoop' or (jump and name==jump.loop)or false,
        light_index=light and self.light_index or nil,plunge_serial=self.plunge_serial})
    return true
end

function M:light_ready()
    return not self.light_pause_until or self.clock+1e-6>=self.light_pause_until
end

function M:pending_ready()
    return self.pending and (self.pending~='light' or self:light_ready())
end

function M:start_heavy(index,windup)
    local stage=assert(self.profile.heavy.stages[index],'Heavy attack stage unavailable')
    if not self:enter(stage.release) then return false end
    self.heavy_windup=windup
    self.heavy_charge_eligible=windup==true
    return true
end

function M:start_art(followup)
    local chain=self.profile.art.light_chain
    if followup==self.profile.art.light and chain then
        for _,name in ipairs(chain)do
            assert(self.profile.clips[name],'Art chain clip unavailable')
        end
    else assert(self.profile.clips[followup],'Art branch clip unavailable')end
    -- Pay only when a queued full art actually starts, never at input time or
    -- again for its automatic strike clips. The runtime supplies native cost.
    if self.pay_art and not self.pay_art(self.serial+1,followup) then
        self:emit('resource_blocked',{resource='UltimateChargeCount',amount=1})
        return false
    end
    self:enter(self.profile.art.start,true)
    self.art_followup=followup
    return true
end

function M:next_art(name)
    local chain=self.profile.art.light_chain
    if not chain then return end
    for index,clip in ipairs(chain)do
        if clip==name and chain[index+1]then
            local at=assert(self.profile.art.next_at[name],'Art chain transition gate unavailable')
            assert(at>=self.contact_end[name] and at<=self.profile.clips[name].duration,'Art gate truncates a strike or exceeds its clip')
            return chain[index+1],at
        end
    end
end

function M:advance_time(old,dt,triangle)
    local windup=self.profile.heavy.windup
    if not self.heavy_windup or old>=windup.seconds then return old+dt end
    -- Apply the rate only within the windup, including a frame that crosses it.
    if not triangle then self.heavy_charge_eligible=false end
    local rate=triangle and windup.held_rate or windup.tap_rate
    local slowed=math.min(dt,(windup.seconds-old)/rate)
    local next_time=old+slowed*rate+(dt-slowed)
    if self.heavy_charge_eligible and next_time+1e-6>=windup.seconds then
        self.heavy_charged=true
    end
    return next_time
end

function M:is_guarding()
    return self.clip=='RKSS_GuardLoop' or self.clip=='RKSS_GuardStart'
end

function M:is_plunging()
    local jump=self.profile.jump
    return jump and (self.clip==jump.start or self.clip==jump.loop or self.clip==jump.land)or false
end

function M:request(input)
    local jump=self.profile.jump
    if jump and (self.clip==jump.start or self.clip==jump.loop)then return end
    if input.airborne then
        if jump and not input.on_ground and not input.landed and (input.attack_pressed or input.triangle_pressed)then return 'plunge'end
        return
    end
    if input.switch_heavy then return 'switch_heavy'end
    if input.guard and input.circle_pressed then return 'art_heavy'end
    if input.guard and input.triangle_pressed then return 'bomb'end
    if input.art_pressed then return 'art'end
    if input.triangle_pressed then return 'heavy'end
    if input.attack_pressed then return 'light'end
end

function M:queue(request)
    -- During a light swing, keep two distinct light presses so rapid
    -- taps can reach the third cut before the second cut starts.
    if request=='light' and self.pending=='light' and family(self.clip)=='light' then
        self.next_light_pending=true
    else
        self.pending=request
        self.next_light_pending=false
    end
end

function M:take_pending()
    local request=self.pending
    self.pending=self.next_light_pending and 'light' or nil
    self.next_light_pending=false
    return request
end

function M:dispatch(request,previous)
    local chain=previous or (self.combo_until and self.clock<=self.combo_until and self.combo_clip)
    if request=='switch_heavy'then return self:start_heavy(1,false)end
    if request=='plunge'then return self:enter(self.profile.jump.start)end
    if request=='bomb'then return self:enter('RKSS_RopeBomb')end
    if request=='art'then return self:start_art(self.profile.art.light)end
    if request=='art_heavy'then return self:start_art(self.profile.art.heavy)end
    if request=='light'then
        local limit=self.profile.light_chain and self.profile.light_chain.max_hits or 5
        if self.light_index==0 or self.light_index>=limit then chain=nil end
        return self:enter((chain and self.profile.combo_next[chain])or 'RKSS_Light1')
    end
    if request=='heavy'then
        local stage=chain and tonumber(chain:match('^RKSS_Heavy([12])Release$'))
        return self:start_heavy(stage and self.profile.heavy.stages[stage].next_stage or 1,true)
    end
end

function M:recover(name)
    self.combo_clip=family(name)and name or nil
    self.combo_until=self.combo_clip and self.clock+COMBO_GRACE or nil
    self:enter(nil)
end

function M:step(dt,input)
    assert(dt>=0 and dt<=.25,'Invalid combat step')
    input=input or {};self.events={};self.clock=self.clock+dt
    if self.light_until and self.clock>self.light_until and self:light_ready()then
        self.light_index=0;self.light_until=nil;self.light_pause_until=nil
    end
    if not input.guard then self.guard_locked=false end
    if input.guard_cost and self:is_guarding()then
        self.stamina=math.max(0,self.stamina-input.guard_cost)
        if self.stamina==0 then self.guard_locked=true;self:emit('guard_break');self:enter('RKSS_GuardEnd')end
    end
    local request=self:request(input)
    local name=self.clip
    if request=='plunge'then
        self.pending=nil;self.next_light_pending=false;self.combo_clip=nil;self.combo_until=nil
        self:dispatch(request)
        return self.events
    end
    local jump=self.profile.jump
    local air_plunge=jump and (name==jump.start or name==jump.loop)
    if air_plunge then self.pending=nil;self.next_light_pending=false end
    if request and not (name==self.profile.art.start and (request=='art' or request=='art_heavy')) then
        self:queue(request)
    end
    local data=name and self.profile.clips[name];local old=self.time
    self.time=self:advance_time(old,dt,input.triangle)
    local light=family(name)=='light'
    if light and self.light_contact_serial~=self.serial and self.time+1e-6>=self.contact_end[name]then
        self.light_contact_serial=self.serial
        local limit=self.profile.light_chain and self.profile.light_chain.max_hits or 5
        if self.light_index==limit then
            local pause=self.profile.light_chain and self.profile.light_chain.pause_seconds or .25
            self.light_pause_until=self.clock-math.max(0,self.time-self.contact_end[name])+pause
        end
    end
    if self:is_guarding()then self.stamina=math.min(100,self.stamina+7*dt)
    else self.stamina=math.min(100,self.stamina+35*dt)end

    local free=not name or name=='RKSS_GuardLoop' or name=='RKSS_GuardStart' or name=='RKSS_GuardEnd'
    if free then
        if self:pending_ready()then
            local command=self:take_pending()
            if self:dispatch(command)then self.combo_clip=nil;self.combo_until=nil end
        elseif input.guard and not self.guard_locked then
            if not self:is_guarding()then
                self.combo_clip=nil;self.combo_until=nil;self:enter('RKSS_GuardStart')
            elseif name=='RKSS_GuardStart' and self.time>=data.duration then self:enter('RKSS_GuardLoop')end
        elseif self:is_guarding()then self:enter('RKSS_GuardEnd')
        elseif data and self.time>=data.duration then self:enter(nil)end
    elseif air_plunge then
        if input.on_ground or input.landed then self:enter(jump.land,true)
        elseif name==jump.start and old+1e-6>=data.duration then self:enter(jump.loop,true)end
    elseif jump and name==jump.land then
        if input.guard_pressed and not self.guard_locked then self.guard_buffer=true end
        local combo_at=self.pending=='heavy' and data.heavy_combo_open or data.light_combo_open
        if self.guard_buffer and not self.guard_locked and old+1e-6>=data.guard_open then
            self:enter('RKSS_GuardStart')
        elseif self:pending_ready()and old+1e-6>=combo_at then
            local command=self:take_pending()
            if not self:dispatch(command,name)then self:recover(name)end
        elseif (input.move and self.time+1e-6>=data.move_open)
            or self.time+1e-6>=math.min(data.duration,jump.land_idle_at or data.move_open)then
            self:recover(name)
        end
    elseif name==self.profile.art.start then
        -- Sample the complete stance once before playing the selected branch.
        if old+1e-6>=data.duration then self:enter(assert(self.art_followup),true)end
    else
        local next_art,art_at=self:next_art(name)
        local bomb=name=='RKSS_RopeBomb'
        if input.guard_pressed and not self.guard_locked then self.guard_buffer=true end
        if bomb and not self.release_fired and self.time>=self.profile.bomb.release then
            self.release_fired=true;self:emit('throw_bomb',{serial=self.serial})
        end
        local ready=bomb and (self.profile.bomb.release+.12)or self.contact_end[name]
        -- Keep the outgoing pose/serial for the last collision sample when
        -- a frame crosses the boundary. Transition on the next sample.
        local recovery=old+1e-6>=ready
        if next_art then
            -- Each automatic follow-up waits for the original R1 gate.
            if old+1e-6>=art_at then self:enter(next_art,true)end
        elseif recovery and self.guard_buffer and not self.guard_locked then
            self.combo_clip=nil;self.combo_until=nil;self.next_light_pending=false
            self:enter('RKSS_GuardStart')
            if name==self.profile.cancel.move or family(name)=='heavy' then
                self:emit('cancel_flame',{seconds=self.profile.cancel.flame_seconds,extra_damage=0})
            end
        elseif recovery and self:pending_ready()then
            local command=self:take_pending()
            if not self:dispatch(command,name)then self:recover(name)end
        elseif recovery and ((input.move and not bomb)or self.time>=math.min(data.duration,ready+RECOVERY_TAIL))then
            self:recover(name)
        end
    end
    if dt>0 and self.clip==name and data then
        local sample_old=jump and name==jump.loop and old%data.duration or old
        local elapsed=self.time-old
        local intervals={{sample_old,math.min(sample_old+elapsed,data.duration),0}}
        if jump and name==jump.loop and sample_old+elapsed>data.duration then
            intervals[#intervals+1]={0,math.min(sample_old+elapsed-data.duration,data.duration),data.duration-sample_old}
        end
        for _,interval in ipairs(intervals)do
            for index,hit in ipairs(data.hits)do
                local first=math.max(interval[1],hit.start)
                local last=math.min(interval[2],hit.finish)
                if last>=first and interval[1]<hit.finish-1e-6 then
                    self:emit('hit_window',{hit=hit,index=index,serial=self.serial,
                        from_time=first,time=last,step_from=interval[1],step_to=interval[2],
                        step_offset=interval[3],step_elapsed=elapsed,
                        light_index=light and self.light_index or nil,plunge_serial=self.plunge_serial,
                        heavy_charged=family(name)=='heavy' and self.heavy_charged or false,
                        plunge_phase=self.plunge_serial and (air_plunge and 'air' or 'land')or nil})
                end
            end
        end
    end
    return self.events
end

function M:cancel()
    self.events={};self.pending=nil;self.next_light_pending=false
    self.combo_clip=nil;self.combo_until=nil;self:enter(nil)
    self.light_index=0;self.light_until=nil;self.light_pause_until=nil
    return self.events
end
return M
