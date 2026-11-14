-- Launch trajectory and ground-only fuse. No damage, VFX or engine API calls.
local M={radius=10,ground_normal_z=.65,ttl=5,max_resweeps=4,restitution=.28}
local function add(a,b,k)return {X=a.X+b.X*k,Y=a.Y+b.Y*k,Z=a.Z+b.Z*k}end

function M.launch_velocity(origin,feet,forward,inherited,profile)
    local down=profile.initial_down_cm_s
    local gravity=profile.gravity_cm
    local height=math.max(0,origin.Z-feet.Z-M.radius)
    local seconds=(math.sqrt(down*down+2*gravity*height)-down)/gravity
    -- Keep the correction bounded if the release pose is unusually low or high.
    seconds=math.max(.12,math.min(.38,seconds))
    local length=math.sqrt(forward.X*forward.X+forward.Y*forward.Y)
    local back=(profile.landing_back_cm or 50)/math.max(length,1e-6)
    local target_x=feet.X-forward.X*back
    local target_y=feet.Y-forward.Y*back
    return {X=inherited.X+(target_x-origin.X)/seconds,
        Y=inherited.Y+(target_y-origin.Y)/seconds,Z=-down}
end

function M.advance(projectile,dt,gravity,trace,ignore_actor)
    local start,velocity=projectile.position,projectile.velocity
    projectile.age=projectile.age+dt
    velocity.Z=velocity.Z-gravity*dt
    local finish=add(start,velocity,dt)
    local ignored={}
    for _=1,M.max_resweeps do
        local retry=false
        for _,hit in ipairs(trace(start,finish,M.radius,ignored))do
            if hit.blocking==true then
                if hit.actor and ignore_actor(hit.actor) then
                    -- A blocking character/attachment can hide the floor in
                    -- a multi trace. Ignore that actor and sweep the same step.
                    ignored[#ignored+1]=hit.actor;retry=true;break
                elseif not hit.start_penetrating then
                    local point,n=hit.ImpactPoint,hit.ImpactNormal
                    local len=math.sqrt(n.X*n.X+n.Y*n.Y+n.Z*n.Z)
                    if len>1e-6 then
                        local normal={X=n.X/len,Y=n.Y/len,Z=n.Z/len}
                        if velocity.Z<0 and normal.Z>=M.ground_normal_z and point.Z<=start.Z+.5 then
                            return 'land',point
                        end
                        local toward=velocity.X*normal.X+velocity.Y*normal.Y+velocity.Z*normal.Z
                        if toward<0 then
                            projectile.velocity=add(velocity,normal,-(1+M.restitution)*toward)
                            projectile.position=add(point,normal,M.radius+1)
                            if projectile.age>=M.ttl then return 'expire' end
                            return 'move',projectile.position
                        end
                    end
                end
            end
        end
        if not retry then break end
    end
    if projectile.age>=M.ttl then return 'expire' end
    projectile.position=finish
    return 'move',finish
end
return M
