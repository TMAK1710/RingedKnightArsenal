"""Compile production query input/dispatch code with recording engine doubles.

Exercises the actual import/ignored/vector_input/trace_batch/run functions.
The doubles verify dispatch ordering and frame ownership, not live UE ABI or
collision results. MSVC environment is supplied by build_native.ps1.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/native/NativeSpatialQuery.hpp').read_text(encoding='utf-8')
body = source[source.index('inline void import('):source.index('inline int lua_query(')]
preamble = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include "../../references/pbz-mc/third_party/nlohmann-json-3.11.3/json.hpp"
using Json=nlohmann::json;
static constexpr std::size_t output_limit=262144;
static constexpr wchar_t system_path[]=L"System";
static bool in_game_thread=true,throw_query=false,throw_result=false,oversize_result=false;
static std::wstring fail_import;
static int created=0,destroyed=0,live=0,max_live=0,dispatches=0,ignore_resolutions=0,ignore_imports=0;
static int expected_segments=0;
static void require(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
static bool IsInGameThread(){return in_game_thread;}
static std::wstring from_utf8(const std::string& s){return {s.begin(),s.end()};}
struct Slot{std::wstring text;};
struct UObject;
struct UFunction{bool overlap=false;};
struct FProperty{
 std::wstring name;int size=sizeof(void*);
 int GetSize()const{return size;}
 const wchar_t* ImportText_Direct(const wchar_t* text,void* target,UObject*,int,void*)const{
  if(name==L"ActorsToIgnore")++ignore_imports;
  if(!fail_import.empty()&&std::wstring_view(text).find(fail_import)!=std::wstring_view::npos)return nullptr;
  static_cast<Slot*>(target)->text=text;return text+wcslen(text);
 }
 void CopyCompleteValue(void* target,const void* source)const{*static_cast<Slot*>(target)=*static_cast<const Slot*>(source);}
};
struct FObjectPropertyBase:FProperty{UObject* GetObjectPropertyValue(const void* p)const{return *static_cast<UObject*const*>(p);}};
struct Parameter{const FProperty* property;std::wstring name;};
struct Signature{
 UFunction* function;std::vector<FProperty> properties;std::vector<Parameter> parameters;
 const Parameter& at(std::wstring_view name)const{for(const auto& p:parameters)if(p.name==name)return p;throw std::runtime_error("missing field");}
};
struct UObject{
 std::string path;bool actor=true,character=false,dead=false;
 bool IsUnreachable(){return dead;}
 void ProcessEvent(UFunction*,void*);
};
struct UStruct:UObject{};
static UStruct schema;
static UObject pawn{"Test.Pawn"},ignored_actor{"Test.Ignore"},enemy{"Test.Enemy",true,true},library{"System",false},not_actor{"Test.Component",false};
static std::map<std::wstring,UObject*> objects{{L"Test.Pawn",&pawn},{L"Test.Ignore",&ignored_actor},{L"Test.Enemy",&enemy},{L"Test.Component",&not_actor},{L"System",&library}};
static UObject* find_object(const wchar_t* path){
 if(std::wstring_view(path).starts_with(L"/Script/"))return &schema;
 if(std::wstring_view(path)==L"Test.Ignore")++ignore_resolutions;
 return objects.at(path);
}
static bool is_a(UObject* object,const wchar_t* type){return object&&!object->dead&&(std::wstring_view(type)==L"/Script/ProjectPBZ.PBZCharacter"?object->character:object->actor);}
static void verify_struct_property(const FProperty*,UObject*){}
static const FProperty* field_named(const UStruct*,std::wstring_view){static FProperty flag;return &flag;}
static std::wstring property_kind(const FProperty*){return L"BoolProperty";}
struct FakeHit{Json snapshot;};
struct ArrayView{void* data;std::int32_t count,capacity;};
struct ParameterFrame{
 std::map<std::wstring,Slot> values;std::vector<FakeHit> hits;std::vector<UObject*> actors;
 explicit ParameterFrame(const Signature& sig){for(const auto& p:sig.parameters)values.emplace(p.name,Slot{});++created;++live;max_live=std::max(max_live,live);}
 ~ParameterFrame(){for(auto& hit:hits)hit.snapshot["target"]="DESTROYED";++destroyed;--live;}
 ParameterFrame(const ParameterFrame&)=delete;
 void* address(const Parameter& p){return &values.at(p.name);}
 const void* address(const Parameter& p)const{return &values.at(p.name);}
 void* data(){return this;}
};
static UFunction trace_function,overlap_function{true};
static Signature make_signature(bool overlap){
 Signature sig;sig.function=overlap?&overlap_function:&trace_function;
 std::vector<std::wstring> names=overlap?std::vector<std::wstring>{L"WorldContextObject",L"SpherePos",L"SphereRadius",L"ObjectTypes",L"ActorClassFilter",L"ActorsToIgnore",L"OutActors",L"ReturnValue"}:
  std::vector<std::wstring>{L"WorldContextObject",L"Start",L"End",L"Radius",L"TraceChannel",L"bTraceComplex",L"ActorsToIgnore",L"DrawDebugType",L"OutHits",L"bIgnoreSelf",L"TraceColor",L"TraceHitColor",L"DrawTime",L"ReturnValue"};
 sig.properties.reserve(names.size());for(const auto& name:names)sig.properties.push_back({name});
 for(std::size_t i=0;i<names.size();++i)sig.parameters.push_back({&sig.properties[i],names[i]});return sig;
}
static const Signature& trace_schema(){static const auto sig=make_signature(false);return sig;}
static const Signature& overlap_schema(){static const auto sig=make_signature(true);return sig;}
static const FProperty* array_inner(const Parameter&,std::wstring_view kind){
 static FProperty hit{L"HitResult",sizeof(FakeHit)};static FObjectPropertyBase object;static FProperty byte;
 return kind==L"StructProperty"?&hit:kind==L"ObjectProperty"?&object:&byte;
}
static ArrayView array_view(const Parameter& parameter,const ParameterFrame& frame,const FProperty*){
 if(parameter.name==L"OutHits")return {const_cast<FakeHit*>(frame.hits.data()),static_cast<int>(frame.hits.size()),static_cast<int>(frame.hits.size())};
 return {const_cast<UObject**>(frame.actors.data()),static_cast<int>(frame.actors.size()),static_cast<int>(frame.actors.size())};
}
static Json hit_result(void* p,const FProperty*){if(throw_result)throw std::runtime_error("snapshot fault");return static_cast<FakeHit*>(p)->snapshot;}
static std::string object_path(UObject* object){return object?object->path:"";}
namespace RingedKnightHit{
 struct Vector{double x,y,z;};
 static UObject* object(const Json& data,const char* key){
  const auto path=from_utf8(data.at(key).get<std::string>());
  require(path.size()<2048&&path.find_first_of(L"\"'\r\n")==std::wstring::npos,"invalid path");
  auto* value=find_object(path.c_str());require(!value->dead,"dead object");return value;
 }
 static Vector vector(const Json& data,const char* key){
  const auto& v=data.at(key);Vector result{v.at("X").get<double>(),v.at("Y").get<double>(),v.at("Z").get<double>()};
  require(std::isfinite(result.x)&&std::isfinite(result.y)&&std::isfinite(result.z)&&std::abs(result.x)<1e9&&std::abs(result.y)<1e9&&std::abs(result.z)<1e9,"vector range");return result;
 }
}
static std::vector<std::wstring> dispatched_starts;
void UObject::ProcessEvent(UFunction* function,void* data){
 auto& f=*static_cast<ParameterFrame*>(data);
 if(expected_segments)assert(live==expected_segments-dispatches); // All inputs prepared; common frame already destroyed.
 ++dispatches;if(throw_query)throw std::runtime_error("query fault");
 assert(f.values.at(L"WorldContextObject").text==L"Object'Test.Pawn'");
 assert(f.values.at(L"ActorsToIgnore").text==L"(Object'Test.Pawn',Object'Test.Ignore')");
 if(function->overlap){
  assert(f.values.at(L"ActorClassFilter").text==L"Class'/Script/ProjectPBZ.PBZCharacter'");
  assert(f.values.at(L"ObjectTypes").text.starts_with(L"(0,1,2,")&&f.values.at(L"ObjectTypes").text.ends_with(L",31)"));
  f.actors={&enemy};return;
 }
 assert(f.values.at(L"TraceChannel").text==L"0"&&f.values.at(L"bTraceComplex").text==L"False");
 assert(f.values.at(L"DrawDebugType").text==L"0"&&f.values.at(L"bIgnoreSelf").text==L"True");
 dispatched_starts.push_back(f.values.at(L"Start").text);
 if(f.values.at(L"Radius").text==L"1.000000")return;
 f.hits.push_back({Json{{"target",oversize_result?std::string(output_limit+1,'x'):"Test.Enemy"},{"point",{{"X",dispatches},{"Y",0},{"Z",0}}},
  {"normal",{{"X",0},{"Y",0},{"Z",1}}},{"blocking",true},{"start_penetrating",false}}});
}
'''
tests = r'''
static Json segment(int x=0,double radius=24){return Json{{"start",{{"X",x},{"Y",0},{"Z",0}}},{"finish",{{"X",x+2},{"Y",1},{"Z",0}}},{"radius",radius}};}
static Json request(std::size_t count){Json data{{"phase","trace_batch"},{"pawn","Test.Pawn"},{"ignore",{"Test.Pawn","Test.Ignore"}},{"segments",Json::array()}};for(std::size_t i=0;i<count;++i)data["segments"].push_back(segment(static_cast<int>(i)));return data;}
static void reset(){assert(live==0&&created==destroyed);created=destroyed=max_live=dispatches=ignore_resolutions=ignore_imports=expected_segments=0;dispatched_starts.clear();fail_import.clear();throw_query=throw_result=oversize_result=false;in_game_thread=true;}
template<typename F>static void fails(F fn){bool rejected=false;try{fn();}catch(const std::exception&){rejected=true;}assert(rejected);assert(live==0&&created==destroyed);}
static void rejected_before_query(const Json& data){reset();fails([&]{run(data.dump());});assert(dispatches==0);}
int main(){
 auto caps=Json::parse(run(R"({"phase":"capabilities"})"));assert(caps["trace_batch"]&&caps["max_batch"]==64&&caps["trace"]&&caps["overlap"]&&dispatches==0);
 for(int count:{1,3,49,64}){
  reset();auto data=request(count);if(count==3)data["segments"][1]["radius"]=1;
  expected_segments=count;auto result=Json::parse(run(data.dump()));
  assert(result["api"]==1&&result["phase"]=="trace_batch"&&result["owned_parameter_frames"]&&result["results"].size()==count);
  assert(dispatches==count&&created==count+1&&created==destroyed&&live==0&&max_live==count+1);
  assert(ignore_resolutions==1&&ignore_imports==1); // shared list resolved/imported once
  for(int i=0;i<count;++i){
   assert(dispatched_starts[i].starts_with(L"(X="+std::to_wstring(i)+L".000000,"));
   const auto& hits=result["results"][i]["hits"];
   if(count==3&&i==1)assert(hits.empty());else assert(hits.size()==1&&hits[0]["target"]=="Test.Enemy"&&hits[0]["point"]["X"]==i+1&&hits[0]["blocking"]&&!hits[0]["start_penetrating"]);
  }
 }
 rejected_before_query(request(0));rejected_before_query(request(65));
 auto bad=request(3);bad["segments"]={};rejected_before_query(bad);
 for(const auto& value:std::vector<Json>{nullptr,"bad",Json::array()}){bad=request(3);bad["segments"][2]=value;rejected_before_query(bad);}
 for(double radius:{0.0,-1.0,1000.1}){bad=request(3);bad["segments"][2]["radius"]=radius;rejected_before_query(bad);}
 bad=request(3);bad["segments"][2].erase("finish");rejected_before_query(bad);
 bad=request(3);bad["segments"][2]["finish"]["Z"]="bad";rejected_before_query(bad);
 bad=request(3);bad["segments"][2]["finish"]["X"]=1e9;rejected_before_query(bad);
 bad=request(3);bad["segments"][2]["radius"]=std::numeric_limits<double>::infinity();reset();fails([&]{trace_batch(bad,&pawn);});assert(dispatches==0);
 bad=request(3);bad["segments"][2]["start"]["Y"]=std::numeric_limits<double>::quiet_NaN();reset();fails([&]{trace_batch(bad,&pawn);});assert(dispatches==0);
 bad=request(3);bad["ignore"].push_back("Test.Component");rejected_before_query(bad);
 bad=request(3);bad["ignore"].push_back("missing");rejected_before_query(bad);
 bad=request(3);bad["ignore"].push_back("bad'path");rejected_before_query(bad);
 bad=request(3);bad["ignore"]=Json::array();for(int i=0;i<129;++i)bad["ignore"].push_back("Test.Pawn");rejected_before_query(bad);
 bad=request(3);bad["pawn"]="Test.Component";rejected_before_query(bad);
 bad=request(3);bad["phase"]="unsupported";rejected_before_query(bad);
 reset();in_game_thread=false;fails([&]{run(request(3).dump());});assert(dispatches==0);in_game_thread=true;
 reset();fails([&]{run(std::string(32769,' '));});assert(dispatches==0);
 reset();bad=request(3);bad["segments"][2]["finish"]["X"]=777;fail_import=L"X=777.000000";fails([&]{run(bad.dump());});assert(dispatches==0&&created==destroyed);
 reset();fail_import=L"Object'Test.Ignore'";fails([&]{run(request(3).dump());});assert(dispatches==0);
 reset();throw_query=true;expected_segments=3;fails([&]{run(request(3).dump());});assert(dispatches==1);
 reset();throw_result=true;expected_segments=3;fails([&]{run(request(3).dump());});assert(dispatches==1);
 reset();oversize_result=true;fails([&]{run(request(1).dump());});assert(dispatches==1);
 reset();auto single=segment();single["phase"]="trace";single["pawn"]="Test.Pawn";single["ignore"]={"Test.Pawn","Test.Ignore"};
 auto single_result=Json::parse(run(single.dump()));assert(single_result["hits"].size()==1&&single_result["phase"]=="trace"&&!single_result.contains("results")&&created==1&&destroyed==1);
 reset();Json overlap{{"phase","overlap"},{"pawn","Test.Pawn"},{"ignore",{"Test.Pawn","Test.Ignore"}},{"center",{{"X",0},{"Y",0},{"Z",0}}},{"radius",25}};
 auto overlap_result=Json::parse(run(overlap.dump()));assert(overlap_result["actors"]==Json::array({"Test.Enemy"})&&overlap_result["phase"]=="overlap"&&created==1&&destroyed==1);
 std::cout<<"PASS actual native spatial query: batch1/3/49/64, full preflight before dispatch, shared ignore once, ordered owned snapshots, empty hits, exception cleanup, bounds, unchanged single/overlap filters\n";
}
'''
out = ROOT / 'build/native'
generated = out / 'test_spatial_query_generated.cpp'
generated.write_text(preamble + body + tests, encoding='utf-8')
subprocess.run(['cl', '/nologo', '/std:c++latest', '/MD', '/O2', '/EHsc', '/utf-8',
                '/Fo' + str(out / 'test_spatial_query.obj'), '/Fe' + str(out / 'test_spatial_query.exe'), str(generated)], check=True, cwd=ROOT)
subprocess.run([str(out / 'test_spatial_query.exe')], check=True, cwd=ROOT)
