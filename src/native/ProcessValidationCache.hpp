#pragma once
#include <exception>
#include <mutex>
#include <utility>
namespace RingedKnightProcessValidation {
// One process-local result, including failure. A failed first validation is
// never retried as a high-frequency I/O loop and never becomes a successful
// result without restarting the process and performing validation again.
template<typename T> class OnceResult {
    std::once_flag once;
    T value{};
    std::exception_ptr error;
public:
    template<typename Producer> const T& get(Producer&& producer) {
        std::call_once(once,[&]{try{value=std::forward<Producer>(producer)();}catch(...){error=std::current_exception();}});
        if(error)std::rethrow_exception(error);
        return value;
    }
};
}
