"""Offline socket/shape validation in the same retargeted pose used by UE."""
import bpy,json,pathlib,math,sys
from mathutils import Matrix,Vector,Quaternion
root=pathlib.Path(__file__).resolve().parents[1];out=pathlib.Path('build/asset-export')
profile=json.loads((root/'build/combat-profile.json').read_text())
reference={b['name']:b for b in json.loads((root/'reports/ds3-reference-bones.json').read_text())}
native=json.loads((root/'extract/pbz/ProjectPBZ/Plugins/HuaShira/Content/Characters/Hero/Hero_Hun/Hun_Skin_Skeleton.Hun_Skin_Skeleton.skel.json').read_text())
native_world={}
for bone in native['bones']:
    q=bone['q'];local=Matrix.LocRotScale(Vector(bone['t']),Quaternion((q[3],q[0],q[1],q[2])),Vector(bone['s']))
    native_world[bone['name'].lower()]=native_world[native['bones'][bone['parent']]['name'].lower()]@local if bone['parent']>=0 else local
c3=Matrix(((1,0,0),(0,0,1),(0,1,0)));c4=Matrix.Diagonal((1,-1,1,1))
attachments=json.loads((root/'reports/geometric-qa.json').read_text())[0]['bindings'];verification=[]
for side in ('r','l'):attachments[side]['space']='native_hand_from_DS3_dummy_'+('20' if side=='r' else '23')
for clip_name,clip in profile['clips'].items():
    bpy.ops.wm.open_mainfile(filepath=str(out/('Retarget_'+clip_name+'.blend')))
    scene=bpy.context.scene;rig=bpy.data.objects['PBZ_Target'];ratio=rig.data.bones['pelvis'].head_local.z/.97
    relative={};mesh_names={'r':'RingedKnightStraightSword','l':'BlackKnightShield'}
    for side,letter in [('r','R'),('l','L')]:
        hand='hand_'+side;attachment=attachments[side];q=attachment['q']
        native_attachment=Matrix.LocRotScale(Vector(attachment['t']),Quaternion((q[3],q[0],q[1],q[2])),Vector(attachment['s']))
        blender_attachment=c4@native_attachment@c4;blender_attachment.translation/=100
        native_reference=c4@native_world[hand]@c4;native_reference.translation/=100
        import_correction=native_reference.inverted_safe()@rig.data.bones[hand].matrix_local
        relative[side]=import_correction.inverted_safe()@blender_attachment
    curves={d:[] for d in profile['weapon_dummies']}
    for frame in range(clip['frames']):
        scene.frame_set(frame);bpy.context.view_layer.update()
        transform=rig.pose.bones['hand_r'].matrix@relative['r']
        root_motion=Vector(clip['root_motion'][frame])
        for name,point in profile['weapon_dummies'].items():
            p=transform@Vector(point);ue=Vector((p.x,-p.y,p.z))*100-root_motion
            curves[name].append(list(ue))
    clip['dummy_tracks']=curves
    verification.append({'clip':clip_name,'frames':clip['frames'],'dummies':len(curves),'source':clip['source']})
    if '--no-render' in sys.argv or clip_name not in ['RKSS_GuardLoop','RKSS_Light1','RKSS_Ember','RKSS_RopeBomb']:continue
    with bpy.data.libraries.load(str(out/'RingedKnight_Assets.blend'),link=False) as (a,b):b.objects=[n for n in mesh_names.values() if n in a.objects]
    props={o.name.split('.')[0]:o for o in b.objects if o}
    for side,name in mesh_names.items():
        obj=props[name];scene.collection.objects.link(obj);obj.hide_render=False
    sample={'RKSS_GuardLoop':0,'RKSS_Light1':30,'RKSS_Ember':40,'RKSS_RopeBomb':32}[clip_name]
    scene.frame_set(sample);bpy.context.view_layer.update()
    for side,name in mesh_names.items():props[name].matrix_world=rig.pose.bones['hand_'+side].matrix@relative[side]
    clay=bpy.data.materials.new('ValidationClay');clay.use_nodes=True;clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.4,.46,.5,1)
    for obj in list(scene.objects):
        if obj.get('pipeline_role')=='source':obj.hide_render=True
        if obj.type=='MESH' and obj.get('pipeline_role')=='target':obj.data.materials.clear();obj.data.materials.append(clay)
    scene.render.engine='CYCLES';scene.cycles.samples=12;scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.22,.22,.22,1)
    center=rig.pose.bones['pelvis'].matrix.translation.copy();center.z=.95
    data=bpy.data.cameras.new('ValidationCamera');camera=bpy.data.objects.new('ValidationCamera',data);scene.collection.objects.link(camera)
    camera.location=center+Vector((2.5,-4,1.2));camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();data.type='ORTHO';data.ortho_scale=3.2;scene.camera=camera
    for name,offset,power in [('Key',(2,-3,4),700),('Fill',(-2,-1,3),600)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.size=3;light=bpy.data.objects.new(name,data);scene.collection.objects.link(light)
        light.location=center+Vector(offset);light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(out/('offline-'+clip_name+'.png'));bpy.ops.render.render(write_still=True)
    print('POSE_SHAPES_READY',clip_name,flush=True)
profile['attachments']=attachments
profile['retarget_revision']='gltf-basis-anatomical-v3'
(root/'build/combat-profile.json').write_text(json.dumps(profile,separators=(',',':')))
(root/'reports/collision-tracks.json').write_text(json.dumps(verification,indent=2))
print('COLLISION_TRACKS_READY',len(verification),flush=True)
