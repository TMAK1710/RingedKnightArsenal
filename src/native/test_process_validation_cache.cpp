#include "ProcessValidationCache.hpp"
#include <array>
#include <atomic>
#include <cassert>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
std::string read(const char* path){std::ifstream file(path);assert(file);return {(std::istreambuf_iterator<char>(file)),{}};}
int main(int argc,char** argv) {
    using RingedKnightProcessValidation::OnceResult;
    assert(argc==3);
    OnceResult<std::array<unsigned char,32>> digest;std::atomic_int reads{};
    auto hash=[&]{++reads;std::array<unsigned char,32> value{};value[0]=0x44;return value;};
    std::vector<std::thread> calls;
    for(int i=0;i<8;++i)calls.emplace_back([&]{for(int j=0;j<100;++j)assert(digest.get(hash)[0]==0x44);});
    for(auto& call:calls)call.join();assert(reads==1);
    OnceResult<bool> rejected;int checks=0;
    assert(!rejected.get([&]{++checks;return false;}));
    assert(!rejected.get([&]{++checks;return true;}));assert(checks==1);
    OnceResult<bool> failed;int attempts=0;
    for(int i=0;i<3;++i){bool threw=false;try{failed.get([&]()->bool{++attempts;throw std::runtime_error("unsupported/read failure");});}catch(const std::runtime_error&){threw=true;}assert(threw);}
    assert(attempts==1);
    OnceResult<bool> new_process;assert(new_process.get([&]{++checks;return true;})&&checks==2);
    const auto main=read(argv[1]),shield=read(argv[2]);
    const auto start=main.find("int lua_compatible(");const auto end=main.find("class RingedKnightBridge",start);assert(start!=std::string::npos&&end!=std::string::npos);
    const auto compatible=main.substr(start,end-start);
    assert(compatible.find("process_executable_hash()")!=std::string::npos&&compatible.find("file_hash(nullptr)")==std::string::npos);
    assert(shield.find("process_executable_hash()")!=std::string::npos&&shield.find("std::ifstream")==std::string::npos);
    assert(main.find("OnceResult<bool> validated")!=std::string::npos);
    std::cout<<"PASS one process hash across800 calls, cached negative/error fail-closed, fresh-process validation and shared shield digest\n";
}
