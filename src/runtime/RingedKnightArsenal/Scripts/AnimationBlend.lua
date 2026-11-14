-- PBZ build 26367565: the native AnimGraph root links directly to BoatSlot.
-- Keep the original AnimInstance and let its slot mix paused pose samples.
local M = {}
M.__index = M

local NATIVE_CLASS = 'AnimBlueprintGeneratedClass /HuaShira/Characters/Hero/Hero_Hun/Animation/PBZ_ABP_Hun_Base.PBZ_ABP_Hun_Base_C'
local DEFAULT_BLEND_IN = .09
local DEFAULT_BLEND_OUT = .16
local LENGTH_TOLERANCE = .02
local MIN_TRACK_RATE, MAX_TRACK_RATE = .01, 100

local function valid(object)
    return object and object:IsValid() == true
end

local function same(first, second)
    return valid(first) and valid(second) and first:GetAddress() == second:GetAddress()
end

local function blend_settings(seconds)
    -- UE 5.7 EMontageBlendMode::Standard and EAlphaBlendOption::HermiteCubic.
    return {BlendMode = 0, Blend = {BlendTime = seconds, BlendOption = 2}}
end

function M.new(mesh)
    assert(valid(mesh), 'Animation blend requires the hero mesh')
    return setmetatable({mesh = mesh, slot = FName('BoatSlot')}, M)
end

function M:native_instance()
    if not valid(self.mesh) then return nil end
    local instance = self.mesh:GetAnimInstance()
    if valid(instance) and instance:GetClass():GetFullName() == NATIVE_CLASS then return instance end
end

function M:native_active()
    local instance = self:native_instance()
    if not instance then return nil end
    local active = instance:GetCurrentActiveMontage()
    return not not (valid(active) and not self:owns(active))
end

function M:owns(montage)
    if same(montage,self.montage)or same(montage,self.pending_montage)then return true end
    for _,entry in ipairs(self.retiring or {})do if same(montage,entry.montage)then return true end end
    return false
end

function M:restore_postprocess()
    if self.postprocess_previous ~= nil and valid(self.mesh) then
        self.mesh:SetDisablePostProcessBlueprint(self.postprocess_previous)
    end
    self.postprocess_previous = nil
    self.postprocess_delay = nil
end

local function optional_number(object, field, method)
    local ok,value=pcall(function()return method and object[method](object)or object[field]end)
    return ok and type(value)=='number'and tostring(value)or 'unavailable'
end

function M:play(asset, duration, loop, blend_in, slot_name, requested_path)
    assert(IsInGameThread(), 'Animation blend requires game thread')
    assert(valid(asset) and type(duration) == 'number' and duration > 0 and duration < math.huge, 'Invalid sword animation')
    local asset_name = asset:GetFullName()
    requested_path=requested_path or asset_name:match('^[^ ]+ (.+)$')
    assert(asset_name=='AnimSequence '..requested_path,
        'Animation asset identity mismatch: requested='..tostring(requested_path)..' actual='..asset_name)
    assert(asset_name:match('^AnimSequence '), 'Unexpected sword animation class: ' .. asset_name)
    assert(asset.bEnableRootMotion == false, 'Slot animation must use the existing manual root motion')
    local asset_length, asset_rate = asset:GetPlayLength(), asset.RateScale
    assert(type(asset_length) == 'number' and asset_length > 0 and asset_length < math.huge,
        'Invalid source animation length: ' .. asset_name)
    assert(type(asset_rate) == 'number' and asset_rate == asset_rate and math.abs(asset_rate) < math.huge,
        'Invalid source animation RateScale: ' .. asset_name)
    -- UE FAnimSegment treats a nearly-zero combined rate as one. These forward
    -- clips use one complete segment with AnimPlayRate=1 and LoopingCount=1.
    local track_rate = math.abs(asset_rate) <= 1e-8 and 1 or asset_rate
    assert(track_rate>=MIN_TRACK_RATE and track_rate<=MAX_TRACK_RATE,
        'Unsupported source animation RateScale: requested='..requested_path..' actual='..asset_name..' RateScale='..tostring(asset_rate))
    local expected_length = asset_length / track_rate
    assert(expected_length>0 and expected_length<math.huge,'Invalid source segment length: '..asset_name)
    local context = string.format('requested=%s asset=%s profile=%.9g source=%.9g SequenceLength=%s RateScale=%.9g expected_montage=%.9g slot=%s',
        requested_path,asset_name,duration,asset_length,optional_number(asset,'SequenceLength'),asset_rate,expected_length,slot_name or 'BoatSlot')
    assert(math.abs(asset_length - duration) <= LENGTH_TOLERANCE, 'Source length differs from the combat profile; ' .. context)
    local instance = assert(self:native_instance(), 'Native hero animation instance unavailable')
    if self.instance and not same(self.instance, instance) then self:stop(0) end
    local active = instance:GetCurrentActiveMontage()
    if valid(active) and not self:owns(active) then return false, 'Native montage active' end

    blend_in = blend_in or DEFAULT_BLEND_IN
    slot_name=slot_name or 'BoatSlot'
    assert(slot_name=='BoatSlot'or slot_name=='LeftArmOverride'or slot_name=='RightArmOverride','Unsupported hero montage slot')
    local slot=FName(slot_name)
    local whole_body=slot_name=='BoatSlot'
    local factory = StaticFindObject('/Script/Engine.Default__AnimMontage')
    assert(valid(factory), 'Native montage factory unavailable')
    local montage = factory:CreateSlotAnimationAsDynamicMontage_WithBlendSettings(
        asset, slot, blend_settings(blend_in), blend_settings(DEFAULT_BLEND_OUT), 1, 1, -1)
    assert(valid(montage), 'Dynamic montage creation failed')

    if whole_body and self.postprocess_previous == nil then
        local previous = self.mesh:GetDisablePostProcessBlueprint()
        assert(type(previous) == 'boolean', 'Unexpected post-process state')
        self.postprocess_previous = previous
        self.mesh:SetDisablePostProcessBlueprint(true)
    end

    local previous_montage = self.montage
    self.pending_montage = montage
    local ok, why = pcall(function()
        -- bStopAllMontages=false. Only the previous owned montage is faded.
        local length = instance:Montage_Play(montage, 1, 0, 0, false)
        local actual=context..' montage='..montage:GetFullName()..' montage_GetPlayLength='..optional_number(montage,nil,'GetPlayLength')
            ..' montage_SequenceLength='..optional_number(montage,'SequenceLength')..' montage_RateScale='..optional_number(montage,'RateScale')
        assert(type(length) == 'number' and length > 0 and length < math.huge,
            'Dynamic montage playback rejected; ' .. actual .. ' returned=' .. tostring(length))
        -- MontageLength is the segment's length, independent of Montage_Play's
        -- InPlayRate. Segment length already includes the source RateScale.
        assert(math.abs(length - expected_length) <= LENGTH_TOLERANCE,
            'Montage length differs from the source segment; ' .. actual .. ' returned=' .. tostring(length))
        instance:Montage_Pause(montage)
        assert(instance:Montage_IsActive(montage) and not instance:Montage_IsPlaying(montage), 'Manual montage clock unavailable')
        if same(instance, self.instance) and valid(previous_montage) then
            instance:Montage_Stop(blend_in, previous_montage)
            self.retiring=self.retiring or {}
            self.retiring[#self.retiring+1]={montage=previous_montage,instance=instance,remaining=blend_in}
        end
    end)
    self.pending_montage = nil
    if not ok then
        pcall(instance.Montage_Stop, instance, 0, montage)
        if not valid(previous_montage) and self.fade_remaining == nil then self:restore_postprocess() end
        error(why)
    end
    self.instance, self.montage = instance, montage
    self.slot=slot
    -- The stock arm masks exclude pelvis/legs. Let native post-process run
    -- again once the outgoing whole-body layer has faded.
    self.postprocess_delay=not whole_body and self.postprocess_previous~=nil and blend_in or nil
    self.duration,self.source_duration,self.loop,self.idle_time,self.track_rate=duration,asset_length,loop,0,track_rate
    self.fade_remaining = nil
    return true
end

function M:seek(time)
    assert(type(time)=='number'and time==time and time>=0 and time<math.huge,'Invalid animation pose time')
    local instance = self:native_instance()
    if not same(instance, self.instance) or not same(instance:GetCurrentActiveMontage(), self.montage) then return false end
    local position = self.loop and time % self.duration or math.min(time, self.duration)
    self.instance:Montage_SetPosition(self.montage, math.min(position,self.source_duration) / self.track_rate)
    return true
end

function M:advance_idle(dt)
    self.idle_time = self.idle_time + dt
    return self:seek(self.idle_time)
end

function M:slot_weight()
    if not same(self:native_instance(), self.instance) then return 0 end
    return self.instance:Blueprint_GetSlotMontageLocalWeight(self.slot)
end

function M:stop(seconds)
    assert(IsInGameThread(), 'Animation blend cleanup requires game thread')
    seconds = seconds or 0
    local stop = valid(self.montage) and same(self:native_instance(), self.instance)
    local ok, why = true, nil
    if stop then ok, why = pcall(self.instance.Montage_Stop, self.instance, seconds, self.montage) end
    if not ok then
        self:restore_postprocess()
        error(why)
    end
    if seconds==0 then
        for _,entry in ipairs(self.retiring or {})do
            if same(entry.instance,self:native_instance())and valid(entry.montage)then
                pcall(entry.instance.Montage_Stop,entry.instance,0,entry.montage)
            end
        end
        self.retiring=nil
    elseif stop then
        self.retiring=self.retiring or {}
        self.retiring[#self.retiring+1]={montage=self.montage,instance=self.instance,remaining=seconds}
    end
    self.montage = nil
    if stop and seconds > 0 then
        self.fade_remaining = seconds
    elseif seconds == 0 or self.fade_remaining == nil then
        self.fade_remaining, self.instance = nil, nil
        self:restore_postprocess()
    end
end

function M:update(dt)
    for i=#(self.retiring or {}),1,-1 do
        local entry=self.retiring[i];entry.remaining=entry.remaining-dt
        if entry.remaining<=0 or not valid(entry.montage)then table.remove(self.retiring,i)end
    end
    if self.postprocess_delay then
        self.postprocess_delay=self.postprocess_delay-dt
        if self.postprocess_delay<=0 then self:restore_postprocess()end
    end
    if self.fade_remaining == nil then return end
    self.fade_remaining = self.fade_remaining - dt
    if self.fade_remaining <= 0 or not same(self:native_instance(), self.instance) then
        self.fade_remaining, self.instance = nil, nil
        self:restore_postprocess()
    end
end

M.move_blend_out = DEFAULT_BLEND_OUT

return M
