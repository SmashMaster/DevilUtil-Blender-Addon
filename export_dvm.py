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
    padding = (4 - (bytes_written % 4)) % 4
    file.write(struct.pack('>' + str(padding) + 'x'))
    
def rotateYUp(vector):
    return [vector[0], vector[2], -vector[1]]

def exportArmature(file, armature):
    bones = armature.bones
    num_bones = len(bones)
    file.write(struct.pack('>i', num_bones))
    
    bone_indices = {}
    
    for i in range(num_bones):
        bone_indices[bones[i].name] = i
    
    for bone in bones:
        #Write bone name
        writePaddedJavaUTF(file, bone.name)
        
        #Write bone parent
        if bone.parent is not None:
            file.write(struct.pack('>i', bone_indices[bone.parent.name]))
        else:
            file.write(struct.pack('>i', -1))
        
        #Write inherit rotation
        file.write(struct.pack('>i', bone.use_inherit_rotation))
        
        #Write bone head and tail
        file.write(struct.pack('>3f', *rotateYUp(bone.head_local)))
        file.write(struct.pack('>3f', *rotateYUp(bone.tail_local)))
    
        #Write bone matrix (NEED TO ROTATE THIS SO Y AXIS IS UP?)
        for i in range(3):
            file.write(struct.pack('>3f', *bone.matrix[i]))
    
    return bone_indices

DVM_ACTION_ID_LOCATION = "LC"
DVM_ACTION_ID_ROTATION = "RT"
DVM_ACTION_INTERPOLATION_CONSTANT = 0
DVM_ACTION_INTERPOLATION_LINEAR = 1
DVM_ACTION_INTERPOLATION_BEZIER = 2

class BoneFCurve:
    def __init__(self, fcurve, bone_index, property):
        self.fcurve = fcurve
        self.bone_index = bone_index
        self.property = property
    
def exportAction(file, armature_bone_indices, action):
    #Write action name
    writePaddedJavaUTF(file, action.name)
    
    #Prepare fcurves
    fcurves = []
    for fcurve in action.fcurves:
        #Ensure we're working with a pose FCurve
        fpath = fcurve.data_path
        if not fpath.startswith("pose.bones[\""):
            continue
        
        #Ensure it has a proper name
        fpath = fpath[12:]
        bone_name_length = fpath.find("\"].")
        if bone_name_length is -1:
            continue
        
        #Ensure the bone actually exists
        bone_name = fpath[:bone_name_length]
        bone_index = armature_bone_indices[bone_name]
        if bone_index is None:
            continue
        
        #Ensure the property is valid
        property_name = fpath[bone_name_length + 3:]
        property = None
        if property_name == "location":
            property = DVM_ACTION_ID_LOCATION
        elif property_name == "rotation_quaternion":
            property = DVM_ACTION_ID_ROTATION
        else:
            continue
        
        fcurves.append(BoneFCurve(fcurve, bone_index, property))
    
    #Write fcurves
    file.write(struct.pack('>i', len(fcurves)))
    for fcurve in fcurves:
        fcurve.fcurve.update()
        
        #Write bone, property, and property index
        file.write(struct.pack('>i', fcurve.bone_index))
        writeJavaUTF(file, fcurve.property)
        file.write(struct.pack('>i', fcurve.fcurve.array_index))
        
        #Write keyframes
        keyframes = fcurve.fcurve.keyframe_points
        file.write(struct.pack('>i', len(keyframes)))
        for keyframe in keyframes:
            interp_name = keyframe.interpolation
            interp_id = DVM_ACTION_INTERPOLATION_LINEAR
            if interp_name == 'CONSTANT':
                interp_id = DVM_ACTION_INTERPOLATION_CONSTANT
            elif interp_name == 'BEZIER':
                interp_id = DVM_ACTION_INTERPOLATION_BEZIER
            
            file.write(struct.pack('>i', interp_id))
            file.write(struct.pack('>2f', *keyframe.co))
            file.write(struct.pack('>2f', *keyframe.handle_left))
            file.write(struct.pack('>2f', *keyframe.handle_right))

class LoopVertex:
    def __init__(self, mesh, poly, loop):
        self.poly = poly
        self.loop = loop
        self.uv_loop = mesh.uv_layers[0].data[loop.index] if mesh.uv_layers else None
        self.vertex_color_loop = mesh.vertex_colors[0].data[loop.index] if mesh.vertex_colors else None
        self.pointers = []

class Triangle:
    def __init__(self, indices):
        self.indices = indices

class LoopVertexPointer:
    def __init__(self, loop_vertex):
        self.loop_vertex = loop_vertex
        loop_vertex.pointers.append(self)
        
def loopVerticesEqual(lva, lvb):
    #Ensure indices are equal
    if lva.loop.vertex_index != lvb.loop.vertex_index:
        return False

    #Ensure normals are equal
    for a, b in zip(lva.loop.normal, lvb.loop.normal):
        if a != b:
            return False
    
    #Ensure uvs are equal
    lva_has_uv = lva.uv_loop is not None
    lvb_has_uv = lvb.uv_loop is not None
    
    if lva_has_uv and lvb_has_uv:
        for a, b in zip(lva.uv_loop.uv, lvb.uv_loop.uv):
            if a != b:
                return False
    elif lva_has_uv != lvb_has_uv:
        return False
    
    #Ensure colors are equal
    lva_has_color = lva.vertex_color_loop is not None
    lvb_has_color = lvb.vertex_color_loop is not None
    
    if lva_has_color and lvb_has_color:
        for a, b in zip(lva.vertex_color_loop.color, lvb.vertex_color_loop.color):
            if a != b:
                return False
    elif lva_has_color != lvb_has_color:
        return False
    
    return True

def prepareMesh(mesh):
    #Make sure we have all of the data we need
    mesh.calc_tessface()
    mesh.calc_normals_split()
    
    has_uvs = False
    has_vertex_colors = False
    
    #Set up LoopVertex list
    loop_vertex_sets = [set() for i in range(len(mesh.vertices))]
    for poly in mesh.polygons:
        for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
            loop = mesh.loops[loop_index]
            loop_vertex = LoopVertex(mesh, poly, loop)
            if loop_vertex.uv_loop is not None:
                has_uvs = True
            if loop_vertex.vertex_color_loop is not None:
                has_vertex_colors = True
            loop_vertex_sets[loop.vertex_index].add(loop_vertex)
    
    #Set up Triangle list
    triangles = []
    for face in mesh.tessfaces:
        verts = face.vertices
        if len(verts) == 4:
            triangles.append(Triangle([verts[0], verts[1], verts[2]]))
            triangles.append(Triangle([verts[2], verts[3], verts[0]]))
        else:
            triangles.append(Triangle(verts))
    
    for triangle in triangles:
        #Find which poly corresponds to this Triangle
        polysets = [set(loop_vertex.poly for loop_vertex in loop_vertex_sets[i]) for i in triangle.indices]
        triangle.poly = next(iter(set.intersection(*polysets)))
        
        #Find which loop_vertex objects correspond to each vertex of this Triangle
        #Also set up pointers
        triangle.loop_vertex_pointers = []
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
                if loopVerticesEqual(loop_vertex, new_loop_vertex):
                    identical = new_loop_vertex
                    for pointer in loop_vertex.pointers:
                        pointer.loop_vertex = new_loop_vertex
                        new_loop_vertex.pointers.append(pointer)
                    break
            if identical is None:
                new_loop_vertices.add(loop_vertex)
        loop_vertices.clear()
        loop_vertices |= new_loop_vertices
        
    #Do some final housecleaning
    vertices = []
    i = 0
    
    for loop_vertices in loop_vertex_sets:
        for loop_vertex in loop_vertices:
            loop_vertex.index = i
            loop_vertex.vert = mesh.vertices[loop_vertex.loop.vertex_index]
            i += 1
            vertices.append(loop_vertex)
    
    return vertices, triangles, has_uvs, has_vertex_colors

DVM_MESH_FLAG_HAS_UVS = 1
DVM_MESH_FLAG_HAS_VERTEX_COLORS = 2

def exportMesh(file, object, mesh, armature_bone_indices):
    vertices, triangles, has_uvs, has_vertex_colors = prepareMesh(mesh)
    
    #Write mesh name
    writePaddedJavaUTF(file, object.name)
    
    #Write flag bits
    flag_bits = 0
    if has_uvs:
        flag_bits |= DVM_MESH_FLAG_HAS_UVS
    if has_vertex_colors:
        flag_bits |= DVM_MESH_FLAG_HAS_VERTEX_COLORS
    file.write(struct.pack('>i', flag_bits))
    
    #Write textures
    textures = []
    if (mesh.materials):
        for texture_slot in mesh.materials[0].texture_slots:
            if texture_slot and texture_slot.use and hasattr(texture_slot.texture, 'image'):
                textures.append(texture_slot.texture)
                if len(textures) is 4:
                    break
    
    file.write(struct.pack('>i', len(textures)))
    for texture in textures:
        writePaddedJavaUTF(file, texture.image.name)
    
    #Write max number of vertex groups
    max_groups = 0
    if armature_bone_indices is not None:
        for vertex in vertices:
            max_groups = max(max_groups, len(vertex.vert.groups))
        file.write(struct.pack('>i', max_groups))
    
    #4 group maximum (just ignore weights after 4th, and don't bother normalizing weights.)
    max_groups = min(max_groups, 4)
    
    #Write vertices
    file.write(struct.pack('>i', len(vertices)))
    #Positions
    for vertex in vertices:
        file.write(struct.pack('>3f', *rotateYUp(vertex.vert.co)))
    #Normals
    for vertex in vertices:
        file.write(struct.pack('>3f', *rotateYUp(vertex.loop.normal)))
    #UVs
    if has_uvs:
        for vertex in vertices: 
            if vertex.uv_loop is not None:
                file.write(struct.pack('>2f', *vertex.uv_loop.uv))
            else:
                file.write(struct.pack('>8x'))
    #Vertex Colors
    if has_vertex_colors:
        for vertex in vertices: 
            if vertex.vertex_color_loop is not None:
                file.write(struct.pack('>3f', *vertex.vertex_color_loop.color))
            else:
                file.write(struct.pack('>12x'))
    
    groups = object.vertex_groups
    
    if armature_bone_indices is not None and max_groups > 0:
        #Vertex groups
        for vertex in vertices:
            groups_written = 0
            for group in vertex.vert.groups:
                bone_name = groups[group.group].name
                bone_index = armature_bone_indices[bone_name]
                if bone_index is None:
                    bone_index = -1
                
                file.write(struct.pack('>i', bone_index))
                groups_written += 1
            while groups_written < max_groups:
                file.write(struct.pack('>i', -1))
                groups_written += 1
        
        #Vertex weights
        for vertex in vertices:
            groups_written = 0
            for group in vertex.vert.groups:
                file.write(struct.pack('>f', group.weight))
                groups_written += 1
            
            while groups_written < max_groups:
                file.write(struct.pack('>f', 0.0))
                groups_written += 1
    
    #Write triangle indices
    file.write(struct.pack('>i', len(triangles)))
    for triangle in triangles:
        for pointer in triangle.loop_vertex_pointers:
            file.write(struct.pack('>i', pointer.loop_vertex.index))

def export(filepath):
    os.system("cls")

    # Exit edit mode before exporting, so current object states are exported properly.
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    file = open(filepath, "wb")
    try:
        writeJavaUTF(file, "DevilModel")
        
        armature_bone_indices = None
        
        #Export armature and actions
        if bpy.data.armatures:
            file.write(struct.pack('>i', True))
            armature = bpy.data.armatures[0]
            armature_bone_indices = exportArmature(file, bpy.data.armatures[0])
            old_pose_position = armature.pose_position
            armature.pose_position = 'REST'
            
            file.write(struct.pack('>i', len(bpy.data.actions)))
            for action in bpy.data.actions:
                exportAction(file, armature_bone_indices, action)
            
            armature.pose_position = old_pose_position
        else:
            file.write(struct.pack('>i', False))
        
        #Export meshes
        meshes = []
        for object in bpy.data.objects:
            if isinstance(object.data, bpy.types.Mesh):
                meshes.append(object)
        
        file.write(struct.pack('>i', len(meshes)))
        for mesh in meshes:
            exportMesh(file, mesh, mesh.data, armature_bone_indices)
    finally:
        file.close()
    
    return {'FINISHED'}
