#include "SignatureNameLookup.hpp"
#include <array>
#include <cassert>
#include <iostream>
struct Field {std::wstring_view name,kind;};
int main() {
    namespace N=RingedKnightSignatureNames;
    const std::array actual{Field{L"SpecHandle",L"StructProperty"},Field{L"duration",L"FloatProperty"},Field{L"ReturnValue",L"StructProperty"}};
    const auto found=N::match(actual,L"Duration");assert(found.count==1&&found.index==1);
    assert(actual[found.index].kind==L"FloatProperty");
    assert(actual[found.index].kind!=L"DoubleProperty"); // Name normalization never coerces property types.
    assert(N::match(actual,L"DURATION").count==1);
    assert(N::match(actual,L"DurationSeconds").count==0);
    const std::array ambiguous{Field{L"Duration",L"FloatProperty"},Field{L"duration",L"FloatProperty"}};
    assert(N::match(ambiguous,L"Duration").count==2); // Even an exact-spelling candidate cannot hide ambiguity.
    assert(!N::equal(L"Duration",L"Durations"));
    assert(!N::equal(L"duration",L"ｄuration"));
    assert(N::equal(L"参数",L"参数"));
    std::cout<<"PASS actual lowercase duration, ASCII FName-equivalent lookup, missing names, ambiguity and strict property-type boundary\n";
}
