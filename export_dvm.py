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
        self.file = open(self.filepath, "r+b")
        self.file.truncate()
        return self
        
    def __exit__(self, type, value, traceback):
        self.file.close()
        
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

def write_fcurve(file, fcurve):
    pass
    
def write_action(file, action):
    write_padded_utf(file, action.name)
    write_struct(file, '>i', len(action.fcurves))
    for fcurve in action.fcurves:
        write_fcurve(file, fcurve)

def write_armature(file, armature):
    write_padded_utf(file, armature.name)

def write_lamp(file, lamp):
    write_padded_utf(file, lamp.name)

def write_material(file, material):
    write_padded_utf(file, material.name)

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
    
    #Name
    write_padded_utf(file, mesh.name)
    
    #UV layer names
    write_struct(file, '>i', pmesh.num_uv_layers)
    for uv_layer in mesh.uv_layers:
        write_padded_utf(file, uv_layer.name)
    
    #Color layer names
    write_struct(file, '>i', pmesh.num_color_layers)
    for color_layer in mesh.vertex_colors:
        write_padded_utf(file, color_layer.name)
        
    #Tangents enabled
    write_struct(file, '>i', pmesh.has_tangents)
    
    #Group count
    write_struct(file, '>i', pmesh.num_groups)
        
    #Vertex count
    write_struct(file, '>i', len(pmesh.vertices))
    
    #Positions
    for vertex in pmesh.vertices:
        write_vec3(file, vertex.vert.co)
        
    #Normals
    for vertex in pmesh.vertices:
        write_vec3(file, vertex.loop.normal)
        
    #Tangents
    if pmesh.has_tangents:
        for vertex in pmesh.vertices:
            write_vec3(file, '>3f', vertex.loop.tangent)
    
    #UVs
    for uv_layer_i in range(pmesh.num_uv_layers):
        for vertex in pmesh.vertices:
            write_struct(file, '>2f', *vertex.uv_loops[uv_layer_i].uv)

    #Colors
    for color_layer_i in range(pmesh.num_color_layers):
        for vertex in pmesh.vertices:
            write_struct(file, '>3f', *vertex.color_loops[color_layer_i].color)
    
    #Group indices
    for vertex in pmesh.vertices:
        groups_written = 0
        for group in vertex.vert.groups:
            write_struct(file, '>i', group.group)
            groups_written += 1
        while groups_written < pmesh.num_groups:
            write_struct(file, '>i', -1)
            groups_written += 1
    
    #Group weights
    for vertex in pmesh.vertices:
        groups_written = 0
        for group in vertex.vert.groups:
            write_struct(file, '>f', group.weight)
            groups_written += 1
        while groups_written < pmesh.num_groups:
            write_struct(file, '>f', 0.0)
            groups_written += 1
            
    #Triangles
    file.write(struct.pack('>i', len(pmesh.triangles)))
    for triangle in pmesh.triangles:
        for pointer in triangle.loop_vertex_pointers:
            write_struct(file, '>i', pointer.loop_vertex.index)
            
    #Material indices
    for triangle in pmesh.triangles:
        write_struct(file, '>i', triangle.poly.material_index)

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
    write_padded_utf(file, vertex_group.name)

def write_object(file, index_map, object):
    data_type = type(object.data)
    rot_mode = object.rotation_mode
    
    #Name
    write_padded_utf(file, object.name)
    
    #Data type and ID
    if data_type in DATA_TYPE_IDS:
        write_struct(file, '>i', DATA_TYPE_IDS[data_type])
        write_struct(file, '>i', index_map[object.data.name])
    else:
        write_struct(file, '>i', -1)
    
    #Location
    write_vec3(file, object.location)
    
    #Rotation type and value
    if rot_mode == 'QUATERNION':
        write_struct(file, '>i', 0)
        write_rot(file, object.rotation_quaternion)
    elif rot_mode == 'AXIS_ANGLE':
        write_struct(file, '>i', 1)
        write_rot(file, object.rotation_axis_angle)
    else:
        write_struct(file, '>i', -1)
    
    #Scale
    write_vec3(file, object.scale)
    
    #Vertex groups
    write_struct(file, '>i', len(object.vertex_groups))
    for vertex_group in object.vertex_groups:
        write_vertex_group(file, vertex_group)

def write_scene(file, index_map, scene):
    #Name
    write_padded_utf(file, scene.name)
    
    #Background color
    write_struct(file, '>3f', *scene.world.horizon_color)
    
    #Object IDs
    write_struct(file, '>i', len(scene.objects))
    for object in scene.objects:
        write_struct(file, '>i', index_map[object.name])

############
### MAIN ###
############

def map_indices(index_map, *lists):
    for list in lists:
        for i, id in enumerate(list):
            index_map[id.name] = i

def export(filepath):
    print('Exporting DVM...')
    
    #Exit edit mode before exporting, so current object states are exported properly
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    index_map = {}
    map_indices(index_map, bpy.data.actions, bpy.data.armatures, bpy.data.lamps,
                           bpy.data.materials, bpy.data.meshes, bpy.data.objects)
    
    with DataFile(filepath) as file:
        file.write(b'\x9F\x0ADevilModel')
        file.write_struct('>2h', 0, 5) #Major/minor version
        
        #write_struct(file, '>i', len(bpy.data.actions)) #Actions
        #for action in bpy.data.actions:
        #    write_action(file, action)
        #write_struct(file, '>i', len(bpy.data.armatures)) #Armatures
        #for armature in bpy.data.armatures:
        #    write_armature(file, armature)
        #write_struct(file, '>i', len(bpy.data.lamps)) #Lamps
        #for lamp in bpy.data.lamps:
        #    write_lamp(file, lamp)
        #write_struct(file, '>i', len(bpy.data.materials)) #Materials
        #for material in bpy.data.materials:
        #    write_material(file, material)
        #write_struct(file, '>i', len(bpy.data.meshes)) #Meshes
        #for mesh in bpy.data.meshes:
        #    write_mesh(file, mesh)
        #write_struct(file, '>i', len(bpy.data.objects)) #Objects
        #for object in bpy.data.objects:
        #    write_object(file, index_map, object)
        #write_struct(file, '>i', len(bpy.data.scenes)) #Scenes
        #for scene in bpy.data.scenes:
        #    write_scene(file, index_map, scene)
    
    print('DVM successfully exported.')
    return {'FINISHED'}
