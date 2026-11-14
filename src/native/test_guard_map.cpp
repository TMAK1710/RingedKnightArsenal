#include "GuardMapMath.hpp"
#include <fstream>
#include <iostream>
#include <cassert>
int main(int argc,char** argv) {
    assert(argc==2);std::ifstream file(argv[1]);std::string input((std::istreambuf_iterator<char>(file)),{});assert(!input.empty());
    const auto result=RingedKnightGuard::scale(std::wstring(input.begin(),input.end()));
    assert(result.text.find(L"PhysicalDamage\"),0.000000")!=std::wstring::npos);
    assert(result.text.find(L"FireDamage\"),1.500000")!=std::wstring::npos);
    assert(result.stamina==18);
    const auto alias=RingedKnightGuard::scale(L"((Damage.Attack.Target.PhysicalDamage,100),(Damage.Attack.Target.FireDamage,100))");
    assert(alias.text.find(L"FireDamage\"),15.000000")!=std::wstring::npos);
    for(const auto* bad:{L"(((TagName=\"Damage.Attack.Target.FireDamage\"),NaN))",L"(((TagName=\"Damage.Attack.Target.PhysicalDamage\"),-50))",L"((UnknownStruct=(X=1,Y=2),100))",L"(((TagName=\"Damage.Attack.Target.FireDamage\"),100),UnrecognizedData)"}) {
        bool rejected=false;try{RingedKnightGuard::scale(bad);}catch(const std::exception&){rejected=true;}assert(rejected);
    }
    std::cout<<"PASS actual UE map format, physical/fire reduction, stability, tag alias and fail-open-to-native fallback inputs\n";
}
