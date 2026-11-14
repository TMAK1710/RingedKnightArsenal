#include "HitPacketMath.hpp"
#include "../../references/pbz-mc/third_party/nlohmann-json-3.11.3/json.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <limits>
int main(int argc,char** argv) {
    namespace P=RingedKnightHitPacket;
    assert(argc==3);std::ifstream file(argv[1]);const auto profile=nlohmann::json::parse(file);
    assert(P::valid("sword",1,.1,1012.5,1,.05)); // Previously disabled every first contact.
    assert(P::valid("sword",1,.1,900,1,.05)); // Latest user-selected first-light posture.
    assert(P::valid("sword",1,.1,900,1,.05,0)); // Omitted optional field preserves the old packet.
    for(const double regen:{0.0,.3137255,.42857143,.5714286,.6862745,1.0})
        assert(P::valid("sword",1,.1,900,1,.05,regen));
    for(const double regen:{-1.0,1000.1,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()})
        assert(!P::valid("sword",1,.1,900,1,.05,regen));
    assert(P::ultimate_charge_entry(0).empty());
    assert(P::ultimate_charge_entry(1)==L",((TagName=\"Damage.Attack.Attacker.UltimateChargeRegen\"),1)");
    assert(P::ultimate_charge_entry(.42857143)==L",((TagName=\"Damage.Attack.Attacker.UltimateChargeRegen\"),0.42857143)");
    unsigned contacts{};
    for(const auto& clip:profile.at("clips"))for(const auto& hit:clip.value("hits",nlohmann::json::array())){
        assert(P::valid("sword",1,.1,hit.value("poise",0.0),1,.05,hit.value("ultimate_charge_regen",0.0)));++contacts;
    }
    assert(contacts>0);
    assert(P::valid("sword",1,.1,540,.8,.05));
    const auto& bomb=profile.at("bomb");
    assert(P::valid("explosion",0,1,bomb.value("poise",0.0),bomb.value("anger",0.0),bomb.value("hit_anger_multiplier",.05)));
    assert(P::valid("explosion",0,1,50,1.2,1));
    assert(P::valid("explosion",0,1,P::maximum_poise,1.2,1));
    assert(!P::valid("explosion",0,1,P::maximum_poise+1,1.2,1));
    for(const auto kind:{"arrow","fire","fall","fly_into_wall"}) {
        assert(P::valid(kind,1,.1,0,0,.05));
        assert(!P::valid(kind,1,.1,50,0,.05));
    }
    assert(!P::valid("sword",1,.1,-1,1,.05));
    assert(!P::valid("sword",1,.1,P::maximum_poise+1,1,.05));
    assert(!P::valid("sword",1,.1,100,-1,.05));
    assert(!P::valid("sword",0,0,100,1,.05));
    assert(!P::valid("sword",1,.1,std::numeric_limits<double>::infinity(),1,.05));
    assert(!P::valid("sword",1,.1,100,1,std::numeric_limits<double>::quiet_NaN()));
    int dispatched=0;
    auto dispatch=[&](std::string_view kind){if(!P::valid(kind,0,1,50,1.2,1))return false;++dispatched;return true;};
    assert(!dispatch("unknown")&&dispatched==0);
    assert(dispatch("explosion")&&dispatched==1);
    std::ifstream input(argv[2]);assert(input);const std::string source((std::istreambuf_iterator<char>(input)),{});
    const auto checked=source.find("RingedKnightHitPacket::valid(kind,");
    const auto kind_checked=source.find("RingedKnightHitPacket::known_kind(kind)");
    const auto mutation=source.find("auto* pawn=object(data,\"pawn\")");
    assert(checked!=std::string::npos&&kind_checked!=std::string::npos&&mutation!=std::string::npos);
    assert(checked<mutation&&kind_checked<mutation);
    const auto count=[&](const std::string& needle){size_t total=0,at=0;while((at=source.find(needle,at))!=std::string::npos){++total;at+=needle.size();}return total;};
    assert(source.find("data.value(\"ultimate_charge_regen\",0.0)")<mutation);
    assert(count("ultimate_charge_entry(ultimate_charge_regen)")==1);
    const auto damage_begin=source.find("if(phase==\"damage\") {");
    const auto feedback_begin=source.find("} else {",damage_begin);
    assert(damage_begin!=std::string::npos&&feedback_begin!=std::string::npos);
    const auto damage_path=source.substr(damage_begin,feedback_begin-damage_begin);
    const std::string dispatch_call="component->ProcessEvent(signature.function,frame.data())";
    const auto dispatch_at=damage_path.find(dispatch_call);
    assert(dispatch_at!=std::string::npos&&damage_path.find(dispatch_call,dispatch_at+1)==std::string::npos);
    assert(source.find("ModifyCharacterAttributeValue")==std::string::npos);
    assert(source.find("SetNumericAttributeBase")==std::string::npos);
    assert(source.find("ultimate_charge_diagnostics\",false")!=std::string::npos);
    std::cout<<"PASS sword/current-profile and explosion50 packets; unchanged numeric/kind limits; optional authored attacker charge weights, legacy zero default, one damage dispatch and read-only diagnostics\n";
}
