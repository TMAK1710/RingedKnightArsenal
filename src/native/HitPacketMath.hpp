#pragma once
#include <cmath>
#include <array>
#include <charconv>
#include <stdexcept>
#include <string>
#include <string_view>
namespace RingedKnightHitPacket {
inline constexpr double maximum_poise=1000000.0;
inline bool coefficient(double value) noexcept {return std::isfinite(value)&&value>=0&&value<=1000;}
inline bool poise(double value) noexcept {return std::isfinite(value)&&value>=0&&value<=maximum_poise;}
inline bool known_kind(std::string_view kind) noexcept {
    return kind=="sword"||kind=="arrow"||kind=="explosion"||kind=="fire"||kind=="fall"||kind=="fly_into_wall";
}
inline bool valid(std::string_view kind,double physical,double fire,double posture,double anger,double hit_anger,
    double ultimate_charge_regen=0) noexcept {
    // Original explosion packets can contain posture damage (the rope bomb
    // uses50). Keep every other kind's prior zero-posture restriction intact.
    return known_kind(kind)&&(kind=="sword"||kind=="explosion"||posture==0)
        &&coefficient(physical)&&coefficient(fire)&&physical+fire>0&&poise(posture)
        &&coefficient(anger)&&coefficient(hit_anger)&&coefficient(ultimate_charge_regen);
}
inline std::wstring ultimate_charge_entry(double value) {
    if(value==0)return {};
    // Retain authored fractional contact weights rather than rounding them to
    // std::to_wstring's six decimals before UE imports the native float map.
    std::array<char,64> buffer{};
    const auto result=std::to_chars(buffer.data(),buffer.data()+buffer.size(),value,std::chars_format::general);
    if(result.ec!=std::errc{})throw std::runtime_error("Ultimate charge coefficient formatting failed");
    return L",((TagName=\"Damage.Attack.Attacker.UltimateChargeRegen\"),"
        +std::wstring(buffer.data(),result.ptr)+L")";
}
}
