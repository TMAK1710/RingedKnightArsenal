#include "GuardContact.hpp"
#include <cassert>
#include <limits>
#include <iostream>
int main() {
    namespace C=RingedKnightGuardContact;
    const auto nan=std::numeric_limits<double>::quiet_NaN();
    const auto infinity=std::numeric_limits<double>::infinity();
    assert(C::frontal(-1,0,0,1,0));
    assert(C::frontal(-100,0,20,1,0));
    assert(C::frontal(0,-1,0,0,1));
    assert(C::frontal(-.501,.865447,0,1,0));
    assert(!C::frontal(1,0,0,1,0));
    assert(!C::frontal(0,1,0,1,0));
    assert(!C::frontal(-.499,.866602,0,1,0));
    assert(!C::frontal(0,0,-10,1,0));
    assert(!C::frontal(nan,0,0,1,0));
    assert(!C::frontal(-1,0,infinity,1,0));
    assert(!C::frontal(-1,0,0,nan,0));
    assert(C::can_pay(1)&&C::can_pay(100));
    assert(!C::can_pay(.999)&&!C::can_pay(0)&&!C::can_pay(nan)&&!C::can_pay(infinity));
    assert(C::debit_matches(10,9)&&C::debit_matches(1,0));
    assert(!C::debit_matches(10,10));
    assert(!C::debit_matches(10,8));
    assert(!C::debit_matches(0,-1));
    assert(!C::debit_matches(10,11));
    assert(!C::debit_matches(10,nan));
    std::cout<<"PASS guard travel-direction cone, native 1-point resource boundary, exact debit and invalid-number rejection\n";
}
