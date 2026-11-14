import bpy,json,pathlib,math,sys
from mathutils import Matrix,Quaternion,Vector
root=pathlib.Path(__file__).resolve().parents[1]
output=pathlib.Path('build/asset-export')
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
clip_name=args[0] if args else 'RKSS_Light1'
source_file=args[1] if len(args)>1 else None
source=bpy.data.objects['DS3_Source'];target=bpy.data.objects['PBZ_Target'];scene=bpy.context.scene
if source_file:
    # Reuse the original target workbench, with a fresh source action per clip.
    for obj in list(bpy.data.objects):
        if obj.get('pipeline_role')=='source':bpy.data.objects.remove(obj,do_unlink=True)
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=source_file)
    imported=set(bpy.data.objects)-before
    source=next(o for o in imported if o.type=='ARMATURE');source.name='DS3_Source'
    for obj in imported:obj['pipeline_role']='source'
source_fps=scene.render.fps/scene.render.fps_base
mapping={'root':'Master_control','pelvis':'Pelvis_control','spine_01':'Spine_control','spine_02':'Spine_control','spine_03':'Spine1_control','spine_04':'Spine2_control','spine_05':'Spine2_control','neck_01':'Neck_control','neck_02':'Neck_control','head':'Head'}
for side,letter in [('l','L'),('r','R')]:
    for dst,src in [('clavicle','Clavicle_control'),('upperarm','UpperArm_control'),('lowerarm','Forearm_control'),('hand','Hand_control'),('thigh','Thigh_control'),('calf','Calf_control'),('foot','Foot_control'),('ball','Toe0')]:mapping[dst+'_'+side]=letter+'_'+src
    for finger,index in [('thumb',0),('index',1),('middle',2),('ring',3),('pinky',4)]:
        for segment,suffix in [(1,str(index)+'_control'),(2,str(index)+'1_control'),(3,str(index)+'2')]:mapping[f'{finger}_{segment:02}_{side}']=f'{letter}_Finger{suffix}'
mapping={t:s for t,s in mapping.items() if t in target.pose.bones and s in source.pose.bones}
native=json.loads((root/'extract/pbz/ProjectPBZ/Plugins/HuaShira/Content/Characters/Hero/Hero_Hun/Hun_Skin_Skeleton.Hun_Skin_Skeleton.skel.json').read_text())
native_bones={b['name'].lower():b for b in native['bones']}
native_world={}
for b in native['bones']:
    q=b['q'];local=Matrix.LocRotScale(Vector(b['t']),Quaternion((q[3],q[0],q[1],q[2])),Vector(b['s']))
    parent=native['bones'][b['parent']]['name'].lower() if b['parent']>=0 else None
    native_world[b['name'].lower()]=native_world[parent]@local if parent else local
# UE is left handed Z-up; CUE4Parse/glTF/Blender use the reflected Y basis.
conversion=Matrix.Diagonal(Vector((1,-1,1,1)))
corrections={}
for bone in target.data.bones:
    original=conversion@native_world[bone.name.lower()]@conversion
    original.translation/=100
    corrections[bone.name]=original.inverted_safe()@bone.matrix_local
source_rest={s:source.data.bones[s].matrix_local.to_quaternion() for s in set(mapping.values())}
target_rest={b.name:b.matrix_local.copy() for b in target.data.bones}
reference_bones=json.loads((root/'reports/ds3-reference-bones.json').read_text())
reference={b['name']:Vector((b['t'][0],b['t'][2],b['t'][1])) for b in reference_bones}
source_conversion=Matrix(((1,0,0),(0,0,1),(0,1,0)))
source_rest={b['name']:(source_conversion@Matrix(b['r'])@source_conversion).to_quaternion() for b in reference_bones}
def original(name):return name.removesuffix('_control')
def basis(side,up):
    z=up.normalized();x=(side-z*side.dot(z)).normalized();y=z.cross(x).normalized()
    return Matrix((x,y,z)).transposed().to_quaternion()
def body_frame(positions,chest=False):
    if chest:return basis(positions['L_UpperArm']-positions['R_UpperArm'],positions['Neck']-positions['Spine1'])
    return basis(positions['L_Thigh']-positions['R_Thigh'],positions['Spine']-positions['Pelvis'])
def hand_frame(positions,letter):
    return basis(positions[letter+'_Finger1']-positions[letter+'_Finger4'],positions[letter+'_Finger2']-positions[letter+'_Hand'])
aim={}
for side,letter in [('l','L'),('r','R')]:
    for target_name,start,end in [('clavicle','Clavicle','UpperArm'),('upperarm','UpperArm','Forearm'),('lowerarm','Forearm','Hand'),('thigh','Thigh','Calf'),('calf','Calf','Foot'),('foot','Foot','Toe0')]:aim[target_name+'_'+side]=(letter+'_'+start,letter+'_'+end)
    for finger,index in [('thumb',0),('index',1),('middle',2),('ring',3),('pinky',4)]:
        aim[finger+'_01_'+side]=(letter+'_Finger'+str(index),letter+'_Finger'+str(index)+'1')
        aim[finger+'_02_'+side]=(letter+'_Finger'+str(index)+'1',letter+'_Finger'+str(index)+'2')
        aim[finger+'_03_'+side]=aim[finger+'_02_'+side]
scene.frame_set(0);bpy.context.view_layer.update()
master=source.matrix_world@source.pose.bones['Master_control'].matrix
heading=Quaternion((1,0,0,0))
initial_master=master.translation.copy()
ratio=target.data.bones['pelvis'].head_local.z/.97
source_action=source.animation_data.action
duration=(source_action.frame_range[1]-source_action.frame_range[0])/source_fps
count=round(duration*60)+1
action=bpy.data.actions.new(clip_name);target.animation_data_create();target.animation_data.action=action
names=set(mapping)|{n for n in target.pose.bones.keys() if n.startswith('weapon_') or n.startswith('ik_weapon_')}
tracks={name:[] for name in names};root_motion=[]
for frame in range(count):
    sample=frame*source_fps/60
    scene.frame_set(math.floor(sample),subframe=sample%1);bpy.context.view_layer.update()
    source_positions={original(b.name):(source.matrix_world@b.matrix).translation for b in source.pose.bones}
    pelvis_delta=body_frame(source_positions)@body_frame(reference).inverted()
    chest_delta=body_frame(source_positions,True)@body_frame(reference,True).inverted()
    for bone in target.pose.bones:bone.matrix_basis=Matrix.Identity(4)
    bpy.context.view_layer.update()
    for bone in target.pose.bones:
        if bone.name not in mapping:continue
        name=mapping[bone.name]
        pose=source.matrix_world@source.pose.bones[name].matrix@Matrix.Rotation(-math.pi/2,4,'X')
        # glTF visualization has identity inverse-bind matrices. Its edit-bone
        # pose is therefore NOT the reference pose. Original FLVER reference
        # rotations give the correct global rotation delta, including limb roll.
        # Direction cross-check against animated joint positions passed at 0 deg
        # for arm/leg segments (reports/source-rotation-probe.json).
        delta=pose.to_quaternion()@source_rest[original(name)].inverted()
        if bone.name=='root':delta=Quaternion((1,0,0,0))
        rotation=heading@delta@target_rest[bone.name].to_quaternion()
        if bone.name=='root':
            position=heading@(pose.translation-initial_master)*ratio
        elif bone.name=='pelvis':
            position=heading@(pose.translation-initial_master)*ratio
        else:
            local_rest=bone.parent.bone.matrix_local.inverted_safe()@bone.bone.matrix_local if bone.parent else bone.bone.matrix_local
            position=(bone.parent.matrix@local_rest).translation if bone.parent else target_rest[bone.name].translation
        bone.rotation_mode='QUATERNION';bone.matrix=Matrix.LocRotScale(position,rotation,Vector((1,1,1)))
        bpy.context.view_layer.update()
    # Keep weapon and IK sockets with the hands using their original offsets.
    for side in ('l','r'):
        hand=target.pose.bones['hand_'+side]
        for name in ('weapon_'+side,'ik_weapon_'+side):
            if name in target.pose.bones:
                target.pose.bones[name].matrix=hand.matrix@target_rest['hand_'+side].inverted_safe()@target_rest[name]
    bpy.context.view_layer.update()
    root_offset=target.pose.bones['root'].matrix.translation*100
    root_motion.append([root_offset.x,-root_offset.y,root_offset.z])
    for name in names:
        bone=target.pose.bones[name]
        bone.keyframe_insert('location',frame=frame,group=name)
        bone.keyframe_insert('rotation_quaternion',frame=frame,group=name)
        bone.keyframe_insert('scale',frame=frame,group=name)
        global_native=bone.matrix@corrections[name].inverted_safe()
        global_native.translation*=100
        global_native=conversion@global_native@conversion
        if bone.parent:
            parent=bone.parent.matrix@corrections[bone.parent.name].inverted_safe()
            parent.translation*=100;parent=conversion@parent@conversion
            local=parent.inverted_safe()@global_native
        else:local=global_native
        t,q,s=local.decompose()
        # Runtime applies the separately recorded root displacement with a swept
        # actor move; the mesh clip stays in place to keep collision synchronized.
        if name=='root':t=Vector((0,0,0))
        tracks[name].append(dict(t=list(t),q=[q.x,q.y,q.z,q.w],s=list(s)))
scene.render.fps=60;scene.frame_start=0;scene.frame_end=count-1
scene.frame_set(18);bpy.context.view_layer.update()
payload=dict(name=clip_name,fps=60,frames=count,duration=duration,mapping=mapping,root_motion=root_motion,tracks=[dict(name=name,keys=keys) for name,keys in tracks.items()])
(root/'build/basis-experiment').mkdir(exist_ok=True,parents=True)
(root/('build/basis-experiment/'+clip_name+'.json')).write_text(json.dumps(payload,separators=(',',':')))
bpy.ops.wm.save_as_mainfile(filepath=str(output/('Basis_'+clip_name+'.blend')))
print('RETARGET_EXPORTED',json.dumps(dict(frames=count,duration=duration,bones=len(names),mapping=len(mapping))),flush=True)
