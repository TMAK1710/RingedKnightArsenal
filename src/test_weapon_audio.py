"""Offline audio contracts using the actual combat profile and PBZ asset readback."""
import json
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/runtime/RingedKnightArsenal/Scripts'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
g = lua.globals()
g.Audio = lua.eval('dofile')(str(SCRIPTS / 'WeaponAudio.lua'))
g.codec = lua.eval('dofile')(str(SCRIPTS / 'dkjson.lua'))
g.definition = lua.execute((SCRIPTS / 'RingedKnightAudio.lua').read_text(encoding='utf-8'))
g.cooked_definition = lua.execute((SCRIPTS / 'RingedKnightAudio.lua').read_text(encoding='utf-8'))
g.definition.waves = None
selected = json.loads((ROOT / 'reports/ds3-audio-selection.json').read_text(encoding='utf-8'))['assets']
assert {path.rsplit('.', 1)[-1] for path in g.cooked_definition.waves.values()} == {item['name'] for item in selected}
assert len(selected) == 19
assert g.cooked_definition.waves.cancel_ignite.endswith('/SW_DS3_Cancel_Ignite.SW_DS3_Cancel_Ignite')
assert g.cooked_definition.waves.cancel_ignite != g.cooked_definition.waves.ember_ignite
assert g.cooked_definition.waves.cancel_ignite != g.cooked_definition.waves.fire
g.selected_count = len(selected)
g.profile = lua.table_from(json.loads((SCRIPTS / 'combat-profile.json').read_text(encoding='utf-8')), recursive=True)
g.State = lua.eval('dofile')(str(SCRIPTS / 'CombatState.lua'))
audio_signature = json.loads((ROOT / 'reports/native-audio-signatures.json').read_text(encoding='utf-8'))
route, = audio_signature['functions']['PostEventAtLocation']
g.function_path = route['owner']['path'] + ':PostEventAtLocation'
g.properties = lua.table_from(route['parameters'], recursive=True)

assets = {}
for role, path in g.definition.events.items():
    package, name = path.rsplit('.', 1)
    source = ROOT / 'extract/audio/ProjectPBZ/Content' / (package.removeprefix('/Game/') + '.json')
    found, = json.loads(source.read_text(encoding='utf-8'))
    assert found['Type'] == 'AkAudioEvent' and found['Package'] == package and found['Name'] == name
    cooked = found['EventCookedData']
    assert cooked['EventId'] > 0
    assert all(x['Value']['SoundBanks'] and x['Value']['Media'] for x in cooked['EventLanguageMap'])
    assert not any(s in name.lower() for s in ('_loop', '_stop'))
    assets[role] = dict(path=path, event_id=cooked['EventId'])

lua.execute(r'''
local function object(fields)
    fields.IsValid = function(self) return not self.invalid end
    return fields
end

local function fname(value)
    return {ToString = function() return value end}
end

local bad_schema, game_thread, rejects, throws = false, true, false, false
local calls, errors, receipts, loads = {}, {}, {}, 0
local layout = {1, 2, 3, 4, 5}
local cdo_path = '/Script/AkAudio.Default__AkGameplayStatics'
local pawn = object({K2_GetActorLocation = function() return {X = 10, Y = 20, Z = 30} end})
local fn = object({
    GetFullName = function() return 'Function ' .. function_path end,
    ForEachProperty = function(_, callback)
        for _, index in ipairs(layout) do
            local field = properties[index]
            local kind = bad_schema and field.offset == 56 and 'BoolProperty' or field.kind
            callback({
                GetFName = function() return fname(field.name:upper()) end,
                GetClass = function() return {GetFName = function() return fname(kind) end} end,
                GetOffset_Internal = function() return field.offset end,
            })
        end
    end,
})
local cdo = object({
    GetFullName = function() return 'AkGameplayStatics ' .. cdo_path end,
    PostEventAtLocation = function(_, ...)
        assert(select('#', ...) == 4)
        local values, argument = {}, 1
        for _, index in ipairs(layout) do
            local field = properties[index]
            if not field['return'] then
                values[field.name] = select(argument, ...)
                argument = argument + 1
            end
        end
        local event, point, rotation, world_context = values.AkEvent, values.Location, values.Orientation, values.WorldContextObject
        assert(world_context == pawn and rotation.Pitch == 0 and rotation.Yaw == 0 and rotation.Roll == 0)
        if throws then error('engine rejected post') end
        calls[#calls + 1] = {asset = event.path, point = point}
        return rejects and 0 or 79
    end,
})
function IsInGameThread() return game_thread end
function StaticFindObject(path)
    if path == function_path then return fn end
    if path == cdo_path then return cdo end
end
local function make()
    return Audio.new(function(path)
        loads = loads + 1
        return object({path = path, GetClass = function()
            return {GetFName = function() return fname('AKAUDIOEVENT') end}
        end})
    end, profile, function(message)
        local entries = message:match('^Audio posted_') and receipts or errors
        entries[#entries + 1] = message
    end, definition)
end

local audio = make()
assert(audio:prepare() and #calls == 0 and loads == 9)
local state = {clip = 'RKSS_Light1', serial = 1, time = .39}
audio:advance(pawn, state)
assert(#calls == 0)
state.time = .40
audio:advance(pawn, state)
audio:advance(pawn, state)
assert(#calls == 1 and calls[1].asset == definition.events.swing_light)

state = {clip = 'RKSS_Heavy1Charge', serial = 2, time = 1.18}
audio:advance(pawn, state)
assert(#calls == 1)
state.heavy_full_paid = true
audio:advance(pawn, state)
audio:advance(pawn, state)
assert(#calls == 2 and calls[2].asset == definition.events.swing_heavy)

state = {clip = 'RKSS_Ember', serial = 3, time = .53}
audio:advance(pawn, state)
state.time = .54
audio:advance(pawn, state)
state.time = 1.02
audio:advance(pawn, state)
audio:advance(pawn, state)
assert(#calls == 4)
assert(#receipts == 2 and receipts[1] == 'Audio posted_swing_light: Wwise playing ID 79')

audio:reset(19)
audio:guard(pawn, 19)
audio:guard(pawn, 20)
audio:guard(pawn, 20)
assert(#calls == 5 and calls[5].asset == definition.events.guard_block)

local ok, playing_id = audio:play('explosion', pawn, {X = 11, Y = 12, Z = 13})
assert(ok and playing_id == 79 and calls[6].point.X == 11 and calls[6].point.Z == 13)
assert(audio:play('throw', pawn) and calls[7].point.Z == 30)
assert(loads == 9)

rejects = true
assert(not audio:play('fire', pawn) and not audio:play('fire', pawn) and #errors == 1)
throws = true
assert(not audio:play('hit_light', pawn) and #errors == 2)
game_thread = false
assert(not audio:play('hit_heavy', pawn) and #errors == 2)
game_thread, rejects, throws, bad_schema = true, false, false, true
local wrong = make()
local count = #calls
assert(not wrong:prepare() and not wrong:play('swing_light', pawn) and #calls == count and #errors == 3)
assert(errors[3]:find('boolproperty worldcontextobject@56', 1, true))

bad_schema = false
layout = {5, 4, 2, 1, 3}
local reordered = make()
assert(reordered:prepare() and reordered:play('swing_light', pawn, {X = 21, Y = 22, Z = 23}))
assert(#calls == count + 1 and calls[count + 1].point.Z == 23)
assert(calls[count + 1].asset == definition.events.swing_light and #errors == 3)

local wave_calls = {}
local native_rejects, native_lies, prepared = false, false, 0
function RK_PlayPcm(payload)
    local request = assert(codec.decode(payload))
    if request.phase == 'prepare' then
        prepared = prepared + 1
        return codec.encode({backend = 'xaudio2_9', validated = true, samples = selected_count})
    end
    assert(request.volume == .8 and request.name:match('^SW_DS3_[%w_]+$'))
    if native_rejects then return nil, 'No Windows output device' end
    if native_lies then return codec.encode({started = true, playing_id = 0}) end
    wave_calls[#wave_calls + 1] = '/HuaShira/Mods/RingedKnight/Audio/' .. request.name .. '.' .. request.name
    return codec.encode({backend = 'xaudio2_9', started = true, sample = request.name, playing_id = #wave_calls})
end
local cooked = Audio.new(function(path)
    error('Selected PCM playback must not load a UE SoundWave: ' .. path)
end, profile, nil, cooked_definition)
assert(cooked:prepare() and #wave_calls == 0 and prepared == 1)
cooked:advance(pawn, {clip = 'RKSS_Light2', serial = 1, time = .32})
assert(#wave_calls == 0)
cooked:advance(pawn, {clip = 'RKSS_Light2', serial = 1, time = .34})
cooked:advance(pawn, {clip = 'RKSS_Light2', serial = 1, time = .8})
assert(#wave_calls == 1 and wave_calls[1] == cooked_definition.waves.swing_light23)
assert(cooked:play('hit_thrust', pawn))
assert(#wave_calls == 2 and wave_calls[2] == cooked_definition.waves.hit_thrust)
cooked:advance(pawn, {clip = 'RKSS_EmberStart', serial = 2, time = .76})
assert(#wave_calls == 2)
cooked:advance(pawn, {clip = 'RKSS_EmberStart', serial = 2, time = .77})
cooked:advance(pawn, {clip = 'RKSS_Ember', serial = 3, time = 1.04})
assert(#wave_calls == 7 and wave_calls[3] == cooked_definition.waves.ember_ignite)
assert(wave_calls[4] == cooked_definition.waves.swing_ember and wave_calls[5] == cooked_definition.waves.fire)
assert(wave_calls[6] == cooked_definition.waves.swing_ember and wave_calls[7] == cooked_definition.waves.fire)
cooked:advance(pawn, {clip = 'RKSS_EmberHeavy', serial = 4, time = .98})
cooked:advance(pawn, {clip = 'RKSS_GuardStart', serial = 5, time = 0})
assert(#wave_calls == 10 and wave_calls[8] == cooked_definition.waves.fire)
assert(wave_calls[9] == cooked_definition.waves.swing_ember_heavy and wave_calls[10] == cooked_definition.waves.guard_raise)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow1', serial = 6, time = .26})
assert(#wave_calls == 10)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow1', serial = 6, time = .27})
assert(#wave_calls == 11 and wave_calls[11] == cooked_definition.waves.fire)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow1', serial = 6, time = .37})
assert(#wave_calls == 12 and wave_calls[12] == cooked_definition.waves.swing_ember_follow)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow1', serial = 6, time = .87})
cooked:advance(pawn, {clip = 'RKSS_EmberFollow1', serial = 6, time = .9})
assert(#wave_calls == 14 and wave_calls[13] == cooked_definition.waves.fire)
assert(wave_calls[14] == cooked_definition.waves.swing_ember_follow)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow2', serial = 7, time = .69})
assert(#wave_calls == 14)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow2', serial = 7, time = .71})
assert(#wave_calls == 15 and wave_calls[15] == cooked_definition.waves.fire)
cooked:advance(pawn, {clip = 'RKSS_EmberFollow2', serial = 7, time = .77})
assert(#wave_calls == 16 and wave_calls[16] == cooked_definition.waves.swing_ember_follow)
cooked:advance(pawn, {clip = 'RKSS_PlungeStart', serial = 8, time = .06})
assert(#wave_calls == 16)
cooked:advance(pawn, {clip = 'RKSS_PlungeStart', serial = 8, time = .07})
assert(#wave_calls == 17 and wave_calls[17] == cooked_definition.waves.plunge_movement)
cooked:advance(pawn, {clip = 'RKSS_PlungeStart', serial = 8, time = .1})
cooked:advance(pawn, {clip = 'RKSS_PlungeStart', serial = 8, time = .5})
assert(#wave_calls == 18 and wave_calls[18] == cooked_definition.waves.plunge_start)
cooked:advance(pawn, {clip = 'RKSS_PlungeLoop', serial = 9, time = .3})
cooked:advance(pawn, {clip = 'RKSS_PlungeLoop', serial = 9, time = 1.3})
assert(#wave_calls == 18)
cooked:advance(pawn, {clip = 'RKSS_PlungeLand', serial = 10, time = 0})
assert(#wave_calls == 19 and wave_calls[19] == cooked_definition.waves.swing_ember)
cooked:advance(pawn, {clip = 'RKSS_PlungeLand', serial = 10, time = .06})
assert(#wave_calls == 19)
cooked:advance(pawn, {clip = 'RKSS_PlungeLand', serial = 10, time = .07})
cooked:advance(pawn, {clip = 'RKSS_PlungeLand', serial = 10, time = .5})
assert(#wave_calls == 20 and wave_calls[20] == cooked_definition.waves.plunge_land)
assert(cooked:fire(pawn))
assert(#wave_calls == 21 and wave_calls[21] == cooked_definition.waves.cancel_ignite)
assert(cooked:play('fire', pawn))
assert(#wave_calls == 22 and wave_calls[22] == cooked_definition.waves.fire)

local stock_count = #calls
native_rejects = true
assert(not cooked:play('guard_raise', pawn) and #wave_calls == 22 and #calls == stock_count)
native_rejects, native_lies = false, true
assert(not cooked:play('swing_light', pawn) and #wave_calls == 22 and #calls == stock_count)
RK_PlayPcm = nil
assert(not cooked:prepare() and not cooked:play('swing_light', pawn) and #calls == stock_count)

local sequence, queued, completed = 0, {}, {}
function RK_PlayPcm(payload)
    local request = assert(codec.decode(payload))
    if request.phase == 'receipts' then
        local batch = completed
        completed = {}
        return codec.encode({backend = 'xaudio2_9', receipts = batch})
    end
    sequence = sequence + 1
    queued[sequence] = request
    return codec.encode({backend = 'xaudio2_9', queued = true, started = false, request_id = sequence})
end
local asynchronous = Audio.new(function() error('No UE audio loading') end, profile, nil, cooked_definition)
assert(asynchronous:prepare() and asynchronous.pcm_ready == false and asynchronous.pending_count == 1)
assert(asynchronous:play('hit_light', pawn) and asynchronous.pending_count == 2)
assert(asynchronous.posted.hit_light == nil and sequence == 2)
completed = {{request_id = 1, validated = true, samples = selected_count}}
asynchronous:advance(pawn, {clip = false, serial = 1, time = 0})
assert(asynchronous.pcm_ready == true and asynchronous.pending_count == 1 and asynchronous.posted.hit_light == nil)
completed = {{request_id = 2, sample = queued[2].name, started = true, playing_id = 91}}
asynchronous:poll()
asynchronous:poll()
assert(asynchronous.pending_count == 0 and asynchronous.posted.hit_light == 1)
assert(asynchronous:play('hit_heavy', pawn))
completed = {{request_id = 3, sample = queued[3].name, started = false, error = 'PCM cue expired in queue'}}
asynchronous:guard(pawn, 0)
assert(asynchronous.pending_count == 0 and asynchronous.posted.hit_heavy == nil and #calls == stock_count)
assert(asynchronous:play('hit_thrust', pawn))
completed = {{request_id = 4, sample = 'SW_DS3_Fire', started = true, playing_id = 92}}
asynchronous:poll()
assert(asynchronous.pending_count == 0 and asynchronous.posted.hit_thrust == nil)
assert(asynchronous:fire(pawn))
assert(queued[5].name == 'SW_DS3_Cancel_Ignite' and asynchronous.posted.cancel_ignite == nil)
completed = {{request_id = 5, sample = queued[5].name, started = true, playing_id = 93}}
asynchronous:poll()
assert(asynchronous.pending_count == 0 and asynchronous.posted.cancel_ignite == 1)
''')

lua.execute(r'''
heavy_swing_timing = {}
for _,mode in ipairs({'tap','held','release_mid_windup','cancel_before_release'})do
    local state=State.new(profile)
    assert(state:start_heavy(2,true))
    local audio=Audio.new(function()error('Timing test must not load audio assets')end,profile,nil,cooked_definition)
    local posted={}
    audio.play=function(_,role)
        if role=='swing_heavy'then
            posted[#posted+1]={source=state.time,wall=state.clock}
        end
        return true
    end
    local canceled=false
    for frame=1,180 do
        local held=mode=='held'or(mode=='release_mid_windup'and frame<=42)
        state:step(1/120,{triangle=held})
        if mode=='cancel_before_release'and frame==10 then state:cancel();canceled=true end
        audio:advance(pawn,state)
        audio:advance(pawn,state) -- Polling twice cannot post the same cue twice.
        if state.clip=='RKSS_Heavy2Release'and state.time+1e-8<profile.heavy.windup.seconds then
            assert(#posted==0,mode..': heavy sound played while still winding up')
        end
    end
    if canceled then
        assert(#posted==0,'Canceled heavy left a stale swing cue')
        heavy_swing_timing[#heavy_swing_timing+1]={mode=mode,posted=0}
    else
        assert(#posted==1,mode..': expected one swing sound')
        assert(posted[1].source+1e-8>=profile.heavy.windup.seconds)
        assert(posted[1].source<=profile.clips.RKSS_Heavy2Release.hits[1].start,
            mode..': swing audio was delayed past contact')
        heavy_swing_timing[#heavy_swing_timing+1]={mode=mode,posted=1,source=posted[1].source,wall=posted[1].wall}
    end
end
''')
timing_results = [{key: value for key, value in row.items()} for row in g.heavy_swing_timing.values()]
report = dict(ok=True, scope='offline PE and selected-asset readback plus mocked native PCM receipts, real combat-state timing and error isolation',
              function=g.function_path, assets=assets, runtime_audio_verified=False,
              heavy_swing_timing=timing_results,
              source_sha256={name: hashlib.sha256((SCRIPTS / name).read_bytes()).hexdigest()
                             for name in ('RingedKnightAudio.lua','WeaponAudio.lua','CombatState.lua','combat-profile.json')})
(ROOT / 'reports/weapon-audio-offline.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(f'PASS {len(selected)} DS3 PCM bindings, 4 heavy windup timing cases, queued versus started receipts, errors and expiry, and {len(assets)} legacy Wwise cues')
