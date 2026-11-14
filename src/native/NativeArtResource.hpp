#pragma once
#include "ArtResourcePolicy.hpp"
namespace RingedKnightArtResource {
using Json=nlohmann::json;
inline std::uint64_t session_counter{};
inline std::map<std::uint64_t,RingedKnightArtPolicy::Session> sessions;
inline std::unique_ptr<Signature> read_signature,modify_signature,valid_signature,player_signature;
inline void schemas() {
    if(read_signature)return;
    constexpr std::array read_params{ExpectedParameter{L"Actor",L"ObjectProperty"},ExpectedParameter{L"Attribute",L"StructProperty"},
        ExpectedParameter{L"bSuccessfullyFoundAttribute",L"BoolProperty"},ExpectedParameter{L"ReturnValue",L"FloatProperty"}};
    constexpr std::array valid_params{ExpectedParameter{L"Attribute",L"StructProperty"},ExpectedParameter{L"ReturnValue",L"BoolProperty"}};
    constexpr std::array modify_params{ExpectedParameter{L"Character",L"ObjectProperty"},ExpectedParameter{L"Attribute",L"StructProperty"},
        ExpectedParameter{L"ModiferOp",L"ByteProperty"},ExpectedParameter{L"Value",L"FloatProperty"}};
    constexpr std::array player_params{ExpectedParameter{L"WorldContextObject",L"ObjectProperty"},ExpectedParameter{L"PlayerIndex",L"IntProperty"},
        ExpectedParameter{L"ReturnValue",L"ObjectProperty"}};
    auto read=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:GetFloatAttribute",read_params));
    auto valid=std::make_unique<Signature>(inspect_signature(L"/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:IsValid",valid_params));
    auto modify=std::make_unique<Signature>(inspect_signature(L"/Script/SGameAttributes.AttributeUtils:ModifyCharacterAttributeValue",modify_params));
    auto player=std::make_unique<Signature>(inspect_signature(L"/Script/Engine.GameplayStatics:GetPlayerCharacter",player_params));
    require(read->at(L"Attribute").property->SameType(modify->at(L"Attribute").property)
        &&read->at(L"Attribute").property->SameType(valid->at(L"Attribute").property),"art resource GameplayAttribute types differ");
    require(modify->size==72&&modify->at(L"Character").offset==0&&modify->at(L"Attribute").offset==8
        &&modify->at(L"ModiferOp").offset==64&&modify->at(L"Value").offset==68,"art resource modification ABI changed");
    const auto* field=class_property(L"/Script/CharacterBasics.BasicAttributeSet",L"UltimateChargeCount");
    require(property_kind(field)==L"StructProperty"&&const_cast<FField*>(reinterpret_cast<const FField*>(field))->GetFullName()
        ==L"StructProperty /Script/CharacterBasics.BasicAttributeSet:UltimateChargeCount","art UltimateChargeCount field schema changed");
    valid_signature=std::move(valid);modify_signature=std::move(modify);player_signature=std::move(player);read_signature=std::move(read);
}
inline void attribute_value(const Signature& signature,ParameterFrame& frame,UObject* pawn) {
    constexpr wchar_t text[]=L"(AttributeName=\"UltimateChargeCount\",Attribute=/Script/CharacterBasics.BasicAttributeSet:UltimateChargeCount,AttributeOwner=/Script/CharacterBasics.BasicAttributeSet)";
    const auto& attribute=signature.at(L"Attribute");
    const auto* end=attribute.property->ImportText_Direct(text,frame.address(attribute),pawn,0,nullptr);
    require(end&&*end==0,"art UltimateChargeCount GameplayAttribute import failed");
    ParameterFrame validation(*valid_signature);
    valid_signature->at(L"Attribute").property->CopyCompleteValue(validation.address(valid_signature->at(L"Attribute")),frame.address(attribute));
    find_object(L"/Script/GameplayAbilities.Default__AbilitySystemBlueprintLibrary")->ProcessEvent(valid_signature->function,validation.data());
    const auto& result=valid_signature->at(L"ReturnValue");
    require(reinterpret_cast<FBoolProperty*>(const_cast<FProperty*>(result.property))->GetPropertyValue(validation.address(result)),
        "art UltimateChargeCount GameplayAttribute did not resolve");
}
inline void verify_player(UObject* pawn) {
    ParameterFrame frame(*player_signature);
    std::memcpy(frame.address(player_signature->at(L"WorldContextObject")),&pawn,sizeof(pawn));
    const std::int32_t index=0;std::memcpy(frame.address(player_signature->at(L"PlayerIndex")),&index,sizeof(index));
    find_object(L"/Script/Engine.Default__GameplayStatics")->ProcessEvent(player_signature->function,frame.data());
    UObject* current{};std::memcpy(&current,frame.address(player_signature->at(L"ReturnValue")),sizeof(current));
    require(current==pawn,"art resource target is not the current local player character");
}
inline double read_for(UObject* pawn) {
    ParameterFrame frame(*read_signature);attribute_value(*read_signature,frame,pawn);
    std::memcpy(frame.address(read_signature->at(L"Actor")),&pawn,sizeof(pawn));
    find_object(L"/Script/GameplayAbilities.Default__AbilitySystemBlueprintLibrary")->ProcessEvent(read_signature->function,frame.data());
    const auto& found=read_signature->at(L"bSuccessfullyFoundAttribute");
    require(reinterpret_cast<FBoolProperty*>(const_cast<FProperty*>(found.property))->GetPropertyValue(frame.address(found)),
        "art UltimateChargeCount attribute unavailable");
    float value{};std::memcpy(&value,frame.address(read_signature->at(L"ReturnValue")),sizeof(value));
    require(std::isfinite(value)&&value>=0,"art UltimateChargeCount value invalid");return value;
}
inline void prepare_debit(UObject* pawn,ParameterFrame& frame) {
    attribute_value(*modify_signature,frame,pawn);
    std::memcpy(frame.address(modify_signature->at(L"Character")),&pawn,sizeof(pawn));
    const std::uint8_t additive=0;const float cost=-1;
    std::memcpy(frame.address(modify_signature->at(L"ModiferOp")),&additive,sizeof(additive));
    std::memcpy(frame.address(modify_signature->at(L"Value")),&cost,sizeof(cost));
}
inline std::string run(const std::string& input) {
    require(IsInGameThread()&&input.size()<=4096,"art resource requires bounded game-thread JSON");
    const auto data=Json::parse(input);require(data.is_object(),"art resource request schema");schemas();
    const auto phase=data.at("phase").get<std::string>();
    if(phase=="capabilities") {
        require(session_counter<RingedKnightArtPolicy::maximum_sequence,"art resource session limit");
        const auto token=++session_counter;sessions.emplace(token,RingedKnightArtPolicy::Session{});
        // Expired sessions fail closed instead of losing their high-water mark
        // and becoming chargeable again. Normal operation retains one session.
        while(sessions.size()>64)sessions.erase(sessions.begin());
        return Json{{"api",1},{"resource","UltimateChargeCount"},{"amount",1},{"once_per_action",true},{"session_token",token},
            {"native_modifier","AttributeUtils.ModifyCharacterAttributeValue.Additive"}}.dump();
    }
    require(phase=="spend"&&!data.contains("amount"),"art resource phase/fixed cost");
    require(data.at("session_token").is_number_unsigned()||data.at("session_token").is_number_integer(),"art resource session type");
    require(data.at("sequence").is_number_unsigned()||data.at("sequence").is_number_integer(),"art resource sequence type");
    const auto token=data.at("session_token").get<std::uint64_t>(),sequence=data.at("sequence").get<std::uint64_t>();
    auto session=sessions.find(token);require(session!=sessions.end()&&RingedKnightArtPolicy::valid_sequence(sequence),"art resource unknown session/action");
    auto* pawn=RingedKnightHit::object(data,"pawn");verify_player(pawn);
    // All fallible frame/schema construction is before the committed boundary.
    // Only the actual native modifier invocation is passed into the ledger.
    ParameterFrame debit_frame(*modify_signature);prepare_debit(pawn,debit_frame);
    auto* modifier=find_object(L"/Script/SGameAttributes.Default__AttributeUtils");
    const auto receipt=session->second.spend(sequence,data.at("pawn").get<std::string>(),[&]{return read_for(pawn);},
        [&]{modifier->ProcessEvent(modify_signature->function,debit_frame.data());});
    return Json{{"api",1},{"resource","UltimateChargeCount"},{"amount",1},{"session_token",token},{"sequence",sequence},
        {"paid",receipt.paid},{"status",receipt.status},{"before",receipt.before},{"after",receipt.after},
        {"dispatched",receipt.dispatched},{"committed",receipt.dispatched},{"replayed",receipt.replayed},{"error",receipt.error}}.dump();
}
inline int lua_spend(const Lua& lua) {
    try {require(lua.get_stack_size()==1&&lua.is_string(1),"usage: RK_ArtResource(json)");lua.set_string(run(std::string(lua.get_string(1))));lua.set_nil();}
    catch(const std::exception& error){lua.set_nil();lua.set_string(std::string("RK art resource: ")+error.what());}return 2;
}
}
