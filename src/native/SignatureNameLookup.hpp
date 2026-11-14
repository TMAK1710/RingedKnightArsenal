#pragma once
#include <cstddef>
#include <string_view>
namespace RingedKnightSignatureNames {
// Native FName display spelling can reuse a case variant (the actual host
// reports SetDuration.duration, although its UHT descriptor says Duration).
// Native parameter identifiers are ASCII; preserve exact non-ASCII spelling.
inline constexpr wchar_t fold_ascii(wchar_t value) noexcept {
    return value>=L'A'&&value<=L'Z'?static_cast<wchar_t>(value+(L'a'-L'A')):value;
}
inline bool equal(std::wstring_view a,std::wstring_view b) noexcept {
    if(a.size()!=b.size())return false;
    for(std::size_t i=0;i<a.size();++i)if(fold_ascii(a[i])!=fold_ascii(b[i]))return false;
    return true;
}
struct Match {std::size_t index{},count{};};
template<typename Parameters> inline Match match(const Parameters& parameters,std::wstring_view name) noexcept {
    Match result;
    for(std::size_t i=0;i<parameters.size();++i)if(equal(parameters[i].name,name)) {
        if(!result.count)result.index=i;++result.count;
    }
    return result;
}
}
