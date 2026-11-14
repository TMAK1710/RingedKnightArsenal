"""Check the grounded-fuse policy, not native trace or visual acceptance."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools/lua-python'))
from lupa.lua54 import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().Landing = lua.execute((root / 'src/runtime/RingedKnightArsenal/Scripts/BombLanding.lua').read_text(encoding='utf-8'))
lua.execute('''
function v(x,y,z)return {X=x,Y=y,Z=z}end
function projectile()return {position=v(0,0,20),velocity=v(50,0,-180),age=0}end
function hit(actor,normal,blocking,penetrating)
    return {actor=actor,ImpactPoint=v(0,0,0),ImpactNormal=normal,blocking=blocking,start_penetrating=penetrating}
end
function ignore(actor)return actor=='hero' or actor=='shield' or actor=='enemy'end
''')
cases = {
    'descending_blocking_floor_lands': '''
local state,point=Landing.advance(projectile(),.1,980,function()return {hit('floor',v(0,0,1),true,false)}end,ignore)
assert(state=='land' and point.Z==0)
''',
    'shield_blocker_is_ignored_and_same_step_is_reswept': '''
local queries=0
local state=Landing.advance(projectile(),.1,980,function(a,b,radius,ignored)
    queries=queries+1
    if queries==1 then assert(#ignored==0);return {hit('shield',v(0,0,1),true,false)}end
    assert(ignored[1]=='shield');return {hit('floor',v(0,0,1),true,false)}
end,ignore)
assert(state=='land' and queries==2)
''',
    'hero_and_enemy_never_detonate': '''
for _,actor in ipairs({'hero','enemy'})do
    local state=Landing.advance(projectile(),.1,980,function(a,b,radius,ignored)
        if #ignored>0 then return {}end
        return {hit(actor,v(0,0,1),true,false)}
    end,ignore)
    assert(state=='move')
end
''',
    'wall_reflects_without_detonation': '''
local p=projectile()
local state=Landing.advance(p,.1,980,function()return {hit('wall',v(-1,0,0),true,false)}end,ignore)
assert(state=='move' and p.velocity.X<0 and p.velocity.Z<0)
''',
    'overlap_and_initial_penetration_do_not_count_as_ground': '''
for _,flags in ipairs({{false,false},{true,true}})do
    local state=Landing.advance(projectile(),.1,980,function()return {hit('volume',v(0,0,1),flags[1],flags[2])}end,ignore)
    assert(state=='move')
end
''',
    'timeout_expires_without_blast': '''
local p=projectile();p.age=4.99
local state,point=Landing.advance(p,.1,980,function()return {}end,ignore)
assert(state=='expire' and point==nil)
''',
}
results = []
for name, case in cases.items():
    lua.execute(case)
    results.append({'name': name, 'pass': True})
    print('PASS', name)
(root / 'reports/bomb-ground-only-offline.json').write_text(json.dumps({'cases': results, 'runtime_verified': False}, indent=2)+'\n', encoding='utf-8')
