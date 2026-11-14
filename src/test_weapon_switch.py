"""Offline contracts for selection recovery after a rejected native switch request."""
import json
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/runtime/RingedKnightArsenal/Scripts'
sys.path.insert(0, str(ROOT / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

lua = LuaRuntime()
g = lua.globals()
g.Switch = lua.execute((SCRIPTS / 'WeaponSwitch.lua').read_text(encoding='utf-8'))
routes = json.loads((ROOT / 'reports/native-weapon-switch-signatures.json').read_text(encoding='utf-8'))
properties = {}
for method, (route,) in routes.items():
    path = route['owner']['path'] + ':' + method
    properties[path] = [f'{p["kind"]} {path}:{p["name"]}' for p in route['parameters']]
commit = json.loads((ROOT / 'reports/weapon-switch-offline.json').read_text(encoding='utf-8'))
g.commit_path, g.cdo_path = commit['function'], commit['cdo']
properties[g.commit_path] = [f'{p["Type"]} {g.commit_path}:{p["Name"]}' for p in commit['fields']]
g.properties = lua.table_from(properties, recursive=True)

lua.execute(r'''
local input = '/Script/SGameInputSystem.AbilityInputComponent:TryActivateExternalActionAbilityInterruptLowerByTag'
local function object(address, fields)
    fields.IsValid = function() return true end
    fields.GetAddress = function() return address end
    return fields
end
function FName(value)
    return {ToString = function() return value end}
end
local malformed, bad_commit, action_asset, cdo_asset
function StaticFindObject(path)
    if path == '/SGameCombatSystem/Weapon/Input/IA_ChangeWeapon.IA_ChangeWeapon' then return action_asset end
    if path == cdo_path then return cdo_asset end
    if not properties[path] then return end
    return object(91, {
        GetFullName = function() return 'Function ' .. path end,
        ForEachProperty = function(_, callback)
            for index, field in ipairs(properties[path]) do
                local changed = (malformed and path == input and index == 4)
                    or (bad_commit and path == commit_path and index == 5)
                local full_name = changed and 'IntProperty Mock:Changed' or field
                callback({GetFullName = function() return full_name end})
            end
        end,
    })
end

local callback
function RegisterHook(path, pre, post)
    assert(path == input and pre() == nil)
    callback = post
    return 7, 8
end
function UnregisterHook(path, pre, post)
    assert(path == input and pre == 7 and post == 8)
    callback = nil
end
local in_game_thread = true
function IsInGameThread() return in_game_thread end
local components
function FindAllOf(class) return components[class] end

local function scenario(changes)
    local s = {
        slots = {'Stock', 'RKA'}, index = 0, actor_index = 0, cooldown = 0,
        select_calls = 0, sync_calls = 0, logs = {},
    }
    for key, value in pairs(changes or {}) do s[key] = value end
    local pawn = object(21, {})
    local owner = object(31, {CurrentMainWeaponID = FName(s.slots[s.index + 1])})
    s.owner = owner
    owner.HasWeapon = function(_, id, normal)
        assert(normal and id:ToString() == 'RKA')
        return not s.unowned
    end
    owner.SetCurrentWeaponByIndex = function(self, index, normal)
        assert(normal and s.slots[index + 1] == 'RKA' and s.actor_index == index)
        s.sync_calls = s.sync_calls + 1
        if s.reject_sync then return end
        s.index = index
        self.CurrentMainWeaponID = FName(s.slots[index + 1])
    end
    local function assert_main(slot)
        assert(slot.TagName:ToString() == 'Weapon.Slot.Main')
    end
    local weapons = object(41, {
        GetOwner = function() return pawn end,
        GetCurrentWeaponIndex = function(_, slot, with_pending)
            assert_main(slot)
            return with_pending and s.pending or s.actor_index
        end,
        GetNextWeaponIndex = function() error('cached next index must not gate an explicit equipped slot') end,
        GetCurrentChangeWeaponCooldown = function(_, slot) assert_main(slot) return s.cooldown end,
        SetCurrentWeapon = function(_, slot, index)
            assert_main(slot)
            assert(s.slots[index + 1] == 'RKA')
            s.select_calls = s.select_calls + 1
            if s.reject then return false end
            if s.defer then
                s.pending = index
                return true
            end
            s.actor_index = index
            if s.auto_sync then
                s.index = index
                owner.CurrentMainWeaponID = FName(s.slots[index + 1])
            end
            return true
        end,
    })
    cdo_asset = object(70, {
        GetFullName = function() return 'BPL_PBZCombatUtils_C ' .. cdo_path end,
        ['Change Weapon'] = function(self, avatar, slot, index, armed, world_context)
            assert(self == cdo_asset and avatar == pawn and world_context == pawn and armed == true)
            if weapons:SetCurrentWeapon(slot, index) then
                s.native_lifecycle_calls = (s.native_lifecycle_calls or 0) + 1
            end
        end,
    })
    components = {
        CharacterWeaponsComponent = {weapons},
        PBZAbilitySystemComponent = {object(42, {
            GetOwner = function() return pawn end,
            HasMatchingGameplayTag = function(_, tag)
                local value=tag.TagName:ToString()
                return s.block==value or (s.blocks and s.blocks[value])==true
            end,
        })},
    }
    local equipment = {snapshot = function(_, queried)
        assert(queried == owner)
        return {slots = {table.unpack(s.slots)}, current = s.index, owner = queried:GetAddress()}
    end}
    local registry = {get = function(_, id) return id == 'RKA' and {} or nil end}
    local action = object(61, {GetFullName = function()
        return 'InputAction /SGameCombatSystem/Weapon/Input/IA_ChangeWeapon.IA_ChangeWeapon'
    end, Triggers = {}, Modifiers = {}})
    action_asset, s.action = action, action
    s.instance = {SourceAction = action, TriggerEvent = 0, LastTriggeredWorldTime = 0}
    s.mapping = {Action = action, Key = {KeyName = FName('ReboundKey')},
        Triggers = {object(62, {
            HoldTimeThreshold = .4,
            GetClass = function()
                return {GetFName = function() return FName('InputTrigger_HoldAndReleaseEarly') end}
            end,
        })}, Modifiers = {}, bShouldBeIgnored = false}
    s.input = object(63, {EnhancedActionMappings = {s.mapping}, ActionInstanceData = {
        Contains = function(_, key) return key == action and not s.no_action_instance end,
        Find = function(_, key) assert(key == action and not s.no_action_instance) return s.instance end,
    }})
    local pc = object(64, {PlayerInput = s.input,
        IsInputKeyDown = function(_, key) return s.down == key.KeyName:ToString() end})
    s.adapter = Switch.new(equipment, registry, function()
        if not s.menu then return pawn, owner, pc end
    end, function(message) s.logs[#s.logs + 1] = message end)
    s.fire = function(result, ability, input_action, priority, other)
        callback(object(51, {GetOwner = function() return other and owner or pawn end}),
            result,
            {TagName = FName(ability or 'Ability.Action.Hun.Weapon.Switch.Normal')},
            object(61, {GetFullName = function()
                local action = input_action or 'IA_ChangeWeapon'
                return 'InputAction /SGameCombatSystem/Weapon/Input/' .. action .. '.' .. action
            end}),
            priority or -4)
    end
    return s
end

local s = scenario()
assert(s.adapter:register())
s.fire(false)
s.fire(false)
assert(s.select_calls == 0 and s.sync_calls == 0)
local receipt = assert(s.adapter:poll())
assert(receipt.pawn == 21 and receipt.owner == 31 and receipt.source == 'Stock'
    and receipt.source_slot == 0 and receipt.slot == 1 and receipt.id == 'RKA')
assert(s.select_calls == 1 and s.sync_calls == 1 and s.index == 1 and s.actor_index == 1)
assert(s.native_lifecycle_calls == 1)
assert(s.slots[1] == 'Stock' and s.slots[2] == 'RKA')
assert(not s.adapter:poll())
s.adapter:dispose()
assert(not callback)

s = scenario({auto_sync = true})
assert(s.adapter:register())
s.fire(false, 'Ability.Action.Hun.Weapon.Switch.Dash')
assert(s.adapter:poll() and s.select_calls == 1 and s.sync_calls == 0)
s.adapter:dispose()

s = scenario({slots = {'RKA', 'Stock'}, index = 1, actor_index = 1})
assert(s.adapter:register())
s.fire(false)
receipt = assert(s.adapter:poll())
assert(receipt.source_slot == 1 and receipt.slot == 0 and s.index == 0 and s.actor_index == 0)
s.adapter:dispose()

for _, options in ipairs({{reject = true}, {defer = true}, {reject_sync = true}}) do
    s = scenario(options)
    assert(s.adapter:register())
    s.fire(false)
    assert(not s.adapter:poll() and not s.adapter:poll() and s.select_calls == 1)
    assert(s.sync_calls == (options.reject_sync and 1 or 0))
    s.adapter:dispose()
end

for _, options in ipairs({
    {slots = {'Stock', 'Other'}},
    {slots = {'Stock', 'RKA'}, index = 1, actor_index = 1},
    {cooldown = .04}, {pending = 1}, {unowned = true}, {menu = true},
    {block = 'CharacterState.Space.Air'}, {block = 'CharacterState.Stand.Break'},
}) do
    s = scenario(options)
    assert(s.adapter:register())
    s.fire(false)
    assert(not s.adapter:poll() and s.select_calls == 0 and s.sync_calls == 0)
    s.adapter:dispose()
end

s = scenario()
assert(s.adapter:register())
s.fire(true)
s.fire(false, nil, 'IA_ChangeArmed')
s.fire(false, nil, 'IA_ChangingWeapon')
s.fire(false, 'Ability.Action.Hun.Weapon.Switch.Air')
s.fire(false, nil, nil, -2)
s.fire(false, nil, nil, nil, true)
in_game_thread = false
s.fire(false)
in_game_thread = true
assert(not s.adapter:poll() and s.select_calls == 0 and s.sync_calls == 0)
s.fire(false)
s.slots[2] = 'Other'
assert(not s.adapter:poll() and s.select_calls == 0)
s.slots[2] = 'RKA'
s.fire(false)
s.menu = true
assert(not s.adapter:poll() and s.select_calls == 0)
s.menu = false
s.fire(false)
s.adapter:dispose()
assert(not callback and not s.adapter:poll() and s.select_calls == 0)

s = scenario()
assert(s.adapter:register())
assert(not s.adapter:poll(4.98))
-- The trigger timestamp persists after the one-frame Triggered enum ended.
s.instance.TriggerEvent, s.instance.LastTriggeredWorldTime = 16, 5
assert(not s.adapter:poll(5) and not s.adapter:poll(5) and s.select_calls == 0)
assert(s.adapter:poll(5.066) and s.select_calls == 1 and s.sync_calls == 1)
assert(not s.adapter:poll(5.082))
s.adapter:dispose()

for _, invalidation in ipairs({
    function(x) x.pending = 1 end,
    function(x) x.block = 'Ability.Action.Hun.Weapon.Switch.Normal' end,
    function(x) x.block = 'Ability.Action.Hun.Weapon.Switch.Dash' end,
    function(x) x.menu = true end,
}) do
    s = scenario()
    assert(s.adapter:register())
    assert(not s.adapter:poll(4.98))
    s.instance.TriggerEvent, s.instance.LastTriggeredWorldTime = 1, 5
    assert(not s.adapter:poll(5))
    invalidation(s)
    assert(not s.adapter:poll(5.066) and s.select_calls == 0 and s.sync_calls == 0)
    s.adapter:dispose()
end

-- A physical tap on the real mapping still works when the aggregate
-- action stamp is not updated, including duplicate equivalent bindings.
s = scenario({no_action_instance = true})
s.input.EnhancedActionMappings[2] = s.mapping
assert(s.adapter:register() and not s.adapter:poll(4.98))
s.down = 'ReboundKey'
assert(not s.adapter:poll(5))
s.down = nil
assert(not s.adapter:poll(5.08) and s.adapter:poll(5.15))
assert(s.select_calls == 1 and s.sync_calls == 1)
s.adapter:dispose()

for _, invalidation in ipairs({
    function(x) x.mapping.bShouldBeIgnored = true end,
    function(x) x.mapping.Triggers[1].HoldTimeThreshold = 0 end,
    function(x) x.action.Modifiers[1] = {} end,
    function(x) x.mapping.Key.KeyName = FName('ChangedWhileHeld') end,
    function(x) x.mapping.Triggers[1].HoldTimeThreshold = .1 end,
}) do
    s = scenario()
    assert(s.adapter:register() and not s.adapter:poll(4.98))
    s.down = 'ReboundKey'
    assert(not s.adapter:poll(5))
    invalidation(s)
    s.down = nil
    assert(not s.adapter:poll(5.12) and not s.adapter:poll(5.19) and s.select_calls == 0)
    s.adapter:dispose()
end

-- A long hold belongs to the game's armed action, never this fallback.
s = scenario()
assert(s.adapter:register() and not s.adapter:poll(4.98))
s.down = 'ReboundKey'
assert(not s.adapter:poll(5))
s.down = nil
assert(not s.adapter:poll(5.45) and not s.adapter:poll(5.52) and s.select_calls == 0)
s.adapter:dispose()

-- Capture a native commit that arrived during the grace period. Reconcile
-- the backpack only and emit the entry receipt once, without a second switch.
s = scenario()
assert(s.adapter:register() and not s.adapter:poll(4.98))
s.instance.LastTriggeredWorldTime = 5
assert(not s.adapter:poll(5))
s.fire(true)
s.actor_index = 1
assert(s.adapter:poll(5.07))
assert(s.select_calls == 0 and s.sync_calls == 1)
assert(not s.adapter:poll(5.08))
s.adapter:dispose()

-- An asynchronous original Change Weapon commit must be read back before
-- the backpack or the entry attack changes.
s = scenario({defer = true})
assert(s.adapter:register())
s.fire(false)
assert(not s.adapter:poll(5) and s.select_calls == 1 and s.sync_calls == 0)
assert(not s.adapter:poll(5.016) and s.select_calls == 1 and s.sync_calls == 0)
s.pending, s.actor_index = nil, 1
assert(s.adapter:poll(5.05) and s.sync_calls == 1)
assert(not s.adapter:poll(5.07) and s.select_calls == 1)
s.adapter:dispose()

s = scenario()
assert(s.adapter:register())
assert(not s.adapter:poll(4.98))
s.instance.TriggerEvent, s.instance.LastTriggeredWorldTime = 1, 5
s.fire(false)
assert(s.adapter:poll(5) and s.select_calls == 1 and s.sync_calls == 1)
assert(not s.adapter:poll(5.066))
s.adapter:dispose()

-- Ignore a stale release when first arming this gameplay context.
s = scenario()
assert(s.adapter:register())
s.instance.LastTriggeredWorldTime = 5
assert(not s.adapter:poll(5) and not s.adapter:poll(5.066))
s.menu = true
s.instance.LastTriggeredWorldTime = 5.02
assert(not s.adapter:poll(5.02))
s.menu = false
assert(not s.adapter:poll(5.03) and not s.adapter:poll(5.046) and s.select_calls == 0)
s.adapter:dispose()

-- A missing action instance before the first key press is a valid baseline.
s = scenario({no_action_instance = true})
assert(s.adapter:register() and not s.adapter:poll(4.98))
s.no_action_instance = false
s.instance.LastTriggeredWorldTime = 5
assert(not s.adapter:poll(5) and s.adapter:poll(5.066))
s.adapter:dispose()

s = scenario()
assert(s.adapter:register() and not s.adapter:poll(4.98))
s.instance.LastTriggeredWorldTime = 5
assert(not s.adapter:poll(5) and not s.adapter:poll(5.30) and s.select_calls == 0)
s.adapter:dispose()

-- A failed original switch during another native owner's action is a real
-- rejection, not permission to forcibly commit the mod weapon afterwards.
local ownership_tags = {
    'Ability.Action.Execution', 'Ability.Executed', 'CharacterState.Native.Sequence',
    'Ability.Action.Hun.SimpleExecution', 'Ability.Action.Hun.PerfectDodge',
    'CharacterState.FlowIdle', 'CharacterState.FlowIdle.CantBreak',
    'Ability.Action.Hun.Dash', 'Ability.SpecialMove', 'Ability.Action.Hun.SpecialMove',
    'CharacterState.AbilityState.InSpecialPerform', 'Ability.UpperBody.Hun.ChangeArmed',
    'CharacterState.ChangingArmed', 'CharacterState.Space.Air', 'CharacterState.Stand.Break',
}
for _, blocked_tag in ipairs(ownership_tags) do
    s = scenario({block = blocked_tag})
    assert(s.adapter:register())
    s.fire(false)
    -- Even if the tag clears before poll, that rejected press is discarded.
    s.block = nil
    assert(not s.adapter:poll(5) and s.select_calls == 0 and s.sync_calls == 0, blocked_tag)
    s.fire(false)
    assert(s.adapter:poll(5.08) and s.select_calls == 1 and s.sync_calls == 1)
    s.adapter:dispose()

    s = scenario()
    assert(s.adapter:register() and not s.adapter:poll(4.98))
    s.block = blocked_tag;s.instance.LastTriggeredWorldTime = 5
    assert(not s.adapter:poll(5))
    s.block = nil
    assert(not s.adapter:poll(5.08) and s.select_calls == 0 and s.sync_calls == 0, blocked_tag)
    s.adapter:dispose()

    s = scenario({defer = true})
    assert(s.adapter:register())
    s.fire(false)
    assert(not s.adapter:poll(5) and s.select_calls == 1)
    s.pending = nil;s.actor_index = 1;s.block = blocked_tag
    assert(not s.adapter:poll(5.04) and s.sync_calls == 0, blocked_tag)
    s.block = nil
    assert(not s.adapter:poll(5.08) and s.sync_calls == 0)
    s.adapter:dispose()
end

-- The exact native Dash route is intentionally legal during Dash. A plain
-- tap inference/Normal route has no equivalent authorization.
s = scenario({block = 'Ability.Action.Hun.Dash'})
assert(s.adapter:register())
s.fire(false, 'Ability.Action.Hun.Weapon.Switch.Dash')
receipt = assert(s.adapter:poll(5))
assert(receipt.native_route == 'Ability.Action.Hun.Weapon.Switch.Dash'
    and s.select_calls == 1 and s.sync_calls == 1)
s.adapter:dispose()
for _, blocked_tag in ipairs(ownership_tags) do
    if blocked_tag ~= 'Ability.Action.Hun.Dash' then
        s = scenario({block = blocked_tag, blocks = {['Ability.Action.Hun.Dash'] = true}})
        assert(s.adapter:register())
        s.fire(false, 'Ability.Action.Hun.Weapon.Switch.Dash')
        assert(not s.adapter:poll(5) and s.select_calls == 0 and s.sync_calls == 0, blocked_tag)
        s.adapter:dispose()
    end
end

bad_commit = true
s = scenario()
assert(s.adapter:register())
s.fire(false)
assert(not s.adapter:poll() and s.select_calls == 0 and s.sync_calls == 0 and #s.logs == 1)
s.adapter:dispose()
bad_commit = false

malformed = true
s = scenario()
assert(not s.adapter:register() and not callback and #s.logs == 1)
assert(s.logs[1]:find('Native switch signature changed', 1, true))
''')

print('Weapon switch contracts passed')
(ROOT / 'reports/weapon-switch-compatibility-audit-tests.json').write_text(json.dumps({
    'scope': 'Actual Lua switch adapter with native-shaped mocks; not in-game acceptance',
    'pass': True,
    'native_ownership_tags': 15,
    'new_ownership_scenarios': 45,
    'native_dash_route_scenarios': 15,
    'source_sha256': hashlib.sha256((SCRIPTS / 'WeaponSwitch.lua').read_bytes()).hexdigest(),
    'installed': False,
    'runtime_verified': False,
}, indent=2) + '\n', encoding='utf-8')
