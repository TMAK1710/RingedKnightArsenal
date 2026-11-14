#pragma once
// Engine queries own their parameter arrays until every result has been copied
// to JSON. No Lua RemoteUnrealParam/LocalUnrealParam escapes this boundary.
namespace RingedKnightQuery {
using Json=nlohmann::json;
using namespace RingedKnightInventory;
inline constexpr wchar_t system_path[]=L"/Script/Engine.Default__KismetSystemLibrary";
inline const Signature& trace_schema() {
    static const auto result=[] {
        constexpr std::array<ExpectedParameter,14> expected{{
            {L"WorldContextObject",L"ObjectProperty"},{L"Start",L"StructProperty"},{L"End",L"StructProperty"},
            {L"Radius",L"FloatProperty"},{L"TraceChannel",L"ByteProperty"},{L"bTraceComplex",L"BoolProperty"},
            {L"ActorsToIgnore",L"ArrayProperty"},{L"DrawDebugType",L"ByteProperty"},{L"OutHits",L"ArrayProperty"},
            {L"bIgnoreSelf",L"BoolProperty"},{L"TraceColor",L"StructProperty"},{L"TraceHitColor",L"StructProperty"},
            {L"DrawTime",L"FloatProperty"},{L"ReturnValue",L"BoolProperty"}}};
        return inspect_signature(L"/Script/Engine.KismetSystemLibrary:SphereTraceMulti",expected);
    }();return result;
}
inline const Signature& overlap_schema() {
    static const auto result=[] {
        constexpr std::array<ExpectedParameter,8> expected{{
            {L"WorldContextObject",L"ObjectProperty"},{L"SpherePos",L"StructProperty"},{L"SphereRadius",L"FloatProperty"},
            {L"ObjectTypes",L"ArrayProperty"},{L"ActorClassFilter",L"ClassProperty"},
            {L"ActorsToIgnore",L"ArrayProperty"},{L"OutActors",L"ArrayProperty"},{L"ReturnValue",L"BoolProperty"}}};
        return inspect_signature(L"/Script/Engine.KismetSystemLibrary:SphereOverlapActors",expected);
    }();return result;
}
inline const FProperty* array_inner(const Parameter& parameter,std::wstring_view kind) {
    require(parameter.kind==L"ArrayProperty"&&parameter.size==sizeof(ArrayView),"query array descriptor ABI changed");
    const auto* inner=reinterpret_cast<const FArrayProperty*>(parameter.property)->GetInner();
    require(inner&&property_kind(inner)==kind&&inner->GetArrayDim()==1&&inner->GetSize()>0&&inner->GetSize()<=4096,
        "query array element schema changed");
    const auto alignment=inner->GetMinAlignment();
    require(alignment>0&&alignment<=4096&&(alignment&(alignment-1))==0,"query array element alignment changed");
    if(kind==L"ObjectProperty")require(inner->GetSize()==sizeof(UObject*),"query object array element size changed");
    return inner;
}
inline ArrayView array_view(const Parameter& parameter,const ParameterFrame& frame,const FProperty* inner) {
    // Reuse the descriptor ABI independently asserted by the UE5.7 editor
    // module and already used by NativeWeaponConfig. Element size/alignment
    // are always taken from the LIVE FArrayProperty, never a HitResult offset.
    ArrayView view{};std::memcpy(&view,frame.address(parameter),sizeof(view));
    require(view.count>=0&&view.count<=1024&&view.capacity>=view.count&&view.capacity<=4096,"query result array bounds");
    if(view.count) {
        require(view.data&&reinterpret_cast<std::uintptr_t>(view.data)%inner->GetMinAlignment()==0,"query result array alignment");
        readable(view.data,static_cast<std::size_t>(view.count)*inner->GetSize());
    }
    return view;
}
inline std::string object_path(UObject* object) {
    if(!object||object->IsUnreachable())return {};
    const auto name=object->GetFullName();const auto space=name.find(L' ');
    require(space!=std::wstring::npos&&space+1<name.size(),"query object has no full path");
    return metadata_utf8(name.substr(space+1));
}
inline bool is_a(UObject* object,const wchar_t* class_path) {
    if(!object||object->IsUnreachable())return false;
    using NativeIsA=bool(*)(const UObject*,const UClass*);
    static auto native=exported<NativeIsA>("?IsA@UObjectBase@Unreal@RC@@QEBA_NPEBVUClass@23@@Z");
    auto* type=find_object(class_path);
    require(type->GetFullName()==std::wstring(L"Class ")+class_path,"query class metadata changed");
    return native(object,reinterpret_cast<const UClass*>(type));
}
inline UObject* weak_value(const FProperty* field,void* container,std::size_t size) {
    require(property_kind(field)==L"WeakObjectProperty"&&field->GetSize()==8,"query hit weak reference schema changed");
    return reinterpret_cast<const FWeakObjectPtr*>(value_address(field,container,size))->Get();
}
inline Json hit_result(void* hit,const FProperty* inner) {
    auto* type=find_object(L"/Script/Engine.HitResult");verify_struct_property(inner,type);
    const auto* structure=reinterpret_cast<const UStruct*>(type);const auto size=structure->GetStructureSize();
    require(size==inner->GetSize(),"query HitResult stride changed");
    auto read_vector=[&](std::wstring_view name,const wchar_t* expected) {
        const auto* field=field_named(structure,name);auto* schema=find_object(expected);verify_struct_property(field,schema);
        const auto* vector_schema=reinterpret_cast<const UStruct*>(schema);auto* address=value_address(field,hit,size);
        Json value;for(const auto* axis:{L"X",L"Y",L"Z"}) {
            const auto* member=field_named(vector_schema,axis,true);
            require(property_kind(member)==L"DoubleProperty"&&member->GetSize()==sizeof(double),"query hit vector component schema");
            double component{};std::memcpy(&component,value_address(member,address,field->GetSize()),sizeof(component));
            require(std::isfinite(component)&&std::abs(component)<1e9,"query hit vector range");value[metadata_utf8(axis)]=component;
        }return value;
    };
    auto point=read_vector(L"ImpactPoint",L"/Script/Engine.Vector_NetQuantize");
    auto normal=read_vector(L"ImpactNormal",L"/Script/Engine.Vector_NetQuantizeNormal");
    const auto* handle=field_named(structure,L"HitObjectHandle");
    auto* handle_type=find_object(L"/Script/Engine.ActorInstanceHandle");verify_struct_property(handle,handle_type);
    const auto* reference=field_named(reinterpret_cast<const UStruct*>(handle_type),L"ReferenceObject");
    auto* object=weak_value(reference,value_address(handle,hit,size),handle->GetSize());
    UObject* actor{};
    if(is_a(object,L"/Script/Engine.Actor"))actor=object;
    else if(is_a(object,L"/Script/Engine.ActorComponent"))actor=RingedKnightHit::owner(object);
    if(!actor) {
        const auto* component=field_named(structure,L"Component");auto* value=weak_value(component,hit,size);
        if(is_a(value,L"/Script/Engine.ActorComponent"))actor=RingedKnightHit::owner(value);
    }
    // Copy the engine's bitfield values before the parameter frame is destroyed.
    // Overlaps and initial penetration are not a grounded projectile contact.
    const auto flag=[&](std::wstring_view name) {
        const auto* field=field_named(structure,name);
        require(property_kind(field)==L"BoolProperty","query hit flag schema changed");
        auto* boolean=reinterpret_cast<FBoolProperty*>(const_cast<FProperty*>(field));
        return boolean->GetPropertyValue(value_address(field,hit,size));
    };
    return Json{{"target",object_path(actor)},{"point",std::move(point)},{"normal",std::move(normal)},
        {"blocking",flag(L"bBlockingHit")},{"start_penetrating",flag(L"bStartPenetrating")}};
}
inline void import(const Parameter& field,ParameterFrame& frame,UObject* context,const std::wstring& value) {
    require(field.property->ImportText_Direct(value.c_str(),frame.address(field),context,0,nullptr)!=nullptr,"query parameter import failed");
}
inline std::wstring ignored(const Json& data) {
    const auto& ignore=data.at("ignore");require(ignore.is_array()&&ignore.size()<=128,"query ignore list bounds");
    std::wstring value=L"(";bool first=true;
    for(const auto& item:ignore) {
        require(item.is_string(),"query ignore requires object paths");const auto path=from_utf8(item.get<std::string>());
        require(path.size()<=2048&&path.find_first_of(L"\"'\r\n")==std::wstring::npos,"query ignored object path invalid");
        auto* object=find_object(path.c_str());require(is_a(object,L"/Script/Engine.Actor"),"query ignored object is not Actor");
        if(!first)value+=L",";first=false;value+=L"Object'"+path+L"'";
    }
    return value+L")";
}
inline void vector_input(const Json& data,const char* key,const Parameter& parameter,ParameterFrame& frame,UObject* context) {
    verify_struct_property(parameter.property,find_object(L"/Script/CoreUObject.Vector"));
    const auto value=RingedKnightHit::vector(data,key);
    import(parameter,frame,context,L"(X="+std::to_wstring(value.x)+L",Y="+std::to_wstring(value.y)+L",Z="+std::to_wstring(value.z)+L")");
}
inline constexpr std::size_t max_trace_batch=64;
inline Json trace_batch(const Json& data,UObject* context) {
    const auto& segments=data.at("segments");
    require(segments.is_array()&&!segments.empty()&&segments.size()<=max_trace_batch,"query batch segment count bounds");
    const auto& signature=trace_schema();
    const auto* inner=array_inner(signature.at(L"OutHits"),L"StructProperty");
    verify_struct_property(inner,find_object(L"/Script/Engine.HitResult"));
    array_inner(signature.at(L"ActorsToIgnore"),L"ObjectProperty");
    auto* library=find_object(system_path);
    std::vector<std::unique_ptr<ParameterFrame>> frames;frames.reserve(segments.size());
    {
        // Resolve/import the shared ignore list once. The engine deep-copies
        // each frame's array; no parameter-array ownership crosses frames.
        ParameterFrame common(signature);
        import(signature.at(L"WorldContextObject"),common,context,L"Object'"+from_utf8(data.at("pawn").get<std::string>())+L"'");
        import(signature.at(L"ActorsToIgnore"),common,context,ignored(data));
        import(signature.at(L"TraceChannel"),common,context,L"0");
        import(signature.at(L"bTraceComplex"),common,context,L"False");
        import(signature.at(L"DrawDebugType"),common,context,L"0");
        import(signature.at(L"bIgnoreSelf"),common,context,L"True");
        // All JSON checks and reflected imports finish before the first
        // ProcessEvent. A malformed final segment cannot execute a partial batch.
        for(const auto& segment:segments) {
            require(segment.is_object(),"query batch segment must be object");
            const double radius=segment.at("radius").get<double>();
            require(std::isfinite(radius)&&radius>0&&radius<=1000,"query radius bounds");
            auto frame=std::make_unique<ParameterFrame>(signature);
            for(const auto* name:{L"WorldContextObject",L"ActorsToIgnore",L"TraceChannel",L"bTraceComplex",L"DrawDebugType",L"bIgnoreSelf"}) {
                const auto& field=signature.at(name);field.property->CopyCompleteValue(frame->address(field),common.address(field));
            }
            vector_input(segment,"start",signature.at(L"Start"),*frame,context);
            vector_input(segment,"finish",signature.at(L"End"),*frame,context);
            import(signature.at(L"Radius"),*frame,context,std::to_wstring(radius));
            frames.push_back(std::move(frame));
        }
    }
    Json results=Json::array();
    for(auto& frame:frames) {
        library->ProcessEvent(signature.function,frame->data());
        const auto view=array_view(signature.at(L"OutHits"),*frame,inner);Json hits=Json::array();
        for(std::int32_t i=0;i<view.count;++i)hits.push_back(hit_result(static_cast<std::byte*>(view.data)+i*inner->GetSize(),inner));
        results.push_back(Json{{"hits",std::move(hits)}});
        frame.reset(); // Snapshot ownership is now entirely in the JSON result.
    }
    return results;
}
inline std::string run(const std::string& input) {
    require(IsInGameThread()&&input.size()<=32768,"query requires bounded game-thread JSON");
    const auto data=Json::parse(input);const auto phase=data.at("phase").get<std::string>();
    if(phase=="capabilities") {
        const auto& trace=trace_schema();const auto& overlap=overlap_schema();
        const auto* inner=array_inner(trace.at(L"OutHits"),L"StructProperty");
        auto* type=find_object(L"/Script/Engine.HitResult");verify_struct_property(inner,type);
        const auto* structure=reinterpret_cast<const UStruct*>(type);
        for (const auto* name : {L"bBlockingHit",L"bStartPenetrating"})
            require(property_kind(field_named(structure,name))==L"BoolProperty","query hit flag schema changed");
        array_inner(trace.at(L"ActorsToIgnore"),L"ObjectProperty");array_inner(overlap.at(L"OutActors"),L"ObjectProperty");
        array_inner(overlap.at(L"ActorsToIgnore"),L"ObjectProperty");array_inner(overlap.at(L"ObjectTypes"),L"ByteProperty");
        return Json{{"api",1},{"owned_parameter_frames",true},{"trace",true},{"overlap",true},
            {"blocking_hit_flags",true},{"trace_batch",true},{"max_batch",max_trace_batch},{"runtime_queries_executed",false}}.dump();
    }
    require(phase=="trace"||phase=="overlap"||phase=="trace_batch","query phase unsupported");
    auto* context=RingedKnightHit::object(data,"pawn");require(is_a(context,L"/Script/Engine.Actor"),"query world context must be Actor");
    if(phase=="trace_batch") {
        Json result={{"api",1},{"phase",phase},{"owned_parameter_frames",true},{"results",trace_batch(data,context)}};
        const auto output=result.dump();require(output.size()<=output_limit,"query result too large");return output;
    }
    const double radius=data.at("radius").get<double>();require(std::isfinite(radius)&&radius>0&&radius<=1000,"query radius bounds");
    const auto& signature=phase=="trace"?trace_schema():overlap_schema();ParameterFrame frame(signature);
    auto* library=find_object(system_path);
    import(signature.at(L"WorldContextObject"),frame,context,L"Object'"+from_utf8(data.at("pawn").get<std::string>())+L"'");
    array_inner(signature.at(L"ActorsToIgnore"),L"ObjectProperty");import(signature.at(L"ActorsToIgnore"),frame,context,ignored(data));
    Json result={{"api",1},{"phase",phase},{"owned_parameter_frames",true}};
    if(phase=="trace") {
        vector_input(data,"start",signature.at(L"Start"),frame,context);vector_input(data,"finish",signature.at(L"End"),frame,context);
        import(signature.at(L"Radius"),frame,context,std::to_wstring(radius));
        import(signature.at(L"TraceChannel"),frame,context,L"0");import(signature.at(L"bTraceComplex"),frame,context,L"False");
        import(signature.at(L"DrawDebugType"),frame,context,L"0");import(signature.at(L"bIgnoreSelf"),frame,context,L"True");
        const auto* inner=array_inner(signature.at(L"OutHits"),L"StructProperty");verify_struct_property(inner,find_object(L"/Script/Engine.HitResult"));
        library->ProcessEvent(signature.function,frame.data());
        const auto view=array_view(signature.at(L"OutHits"),frame,inner);result["hits"]=Json::array();
        for(std::int32_t i=0;i<view.count;++i)result["hits"].push_back(hit_result(static_cast<std::byte*>(view.data)+i*inner->GetSize(),inner));
    }else {
        vector_input(data,"center",signature.at(L"SpherePos"),frame,context);import(signature.at(L"SphereRadius"),frame,context,std::to_wstring(radius));
        array_inner(signature.at(L"ObjectTypes"),L"ByteProperty");std::wstring types=L"(";
        for(int i=0;i<32;++i){if(i)types+=L",";types+=std::to_wstring(i);}types+=L")";import(signature.at(L"ObjectTypes"),frame,context,types);
        import(signature.at(L"ActorClassFilter"),frame,context,L"Class'/Script/ProjectPBZ.PBZCharacter'");
        const auto* inner=array_inner(signature.at(L"OutActors"),L"ObjectProperty");
        library->ProcessEvent(signature.function,frame.data());
        const auto view=array_view(signature.at(L"OutActors"),frame,inner);result["actors"]=Json::array();
        for(std::int32_t i=0;i<view.count;++i) {
            auto* actor=reinterpret_cast<const FObjectPropertyBase*>(inner)->GetObjectPropertyValue(static_cast<std::byte*>(view.data)+i*inner->GetSize());
            require(!actor||is_a(actor,L"/Script/ProjectPBZ.PBZCharacter"),"query overlap actor filter mismatch");
            const auto name=object_path(actor);if(!name.empty())result["actors"].push_back(name);
        }
    }
    const auto output=result.dump();require(output.size()<=output_limit,"query result too large");return output;
}
inline int lua_query(const Lua& lua) {
    try {require(lua.get_stack_size()==1&&lua.is_string(1),"usage: RK_NativeQuery(json)");lua.set_string(run(std::string(lua.get_string(1))));lua.set_nil();}
    catch(const std::exception& error){lua.set_nil();lua.set_string(std::string("RK native query: ")+error.what());}return 2;
}
}
