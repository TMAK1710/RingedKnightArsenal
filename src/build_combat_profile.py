import json,pathlib,sys,hashlib,math
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/soul-python'))
from soulstruct.flver import FLVER
def read(path):return json.loads((root/path).read_text(encoding='utf-8-sig'))
def cells(row):return {k.lower():v for k,v in row['Cells'].items()}
weapon=cells(next(x for x in read('reports/ds3-weapon-params.json') if x['ID']==2250000))
shield=cells(next(x for x in read('reports/ds3-weapon-params.json') if x['ID']==21100000))
attacks={r['ID']:cells(r) for r in read('reports/ds3-attack-selected.json')+read('reports/ds3-heavy-attack.json')+read('reports/ds3-ember-heavy-attack.json')+read('reports/ds3-ember-follow-attack.json')+read('reports/ds3-plunge-attack.json')}
behaviors={(cells(r)['variationid'],cells(r)['behaviorjudgeid']):cells(r) for r in read('reports/ds3-behavior-pc-all.json')}
bomb=cells(next(r for r in read('reports/ds3-bomb-attack.json') if r['ID']==1059))
source=FLVER.from_path(root/'extract/ds3/models/rkss/WP_A_0225.flver')
dummies={str(d.reference_id):[float(d.translate.x),float(d.translate.z),float(d.translate.y)] for d in source.dummies}
(root/'reports/ds3-sword-dummies.json').write_text(json.dumps(dummies,indent=2))
banks={23:read('reports/ds3-a23-all.json'),251:read('reports/ds3-a251-all.json'),0:read('reports/ds3-a00-all.json')}
selection={'RKSS_Light1':(23,30000),'RKSS_Light2':(23,30010),'RKSS_Light3':(23,30020),'RKSS_Idle':(0,0),'RKSS_GuardStart':(0,19000),'RKSS_GuardLoop':(0,100),'RKSS_GuardEnd':(0,19100),'RKSS_EmberStart':(251,36200),'RKSS_Ember':(251,36230),'RKSS_EmberFollow1':(251,36250),'RKSS_EmberFollow2':(251,36290),'RKSS_EmberHeavy':(251,36240),'RKSS_RopeBomb':(0,50130)}
selection.update({'RKSS_Heavy1Charge':(23,30320),'RKSS_Heavy1Release':(23,30321),'RKSS_Heavy2Charge':(23,30340),'RKSS_Heavy2Release':(23,30341)})
selection.update({'RKSS_PlungeStart':(23,30800),'RKSS_PlungeLoop':(23,30801),'RKSS_PlungeLand':(23,30810)})
base_attack_scale_numerator=23
first_light_damage_scale=1.5
first_heavy_damage_scale=1.5
heavy_damage_scale=1.4
art_damage_scale=2
art_anger_scale=2
# User feedback 2026-11-07: multiply the installed 0.8.9 enemy Anger
# budgets once. HitAngerDamageMultiplier, health, poise and player recharge
# retain their authored values; multiplying both native anger inputs would
# accidentally turn this requested fivefold adjustment into twenty-fivefold.
enemy_anger_scale=5
# User requested an independently stronger L1+Circle branch. These absolute
# base-level budgets override the common art/global scales, not multiply them.
heavy_art_override={'physical':1600,'anger':32}
balance=read('reports/vanilla-zhanma-balance.json')
def native_damage(name):
    return balance['bullet_data'][name]['damage_data']
light_reference=native_damage('BD_Hun_ZhanMa_A_01')
base_poise=light_reference['Damage.Attack.Target.PoiseDamage']
first_light_poise=900
first_heavy_poise=900
follow_heavy_poise=150
resource_references={
    'RKSS_Heavy1Charge':[native_damage('BD_Hun_ZhanMa_B_01_Weak')],
    'RKSS_Heavy1Release':[native_damage('BD_Hun_ZhanMa_B_01_Weak')],
    'RKSS_Heavy2Charge':[native_damage('BD_Hun_ZhanMa_BB_01_Weak')],
    'RKSS_Heavy2Release':[native_damage('BD_Hun_ZhanMa_BB_01_Weak')],
    'RKSS_Ember':[native_damage('BD_Hun_ZhanMa_C_01'),native_damage('BD_Hun_ZhanMa_C_03')],
    'RKSS_EmberFollow1':[native_damage('BD_Hun_ZhanMa_C_04'),native_damage('BD_Hun_ZhanMa_C_05')],
    'RKSS_EmberFollow2':[native_damage('BD_Hun_ZhanMa_C_06')],
    'RKSS_EmberHeavy':[native_damage('BD_Hun_ZhanMa_C_06')],
    'RKSS_PlungeStart':[native_damage('B_Hun_Long_Air_A')],
    'RKSS_PlungeLoop':[native_damage('B_Hun_Long_Air_A')]*2,
    'RKSS_PlungeLand':[native_damage('B_Hun_Long_Air_B')],
}
profile={'format':1,'source_weapon_id':2250000,'upgrade':0,
    'base_physical':(weapon['atkbasephysics']*base_attack_scale_numerator+5)//10,
    'base_fire':(weapon['atkbasefire']*base_attack_scale_numerator+5)//10,
    'first_light_damage_scale':first_light_damage_scale,'first_light_poise':first_light_poise,
    'first_heavy_damage_scale':first_heavy_damage_scale,'first_heavy_poise':first_heavy_poise,
    'heavy_damage_scale':heavy_damage_scale,
    'follow_heavy_poise':follow_heavy_poise,
    'base_poise':base_poise,
    'enemy_anger_scale':enemy_anger_scale,
    'light_chain':{'max_hits':5,'pause_seconds':.25,'damage_first':1.5,'damage_follow':1,
        'poise_base':base_poise,'poise_first':first_light_poise/base_poise,'poise_follow':1,
        'anger_damage':light_reference['Damage.Attack.Target.AngerDamage']*enemy_anger_scale},
    'resource_damage_reference':{'item':'ZhanMaBlade','report':'reports/vanilla-zhanma-balance.json',
        'light_policy':'Five times the installed vanilla first-step budget per cut; five-cut total 22.95 vs installed 4.59 and vanilla four-step 4.47525',
        'heavy_policy':'Lower authored Weak budget, without importing the original health-spend mechanic',
        'bomb_policy':'Installed enemy grenade anger 1.2 times enemy_anger_scale; player explosion hit multiplier 1 and poise 50 unchanged',
        'enemy_anger_policy':{'baseline':'installed 0.8.9-dev',
            'scale':enemy_anger_scale,'applies_to':['light_chain.anger_damage','clips.*.hits.*.anger','bomb.anger'],
            'baseline_light_anger':light_reference['Damage.Attack.Target.AngerDamage'],
            'baseline_bomb_anger':1.2,'baseline_art_anger_scale':art_anger_scale,
            'final_overrides':{'RKSS_EmberHeavy':heavy_art_override},
            'unchanged':['physical','fire','poise','hit_anger_multiplier','ultimate_charge_regen']},
        'ultimate_policy':'ZhanMa authored UltimateChargeRegen: one full light step1, heavy1, art0, native air1; no direct resource writes'},
    'combo':['RKSS_Light1','RKSS_Light2','RKSS_Light3'],'combo_next':{'RKSS_Light1':'RKSS_Light2','RKSS_Light2':'RKSS_Light3','RKSS_Light3':'RKSS_Light2'},
    'cancel':{'move':'RKSS_Light1','open':.6,'close':.93333334,'flame_seconds':.35,'extra_damage':0,'timing_status':'custom simplified input; runtime feel not yet verified'},
    'guard':{'physical':shield['physguardcutrate']/100,'fire':shield['fireguardcutrate']/100,'magic':shield['magguardcutrate']/100,'lightning':shield['thunguardcutrate']/100,'dark':shield['darkguardcutrate']/100,'stability':shield['staminaguarddef'],'half_angle_degrees':60},
    'bomb':{'release':32/60,'radius_cm':280,'physical':bomb['atkphys'],'fire':400,'source_fire':bomb['atkfire'],'poise':50,'anger':1.2*enemy_anger_scale,'hit_anger_multiplier':1,'ultimate_charge_regen':0,
        'radius_fit':{'effect':'NS_BarrelExplosion_303','effect_scale':.35,
            'reference_native_radius_cm':400,'authored_culling_half_extent_cm':1000,
            'scaled_culling_half_extent_cm':350,'previous_radius_cm':140,
            'policy':'Expanded blast-body starting fit; culling bounds are not measured visible flame edges',
            'verification':'Offline estimate; actual visual/range fit pending manual test'},
        'source_animation':'a000_050130','gravity_cm':980,'mode':'drop_at_feet','initial_down_cm_s':180,'landing_back_cm':50,'landing_status':'runtime landing point pending verification'},
    'art':{'start':'RKSS_EmberStart','light':'RKSS_Ember','heavy':'RKSS_EmberHeavy','flame_at':.8333333,
        # Supersedes the former free-art policy; native settlement owns this
        # one-per-sequence full ultimate charge, never SpiritShadow or a
        # private focus budget. The user clarified the resource as 精纯杀气.
        'cost_policy':'native_ultimate_charge_once_per_sequence',
        'cost':{'resource':'UltimateChargeCount','amount':1,'unit':'full_charge','per_sequence':True},
        'damage_scale':art_damage_scale,'anger_scale':art_anger_scale,
        'heavy_override':{'values_at_base_level':heavy_art_override,
            'priority':'Applied after common art and enemy Anger scales; fire and other contacts unchanged'},
        'poise_policy':'keep original authored ZhanMa attack-specific poise',
        'hit_volume':{'space':'sword_local_cm','base':{'X':.056,'Y':.484,'Z':-30.457},
            'steel_tip':{'X':.056,'Y':.484,'Z':-111.485},'tip_extension_cm':100,'radius_cm':24,
            'activation':'real_art_hit_windows_only',
            'verification':'Screenshot-based approximate flame extension; runtime visual match pending manual test'},
        'light_chain':['RKSS_Ember','RKSS_EmberFollow1','RKSS_EmberFollow2'],
        'next_at':{'RKSS_Ember':1.4333333,'RKSS_EmberFollow1':1.1333333}},
    'weapon_dummies':dummies,'clips':{},
    # Slow the authored anticipation, then retain the original strike speed.
    # Both ordinary releases start immediately but contact after a light cut.
    'heavy':{'stages':[],'windup':{'seconds':.24,'tap_rate':.45,'held_rate':.32}},
    'jump':{'start':'RKSS_PlungeStart','loop':'RKSS_PlungeLoop','land':'RKSS_PlungeLand','land_idle_at':1.4},
    'verification':{'runtime':False}}
for name,(bank,animid) in selection.items():
    anim=next(x for x in banks[bank] if x['ID']==animid)
    data=read('build/animations/'+name+'.json')
    assert data.get('retarget_revision')=='gltf-basis-anatomical-v3','Rejected legacy retarget: '+name
    assert data['name']==name and data['frames']>1
    for track in data['tracks']:
        assert len(track['keys'])==data['frames']
        assert all(all(math.isfinite(v) for v in k['t']+k['q']+k['s']) for k in track['keys'])
    events=anim['Events'];hits=[];stamina=0
    for event in events:
        if event['Type']!='Unk001':continue
        judge=event['Data']['Condition'];behavior=behaviors.get((2330,judge),behaviors.get((2300,judge)))
        assert behavior and behavior['refid'] in attacks,(name,judge)
        attack=attacks[behavior['refid']]
        art_attack=name in ('RKSS_Ember','RKSS_EmberFollow1','RKSS_EmberFollow2','RKSS_EmberHeavy')
        buff=90 if art_attack else 0
        collision=[]
        for i in range(4):
            a,b=attack[f'hit{i}_dmypoly1'],attack[f'hit{i}_dmypoly2'];radius=attack[f'hit{i}_radius']
            if radius<=0 or a<0:continue
            assert str(a) in dummies and (b<0 or str(b) in dummies),(name,a,b)
            collision.append({'a':a,'b':b if b>=0 else a,'radius_cm':radius*100})
        first_light=name=='RKSS_Light1'
        first_heavy=name in ('RKSS_Heavy1Charge','RKSS_Heavy1Release')
        strike_scale=first_light_damage_scale if first_light else first_heavy_damage_scale if first_heavy else 1
        if name.startswith('RKSS_Heavy'):
            strike_scale*=heavy_damage_scale
        if art_attack:
            strike_scale*=art_damage_scale
        physical=attack['atkphys']+profile['base_physical']*attack['atkphyscorrection']/100
        fire=attack['atkfire']+(profile['base_fire']+buff)*attack['atkfirecorrection']/100
        reference=None
        if name.startswith('RKSS_Light'):
            reference=light_reference
        elif name in resource_references:
            reference=resource_references[name][len(hits)]
        if name.startswith('RKSS_Light'):
            poise=first_light_poise if first_light else base_poise
        elif first_heavy:
            poise=first_heavy_poise
        elif name in ('RKSS_Heavy2Charge','RKSS_Heavy2Release'):
            poise=follow_heavy_poise
        elif reference:
            poise=reference['Damage.Attack.Target.PoiseDamage']
        else:
            poise=attack['atkstam']+weapon['atkbasestamina']*attack['atkstamcorrection']/100
        final_physical=physical*strike_scale
        final_anger=reference['Damage.Attack.Target.AngerDamage']*(art_anger_scale if art_attack else 1)*enemy_anger_scale if reference else 0
        if name=='RKSS_EmberHeavy':
            final_physical=heavy_art_override['physical']
            final_anger=heavy_art_override['anger']
        hits.append({'start':event['StartTime'],'finish':event['EndTime'],'behavior':judge,'attack_id':behavior['refid'],
            'physical':final_physical,'fire':fire*strike_scale,'poise':poise,'capsules':collision,
            'anger':final_anger,
            'ultimate_charge_regen':reference.get('Damage.Attack.Attacker.UltimateChargeRegen',0) if reference else 0,
            'hit_anger_multiplier':reference['Damage.Attack.Target.HitAngerDamageMultiplier'] if reference else 0})
        stamina=max(stamina,behavior['stamina'])
    jump=lambda id:min((e['StartTime'] for e in events if e['Type']=='JumpTable' and e['Data']['JumpTableID']==id),default=data['duration'])
    profile['clips'][name]={'source':f'a{bank:03}_{animid:06}','asset':'/HuaShira/Mods/RingedKnight/Animations/A_'+name+'.A_'+name,
        'duration':data['duration'],'frames':data['frames'],'fps':data['fps'],'stamina':stamina,'focus':0,
        'combo_open':jump(4),'heavy_combo_open':min(jump(116),jump(4)),'light_combo_open':min(jump(115),jump(4)),
        'guard_open':jump(22),'move_open':jump(11),'dodge_open':jump(26),'hits':hits,'root_motion':data['root_motion'],
        'animation_sha256':hashlib.sha256((root/'build/animations'/f'{name}.json').read_bytes()).hexdigest()}
for index in (1,2):
    charge=f'RKSS_Heavy{index}Charge';release=f'RKSS_Heavy{index}Release'
    source_anim=next(a for a in banks[23] if a['ID']==selection[charge][1])
    gate=next(e for e in source_anim['Events'] if e['Type']=='CreateSpEffect2' and e['Data'].get('SpEffectID')==100280)
    profile['heavy']['stages'].append({'charge':charge,'release':release,'release_open':gate['StartTime'],'release_close':gate['EndTime'],
        'normal_stamina':profile['clips'][release]['stamina'],'charged_stamina':profile['clips'][charge]['stamina'],
        'next_stage':2 if index==1 else 1})
previous=read('build/combat-profile.json')
for key in ('attachments','retarget_revision','mesh_basis_verified'):
    if key in previous:profile[key]=previous[key]
for name,clip in profile['clips'].items():
    old=previous['clips'].get(name,{})
    if clip['animation_sha256']==old.get('animation_sha256'):
        for key in ('dummy_tracks','blade_tracks'):
            if key in old:clip[key]=old[key]
(root/'build/combat-profile.json').write_text(json.dumps(profile,separators=(',',':')))
print('COMBAT_PROFILE_READY',json.dumps({'clips':len(profile['clips']),'guard':profile['guard'],'bomb':profile['bomb']}))
