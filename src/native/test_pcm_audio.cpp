// Actual PCM parsing plus an intentionally blocked fake mixer backend.
// The system audio Device is never constructed and no sound is played.
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <future>
#include <map>
#include <thread>
#include <Windows.h>
#include <xaudio2.h>
#include "../../references/pbz-mc/third_party/nlohmann-json-3.11.3/json.hpp"
namespace {
struct Lua {
    int get_stack_size() const;
    bool is_string(int) const;
    std::string get_string(int) const;
    void set_string(const std::string&) const;
    void set_nil() const;
};
void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
#include "NativeAudio.hpp"
constexpr std::array<std::string_view,18> previous_sample_names{
    "SW_DS3_Swing_Light1", "SW_DS3_Swing_Light23", "SW_DS3_Swing_Heavy",
    "SW_DS3_Swing_Ember", "SW_DS3_Ember_Heavy", "SW_DS3_Ember_Ignite",
    "SW_DS3_Hit_Light", "SW_DS3_Hit_Heavy", "SW_DS3_Hit_Thrust",
    "SW_DS3_Guard_Raise", "SW_DS3_Guard_Block", "SW_DS3_Fire",
    "SW_DS3_Throw", "SW_DS3_Explosion", "SW_DS3_Swing_EmberFollow",
    "SW_DS3_Plunge_Movement", "SW_DS3_Plunge_Start", "SW_DS3_Plunge_Land"
};
static_assert(NativeAudio::sample_names.size()==19,"Native PCM catalog must contain the approved 19 samples");
static_assert(std::equal(previous_sample_names.begin(),previous_sample_names.end(),NativeAudio::sample_names.begin()),
    "The original 18 PCM catalog entries must remain unchanged");
static_assert(NativeAudio::sample_names.back()=="SW_DS3_Cancel_Ignite","The approved cancel ignition must be the 19th sample");
struct FakeOutput {
    inline static std::mutex gate;
    inline static std::condition_variable changed;
    inline static bool entered=false,released=false,watchdog=false;
    inline static std::atomic<int> preloads=0,initializations=0,plays=0;
    void preload() {
        ++preloads;std::unique_lock lock(gate);entered=true;changed.notify_all();
        changed.wait(lock,[]{return released;});
    }
    void initialize(){++initializations;}
    void collect(){}
    NativeAudio::Json play(const std::string& name,float) {
        return NativeAudio::Json{{"started",true},{"playing_id",++plays},{"sample",name}};
    }
};
void check_nonblocking_queue() {
    NativeAudio::Mixer<FakeOutput> mixer;
    const auto preparation=mixer.submit({},0,true);
    require(preparation.at("queued")==true&&preparation.at("started")==false,"Preparation must return a queue receipt");
    {
        std::unique_lock lock(FakeOutput::gate);
        require(FakeOutput::changed.wait_for(lock,std::chrono::seconds(2),[]{return FakeOutput::entered;}),"Fake backend did not enter preload");
    }
    std::jthread watchdog([]{
        std::unique_lock lock(FakeOutput::gate);
        if(!FakeOutput::changed.wait_for(lock,std::chrono::seconds(2),[]{return FakeOutput::released;})) {
            FakeOutput::watchdog=true;FakeOutput::released=true;FakeOutput::changed.notify_all();
        }
    });
    for(int index=0;index<32;++index) {
        const auto accepted=mixer.submit("SW_DS3_Hit_Light",.8f);
        require(accepted.at("queued")==true&&accepted.at("started")==false&&!accepted.contains("playing_id"),
            "Queued audio was incorrectly reported as started");
    }
    bool full=false;try{mixer.submit("SW_DS3_Hit_Light",.8f);}catch(const std::exception&){full=true;}
    require(full,"PCM queue did not enforce its bound");
    {
        std::lock_guard lock(FakeOutput::gate);
        require(!FakeOutput::released&&FakeOutput::plays==0,"Audio submission waited for the blocked backend");
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(175));
    {std::lock_guard lock(FakeOutput::gate);FakeOutput::released=true;}
    FakeOutput::changed.notify_all();
    std::vector<NativeAudio::Json> receipts;
    const auto await=[&](size_t expected) {
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
        while(receipts.size()<expected&&std::chrono::steady_clock::now()<deadline) {
            auto batch=mixer.receipts();
            for(auto& receipt:batch.at("receipts"))receipts.push_back(std::move(receipt));
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        require(receipts.size()==expected,"PCM completion receipt missing");
    };
    await(33);require(receipts.front().at("validated")==true,"Preload completion was not confirmed");
    for(size_t index=1;index<receipts.size();++index)
        require(receipts[index].at("started")==false&&receipts[index].at("error")=="PCM cue expired in queue",
            "A stale hit sound was played after its deadline");
    mixer.submit("SW_DS3_Hit_Heavy",.8f);await(34);
    require(receipts.back().at("started")==true&&receipts.back().at("playing_id")==1&&FakeOutput::plays==1,
        "Actual backend start was not delivered as a completion receipt");
    require(FakeOutput::preloads==1&&FakeOutput::initializations==1&&!FakeOutput::watchdog,"PCM backend was initialized repeatedly or blocked submission");
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"Pass the DS3 selection JSON path");
        const std::filesystem::path selection=std::filesystem::canonical(argv[1]);
        const auto root=selection.parent_path().parent_path();
        std::ifstream manifest(selection);nlohmann::json data;manifest>>data;
        size_t count=0;
        for(const auto& asset:data.at("assets")) {
            const auto name=asset.at("name").get<std::string>();
            require(std::find(NativeAudio::sample_names.begin(),NativeAudio::sample_names.end(),name)!=NativeAudio::sample_names.end(),
                "Selected PCM name is absent from the native allowlist");
            const auto path=root/asset.at("wav").get<std::string>();
            std::ifstream stream(path,std::ios::binary);
            std::vector<BYTE> bytes((std::istreambuf_iterator<char>(stream)),{});
            const auto decoded=NativeAudio::decode_sample(bytes);
            require(decoded.format.nChannels==1&&decoded.format.wBitsPerSample==16&&decoded.format.nSamplesPerSec==48000,
                "Selected source PCM format changed");
            require(!decoded.pcm.empty(),"Selected source PCM is empty");
            const auto reject=[&](std::vector<BYTE> damaged){
                try{NativeAudio::decode_sample(damaged);}catch(const std::exception&){return;}
                throw std::runtime_error("Malformed WAV was accepted");
            };
            auto damaged=bytes;damaged.resize(20);reject(damaged);
            damaged=bytes;damaged[0]='X';reject(damaged);
            damaged=bytes;damaged[4]^=1;reject(damaged);
            damaged=bytes;damaged[16]=0xff;damaged[17]=0xff;damaged[18]=0xff;damaged[19]=0xff;reject(damaged);
            ++count;
        }
        require(count==NativeAudio::sample_names.size(),"Native PCM sample allowlist differs from selection");
        check_nonblocking_queue();
        std::cout<<"PASS "<<count<<" selected PCM files, chunk bounds, nonblocking blocked-backend submission, queue cap, cue expiry and genuine completion receipts; no audio played\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
