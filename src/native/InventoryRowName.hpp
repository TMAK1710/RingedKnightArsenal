#pragma once
#include <string_view>
namespace RingedKnightInventory {
// Input has already passed strict UTF-8 decoding. Preserve native translated
// row keys while rejecting ImportText delimiters and invisible controls.
inline bool valid_source_row_name(std::wstring_view value) {
    if(value.empty()||value.size()>96||value.find_first_of(L"\"'\\(),;=[]{}<>")!=std::wstring_view::npos)return false;
    for(const auto character:value) {
        const auto c=static_cast<unsigned int>(character);
        if(c<=0x20||(c>=0x7f&&c<=0x9f)||(c>=0x200b&&c<=0x200f)
            ||(c>=0x2028&&c<=0x202e)||(c>=0x2060&&c<=0x206f)||c==0xfeff)return false;
    }
    return true;
}
}
