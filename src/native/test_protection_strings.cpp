#include "ProtectionStringPolicy.hpp"
#include <array>
#include <cassert>
#include <fstream>
#include <iostream>
int main(int argc,char** argv) {
    namespace P=RingedKnightProtectionStrings;
    assert(argc==2);
    for(const auto* path:{L"/PBZCombatAsset/Prototypes/GameplayEffects/GE_IgnoreHit.GE_IgnoreHit_C",
                          L"/PBZCombatAsset/Prototypes/GameplayEffects/GE_IgnoreBreak.GE_IgnoreBreak_C"}) {
        const auto input=P::plain_fstring_input(path);assert(input==path);
        // Engine non-delimited FString import copies input verbatim.
        const auto stored=input;assert(P::path_roundtrip(path,stored));
        const auto old_quoted=L"\""+input+L"\"";
        assert(!P::path_roundtrip(path,old_quoted));
        assert(!P::path_roundtrip(old_quoted,old_quoted));
        assert(!P::path_roundtrip(path,L""));
    }
    assert(!P::path_roundtrip(L"",L""));
    std::ifstream file(argv[1]);assert(file);const std::string source((std::istreambuf_iterator<char>(file)),{});
    const auto check=source.find("RingedKnightProtectionStrings::path_roundtrip(path,imported_input)");
    const auto make=source.find("system->ProcessEvent(make_path->function");
    assert(check!=std::string::npos&&make!=std::string::npos&&check<make);
    assert(source.find("; actual=")!=std::string::npos&&source.find("; imported_PathString=")!=std::string::npos);
    std::cout<<"PASS raw FString path roundtrip before any load, old quoted-path rejection and requested/actual diagnostics\n";
}
