-- Recover a short-press switch into an already-equipped mod weapon after
-- native handling. The caller consumes a committed receipt as one entry attack.
local M = {}
M.__index = M

local INPUT = '/Script/SGameInputSystem.AbilityInputComponent:TryActivateExternalActionAbilityInterruptLowerByTag'
local ACTION_PATH = '/SGameCombatSystem/Weapon/Input/IA_ChangeWeapon.IA_ChangeWeapon'
local ACTION = 'InputAction ' .. ACTION_PATH
local WEAPONS = '/Script/SGameCombatSystem.CharacterWeaponsComponent:'
local COMBAT_UTILS = '/PBZCombatAsset/Prototypes/BPL_PBZCombatUtils.'
local COMMIT = COMBAT_UTILS .. 'BPL_PBZCombatUtils_C:Change Weapon'
local COMMIT_CDO = COMBAT_UTILS .. 'Default__BPL_PBZCombatUtils_C'
local COMMIT_FIELDS = table.concat({
    'ObjectProperty Avatar',
    'StructProperty Slot Tag',
    'IntProperty New Index',
    'BoolProperty Armed',
    'ObjectProperty __WorldContext',
    'ObjectProperty Character Weapons Component',
    'ObjectProperty Temp_object_Variable',
    'StructProperty Temp_struct_Variable',
    'StructProperty Temp_struct_Variable_1',
    'InterfaceProperty K2Node_DynamicCast_AsCharacter_Weapons_Holder',
    'BoolProperty K2Node_DynamicCast_bSuccess',
    'ObjectProperty CallFunc_GetCharacterWeaponsComponent_ReturnValue',
    'FloatProperty CallFunc_GetCharacterAttributeValue_ReturnValue',
    'BoolProperty CallFunc_SetCurrentWeapon_ReturnValue',
}, ',')
local GROUNDED_SWITCH = {
    ['Ability.Action.Hun.Weapon.Switch.Normal'] = true,
    ['Ability.Action.Hun.Weapon.Switch.Dash'] = true,
}
local NATIVE_SWITCH_TAGS = {
    'Ability.Action.Hun.Weapon.Switch.Normal',
    'Ability.Action.Hun.Weapon.Switch.Dash',
    'Ability.Action.Hun.Weapon.Switch.Air',
}
-- These are ownership/rejection states, not a failed custom-weapon lookup.
-- Never turn a rejected native request during one of them into a forced switch.
local NATIVE_OWNERSHIP_TAGS = {
    'Ability.Action.Execution', 'Ability.Executed', 'CharacterState.Native.Sequence',
    'Ability.Action.Hun.SimpleExecution', 'Ability.Action.Hun.PerfectDodge',
    'CharacterState.FlowIdle', 'CharacterState.FlowIdle.CantBreak',
    'Ability.Action.Hun.Dash', 'Ability.SpecialMove', 'Ability.Action.Hun.SpecialMove',
    'CharacterState.AbilityState.InSpecialPerform', 'Ability.UpperBody.Hun.ChangeArmed',
    'CharacterState.ChangingArmed', 'CharacterState.Space.Air', 'CharacterState.Stand.Break',
}
local REQUEST_TIMEOUT = .25
local NATIVE_GRACE = .05

local function valid(object)
    return object and object:IsValid()
end

local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end

local function unwrap(value)
    if type(value) == 'userdata' then
        local kind = value:type()
        if kind == 'LocalUnrealParam' or kind == 'RemoteUnrealParam' then return value:get() end
    end
    return value
end

local function name(value)
    value = unwrap(value)
    return type(value) == 'string' and value or value:ToString()
end

local function tag(value)
    return {TagName = FName(value)}
end

local function same_slots(snapshot, request)
    return #snapshot.slots == 2 and snapshot.owner == request.owner
        and snapshot.slots[request.source_slot + 1] == request.source
        and snapshot.slots[request.slot + 1] == request.id
end

local function tap_mappings(input, action)
    local keys, ambiguous = {}, {}
    if #action.Triggers ~= 0 or #action.Modifiers ~= 0 then return keys end
    local mappings = input.EnhancedActionMappings
    for index = 1, #mappings do
        local mapping = unwrap(mappings[index])
        if same(unwrap(mapping.Action), action) and not mapping.bShouldBeIgnored then
            local key = name(mapping.Key.KeyName)
            local trigger = #mapping.Triggers == 1 and unwrap(mapping.Triggers[1])
            local threshold
            if #mapping.Modifiers == 0 and valid(trigger or nil)
                and name(trigger:GetClass():GetFName()) == 'InputTrigger_HoldAndReleaseEarly' then
                threshold = trigger.HoldTimeThreshold
            end
            if type(threshold) ~= 'number' or threshold <= 0 or threshold > 2
                or (keys[key] and keys[key] ~= threshold) then
                ambiguous[key] = true
            else
                keys[key] = threshold
            end
        end
    end
    for key in pairs(ambiguous) do keys[key] = nil end
    keys[''], keys.None = nil, nil
    return keys
end

local function action_stamp(input, action)
    local instances = input.ActionInstanceData
    if not instances:Contains(action) then return 0 end
    local instance = unwrap(instances:Find(action))
    if instance and same(unwrap(instance.SourceAction), action) then
        return instance.LastTriggeredWorldTime
    end
end

function M:short_tap(pc, mappings, now)
    local released = false
    local previous, current = self.down or {}, {}
    for key, threshold in pairs(mappings) do
        local down = pc:IsInputKeyDown({KeyName = FName(key)})
        local held = previous[key]
        if held and held.threshold ~= threshold then held = nil end
        if down then
            -- Use the last up sample as the earliest possible press time.
            current[key] = held or {threshold = threshold, start = self.up and self.up[key]}
        elseif held and held.start and now - held.start < threshold then
            released = true
        end
    end
    self.down, self.up = current, {}
    for key in pairs(mappings) do if not current[key] then self.up[key] = now end end
    return released
end

local function component(class, pawn)
    local found
    for _, candidate in ipairs(FindAllOf(class) or {}) do
        if valid(candidate) and same(candidate:GetOwner(), pawn) then
            if found then return nil end
            found = candidate
        end
    end
    return found
end

local function schema(path, expected)
    local fn = StaticFindObject(path)
    assert(valid(fn) and fn:GetFullName() == 'Function ' .. path, 'Native switch function missing: ' .. path)
    local fields = {}
    fn:ForEachProperty(function(property)
        local kind, key = property:GetFullName():match('^(%S+) .+:([^:]+)$')
        fields[#fields + 1] = tostring(kind) .. ' ' .. tostring(key)
    end)
    assert(table.concat(fields, ',') == expected, 'Native switch signature changed: ' .. path)
end

function M.new(equipment, registry, resolve, log)
    return setmetatable({equipment = equipment, registry = registry, resolve = resolve, log = log}, M)
end

function M:report(message)
    if self.last_error ~= message then
        self.last_error = message
        if self.log then self.log('Weapon switch: ' .. message) end
    end
end

function M:native_owner_busy(pawn, request)
    local abilities = self.owner_abilities
    if not valid(abilities) or not same(abilities:GetOwner(), pawn) then
        abilities = component('PBZAbilitySystemComponent', pawn)
        self.owner_abilities = abilities
    end
    if not abilities then return true end
    for _, value in ipairs(NATIVE_OWNERSHIP_TAGS) do
        -- AIM_Hun_ChangeWeapon explicitly permits Switch.Dash while Dash is
        -- active. Only that observed native route grants this exception;
        -- remapped tap inference and ordinary Switch.Normal never do.
        local native_dash = value == 'Ability.Action.Hun.Dash' and request
            and request.native_route == 'Ability.Action.Hun.Weapon.Switch.Dash'
        if not native_dash and abilities:HasMatchingGameplayTag(tag(value)) then return true end
    end
    return false
end

function M:slot_pair(pawn, owner)
    local source_id = name(owner.CurrentMainWeaponID)
    if self.registry:get(source_id) then return end
    local before = self.equipment:snapshot(owner)
    if #before.slots ~= 2 or (before.current ~= 0 and before.current ~= 1) then return end
    local source = before.slots[before.current + 1]
    if source == '' or source == 'None' or source_id ~= source then return end
    local slot = 1 - before.current
    local target = before.slots[slot + 1]
    if not self.registry:get(target) or not owner:HasWeapon(FName(target), true) then return end
    return {pawn = pawn:GetAddress(), owner = before.owner, source = source, source_slot = before.current,
        id = target, slot = slot}
end

function M:destination(pawn, request)
    local weapons = component('CharacterWeaponsComponent', pawn)
    local abilities = component('PBZAbilitySystemComponent', pawn)
    if not weapons or not abilities then return nil, 'live weapon or ability component unavailable' end
    if abilities:HasMatchingGameplayTag(tag('CharacterState.Space.Air'))
        or abilities:HasMatchingGameplayTag(tag('CharacterState.Stand.Break')) then return nil, 'airborne or staggered' end
    for _, value in ipairs(NATIVE_SWITCH_TAGS) do
        if abilities:HasMatchingGameplayTag(tag(value)) then return nil, 'native switch still active' end
    end
    local main = tag('Weapon.Slot.Main')
    if weapons:GetCurrentWeaponIndex(main, false) ~= request.source_slot
        or weapons:GetCurrentWeaponIndex(main, true) ~= request.source_slot then
        return nil, 'character weapon index differs from source or is pending'
    end
    if weapons:GetCurrentChangeWeaponCooldown(main) > 0 then return nil, 'native switch cooldown active' end
    return weapons
end

function M:observe(context, result, ability, action, priority)
    if not self.hook or self.applying or not IsInGameThread() then return end
    result = unwrap(result)
    if type(result) ~= 'boolean' or unwrap(priority) ~= -4 then return end
    action = unwrap(action)
    if not valid(action) or action:GetFullName() ~= ACTION then return end
    ability = unwrap(ability)
    if not ability or not GROUNDED_SWITCH[name(ability.TagName)] then return end
    context = unwrap(context)
    local pawn, owner = self.resolve()
    if not valid(pawn) or not valid(owner) or not valid(context) or not same(context:GetOwner(), pawn) then return end
    if result then
        self.request, self.native_accepted = nil, true
    elseif not self.request and not self.native_accepted then
        local request = self:slot_pair(pawn, owner)
        if request then
            request.native_route = name(ability.TagName)
            if not self:native_owner_busy(pawn, request) then self.request = request end
        end
    end
end

function M:observe_mapped_input(now, suppressed)
    local pawn, owner, pc = self.resolve()
    local pending = self.mapped_request
    self.mapped_request = nil
    if not valid(pawn) or not valid(owner) or not valid(pc) then
        self.last_input_address, self.last_pair, self.down, self.up = nil, nil, nil, nil
        return
    end
    local input = pc.PlayerInput
    if not valid(input) then return end
    local address = input:GetAddress()
    local pawn_address, owner_address = pawn:GetAddress(), owner:GetAddress()
    local pair = self:slot_pair(pawn, owner)
    local previous_pair = self.last_pair
    self.last_pair = pair
    if not pair and not previous_pair and not pending then
        self.last_input_address, self.down, self.up = nil, nil, nil
        return
    end
    local action = self.action
    if not valid(action) then
        action = StaticFindObject(ACTION_PATH)
        if not valid(action) or action:GetFullName() ~= ACTION then return end
        self.action = action
    end
    local ok, stamp = pcall(action_stamp, input, action)
    if not ok then
        self:report('Enhanced Input trigger stamp unavailable: ' .. tostring(stamp))
        stamp = nil
    end
    if type(stamp) ~= 'number' or not (stamp >= 0 and stamp <= now) then stamp = nil end
    if self.last_input_address ~= address or self.last_pawn ~= pawn_address or self.last_owner ~= owner_address then
        self.last_input_address, self.last_mapped_time = address, stamp or 0
        self.last_pawn, self.last_owner = pawn_address, owner_address
        self.down, self.up = nil, nil
        if pair then self:short_tap(pc, tap_mappings(input, action), now) end
        return
    end
    local triggered = stamp and stamp > self.last_mapped_time and now - stamp <= REQUEST_TIMEOUT
    if stamp then self.last_mapped_time = math.max(self.last_mapped_time, stamp) end
    local tapped
    if pair then tapped = self:short_tap(pc, tap_mappings(input, action), now)
    else self.down, self.up = nil, nil end
    if suppressed then return end
    -- A real aggregate trigger is authoritative. When it was not dispatched,
    -- track the same active remappable short-press binding as a fallback.
    local request = pair or (triggered and previous_pair)
    if (pending or (request and (triggered or tapped))) and self:native_owner_busy(pawn) then
        self.down, self.up = nil, nil
        return
    end
    if not pending and request and (triggered or tapped) then
        pending = {request = request, observed = now}
    end
    if not pending or now - pending.observed > REQUEST_TIMEOUT then return end
    if now - pending.observed < NATIVE_GRACE then
        self.mapped_request = pending
    else
        return pending.request
    end
end

function M:register()
    if self.hook then return true end
    local ok, why = pcall(function()
        schema(WEAPONS .. 'GetCurrentWeaponIndex', 'StructProperty SlotTag,BoolProperty WithPending,IntProperty ReturnValue')
        schema(WEAPONS .. 'GetCurrentChangeWeaponCooldown', 'StructProperty SlotTag,FloatProperty ReturnValue')
        schema(WEAPONS .. 'SetCurrentWeapon', 'StructProperty SlotTag,IntProperty Index,BoolProperty ReturnValue')
        schema('/Script/ProjectPBZ.PBZBackPackSubsystem:SetCurrentWeaponByIndex', 'IntProperty WeaponIndex,BoolProperty IsNormalWeapon')
        self.ready = true
        schema(INPUT, 'StructProperty AbilityTag,ObjectProperty InputAction,IntProperty ActionPriority,BoolProperty ReturnValue')
        local pre, post = RegisterHook(INPUT, function() end, function(...)
            local success, error_message = pcall(self.observe, self, ...)
            if not success then self:report(tostring(error_message)) end
        end)
        assert(type(pre) == 'number' and type(post) == 'number', 'Native switch hook handles missing')
        self.hook = {pre = pre, post = post}
    end)
    if not ok then self:report(tostring(why)) end
    return ok
end

function M:commit(pawn, main, slot)
    local cdo = self.commit_cdo
    if not valid(cdo) then
        cdo = StaticFindObject(COMMIT_CDO)
        assert(valid(cdo) and cdo:GetFullName() == 'BPL_PBZCombatUtils_C ' .. COMMIT_CDO,
            'Original Change Weapon utility is unavailable')
        schema(COMMIT, COMMIT_FIELDS)
        self.commit_cdo = cdo
    end
    -- Native utility selects the slot and runs its armed state, cooldown,
    -- and Shachi lifecycle only when CharacterWeaponsComponent accepts it.
    cdo['Change Weapon'](cdo, pawn, main, slot, true, pawn)
end

local function committed(weapons, main, request)
    return weapons:GetCurrentWeaponIndex(main, false) == request.slot
        and weapons:GetCurrentWeaponIndex(main, true) == request.slot
end

function M:confirm(pawn, owner, request, allow_sync)
    if self:native_owner_busy(pawn, request) then return end
    local after = self.equipment:snapshot(owner)
    if pawn:GetAddress() ~= request.pawn or not same_slots(after, request)
        or not owner:HasWeapon(FName(request.id), true) then return end
    local weapons = component('CharacterWeaponsComponent', pawn)
    local main = tag('Weapon.Slot.Main')
    if not weapons or not committed(weapons, main, request) then return end
    -- Only sync the backpack after the character actually committed the slot.
    if allow_sync and after.current == request.source_slot and name(owner.CurrentMainWeaponID) == request.source then
        owner:SetCurrentWeaponByIndex(request.slot, true)
        after = self.equipment:snapshot(owner)
    end
    if same_slots(after, request) and after.current == request.slot and name(owner.CurrentMainWeaponID) == request.id
        and committed(weapons, main, request) then return request end
end

function M:poll(now)
    local request = self.request
    self.request, self.native_accepted = nil, nil
    if not self.ready or not IsInGameThread() then return end
    if type(now) == 'number' then
        -- The engine samples real time into a float before stamping the action.
        now = string.unpack('f', string.pack('f', now))
        local ok, mapped = pcall(self.observe_mapped_input, self, now, request ~= nil or self.waiting ~= nil)
        if ok then request = request or mapped
        else self:report('Enhanced Input observation unavailable: ' .. tostring(mapped)) end
    end
    if not request and not self.waiting then return end
    self.applying = true
    local ok, receipt = pcall(function()
        local pawn, owner = self.resolve()
        if not valid(pawn) or not valid(owner) then self.waiting = nil;return end
        if self:native_owner_busy(pawn, self.waiting and self.waiting.request or request) then
            self.waiting, self.mapped_request, self.down, self.up = nil, nil, nil, nil
            return
        end
        if self.waiting then
            local waiting = self.waiting
            local snapshot = self.equipment:snapshot(owner)
            if not now or now > waiting.deadline or pawn:GetAddress() ~= waiting.request.pawn
                or not same_slots(snapshot, waiting.request) then
                self.waiting = nil
                return
            end
            local confirmed = self:confirm(pawn, owner, waiting.request, true)
            if confirmed then self.waiting = nil;return confirmed end
            return
        end

        local confirmed = self:confirm(pawn, owner, request, true)
        if confirmed then return confirmed end
        local current = self:slot_pair(pawn, owner)
        if not current then return end
        for _, key in ipairs({'pawn','owner','source','source_slot','id','slot'}) do
            if current[key] ~= request[key] then return end
        end
        local weapons, blocked = self:destination(pawn, request)
        if not weapons then
            local active = component('CharacterWeaponsComponent', pawn)
            if now and active and active:GetCurrentWeaponIndex(tag('Weapon.Slot.Main'), true) == request.slot then
                self.waiting = {request = request, deadline = now + REQUEST_TIMEOUT}
            else
                self:report(blocked)
            end
            return
        end

        local main = tag('Weapon.Slot.Main')
        self:commit(pawn, main, request.slot)
        confirmed = self:confirm(pawn, owner, request, true)
        if confirmed then return confirmed end
        if now and weapons:GetCurrentWeaponIndex(main, true) == request.slot
            and not committed(weapons, main, request) then
            self.waiting = {request = request, deadline = now + REQUEST_TIMEOUT}
        else
            self:report('native change did not confirm the requested slot and item')
        end
    end)
    self.applying = false
    if not ok then self:report(tostring(receipt));return end
    if receipt then
        self.last_error = nil
        if self.log then self.log('Weapon switch: confirmed slot ' .. receipt.slot .. ' (' .. receipt.id .. ')') end
    end
    return receipt
end

function M:dispose()
    local hook = self.hook
    self.hook, self.request, self.mapped_request, self.native_accepted = nil, nil, nil, nil
    self.last_input_address, self.last_mapped_time, self.commit_cdo, self.action = nil, nil, nil, nil
    self.last_pawn, self.last_owner, self.last_pair = nil, nil, nil
    self.owner_abilities = nil
    self.ready, self.waiting, self.down, self.up = nil, nil, nil, nil
    if hook then
        local ok, why = pcall(UnregisterHook, INPUT, hook.pre, hook.post)
        if not ok then self:report(tostring(why)) end
    end
end

return M
