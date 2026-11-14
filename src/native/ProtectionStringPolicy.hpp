#pragma once
#include <string>
#include <string_view>
namespace RingedKnightProtectionStrings {
// ImportText_Direct with PortFlags=0 copies FString input verbatim. Do not
// supply export-text quotes around a plain path (UE StrProperty.cpp.inl).
inline std::wstring plain_fstring_input(std::wstring_view path) {return std::wstring(path);}
inline bool path_roundtrip(std::wstring_view requested,std::wstring_view imported) noexcept {
    return !requested.empty()&&requested.front()==L'/'&&requested.find(L'"')==std::wstring_view::npos
        &&requested==imported;
}
}
