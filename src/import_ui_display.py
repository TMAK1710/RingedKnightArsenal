"""UE 5.7 editor commandlet: import only custom UI + rigid display skeletal mesh.

This file deliberately does not launch UE, cook, package or install anything.
Existing runtime meshes and the native PBZ skeleton are never imported here.
"""
import unreal
import json
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = '/HuaShira/Mods/RingedKnight'
EAL = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
report_path = ROOT / 'reports/UIAssets.json'
report = json.loads(report_path.read_text())
preview_only = os.environ.get('PBZ_UI_PREVIEW_ONLY') == '1'
unreal.AssetRegistryHelpers.get_asset_registry().search_all_assets(True)
EAL.make_directory(BASE + '/UI')

def import_asset(source, destination, name, factory, options=None):
    task = unreal.AssetImportTask()
    task.filename = str(source)
    task.destination_path = destination
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.factory = factory
    if options:
        task.options = options
    TOOLS.import_asset_tasks([task])
    asset = unreal.load_asset(destination + '/' + name)
    assert asset, 'Could not import ' + str(source)
    return asset

textures = report['textures']
if preview_only:
    textures = [item for item in textures if Path(item['source']).stem in {'T_RKA_Render', 'T_RKA_Upgrade'}]
    assert len(textures) == 2 and report['preview_canvas']['mask_aligned']
for item in textures:
    name = Path(item['source']).stem
    if preview_only:
        source_hash = hashlib.sha256(Path(item['source']).read_bytes()).hexdigest()
        assert source_hash == item['sha256'], 'Preview source differs from fitted-canvas receipt'
    texture = import_asset(item['source'], BASE + '/UI', name, unreal.TextureFactory())
    assert texture.get_class().get_name() == 'Texture2D', texture.get_class().get_name()
    texture.set_editor_property('srgb', item['srgb'])
    texture.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_UI)
    texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    texture.set_editor_property('compression_settings',
        unreal.TextureCompressionSettings.TC_MASKS if name == 'T_RKA_Upgrade'
        else unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    texture.set_editor_property('virtual_texture_streaming', False)
    texture.set_editor_property('never_stream', True)
    texture.set_editor_property('compression_no_alpha', False)
    texture.set_editor_property('address_x', unreal.TextureAddress.TA_CLAMP)
    texture.set_editor_property('address_y', unreal.TextureAddress.TA_CLAMP)
    assert texture.get_editor_property('srgb') == item['srgb']
    assert not texture.get_editor_property('virtual_texture_streaming')
    assert EAL.save_loaded_asset(texture), 'Could not save ' + name
    item['imported_asset'] = texture.get_path_name()
    item['compression'] = str(texture.get_editor_property('compression_settings'))

if not preview_only:
    EAL.make_directory(BASE + '/Meshes')
    own_skeleton = BASE + '/Meshes/SK_RKA_Display_Skeleton'
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = True
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    options.create_physics_asset = False
    options.skeleton = unreal.load_asset(own_skeleton) if EAL.does_asset_exist(own_skeleton) else None
    data = options.skeletal_mesh_import_data
    data.convert_scene = True
    data.convert_scene_unit = True
    data.import_uniform_scale = 1.0
    # These editor-only UPROPERTY fields lack BlueprintReadWrite in UE 5.7 and
    # therefore are available through reflection, not Python attribute setters.
    data.set_editor_property('import_morph_targets', False)
    data.set_editor_property('update_skeleton_reference_pose', False)
    data.set_editor_property('use_t0_as_ref_pose', False)
    data.set_editor_property('preserve_smoothing_groups', True)
    data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS
    mesh = import_asset(report['mesh_fbx'], BASE + '/Meshes', 'SK_RKA_Display', unreal.FbxFactory(), options)
    assert mesh.get_class().get_name() == 'SkeletalMesh', mesh.get_class().get_name()
    skeleton = mesh.get_editor_property('skeleton')
    assert skeleton and skeleton.get_path_name() == own_skeleton + '.SK_RKA_Display_Skeleton', skeleton
    assert mesh.get_editor_property('physics_asset') is None, 'Unexpected generated PhysicsAsset'

    materials = {name: unreal.load_asset(BASE + '/Materials/' + name)
                 for name in ['MI_RingedKnightStraightSword', 'MI_BlackKnightShield']}
    assert all(materials.values()), 'Required custom native-parent material instances are missing'
    slots = mesh.get_editor_property('materials')
    assert len(slots) == 2, 'Expected exactly sword + shield material slots'
    assigned = []
    for index, slot in enumerate(slots):
        names = [str(slot.get_editor_property(p)) for p in ['imported_material_slot_name', 'material_slot_name']]
        name = next((candidate for candidate in materials if candidate in names), None)
        assert name, 'Unknown display FBX material slot: ' + str(names)
        slot.set_editor_property('material_interface', materials[name])
        assigned.append(dict(index=index, name=name, material=materials[name].get_path_name()))
    mesh.set_editor_property('materials', slots)
    assert EAL.save_loaded_asset(skeleton)
    assert EAL.save_loaded_asset(mesh)

    report['validation']['ue_imported'] = True
    report['ue_display'] = dict(mesh=mesh.get_path_name(), skeleton=skeleton.get_path_name(),
                              physics_asset=None, materials=assigned,
                              generated_assets=report['expected_new_asset_count'])

if 'preview_canvas' in report:
    report['validation']['preview_textures_pending_import'] = False
report_path.write_text(json.dumps(report, indent=2))
if preview_only:
    unreal.log('RKA_UI_PREVIEW_IMPORTED ' + json.dumps(textures))
else:
    unreal.log('RKA_UI_DISPLAY_IMPORTED ' + json.dumps(report['ue_display']))
