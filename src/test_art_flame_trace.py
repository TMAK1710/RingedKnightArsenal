"""Pure Lua segment geometry checks; no Unreal/gameplay/visual acceptance."""
import hashlib,json,sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/lua-python'))
from lupa.lua54 import LuaRuntime

scripts=root/'src/runtime/RingedKnightArsenal/Scripts'
module=scripts/'ArtFlameTrace.lua'
profile_path=scripts/'combat-profile.json'
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().Trace=lua.execute(module.read_text(encoding='utf-8'))
lua.globals().P=lua.execute((scripts/'dkjson.lua').read_text()).decode(profile_path.read_text())[0]
lua.execute('''
function volume()
 return {space='sword_local_cm',base={X=.056,Y=.484,Z=-30.457},
  steel_tip={X=.056,Y=.484,Z=-111.485},tip_extension_cm=100,radius_cm=24}
end
function near(a,b)assert(math.abs(a-b)<1e-9,tostring(a)..' ~= '..tostring(b))end
''')
cases={
 'double_reach_preserves_width_and_origin':"""
local v=volume();local old=Trace.segment(v);local new=Trace.scaled_segment(v,2)
for _,axis in ipairs({'X','Y','Z'})do near(new.start[axis],old.start[axis]);near(new.finish[axis]-new.start[axis],2*(old.finish[axis]-old.start[axis]))end
assert(new.radius_cm==old.radius_cm and v.tip_extension_cm==100)
v.tip_extension_cm=0;old=Trace.segment(v);new=Trace.scaled_segment(v,2)
near(new.finish.Z-new.start.Z,2*(old.finish.Z-old.start.Z))
""",
 'invalid_reach_scale_rejected':"""
for _,scale in ipairs({0,-1,.5,5,0/0,math.huge})do assert(not pcall(Trace.scaled_segment,volume(),scale))end
""",

 'profile_negative_Z_extension_matches_estimate':"""
local s=Trace.segment(P.art.hit_volume)
near(s.start.X,.056);near(s.start.Y,.484);near(s.start.Z,-30.457)
near(s.finish.X,.056);near(s.finish.Y,.484);near(s.finish.Z,-211.485)
assert(s.radius_cm==24 and s.space=='sword_local_cm')
assert(P.art.hit_volume.activation=='real_art_hit_windows_only')
""",
 'returns_independent_points_without_mutating_input':"""
local v=volume();local s=Trace.segment(v);s.start.X=10;s.finish.Z=10
assert(v.base.X==.056 and v.steel_tip.Z==-111.485 and v.tip_extension_cm==100)
""",
 'zero_extension_stops_exactly_at_steel_tip':"""
local v=volume();v.tip_extension_cm=0;local s=Trace.segment(v)
for _,axis in ipairs({'X','Y','Z'})do near(s.finish[axis],v.steel_tip[axis])end
""",
 'diagonal_extension_uses_normalized_direction':"""
local v=volume();v.base={X=1,Y=2,Z=3};v.steel_tip={X=4,Y=6,Z=3};v.tip_extension_cm=10
local s=Trace.segment(v);near(s.finish.X,10);near(s.finish.Y,14);near(s.finish.Z,3)
""",
 'positive_axis_is_not_inverted':"""
local v=volume();v.base={X=0,Y=0,Z=0};v.steel_tip={X=0,Y=0,Z=10};v.tip_extension_cm=20
near(Trace.segment(v).finish.Z,30)
""",
 'nonfinite_scalars_are_rejected':"""
for _,key in ipairs({'tip_extension_cm','radius_cm'})do
 for _,invalid in ipairs({0/0,math.huge,-math.huge})do local v=volume();v[key]=invalid;assert(not pcall(Trace.segment,v))end
end
""",
 'nonfinite_or_missing_points_are_rejected':"""
for _,key in ipairs({'base','steel_tip'})do
 for _,axis in ipairs({'X','Y','Z'})do
  for _,invalid in ipairs({0/0,math.huge,-math.huge,'1'})do
   local v=volume();v[key][axis]=invalid;assert(not pcall(Trace.segment,v))
  end
  local v=volume();v[key][axis]=nil;assert(not pcall(Trace.segment,v))
 end
end
""",
 'invalid_space_and_container_are_rejected':"""
assert(not pcall(Trace.segment,nil));assert(not pcall(Trace.segment,{}))
for _,space in ipairs({'world_cm','sword_local_m',true})do local v=volume();v.space=space;assert(not pcall(Trace.segment,v))end
""",
 'negative_extension_and_invalid_radius_are_rejected':"""
local v=volume();v.tip_extension_cm=-.01;assert(not pcall(Trace.segment,v))
for _,radius in ipairs({0,-1,Trace.max_radius_cm+.01})do local v=volume();v.radius_cm=radius;assert(not pcall(Trace.segment,v))end
v=volume();v.tip_extension_cm=Trace.max_extension_cm+.01;assert(not pcall(Trace.segment,v))
""",
 'degenerate_steel_and_runaway_coordinates_are_rejected':"""
local v=volume();v.steel_tip=v.base;assert(not pcall(Trace.segment,v))
v=volume();v.steel_tip={X=v.base.X,Y=v.base.Y,Z=v.base.Z-.0001};assert(not pcall(Trace.segment,v))
v=volume();v.base.X=Trace.max_coordinate_cm+1;assert(not pcall(Trace.segment,v))
v=volume();v.steel_tip={X=v.base.X,Y=v.base.Y,Z=v.base.Z-Trace.max_steel_length_cm-1};assert(not pcall(Trace.segment,v))
""",
 'inclusive_valid_bounds_and_extended_tip_bounds':"""
local v=volume();v.base={X=0,Y=0,Z=0};v.steel_tip={X=0,Y=0,Z=-Trace.max_steel_length_cm}
v.tip_extension_cm=Trace.max_extension_cm;v.radius_cm=Trace.max_radius_cm
local s=Trace.segment(v);near(s.finish.Z,-Trace.max_steel_length_cm-Trace.max_extension_cm)
v.base={X=Trace.max_coordinate_cm-1,Y=0,Z=0};v.steel_tip={X=Trace.max_coordinate_cm,Y=0,Z=0}
assert(not pcall(Trace.segment,v))
""",
}
results=[]
for name,body in cases.items():
 try:lua.execute(body);results.append({'name':name,'pass':True});print('PASS',name)
 except Exception as error:results.append({'name':name,'pass':False,'error':str(error)});print('FAIL',name,error)
report={'scope':__doc__,'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),
 'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),
 'api':'ArtFlameTrace.segment(volume) -> {start={X,Y,Z},finish={X,Y,Z},radius_cm,space}',
 'measured_source':False,'source_policy':'Screenshot estimate; actual flame rendering fit pending manual test',
 'runtime_verified':False,'cases':results}
(root/'reports/offline-art-flame-trace-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
if not all(x['pass'] for x in results):raise SystemExit(1)
print('ART_FLAME_TRACE_READY cases='+str(len(results)))
