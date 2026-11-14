"""UE editor: native material parent reference; editor placeholders never packaged."""
import unreal,json,pathlib,struct,zlib,binascii
root=pathlib.Path(__file__).resolve().parents[1]
base='/HuaShira/Mods/RingedKnight'
tools=unreal.AssetToolsHelpers.get_asset_tools();eal=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
unreal.AssetRegistryHelpers.get_asset_registry().search_all_assets(True)
parent_path='/Game/PBZContent/Characters/Hero/Weapon/Material/MI_Hun_JueYing'
dummy_path='/Game/RingedKnightEditor/PlaceholderEquipmentMaster'
dummy=unreal.load_asset(dummy_path)
if not dummy:
    dummy=tools.create_asset('PlaceholderEquipmentMaster','/Game/RingedKnightEditor',unreal.Material,unreal.MaterialFactoryNew())
    eal.save_loaded_asset(dummy)
parent=unreal.load_asset(parent_path)
if not parent:
    folder,name=parent_path.rsplit('/',1);eal.make_directory(folder)
    parent=tools.create_asset(name,folder,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(parent,dummy);eal.save_loaded_asset(parent)
assert parent and parent.get_class().get_name()=='MaterialInstanceConstant'

def data_texture(name,rgba,srgb,normal=False):
    # Technical constant textures, 4x4 RGBA8; no external image generator needed.
    path=root/'build/material-inputs'/(name+'.png');path.parent.mkdir(parents=True,exist_ok=True)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    raw=(b'\0'+bytes(rgba)*4)*4
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',4,4,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
    task=unreal.AssetImportTask();task.filename=str(path);task.destination_path=base+'/Textures';task.destination_name=name
    task.factory=unreal.TextureFactory();task.automated=True;task.replace_existing=True;task.save=False
    tools.import_asset_tasks([task]);texture=unreal.load_asset(base+'/Textures/'+name);assert texture
    texture.set_editor_property('srgb',srgb);texture.set_editor_property('virtual_texture_streaming',True)
    if normal:texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
    eal.save_loaded_asset(texture);return texture
normal=data_texture('T_EquipmentFlatNormal',(128,128,255,255),False,True)
mix=data_texture('T_EquipmentMix',(255,255,255,255),False)
white=data_texture('T_EquipmentWhite',(255,255,255,255),True)
report={'parent':parent_path,'placeholder_roots':['/Game/RingedKnightEditor',parent_path],
        'shader_policy':'native parent; parameter overrides only; no static permutations','materials':[],'runtime_verified':False}

def instance(name,albedo,tint,metallic,roughness,normal_texture=None,mix_texture=None):
    asset=unreal.load_asset(base+'/Materials/'+name)
    if not asset:asset=tools.create_asset(name,base+'/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    assert asset and asset.get_class().get_name()=='MaterialInstanceConstant'
    assert unreal.RingedKnightEditorLibrary.configure_equipment_material(asset,parent,albedo,normal_texture or normal,mix_texture or mix,unreal.LinearColor(*tint,0),metallic,roughness)
    eal.save_loaded_asset(asset)
    report['materials'].append({'path':asset.get_path_name(),'class':asset.get_class().get_name(),'parent':parent.get_path_name(),'layer':0,
        'textures':{'albedo':albedo.get_path_name(),'normal':(normal_texture or normal).get_path_name(),'mix':(mix_texture or mix).get_path_name()}})
    return asset
conversion=json.loads((root/'reports/pbr-conversion.json').read_text())
for item in conversion['materials']:
    name=item['name'];textures={}
    for role,suffix,srgb,compression in [('albedo','BaseColor',True,unreal.TextureCompressionSettings.TC_DEFAULT),
            ('normal','Normal',False,unreal.TextureCompressionSettings.TC_NORMALMAP),
            ('mix','ARM',False,unreal.TextureCompressionSettings.TC_MASKS)]:
        task=unreal.AssetImportTask();task.filename=item['files'][role]['file'];task.destination_path=base+'/Textures';task.destination_name='T_'+name+'_'+suffix
        task.factory=unreal.TextureFactory();task.automated=True;task.replace_existing=True;task.save=False
        tools.import_asset_tasks([task]);texture=unreal.load_asset(base+'/Textures/'+task.destination_name);assert texture
        texture.set_editor_property('srgb',srgb);texture.set_editor_property('virtual_texture_streaming',True);texture.set_editor_property('compression_settings',compression)
        if role=='normal':texture.set_editor_property('flip_green_channel',False)
        eal.save_loaded_asset(texture);textures[role]=texture
    mat=instance('MI_'+name,textures['albedo'],(1,1,1),1,1,textures['normal'],textures['mix'])
    mesh=unreal.load_asset(base+'/Meshes/SM_'+name);assert mesh
    mesh.set_material(0,mat);eal.save_loaded_asset(mesh)
if (root/'reports/native-bomb-textures.json').is_file():
    # The old three-slot proxy used T_EquipmentWhite; Albedo Controls.A=0 in
    # the native parent means its RGB tint did not color the texture. Keep the
    # real native grenade + UV textures when the full material pipeline is run.
    import runpy
    report['bomb_native_import']=runpy.run_path(str(root/'src/import_bomb_prop.py'))['main']()
else:
    pot=unreal.load_asset(base+'/Meshes/SM_RopeBlackFirebomb');assert pot
    for i,color in enumerate([(.035,.025,.02),(.12,.07,.03),(.26,.19,.1)]):
        pot.set_material(i,instance('MI_RopeBomb_'+str(i),white,color,0,.85))
    eal.save_loaded_asset(pot)
for obsolete in ['M_RingedKnightStraightSword','M_BlackKnightShield','M_RopeBomb_0','M_RopeBomb_1','M_RopeBomb_2']:
    path=base+'/Materials/'+obsolete
    if eal.does_asset_exist(path):assert eal.delete_asset(path),'Could not remove obsolete own master material: '+path
(root/'reports/native-material-build.json').write_text(json.dumps(report,indent=2))
unreal.log('RK_NATIVE_MATERIALS_READY '+str(len(report['materials'])))
