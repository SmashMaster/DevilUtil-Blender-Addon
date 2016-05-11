bl_info = {
    "name": "DevilModel format (.dvm)",
    "description": "Exports DevilModel files.",
    "author": "SmashMaster",
    "version": (0, 16),
    "blender": (2, 27, 0),
    "location": "File > Export > DevilModel (.dvm)",
    "category": "Import-Export"}

import imp
import bpy

from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper

class DVMExporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_mesh.dvm"
    bl_label = "Export DVM"

    filename_ext = ".dvm"
    filter_glob = StringProperty(default="*.dvm", options={'HIDDEN'})
    
    bpy.types.ID.dvm_array_index = bpy.props.IntProperty(options = {'HIDDEN'})
    bpy.types.Bone.dvm_bone_index = bpy.props.IntProperty(options = {'HIDDEN'})
    bpy.types.Mesh.dvm_exp_normal = bpy.props.BoolProperty(name = "DVM Export Normals", default = True)
    bpy.types.Mesh.dvm_exp_tangent = bpy.props.BoolProperty(name = "DVM Export Tangents")
    bpy.types.Mesh.dvm_tan_uv_src = bpy.props.StringProperty(name = "DVM Tangent UV Source")
    bpy.types.Mesh.dvm_exp_groups = bpy.props.BoolProperty(name = "DVM Export Groups")
    bpy.types.Mesh.dvm_exp_mat_inds = bpy.props.BoolProperty(name = "DVM Export Material Indices")
    bpy.types.Object.dvm_type = bpy.props.StringProperty(name = "DVM Type")
    
    def execute(self, context):
        from . import export_dvm
        imp.reload(export_dvm)
        return export_dvm.export(self.filepath)

def menu_export(self, context):
    self.layout.operator(DVMExporter.bl_idname, text="DevilModel (.dvm)")

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_export.append(menu_export)
 
def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_export.remove(menu_export)

if __name__ == "__main__":
    register()