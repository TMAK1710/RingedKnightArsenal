// Adapted from fjdsjd/pbz-mc, PolyForm Noncommercial 1.0.0.
// Required Notice: Copyright (c) 2026 桃天帝不差
// Required Notice: 黑神话：史蒂夫 — 作者 / B站：桃天帝不差
#pragma once
#include "SignatureNameLookup.hpp"
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

std::wstring from_utf8(std::string_view text) {
    require(!text.empty() && text.size() <= input_limit, "input must contain 1..65536 UTF-8 bytes");
    require(text.find('\0') == std::string_view::npos, "embedded NUL is not supported");
    const auto length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0);
    require(length > 0, "input is not valid UTF-8");
    std::wstring result(length, L'\0');
    require(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), result.data(), length) == length,
            "UTF-8 conversion failed");
    return result;
}

std::string native_diagnostic_text(std::wstring_view text) {
    if(text.empty())return "<unnamed>";
    const auto size=WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
    if(size<=0)return "<unprintable>";
    std::string result(size,'\0');
    if(WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),result.data(),size,nullptr,nullptr)!=size)return "<unprintable>";
    return result;
}

class Sha256 {
    BCRYPT_ALG_HANDLE algorithm_{};
    BCRYPT_HASH_HANDLE hash_{};
public:
    Sha256() {
        require(BCryptOpenAlgorithmProvider(&algorithm_, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0, "cannot open SHA256 provider");
        if (BCryptCreateHash(algorithm_, &hash_, nullptr, 0, nullptr, 0, 0) < 0) {
            BCryptCloseAlgorithmProvider(algorithm_, 0);
            algorithm_ = nullptr;
            throw std::runtime_error("cannot create SHA256 state");
        }
    }
    ~Sha256() {
        if (hash_) BCryptDestroyHash(hash_);
        if (algorithm_) BCryptCloseAlgorithmProvider(algorithm_, 0);
    }
    void update(unsigned char* data, ULONG size) { require(BCryptHashData(hash_, data, size, 0) >= 0, "SHA256 update failed"); }
    std::array<unsigned char, 32> finish() {
        std::array<unsigned char, 32> hash{};
        require(BCryptFinishHash(hash_, hash.data(), static_cast<ULONG>(hash.size()), 0) >= 0, "SHA256 finalization failed");
        return hash;
    }
};

UObject* find_object(const wchar_t* path) {
    auto* object = FUObjectHashTables::StaticFindObjectByPath(nullptr, path, false, true);
    if(!object)throw std::runtime_error("required native object is not loaded: "+native_diagnostic_text(path));
    const auto name = object->GetFullName();
    require(name.ends_with(path), "native object lookup returned an unexpected path");
    return object;
}

struct Parameter {
    const FProperty* property{};
    std::wstring name;
    std::wstring kind;
    std::size_t offset{};
    std::size_t size{};
    std::size_t alignment{};
};

struct Signature {
    UFunction* function{};
    std::size_t size{};
    std::size_t alignment{alignof(std::max_align_t)};
    std::vector<Parameter> parameters;
    std::wstring function_path;

    const Parameter& at(std::wstring_view name) const {
        const auto matched=RingedKnightSignatureNames::match(parameters,name);
        if(matched.count!=1) {
            std::string message=std::string(matched.count?"ambiguous native parameter name: function=":"required native parameter is absent: function=")+native_diagnostic_text(function_path)
                +"; parameter="+native_diagnostic_text(name)+"; actual=[";
            for(std::size_t index=0;index<parameters.size();++index) {
                if(index)message+=", ";
                message+=native_diagnostic_text(parameters[index].name)+":"+native_diagnostic_text(parameters[index].kind);
            }
            throw std::runtime_error(message+"]");
        }
        return parameters[matched.index];
    }
};

struct ExpectedParameter {
    std::wstring_view name;
    std::wstring_view kind;
};
Signature inspect_signature(const wchar_t* path, std::span<const ExpectedParameter> expected) {
    auto* object = find_object(path);
    require(object->GetFullName() == std::wstring(L"Function ") + path, "native method does not match its fixed UFunction path");
    Signature result{reinterpret_cast<UFunction*>(object)};
    result.function_path=path;
    result.size = result.function->GetParmsSize();
    require(result.size > 0 && result.size <= 65535 && result.function->GetNumParms() == expected.size(),
            "unexpected JSON UFunction parameter shape");
    const auto* structure = reinterpret_cast<const UStruct*>(object);
    auto* field = structure->GetChildProperties();
    std::vector<const FField*> seen;
    while (field) {
        require(seen.size() < 16 && std::find(seen.begin(), seen.end(), field) == seen.end(), "cyclic or unexpected native property chain");
        seen.push_back(field);
        auto* property = reinterpret_cast<const FProperty*>(field);
        const auto name = field->GetName();
        const auto full_name = const_cast<FField*>(field)->GetFullName();
        const auto type_end = full_name.find(L' ');
        require(type_end != std::wstring::npos, "native property type cannot be identified");
        const auto kind = full_name.substr(0, type_end);
        const auto offset = property->GetOffset_Internal();
        const auto size = property->GetSize();
        const auto alignment = property->GetMinAlignment();
        require(property->GetArrayDim() == 1 && offset >= 0 && size > 0 && alignment > 0 && alignment <= 4096 &&
                (alignment & (alignment - 1)) == 0, "unsupported native property extent or alignment");
        require(static_cast<std::size_t>(offset) + static_cast<std::size_t>(size) <= result.size && offset % alignment == 0,
                "native parameter is outside its reflected buffer or misaligned");
        for (const auto& other : result.parameters) {
            if(RingedKnightSignatureNames::equal(name,other.name))throw std::runtime_error("ambiguous native parameter names: function="
                +native_diagnostic_text(path)+"; first="+native_diagnostic_text(other.name)+"; second="+native_diagnostic_text(name));
            require(static_cast<std::size_t>(offset + size) <= other.offset || other.offset + other.size <= static_cast<std::size_t>(offset),
                    "overlapping native parameters are unsupported");
        }
        result.parameters.push_back({property, name, kind, static_cast<std::size_t>(offset), static_cast<std::size_t>(size), static_cast<std::size_t>(alignment)});
        result.alignment = std::max(result.alignment, static_cast<std::size_t>(alignment));
        field = FieldAccess::next(field);
    }
    require(result.parameters.size() == expected.size(), "native UFunction parameters differ from its fixed signature");
    for(std::size_t index=0;index<expected.size();++index)for(std::size_t other=0;other<index;++other)
        if(RingedKnightSignatureNames::equal(expected[index].name,expected[other].name))throw std::runtime_error("ambiguous expected native parameter names: function="
            +native_diagnostic_text(path)+"; parameter="+native_diagnostic_text(expected[index].name));
    for (const auto& parameter : expected) {
        const auto& actual=result.at(parameter.name);
        if(actual.kind!=parameter.kind)throw std::runtime_error("native UFunction parameter type changed: function="
            +native_diagnostic_text(path)+"; parameter="+native_diagnostic_text(parameter.name)
            +"; expected="+native_diagnostic_text(parameter.kind)+"; actual="+native_diagnostic_text(actual.kind));
    }
    const auto has_return = std::any_of(expected.begin(), expected.end(), [](const auto& p) { return p.name == L"ReturnValue"; });
    if (has_return) {
        require(result.at(L"ReturnValue").offset == result.function->GetReturnValueOffset(), "native return offset mismatch");
    } else {
        // Pinned LuaUObject.cpp:181 identifies 0xFFFF as the no-return sentinel.
        require(result.function->GetReturnValueOffset() == 0xffff, "fixed void function unexpectedly has a return slot");
    }
    return result;
}

std::wstring property_kind(const FProperty* property) {
    require(property != nullptr, "required reflected property is null");
    const auto full = reinterpret_cast<FField*>(const_cast<FProperty*>(property))->GetFullName();
    const auto space = full.find(L' ');
    require(space != std::wstring::npos, "cannot identify the reflected property kind");
    return full.substr(0, space);
}

const FProperty* class_property(const wchar_t* path, std::wstring_view wanted) {
    auto* object = find_object(path);
    require(object->GetFullName() == std::wstring(L"Class ") + path, "fixed capture class metadata changed");
    const auto* field = reinterpret_cast<const UStruct*>(object)->GetChildProperties();
    std::vector<const FField*> seen;
    while (field) {
        require(seen.size() < 512 && std::find(seen.begin(), seen.end(), field) == seen.end(), "invalid capture class property chain");
        seen.push_back(field);
        if (field->GetName() == wanted) return reinterpret_cast<const FProperty*>(field);
        field = FieldAccess::next(field);
    }
    throw std::runtime_error("fixed capture class property is absent");
}

class ParameterFrame {
    const Signature& signature_;
    void* data_{};
    std::size_t initialized_{};
public:
    explicit ParameterFrame(const Signature& signature) : signature_(signature) {
        data_ = _aligned_malloc(signature.size, signature.alignment);
        if (!data_) throw std::bad_alloc();
        std::memset(data_, 0, signature.size); // padding only; each property is then constructed below
        try {
            for (const auto& parameter : signature.parameters) {
                parameter.property->InitializeValue(address(parameter));
                ++initialized_;
            }
        } catch (...) {
            destroy();
            throw;
        }
    }
    ParameterFrame(const ParameterFrame&) = delete;
    ParameterFrame& operator=(const ParameterFrame&) = delete;
    ~ParameterFrame() { destroy(); }
    void* address(const Parameter& parameter) const { return static_cast<std::byte*>(data_) + parameter.offset; }
    void* data() const { return data_; }
private:
    void destroy() noexcept {
        while (initialized_ != 0) {
            const auto& parameter = signature_.parameters[--initialized_];
            // Native faults are not swallowed. A successful native construction
            // has exactly one corresponding destruction, in reverse order.
            parameter.property->DestroyValue(address(parameter));
        }
        _aligned_free(std::exchange(data_, nullptr));
    }
};
