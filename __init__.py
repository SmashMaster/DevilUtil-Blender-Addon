bl_info = {
    "name": "DevilModel format (.dvm)",
    "description": "Exports DevilModel files.",
    "author": "SmashMaster",
    "version": (0, 1),
    "blender": (2, 74, 0),
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
    
    bpy.types.ID.dvm_array_index = bpy.props.IntProperty(name = "DVMArrayIndex")
    bpy.types.Bone.dvm_bone_index = bpy.props.IntProperty(name = "DVMBoneIndex")
    bpy.types.Mesh.dvm_exp_normal = bpy.props.BoolProperty(name = "DVMExpNormal")
    bpy.types.Mesh.dvm_exp_tangent = bpy.props.BoolProperty(name = "DVMExpTangent")
    bpy.types.Mesh.dvm_exp_groups = bpy.props.BoolProperty(name = "DVMExpGroups")
    bpy.types.Mesh.dvm_exp_mat_inds = bpy.props.BoolProperty(name = "DVMExpMatInds")
    bpy.types.Mesh.dvm_tan_uv_src = bpy.props.StringProperty(name = "DVMTanUVSrc")
    
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