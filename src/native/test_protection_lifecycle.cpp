#include "ProtectionLeaseStorage.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <thread>
using namespace RingedKnightProtection;
void prime() {
    action={L"Pawn",L"ASC",{L"action-handle"},"action-token",100};
    block={L"Pawn",L"ASC",{L"block-handle"},"block-token",110};
}
void empty() {
    assert(action.pawn.empty()&&action.asc.empty()&&action.handles.empty()&&action.token.empty()&&action.refreshed==0);
    assert(block.pawn.empty()&&block.asc.empty()&&block.handles.empty()&&block.token.empty()&&block.refreshed==0);
}
std::string source(const char* file) {std::ifstream input(file);assert(input);return {(std::istreambuf_iterator<char>(input)),{}};}
int main(int argc,char** argv) {
    assert(argc==3);
    prime();std::thread stopped([]{forget();});stopped.join();empty();
    forget();forget();empty();
    prime();{struct BridgeShutdown {~BridgeShutdown(){forget();}} bridge;}empty();
    prime();std::vector<std::thread> stops;
    for(int i=0;i<8;++i)stops.emplace_back([]{forget();});
    for(auto& stop:stops)stop.join();empty();
    const auto main=source(argv[1]),implementation=source(argv[2]);
    const std::string forget_call="RingedKnightProtection::forget()";
    const auto first=main.find(forget_call);assert(first!=std::string::npos&&main.find(forget_call,first+forget_call.size())!=std::string::npos);
    assert(main.find("RingedKnightProtection::shutdown")==std::string::npos);
    assert(main.find("RingedKnightProtection::cleanup")==std::string::npos);
    assert(implementation.find("if(IsInGameThread()){remove_handles(action);action=Lease{};}else forget();")!=std::string::npos);
    assert(implementation.find("if(phase==\"cleanup\") {cleanup();")!=std::string::npos);
    assert(implementation.find("require(IsInGameThread(),\"protection cleanup requires game thread\")")!=std::string::npos);
    std::cout<<"PASS actual engine-free protection forget: non-GT, repeated/destructor/concurrent stops and GT-only removal call sites\n";
}
