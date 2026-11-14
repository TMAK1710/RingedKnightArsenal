-- Direction input adjusts the actor, while the sampled source displacement
-- remains in the action's original basis. Apply only the actual yaw delta.
-- Native land montages already keep ownership until they finish. This brief
-- grace covers state-machine landings before the weapon's idle blends in.
local M={turn_degrees_per_second=720,deadzone=.16,native_landing_grace=.25}

function M.is_plunge(clip)
    return clip and clip:match('^RKSS_Plunge')~=nil or false
end

function M.is_mobile(clip)
    return clip=='RKSS_GuardStart'or clip=='RKSS_GuardLoop'or clip=='RKSS_GuardEnd'or clip=='RKSS_RopeBomb'
end

function M.slot(clip)
    if clip=='RKSS_RopeBomb'then return 'RightArmOverride'end
    if M.is_mobile(clip)then return 'LeftArmOverride'end
    return 'BoatSlot'
end

function M.can_steer(clip)
    return clip=='RKSS_EmberStart' or clip=='RKSS_Ember'
        or clip=='RKSS_EmberFollow1' or clip=='RKSS_EmberFollow2'
        or clip=='RKSS_EmberHeavy'
        or (clip and (clip:match('^RKSS_Light%d$')or clip:match('^RKSS_Heavy[12]Release$'))~=nil)
end

function M.aim_yaw(right,forward,view_yaw)
    if right*right+forward*forward < M.deadzone*M.deadzone then return end
    return view_yaw+math.deg(math.atan(right,forward))
end

function M.approach_yaw(current,target,dt)
    local delta=(target-current+180)%360-180
    local limit=M.turn_degrees_per_second*dt
    return current+math.max(-limit,math.min(limit,delta))
end

function M.rotate_yaw(vector,degrees)
    local angle=math.rad(degrees);local c,s=math.cos(angle),math.sin(angle)
    return {X=c*vector.X-s*vector.Y,Y=s*vector.X+c*vector.Y,Z=vector.Z}
end
return M
