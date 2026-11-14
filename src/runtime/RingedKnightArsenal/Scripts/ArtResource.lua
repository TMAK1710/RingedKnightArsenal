-- Original ZhanMa CombatArt pays one UltimateChargeCount through PBZ's native
-- attribute utility. This is pure killing energy, separate from SpiritShadow.
local M={};M.__index=M
local function sequence_ok(value)
    return type(value)=='number'and value>0 and value<=9007199254740991 and value==math.floor(value)
end
function M.new(invoke,pawn_path)
    assert(type(invoke)=='function'and type(pawn_path)=='string'and #pawn_path>0,'Art resource bridge/player required')
    local capability=assert(invoke({phase='capabilities'}),'Art resource capability reply missing')
    assert(capability.api==1 and capability.resource=='UltimateChargeCount'and capability.amount==1
        and capability.once_per_action==true and sequence_ok(capability.session_token),'Art resource native capability mismatch')
    return setmetatable({invoke=invoke,pawn=pawn_path,session_token=capability.session_token},M)
end
-- sequence identifies the complete stance+branch, never an individual hit.
-- Native receipts retain the high-water mark even after an uncertain debit;
-- retrying a reply must not charge the same activation a second time.
function M:pay(sequence)
    assert(sequence_ok(sequence),'Art resource requires a positive integer action sequence')
    local receipt=assert(self.invoke({phase='spend',pawn=self.pawn,session_token=self.session_token,sequence=sequence}),
        'Art resource spend reply missing')
    assert(receipt.api==1 and receipt.resource=='UltimateChargeCount'and receipt.amount==1
        and receipt.session_token==self.session_token and receipt.sequence==sequence
        and type(receipt.paid)=='boolean'and type(receipt.committed)=='boolean','Art resource native receipt mismatch')
    if receipt.paid then
        assert(receipt.status=='paid'and receipt.dispatched==true and receipt.committed==true and type(receipt.before)=='number'
            and type(receipt.after)=='number'and receipt.before>=1 and receipt.after>=0
            and math.abs(receipt.before-receipt.after-1)<.0001,'Art resource debit readback mismatch')
    else
        assert(receipt.status=='insufficient'or receipt.status=='uncertain'or receipt.status=='debit_mismatch',
            'Art resource native failure status mismatch')
        assert((receipt.status=='insufficient'and receipt.committed==false and receipt.dispatched==false)
            or(receipt.status~='insufficient'and receipt.committed==true and receipt.dispatched==true),
            'Art resource commitment status mismatch')
    end
    self.last_receipt=receipt
    -- The modifier is a void native API. Once dispatched, a failed optional
    -- readback must neither cancel the paid action nor cause another debit.
    return receipt.paid or receipt.committed,receipt
end
return M
