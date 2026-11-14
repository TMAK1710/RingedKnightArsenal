"""Actual ArtResource Lua adapter with mocked decoded native receipts."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/lua-python'))
from lupa.lua54 import LuaRuntime
SOURCE=ROOT/'src/runtime/RingedKnightArsenal/Scripts/ArtResource.lua'
cases={
 'normal_and_duplicate_action_receipts_use_one_native_identity':r'''
local requests={};local M=dofile(source)
local invoke=function(q)
 requests[#requests+1]=q
 if q.phase=='capabilities'then return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=12}end
 assert(q.pawn=='Player.Path'and q.sequence==3 and q.session_token==12 and q.amount==nil)
 return {api=1,resource='UltimateChargeCount',amount=1,sequence=3,session_token=12,paid=true,committed=true,dispatched=true,status='paid',before=2,after=1}
end
local r=M.new(invoke,'Player.Path');assert(r:pay(3));assert(r:pay(3))
assert(#requests==3 and requests[2].sequence==requests[3].sequence)
''',
 'insufficient_same_identity_can_succeed_after_native_refill':r'''
local stock=0;local M=dofile(source)
local r=M.new(function(q)
 if q.phase=='capabilities'then return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1}end
 local b=stock;local paid=stock>=1;if paid then stock=stock-1 end
 return {api=1,resource='UltimateChargeCount',amount=1,sequence=q.sequence,session_token=1,paid=paid,committed=paid,dispatched=paid,status=paid and 'paid'or'insufficient',before=b,after=stock}
end,'Player.Path')
assert(not r:pay(7));stock=2;assert(r:pay(7)and stock==1)
''',
 'committed_readback_failure_does_not_cancel_or_recharge_action':r'''
local M=dofile(source);local receipt
local r=M.new(function(q)
 if q.phase=='capabilities'then return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1}end
 receipt={api=1,resource='UltimateChargeCount',amount=1,sequence=q.sequence,session_token=1,paid=false,committed=true,dispatched=true,status='uncertain',before=2,after=2,error='readback failed'}
 return receipt
end,'Player.Path')
local allowed,returned=r:pay(9);assert(allowed and returned==receipt)
''',
 'wrong_resource_or_cost_or_idempotence_capability_rejected':r'''
local M=dofile(source)
for _,key in ipairs({'api','resource','amount','once_per_action','session_token'})do
 local ok=pcall(M.new,function()local q={api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1};q[key]=nil;return q end,'Player.Path')
 assert(not ok,key)
end
''',
 'invalid_action_id_rejected_before_spend':r'''
local M=dofile(source);local spends=0
local r=M.new(function(q)assert(q.phase=='capabilities');return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1}end,'Player.Path')
for _,id in ipairs({0,-1,.5,math.huge,0/0,9007199254740992,'1'})do assert(not pcall(r.pay,r,id))end
''',
 'mismatched_native_receipt_rejected':r'''
local M=dofile(source)
for _,key in ipairs({'api','resource','amount','sequence','session_token','paid','committed'})do
 local r=M.new(function(q)
  if q.phase=='capabilities'then return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1}end
  local v={api=1,resource='UltimateChargeCount',amount=1,sequence=2,session_token=1,paid=true,committed=true,dispatched=true,status='paid',before=2,after=1};v[key]=nil;return v
 end,'Player.Path')
 assert(not pcall(r.pay,r,2),key)
end
''',
 'claimed_paid_without_exact_debit_rejected':r'''
local M=dofile(source)
local r=M.new(function(q)
 if q.phase=='capabilities'then return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1}end
 return {api=1,resource='UltimateChargeCount',amount=1,sequence=2,session_token=1,paid=true,committed=true,dispatched=true,status='paid',before=2,after=2}
end,'Player.Path');assert(not pcall(r.pay,r,2))
''',
 'insufficient_cannot_be_marked_committed':r'''
local M=dofile(source)
local r=M.new(function(q)
 if q.phase=='capabilities'then return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=1}end
 return {api=1,resource='UltimateChargeCount',amount=1,sequence=2,session_token=1,paid=false,committed=true,dispatched=true,status='insufficient',before=0,after=0}
end,'Player.Path');assert(not pcall(r.pay,r,2))
''',
 'new_activation_gets_fresh_native_session':r'''
local M=dofile(source);local token=0
local invoke=function(q)assert(q.phase=='capabilities');token=token+1;return {api=1,resource='UltimateChargeCount',amount=1,once_per_action=true,session_token=token}end
local a=M.new(invoke,'Player.Path');local b=M.new(invoke,'Player.Path');assert(a.session_token~=b.session_token)
''',
}
results=[]
for name,body in cases.items():
 lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().source=str(SOURCE).replace('\\','/')
 try:lua.execute(body);results.append({'name':name,'pass':True})
 except Exception as error:results.append({'name':name,'pass':False,'error':str(error)})
report={'scope':'Actual Lua adapter with mocked native receipts; no in-game payment proof','sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'runtime_verified':False,'cases':results}
(ROOT/'reports/offline-art-resource-tests-087.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':sum(x['pass'] for x in results),'total':len(results)}))
assert all(x['pass'] for x in results),results
