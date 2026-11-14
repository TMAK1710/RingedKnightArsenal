#pragma once
#include <string>
#include <regex>
#include <cmath>
#include <stdexcept>
#include <algorithm>
namespace RingedKnightGuard {
struct ScaledMap {std::wstring text;double stamina;};
inline ScaledMap scale(const std::wstring& input) {
    const auto check=[](bool yes,const char* why){if(!yes)throw std::runtime_error(why);};
    check(!input.empty()&&input.size()<32768,"shield map text length");
    static const std::wregex pairs(LR"rk(\((?:\(TagName=)?"?([A-Za-z][A-Za-z0-9_.]+)"?\)?,\s*([+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\))rk");
    std::wstring output=L"(";unsigned count=0;double energy=-1,poise=-1;
    for(auto it=std::wsregex_iterator(input.begin(),input.end(),pairs);it!=std::wsregex_iterator();++it) {
        check(++count<=64,"shield map entry budget");const std::wstring tag=(*it)[1];
        const double value=std::stod((*it)[2]);check(std::isfinite(value)&&value>=0,"negative/healing value bypasses shield");
        double multiplier=1;
        if(tag.ends_with(L"PhysicalDamage"))multiplier=0;
        else if(tag.ends_with(L"FireDamage"))multiplier=.15;
        else if(tag.ends_with(L"MagicDamage"))multiplier=.35;
        else if(tag.ends_with(L"LightningDamage")||tag.ends_with(L"ThunderDamage"))multiplier=.48;
        else if(tag.ends_with(L"DarkDamage"))multiplier=.37;
        else if(tag.ends_with(L"PoiseDamage")||tag.ends_with(L"EnergyDamage"))multiplier=.4;
        if(tag.ends_with(L"EnergyDamage"))energy=value*.4;
        if(tag.ends_with(L"PoiseDamage"))poise=value*.4;
        if(count>1)output+=L",";
        output+=L"((TagName=\""+tag+L"\"),"+std::to_wstring(value*multiplier)+L")";
    }
    check(count>0,"shield map unrecognized");
    const auto remainder=std::regex_replace(input,pairs,std::wstring{});
    check(std::regex_match(remainder,std::wregex(LR"([\s(),]*)")),"shield map contains an unrecognized entry");
    return {output+L")",energy>=0?energy:std::max(0.,poise)};
}
}
