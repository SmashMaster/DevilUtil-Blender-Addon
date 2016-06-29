import bpy
import os
import struct

class DataFile:
    def __init__(self, filepath):
        self.filepath = filepath
        self.file = None
        self.block_offsets = []
        self.block_sizes = []
        
    def __enter__(self):
        self.file = open(self.filepath, 'w+b')
        self.file.truncate()
        return self
        
    def __exit__(self, type, value, traceback):
        self.file.close()
        self.file = None

def write(bytes):
    file = __FILE__
    file.file.write(bytes)
    if len(file.block_sizes) > 0:
        file.block_sizes[-1] += len(bytes)

def write_padding(num_bytes):
    write(b'\0'*num_bytes)

def begin_block():
    file = __FILE__
    offset = file.file.tell()
    write_padding(4)
    file.block_offsets.append(offset)
    file.block_sizes.append(0)
    
def end_block():
    file = __FILE__
    offset = file.file.tell()
    file.file.seek(file.block_offsets.pop())
    size = file.block_sizes.pop()
    file.file.write(struct.pack('>i', size))
    file.file.seek(offset)
    if len(file.block_sizes) > 0:
        file.block_sizes[-1] += size

def write_struct(fmt, *values):
    write(struct.pack(fmt, *values))

def write_padded_utf(string):
    utf8 = string.encode('utf_8')
    utf_len = len(utf8)
    write_struct('>h', utf_len)
    write(utf8)
    write_padding((2 - utf_len) & 0b11)
    
def write_list(list, write_func, *args):
    write_struct('>i', len(list))
    for element in list:
        write_func(element, *args)

def write_datablock(magic_number, id_list, write_func, *args):
    local_ids = []
    for id in id_list:
        if id.library is None:
            local_ids.append(id)
    
    write_struct('>i', magic_number)
    begin_block()
    write_list(local_ids, write_func, *args)
    end_block()

def write_vec3(v):
    write_struct('>3f', v[1], v[2], v[0])
    
def write_color(c, intensity):
    write_struct('>3f', c.r*intensity, c.g*intensity, c.b*intensity)
    
def write_mat3(m):
    write_struct('>9f', m[1][1], m[1][2], m[1][0],
                        m[2][1], m[2][2], m[2][0],
                        m[0][1], m[0][2], m[0][0])
                        
def write_mat4(m):
    write_struct('>16f', m[1][1], m[1][2], m[1][0], m[1][3],
                         m[2][1], m[2][2], m[2][0], m[2][3],
                         m[0][1], m[0][2], m[0][0], m[0][3],
                         m[3][1], m[3][2], m[3][0], m[3][3])
    
def write_rot(r): #Works for quaternions and axis-angle
    write_struct('>4f', r[0], r[2], r[3], r[1])
    
def write_transform(object):
    write_vec3(object.location)
    write_rot(object.rotation_quaternion)
    write_vec3(object.scale)

### LIBRARY EXPORTING ###

def write_library(library):
    write_padded_utf(library.filepath)

### ACTION EXPORTING ###
    
FCURVE_INTERPOLATION_IDS = {
    'CONSTANT': 0,
    'LINEAR': 1,
    'BEZIER': 2
}

def write_keyframe(keyframe):
    write_struct('>i', FCURVE_INTERPOLATION_IDS[keyframe.interpolation])
    write_struct('>2f', *keyframe.co)
    write_struct('>2f', *keyframe.handle_left)
    write_struct('>2f', *keyframe.handle_right)

FCURVE_PROPERTY_TYPE_IDS = {
    'location': 0,
    'rotation_quaternion': 1,
    'rotation_axis_angle': 2,
    'scale': 3
}

FCURVE_ARRAY_INDEX_MAP = [
    [2, 0, 1],
    [0, 3, 1, 2],
    [0, 3, 1, 2],
    [2, 0, 1]
]

def write_fcurve(fcurve):
    fcurve.update()
    
    property_id = None

    if fcurve.data_path.startswith('pose.bones[\"'):
        bone_name_end_index = fcurve.data_path.index('\"].')
        bone_name = fcurve.data_path[12:bone_name_end_index]
        property_name = fcurve.data_path[bone_name_end_index + 3:]
        property_id = FCURVE_PROPERTY_TYPE_IDS[property_name]
        
        write_struct('>h', 1)
        write_struct('>h', property_id)
        write_padded_utf(bone_name)
    else:
        property_id = FCURVE_PROPERTY_TYPE_IDS[fcurve.data_path]
    
        write_struct('>h', 0)
        write_struct('>h', property_id)
    
    write_struct('>i', FCURVE_ARRAY_INDEX_MAP[property_id][fcurve.array_index])
    write_list(fcurve.keyframe_points, write_keyframe)
    
class Marker:
    def __init__(self, name, frame):
        self.name = name
        self.frame = frame
    
def write_marker(marker):
    write_padded_utf(marker.name)
    write_struct('>i', marker.frame)

def write_action(action):
    write_padded_utf(action.name)
    write_list(action.fcurves, write_fcurve)
    
    markers = []
    for marker in action.pose_markers:
        for name in marker.name.split('+'):
            markers.append(Marker(name, marker.frame))
    markers.sort(key=lambda marker: marker.frame)
    write_list(markers, write_marker)

### ARMATURE EXPORTING ###
    
def write_bone(bone):
    write_padded_utf(bone.name)
    write_struct('>i', bone.parent.dvm_bone_index if bone.parent is not None else -1)
    write_struct('>i', bone.use_inherit_rotation)
    write_vec3(bone.head_local)
    write_vec3(bone.tail_local)
    write_mat3(bone.matrix_local)
        
def write_armature(armature):
    for bone_index, bone in enumerate(armature.bones):
        bone.dvm_bone_index = bone_index
    
    write_padded_utf(armature.name)
    write_list(armature.bones, write_bone)
    
### CURVE EXPORTING ###

def write_spline_point(point):
    write_vec3(point.co)
    write_vec3(point.handle_left)
    write_vec3(point.handle_right)

def write_spline(spline):
    write_struct('>i', spline.use_cyclic_u)
    write_list(spline.bezier_points, write_spline_point)

def write_curve(curve):
    write_padded_utf(curve.name)
    write_list(curve.splines, write_spline)
    
def write_lamp(lamp):
    write_padded_utf(lamp.name)
    write_color(lamp.color, lamp.energy)
    
    if lamp.type == 'POINT':
        write_struct('>i', 0)
        write_struct('>f', lamp.distance)
    else: #SUN
        write_struct('>i', 1)
    
### MATERIAL EXPORTING ###
    
def write_material(material):
    write_padded_utf(material.name)
    write_color(material.diffuse_color, material.diffuse_intensity)
    write_color(material.specular_color, material.specular_intensity)
    write_struct('>f', material.specular_hardness)
    write_struct('>f', material.specular_ior)
    write_struct('>f', material.emit)
    
######################
### MESH EXPORITNG ###
######################

class LoopVertex:
    def __init__(self, mesh, poly, loop):
        self.index = -1
        self.vert = mesh.vertices[loop.vertex_index]
        self.poly = poly
        self.loop = loop
        self.uv_loops = [uv_loop.data[loop.index] for uv_loop in mesh.uv_layers]
        self.color_loops = [color_loop.data[loop.index] for color_loop in mesh.vertex_colors]
        self.pointers = []

class Triangle:
    def __init__(self, indices):
        self.indices = indices
        self.loop_vertex_pointers = []

class LoopVertexPointer:
    def __init__(self, loop_vertex):
        self.loop_vertex = loop_vertex
        loop_vertex.pointers.append(self)

def loop_vertices_equal(lva, lvb, pmesh):
    if lva.loop.vertex_index != lvb.loop.vertex_index:
        return False
    
    if pmesh.exp_normals:
        for a, b in zip(lva.loop.normal, lvb.loop.normal):
            if a != b:
                return False
    
    if pmesh.exp_tangents:
        for a, b in zip(lva.loop.tangent, lvb.loop.tangent):
            if a != b:
                return False
    
    for loopA, loopB, in zip(lva.uv_loops, lvb.uv_loops):
        for a, b, in zip(loopA.uv, loopB.uv):
            if a != b:
                return False
    
    for loopA, loopB, in zip(lva.color_loops, lvb.color_loops):
        for a, b, in zip(loopA.color, loopB.color):
            if a != b:
                return False
    
    if len(lva.vert.groups) != len(lvb.vert.groups):
        return False
    
    for ga, gb, in zip(lva.vert.groups, lvb.vert.groups):
        if ga.group != gb.group:
            return False
        if ga.weight != gb.weight:
            return False
            
    if pmesh.exp_mat_inds:
        if lva.poly.material_index != lvb.poly.material_index:
            return False
    
    return True

class ProcessedMesh:
    def __init__(self, mesh):
        #Set up fields
        self.num_uv_layers = len(mesh.uv_layers)
        self.exp_normals = mesh.dvm_exp_normal
        self.exp_tangents = mesh.dvm_exp_tangent and self.num_uv_layers > 0
        self.exp_groups = mesh.dvm_exp_groups
        self.exp_mat_inds = mesh.dvm_exp_mat_inds and len(mesh.materials) > 0
        self.num_color_layers = len(mesh.vertex_colors)
        self.num_groups = 0
        self.triangles = []
        self.vertices = []
        
        #Prepare mesh
        mesh.calc_tessface()
        if self.exp_tangents:
            try:
                mesh.calc_tangents(mesh.dvm_tan_uv_src)
            except:
                self.exp_tangents = False
        else:
            mesh.calc_normals_split()
        
        #Set up LoopVertex list
        loop_vertex_sets = [set() for i in range(len(mesh.vertices))]
        for poly in mesh.polygons:
            for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loop = mesh.loops[loop_index]
                loop_vertex = LoopVertex(mesh, poly, loop)
                loop_vertex_sets[loop.vertex_index].add(loop_vertex)
        
        #Populate triangle list
        for face in mesh.tessfaces:
            verts = face.vertices
            if len(verts) == 4:
                self.triangles.append(Triangle([verts[0], verts[1], verts[2]]))
                self.triangles.append(Triangle([verts[2], verts[3], verts[0]]))
            else:
                self.triangles.append(Triangle(verts))
        
        for triangle in self.triangles:
            #Find which poly corresponds to this Triangle
            polysets = [set(loop_vertex.poly for loop_vertex in loop_vertex_sets[i]) for i in triangle.indices]
            triangle.poly = next(iter(set.intersection(*polysets)))
            
            #Find which loop_vertex objects correspond to each vertex of this Triangle
            #Also set up pointers
            for i in triangle.indices:
                for loop_vertex in loop_vertex_sets[i]:
                    if loop_vertex.poly is triangle.poly:
                        triangle.loop_vertex_pointers.append(LoopVertexPointer(loop_vertex))
                        break
        
        #Dissolve redundant LoopVertex objects
        for loop_vertices in loop_vertex_sets:
            new_loop_vertices = set()
            for loop_vertex in loop_vertices:
                identical = None
                for new_loop_vertex in new_loop_vertices:
                    if loop_vertices_equal(loop_vertex, new_loop_vertex, self):
                        identical = new_loop_vertex
                        for pointer in loop_vertex.pointers:
                            pointer.loop_vertex = new_loop_vertex
                            new_loop_vertex.pointers.append(pointer)
                        break
                if identical is None:
                    new_loop_vertices.add(loop_vertex)
            loop_vertices.clear()
            loop_vertices |= new_loop_vertices
        
        #Populate vertex list
        i = 0
        for loop_vertices in loop_vertex_sets:
            for loop_vertex in loop_vertices:
                loop_vertex.index = i
                i += 1
                self.vertices.append(loop_vertex)
        
        #Count groups
        for vertex in self.vertices:
            self.num_groups = max(self.num_groups, len(vertex.vert.groups))

def write_mesh(mesh):
    pmesh = ProcessedMesh(mesh)
    
    write_padded_utf(mesh.name)
    
    export_flags = 0
    export_flags |= 1 if pmesh.exp_normals else 0
    export_flags |= 2 if pmesh.exp_tangents else 0
    export_flags |= 4 if pmesh.exp_groups else 0
    export_flags |= 8 if pmesh.exp_mat_inds else 0
    write_struct('>i', export_flags)
    
    write_struct('>i', pmesh.num_uv_layers)
    for uv_layer in mesh.uv_layers:
        write_padded_utf(uv_layer.name)
        
    write_struct('>i', pmesh.num_color_layers)
    for color_layer in mesh.vertex_colors:
        write_padded_utf(color_layer.name)
    
    write_struct('>i', pmesh.num_groups if pmesh.exp_groups else 0)
    write_struct('>i', len(pmesh.vertices))
    
    for vertex in pmesh.vertices:
        write_vec3(vertex.vert.co)
    
    if pmesh.exp_normals:
        for vertex in pmesh.vertices:
            write_vec3(vertex.loop.normal)
    
    for uv_layer_i in range(pmesh.num_uv_layers):
        for vertex in pmesh.vertices:
            write_struct('>2f', *vertex.uv_loops[uv_layer_i].uv)
            
    if pmesh.exp_tangents:
        for vertex in pmesh.vertices:
            write_vec3(vertex.loop.tangent)

    for color_layer_i in range(pmesh.num_color_layers):
        for vertex in pmesh.vertices:
            write_struct('>3f', *vertex.color_loops[color_layer_i].color)
    
    if pmesh.exp_groups:
        for vertex in pmesh.vertices:
            groups_written = 0
            for group in vertex.vert.groups:
                write_struct('>i', group.group)
                groups_written += 1
            while groups_written < pmesh.num_groups:
                write_struct('>i', -1)
                groups_written += 1
        
        for vertex in pmesh.vertices:
            groups_written = 0
            for group in vertex.vert.groups:
                write_struct('>f', group.weight)
                groups_written += 1
            while groups_written < pmesh.num_groups:
                write_struct('>f', 0.0)
                groups_written += 1
    
    if pmesh.exp_mat_inds:
        for vertex in pmesh.vertices:
            local_index = vertex.poly.material_index
            material = mesh.materials[local_index]
            if material is not None:
                if material.library is not None:
                    raise ValueError("Cannot export library materials")
                write_struct('>i', material.dvm_array_index)
            else:
                write_struct('>i', 0)
    
    write_struct('>i', len(pmesh.triangles))
    for triangle in pmesh.triangles:
        for pointer in triangle.loop_vertex_pointers:
            write_struct('>i', pointer.loop_vertex.index)

########################
### OBJECT EXPORTING ###
########################

def write_pose(pose):
    write_struct('>i', len(pose.bones))
    for bone in pose.bones:
        write_padded_utf(bone.bone.name)
        write_transform(bone)

def write_vertex_group(vertex_group):
    write_padded_utf(vertex_group.name)
        
class IKConstraint:
    def __init__(self, bone, constraint):
        self.bone = bone
        self.constraint = constraint
        
def write_ik_constraint(ik_constraint):
    write_padded_utf(ik_constraint.bone.name)
    write_padded_utf(ik_constraint.constraint.subtarget)
    write_padded_utf(ik_constraint.constraint.pole_subtarget)
    write_struct('>f', ik_constraint.constraint.pole_angle)

DATA_TYPE_IDS = {
    bpy.types.Library: 0,
    bpy.types.Action: 1,
    bpy.types.Armature: 2,
    bpy.types.Curve: 3,
    bpy.types.PointLamp: 4,
    bpy.types.SunLamp: 4,
    bpy.types.Mesh: 5,
    bpy.types.Scene: 6
}

EMPTY_TYPE_IDS = {
    'PLAIN_AXES': 0,
    'CUBE': 1,
    'SPHERE': 2
}
    
def write_object(object):
    write_padded_utf(object.name)
    
    write_struct('>i', len(object.dvm_args))
    for arg in object.dvm_args:
        write_padded_utf(arg.name)
        write_padded_utf(arg.value)
    
    data_type = type(object.data)
    if data_type in DATA_TYPE_IDS:
        write_struct('>i', DATA_TYPE_IDS[data_type])
        if object.data.library is None:
            write_struct('>i', -1)
            write_struct('>i', object.data.dvm_array_index)
        else:
            write_struct('>i', object.data.library.dvm_array_index)
            write_padded_utf(object.data.name)
    else:
        write_struct('>i', -1)
    
    if object.parent is not None:
        write_struct('>i', object.parent.dvm_array_index)
        write_mat4(object.matrix_parent_inverse)
        if object.parent_type == 'BONE':
            write_struct('>i', 1)
            write_padded_utf(object.parent_bone)
        else:
            write_struct('>i', 0)
    else:
        write_struct('>i', -1)
    
    object.rotation_mode = 'QUATERNION'
    write_transform(object)
    write_list(object.vertex_groups, write_vertex_group)
    
    has_pose = object.pose is not None
    write_struct('>i', has_pose)
    if has_pose:
        write_pose(object.pose)
        ik_constraints = []
        for bone in object.pose.bones:
            for constraint in bone.constraints:
                if not isinstance(constraint, bpy.types.KinematicConstraint):
                    continue
                if constraint.chain_count != 2:
                    continue
                if constraint.target is None or constraint.subtarget == "":
                    continue
                if constraint.pole_target is None or constraint.pole_subtarget == "":
                    continue
                ik_constraints.append(IKConstraint(bone.bone, constraint))
        write_list(ik_constraints, write_ik_constraint)
    
    if object.animation_data is not None and object.animation_data.action is not None:
        write_struct('>i', object.animation_data.action.dvm_array_index)
    else:
        write_struct('>i', -1)
        
    empty_type = object.empty_draw_type
    if empty_type in EMPTY_TYPE_IDS:
        write_struct('>i', EMPTY_TYPE_IDS[empty_type])
    else:
        write_struct('>i', -1)

def write_scene(scene):
    write_padded_utf(scene.name)
    if (scene.world is not None):
        write_struct('>3f', *scene.world.horizon_color)
    else:
        write_struct('>3f', 0.0, 0.0, 0.0)
    write_struct('>i', len(scene.objects))
    for object in scene.objects:
        write_struct('>i', object.dvm_array_index)

############
### MAIN ###
############

def map_indices(*lists):
    for list in lists:
        i = 0
        for i, id in enumerate(list):
            if id.library is None: 
                id.dvm_array_index = i
                i += 1
            else:
                id.dvm_array_index = -1
                    
 
def export(filepath):
    print("export dvm: " + filepath)
    
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    map_indices(bpy.data.libraries, bpy.data.actions, bpy.data.armatures,
                bpy.data.curves, bpy.data.lamps, bpy.data.materials,
                bpy.data.meshes, bpy.data.objects)
    
    global __FILE__
    with DataFile(filepath) as __FILE__:
        write(b'\x9F\x0ADevilModel')
        write_struct('>2h', 0, 21) #Major/minor version
        write_datablock(1112276993, bpy.data.libraries, write_library)
        write_datablock(1112276994, bpy.data.actions, write_action)
        write_datablock(1112276995, bpy.data.armatures, write_armature)
        write_datablock(1112276996, bpy.data.curves, write_curve)
        write_datablock(1112276997, bpy.data.lamps, write_lamp)
        write_datablock(1112276998, bpy.data.materials, write_material)
        write_datablock(1112276999, bpy.data.meshes, write_mesh)
        write_datablock(1112277000, bpy.data.objects, write_object)
        write_datablock(1112277001, bpy.data.scenes, write_scene)
    
    return {'FINISHED'}
