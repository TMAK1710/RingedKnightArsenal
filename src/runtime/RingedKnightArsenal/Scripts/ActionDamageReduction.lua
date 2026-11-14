-- Private copy of vanilla physical/elemental reduction. Never edit its CDO.
local M={}
local OUTER='/HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight'
local SOURCE='/PBZCombatAsset/ActorData/Players/Hun/ShaqiWeapon/HuoLiuXing/UpgradeData/GE_ShachiWeapon_HuoLiuXing_Defence'
local CLASS=SOURCE..'.GE_ShachiWeapon_HuoLiuXing_Defence_C'
local DEFAULT=SOURCE..'.Default__GE_ShachiWeapon_HuoLiuXing_Defence_C'
local NAME='RKA_ActionDamageReduction'
M.path=OUTER..'.'..NAME
local function valid(o)return o and o:IsValid()end
local function check_modifiers(effect,value)
    assert(#effect.Modifiers==2,'Damage reduction modifier schema changed')
    local seen={}
    for i=1,2 do
        local mod=effect.Modifiers[i]
        local name=mod.Attribute.AttributeName
        if type(name)~='string'then name=name:ToString()end
        assert(name=='TakenReductionMultiplier_Physical'or name=='TakenReductionMultiplier_Elemental','Unexpected reduction attribute')
        assert(not seen[name]);seen[name]=true
        assert(math.abs(mod.ModifierMagnitude.ScalableFloatMagnitude.Value-value)<1e-5,'Damage reduction magnitude mismatch')
    end
end
function M.prepare(outer)
    assert(IsInGameThread() and valid(outer) and outer:GetFullName()=='Package '..OUTER,'Reduction requires owned package')
    local class,original=StaticFindObject(CLASS),StaticFindObject(DEFAULT)
    assert(valid(class) and valid(original),'Native reduction prototype not prepared')
    check_modifiers(original,.75)
    local effect=StaticFindObject(M.path)
    if not valid(effect)then
        effect=StaticConstructObject(class,outer,FName(NAME),0xC1,0x40000000,false,false)
        assert(valid(effect),'Could not construct owned reduction effect')
        check_modifiers(effect,.75)
        effect.DurationPolicy=2 -- HasDuration; independently expires if renewal stops.
        effect.DurationMagnitude.MagnitudeCalculationType=0
        effect.DurationMagnitude.ScalableFloatMagnitude.Value=.25
        for i=1,2 do effect.Modifiers[i].ModifierMagnitude.ScalableFloatMagnitude.Value=.2 end
    end
    assert(effect:GetOuter():GetAddress()==outer:GetAddress(),'Reduction effect owner mismatch')
    assert(effect.DurationPolicy==2 and math.abs(effect.DurationMagnitude.ScalableFloatMagnitude.Value-.25)<1e-5,'Reduction must be finite')
    check_modifiers(effect,.2);check_modifiers(original,.75)
    return effect
end
return M
