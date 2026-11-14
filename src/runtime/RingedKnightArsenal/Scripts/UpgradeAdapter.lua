-- Query PBZ's saved weapon level / native multiplier. This module never grants,
-- spends currency, invokes UpgradeWeapon, or bypasses the native upgrade UI.
local M={}
local function owned(id)assert(id=='RKA_RingedKnight','Unsupported independent weapon')end
local function integer(value,label)
    assert(type(value)=='number' and value%1==0,label..' is not an integer');return value
end
function M.level(backpack,id)
    owned(id)
    local level=integer(backpack:GetWeaponLevel(FName(id),true),'Native weapon level')
    local maximum=integer(backpack:GetWeaponMaxLevel(FName(id),true),'Native weapon maximum')
    -- The real native getter caps the 59-upgrade row's final level (60) by
    -- MainWeaponInfo.ReincarnationCount: min(60, 5*(6+min(count,6))). Keep the
    -- native current cap; first-cycle weapons can legitimately report 30.
    assert(maximum>=1 and maximum<=60,'Native maximum exceeds the extracted progression')
    assert(level>=1 and level<=maximum,'Independent weapon is missing or level convention changed')
    return level,maximum
end
function M.multiplier(backpack,owner,weapon_config,id)
    owned(id)
    local level,maximum=M.level(backpack,id)
    -- Pinned UE4SS UFunction binding writes scalar OutParm into a supplied table,
    -- keyed by the reflected parameter name; it does not return the float second.
    local out={}
    local found=backpack:GetWeaponAttackMultipliers(owner,weapon_config,out)
    assert(type(found)=='boolean','Native weapon strength query return type changed')
    if not found then
        -- Real CL-302256 native code skips level<=1 before config matching:
        -- 0x6991e68..1e6e jumps to the next equipped weapon. No upgrade entry
        -- exists at level 1, so false means its identity upgrade factor, 1.0.
        -- A later-level miss remains an error: never drop an upgraded weapon
        -- back to base strength or substitute an unverified table fallback.
        assert(level==1,'Native weapon strength query failed for upgraded level '..level)
        return 1.0,{level=level,max_level=maximum,source='native-base-level-one',id=id,
            helper_returned=false,multiplier_scope='weapon_upgrade',runtime_verified=false}
    end
    local strength=out.WeaponStrengthMultiplier
    assert(type(strength)=='number' and strength==strength and strength>0 and strength<100,
        'Invalid native weapon strength multiplier')
    return strength,{level=level,max_level=maximum,source='native',id=id,
        helper_returned=true,multiplier_scope='weapon_upgrade'}
end
function M.expected_multiplier(definitions,level)
    integer(level,'Weapon level')
    local convention=definitions.level_convention
    assert(level>=convention.base_level and level<=convention.max_level,'Level outside extracted progression')
    return level==convention.base_level and convention.base_multiplier or definitions.progression[level-1].AttackMultipliers
end
return M
