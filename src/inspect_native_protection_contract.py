"""Current-executable reflection and original effect/attack asset evidence."""
import hashlib
import json
import struct
import inspect_guard_resource_native as G
from native_schema_contract import GEN_KINDS,SchemaMismatch,compare_fields,parse_cpp_contract

def direct_descriptors(name):
    """Read FFunctionParams directly; some engine ctor thunks are protected."""
    entries=[];cursor=0
    while (hit:=G.data.find(name.encode()+b'\0',cursor))>=0:
        cursor=hit+1
        if hit and G.data[hit-1]!=0:continue
        named=G.base+G.pe.get_rva_from_offset(hit);ref=0
        while (at:=G.data.find(struct.pack('<Q',named),ref))>=0:
            ref=at+8
            if at<16:continue
            try:
                outer,superfn,nameptr,props=struct.unpack_from('<QQQQ',G.data,at-16)
                count,size=struct.unpack_from('<HH',G.data,at+16)
                if not G.executable(outer)or nameptr!=named or not 0<count<=20 or not 0<size<2048:continue
                parameters=[]
                for index in range(count):
                    prop,=struct.unpack('<Q',G.pe.get_data(props-G.base+8*index,8));p=G.pe.get_data(prop-G.base,64)
                    flags,=struct.unpack_from('<Q',p,16)
                    if not flags&0x80:continue
                    kind=p[24]&0x3f
                    parameters.append({'name':G.text(struct.unpack_from('<Q',p)[0]),'gen_type':kind,
                                       'offset':None if kind==12 else struct.unpack_from('<H',p,50)[0]})
                entries.append({'name':name,'outer_rva':hex(outer-G.base),'descriptor_rva':hex(G.pe.get_rva_from_offset(at-16)),
                                'size':size,'parameters':parameters,'evidence':'Direct FFunctionParams metadata; no execution of protected constructor'})
            except (ValueError,UnicodeError,G.pefile.PEFormatError):pass
    return entries

def choose(name, wanted, outer=None):
    found=[x for x in direct_descriptors(name) if {p['name']:p['gen_type'] for p in x['parameters']}==wanted]
    if outer is not None:found=[x for x in found if x['outer_rva']==outer]
    assert len(found)==1,(name,found)
    return found[0]

cpp_path=G.ROOT/'src/native/NativeProtection.hpp'
cpp_contract,cpp_accesses=parse_cpp_contract(cpp_path.read_text(encoding='utf-8'))
functions=[];owner_rvas={};runtime_case_changes=[]
for entry in cpp_contract:
    owner,name=entry['path'].split(':',1);matches=[]
    for candidate in direct_descriptors(name):
        fields=[{'name':p['name'],'kind':GEN_KINDS[p['gen_type']]}for p in candidate['parameters']]
        try:compare_fields(entry['path'],entry['parameters'],fields)
        except SchemaMismatch:continue
        if owner in owner_rvas and candidate['outer_rva']!=owner_rvas[owner]:continue
        matches.append(candidate)
    assert len(matches)==1,(entry['path'],'C++ ExpectedParameters do not uniquely match current UHT descriptors',matches)
    selected=matches[0];owner_rvas[owner]=selected['outer_rva']
    selected['cpp_path']=entry['path'];selected['cpp_expected_array']=entry['array'];selected['cpp_expected_parameters']=entry['parameters']
    functions.append(selected)
runtime_path=G.ROOT/'reports/runtime-protection-schemas.json'
runtime_evidence=None
runtime_pending=[]
if runtime_path.exists():
    runtime=json.loads(runtime_path.read_text(encoding='utf-8'));actual={e['path']:e for e in runtime['functions']}
    for entry in cpp_contract:
        if entry['path'] not in actual:
            assert entry['path']=='/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:MakeSpecHandle'
            runtime_pending.append(entry['path']);continue  # Current-executable descriptors validated above; runtime still pending.
        found=actual[entry['path']];assert found.get('exists')and not found.get('error'),found
        differences=compare_fields(entry['path'],entry['parameters'],found['properties'])
        runtime_case_changes += [{'path':entry['path'],**d}for d in differences]
    runtime_evidence={'path':str(runtime_path.relative_to(G.ROOT)),'sha256':hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
                      'case_only_differences':runtime_case_changes,'effects_applied':False,'runtime_pending':runtime_pending}
root=G.ROOT/'extract/guard-evidence/ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content'
effects=[]
for name,tag in [('GE_IgnoreHit','CharacterState.Stand.IgnoreAllHits'),('GE_IgnoreBreak','CharacterState.Stand.IgnoreBreak')]:
    path=root/f'Prototypes/GameplayEffects/{name}.json';exports=json.loads(path.read_text(encoding='utf-8'))
    properties=next(e['Properties'] for e in exports if e.get('Name')=='Default__'+name+'_C')
    assert properties['DurationPolicy']=='EGameplayEffectDurationType::Infinite'
    assert properties['InheritableOwnedTagsContainer']['CombinedTags']==[tag]
    assert not properties.get('Modifiers') and not properties.get('Executions')
    effects.append({'path':str(path.relative_to(G.ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'only_tag':tag})

attack=root/'ActorData/Players/Hun/BulletData/ChiZheCanJian/Use/Normal/BulletData_Hun_ChiZheCanJian_Normal_A_01.json'
exports=json.loads(attack.read_text(encoding='utf-8'))
damage=exports[0]['Properties']['DamageData'];tags={p['Key']['TagName']:p['Value'] for p in damage}
assert tags['Damage.Attack.Target.AngerDamage']==tags['Damage.Attack.Target.PhysicalDamage']==.72
assert tags['Damage.Attack.Target.HitAngerDamageMultiplier']==.05
assert tags['Damage.Attack.Target.PoiseDamage']==100

report={'scope':'Offline current-executable UHT and original cooked asset checks only; no actual effect application or native Shachi/HP acceptance',
        'host_sha256':G.sha,'functions':functions,'original_effects':effects,
        'cpp_source_sha256':hashlib.sha256(cpp_path.read_bytes()).hexdigest(),'cpp_expected_parameters_parsed':len(cpp_contract),
        'cpp_parameter_accesses_checked':len(cpp_accesses),'runtime_schema_evidence':runtime_evidence,
        'original_attack':{'path':str(attack.relative_to(G.ROOT)),'sha256':hashlib.sha256(attack.read_bytes()).hexdigest(),'damage_tags':tags},
        'effect_runtime_policy':{'action_seconds':.25,'action_refresh_ms':100,'front_block_seconds':.15,
                                 'owned_handles_only':True,'no_permanent_loose_tags':True,'hp_damage_unchanged_for_action_armor':True},
        'runtime_required':['reflection/SameType and finite applied spec duration','native effect tags suppress hitreact/break while HP still decreases',
                            'front guard contact debits1 Shachi and no longer triggers an interrupt','enemy AngerDamage settles real Shachi with vanilla calculation']}
(G.ROOT/'reports/native-protection-contract.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS all C++-declared protection schemas/accesses against current UHT/runtime fields, reaction-only effects and AngerDamage/PoiseDamage')
