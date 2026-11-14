#pragma once
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
namespace RingedKnightArtPolicy {
inline constexpr double amount=1;
inline constexpr std::uint64_t maximum_sequence=9007199254740991ull;
inline bool valid_sequence(std::uint64_t value){return value>0&&value<=maximum_sequence;}
inline bool can_pay(double value){return std::isfinite(value)&&value>=amount;}
inline bool matches(double before,double after){return can_pay(before)&&std::isfinite(after)&&after>=0&&std::abs(before-after-amount)<.0001;}
struct Receipt {
    bool paid{},dispatched{},replayed{};
    double before{},after{};
    std::string status="unattempted",error;
};
// One high-water mark per activation session. A stale request can never become
// chargeable again even after its previous receipt is replaced.
class Session {
    std::uint64_t latest{};
    std::string pawn;
    Receipt receipt;
public:
    template<class Read,class Debit> Receipt spend(std::uint64_t sequence,const std::string& owner,Read read,Debit debit) {
        if(!valid_sequence(sequence)||owner.empty())throw std::runtime_error("art resource invalid action identity");
        if(!pawn.empty()&&pawn!=owner)throw std::runtime_error("art resource session owner changed");
        if(sequence<latest)throw std::runtime_error("art resource stale action identity");
        if(sequence==latest){auto copy=receipt;copy.replayed=true;return copy;}
        const double before=read();
        if(!std::isfinite(before)||before<0)throw std::runtime_error("art resource invalid current value");
        // Insufficient stock does not consume an identity: the same buffered
        // action may be retried after native stock is restored.
        if(!can_pay(before)){Receipt insufficient;insufficient.before=before;insufficient.after=before;insufficient.status="insufficient";return insufficient;}
        // Reserve before dispatch; failure/readback uncertainty is never retried
        // or refunded automatically, preserving external native mutations.
        pawn=owner;latest=sequence;receipt={};receipt.before=before;receipt.after=before;
        receipt.status="uncertain";receipt.dispatched=true;
        try {
            debit();receipt.after=read();
            receipt.paid=matches(before,receipt.after);
            receipt.status=receipt.paid?"paid":"debit_mismatch";
        }catch(const std::exception& error){receipt.error=error.what();}
        return receipt;
    }
};
}
