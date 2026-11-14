#pragma once
#include <cmath>
namespace RingedKnightGuardContact {
inline constexpr double cost=1.0;
// Incoming travel direction points opposite the player's forward vector.
// Require a horizontal direction and the existing open +/-60 degree cone.
inline bool frontal(double x,double y,double z,double forward_x,double forward_y) noexcept {
    const auto length=std::hypot(x,y);
    return std::isfinite(length)&&length>1e-6&&std::isfinite(z)
        &&std::isfinite(forward_x)&&std::isfinite(forward_y)
        &&(x*forward_x+y*forward_y)/length<-.5;
}
inline bool can_pay(double value) noexcept {return std::isfinite(value)&&value>=cost;}
inline bool debit_matches(double before,double after) noexcept {
    return can_pay(before)&&std::isfinite(after)&&after>=0&&after<=before&&std::abs((before-after)-cost)<.01;
}
}
