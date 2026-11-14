#pragma once
// Compiled only by the real UE 5.7 editor module, never by the capsule bridge.
#include "UObject/Class.h"
#include <cstddef>
#include <type_traits>
namespace RKAUE57LayoutCheck {
using namespace UE::CoreUObject::Private;
static_assert(sizeof(void*) == 8);
static_assert(sizeof(FScriptArray) == 16 && alignof(FScriptArray) == 8);
static_assert(sizeof(TObjectPtr<UScriptStruct>) == 8);
static_assert(sizeof(FCapabilities) == 16 && alignof(FCapabilities) == 8);
static_assert(sizeof(FStructOpsFakeVTable) == 24 && alignof(FStructOpsFakeVTable) == 8);
static_assert(offsetof(FStructOpsFakeVTable, Flags) == 0);
static_assert(offsetof(FStructOpsFakeVTable, Capabilities) == 8);
static_assert(static_cast<uint32>(EStructOpsFakeVTableFlags::Copy) == (1u << 10));
static_assert(std::is_same_v<THandlingFunctionType<EStructOpsFakeVTableFlags::Copy>::Type,
                            bool(void*, const void*, int32)>);
}
