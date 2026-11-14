-- Mod-owned IDs and definitions. Registration never replaces an existing ID.
local M={};M.__index=M
function M.new()return setmetatable({entries={},order={}},M)end
function M:add(definition)
    assert(type(definition)=='table' and type(definition.id)=='string' and definition.id:match('^RKA_[A-Za-z0-9_]+$'),'Invalid independent weapon ID')
    assert(not self.entries[definition.id],'Duplicate independent weapon ID: '..definition.id)
    assert(type(definition.name)=='string' and type(definition.base_item)=='string','Incomplete weapon definition')
    self.entries[definition.id]=definition;self.order[#self.order+1]=definition.id;return definition
end
function M:get(id)return self.entries[id]end
return M
