-- UIHelper consumes FlowLocText.Key through native MakeTextByKey, not ValueCache.
-- Normal registration uses loader startup. A diagnostic game-thread reload
-- requires the pinned loader's successful same-runtime hook canary.
-- Pinned UE4SS native post-hook parameters: context, original return, inputs.
local M={};M.__index=M
local PATH='/Script/ProjectPBZ.PBZBlueprintFunctionLibrary:MakeTextByKey'
-- Declaring owner and both parameters were captured from the real game in
-- reports/runtime-pickup-ui.json; this is not an inferred function path.
local CONV_PATH='/Script/ProjectPBZ.EventPipelineManager:Conv_LocTextToText'
local PREFIX='RKA_'
local function unwrap(value)
    if type(value)=='userdata'then
        local parameter_type=value:type()
        -- The pinned loader wraps StructProperty GetParam as LocalUnrealParam.
        if parameter_type=='RemoteUnrealParam'or parameter_type=='LocalUnrealParam'then return value:get()end
    elseif type(value)=='table'and type(value.get)=='function'then return value:get()end
    return value
end
local function key_string(value)
    value=unwrap(value)
    if type(value)=='string'then return value end
    local ok,result=pcall(function()return value:ToString()end)
    return ok and type(result)=='string' and result or nil
end
local function inspect_schema()
    local fn=StaticFindObject(PATH)
    assert(fn and fn:IsValid()==true and fn:GetFullName()=='Function '..PATH,'Native MakeTextByKey UFunction unavailable')
    local result={path=PATH,fields={},input_count=0,text_return_count=0,verified=false}
    fn:ForEachProperty(function(property)
        local full=property:GetFullName()
        local kind,name=full:match('^(%S+) .+:([^:]+)$')
        result.fields[#result.fields+1]={path=full,type=kind,name=name}
        if name=='ReturnValue'then
            assert(kind=='TextProperty','MakeTextByKey return is no longer FText')
            result.text_return_count=result.text_return_count+1
        else
            assert(kind=='StrProperty' or kind=='NameProperty','MakeTextByKey input schema changed: '..full)
            result.input_count=result.input_count+1
            result.input_type=kind;result.input_name=name
        end
    end)
    assert(result.input_count==1 and result.text_return_count==1 and #result.fields==2,
        'MakeTextByKey must have exactly one string/name input and one FText return')
    result.verified=true
    return result
end
local function valid(value)return value and value:IsValid()==true end
local function find_function(class,name)
    for _=1,32 do
        if not valid(class)then return nil end
        local found
        class:ForEachFunction(function(fn)
            if fn:GetFName():ToString()==name then assert(not found,'Ambiguous reflected function '..name);found=fn end
        end)
        if found then return found end
        class=class:GetSuperStruct()
    end
    error('Reflected widget superclass chain exceeds 32 entries')
end
local function setter_schema(fn,expected)
    assert(valid(fn),'Reflected '..expected..' UFunction missing')
    local full=fn:GetFullName();local path=assert(full:match('^Function (.+)$'),'Widget function is not UFunction')
    assert(path:match(':([^:]+)$')==expected,'Reflected widget function name mismatch')
    local result={path=path,fields={},input_count=0,return_count=0}
    fn:ForEachProperty(function(property)
        local full_name=property:GetFullName();local kind,name=full_name:match('^(%S+) .+:([^:]+)$')
        assert(kind and name,'Malformed widget UFunction property')
        result.fields[#result.fields+1]={path=full_name,type=kind,name=name}
        if name=='ReturnValue'then
            assert(expected=='SetTextByLocKey' and kind=='BoolProperty','Unsupported widget setter return schema')
            result.return_count=result.return_count+1
        else
            if expected=='SetText'or expected=='SetPBZFormatText'then assert(kind=='TextProperty','Text setter input is no longer FText')
            else assert(kind=='StrProperty' or kind=='NameProperty','Loc-key setter input is not string/name')end
            result.input_count=result.input_count+1;result.input_type=kind;result.input_name=name
        end
    end)
    assert(result.input_count==1 and result.return_count<=1 and #result.fields==1+result.return_count,
        'Widget setter must have exactly one supported input')
    assert((expected~='SetText'and expected~='SetPBZFormatText')or result.return_count==0,'Text setter must return void')
    result.verified=true;return result
end
function M:register_widget_hook(generation)
    assert(type(FindObject)=='function','Native UClass finder unavailable for optional loc-key widget hook')
    -- Resolve the actual loaded UClass by its asset-proven short name, then
    -- discover declaring function owners through reflection. No owner path is
    -- guessed, and an unexpected optional schema cannot block the item system.
    local class=FindObject('Class','PBZCommonLocText')
    assert(valid(class) and class:GetFName():ToString()=='PBZCommonLocText','Actual PBZCommonLocText UClass unavailable')
    local schema={class=class:GetFullName(),key=setter_schema(find_function(class,'SetTextByLocKey'),'SetTextByLocKey'),
        set_text=setter_schema(find_function(class,'SetText'),'SetText'),verified=true}
    local format_fn=find_function(class,'SetPBZFormatText')
    if valid(format_fn)then schema.format_text=setter_schema(format_fn,'SetPBZFormatText')end
    local pre,post=RegisterHook(schema.key.path,function()return nil end,function(context,...)
        if not self.active or generation~=self.generation then return nil end
        self.widget_calls=self.widget_calls+1
        -- Native void post-hooks receive (context, inputs); functions with a
        -- return insert that original return after context (pinned LuaMod.cpp).
        local key=key_string(select(schema.key.return_count==1 and 2 or 1,...))
        if not key or key:sub(1,#PREFIX)~=PREFIX then return nil end
        local source=self.lookup(key)
        if source==nil then return nil end
        if type(source)~='string'then self.widget_error='Own widget text lookup did not return UTF8';return nil end
        local widget=unwrap(context)
        if not valid(widget)then self.widget_error='Loc-key hook context is not a valid widget';return nil end
        local cached=self.cache[key]
        if not cached or cached.source~=source then cached={source=source,value=FText(source)};self.cache[key]=cached end
        -- PBZCommonLocText has a native formatting/display path beyond the
        -- inherited TextBlock text. Its actual one-FText setter is preferred;
        -- raw SetText alone was observed leaving real attribute labels blank.
        local ok,why=pcall(function()
            if schema.format_text then widget:SetPBZFormatText(cached.value)else widget:SetText(cached.value)end
        end)
        if ok then self.widget_hits=self.widget_hits+1 else self.widget_error=tostring(why)end
        return nil -- Preserve any native setter return value.
    end)
    assert(type(pre)=='number' and type(post)=='number','Widget localization hook IDs unavailable')
    self.widget_hook={name=schema.key.path,pre=pre,post=post};return schema
end
function M:register_flow_hook(generation)
    local fn=StaticFindObject(CONV_PATH)
    assert(valid(fn)and fn:GetFullName()=='Function '..CONV_PATH,'Actual FlowLocText converter UFunction unavailable')
    local schema={path=CONV_PATH,fields={},struct_inputs=0,text_returns=0}
    fn:ForEachProperty(function(property)
        local full=property:GetFullName();local kind,name=full:match('^(%S+) .+:([^:]+)$')
        schema.fields[#schema.fields+1]={path=full,type=kind,name=name}
        if name=='InLocText'then assert(kind=='StructProperty','Converter input is no longer a struct');schema.struct_inputs=schema.struct_inputs+1
        elseif name=='ReturnValue'then assert(kind=='TextProperty','Converter return is no longer FText');schema.text_returns=schema.text_returns+1
        else error('Unexpected converter parameter '..full)end
    end)
    assert(#schema.fields==2 and schema.struct_inputs==1 and schema.text_returns==1,'Converter schema changed')
    schema.verified=true
    local pre,post=RegisterHook(CONV_PATH,function()return nil end,function(context,original_return,loc_parameter)
        if not self.active or generation~=self.generation then return nil end
        self.flow_calls=self.flow_calls+1
        local field=unwrap(loc_parameter)
        if field==nil then return nil end
        -- InLocText is valid only for this callback. Extract the scalar key
        -- immediately; never retain the native struct or inspect maps/arrays.
        local key=key_string(field.Key)
        if not key or key:sub(1,#PREFIX)~=PREFIX then return nil end
        local source=self.lookup(key)
        if source==nil then return nil end
        assert(type(source)=='string','Owned FlowLocText lookup must return UTF8 or nil')
        local cached=self.cache[key]
        if not cached or cached.source~=source then cached={source=source,value=FText(source)};self.cache[key]=cached end
        self.flow_hits=self.flow_hits+1;return cached.value
    end)
    assert(type(pre)=='number'and type(post)=='number','Converter localization hook IDs unavailable')
    self.flow_hook={name=CONV_PATH,pre=pre,post=post};return schema
end
function M.new(lookup)
    assert(type(lookup)=='function','Localization requires lookup(key) returning own UTF8 source text or nil')
    return setmetatable({lookup=lookup,active=false,generation=0,cache={},hits=0,widget_hits=0,widget_calls=0,flow_hits=0,flow_calls=0},M)
end
function M:register()
    if self.active and self.hook then return self.schema end
    assert(type(RegisterHook)=='function' and type(UnregisterHook)=='function',
        'Native localization hook APIs are unavailable')
    self.schema=inspect_schema()
    self.generation=self.generation+1
    local generation=self.generation
    local pre,post=RegisterHook(PATH,function()
        -- The native lookup still runs; post selectively replaces its result.
        return nil
    end,function(context,original_return,key_parameter)
        if not self.active or generation~=self.generation then return nil end
        local key=key_string(key_parameter)
        if not key or key:sub(1,#PREFIX)~=PREFIX then return nil end
        local source=self.lookup(key)
        if source==nil then return nil end
        assert(type(source)=='string','Own localization lookup must return UTF8 source text or nil')
        local cached=self.cache[key]
        if not cached or cached.source~=source then
            cached={source=source,value=FText(source)};self.cache[key]=cached
        end
        self.hits=self.hits+1
        return cached.value -- UE4SS TextProperty handler writes the FText return.
    end)
    assert(type(pre)=='number' and type(post)=='number','Native localization hook IDs unavailable')
    self.hook={name=PATH,pre=pre,post=post}
    self.active=true
    local widget_ok,widget_result=pcall(self.register_widget_hook,self,generation)
    if widget_ok then self.widget_schema=widget_result;self.schema.widget=widget_result;self.widget_error=nil
    else self.widget_schema=nil;self.widget_error=tostring(widget_result);self.schema.widget={verified=false,error=self.widget_error}end
    local flow_ok,flow_result=pcall(self.register_flow_hook,self,generation)
    if flow_ok then self.flow_schema=flow_result;self.schema.flow=flow_result;self.flow_error=nil
    else self.flow_schema=nil;self.flow_error=tostring(flow_result);self.schema.flow={verified=false,error=self.flow_error}end
    return self.schema -- Caller can serialize the REAL validated schema report.
end
function M:dispose()
    -- Invalidate callbacks before unregistering; UE4SS removal may be deferred.
    self.active=false;self.generation=self.generation+1;self.cache={}
    local hooks={};if self.hook then hooks[#hooks+1]=self.hook end;if self.widget_hook then hooks[#hooks+1]=self.widget_hook end;if self.flow_hook then hooks[#hooks+1]=self.flow_hook end
    self.hook=nil;self.widget_hook=nil;self.widget_schema=nil;self.flow_hook=nil;self.flow_schema=nil
    local failures={}
    for _,hook in ipairs(hooks)do
        local ok,why=pcall(UnregisterHook,hook.name,hook.pre,hook.post)
        if not ok then failures[#failures+1]=tostring(why)end
    end
    assert(#failures==0,table.concat(failures,'; '))
    return {active=false,unregistered=#hooks>0,unregistered_count=#hooks}
end
M.hook_path=PATH
M.key_prefix=PREFIX
return M
