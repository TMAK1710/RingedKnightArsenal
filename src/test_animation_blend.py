"""Exercise ownership and the manual pose clock with UE5.7-shaped Lua mocks."""

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

lua = LuaRuntime()
lua.globals().module_path = (root / 'src/runtime/RingedKnightArsenal/Scripts/AnimationBlend.lua').as_posix()
lua.execute(r'''
local adapter = dofile(module_path)
local native_class = 'AnimBlueprintGeneratedClass /HuaShira/Characters/Hero/Hero_Hun/Animation/PBZ_ABP_Hun_Base.PBZ_ABP_Hun_Base_C'
local next_address = 0
local function object(fields)
    next_address = next_address + 1
    local address = next_address
    fields = fields or {}
    fields.GetAddress = function() return address end
    fields.IsValid = function(self) return not self.invalid end
    fields.GetFullName = fields.GetFullName or function() return 'AnimSequence Test.Animation' end
    if fields.duration then
        fields.RateScale = fields.RateScale or 1
        fields.GetPlayLength = function(self) return self.duration end
    end
    return fields
end

local game_thread = true
function IsInGameThread() return game_thread end
function FName(value) return value end
local created = {}
local factory = object({
    CreateSlotAnimationAsDynamicMontage_WithBlendSettings = function(_, asset, slot, blend_in, blend_out, rate, loops, trigger)
        assert(({BoatSlot=true,LeftArmOverride=true,RightArmOverride=true})[slot] and rate == 1 and loops == 1 and trigger == -1)
        assert(blend_in.BlendMode == 0 and blend_in.Blend.BlendOption == 2)
        assert(blend_out.BlendMode == 0 and blend_out.Blend.BlendTime == .16)
        local track_rate = math.abs(asset.RateScale) <= 1e-8 and 1 or asset.RateScale
        local montage = object({asset = asset, slot = slot, incoming_blend = blend_in.Blend.BlendTime,
            length = asset.duration / math.abs(track_rate), RateScale=1,
            GetFullName=function()return 'AnimMontage Test.Dynamic'end,
            GetPlayLength=function(self)return self.length end})
        montage.SequenceLength=montage.length
        created[#created + 1] = montage
        return montage
    end,
})
function StaticFindObject(path)
    assert(path == '/Script/Engine.Default__AnimMontage')
    return factory
end

local function fixture(postprocess_disabled)
    local instance = object({
        GetClass = function() return {GetFullName = function() return native_class end} end,
        GetCurrentActiveMontage = function(self) return self.active end,
        Montage_Play = function(self, montage, rate, result_kind, start, stop_all)
            assert(rate == 1 and result_kind == 0 and start == 0 and stop_all == false)
            montage.active, montage.playing, montage.position = true, true, start
            self.active = montage
            return self.play_length_override or montage.length
        end,
        Montage_Pause = function(_, montage) montage.playing = false end,
        Montage_IsActive = function(_, montage) return montage.active end,
        Montage_IsPlaying = function(_, montage) return montage.playing end,
        Montage_SetPosition = function(_, montage, position) montage.position = position end,
        Montage_Stop = function(self, duration, montage)
            assert(montage, 'Never call broad montage stop')
            montage.active, montage.fade_out = false, duration
            if self.active == montage then self.active = nil end
        end,
        Blueprint_GetSlotMontageLocalWeight = function(self, slot)
            assert(self.active and slot == self.active.slot)
            return .75
        end,
    })
    local mesh = object({
        instance = instance,
        GetAnimInstance = function(self) return self.instance end,
        GetDisablePostProcessBlueprint = function(self) return self.postprocess_disabled end,
        SetDisablePostProcessBlueprint = function(self, value) self.postprocess_disabled = value end,
        postprocess_disabled = postprocess_disabled,
    })
    return adapter.new(mesh), mesh, instance
end

local idle = object({bEnableRootMotion = false, duration = 2})
local attack = object({bEnableRootMotion = false, duration = 2.4})
local guard = object({bEnableRootMotion = false, duration = 1.33})
local blend, mesh, instance = fixture(false)
assert(blend:play(idle, 2, true, .16))
local idle_montage = blend.montage
assert(not idle_montage.playing and mesh.postprocess_disabled and blend:slot_weight() == .75)
assert(blend:advance_idle(2.25) and idle_montage.position == .25)

assert(blend:play(attack, 2.4, false))
local attack_montage = blend.montage
assert(idle_montage.fade_out == .09 and attack_montage.incoming_blend == .09)
assert(blend:seek(.46666667) and attack_montage.position == .46666667)
assert(blend:seek(3) and attack_montage.position == 2.4)

assert(blend:play(guard, 1.33, true))
assert(attack_montage.fade_out == .09 and attack_montage.position == 2.4)
assert(blend:seek(1.58) and math.abs(blend.montage.position - .25) < .00001)

local guard_montage = blend.montage
blend:stop(adapter.move_blend_out)
assert(guard_montage.fade_out == .16 and mesh.postprocess_disabled)
blend:update(.08)
assert(mesh.postprocess_disabled)
blend:update(.081)
assert(not mesh.postprocess_disabled and blend.montage == nil and blend.instance == nil)

-- Left arm guard and right arm throw leave native postprocess on. A whole-body
-- predecessor keeps its settings only until its own pose stops blending out.
assert(blend:play(guard, 1.33, true, nil, 'LeftArmOverride'))
assert(blend.montage.slot == 'LeftArmOverride' and blend:slot_weight() == .75)
assert(not mesh.postprocess_disabled)
assert(blend:play(attack, 2.4, false) and mesh.postprocess_disabled)
assert(blend:play(guard, 1.33, false, nil, 'RightArmOverride'))
assert(blend.montage.slot == 'RightArmOverride' and mesh.postprocess_disabled)
blend:update(.06)
assert(mesh.postprocess_disabled)
blend:update(.04)
assert(not mesh.postprocess_disabled)
blend:stop(0)

local native_montage = object({active = true})
instance.active = native_montage
local count = #created
assert(blend:native_active() and not blend:play(attack, 2.4, false))
assert(#created == count and native_montage.active and not mesh.postprocess_disabled)

instance.active = nil
assert(blend:play(attack, 2.4, false))
local own_montage = blend.montage
instance.active = native_montage
assert(blend:native_active() and not blend:seek(.5))
blend:stop(0)
assert(own_montage.fade_out == 0 and native_montage.active and not mesh.postprocess_disabled)

local disabled, disabled_mesh = fixture(true)
assert(disabled:play(attack, 2.4, false))
disabled:stop(0)
assert(disabled_mesh.postprocess_disabled)

local stale, stale_mesh = fixture(false)
assert(stale:play(attack, 2.4, false))
local stale_montage = stale.montage
local _, _, replacement = fixture(false)
stale_mesh.instance = replacement
assert(not stale:seek(.5))
stale:stop(0)
assert(stale_montage.fade_out == nil and not stale_mesh.postprocess_disabled)

local failed, failed_mesh = fixture(false)
local before = #created
assert(not pcall(failed.play, failed, object({bEnableRootMotion = true}), 2, false))
assert(#created == before and not failed_mesh.postprocess_disabled)
assert(not pcall(failed.play, failed, attack, 3, false))
assert(#created == before and not failed_mesh.postprocess_disabled)

-- A segment includes the source RateScale, while MontageLength ignores the
-- instance play rate. Pose-clock seconds must be converted back into segment time.
local rated, rated_mesh, rated_instance = fixture(false)
local fast = object({bEnableRootMotion=false, duration=2.4, RateScale=2})
assert(rated:play(fast, 2.4, true) and rated.montage.length == 1.2)
assert(rated:seek(.6) and math.abs(rated.montage.position-.3)<1e-6)
assert(rated:seek(2.5) and math.abs(rated.montage.position-.05)<1e-6)
rated:stop(0)
local slow = object({bEnableRootMotion=false, duration=2.4, RateScale=.5})
assert(rated:play(slow, 2.4, false) and rated.montage.length == 4.8)
assert(rated:seek(1.2) and rated.montage.position == 2.4)
rated:stop(0)
local zero = object({bEnableRootMotion=false, duration=2.4, RateScale=0})
assert(rated:play(zero, 2.4, false) and rated.montage.length == 2.4)
assert(rated:seek(.6) and rated.montage.position == .6)
rated:stop(0)
rated_instance.play_length_override = 3
local accepted, diagnostic = pcall(rated.play, rated, attack, 2.4, false)
assert(not accepted and diagnostic:find('asset=AnimSequence Test.Animation',1,true))
assert(diagnostic:find('profile=2.4',1,true) and diagnostic:find('source=2.4',1,true))
assert(diagnostic:find('RateScale=1',1,true) and diagnostic:find('expected_montage=2.4',1,true))
assert(diagnostic:find('returned=3',1,true) and diagnostic:find('slot=BoatSlot',1,true))
assert(diagnostic:find('requested=Test.Animation',1,true) and diagnostic:find('montage=AnimMontage Test.Dynamic',1,true))
assert(diagnostic:find('montage_GetPlayLength=2.4',1,true) and diagnostic:find('montage_RateScale=1',1,true))
assert(created[#created].fade_out == 0 and not rated_mesh.postprocess_disabled)
rated_instance.play_length_override=nil
local created_before=#created
for _,rate in ipairs({-1,.00001,101,math.huge,0/0})do
 local invalid=object({bEnableRootMotion=false,duration=2.4,RateScale=rate})
 assert(not pcall(rated.play,rated,invalid,2.4,false))
end
assert(#created==created_before and not rated_mesh.postprocess_disabled)
assert(not pcall(rated.play,rated,attack,2.4,false,nil,nil,'Test.WrongRequested'))
assert(#created==created_before)
-- Source/profile rounding may differ inside tolerance; never seek beyond the
-- real segment endpoint. Non-finite or backward clock input is rejected.
local rounded=object({bEnableRootMotion=false,duration=2.39,RateScale=2})
assert(rated:play(rounded,2.4,false)and rated:seek(3))
assert(math.abs(rated.montage.position-1.195)<1e-6)
for _,time in ipairs({-.1,math.huge,0/0})do assert(not pcall(rated.seek,rated,time))end
rated:stop(0)

game_thread = false
assert(not pcall(failed.play, failed, idle, 2, true))
assert(not pcall(failed.stop, failed, 0))
''')
print('Animation blend checks passed: crossfade ownership, manual clocks, movement, reaction and failure cleanup')
