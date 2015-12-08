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
        
    def write(self, bytes):
        self.file.write(bytes)
        if len(self.block_sizes) > 0:
            self.block_sizes[-1] += len(bytes)
            
    def write_padding(self, num_bytes):
        self.write(b'\0'*num_bytes)
        
    def write_struct(self, fmt, *values):
        self.write(struct.pack(fmt, *values))
        
    def write_utf(self, string):
        utf8 = string.encode('utf_8')
        self.write_struct('>h', len(utf8))
        self.write(utf8)

    def write_padded_utf(self, string):
        utf8 = string.encode('utf_8')
        utflen = len(utf8)
        self.write_struct('>h', utflen)
        self.write(utf8)
        self.write_padding((2 - utflen) & 0b11)
        
    def write_vec3(self, v):
        self.write_struct('>3f', v[1], v[2], v[0])
        
    def write_mat3(self, m):
        self.write_struct('>9f', m[1][1], m[1][2], m[1][0],
                                 m[2][1], m[2][2], m[2][0],
                                 m[0][1], m[0][2], m[0][0])
        
    def write_rot(self, r): #Works for quaternions and axis-angle
        self.write_struct('>4f', r[0], r[2], r[3], r[1])
        
    def begin_block(self):
        offset = self.file.tell()
        self.write_padding(4)
        self.block_offsets.append(offset)
        self.block_sizes.append(0)
        
    def end_block(self):
        offset = self.file.tell()
        self.file.seek(self.block_offsets.pop())
        size = self.block_sizes.pop()
        self.file.write(struct.pack('>i', size))
        self.file.seek(offset)
        if len(self.block_sizes) > 0:
            self.block_sizes[-1] += size
        
    def close(self):
        self.file.close()

FCURVE_INTERPOLATION_IDS = {
    'CONSTANT': 0,
    'LINEAR': 1,
    'BEZIER': 2
}

def write_keyframe(file, keyframe):
    file.write_struct('>i', FCURVE_INTERPOLATION_IDS[keyframe.interpolation])
    file.write_struct('>2f', *keyframe.co)
    file.write_struct('>2f', *keyframe.handle_left)
    file.write_struct('>2f', *keyframe.handle_right)

FCURVE_PROPERTY_TYPE_IDS = {
    'location': 1,
    'rotation_quaternion': 2,
    'rotation_axis_angle': 3,
    'scale': 4
}

def write_fcurve(file, fcurve):
    fcurve.update()

    if fcurve.data_path.startswith('pose.bones[\"'):
        bone_name_end_index = fcurve.data_path.index('\"].')
        bone_name = fcurve.data_path[12:bone_name_end_index]
        property_name = fcurve.data_path[bone_name_end_index + 3:]
        
        file.write_struct('>h', 1)
        file.write_struct('>h', FCURVE_PROPERTY_TYPE_IDS[property_name])
        file.write_padded_utf(bone_name)
    else:
        file.write_struct('>h', 0)
        file.write_struct('>h', FCURVE_PROPERTY_TYPE_IDS[fcurve.data_path])
    
    file.write_struct('>i', len(fcurve.keyframe_points))
    for keyframe in fcurve.keyframe_points:
        write_keyframe(file, keyframe)

def write_action(file, action):
    file.write_padded_utf(action.name)
    file.write_struct('>i', len(action.fcurves))
    for fcurve in action.fcurves:
        write_fcurve(file, fcurve)

def write_armature(file, armature):
    file.write_padded_utf(armature.name)

def write_lamp(file, lamp):
    file.write_padded_utf(lamp.name)

def write_material(file, material):
    file.write_padded_utf(material.name)

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
        
def loop_vertices_equal(lva, lvb, has_tangents):
    #Ensure indices are equal
    if lva.loop.vertex_index != lvb.loop.vertex_index:
        return False

    #Ensure normals are equal
    for a, b in zip(lva.loop.normal, lvb.loop.normal):
        if a != b:
            return False
            
    #Ensure tangents are equal
    if has_tangents:
        for a, b in zip(lva.loop.tangent, lvb.loop.tangent):
            if a != b:
                return False
    
    #Ensure uvs are equal
    for loopA, loopB, in zip(lva.uv_loops, lvb.uv_loops):
        for a, b, in zip(loopA.uv, loopB.uv):
            if a != b:
                return False
    
    #Ensure colors are equal
    for loopA, loopB, in zip(lva.color_loops, lvb.color_loops):
        for a, b, in zip(loopA.color, loopB.color):
            if a != b:
                return False
    
    #Ensure same number of groups
    if len(lva.vert.groups) != len(lvb.vert.groups):
        return False
    
    #Ensure groups are equal
    for ga, gb, in zip(lva.vert.groups, lvb.vert.groups):
        if ga.group != gb.group:
            return False
        if ga.weight != gb.weight:
            return False
    
    return True

class ProcessedMesh:
    def __init__(self, mesh, use_tangents):
        #Set up fields
        self.num_uv_layers = len(mesh.uv_layers)
        self.has_tangents = use_tangents and self.num_uv_layers > 0
        self.num_color_layers = len(mesh.vertex_colors)
        self.num_groups = 0
        self.triangles = []
        self.vertices = []
        
        #Prepare mesh
        mesh.calc_tessface()
        if self.has_tangents:
            try:
                mesh.calc_tangents()
            except:
                self.has_tangents = False
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
                    if loop_vertices_equal(loop_vertex, new_loop_vertex, self.has_tangents):
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

def write_mesh(file, mesh):
    pmesh = ProcessedMesh(mesh, False)
    
    file.write_padded_utf(mesh.name)
    
    file.write_struct('>i', pmesh.num_uv_layers)
    for uv_layer in mesh.uv_layers:
        file.write_padded_utf(uv_layer.name)
        
    file.write_struct('>i', pmesh.num_color_layers)
    for color_layer in mesh.vertex_colors:
        file.write_padded_utf(color_layer.name)
        
    file.write_struct('>i', pmesh.has_tangents)
    file.write_struct('>i', pmesh.num_groups)
    file.write_struct('>i', len(pmesh.vertices))
    
    for vertex in pmesh.vertices:
        file.write_vec3(vertex.vert.co)
    
    for vertex in pmesh.vertices:
        file.write_vec3(vertex.loop.normal)
    
    if pmesh.has_tangents:
        for vertex in pmesh.vertices:
            file.write_vec3(vertex.loop.tangent)
    
    for uv_layer_i in range(pmesh.num_uv_layers):
        for vertex in pmesh.vertices:
            file.write_struct('>2f', *vertex.uv_loops[uv_layer_i].uv)

    for color_layer_i in range(pmesh.num_color_layers):
        for vertex in pmesh.vertices:
            file.write_struct('>3f', *vertex.color_loops[color_layer_i].color)
    
    for vertex in pmesh.vertices:
        groups_written = 0
        for group in vertex.vert.groups:
            file.write_struct('>i', group.group)
            groups_written += 1
        while groups_written < pmesh.num_groups:
            file.write_struct('>i', -1)
            groups_written += 1
    
    for vertex in pmesh.vertices:
        groups_written = 0
        for group in vertex.vert.groups:
            file.write_struct('>f', group.weight)
            groups_written += 1
        while groups_written < pmesh.num_groups:
            file.write_struct('>f', 0.0)
            groups_written += 1
    
    file.write(struct.pack('>i', len(pmesh.triangles)))
    for triangle in pmesh.triangles:
        for pointer in triangle.loop_vertex_pointers:
            file.write_struct('>i', pointer.loop_vertex.index)
    
    for triangle in pmesh.triangles:
        file.write_struct('>i', triangle.poly.material_index)

########################
### OBJECT EXPORTING ###
########################

DATA_TYPE_IDS = {
    bpy.types.Action: 0,
    bpy.types.Armature: 1,
    bpy.types.Lamp: 2,
    bpy.types.Material: 3,
    bpy.types.Mesh: 4
}

def write_vertex_group(file, vertex_group):
    file.write_padded_utf(vertex_group.name)

def write_object(file, object, index_map):
    data_type = type(object.data)
    rot_mode = object.rotation_mode
    
    file.write_padded_utf(object.name)
    
    if data_type in DATA_TYPE_IDS:
        file.write_struct('>i', DATA_TYPE_IDS[data_type])
        file.write_struct('>i', index_map[object.data.name])
    else:
        file.write_struct('>i', -1)
    
    file.write_vec3(object.location)
    
    if rot_mode == 'QUATERNION':
        file.write_struct('>i', 0)
        file.write_rot(object.rotation_quaternion)
    elif rot_mode == 'AXIS_ANGLE':
        file.write_struct('>i', 1)
        file.write_rot(object.rotation_axis_angle)
    else:
        file.write_struct('>i', -1)
    
    file.write_vec3(object.scale)
    
    file.write_struct('>i', len(object.vertex_groups))
    for vertex_group in object.vertex_groups:
        write_vertex_group(file, vertex_group)
    
    if object.animation_data is not None:
        file.write_struct('>i', index_map[object.animation_data.action.name])
    else:
        file.write_struct('>i', -1)

def write_scene(file, scene, index_map):
    file.write_padded_utf(scene.name)
    file.write_struct('>3f', *scene.world.horizon_color)
    file.write_struct('>i', len(scene.objects))
    for object in scene.objects:
        file.write_struct('>i', index_map[object.name])

############
### MAIN ###
############

def map_indices(index_map, *lists):
    for list in lists:
        for i, id in enumerate(list):
            index_map[id.name] = i

def write_list_as_block(file, magic_number, list, write_func, *args):
    file.write_struct('>i', magic_number)
    file.begin_block()
    file.write_struct('>i', len(list))
    for element in list:
        write_func(file, element, *args)
    file.end_block()
            
def export(filepath):
    print('Exporting DVM...')
    
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    index_map = {}
    map_indices(index_map, bpy.data.actions, bpy.data.armatures, bpy.data.lamps,
                           bpy.data.materials, bpy.data.meshes, bpy.data.objects)
    
    with DataFile(filepath) as file:
        file.write(b'\x9F\x0ADevilModel')
        file.write_struct('>2h', 0, 5) #Major/minor version
        write_list_as_block(file, 32, bpy.data.actions, write_action)
        write_list_as_block(file, 33, bpy.data.armatures, write_armature)
        write_list_as_block(file, 34, bpy.data.lamps, write_lamp)
        write_list_as_block(file, 35, bpy.data.materials, write_material)
        write_list_as_block(file, 36, bpy.data.meshes, write_mesh)
        write_list_as_block(file, 37, bpy.data.objects, write_object, index_map)
        write_list_as_block(file, 38, bpy.data.scenes, write_scene, index_map)
    
    print('DVM successfully exported.')
    return {'FINISHED'}
