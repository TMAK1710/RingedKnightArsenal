from pathlib import Path
import sys
p=Path(__file__).resolve().parents[1];sys.path.insert(0,str(p/'tools/lua-python'))
from lupa.lua54 import LuaRuntime
l=LuaRuntime(unpack_returned_tuples=True)
l.globals().M=l.execute((p/'src/runtime/RingedKnightArsenal/Scripts/ActionDamageReduction.lua').read_text(encoding='utf-8'))
l.execute(r'''
local function modifier(name,value)return {Attribute={AttributeName=name},ModifierMagnitude={ScalableFloatMagnitude={Value=value}}}end
local function effect(value)return {Modifiers={modifier('TakenReductionMultiplier_Physical',value),modifier('TakenReductionMultiplier_Elemental',value)},DurationMagnitude={ScalableFloatMagnitude={Value=0}},DurationPolicy=1,IsValid=function()return true end}end
local original=effect(.75)
local outer={IsValid=function()return true end,GetFullName=function()return 'Package /HuaShira/Mods/RingedKnight/Data/Weapon_RKA_RingedKnight'end,GetAddress=function()return 1 end}
local class={IsValid=function()return true end};local owned;local made=0
function IsInGameThread()return true end
function FName(s)return s end
function StaticFindObject(path)
 if path==M.path then return owned end
 if path:find('Default__',1,true)then return original end
 return class
end
function StaticConstructObject(c,o,n,flags,internal)
 assert(c==class and o==outer and flags==0xC1 and internal==0x40000000)
 made=made+1;owned=effect(.75);owned.GetOuter=function()return outer end;return owned
end
assert(M.prepare(outer)==owned and made==1)
assert(owned.DurationPolicy==2 and owned.DurationMagnitude.ScalableFloatMagnitude.Value==.25)
assert(owned.Modifiers[1].ModifierMagnitude.ScalableFloatMagnitude.Value==.2)
assert(owned.Modifiers[2].ModifierMagnitude.ScalableFloatMagnitude.Value==.2)
assert(original.DurationPolicy==1 and original.Modifiers[1].ModifierMagnitude.ScalableFloatMagnitude.Value==.75)
assert(M.prepare(outer)==owned and made==1)
owned.DurationPolicy=1;assert(not pcall(M.prepare,outer));owned.DurationPolicy=2
owned.Modifiers[1].ModifierMagnitude.ScalableFloatMagnitude.Value=.1;assert(not pcall(M.prepare,outer))
owned.Modifiers[1].ModifierMagnitude.ScalableFloatMagnitude.Value=.2
original.Modifiers[2].Attribute.AttributeName='Health';assert(not pcall(M.prepare,outer))
''')
print('PASS owned finite 80% reduction: physical/elemental, original preservation, idempotence, bad lifetime/schema rejection')
