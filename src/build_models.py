"""Run in a fresh background Blender; export original DS3 weapon geometry."""
import bpy, json, math, pathlib, sys, subprocess
from mathutils import Vector
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/soul-python'))
import numpy as np
from soulstruct.flver import FLVER
from soulstruct.containers import TPF
output=pathlib.Path('build/asset-export')
inputs=pathlib.Path('private/asset-input')
output.mkdir(exist_ok=True,parents=True)
(inputs/'textures').mkdir(exist_ok=True,parents=True)
print('BACKGROUND_SCENE',bpy.app.version_string,bpy.data.filepath,len(bpy.context.scene.objects),bpy.context.mode,flush=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
reports=[]
objects=[]
for label,folder in [('RingedKnightStraightSword','rkss'),('BlackKnightShield','shield')]:
    source=next((root/'extract/ds3/models'/folder).glob('*.flver'))
    flver=FLVER.from_path(source)
    tpf=TPF.from_path(source.with_suffix('.tpf'))
    textures={}
    for texture in tpf.textures:
        dds=inputs/'textures'/(texture.stem+'.dds')
        dds.write_bytes(texture.data)
        png=inputs/'textures'/(texture.stem+'.png')
        converter=root/'tools/soul-python/soulstruct/base/textures/texconv.exe'
        subprocess.run([str(converter),'-nologo','-y','-ft','png','-f','R8G8B8A8_UNORM','-o',str(png.parent),str(dds)],check=True,capture_output=True)
        if not png.exists():
            generated=next(png.parent.glob(texture.stem+'.PNG'))
            generated.rename(png)
        image=bpy.data.images.load(str(png),check_existing=True)
        if not texture.stem.endswith('_a'):image.colorspace_settings.name='Non-Color'
        textures[texture.stem[-1]]=image
    mesh=flver.meshes[0]
    vertices=mesh.vertices
    positions=np.array(vertices['position'])
    normals=np.array(vertices['normal'])
    if not mesh.is_dynamic:
        indices=vertices['normal_w'].reshape(-1).astype(int)
        if mesh.bone_indices is not None:indices=mesh.bone_indices[indices]
        transforms=flver.get_bone_tree().get_bone_armature_space_transforms()
        for index in np.unique(indices):
            translate,rotate,scale=transforms[int(index)]
            mask=indices==index
            positions[mask]=(positions[mask]*scale.data)@rotate.data.T+translate.data
            normals[mask]=normals[mask]@rotate.data.T
    positions=positions[:,[0,2,1]]
    normals=normals[:,[0,2,1]]
    faces=mesh.face_sets[0].triangulate(len(positions)<65535)
    face_normals=np.cross(positions[faces[:,1]]-positions[faces[:,0]],positions[faces[:,2]]-positions[faces[:,0]])
    alignment=np.einsum('ij,ij->i',face_normals,normals[faces].mean(axis=1))
    if np.median(alignment)<0:faces=faces[:,[0,2,1]]
    data=bpy.data.meshes.new(label)
    data.from_pydata(positions.tolist(),[],faces.tolist());data.update()
    uv=data.uv_layers.new(name='UVMap')
    for loop in data.loops:
        value=vertices['uv_0'][loop.vertex_index]
        uv.data[loop.index].uv=(float(value[0]),1-float(value[1]))
    data.normals_split_custom_set_from_vertices(normals.tolist())
    for polygon in data.polygons:polygon.use_smooth=True
    obj=bpy.data.objects.new(label,data);bpy.context.collection.objects.link(obj)
    material=bpy.data.materials.new('M_'+label);material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    shader=nodes.get('Principled BSDF');shader.inputs['Metallic'].default_value=.45;shader.inputs['Roughness'].default_value=.45
    diffuse=nodes.new('ShaderNodeTexImage');diffuse.image=textures['a'];links.new(diffuse.outputs['Color'],shader.inputs['Base Color'])
    # The original packed normal map is retained for UE; preview initially uses
    # supplied geometry normals so DDS channel conventions cannot distort it.
    obj.data.materials.append(material)
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.export_scene.fbx(filepath=str(output/(label+'.fbx')),use_selection=True,object_types={'MESH'},add_leaf_bones=False,axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False)
    reports.append(dict(name=label,vertices=len(data.vertices),triangles=len(data.polygons),dimensions=list(obj.dimensions),source=str(source),fbx=str(output/(label+'.fbx'))))
    objects.append(obj)
objects[0].location=(-.38,0,0);objects[0].rotation_euler=(0,math.pi,0)
objects[1].location=(.44,0,.65)
objects[1].rotation_euler=(0,math.pi/2,0)
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24
scene.render.resolution_x=1200;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.world.use_nodes=True
scene.world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.3,.3,.3,1)
scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.7
camera_data=bpy.data.cameras.new('AssetPreview');camera=bpy.data.objects.new('AssetPreview',camera_data);scene.collection.objects.link(camera)
camera.location=(2.3,-4,1.8);direction=Vector((0,0,.55))-camera.location;camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=1.8;scene.camera=camera
for name,location,power,size in [('Key',(1,-3,3),500,3),('Fill',(-2,-1,1.2),350,2),('Rim',(0,2,2),600,2)]:
    light_data=bpy.data.lights.new(name,'AREA');light_data.energy=power;light_data.shape='DISK';light_data.size=size
    light=bpy.data.objects.new(name,light_data);scene.collection.objects.link(light);light.location=location;light.rotation_euler=(Vector((0,0,.5))-light.location).to_track_quat('-Z','Y').to_euler()
scene.view_settings.view_transform='AgX'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(output/'RingedKnight_Assets.blend'))
(root/'reports/models.json').write_text(json.dumps(reports,indent=2))
scene.render.filepath=str(output/'asset-preview.png');bpy.ops.render.render(write_still=True)
print('MODELS_EXPORTED',json.dumps(reports),flush=True)
