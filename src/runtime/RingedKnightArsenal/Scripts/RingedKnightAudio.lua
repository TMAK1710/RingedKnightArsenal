-- DS3 one-shots from the local FMOD events and PBZ fallback cues.
local root = '/Game/Wwise/Events/'
local combat = 'SFX/Combat/'
local sword = combat .. 'Whoosh/Hero_Whoosh/Sword/'
local monster = combat .. 'Special/Monster_Special/'
local impact = combat .. 'Special/Hero_Special/Hun/Common/ShouJi/'

local function event(folder, name)
    return root .. folder .. name .. '.' .. name
end

local function wave(name)
    return '/HuaShira/Mods/RingedKnight/Audio/' .. name .. '.' .. name
end

return {
    waves = {
        swing_light = wave('SW_DS3_Swing_Light1'),
        swing_light23 = wave('SW_DS3_Swing_Light23'),
        swing_heavy = wave('SW_DS3_Swing_Heavy'),
        swing_ember = wave('SW_DS3_Swing_Ember'),
        swing_ember_follow = wave('SW_DS3_Swing_EmberFollow'),
        plunge_movement = wave('SW_DS3_Plunge_Movement'),
        plunge_start = wave('SW_DS3_Plunge_Start'),
        plunge_land = wave('SW_DS3_Plunge_Land'),
        swing_ember_heavy = wave('SW_DS3_Ember_Heavy'),
        ember_ignite = wave('SW_DS3_Ember_Ignite'),
        cancel_ignite = wave('SW_DS3_Cancel_Ignite'),
        hit_light = wave('SW_DS3_Hit_Light'),
        hit_heavy = wave('SW_DS3_Hit_Heavy'),
        hit_thrust = wave('SW_DS3_Hit_Thrust'),
        guard_raise = wave('SW_DS3_Guard_Raise'),
        guard_block = wave('SW_DS3_Guard_Block'),
        fire = wave('SW_DS3_Fire'),
        throw = wave('SW_DS3_Throw'),
        explosion = wave('SW_DS3_Explosion'),
    },
    -- Source events from the exact DS3 TAE clips. Hit and block sounds remain
    -- tied to actual contact and the projectile sound to the ground fuse.
    cooked_clips = {
        RKSS_Light1 = {role = 'swing_light', time = .4},
        RKSS_Light2 = {role = 'swing_light23', time = .33333334},
        RKSS_Light3 = {role = 'swing_light23', time = .3},
        RKSS_Heavy1Release = {role = 'swing_heavy', time = .23333333},
        -- Match the current source-clock windup boundary, including held input.
        RKSS_Heavy2Release = {role = 'swing_heavy', time = .24},
        RKSS_EmberStart = {role = 'ember_ignite', time = .76666665},
        RKSS_Ember = {cues = {
            {role = 'swing_ember', time = .53333336}, {role = 'fire', time = .56666666},
            {role = 'swing_ember', time = .96666664}, {role = 'fire', time = 1.0333333},
        }},
        RKSS_EmberFollow1 = {cues = {
            {role = 'fire', time = .26666668}, {role = 'swing_ember_follow', time = .36666667},
            {role = 'fire', time = .6666667}, {role = 'swing_ember_follow', time = .8666667},
        }},
        RKSS_EmberFollow2 = {cues = {
            {role = 'fire', time = .7}, {role = 'swing_ember_follow', time = .76666665},
        }},
        RKSS_EmberHeavy = {cues = {
            {role = 'fire', time = .93333334}, {role = 'swing_ember_heavy', time = .96666664},
        }},
        -- Exact a023_030800/030810 sword cues. The airborne loop has no cue.
        RKSS_PlungeStart = {cues = {
            {role = 'plunge_movement', time = .06666667}, {role = 'plunge_start', time = .1},
        }},
        RKSS_PlungeLoop = {cues = {}},
        RKSS_PlungeLand = {cues = {
            {role = 'swing_ember', time = 0}, {role = 'plunge_land', time = .06666667},
        }},
        RKSS_GuardStart = {role = 'guard_raise', time = 0},
    },
    fallback_roles = {swing_light23 = 'swing_light', swing_ember = 'swing_heavy', swing_ember_follow = 'swing_heavy', swing_ember_heavy = 'swing_heavy', ember_ignite = 'fire', hit_thrust = 'hit_heavy'},
    events = {
        swing_light = event(sword, 'SFX_Combat_WHOOSH_Sword_Wave_One_S_04'),
        swing_heavy = event(sword, 'SFX_Combat_WHOOSH_Sword_Wave_Heavy_L_03'),
        hit_light = event(impact, 'SFX_Combat_Hit_SlashTangBlade_Meat_Light'),
        hit_heavy = event(impact, 'SFX_Combat_Hit_SlashTangBlade_Meat_Heavy'),
        guard_raise = event(monster .. 'Bandit/', 'SFX_Combat_Special_Bandi_Rotate_Shield'),
        guard_block = event('SFX_Impact/ShouJi/MHP/', 'SFX_Combat_Hit_SlashDefault_ShieldIron_Middle'),
        fire = event(monster .. 'QiShuHuo/', 'SFX_Combat_Special_QiShuHuo_Fire_Burst'),
        throw = event(monster .. 'BaoTu/', 'SFX_Combat_Special_BaoTu_Grenade_Throw'),
        explosion = event(monster .. 'BaoTu/', 'SFX_Combat_Special_BaoTu_Grenade_Explosion'),
    },
    clips = {
        RKSS_Light1 = {role = 'swing_light', lead = .07},
        RKSS_Light2 = {role = 'swing_light', lead = .07},
        RKSS_Light3 = {role = 'swing_light', lead = .07},
        RKSS_Heavy1Charge = {role = 'swing_heavy', lead = .07, requires_charge = true},
        RKSS_Heavy1Release = {role = 'swing_heavy', lead = .07},
        RKSS_Heavy2Charge = {role = 'swing_heavy', lead = .07, requires_charge = true},
        RKSS_Heavy2Release = {role = 'swing_heavy', lead = .07},
        RKSS_EmberStart = {role = 'fire', time = .76666665},
        RKSS_Ember = {role = 'swing_heavy', lead = .07},
        RKSS_EmberFollow1 = {role = 'swing_heavy', lead = .07},
        RKSS_EmberFollow2 = {role = 'swing_heavy', lead = .07},
        RKSS_EmberHeavy = {role = 'swing_heavy', lead = .07},
        RKSS_PlungeStart = {cues = {}},
        RKSS_PlungeLoop = {cues = {}},
        RKSS_PlungeLand = {role = 'swing_heavy', time = 0},
        RKSS_GuardStart = {role = 'guard_raise', time = .08},
    },
}
