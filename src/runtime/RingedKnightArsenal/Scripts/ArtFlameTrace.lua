-- Pure geometry only. Runtime enables extra reach inside real sword contact
-- windows and shares the steel contact damage key.
local M={max_coordinate_cm=10000,max_steel_length_cm=1000,max_extension_cm=1000,max_radius_cm=500}

local function finite(value,label)
    assert(type(value)=='number' and value==value and math.abs(value)<math.huge,
        'Art flame trace requires finite '..label)
    return value
end

local function point(value,label)
    assert(type(value)=='table','Art flame trace requires '..label)
    local result={}
    for _,axis in ipairs({'X','Y','Z'})do
        result[axis]=finite(value[axis],label..'.'..axis)
        assert(math.abs(result[axis])<=M.max_coordinate_cm,'Art flame trace coordinate exceeds bounds')
    end
    return result
end

function M.segment(volume)
    assert(type(volume)=='table' and volume.space=='sword_local_cm',
        'Art flame trace requires sword_local_cm geometry')
    local base=point(volume.base,'base')
    local tip=point(volume.steel_tip,'steel_tip')
    local extension=finite(volume.tip_extension_cm,'tip_extension_cm')
    local radius=finite(volume.radius_cm,'radius_cm')
    assert(extension>=0 and extension<=M.max_extension_cm,'Art flame trace extension exceeds bounds')
    assert(radius>0 and radius<=M.max_radius_cm,'Art flame trace radius exceeds bounds')
    local dx,dy,dz=tip.X-base.X,tip.Y-base.Y,tip.Z-base.Z
    local length=math.sqrt(dx*dx+dy*dy+dz*dz)
    assert(length>=.001 and length<=M.max_steel_length_cm,'Art flame trace steel length exceeds bounds')
    local finish=point({X=tip.X+dx/length*extension,Y=tip.Y+dy/length*extension,
        Z=tip.Z+dz/length*extension},'extended_tip')
    return {start=base,finish=finish,radius_cm=radius,space='sword_local_cm'}
end

-- Scale reach from the blade base; keep width and original profile immutable.
function M.scaled_segment(volume,scale)
    local original=M.segment(volume)
    scale=finite(scale,'reach_scale')
    assert(scale>=1 and scale<=4,'Sword reach scale exceeds bounds')
    local dx=volume.steel_tip.X-volume.base.X
    local dy=volume.steel_tip.Y-volume.base.Y
    local dz=volume.steel_tip.Z-volume.base.Z
    local steel=math.sqrt(dx*dx+dy*dy+dz*dz)
    return M.segment({space=volume.space,base=volume.base,steel_tip=volume.steel_tip,
        tip_extension_cm=(steel+volume.tip_extension_cm)*scale-steel,
        radius_cm=original.radius_cm})
end

local function distance(a,b)
    return math.sqrt((a.X-b.X)^2+(a.Y-b.Y)^2+(a.Z-b.Z)^2)
end

local function distance_to_segment(value,start,finish)
    local x,y,z=finish.X-start.X,finish.Y-start.Y,finish.Z-start.Z
    local t=math.max(0,math.min(1,((value.X-start.X)*x+(value.Y-start.Y)*y+(value.Z-start.Z)*z)/(x*x+y*y+z*z)))
    return math.sqrt((value.X-start.X-t*x)^2+(value.Y-start.Y-t*y)^2+(value.Z-start.Z-t*z)^2)
end

local function track_point(track,time,fps)
    local frame=math.max(0,math.min(#track-1,time*fps))
    local lo=math.floor(frame)+1;local hi=math.min(#track,lo+1);local fraction=frame%1
    local a,b=track[lo],track[hi]
    assert(type(a)=='table'and type(b)=='table','Blade sweep requires sampled points')
    local output={}
    for i,axis in ipairs({'X','Y','Z'})do
        local first=finite(a[i],'track point');local last=finite(b[i],'track point')
        output[axis]=first+(last-first)*fraction
    end
    return point(output,'blade track')
end

-- The curve is the exported mesh-local pose, never the asynchronously updated
-- attached sword component. Every output uses a constant authored reach.
function M.swept_segments(clip,from_time,to_time,length_cm,radius_cm,max_samples)
    assert(type(clip)=='table'and type(clip.blade_tracks)=='table','Blade sweep requires baked blade tracks')
    local tracks=clip.blade_tracks;local fps=finite(clip.fps,'blade fps')
    local duration=finite(clip.duration,'blade duration')
    assert(fps>0 and fps<=240 and duration>0,'Invalid blade sample grid')
    assert(type(tracks.base)=='table'and type(tracks.steel_tip)=='table'
        and #tracks.base>=2 and #tracks.base==#tracks.steel_tip
        and #tracks.base==clip.frames,'Blade sweep track frame mismatch')
    from_time=finite(from_time,'sweep start');to_time=finite(to_time,'sweep finish')
    assert(from_time>=0 and to_time>=from_time and to_time<=duration+1e-6,'Blade sweep outside clip interval')
    from_time=math.min(from_time,duration);to_time=math.min(to_time,duration)
    length_cm=finite(length_cm,'sweep length');radius_cm=finite(radius_cm,'sweep radius')
    assert(length_cm>0 and length_cm<=M.max_steel_length_cm+M.max_extension_cm,'Blade sweep length exceeds bounds')
    assert(radius_cm>0 and radius_cm<=M.max_radius_cm,'Blade sweep radius exceeds bounds')
    max_samples=finite(max_samples or 64,'sweep sample budget')
    assert(max_samples>=1 and max_samples<=64 and max_samples%1==0,'Blade sweep permits at most 64 queries')
    local pose_cache={}
    local function pose(time)
        if pose_cache[time] then return pose_cache[time] end
        local base=track_point(tracks.base,time,fps);local tip=track_point(tracks.steel_tip,time,fps)
        local steel=distance(base,tip)
        assert(steel>=.001 and steel<=M.max_steel_length_cm,'Degenerate blade sweep direction')
        local axis={X=(tip.X-base.X)/steel,Y=(tip.Y-base.Y)/steel,Z=(tip.Z-base.Z)/steel}
        local result={base=base,axis=axis,steel=steel,
            tip=point({X=base.X+length_cm*axis.X,Y=base.Y+length_cm*axis.Y,Z=base.Z+length_cm*axis.Z},'sweep tip')}
        pose_cache[time]=result
        return result
    end
    local function enclosure(first,last)
        local middle=(first+last)/2;local center=pose(middle)
        local times={first}
        for frame=math.floor(first*fps)+1,math.ceil(last*fps)-1 do
            local time=frame/fps
            if time>first and time<last then times[#times+1]=time end
        end
        if last>first then times[#times+1]=last end
        local displacement,curvature,previous=0,0,nil
        for _,time in ipairs(times)do
            local current=pose(time)
            displacement=math.max(displacement,distance_to_segment(current.base,center.base,center.tip),
                distance_to_segment(current.tip,center.base,center.tip))
            if previous then
                local a,b=previous.axis,current.axis
                local dot=math.max(-1,math.min(1,a.X*b.X+a.Y*b.Y+a.Z*b.Z))
                local half_cos=math.sqrt((1+dot)/2)
                assert(half_cos>.001,'Blade track reverses direction within one frame')
                -- Frame interpolation normalizes the tip-base vector. Its arc
                -- can leave the endpoint chord; enclose that sagitta as well.
                -- Unequal steel lengths slightly reparameterize the arc.
                local r1,r2=math.sqrt(previous.steel),math.sqrt(current.steel)
                local parameter_error=math.abs(r1-r2)/(r1+r2)
                local bound=length_cm*(1-half_cos+2*parameter_error*distance(a,b)/half_cos)
                curvature=math.max(curvature,bound)
            end
            previous=current
        end
        local inflation=displacement+curvature
        return {start=center.base,finish=center.tip,radius_cm=radius_cm+inflation,
            inflation_cm=inflation,space='mesh_local_cm',time=middle,from_time=first,to_time=last}
    end
    local output={enclosure(from_time,to_time)}
    while #output<max_samples do
        local selected,worst=nil,12
        for index,segment in ipairs(output)do
            if segment.inflation_cm>worst and segment.to_time-segment.from_time>1e-7 then
                selected,worst=index,segment.inflation_cm
            end
        end
        if not selected then break end
        local segment=output[selected];local middle=(segment.from_time+segment.to_time)/2
        output[selected]=enclosure(segment.from_time,middle)
        table.insert(output,selected+1,enclosure(middle,segment.to_time))
    end
    -- Never turn an undersampled fast swing into a huge damage sphere. The
    -- caller can fall back to one exact event-time capsule and record overflow.
    for _,segment in ipairs(output)do
        if segment.inflation_cm>24 then return nil,'sweep_budget_exhausted' end
    end
    return output
end
return M
