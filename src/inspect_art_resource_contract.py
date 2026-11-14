"""Verify original ZhanMa ultimate-count payment and this executable's native ABI."""
from pathlib import Path
import hashlib
import json
import runpy

ROOT=Path(__file__).resolve().parents[1]
guard=runpy.run_path(str(ROOT/'src/inspect_guard_resource_native.py'))
select=guard['select']
player=select('GetPlayerCharacter',{'WorldContextObject':18,'PlayerIndex':3,'ReturnValue':18})
assert {p['name']:p['offset'] for p in player['parameters']}=={'WorldContextObject':0,'PlayerIndex':8,'ReturnValue':16}
assert player['size']==24
paths=['extract/vanilla-balance/ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/ActorData/Players/Hun/Abilities/ZhanMaBlade/GA_Hun_ZhanMa_C.json']
exports=json.loads((ROOT/paths[0]).read_text(encoding='utf-8'))
graph=next(e for e in exports if e.get('Name')=='ExecuteUbergraph_GA_Hun_ZhanMa_C')['ScriptBytecode']
attribute=next(c for c in graph if c.get('StatementIndex')==205)
assert attribute['Token']=='EX_Let' and attribute['Expression']['Token']=='EX_StructConst'
assert attribute['Expression']['Properties'][0]=={'Token':'EX_StringConst','Value':'UltimateChargeCount'}
assert attribute['Expression']['Properties'][1]['Value']['Value']=='/Script/CharacterBasics.BasicAttributeSet:UltimateChargeCount'
temporary=attribute['Variable']['Variable']['Property']['Name']
debit=next(c for c in graph if c.get('StatementIndex')==351)
assert debit['Token']=='EX_CallMath' and debit['Function']=={'ObjectName':"Class'AttributeUtils:ModifyCharacterAttributeValue'",'ObjectPath':'/Script/SGameAttributes'}
assert debit['Parameters'][1]['Variable']['Property']['Name']==temporary
assert debit['Parameters'][2]=={'Token':'EX_ByteConst','Value':0}
assert debit['Parameters'][3]=={'Token':'EX_FloatConst','Value':-1.0}
assert next(e for e in exports if e.get('Name')=='Default__GA_Hun_ZhanMa_C_C')['Properties']['Ultimate Charge Cost']==1
source_text=(ROOT/paths[0]).read_text(encoding='utf-8')
assert 'AbilitySystemComponent:GetGameplayAttributeValue' in source_text
native=(ROOT/'src/native/NativeArtResource.hpp').read_text(encoding='utf-8')
assert 'GetPlayerCharacter' in native and 'current==pawn' in native
assert 'IsInGameThread()&&input.size()<=4096' in native
assert 'ModifyCharacterAttributeValue' in native and 'const float cost=-1' in native
assert 'SpiritShadow' not in native and ':Health' not in native
assert 'BasicAttributeSet:UltimateCharge,' not in native and 'BasicAttributeSet:UltimateChargeCount,' in native
report={
 'status':'passed_offline','resource':'UltimateChargeCount','localized_resource':'精纯杀气','cost':1,
 'scope':'Original ZhanMa CombatArt directly pays UltimateChargeCount through AttributeUtils Additive -1; current executable ABI; no runtime debit proof',
 'original_base_gate_attribute':'/Script/CharacterBasics.BasicAttributeSet:UltimateChargeCount',
 'original_debit_statement':351,'original_attribute_statement':205,
 'original_default_cost_field':'Ultimate Charge Cost','original_default_cost_value':1,
 'native_modifier_reused':'/Script/SGameAttributes.AttributeUtils:ModifyCharacterAttributeValue',
 'modifier_operation':'Additive 0, delta -1',
 'payment_route':'PBZ native attribute utility/ASC delegates, not raw GameplayAttributeData writes',
 'functions':[guard['read'],guard['valid'],guard['modify'],player],
 'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
 'host_sha256':guard['sha'],'runtime_verified':False,
}
(ROOT/'reports/native-art-resource-schemas-087.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS original ZhanMa UltimateChargeCount payment Additive -1 and current-executable native modifier/player ABI')
