"""Offline Lua registration contract checks; does not execute native Copy/game."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tools/lua-python"))
from lupa import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
module = lua.execute((root / "src/runtime/RingedKnightArsenal/Scripts/NativeInventory.lua").read_text(encoding="utf-8"))
lua.globals().Inventory = module
lua.execute(r'''
function FText(s) assert(type(s)=='string','FText requires string');return {ToString=function()return s end} end
FName=FText
function IsInGameThread()return true end
local function flow(s)return {Namespace='',Key='',ValueCache=FText(s)}end
local function row(id)
    return {ItemId=FName(id),WeaponName=flow(id),EquipDescription=flow(''),ShortIntroduction=flow(''),WeaponConfig={GetObjectID=function()
        return {GetAssetPathName=function()return FName('/Game/Original/'..id)end}end}}
end
local function setup(invoke)
    local rows={['黑伤']=row('Tang'),Other=row('Other')}
    local state={calls={},cache={Tang=rows['黑伤'],Other=rows.Other},published={}}
    local data={}
    function data:GetRowStruct()return {GetFullName=function()return 'ScriptStruct /Script/ProjectPBZ.WeaponData'end}end
    function data:ForEachRow(fn)for k,v in pairs(rows)do fn(k,v)end end
    function data:FindRow(id)return rows[id]end
    function data:RemoveRow(id)rows[id]=nil end
    local spec={base_item='Tang',name='Ringed Knight',description='Independent weapon'}
    local registry={get=function(_,id)if id=='RKA_RingedKnight'then return spec end end}
    local function clone(req)
        state.calls[#state.calls+1]=req.phase
        if req.phase=='publish'then
            local value=assert(rows[req.id]);assert(value.ItemId:ToString()==req.id)
            assert(value.WeaponName.ValueCache:ToString()=='Ringed Knight','Metadata must finish before native publication')
            assert(rows['黑伤'].ItemId:ToString()=='Tang' and state.cache.Tang==rows['黑伤'])
            state.cache[req.id]=value;state.published[req.id]=true
            return {ok=true,id=req.id,published=true,cache_pointer_verified=true}
        end
        if req.phase=='row_rollback'then
            assert(not state.published[req.id],'Cannot remove a published native row')
            assert(req.id=='RKA_RingedKnight' and rows[req.id]);rows[req.id]=nil
            return {ok=true,removed=true,id=req.id}
        end
        assert(req.phase=='clone' and req.base_row=='黑伤' and req.base_item=='Tang')
        assert(not rows[req.id])
        rows[req.id]=row('Tang')
        return {ok=true,deep_copy=true,id=req.id}
    end
    local function prepare(value,definition)
        value.WeaponName.Namespace='';value.WeaponName.Key='';value.WeaponName.ValueCache=FText(definition.name)
        value.EquipDescription.ValueCache=FText(definition.description)
        value.ShortIntroduction.ValueCache=FText(definition.description)
    end
    return Inventory.new(function()return data end,registry,invoke==false and nil or (invoke or clone),prepare),rows,spec,state
end
do
    local inv,rows,_,state=setup()
    local result=inv:register('RKA_RingedKnight')
    assert(result.original_rows==2 and result.rows_after==3 and not result.granted and not result.selected)
    assert(rows['黑伤'].ItemId:ToString()=='Tang' and rows['黑伤'].WeaponName.ValueCache:ToString()=='Tang')
    assert(rows.Other.ItemId:ToString()=='Other')
    assert(rows.RKA_RingedKnight.WeaponName.ValueCache:ToString()=='Ringed Knight')
    assert(result.published and state.cache.RKA_RingedKnight==rows.RKA_RingedKnight)
    assert(state.calls[1]=='clone' and state.calls[2]=='publish' and #state.calls==2)
    assert(inv:register('RKA_RingedKnight')==result)
    assert(#state.calls==2,'Registration must not republish or duplicate cache entries')
    assert(not pcall(function()inv:remove_unreferenced('RKA_RingedKnight',function()return true end)end))
    assert(rows.RKA_RingedKnight)
    assert(not pcall(function()inv:remove_unreferenced('RKA_RingedKnight',function()return false end)end))
    assert(rows.RKA_RingedKnight and state.cache.RKA_RingedKnight==rows.RKA_RingedKnight and rows['黑伤'] and rows.Other)
end
do
    local inv,rows,spec,state=setup()
    spec.name={bad=true} -- forces row metadata readback failure after cloning
    assert(not pcall(function()inv:register('RKA_RingedKnight')end))
    assert(not rows.RKA_RingedKnight and rows['黑伤'].ItemId:ToString()=='Tang')
    assert(#state.calls==2 and state.calls[1]=='clone' and state.calls[2]=='row_rollback' and not state.cache.RKA_RingedKnight)
    spec.name='Ringed Knight'
    assert(inv:register('RKA_RingedKnight').rows_after==3)
    assert(not pcall(function()inv:remove_unreferenced('RKA_RingedKnight',function()return false end)end))
    assert(rows.RKA_RingedKnight and state.cache.RKA_RingedKnight==rows.RKA_RingedKnight)
end
do
    local inv,rows=setup(false)
    inv.invoke=nil
    assert(not pcall(function()inv:register('RKA_RingedKnight')end))
    assert(not rows.RKA_RingedKnight and rows['黑伤'] and rows.Other)
end
do
    local inv,rows=setup()
    inv.prepare_row=nil
    assert(not pcall(function()inv:register('RKA_RingedKnight')end))
    assert(not rows.RKA_RingedKnight and rows['黑伤'] and rows.Other)
end
do
    local inv,rows=setup()
    -- Replace the bridge after setup so it can model a publication failure
    -- after the native cache may already retain the metadata-complete row.
    local clone_data
    inv.invoke=function(req)
        if req.phase=='clone'then
            rows[req.id]=row('Tang');return {ok=true,deep_copy=true,id=req.id}
        end
        assert(req.phase=='publish');clone_data=rows[req.id]
        error('simulated native publication verification failure')
    end
    assert(not pcall(function()inv:register('RKA_RingedKnight')end))
    assert(clone_data and rows.RKA_RingedKnight==clone_data and rows['黑伤'] and rows.Other,
        'Publication failure must retain the potentially cached row; never leave a dangling pointer')
end
''')
print("PASS Lua registration: Chinese source key, separate row, FlowLocText, original preservation, prewarmed cache publication, idempotence, published-pointer retention, metadata rollback, missing bridge/callback fail-closed")
print("Native UE Copy, map ownership, selection, save/load and upgrades require prepared in-game acceptance.")
