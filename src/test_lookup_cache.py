"""Lookup lifetime tests; mock checks do not establish game performance."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/lua-python'))
from lupa.lua54 import LuaRuntime
lua=LuaRuntime(unpack_returned_tuples=True)
s=root/'src/runtime/RingedKnightArsenal/Scripts'
lua.globals().Context=lua.execute((s/'PlayerContext.lua').read_text(encoding='utf-8'))
lua.globals().Inventory=lua.execute((s/'NativeInventory.lua').read_text(encoding='utf-8'))
main=(s/'main.lua').read_text(encoding='utf-8')
menu=main[main.index('function runtime:menu_blocked'):main.index('runtime.weapon_switch=')]
lua.execute("runtime={}; function valid(o)return o and o:IsValid()end; function same(a,b)return valid(a)and valid(b)and a:GetAddress()==b:GetAddress()end; Gameplay={IsGamePaused=function()return false end}; FName=function(s)return s end")
lua.execute(menu)
lua.execute(r'''
local function obj(id,outer)
 return {ok=true,IsValid=function(self)return self.ok end,GetAddress=function()return id end,
 GetOuter=function()return outer end,GetFullName=function()return 'Live '..id end}
end
function CreateInvalidObject()return {IsValid=function()return false end}end
local now,calls=0,0;local pc=obj(1);pc.Pawn=obj(2)
local base={GetPlayerController=function()calls=calls+1;return pc end}
local original=base.GetPlayerController
local h=Context.new(base,function()return now end)
assert(h.GetPlayer()==pc.Pawn and h.GetPlayerController()==pc and calls==1)
assert(base.GetPlayerController==original)
pc.Pawn=obj(3);assert(h.GetPlayer()==pc.Pawn and calls==1)
now=.26;h.GetPlayerController();assert(calls==2)
local old=pc;old.ok=false;pc=obj(4);pc.Pawn=obj(5)
assert(h.GetPlayer()==pc.Pawn and calls==3)
local old2=pc;pc=obj(6);pc.Pawn=obj(7);now=.52
assert(h.GetPlayer()==pc.Pawn and calls==4 and old2.ok)
pc.ok=false;assert(not h.GetPlayer():IsValid())
local world1,world2=obj(20),obj(21);local a,b=obj(22,world1),obj(23,world2)
a.CurrentMainWeaponID='ringed';b.CurrentMainWeaponID='other'
local scans=0;FindAllOf=function(class)assert(class=='PBZBackPackSubsystem');scans=scans+1;return {a,b}end
local inv=Inventory.new(nil,{get=function(_,id)return id end})
local id,owner=inv:selection(world1);assert(id=='ringed'and owner==a and scans==1)
a.CurrentMainWeaponID='other';assert(inv:selection(world1)=='other'and scans==1)
local _,owner2=inv:selection(world2);assert(owner2==b and scans==2)
b.ok=false;assert(inv:selection(world2)==nil and scans==3)
assert(inv:selection(nil)==nil and inv.selection_owner==nil)
local player1,player2=obj(30),obj(31)
local router1,router2=obj(32,player1),obj(33,player2)
router1.mode=1;router2.mode=0
function router1:GetActiveInputMode()return self.mode end
router2.GetActiveInputMode=router1.GetActiveInputMode
local c=obj(34);c.Player=player1;c.IsInputKeyDown=function()return false end
runtime.native_input_blocked=function()return false end
runtime.control_lease_guard={router=router1,update=function()end,interaction_active=function(self)return self.busy end}
local ui_scans=0;FindAllOf=function(class)assert(class=='PBZUIActionRouterBase');ui_scans=ui_scans+1;return {router1,router2}end
assert(not runtime:menu_blocked(c,obj(35))and ui_scans==0)
router1.mode=0;assert(runtime:menu_blocked(c,obj(35))and ui_scans==0)
router1.mode=1;runtime.control_lease_guard.busy=true;assert(runtime:menu_blocked(c,obj(35)))
runtime.control_lease_guard.busy=false;c.Player=player2
assert(runtime:menu_blocked(c,obj(35))and ui_scans==1)
router2.ok=false;assert(not runtime:menu_blocked(c,obj(35))and ui_scans==2)
''')
print('lookup lifetime: 17 assertions passed (offline)')
