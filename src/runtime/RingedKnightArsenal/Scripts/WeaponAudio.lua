-- One-shots from the selected DS3 PCM samples, with stock Wwise cues for
-- roles without a local sample. Audio errors never interrupt combat.
local M = {}
M.__index = M
local folder = assert(debug.getinfo(1, 'S').source:match('^@(.*[/\\])'), 'Cannot locate audio scripts')
local json = dofile(folder .. 'dkjson.lua')

local FUNCTION = '/Script/AkAudio.AkGameplayStatics:PostEventAtLocation'
local CDO = '/Script/AkAudio.Default__AkGameplayStatics'
local parameters = {
    [0] = {'akevent', 'objectproperty'},
    [8] = {'location', 'structproperty'},
    [32] = {'orientation', 'structproperty'},
    [56] = {'worldcontextobject', 'objectproperty'},
    [64] = {'returnvalue', 'intproperty'},
}
local orientation = {Pitch = 0, Yaw = 0, Roll = 0}

local function valid(object)
    return object and object:IsValid()
end

local function finite(value)
    return type(value) == 'number' and value > -math.huge and value < math.huge
end

function M.new(load_asset, profile, log, definition)
    local clips = {}
    for name, stock_rule in pairs(definition.clips) do
        local cooked_rule = definition.waves and definition.cooked_clips and definition.cooked_clips[name]
        local rule = cooked_rule or stock_rule
        local cues = {}
        if rule.cues then
            cues = {table.unpack(rule.cues)}
        elseif rule.time then
            cues[1] = {time = rule.time, role = rule.role}
        elseif profile.clips[name] then
            for _, hit in ipairs(profile.clips[name].hits) do
                cues[#cues + 1] = {time = math.max(0, hit.start - rule.lead), role = rule.role}
            end
            table.sort(cues, function(a, b) return a.time < b.time end)
        end
        clips[name] = {requires_charge = rule.requires_charge, cues = cues}
    end
    return setmetatable({load_asset = load_asset, log = log, events = definition.events, clips = clips,
        waves = definition.waves or {}, wave_assets = {}, fallback_roles = definition.fallback_roles or {},
        assets = {}, reported = {}, posted = {}, pending = {}, pending_count = 0, index = 1}, M)
end

function M:report_once(key, message)
    if self.reported[key] then return end
    self.reported[key] = true
    if self.log then self.log('Audio ' .. key .. ': ' .. tostring(message)) end
end

function M:dispatcher()
    if valid(self.statics) then return self.statics end
    if self.schema_error then error(self.schema_error) end
    local ok, result, arguments = pcall(function()
        local fn = StaticFindObject(FUNCTION)
        assert(valid(fn) and fn:GetFullName() == 'Function ' .. FUNCTION, 'native PostEventAtLocation unavailable')
        local argument_order, observed, offsets = {}, {}, {}
        local matches = true
        fn:ForEachProperty(function(property)
            local name = property:GetFName():ToString():lower()
            local kind = property:GetClass():GetFName():ToString():lower()
            local offset = property:GetOffset_Internal()
            local expected = parameters[offset]
            observed[#observed + 1] = string.format('%s %s@%d', kind, name, offset)
            if not expected or offsets[offset] or name ~= expected[1] or kind ~= expected[2] then
                matches = false
                return
            end
            offsets[offset] = true
            -- UE4SS marshals positional arguments in reflected order, skipping the return value.
            if name ~= 'returnvalue' then argument_order[#argument_order + 1] = name end
        end)
        assert(matches and #observed == 5, 'native Wwise parameter schema changed: ' .. table.concat(observed, ', '))
        local statics = StaticFindObject(CDO)
        assert(valid(statics) and statics:GetFullName() == 'AkGameplayStatics ' .. CDO, 'native Wwise default object unavailable')
        return statics, argument_order
    end)
    if not ok then
        self.schema_error = result
        error(result)
    end
    self.statics = result
    self.arguments = arguments
    return result
end

function M:asset(role)
    if valid(self.assets[role]) then return self.assets[role] end
    local object = self.load_asset(assert(self.events[role], 'unknown native sound cue'))
    assert(valid(object) and object:GetClass():GetFName():ToString():lower() == 'akaudioevent', 'sound cue is not a live AkAudioEvent')
    self.assets[role] = object
    return object
end

function M:wave(path)
    if valid(self.wave_assets[path]) then return self.wave_assets[path] end
    local asset = self.load_asset(path)
    assert(valid(asset) and asset:GetClass():GetFName():ToString():lower() == 'soundwave',
        'Expected cooked weapon SoundWave: ' .. path)
    self.wave_assets[path] = asset
    return asset
end

function M:play_wave(role, pawn, point)
    assert(self.pending_count < 64, 'PCM request tracking limit reached')
    local path = self.waves[role]
    local name = assert(path and path:match('%.(SW_DS3_[%w_]+)$'), 'Invalid selected DS3 sample')
    assert(type(RK_PlayPcm) == 'function', 'Native PCM audio bridge unavailable')
    local raw, failure = RK_PlayPcm(json.encode({name = name, volume = .8}))
    assert(raw, failure or 'Native PCM audio rejected the sample')
    local receipt, _, error_message = json.decode(raw)
    if type(receipt) == 'table' and receipt.backend == 'xaudio2_9' and receipt.queued == true
        and receipt.started == false and finite(receipt.request_id) and receipt.request_id > 0 then
        assert(self.pending_count < 64 and not self.pending[receipt.request_id], 'PCM request tracking limit reached')
        self.pending[receipt.request_id] = {role = role, name = name}
        self.pending_count = self.pending_count + 1
        return true, receipt.request_id
    end
    assert(type(receipt) == 'table' and receipt.backend == 'xaudio2_9' and receipt.started == true
        and receipt.sample == name and finite(receipt.playing_id) and receipt.playing_id > 0,
        error_message or 'Native PCM audio did not confirm a started voice')
    self.posted[role] = (self.posted[role] or 0) + 1
    self:report_once('posted_' .. role, 'DS3 PCM ' .. name .. ' playing ID ' .. receipt.playing_id)
    return true, receipt.playing_id
end

function M:poll()
    if self.pending_count == 0 or type(RK_PlayPcm) ~= 'function' or not IsInGameThread() then return end
    local ok, failure = pcall(function()
        local raw, error_message = RK_PlayPcm(json.encode({phase = 'receipts'}))
        assert(raw, error_message or 'PCM receipts unavailable')
        local batch = json.decode(raw)
        assert(type(batch) == 'table' and batch.backend == 'xaudio2_9' and type(batch.receipts) == 'table'
            and #batch.receipts <= 64, 'Invalid PCM receipt batch')
        for _, receipt in ipairs(batch.receipts) do
            local pending = self.pending[receipt.request_id]
            if pending then
                self.pending[receipt.request_id] = nil
                self.pending_count = self.pending_count - 1
                if pending.prepare then
                    self.pcm_ready = receipt.validated == true
                    if not self.pcm_ready then self:report_once('pcm_prepare', receipt.error or 'PCM preload failed') end
                elseif receipt.sample == pending.name and receipt.started == true
                    and finite(receipt.playing_id) and receipt.playing_id > 0 then
                    self.posted[pending.role] = (self.posted[pending.role] or 0) + 1
                    self:report_once('posted_' .. pending.role, 'DS3 PCM ' .. pending.name .. ' playing ID ' .. receipt.playing_id)
                else
                    self:report_once('wave_' .. pending.role, receipt.error or 'PCM voice did not start')
                end
            end
        end
    end)
    if not ok then self:report_once('pcm_receipts', failure) end
end

function M:prepare()
    if not IsInGameThread() then return false end
    self:poll()
    local ready = true
    if next(self.waves) then
        local loaded, failure = pcall(function()
            assert(self.pending_count < 64, 'PCM request tracking limit reached')
            assert(type(RK_PlayPcm) == 'function', 'Native PCM audio bridge unavailable')
            local raw, error_message = RK_PlayPcm(json.encode({phase = 'prepare'}))
            assert(raw, error_message or 'Native PCM sample validation failed')
            local receipt = json.decode(raw)
            assert(type(receipt) == 'table' and receipt.backend == 'xaudio2_9', 'Invalid native PCM preparation receipt')
            if receipt.queued == true and receipt.started == false and finite(receipt.request_id) and receipt.request_id > 0 then
                assert(self.pending_count < 64 and not self.pending[receipt.request_id], 'PCM request tracking limit reached')
                self.pending[receipt.request_id] = {prepare = true}
                self.pending_count = self.pending_count + 1
                self.pcm_ready = false
            else
                assert(receipt.validated == true, 'Native PCM sample validation was not confirmed')
                self.pcm_ready = true
            end
        end)
        if not loaded then self:report_once('pcm_prepare', failure); ready = false end
    end
    for role in pairs(self.events) do
        if not self.waves[role] then
            local loaded, failure = pcall(function()
                self:dispatcher()
                self:asset(role)
            end)
            if not loaded then
                self:report_once(self.schema_error and 'schema' or role, failure)
                ready = false
            end
        end
    end
    return ready
end

function M:play(role, pawn, location)
    if not IsInGameThread() then return false end
    self:poll()
    if self.waves[role] then
        local ok, played = pcall(function()
            assert(valid(pawn), 'sound world context unavailable')
            local point = location or pawn:K2_GetActorLocation()
            local xyz = {X = point.X, Y = point.Y, Z = point.Z}
            assert(finite(xyz.X) and finite(xyz.Y) and finite(xyz.Z), 'invalid sound position')
            return self:play_wave(role, pawn, xyz)
        end)
        if not ok then self:report_once('wave_' .. role, played) end
        -- A selected DS3 cue must not silently turn into a different stock cue.
        return ok and played or false
    end
    local fallback_role = self.events[role] and role or self.fallback_roles[role]
    if self.schema_error or not fallback_role then return false end
    local ok, playing_id = pcall(function()
        assert(valid(pawn), 'sound world context unavailable')
        local statics = self:dispatcher()
        local event = self:asset(fallback_role)
        local position = location or pawn:K2_GetActorLocation()
        local xyz = {X = position.X, Y = position.Y, Z = position.Z}
        assert(finite(xyz.X) and finite(xyz.Y) and finite(xyz.Z), 'invalid sound position')
        local values = {akevent = event, location = xyz, orientation = orientation, worldcontextobject = pawn}
        local arguments = {}
        for index, name in ipairs(self.arguments) do arguments[index] = values[name] end
        return statics:PostEventAtLocation(table.unpack(arguments))
    end)
    if not ok or not finite(playing_id) or playing_id == 0 then
        self:report_once(self.schema_error and 'schema' or role, ok and 'Wwise rejected the one-shot event' or playing_id)
        return false
    end
    self.posted[role] = (self.posted[role] or 0) + 1
    self:report_once('posted_' .. role, 'Wwise playing ID ' .. playing_id)
    return true, playing_id
end

function M:fire(pawn)
    -- User-approved quiet612 release; stance entry and swing-fire retain their own cues.
    return self:play('cancel_ignite', pawn)
end

function M:reset(blocked)
    self.serial, self.clip, self.index = nil, nil, 1
    self.blocked = blocked
end

function M:advance(pawn, state)
    self:poll()
    if self.serial ~= state.serial or self.clip ~= state.clip then
        self.serial, self.clip, self.index = state.serial, state.clip, 1
    end
    local rule = self.clips[state.clip]
    if not rule or (rule.requires_charge and not state.heavy_full_paid) then return end
    while rule.cues[self.index] and state.time >= rule.cues[self.index].time do
        local cue = rule.cues[self.index]
        self.index = self.index + 1
        self:play(cue.role, pawn)
    end
end

function M:guard(pawn, blocked)
    self:poll()
    if type(blocked) ~= 'number' then return end
    local previous = self.blocked
    self.blocked = blocked
    if previous and blocked > previous then self:play('guard_block', pawn) end
end

return M
