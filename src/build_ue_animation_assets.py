import unreal,json,pathlib,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
profile=json.loads((root/'build/combat-profile.json').read_text())
skeleton=unreal.load_asset('/HuaShira/Characters/Hero/Hero_Hun/Hun_Skin_Skeleton');assert skeleton
assets=[]
for name,clip in profile['clips'].items():
    source=root/'build/animations'/(name+'.json')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==clip['animation_sha256'],'Animation changed since profile build'
    assert 'dummy_tracks' in clip,'Offline collision export is incomplete'
    animation=unreal.RingedKnightEditorLibrary.create_animation('/HuaShira/Mods/RingedKnight/Animations/A_'+name,skeleton,str(source))
    assert animation,'Animation creation failed: '+name
    actual=animation.get_play_length();assert abs(actual-clip['duration'])<1/59,(name,actual,clip['duration'])
    assets.append({'name':name,'asset':animation.get_path_name(),'length':actual,'sha256':clip['animation_sha256']})
tools=unreal.AssetToolsHelpers.get_asset_tools();base='/HuaShira/Mods/RingedKnight'
task=unreal.AssetImportTask();task.filename='build/asset-export/RopeBlackFirebomb.fbx';task.destination_path=base+'/Meshes';task.destination_name='SM_RopeBlackFirebomb';task.factory=unreal.FbxFactory();task.automated=True;task.replace_existing=True;task.save=True
options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False;options.import_materials=False;options.import_textures=False;options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;options.static_mesh_import_data.combine_meshes=True;options.static_mesh_import_data.convert_scene=True;options.static_mesh_import_data.convert_scene_unit=True;task.options=options
tools.import_asset_tasks([task]);mesh=unreal.load_asset(base+'/Meshes/SM_RopeBlackFirebomb');assert mesh
import runpy
runpy.run_path(str(root/'src/build_native_materials.py'))
(root/'reports/ue-animation-assets.json').write_text(json.dumps(assets,indent=2))
unreal.log('RK_ALL_ANIMATIONS_READY '+str(len(assets)))
