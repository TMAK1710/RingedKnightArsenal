import bpy,pathlib,math
root=pathlib.Path('build/asset-export')
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def material(name,color):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*color,1);return m
pot=material('BlackClay',(.035,.025,.02));rope=material('Rope',(.26,.19,.1));cork=material('Cork',(.12,.07,.03))
bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12,radius=1,location=(0,0,.075))
o=bpy.context.object;o.name='BlackFirebomb_Pot';o.scale=(.075,.075,.08);o.data.materials.append(pot)
bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=.024,depth=.03,location=(0,0,.157))
bpy.context.object.name='BlackFirebomb_Stopper';bpy.context.object.data.materials.append(cork)
curve=bpy.data.curves.new('RopeFuse','CURVE');curve.dimensions='3D';curve.bevel_depth=.0035;curve.bevel_resolution=2
spline=curve.splines.new('POLY');points=[(.0,.0,.174),(.01,0,.19),(.025,.003,.2),(.04,.004,.198),(.05,.006,.185)]
spline.points.add(len(points)-1)
for p,v in zip(spline.points,points):p.co=(*v,1)
obj=bpy.data.objects.new('BlackFirebomb_RopeFuse',curve);bpy.context.collection.objects.link(obj);obj.data.materials.append(rope)
for obj in list(bpy.context.scene.objects):
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    if obj.type=='CURVE':bpy.ops.object.convert(target='MESH')
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
bpy.ops.export_scene.fbx(filepath=str(root/'RopeBlackFirebomb.fbx'),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',bake_anim=False)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'RopeBlackFirebomb.blend'))
print('BOMB_PROP_READY',flush=True)
