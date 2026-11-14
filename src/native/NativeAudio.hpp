#pragma once

#include <chrono>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <map>
#include <thread>
#include <xaudio2.h>

// The shipping game does not create a UE audio component for these SoundWaves.
// Play the same selected mono PCM files through the system XAudio2 mixer.
// A private worker owns COM, the mixer and voices. No audio callback enters
// Lua or UE, and shutdown joins the worker before this DLL can be unloaded.
namespace NativeAudio {
using Json = nlohmann::json;
constexpr std::array<std::string_view,19> sample_names{
    "SW_DS3_Swing_Light1", "SW_DS3_Swing_Light23", "SW_DS3_Swing_Heavy",
    "SW_DS3_Swing_Ember", "SW_DS3_Ember_Heavy", "SW_DS3_Ember_Ignite",
    "SW_DS3_Hit_Light", "SW_DS3_Hit_Heavy", "SW_DS3_Hit_Thrust",
    "SW_DS3_Guard_Raise", "SW_DS3_Guard_Block", "SW_DS3_Fire",
    "SW_DS3_Throw", "SW_DS3_Explosion", "SW_DS3_Swing_EmberFollow",
    "SW_DS3_Plunge_Movement", "SW_DS3_Plunge_Start", "SW_DS3_Plunge_Land",
    "SW_DS3_Cancel_Ignite"
};

inline void succeeded(HRESULT result,const char* operation) {
    if(FAILED(result))throw std::runtime_error(std::string(operation)+" HRESULT="+std::to_string(static_cast<unsigned long>(result)));
}
inline std::filesystem::path audio_root() {
    HMODULE module{};
    require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&audio_root),&module)!=0,"PCM module path unavailable");
    std::array<wchar_t,32768> path{};
    const DWORD size=GetModuleFileNameW(module,path.data(),static_cast<DWORD>(path.size()));
    require(size>0&&size<path.size(),"PCM module path truncated");
    return std::filesystem::path(path.data()).parent_path().parent_path()/L"Audio";
}
inline std::uint32_t little32(const std::vector<BYTE>& bytes,size_t offset) {
    require(offset<=bytes.size()&&bytes.size()-offset>=4,"Truncated PCM chunk");
    return std::uint32_t(bytes[offset])|(std::uint32_t(bytes[offset+1])<<8)|
        (std::uint32_t(bytes[offset+2])<<16)|(std::uint32_t(bytes[offset+3])<<24);
}
inline std::uint16_t little16(const std::vector<BYTE>& bytes,size_t offset) {
    require(offset<=bytes.size()&&bytes.size()-offset>=2,"Truncated PCM format");
    return std::uint16_t(bytes[offset])|(std::uint16_t(bytes[offset+1])<<8);
}
struct Sample {WAVEFORMATEX format{};std::vector<BYTE> pcm;};
inline Sample decode_sample(const std::vector<BYTE>& bytes) {
    require(bytes.size()>=44&&bytes.size()<=4*1024*1024,"PCM file size outside bounds");
    require(std::memcmp(bytes.data(),"RIFF",4)==0&&std::memcmp(bytes.data()+8,"WAVE",4)==0&&little32(bytes,4)==bytes.size()-8,
        "PCM sample must be a complete RIFF WAVE");
    Sample sample;bool format_found=false,data_found=false;
    for(size_t offset=12;offset<bytes.size();) {
        require(bytes.size()-offset>=8,"Truncated PCM chunk header");
        const auto count=little32(bytes,offset+4);const auto payload=offset+8;
        require(count<=bytes.size()-payload,"PCM chunk exceeds file bounds");
        if(std::memcmp(bytes.data()+offset,"fmt ",4)==0) {
            require(!format_found&&count>=16,"PCM format chunk invalid");format_found=true;
            auto& format=sample.format;
            format.wFormatTag=little16(bytes,payload);format.nChannels=little16(bytes,payload+2);
            format.nSamplesPerSec=little32(bytes,payload+4);format.nAvgBytesPerSec=little32(bytes,payload+8);
            format.nBlockAlign=little16(bytes,payload+12);format.wBitsPerSample=little16(bytes,payload+14);
            require(format.wFormatTag==WAVE_FORMAT_PCM&&format.nChannels==1&&format.wBitsPerSample==16&&format.nBlockAlign==2&&
                format.nSamplesPerSec>=8000&&format.nSamplesPerSec<=96000&&format.nAvgBytesPerSec==format.nSamplesPerSec*2,
                "PCM sample must use mono PCM16 at 8-96 kHz");
        } else if(std::memcmp(bytes.data()+offset,"data",4)==0) {
            require(!data_found&&count>0,"PCM data chunk invalid");data_found=true;
            sample.pcm.assign(bytes.begin()+payload,bytes.begin()+payload+count);
        }
        offset=payload+count+(count&1);
        require(offset<=bytes.size(),"PCM chunk padding absent");
    }
    require(format_found&&data_found&&sample.pcm.size()%2==0&&sample.pcm.size()<=sample.format.nAvgBytesPerSec*10,
        "PCM sample has no valid audio or exceeds 10 seconds");
    return sample;
}
inline Sample load_sample(const std::string& name) {
    require(std::find(sample_names.begin(),sample_names.end(),name)!=sample_names.end(),"PCM sample is not allowlisted");
    const auto root=std::filesystem::canonical(audio_root());
    const auto path=std::filesystem::canonical(root/(name+".wav"));
    require(path.parent_path()==root,"PCM sample is outside the mod Audio directory");
    const auto size=std::filesystem::file_size(path);
    require(size>=44&&size<=4*1024*1024,"PCM file size outside bounds");
    std::vector<BYTE> bytes(static_cast<size_t>(size));
    std::ifstream file(path,std::ios::binary);
    require(bool(file.read(reinterpret_cast<char*>(bytes.data()),bytes.size())),"PCM file read failed");
    return decode_sample(bytes);
}
struct SystemModule {
    HMODULE handle{};
    explicit SystemModule(const wchar_t* name):handle(LoadLibraryExW(name,nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32)) {
        require(handle!=nullptr,"System audio module unavailable");
    }
    ~SystemModule(){if(handle)FreeLibrary(handle);}
    SystemModule(const SystemModule&)=delete;
    SystemModule& operator=(const SystemModule&)=delete;
};
struct Apartment {
    SystemModule module{L"ole32.dll"};
    using Initialize=HRESULT(WINAPI*)(LPVOID,DWORD);
    using Uninitialize=void(WINAPI*)();
    Uninitialize uninitialize{};
    Apartment() {
        const auto initialize=reinterpret_cast<Initialize>(GetProcAddress(module.handle,"CoInitializeEx"));
        uninitialize=reinterpret_cast<Uninitialize>(GetProcAddress(module.handle,"CoUninitialize"));
        require(initialize&&uninitialize,"COM initialization API unavailable");
        succeeded(initialize(nullptr,COINIT_MULTITHREADED),"COM audio initialization");
    }
    ~Apartment(){uninitialize();}
};
struct Voice {
    IXAudio2SourceVoice* source{};
    bool active=false;
    ~Voice(){if(source)source->DestroyVoice();}
};
class Device {
    Apartment apartment;
    SystemModule module{L"xaudio2_9.dll"};
    IXAudio2* engine{};
    IXAudio2MasteringVoice* master{};
    std::map<std::string,Sample> samples;
    std::vector<std::unique_ptr<Voice>> voices;
    std::uint64_t sequence{};
public:
    void preload() {
        if(samples.size()==sample_names.size())return;
        std::map<std::string,Sample> loaded;
        size_t bytes=0;
        for(const auto name:sample_names) {
            auto sample=load_sample(std::string(name));bytes+=sample.pcm.size();
            require(bytes<=8*1024*1024,"PCM sample cache exceeds bounds");
            require(sample.format.nSamplesPerSec==48000,"Selected PCM pool requires 48 kHz samples");
            loaded.emplace(std::string(name),std::move(sample));
        }
        samples.swap(loaded);
    }
    void initialize() {
        using Create=HRESULT(WINAPI*)(IXAudio2**,UINT32,XAUDIO2_PROCESSOR);
        const auto create=reinterpret_cast<Create>(GetProcAddress(module.handle,"XAudio2Create"));
        require(create!=nullptr,"XAudio2 creation API unavailable");
        succeeded(create(&engine,0,XAUDIO2_DEFAULT_PROCESSOR),"XAudio2Create");
        succeeded(engine->CreateMasteringVoice(&master),"XAudio2 mastering voice");
        require(samples.size()==sample_names.size(),"PCM samples were not preloaded");
        for(size_t index=0;index<24;++index) {
            auto voice=std::make_unique<Voice>();
            succeeded(engine->CreateSourceVoice(&voice->source,&samples.begin()->second.format),"XAudio2 pooled source voice");
            voices.push_back(std::move(voice));
        }
    }
    ~Device() {
        voices.clear();
        if(master)master->DestroyVoice();
        if(engine){engine->StopEngine();engine->Release();}
    }
    void collect() {
        for(const auto& voice:voices) {
            if(!voice->active)continue;
            XAUDIO2_VOICE_STATE state{};
            voice->source->GetState(&state,XAUDIO2_VOICE_NOSAMPLESPLAYED);
            if(state.BuffersQueued==0){voice->source->Stop();voice->active=false;}
        }
    }
    Json play(const std::string& name,float volume) {
        collect();const auto found=samples.find(name);
        require(found!=samples.end(),"PCM sample was not preloaded");
        const auto& sample=found->second;
        const auto slot=std::find_if(voices.begin(),voices.end(),[](const auto& voice){return !voice->active;});
        require(slot!=voices.end(),"PCM concurrent voice limit reached");
        auto& voice=**slot;
        succeeded(voice.source->SetVolume(volume),"XAudio2 sample volume");
        XAUDIO2_BUFFER buffer{};buffer.Flags=XAUDIO2_END_OF_STREAM;
        buffer.AudioBytes=static_cast<UINT32>(sample.pcm.size());buffer.pAudioData=sample.pcm.data();
        succeeded(voice.source->SubmitSourceBuffer(&buffer),"XAudio2 PCM submission");
        const auto started=voice.source->Start();
        if(FAILED(started)){voice.source->Stop();voice.source->FlushSourceBuffers();}
        succeeded(started,"XAudio2 source start");voice.active=true;
        return Json{{"api",2},{"backend","xaudio2_9"},{"started",true},{"playing_id",++sequence},
            {"sample",name},{"volume",volume}};
    }
};
struct Request {
    std::uint64_t id{};std::string name;float volume{};bool prepare=false;
    std::chrono::steady_clock::time_point queued;
};
template<class Output=Device>
class Mixer {
    std::mutex mutex;
    std::condition_variable changed;
    std::deque<Request> pending;
    std::deque<Json> completed;
    std::uint64_t sequence{};
    bool inflight=false;
    bool stopping=false;
    std::thread worker;
    void run() {
        std::unique_ptr<Output> device;
        for(;;) {
            Request request;
            {
                std::unique_lock lock(mutex);
                changed.wait_for(lock,std::chrono::milliseconds(20),[this]{return stopping||!pending.empty();});
                if(stopping)break;
                if(!pending.empty()){request=std::move(pending.front());pending.pop_front();inflight=true;}
            }
            if(device)device->collect();
            if(!request.id)continue;
            Json result;
            try {
                if(!device){auto candidate=std::make_unique<Output>();candidate->preload();candidate->initialize();device=std::move(candidate);}
                if(request.prepare)result=Json{{"validated",true},{"samples",sample_names.size()}};
                else {
                    require(std::chrono::steady_clock::now()-request.queued<=std::chrono::milliseconds(150),"PCM cue expired in queue");
                    result=device->play(request.name,request.volume);
                }
            } catch(const std::exception& error) {result=Json{{"started",false},{"validated",false},{"error",error.what()}};}
            result["api"]=2;result["backend"]="xaudio2_9";result["request_id"]=request.id;
            if(!request.prepare)result["sample"]=request.name;
            {std::lock_guard lock(mutex);inflight=false;completed.push_back(std::move(result));}
        }
        // Device destruction runs here on the same COM apartment that created it.
    }
public:
    Mixer():worker([this]{run();}){}
    ~Mixer() {
        {std::lock_guard lock(mutex);stopping=true;}
        changed.notify_one();worker.join();
    }
    Json submit(std::string name,float volume,bool prepare=false) {
        std::uint64_t id;
        {
            std::unique_lock lock(mutex,std::try_to_lock);
            require(lock.owns_lock(),"PCM queue busy");
            require(!stopping&&pending.size()<32&&pending.size()+completed.size()+size_t(inflight)<64,"PCM mixer queue full");
            id=++sequence;pending.push_back({id,std::move(name),volume,prepare,std::chrono::steady_clock::now()});
        }
        changed.notify_one();
        return Json{{"api",2},{"backend","xaudio2_9"},{"queued",true},{"started",false},{"request_id",id}};
    }
    Json receipts() {
        std::deque<Json> finished;
        {
            std::unique_lock lock(mutex,std::try_to_lock);
            if(lock.owns_lock())finished.swap(completed);
        }
        Json results=Json::array();for(auto& result:finished)results.push_back(std::move(result));
        return Json{{"api",2},{"backend","xaudio2_9"},{"receipts",std::move(results)}};
    }
};
inline std::mutex mixer_mutex;
inline std::unique_ptr<Mixer<>> mixer;
inline void shutdown() {
    std::lock_guard lock(mixer_mutex);mixer.reset();
}
inline std::string run(const std::string& input) {
    require(input.size()<=1024,"PCM request exceeds bounds");const auto data=Json::parse(input);
    const auto phase=data.value("phase",std::string("play"));
    require(phase=="play"||phase=="prepare"||phase=="receipts","PCM phase unsupported");
    const auto name=phase=="play"?data.at("name").get<std::string>():std::string();
    require(phase!="play"||std::find(sample_names.begin(),sample_names.end(),name)!=sample_names.end(),"PCM sample is not allowlisted");
    const double volume=data.value("volume",0.8);
    require(std::isfinite(volume)&&volume>=0&&volume<=1,"PCM volume outside bounds");
    std::unique_lock lock(mixer_mutex,std::try_to_lock);require(lock.owns_lock(),"PCM mixer busy");
    if(phase=="receipts")return mixer?mixer->receipts().dump():Json{{"api",2},{"backend","xaudio2_9"},{"receipts",Json::array()}}.dump();
    if(!mixer)mixer=std::make_unique<Mixer<>>();
    return mixer->submit(name,static_cast<float>(volume),phase=="prepare").dump();
}
inline int lua_play(const Lua& lua) {
    try {
        require(lua.get_stack_size()==1&&lua.is_string(1),"usage: RK_PlayPcm(json)");
        lua.set_string(run(std::string(lua.get_string(1))));lua.set_nil();
    } catch(const std::exception& error) {
        lua.set_nil();lua.set_string(std::string("RK PCM audio: ")+error.what());
    }
    return 2;
}
}
