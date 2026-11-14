-- Mod-local lookup cache. Never changes UEHelpers or caches input/menu state.
local M={}
function M.new(base,clock)
    clock=clock or os.clock
    local controller,expires=nil,0
    local facade=setmetatable({},{__index=base})
    function facade.GetPlayerController()
        local now=clock()
        if not controller or not controller:IsValid() or now>=expires then
            controller=base.GetPlayerController()
            expires=now+.25
        end
        return controller
    end
    function facade.GetPlayer()
        local pc=facade.GetPlayerController()
        -- Pawn is read fresh: possession/respawn must not reuse the old pawn.
        if pc and pc:IsValid() and pc.Pawn then return pc.Pawn end
        return CreateInvalidObject()
    end
    return facade
end
return M
