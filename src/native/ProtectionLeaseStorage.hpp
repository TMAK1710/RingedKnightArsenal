#pragma once
// Plain process-memory storage only. This header intentionally has no engine,
// UObject, reflection, Windows or thread-affinity API dependency.
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>
namespace RingedKnightProtection {
struct Lease {std::wstring pawn,asc;std::vector<std::wstring> handles;std::string token;std::uint64_t refreshed{};};
inline Lease action,block;
inline std::recursive_mutex lease_mutex;
// Safe for LuaStop, bridge destruction and rejected non-GT calls. Finite
// native specs expire themselves if ordinary GT cleanup did not already run.
inline void forget() noexcept {
    std::lock_guard lock(lease_mutex);action=Lease{};block=Lease{};
}
}
