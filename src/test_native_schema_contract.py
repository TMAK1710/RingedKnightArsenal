"""Source/evidence contract regressions, independent of the running game."""
from pathlib import Path
import json
from native_schema_contract import SchemaMismatch,compare_fields,parse_cpp_contract

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'src/native/NativeProtection.hpp').read_text(encoding='utf-8')
entries,accesses=parse_cpp_contract(source)
assert len(entries)==11 and any(e['path'].endswith(':Conv_DoubleToString')for e in entries)
runtime=json.loads((ROOT/'reports/runtime-protection-schemas.json').read_text(encoding='utf-8'))
actual={e['path']:e for e in runtime['functions']}
from native_schema_contract import GEN_KINDS
owned=json.loads((ROOT/'reports/armor-0912-makespec-schema.json').read_text())[0]
actual['/Script/GameplayAbilities.AbilitySystemBlueprintLibrary:MakeSpecHandle']={'exists':True,'properties':[{'name':v['name'],'kind':GEN_KINDS[v['gen_type']]}for v in owned['parameters']]}

changes=[]
for entry in entries:
    evidence=actual[entry['path']]
    assert evidence.get('exists')and not evidence.get('error')
    changes+=compare_fields(entry['path'],entry['parameters'],evidence['properties'])
assert {'expected':'Duration','actual':'duration'} in changes

duration=[{'name':'Duration','kind':'FloatProperty'}]
def rejects(expected,found):
    try:compare_fields('SetDuration',expected,found)
    except SchemaMismatch:return
    raise AssertionError('Invalid schema was accepted')
assert compare_fields('SetDuration',duration,[{'name':'duration','kind':'FloatProperty'}])
rejects(duration,[{'name':'duration','kind':'DoubleProperty'}])
rejects(duration,[{'name':'duration','kind':'FloatProperty'},{'name':'Duration','kind':'FloatProperty'}])
rejects(duration,[{'name':'DurationSeconds','kind':'FloatProperty'}])
for bad in [source.replace('L"Duration",L"FloatProperty"','L"DurationSeconds",L"FloatProperty"',1),
            source.replace('L"InDouble",L"DoubleProperty"','L"InDouble_BAD",L"DoubleProperty"',1)]:
    try:
        parsed,_=parse_cpp_contract(bad)
        for entry in parsed:compare_fields(entry['path'],entry['parameters'],actual[entry['path']]['properties'])
    except SchemaMismatch:continue
    raise AssertionError('Changed C++ expected field escaped source/evidence validation')
print('PASS actual lowercase duration; all11 C++ schemas/accesses; omitted string-buffer field; missing/ambiguous/type mismatches')
