import bpy
import struct
import os

def writeJavaUTF(file, string):
    utf8 = string.encode('utf_8')
    strlen = len(utf8)
    file.write(struct.pack('>h', strlen))
    file.write(struct.pack('>' + str(strlen) + 's', utf8))
    return strlen + 2

def writePaddedJavaUTF(file, string):
    #Padded to multiples of 4 bytes
    bytes_written = writeJavaUTF(file, string)
    padding = (4 - bytes_written) & 0b11
    file.write(struct.pack('>' + str(padding) + 'x'))

def vec3BlendToDevil(vector):
    return [vector[1], vector[2], vector[0]]
    
def quatBlendToDevil(quat):
    return [quat[0], quat[2], quat[3], quat[1]]

######################
### MESH EXPORITNG ###
######################

#Vertex container which holds vertices and their loops
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
        
#Mutable LoopVertex wrapper to make dissolving vertices easy
class LoopVertexPointer:
    def __init__(self, loop_vertex):
        self.loop_vertex = loop_vertex
        loop_vertex.pointers.append(self)
        
def loopVerticesEqual(lva, lvb, has_tangents):
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
        if self.has_tangents:
            try:
                mesh.calc_tangents("Mr. Poopybutthole")
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
                    if loopVerticesEqual(loop_vertex, new_loop_vertex, self.has_tangents):
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

def exportMesh(file, mesh, use_tangents):
    pmesh = ProcessedMesh(mesh, use_tangents)
    
    writePaddedJavaUTF(file, mesh.name)
    
    #UV layer names
    file.write(struct.pack('>i', pmesh.num_uv_layers))
    for uv_layer in mesh.uv_layers:
        writePaddedJavaUTF(file, uv_layer.name)
    
    #Color layer names
    file.write(struct.pack('>i', pmesh.num_color_layers))
    for color_layer in mesh.vertex_colors:
        writePaddedJavaUTF(file, color_layer.name)
        
    #Tangents enabled
    file.write(struct.pack('>i', pmesh.has_tangents))
    
    #Group count
    file.write(struct.pack('>i', pmesh.num_groups))
        
    #Vertex count
    file.write(struct.pack('>i', len(pmesh.vertices)))
    
    #Positions
    for vertex in pmesh.vertices:
        file.write(struct.pack('>3f', *vec3BlendToDevil(vertex.vert.co)))
        
    #Normals
    for vertex in pmesh.vertices:
        file.write(struct.pack('>3f', *vec3BlendToDevil(vertex.loop.normal)))
        
    #Tangents
    if pmesh.has_tangents:
        for vertex in pmesh.vertices:
            file.write(struct.pack('>3f', *vec3BlendToDevil(vertex.loop.tangent)))
    
    #UVs
    for uv_layer_i in range(pmesh.num_uv_layers):
        for vertex in pmesh.vertices:
            file.write(struct.pack('>2f', *vertex.uv_loops[uv_layer_i].uv))

    #Colors
    for color_layer_i in range(pmesh.num_color_layers):
        for vertex in pmesh.vertices:
            file.write(struct.pack('>3f', *vertex.color_loops[color_layer_i].color))
    
    #Group indices
    for vertex in pmesh.vertices:
        groups_written = 0
        for group in vertex.vert.groups:
            file.write(struct.pack('>i', group.group))
            groups_written += 1
        while groups_written < pmesh.num_groups:
            file.write(struct.pack('>i', -1))
            groups_written += 1
    
    #Group weights
    for vertex in pmesh.vertices:
        groups_written = 0
        for group in vertex.vert.groups:
            file.write(struct.pack('>f', group.weight))
            groups_written += 1
        while groups_written < pmesh.num_groups:
            file.write(struct.pack('>f', 0.0))
            groups_written += 1
            
    #Triangles
    file.write(struct.pack('>i', len(pmesh.triangles)))
    for triangle in pmesh.triangles:
        for pointer in triangle.loop_vertex_pointers:
            file.write(struct.pack('>i', pointer.loop_vertex.index))

########################
### OBJECT EXPORTING ###
########################

def exportMeshObject(file, obj):
    writePaddedJavaUTF(file, obj.name)

    #Mesh index
    file.write(struct.pack('>i', obj.data.tag))
    
    #Scale
    file.write(struct.pack('>3f', *vec3BlendToDevil(obj.scale)))
    
    #Rotation
    file.write(struct.pack('>4f', *quatBlendToDevil(obj.rotation_quaternion)))
    
    #Position
    file.write(struct.pack('>3f', *vec3BlendToDevil(obj.location)))
    
    #Vertex groups
    file.write(struct.pack('>i', len(obj.vertex_groups)))
    for group in obj.vertex_groups:
        writePaddedJavaUTF(file, group.name)

def exportSunObject(file, obj):
    writePaddedJavaUTF(file, obj.name)
    
    #Rotation
    file.write(struct.pack('>4f', *quatBlendToDevil(obj.rotation_quaternion)))
    
    #Soft shadow size (why is this in meters and not radians/degrees?)
    file.write(struct.pack('>1f', obj.data.shadow_soft_size))
    
    #Color
    emission_node = obj.data.node_tree.nodes["Emission"]
    r, g, b = emission_node.inputs[0].default_value[0:3]
    strength = emission_node.inputs[1].default_value
    file.write(struct.pack('>3f', r*strength, g*strength, b*strength))
    
############
### MAIN ###
############

def tagIndex(idList):
    for i, id in enumerate(idList):
        id.tag = i

def export(filepath, use_tangents):
    os.system("cls")
    print("EXPORTING DVM...")
    
    #Exit edit mode before exporting, so current object states are exported properly
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    #Export lists
    meshes = []
    meshObjects = []
    sunObjects = []
    world = bpy.context.scene.world
    
    #Find valid exportable data blocks
    for mesh in bpy.data.meshes:
        if mesh.users > 0:
            meshes.append(mesh)
    
    for obj in bpy.data.objects:
        if isinstance(obj.data, bpy.types.Mesh):
            meshObjects.append(obj)
        if isinstance(obj.data, bpy.types.SunLamp):
            sunObjects.append(obj)
            
    #Set data block tags to array indices
    tagIndex(meshes)
    tagIndex(meshObjects)
    
    file = open(filepath, "wb")
    try:
        #Header
        writeJavaUTF(file, "DevilModel 0.3")
        
        #Background color
        file.write(struct.pack('>3f', *world.horizon_color))
        
        #Count everything
        numMeshes = len(meshes)
        numMeshObjs = len(meshObjects)
        numSuns = len(sunObjects)
        
        print("Meshes:         {}".format(numMeshes))
        print("Mesh instances: {}".format(numMeshObjs))
        print("Sun lamps:      {}".format(numSuns))
        
        #Mesh blocks
        file.write(struct.pack('>i', numMeshes))
        for mesh in meshes:
            exportMesh(file, mesh, use_tangents)
        
        #Mesh object blocks
        file.write(struct.pack('>i', numMeshObjs))
        for obj in meshObjects:
            exportMeshObject(file, obj)
        
        #Sun object blocks
        file.write(struct.pack('>i', numSuns))
        for obj in sunObjects:
            exportSunObject(file, obj)
        
    finally:
        file.close()
    
    print("DVM EXPORT SUCCESSFUL.")
    return {'FINISHED'}
