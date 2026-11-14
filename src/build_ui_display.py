"""Offline Blender UI/display builder; never writes source assets or active scene.

Run with Blender 5.2 --background PBR_Assets.blend --python-exit-code 1
--python src/build_ui_display.py -- [--inspect|--preview|--final].
Technical alpha/mask packing is local Pillow, with no generated artwork.
"""
import bpy
import json
import math
import pathlib
import sys
import hashlib
from mathutils import Vector, Matrix
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path('build/asset-export')
UI = ROOT / 'build/ui-inputs'
UI.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'tools/python-libs'))
from PIL import Image
sys.path.insert(0, str(ROOT / 'src'))
from fit_ui_preview_textures import SCALE as PREVIEW_CANVAS_SCALE, write_fitted_previews

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
mode = args[0] if args else '--final'
source = pathlib.Path(bpy.data.filepath)
assert source.name == 'PBR_Assets.blend', source
meshes = [bpy.data.objects.get(n) for n in ['RingedKnightStraightSword', 'BlackKnightShield']]
assert all(m and m.type == 'MESH' for m in meshes), 'Expected source sword and shield'
def object_info(o):
    return dict(name=o.name, location=list(o.location), rotation=list(o.rotation_euler),
                dimensions=list(o.dimensions), vertices=len(o.data.vertices),
                triangles=sum(len(p.vertices)-2 for p in o.data.polygons),
                materials=[m.name if m else None for m in o.data.materials],
                local_min=[min(v.co[i] for v in o.data.vertices) for i in range(3)],
                local_max=[max(v.co[i] for v in o.data.vertices) for i in range(3)])
initial = dict(blender=bpy.app.version_string, source=str(source), mode=bpy.context.mode,
               active=bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
               objects=[object_info(m) for m in meshes])
print('RKA_DISPLAY_SOURCE ' + json.dumps(initial), flush=True)
if mode == '--inspect':
    (ROOT / 'reports/ui-source-inspection.json').write_text(json.dumps(initial, indent=2))
    raise SystemExit(0)
if mode == '--verify-export':
    report_path = ROOT / 'reports/UIAssets.json'
    report = json.loads(report_path.read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=report['mesh_fbx'], use_anim=False)
    rigs = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    imported = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    assert len(rigs) == len(imported) == 1, (len(rigs),len(imported))
    mesh, rig = imported[0], rigs[0]
    assert [b.name for b in rig.data.bones] == ['root']
    assert len(mesh.data.vertices) == report['vertex_count']
    assert sum(len(p.vertices)-2 for p in mesh.data.polygons) == report['triangle_count']
    assert [m.name for m in mesh.data.materials] == report['material_slots']
    assert all(len(v.groups) == 1 and abs(v.groups[0].weight-1.0) < 1e-6 for v in mesh.data.vertices)
    assert mesh.vertex_groups[0].name == 'root'
    report['fbx_roundtrip'] = dict(meshes=1, armatures=1, bones=['root'],
        vertices=len(mesh.data.vertices), dimensions_m=list(mesh.dimensions),
        fully_weighted_to_root=True, material_slots=[m.name for m in mesh.data.materials])
    for item in report['textures']:
        p = pathlib.Path(item['source'])
        im = Image.open(p).convert('RGBA')
        box = im.getchannel('A').getbbox()
        assert box and all(0 < box[i] < im.width for i in range(4)), (p,box)
        assert list(im.size) == item['size']
        if p.stem == 'T_RKA_Upgrade':
            channels = im.split()
            assert all(ch.tobytes() == channels[3].tobytes() for ch in channels[:3])
        if p.stem == 'T_RKA_White':
            assert all(im.getchannel(c).getextrema() == (255,255) for c in 'RGB')
        item['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        item['alpha_bounds'] = list(box)
    report['mesh_fbx_sha256'] = hashlib.sha256(pathlib.Path(report['mesh_fbx']).read_bytes()).hexdigest()
    report['validation']['fbx_roundtrip'] = True
    report['validation']['ui_pixels_checked'] = True
    report_path.write_text(json.dumps(report, indent=2))
    print('RKA_UI_DISPLAY_VERIFIED ' + json.dumps(report['fbx_roundtrip']), flush=True)
    raise SystemExit(0)

# Work on copied datablocks in this independent process and new saved file.
for o in bpy.context.scene.objects:
    o.hide_render = o.type not in {'MESH', 'LIGHT', 'CAMERA'}
for o in [o for o in bpy.context.scene.objects if o.type == 'MESH' and o not in meshes]:
    o.hide_render = True
for obj in meshes:
    obj.data = obj.data.copy()
    obj.hide_render = False
    obj.hide_set(False)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 32 if mode == '--preview' else 80
scene.cycles.use_denoising = True
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
scene.render.resolution_x = scene.render.resolution_y = 512 if mode == '--preview' else 1024
scene.render.resolution_percentage = 100
scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.3

# Align the actual shield plane. Its long axis is diagonal in the extracted
# model, so a quarter-turn about the model Y axis leaves its face tilted.
sword, shield = meshes
points = np.asarray([tuple(v.co) for v in shield.data.vertices])
_, axes = np.linalg.eigh(np.cov(points.T))
long_axis = Vector(axes[:, 2])
normal = Vector(axes[:, 0])
if long_axis.x < 0:
    long_axis.negate()
if normal.y > 0:
    normal.negate()
width_axis = normal.cross(long_axis).normalized()
source_basis = Matrix((long_axis, width_axis, normal)).transposed()
# Front is -Y, with the decorated shield face looking toward the camera.
target_basis = Matrix(((0, 0, 1), (-1, 0, 0), (0, -1, 0))).transposed()
shield.rotation_mode = sword.rotation_mode = 'QUATERNION'
shield.rotation_quaternion = (target_basis @ source_basis.transposed()).to_quaternion()
sword.rotation_quaternion = Matrix.Rotation(math.pi, 3, 'Y').to_quaternion()
# Keep the complete blade, hilt and shield silhouettes separate. Set the gap
# from actual rotated geometry bounds, not object origins or unrotated axes.
display_gap = .10
projected_bounds = {}
for obj in meshes:
    obj.scale = (1, 1, 1)
    rotated = [obj.rotation_quaternion @ v.co for v in obj.data.vertices]
    lo = Vector(tuple(min(v[i] for v in rotated) for i in range(3)))
    hi = Vector(tuple(max(v[i] for v in rotated) for i in range(3)))
    horizontal = -display_gap/2-hi.x if obj == sword else display_gap/2-lo.x
    obj.location = (horizontal, -(lo.y+hi.y)/2, .7-(lo.z+hi.z)/2)
    projected_bounds[obj.name] = dict(min=list(lo+obj.location), max=list(hi+obj.location))
bpy.context.view_layer.update()
composition = dict(revision='upright-separated-sword-shield-v2',
    source_shield_long_axis=list(long_axis), source_shield_front=list(normal),
    gap_m=display_gap, projected_bounds=projected_bounds,
    transforms=[dict(name=o.name, location=list(o.location),
                     quaternion=list(o.rotation_quaternion), scale=list(o.scale)) for o in meshes])

# Use one measured, near-frontal view for the transparent image and rigid
# display geometry, preserving the original PBR material and model scale.
camera = scene.camera
assert camera and camera.type == 'CAMERA'
camera.data.type = 'ORTHO'
camera.rotation_euler = Vector((0, 1, 0)).to_track_quat('-Z', 'Y').to_euler()
world_vertices = [obj.matrix_world @ v.co for obj in meshes for v in obj.data.vertices]
world_center = sum(world_vertices, Vector()) / len(world_vertices)
rotation = camera.rotation_euler.to_matrix()
view_vertices = [rotation.transposed() @ v for v in world_vertices]
lo = Vector(tuple(min(v[i] for v in view_vertices) for i in range(3)))
hi = Vector(tuple(max(v[i] for v in view_vertices) for i in range(3)))
view_center = (lo + hi) / 2
center = rotation @ view_center
camera.location = center + rotation @ Vector((0, 0, 4))
camera.data.ortho_scale = max(hi.x-lo.x, hi.y-lo.y) / .86
composition['full_canvas_gap_fraction'] = display_gap/camera.data.ortho_scale
assert composition['full_canvas_gap_fraction'] >= .04, 'Sword/shield gap is too small'

render_file = UI / ('preview.png' if mode == '--preview' else 'T_RKA_Render_full.png')
scene.render.filepath = str(render_file)
bpy.ops.render.render(write_still=True)
render = Image.open(render_file).convert('RGBA')
alpha = render.getchannel('A')
bounds = alpha.getbbox()
assert bounds and all(0 < bounds[i] < render.width for i in range(4)), bounds
if mode == '--preview':
    print('RKA_DISPLAY_PREVIEW ' + str(render_file) + ' BOUNDS ' + str(bounds), flush=True)
    raise SystemExit(0)

# W_WeaponUI.weapon and weapon_1 inherit -45 degrees from Overlay_0/1.
# Precompensate their shared small texture, while the large render stays upright.
icon = render.crop(bounds).rotate(-45, Image.Resampling.BICUBIC, expand=True)
icon = icon.crop(icon.getchannel('A').getbbox())
icon.thumbnail((440, 440), Image.Resampling.LANCZOS)
icon_canvas = Image.new('RGBA', (512, 512))
icon_canvas.paste(icon, ((512-icon.width)//2, (512-icon.height)//2))
icon = icon_canvas
icon.save(UI / 'T_RKA_Icon.png')
composition['small_icon_clockwise_degrees'] = 45
composition['native_hud_parent_degrees'] = -45
hud_native = icon.rotate(45, Image.Resampling.BICUBIC, expand=True)
hud_preview = hud_native.crop(hud_native.getchannel('A').getbbox())
hud_preview.thumbnail((260, 360), Image.Resampling.LANCZOS)
hud_canvas = Image.new('RGBA', (360, 400))
hud_canvas.paste(hud_preview, ((360-hud_preview.width)//2, (400-hud_preview.height)//2))
hud_preview_file = OUT / 'RKA_HudIconPreview.png'
hud_canvas.save(hud_preview_file)
hud_columns = [max(hud_native.getchannel('A').crop((x, 0, x+1, hud_native.height)).getdata())
               for x in range(hud_native.width)]
occupied = [x for x, value in enumerate(hud_columns) if value]
gaps = []
start = None
for x in range(min(occupied), max(occupied)+1):
    if hud_columns[x] == 0 and start is None:
        start = x
    elif hud_columns[x] and start is not None:
        gaps.append(x-start)
        start = None
composition['hud_native_rotated_canvas_size'] = list(hud_native.size)
composition['hud_native_gap_pixels'] = max(gaps, default=0)
composition['hud_native_gap_fraction'] = composition['hud_native_gap_pixels']/hud_native.width
assert composition['hud_native_gap_fraction'] >= .04, 'HUD silhouettes overlap or gap is too small'
composition['hud_preview'] = str(hud_preview_file)
composition['hud_evidence'] = dict(asset='/Game/PBZContent/UI/Hud/W_WeaponUI',
    images=['weapon', 'weapon_1'], parent_overlays=['Overlay_0', 'Overlay_1'],
    parent_angle_degrees=-45)
white = Image.new('RGBA', icon.size, (255,255,255,0))
white.putalpha(icon.getchannel('A'))
white.save(UI / 'T_RKA_White.png')
# Pickup and upgrade use the same render canvas. Fit it after making the
# independent small icons, then derive the upgrade wipe mask from fitted alpha.
full_alpha_bounds = bounds
render = write_fitted_previews(render, UI)
alpha = render.getchannel('A')
bounds = alpha.getbbox()

# Display is the exact same pair with its PBR UVs, joined into one rigid mesh.
# New mesh/armature paths only: no PBZ skeleton or runtime mesh is reused.
for obj in meshes:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials[0].name = 'MI_' + obj.name
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()
combined = bpy.context.view_layer.objects.active
combined.name = 'SK_RKA_Display'
combined.data.name = 'RKA_Display_Geometry'
# Recenter in X/Y while keeping Z base at zero. Source dimensions remain m.
coords = [v.co.copy() for v in combined.data.vertices]
offset = Vector(((min(v.x for v in coords)+max(v.x for v in coords))/2,
                 (min(v.y for v in coords)+max(v.y for v in coords))/2,
                 min(v.z for v in coords)))
for v in combined.data.vertices:
    v.co -= offset
camera.location -= offset
for lamp in [o for o in scene.objects if o.type == 'LIGHT']:
    lamp.location -= offset
arm_data = bpy.data.armatures.new('RKA_Display_Skeleton')
arm = bpy.data.objects.new('Armature', arm_data)
scene.collection.objects.link(arm)
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
bone = arm_data.edit_bones.new('root')
bone.head = (0,0,0)
bone.tail = (0,0,.15)
bpy.ops.object.mode_set(mode='OBJECT')
group = combined.vertex_groups.new(name='root')
group.add(list(range(len(combined.data.vertices))), 1.0, 'REPLACE')
modifier = combined.modifiers.new('RKA_RigidDisplaySkin','ARMATURE')
modifier.object = arm
combined.parent = arm
bpy.ops.object.select_all(action='DESELECT')
combined.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = combined
fbx = OUT / 'SK_RKA_Display.fbx'
bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True,
    object_types={'ARMATURE','MESH'}, add_leaf_bones=False, use_armature_deform_only=True,
    axis_forward='-Y', axis_up='Z', apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_NONE', bake_anim=False, use_tspace=True,
    mesh_smooth_type='FACE', path_mode='STRIP', embed_textures=False)
bpy.ops.file.pack_all()
blend = OUT / 'RKA_DisplayAssets.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))

report = dict(source_blend=str(source), generated_blend=str(blend),
    source_objects=initial['objects'], composition=composition,
    render_size=list(render.size), render_alpha_bounds=list(bounds),
    alpha_coverage=sum(1 for v in alpha.getdata() if v)/len(alpha.getdata()),
    preview_canvas=dict(scale=PREVIEW_CANVAS_SCALE, full_source=str(render_file),
                        before_alpha_bounds=list(full_alpha_bounds), after_alpha_bounds=list(bounds),
                        size=list(render.size), mask_aligned=True),
    mesh_fbx=str(fbx), mesh_asset='/HuaShira/Mods/RingedKnight/Meshes/SK_RKA_Display.SK_RKA_Display',
    skeleton_asset='/HuaShira/Mods/RingedKnight/Meshes/SK_RKA_Display_Skeleton.SK_RKA_Display_Skeleton',
    bones=['root'], material_slots=[m.name for m in combined.data.materials],
    vertex_count=len(combined.data.vertices), triangle_count=sum(len(p.vertices)-2 for p in combined.data.polygons),
    physics_asset=False, runtime_static_meshes_modified=False, expected_new_asset_count=6,
    textures=[dict(source=str(UI/(name+'.png')), asset='/HuaShira/Mods/RingedKnight/UI/'+name+'.'+name,
                   size=list(Image.open(UI/(name+'.png')).size), srgb=name in {'T_RKA_Icon','T_RKA_Render','T_RKA_White'},
                   sha256=hashlib.sha256((UI/(name+'.png')).read_bytes()).hexdigest())
              for name in ['T_RKA_Icon','T_RKA_Render','T_RKA_White','T_RKA_Upgrade']],
    validation={'background_rendered':True, 'visually_reviewed':False, 'ue_imported':False,
                'preview_textures_pending_import':True, 'game_verified':False})
(ROOT / 'reports/UIAssets.json').write_text(json.dumps(report, indent=2))
print('RKA_UI_DISPLAY_READY ' + json.dumps(report), flush=True)
