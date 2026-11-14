#pragma once

#include <cstdint>
#include <string>

// Declaration-only ABI capsules, NOT Unreal object layout definitions.
// Never instantiate, sizeof, delete, or access data members on these classes.
// Signatures are checked against the pinned UE4SS.dll export table by the
// linker. See ABI.md for source call sites and the remaining runtime limits.
namespace RC::Unreal {
class UClass;
class UFunction;
class FField;
class FOutputDevice;
class FString;
struct FieldAccess;
class FName {
    FName() = delete;
    ~FName() = delete;
public:
    __declspec(dllimport) const std::wstring ToString() const;
};

class UObject {
    UObject() = delete;
    ~UObject() = delete;
public:
    __declspec(dllimport) void ProcessEvent(UFunction*, void*);
    __declspec(dllimport) std::wstring GetFullName(UObject* stop_outer = nullptr) const;
    __declspec(dllimport) bool IsUnreachable();
    __declspec(dllimport) bool IsRootSet();
};

class FWeakObjectPtr {
    FWeakObjectPtr() = delete;
    ~FWeakObjectPtr() = delete;
public:
    __declspec(dllimport) UObject* Get() const;
};

class UStruct {
    UStruct() = delete;
    ~UStruct() = delete;
public:
    __declspec(dllimport) const FField*& GetChildProperties() const;
    __declspec(dllimport) const UStruct*& GetSuperStruct() const;
    __declspec(dllimport) const std::int32_t& GetPropertiesSize() const;
    __declspec(dllimport) std::int32_t GetStructureSize() const;
    __declspec(dllimport) const std::int16_t& GetMinAlignment() const;
    __declspec(dllimport) void InitializeStruct(void*, std::int32_t) const;
    __declspec(dllimport) void DestroyStruct(void*, std::int32_t) const;
};

namespace UE::CoreUObject::Private { struct FStructOpsFakeVTable; }
class UScriptStruct {
    UScriptStruct() = delete;
    ~UScriptStruct() = delete;
public:
    struct ICppStructOps {
        ICppStructOps() = delete;
        ~ICppStructOps() = delete;
        __declspec(dllimport) const UE::CoreUObject::Private::FStructOpsFakeVTable*& GetFakeVPtr() const;
        __declspec(dllimport) const std::int32_t& GetSize() const;
        __declspec(dllimport) const std::int32_t& GetAlignment() const;
    };
    __declspec(dllimport) const ICppStructOps*& GetCppStructOps() const;
};
class FMemory {
    FMemory() = delete;
    ~FMemory() = delete;
public:
    __declspec(dllimport) static void* Malloc(std::size_t, std::uint32_t);
    __declspec(dllimport) static void Free(void*);
};

class UFunction {
    UFunction() = delete;
    ~UFunction() = delete;
public:
    __declspec(dllimport) const std::uint16_t& GetParmsSize() const;
    __declspec(dllimport) const std::uint8_t& GetNumParms() const;
    __declspec(dllimport) const std::uint16_t& GetReturnValueOffset() const;
};

class FField {
    FField() = delete;
    ~FField() = delete;
    friend struct FieldAccess;
    // Access qualification is part of the MSVC mangled symbol.
    __declspec(dllimport) const FField*& GetNext() const;
public:
    __declspec(dllimport) std::wstring GetName() const;
    __declspec(dllimport) std::wstring GetFullName();
};

struct FieldAccess {
    static const FField* next(const FField* field) { return field->GetNext(); }
};

class FProperty {
    FProperty() = delete;
    ~FProperty() = delete;
public:
    __declspec(dllimport) const std::int32_t& GetOffset_Internal() const;
    __declspec(dllimport) const std::int32_t& GetArrayDim() const;
    __declspec(dllimport) std::int32_t GetSize() const;
    __declspec(dllimport) std::int32_t GetMinAlignment() const;
    __declspec(dllimport) void InitializeValue(void*) const;
    __declspec(dllimport) void DestroyValue(void*) const;
    __declspec(dllimport) void CopyCompleteValue(void*, const void*) const;
    __declspec(dllimport) bool SameType(const FProperty*) const;
    __declspec(dllimport) const wchar_t* ImportText_Direct(const wchar_t*, void*, UObject*, std::int32_t, FOutputDevice*) const;
    __declspec(dllimport) bool ExportText_Direct(FString&, const void*, const void*, UObject*, std::int32_t, UObject*);
};

class FArrayProperty {
    FArrayProperty() = delete;
    ~FArrayProperty() = delete;
public:
    __declspec(dllimport) const FProperty*& GetInner() const;
};

// Opaque property metadata view only. The bridge compares the eight-byte
// resolved object handle with a separately looked-up fixed schema; unresolved
// handles are rejected rather than interpreted as an address.
template<typename T> class TObjectPtr;
class FStructProperty {
    FStructProperty() = delete;
    ~FStructProperty() = delete;
public:
    __declspec(dllimport) const TObjectPtr<UScriptStruct>& GetStruct() const;
};

class FBoolProperty {
    FBoolProperty() = delete;
    ~FBoolProperty() = delete;
public:
    __declspec(dllimport) bool GetPropertyValue(const void*);
};

class FObjectPropertyBase {
    FObjectPropertyBase() = delete;
    ~FObjectPropertyBase() = delete;
public:
    __declspec(dllimport) UObject* GetObjectPropertyValue(const void*) const;
};

template<typename Character> class TStringBase {
    TStringBase() = delete;
    ~TStringBase() = delete;
public:
    __declspec(dllimport) TStringBase& Append(const Character*);
    __declspec(dllimport) const Character* operator*() const;
    __declspec(dllimport) std::int32_t Len() const;
};

namespace UObjectGlobals {
    __declspec(dllimport) UObject* StaticFindObject_InternalSlow(UClass*, UObject*, const wchar_t*, bool);
}
class FUObjectHashTables {
    FUObjectHashTables() = delete;
    ~FUObjectHashTables() = delete;
public:
    // Pinned upstream GUI/Profilers.cpp uses the same four arguments; true
    // selects native hash lookup, with package/outer parsing of the full path.
    __declspec(dllimport) static UObject* StaticFindObjectByPath(UClass*, const wchar_t*, bool, bool);
};
__declspec(dllimport) bool IsInGameThread();
} // namespace RC::Unreal
