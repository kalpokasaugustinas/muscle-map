# run inside blender: extracts muscles, tendons and bones from the z-anatomy blend,
# simplifies them and exports one draco-compressed glb for the web app.
# usage: blender -b Startup.blend --python export_muscles.py -- out.glb
import bpy, re, sys

out = sys.argv[sys.argv.index('--') + 1]

# names we never want (connective tissue that would cover the muscles, labels, alternatives)
# (.g = floating text titles, .i/.j/.t = label lines)
skip_re = re.compile(r'fascia|bursa|sheath|septum|ligament|\.[gijt]$|^\(', re.I)
tendon_re = re.compile(r'tendon|aponeurosis|linea alba|retinaculum|galea', re.I)

def kind_of(ob):
    cols = [c.name for c in ob.users_collection]
    name = ob.name
    if ob.type != 'MESH' or len(ob.data.vertices) < 20:
        return None
    if any(c.startswith('4: Muscular system') for c in cols) or any('Muscular system' in c for c in cols):
        if tendon_re.search(name):
            return 'tendon'
        if skip_re.search(name):
            return None
        return 'muscle'
    if any(c.startswith('1: Skeletal system') for c in cols):
        if skip_re.search(name) or 'cartilage' in name.lower():
            return None
        return 'bone'
    return None

keep = {ob: kind_of(ob) for ob in bpy.data.objects}
keep = {ob: k for ob, k in keep.items() if k}
print('keeping', len(keep), {k: sum(1 for v in keep.values() if v == k) for k in ('muscle', 'tendon', 'bone')})

# detach kept objects from parents without moving them, then delete everything else
for ob in keep:
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw
for ob in list(bpy.data.objects):
    if ob not in keep:
        bpy.data.objects.remove(ob, do_unlink=True)

# make everything visible so the exporter includes it
def unhide(lc):
    lc.exclude = False
    lc.hide_viewport = False
    for c in lc.children:
        unhide(c)
unhide(bpy.context.view_layer.layer_collection)
for c in bpy.data.collections:
    c.hide_viewport = False
    c.hide_render = False

for i, (ob, kind) in enumerate(keep.items()):
    ob.hide_viewport = False
    ob.hide_render = False
    ob.hide_set(False)
    # remember the anatomical name + type for the web app (exported as gltf extras -> userData)
    ob['zname'] = ob.name
    ob['kind'] = kind
    # simplify: keep ~30% of muscle detail, less for bones, never below ~250 verts
    n = len(ob.data.vertices)
    base = 0.3 if kind == 'muscle' else 0.2
    ratio = max(base, min(1.0, 250 / max(n, 1)))
    if ratio < 1.0:
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        mod = ob.modifiers.new('decimate', 'DECIMATE')
        mod.ratio = ratio
    ob.name = f'o{i}'

bpy.ops.export_scene.gltf(
    filepath=out,
    export_format='GLB',
    use_selection=False,
    export_apply=True,
    export_extras=True,
    export_yup=True,
    export_texcoords=False,
    export_normals=True,
    export_materials='NONE',
    export_animations=False,
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=7,
    export_draco_position_quantization=12,
    export_draco_normal_quantization=8,
)
print('exported', out)
