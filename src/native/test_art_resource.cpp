#include "ArtResourcePolicy.hpp"
#include <cassert>
#include <limits>
#include <iostream>
int main() {
    namespace P=RingedKnightArtPolicy;
    assert(P::can_pay(1)&&P::can_pay(20)&&!P::can_pay(.9999));
    assert(!P::can_pay(std::numeric_limits<double>::quiet_NaN()));
    assert(!P::can_pay(std::numeric_limits<double>::infinity()));
    assert(P::matches(1,0)&&P::matches(5,4)&&!P::matches(5,3)&&!P::matches(5,5));
    assert(!P::valid_sequence(0)&&!P::valid_sequence(P::maximum_sequence+1));
    P::Session session;double stock=3;int reads=0,debits=0;
    auto read=[&]{++reads;return stock;};auto debit=[&]{++debits;stock-=1;};
    auto first=session.spend(1,"player",read,debit);
    assert(first.paid&&first.before==3&&first.after==2&&stock==2&&debits==1&&reads==2);
    auto replay=session.spend(1,"player",read,debit);
    assert(replay.paid&&replay.replayed&&stock==2&&debits==1&&reads==2);
    auto second=session.spend(2,"player",read,debit);assert(second.paid&&stock==1&&debits==2);
    bool rejected=false;try{session.spend(1,"player",read,debit);}catch(const std::runtime_error&){rejected=true;}
    assert(rejected&&debits==2);
    rejected=false;try{session.spend(3,"another_player",read,debit);}catch(const std::runtime_error&){rejected=true;}
    assert(rejected&&debits==2);
    session.spend(3,"player",read,debit);assert(stock==0&&debits==3);
    auto insufficient=session.spend(4,"player",read,debit);assert(!insufficient.paid&&insufficient.status=="insufficient"&&debits==3);
    stock=5;assert(session.spend(4,"player",read,debit).paid&&stock==4&&debits==4);
    assert(session.spend(5,"player",read,debit).paid&&stock==3);
    P::Session failure;stock=3;debits=0;
    auto unknown=failure.spend(1,"player",read,[&]{--stock;++debits;throw std::runtime_error("dispatch interrupted");});
    assert(!unknown.paid&&unknown.dispatched&&unknown.status=="uncertain"&&stock==2&&debits==1);
    auto unknown_replay=failure.spend(1,"player",read,debit);assert(unknown_replay.replayed&&stock==2&&debits==1);
    P::Session mismatched;stock=3;
    auto mismatch=mismatched.spend(1,"player",read,[&]{stock-=2;++debits;});
    assert(!mismatch.paid&&mismatch.status=="debit_mismatch"&&stock==1);
    P::Session badread;bool readfailed=false;
    try{badread.spend(1,"player",[]{return -1.;},debit);}catch(const std::runtime_error&){readfailed=true;}
    assert(readfailed);
    std::cout<<"PASS fixed1 UltimateChargeCount payment, exact readback, full-action idempotence, stale/owner rejection, insufficient and uncertain no-retry\n";
}
