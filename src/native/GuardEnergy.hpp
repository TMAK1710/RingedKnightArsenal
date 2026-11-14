// Included within ShieldGate; all access uses verified reflection/UE4SS APIs.
// GE_ShieldShaqiCost and GE_Chaos_SwitchShaQiCost both identify native killing
// energy as CharacterBasics.BasicAttributeSet.Shachi (not an Energy field).
// No raw GameplayAttribute layout or HP rollback.
namespace Energy {
inline constexpr double contact_cost=RingedKnightGuardContact::cost;
inline std::unique_ptr<Signature> read_signature,modify_signature,valid_signature;
inline UObject* component_bound{};
inline UObject* pawn_bound{};
inline std::wstring component_name,pawn_name;
inline constexpr char attribute_path[]="/Script/CharacterBasics.BasicAttributeSet:Shachi";
inline std::atomic<double> spent{},last_before{},last_after{};

inline UObject* component_owner(UObject* component) {
    constexpr std::array expected{ExpectedParameter{L"ReturnValue",L"ObjectProperty"}};
    const auto signature=inspect_signature(L"/Script/Engine.ActorComponent:GetOwner",expected);
    ParameterFrame frame(signature);component->ProcessEvent(signature.function,frame.data());
    UObject* pawn{};std::memcpy(&pawn,frame.address(signature.at(L"ReturnValue")),sizeof(pawn));
    require(pawn&&!pawn->IsUnreachable(),"shield resource pawn unavailable");return pawn;
}
inline void schemas() {
    if(read_signature)return;
    constexpr std::array read_params{ExpectedParameter{L"Actor",L"ObjectProperty"},ExpectedParameter{L"Attribute",L"StructProperty"},
        ExpectedParameter{L"bSuccessfullyFoundAttribute",L"BoolProperty"},ExpectedParameter{L"ReturnValue",L"FloatProperty"}};
    constexpr std::array valid_params{ExpectedParameter{L"Attribute",L"StructProperty"},ExpectedParameter{L"ReturnValue",L"BoolProperty"}};
    constexpr std::array modify_params{ExpectedParameter{L"Character",L"ObjectProperty"},ExpectedParameter{L"Attribute",L"StructProperty"},
        ExpectedParameter{L"ModiferOp",L"ByteProperty"},ExpectedParameter{L"Value",L"FloatProperty"}};
    auto read=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:GetFloatAttribute",read_params));
    auto valid=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:IsValid",valid_params));
    auto modify=std::make_unique<Signature>(inspect_signature(L"/Script/SGameAttributes.AttributeUtils:ModifyCharacterAttributeValue",modify_params));
    require(read->at(L"Attribute").property->SameType(modify->at(L"Attribute").property)
        &&read->at(L"Attribute").property->SameType(valid->at(L"Attribute").property),"shield resource GameplayAttribute types differ");
    require(modify->size==72&&modify->at(L"Character").offset==0&&modify->at(L"Attribute").offset==8
        &&modify->at(L"ModiferOp").offset==64&&modify->at(L"Value").offset==68,"shield resource modification ABI changed");
    read_signature=std::move(read);valid_signature=std::move(valid);modify_signature=std::move(modify);
}
inline void attribute_value(const Signature& signature,ParameterFrame& frame,UObject* pawn) {
    constexpr wchar_t text[]=L"(AttributeName=\"Shachi\",Attribute=/Script/CharacterBasics.BasicAttributeSet:Shachi,AttributeOwner=/Script/CharacterBasics.BasicAttributeSet)";
    const auto& attribute=signature.at(L"Attribute");
    const auto* end=attribute.property->ImportText_Direct(text,frame.address(attribute),pawn,0,nullptr);
    require(end&&*end==L'\0',"shield Shachi GameplayAttribute import failed");
    ParameterFrame validation(*valid_signature);
    valid_signature->at(L"Attribute").property->CopyCompleteValue(validation.address(valid_signature->at(L"Attribute")),frame.address(attribute));
    find_object(L"/Script/GameplayAbilities.Default__AbilitySystemBlueprintLibrary")->ProcessEvent(valid_signature->function,validation.data());
    const auto& result=valid_signature->at(L"ReturnValue");
    require(reinterpret_cast<FBoolProperty*>(const_cast<FProperty*>(result.property))->GetPropertyValue(validation.address(result)),
        "shield Shachi GameplayAttribute did not resolve");
}
inline double read_for(UObject* pawn) {
    ParameterFrame frame(*read_signature);attribute_value(*read_signature,frame,pawn);
    std::memcpy(frame.address(read_signature->at(L"Actor")),&pawn,sizeof(pawn));
    auto* library=find_object(L"/Script/GameplayAbilities.Default__AbilitySystemBlueprintLibrary");
    library->ProcessEvent(read_signature->function,frame.data());
    const auto& found=read_signature->at(L"bSuccessfullyFoundAttribute");
    require(reinterpret_cast<FBoolProperty*>(const_cast<FProperty*>(found.property))->GetPropertyValue(frame.address(found)),
        "shield Shachi is not owned by the player's ability system");
    float value{};std::memcpy(&value,frame.address(read_signature->at(L"ReturnValue")),sizeof(value));
    require(std::isfinite(value)&&value>=0,"shield Shachi value invalid");return value;
}
inline double read() {
    require(pawn_bound&&!pawn_bound->IsUnreachable()&&pawn_bound->GetFullName()==pawn_name,"shield resource pawn retired");
    return read_for(pawn_bound);
}
inline void bind(UObject* component) {
    if(component==component_bound&&component->GetFullName()==component_name)return;
    schemas();auto* pawn=component_owner(component);
    const auto* shachi=class_property(L"/Script/CharacterBasics.BasicAttributeSet",L"Shachi");
    require(property_kind(shachi)==L"StructProperty"&&const_cast<FField*>(reinterpret_cast<const FField*>(shachi))->GetFullName()
        ==L"StructProperty /Script/CharacterBasics.BasicAttributeSet:Shachi","shield Shachi field schema changed");
    read_for(pawn); // Read-only validity/ownership/value preflight, before publishing binding.
    component_bound=component;component_name=component->GetFullName();pawn_bound=pawn;pawn_name=pawn->GetFullName();
}
inline bool debit() {
    const auto before=read();last_before=before;last_after=before;
    if(!RingedKnightGuardContact::can_pay(before))return false;
    // Engine-owned parameter values are local to this game-thread call. No
    // global ParameterFrame destructor runs after engine UObject teardown.
    ParameterFrame frame(*modify_signature);attribute_value(*modify_signature,frame,pawn_bound);
    std::memcpy(frame.address(modify_signature->at(L"Character")),&pawn_bound,sizeof(pawn_bound));
    // UE EGameplayModOp::Additive is zero; this is a current-value delta,
    // dispatched through PBZ's own ASC/delegates rather than a raw field write.
    const std::uint8_t additive=0;const float cost=-static_cast<float>(contact_cost);
    std::memcpy(frame.address(modify_signature->at(L"ModiferOp")),&additive,sizeof(additive));
    std::memcpy(frame.address(modify_signature->at(L"Value")),&cost,sizeof(cost));
    find_object(L"/Script/SGameAttributes.Default__AttributeUtils")->ProcessEvent(modify_signature->function,frame.data());
    const auto after=read();last_after=after;
    require(RingedKnightGuardContact::debit_matches(before,after),"shield native Shachi debit did not match 1 point");
    spent.fetch_add(before-after);return true;
}
}
