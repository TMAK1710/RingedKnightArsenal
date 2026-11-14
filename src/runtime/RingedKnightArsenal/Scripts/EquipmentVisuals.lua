-- Keep native display ownership tied to the equipped ID/slot. The inactive
-- custom or holstered active weapon gets one sword on the back; other native
-- weapons stay native.
local M={};M.__index=M
local function valid(value)return value and value:IsValid()==true end
local function same(a,b)return valid(a)and valid(b)and a:GetAddress()==b:GetAddress()end
local function vec(value)return {X=value[1],Y=value[2],Z=value[3]}end
local function identity()return {Rotation={X=0,Y=0,Z=0,W=1},Translation={X=0,Y=0,Z=0},Scale3D={X=1,Y=1,Z=1}}end
local BACK_SOCKET='Pt_TangBlade_Back_Socket'
local function hidden_flag(object)
    if object:IsA(StaticFindObject('/Script/Engine.Actor'))then return object.bHidden,'actor'end
    assert(object:IsA(StaticFindObject('/Script/Engine.SceneComponent')),'Unsupported native weapon display object class')
    return object.bHiddenInGame,'component'
end
local function set_hidden(object,kind,hidden)
    if kind=='actor'then object:SetActorHiddenInGame(hidden)
    else object:SetHiddenInGame(hidden,false)end
end
local function native_back_mount(mesh)
    local bone=mesh:GetSocketBoneName(FName(BACK_SOCKET)):ToString()
    for _=1,16 do
        if bone:lower():match('^spine_')then break end
        assert(bone~=''and bone~='None','Native back sword socket has no spine ancestor')
        bone=mesh:GetParentBone(FName(bone)):ToString()
    end
    assert(bone:lower():match('^spine_'),'Native back sword socket has no spine ancestor')
    local mathlib=StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
    assert(valid(mathlib),'Native back sword transform library unavailable')
    -- RTS_Component=2; convert the original socket into the actual spine bone's
    -- space, retaining native character/outfit socket offsets without guessing.
    local relative=mathlib:MakeRelativeTransform(mesh:GetSocketTransform(FName(BACK_SOCKET),2),mesh:GetSocketTransform(FName(bone),2))
    local q,t,s=relative.Rotation,relative.Translation,relative.Scale3D
    -- The mod sword extends along -Z, while the native Tang asset extends +Z.
    -- Flip local X180, then roll local Z90 so the blade plane lies against the
    -- back while its length keeps the native socket's downward direction.
    local x,y,z,w=q.W,q.Z,-q.Y,-q.X
    local half=math.sqrt(.5)
    return {bone=bone,t={t.X,t.Y,t.Z},q={(x+y)*half,(y-x)*half,(z+w)*half,(w-z)*half},s={s.X,s.Y,s.Z}}
end
function M.new(loader,equipment,registry,sword,back_mount)
    return setmetatable({load=loader,equipment=equipment,registry=registry,sword=sword,
        back_mount=back_mount,hidden={}},M)
end
function M:clear_back()
    assert(IsInGameThread(),'Back sword cleanup requires game thread')
    if valid(self.back)then self.back:K2_DestroyComponent(self.back)end
    self.back=nil
end
function M:clear()
    assert(IsInGameThread(),'Equipment visual cleanup requires game thread')
    local ok,why=pcall(self.clear_back,self)
    -- Restore only flags this module actually changed from visible to hidden.
    -- A native back-weapon's old hidden snapshot must never hide a new active one.
    for _,entry in ipairs(self.hidden)do
        if valid(entry.actor)then
            local restored,error_message=pcall(set_hidden,entry.actor,entry.kind,false)
            if not restored and ok then ok=false;why=error_message end
        end
    end
    self.hidden={};self.pawn=nil;self.world=nil;self.mesh=nil
    if not ok then error(why,0)end
end
function M:update(pawn,owner,drawn,active_holstered)
    assert(IsInGameThread(),'Equipment visuals require game thread')
    if not valid(pawn)or not valid(owner)or not valid(pawn.Mesh)then self:clear();return end
    local world=pawn:GetWorld()
    if not valid(world)then self:clear();return end
    if not same(self.pawn,pawn)or not same(self.world,world)or not same(self.mesh,pawn.Mesh)then
        self:clear();self.pawn=pawn;self.world=world;self.mesh=pawn.Mesh
    end
    local display=self.equipment:display_slots(pawn,owner)
    -- A native index transition may be pending while individual slot configs
    -- remain verified. Use only those fresh identities, never a cached hide list.
    local inactive=false
    local hide={}
    for _,slot in ipairs(display.slots)do
        if self.registry:get(slot.id)and slot.verified~=false then
            local stowed=slot.index~=display.current or active_holstered==true
            inactive=inactive or stowed
            if stowed or drawn then
                for _,actor in ipairs(slot.actors)do
                    assert(valid(actor),'Owned native weapon display actor invalid')
                    hide[actor:GetAddress()]=actor
                end
            end
        end
    end
    for index=#self.hidden,1,-1 do
        local entry=self.hidden[index]
        if not valid(entry.actor)or not hide[entry.actor:GetAddress()]then
            if valid(entry.actor)then set_hidden(entry.actor,entry.kind,false)end
            table.remove(self.hidden,index)
        end
    end
    for address,actor in pairs(hide)do
        local hidden,kind=hidden_flag(actor)
        assert(type(hidden)=='boolean','Native weapon display hidden flag unavailable')
        local known=false
        for _,entry in ipairs(self.hidden)do if same(entry.actor,actor)then known=true;break end end
        if not known and hidden==false then
            set_hidden(actor,kind,true)
            self.hidden[#self.hidden+1]={actor=actor,kind=kind}
        elseif known and hidden==false then
            -- Native switches can show their display actor again; only our own
            -- independently identified slot is suppressed on the next sample.
            set_hidden(actor,kind,true)
        end
    end
    if not inactive then self:clear_back();return end
    if valid(self.back)then return end
    local attachment=self.back_mount or native_back_mount(pawn.Mesh)
    local object=pawn:AddComponentByClass(StaticFindObject('/Script/Engine.StaticMeshComponent'),true,identity(),false)
    assert(valid(object),'Back sword component allocation failed')
    self.back=object
    assert(object:SetStaticMesh(self.load(self.sword)),'Back sword mesh assignment failed')
    object:SetCollisionEnabled(0)
    object:K2_AttachToComponent(pawn.Mesh,FName(attachment.bone),0,0,0,false)
    local q=attachment.q
    object:K2_SetRelativeTransform({Rotation={X=q[1],Y=q[2],Z=q[3],W=q[4]},Translation=vec(attachment.t),
        Scale3D=attachment.s and vec(attachment.s)or {X=1,Y=1,Z=1}},false,{},true)
    object:SetVisibility(true,false)
end
return M
