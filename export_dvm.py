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

def vec3BlendToDevil(vector):
    return [vector[1], vector[2], vector[0]]
    
def mat4BlendToDevilmat3(m):
    return [m[1][1], m[1][2], m[1][0],    m[2][1], m[2][2], m[2][0],    m[0][1], m[0][2], m[0][0]]

class IKConstraint:
    def __init__(self, bone, constraint, bone_indices):
        self.constraint = constraint
        self.bone_index = bone_indices[bone.name]
        self.target_index = bone_indices[constraint.subtarget]
        self.pole_target_index = bone_indices[constraint.pole_subtarget]

DVM_BONE_INHERIT_ROTATION_FLAG = 1
DVM_BONE_LOCAL_LOCATION = 2

def exportArmature(file, object):
    armature = object.data
    pose = object.pose
    bones = armature.bones
    num_bones = len(bones)
    file.write(struct.pack('>i', num_bones))
    
    bone_indices = {}
    
    for i in range(num_bones):
        bone_indices[bones[i].name] = i
    
    #Export bones
    for bone in bones:
        #Write bone name
        writePaddedJavaUTF(file, bone.name)
        
        #Write bone parent
        if bone.parent is not None:
            file.write(struct.pack('>i', bone_indices[bone.parent.name]))
        else:
            file.write(struct.pack('>i', -1))
        
        #Write bone flags
        flag_bits = 0
        if bone.use_inherit_rotation:
            flag_bits |= DVM_BONE_INHERIT_ROTATION_FLAG
        if bone.use_local_location:
            flag_bits |= DVM_BONE_LOCAL_LOCATION
        file.write(struct.pack('>i', flag_bits))
        
        #Write bone head and tail
        file.write(struct.pack('>3f', *vec3BlendToDevil(bone.head_local)))
        file.write(struct.pack('>3f', *vec3BlendToDevil(bone.tail_local)))
        
        #Write bone matrix
        file.write(struct.pack('>9f', *mat4BlendToDevilmat3(bone.matrix_local)))
    
    #Export IK constraints
    ik_constraints = []
    for pose_bone in pose.bones:
        for constraint in pose_bone.constraints:
            if isinstance(constraint, bpy.types.KinematicConstraint):
                if constraint.chain_count != 2:
                    continue
                if constraint.target is None or constraint.subtarget not in bone_indices:
                    continue
                if constraint.pole_target is None or constraint.pole_subtarget not in bone_indices:
                    continue
                ik_constraints.append(IKConstraint(pose_bone.bone, constraint, bone_indices))
    
    file.write(struct.pack('>i', len(ik_constraints)))
    for ik_constraint in ik_constraints:
        file.write(struct.pack('>i', ik_constraint.bone_index))
        file.write(struct.pack('>i', ik_constraint.target_index))
        file.write(struct.pack('>i', ik_constraint.pole_target_index))
        file.write(struct.pack('>f', ik_constraint.constraint.pole_angle))
    
    return bone_indices

DVM_PROPERTY_NAMES = ["LC", "RT"]
DVM_PROPERTY_LOCATION = 0
DVM_PROPERTY_ROTATION = 1
DVM_REMAP_LOCATION = [2, 0, 1]
DVM_REMAP_ROTATION = [0, 3, 1, 2]
DVM_INTERPOLATION_CONSTANT = 0
DVM_INTERPOLATION_LINEAR = 1
DVM_INTERPOLATION_BEZIER = 2

class BoneFCurve:
    def __init__(self, fcurve, bone_index, property):
        self.fcurve = fcurve
        self.bone_index = bone_index
        self.property = property
        
        if property == DVM_PROPERTY_LOCATION:
            self.array_index = DVM_REMAP_LOCATION[fcurve.array_index]
        elif property == DVM_PROPERTY_ROTATION:
            self.array_index = DVM_REMAP_ROTATION[fcurve.array_index]
    
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
            property = DVM_PROPERTY_LOCATION
        elif property_name == "rotation_quaternion":
            property = DVM_PROPERTY_ROTATION
        else:
            continue
        
        fcurves.append(BoneFCurve(fcurve, bone_index, property))
    
    #Write fcurves
    file.write(struct.pack('>i', len(fcurves)))
    for fcurve in fcurves:
        fcurve.fcurve.update()
        
        #Write bone, property, and property index
        file.write(struct.pack('>i', fcurve.bone_index))
        writeJavaUTF(file, DVM_PROPERTY_NAMES[fcurve.property])
        file.write(struct.pack('>i', fcurve.array_index))
        
        #Write keyframes
        keyframes = fcurve.fcurve.keyframe_points
        file.write(struct.pack('>i', len(keyframes)))
        for keyframe in keyframes:
            interp_name = keyframe.interpolation
            interp_id = DVM_INTERPOLATION_LINEAR
            if interp_name == 'CONSTANT':
                interp_id = DVM_INTERPOLATION_CONSTANT
            elif interp_name == 'BEZIER':
                interp_id = DVM_INTERPOLATION_BEZIER
            
            file.write(struct.pack('>i', interp_id))
            file.write(struct.pack('>2f', *keyframe.co))
            file.write(struct.pack('>2f', *keyframe.handle_left))
            file.write(struct.pack('>2f', *keyframe.handle_right))

class LoopVertex:
    def __init__(self, mesh, poly, loop):
        self.poly = poly
        self.loop = loop
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
        
def loopVerticesEqual(lva, lvb):
    #Ensure indices are equal
    if lva.loop.vertex_index != lvb.loop.vertex_index:
        return False

    #Ensure normals are equal
    for a, b in zip(lva.loop.normal, lvb.loop.normal):
        if a != b:
            return False
    
    #Ensure uvs, colors, tangents, and groups are equal
    
    return True

def prepareMesh(mesh):
    #Make sure we have all of the data we need
    mesh.calc_tessface()
    mesh.calc_normals_split()
    
    num_uv_layers = len(mesh.uv_layers)
    num_color_layers = len(mesh.vertex_colors)
    num_groups = 0
    
    #Set up LoopVertex list
    loop_vertex_sets = [set() for i in range(len(mesh.vertices))]
    for poly in mesh.polygons:
        for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
            loop = mesh.loops[loop_index]
            loop_vertex = LoopVertex(mesh, poly, loop)
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
    
    return vertices, triangles, num_uv_layers, num_color_layers, num_groups

DVM_MESH_FLAG_HAS_UVS = 1
DVM_MESH_FLAG_HAS_VERTEX_COLORS = 2

def exportMesh(file, mesh):
    vertices, triangles, num_uv_layers, num_color_layers, num_groups = prepareMesh(mesh)
    
    print(num_color_layers)

def tagIndex(idList):
    for i, id in enumerate(idList):
        id.tag = i

def export(filepath, use_tangents):
    os.system("cls")
    print("EXPORTING DVM...")
    
    # Exit edit mode before exporting, so current object states are exported properly.
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    
    #Export lists
    meshes = []
    armatures = []
    objects = []
    
    #Find valid exportable data blocks
    for obj in bpy.data.objects:
        if isinstance(obj.data, bpy.types.Mesh):
            meshes.append(obj.data)
            objects.append(obj)
        elif isinstance(obj.data, bpy.types.Armature):
            armatures.append(obj.data)
            objects.append(obj)
    
    #Set data block tags to array indices
    tagIndex(meshes)
    tagIndex(armatures)
    tagIndex(objects)
    
    for mesh in meshes:
        exportMesh(None, mesh)
    
    print("DVM EXPORT SUCCESSFUL.")
    return {'FINISHED'}
