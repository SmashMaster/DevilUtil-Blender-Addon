bl_info = {
    "name": "DevilModel format (.dvm)",
    "description": "Exports DevilModel files.",
    "author": "SmashMaster",
    "version": (0, 20),
    "blender": (2, 27, 0),
    "location": "File > Export > DevilModel (.dvm)",
    "category": "Import-Export"}

import imp
import bpy

from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper
from bpy.types import Operator, Panel, UIList

class DVMArgPropertyGroup(bpy.types.PropertyGroup):
    value = bpy.props.StringProperty(name = "Value")

class DVM_object_args_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text = "", emboss=False)
        layout.prop(item, "value", text = "", emboss=True)
        pass
        
class OBJECT_OT_dvm_arg_add(Operator):
    bl_idname = "object.dvm_arg_add"
    bl_label = "Add DVM Argument"
 
    def execute(self, context):
        obj = context.object
        val = obj.dvm_args.add()
        val.name = "Argument" + str(len(obj.dvm_args))
        obj.dvm_args_active_index = max(obj.dvm_args_active_index, 0)
        return {'FINISHED'}
        
class OBJECT_OT_dvm_arg_remove(Operator):
    bl_idname = "object.dvm_arg_remove"
    bl_label = "Remove DVM Argument"
 
    def execute(self, context):
        obj = context.object
        obj.dvm_args.remove(obj.dvm_args_active_index)
        obj.dvm_args_active_index = min(obj.dvm_args_active_index, len(obj.dvm_args) - 1)
        return {'FINISHED'}

class DVM_object_menu(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_label = "DevilModel"
    
    def draw(self, context):
        layout = self.layout
        obj = context.object
        
        layout.label("Arguments")
        
        row = layout.row()
        row.template_list("DVM_object_args_list", "dvmargs", obj, "dvm_args", obj, "dvm_args_active_index", rows=1)
        
        col = row.column(align=True)
        col.operator("object.dvm_arg_add", icon='ZOOMIN', text="")
        col.operator("object.dvm_arg_remove", icon='ZOOMOUT', text="")
        
class DVMExporter(Operator, ExportHelper):
    bl_idname = "export_mesh.dvm"
    bl_label = "Export DVM"

    filename_ext = ".dvm"
    filter_glob = StringProperty(default="*.dvm", options={'HIDDEN'})
    
    def execute(self, context):
        from . import export_dvm
        imp.reload(export_dvm)
        return export_dvm.export(self.filepath)
        
def menu_export(self, context):
    self.layout.operator(DVMExporter.bl_idname, text="DevilModel (.dvm)")

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_export.append(menu_export)
    
    bpy.types.ID.dvm_array_index = bpy.props.IntProperty(options = {'HIDDEN', 'SKIP_SAVE'})
    bpy.types.Bone.dvm_bone_index = bpy.props.IntProperty(options = {'HIDDEN', 'SKIP_SAVE'})
    bpy.types.Mesh.dvm_exp_normal = bpy.props.BoolProperty(name = "DVM Export Normals", default = True)
    bpy.types.Mesh.dvm_exp_tangent = bpy.props.BoolProperty(name = "DVM Export Tangents")
    bpy.types.Mesh.dvm_tan_uv_src = bpy.props.StringProperty(name = "DVM Tangent UV Source")
    bpy.types.Mesh.dvm_exp_groups = bpy.props.BoolProperty(name = "DVM Export Groups", default = True)
    bpy.types.Mesh.dvm_exp_mat_inds = bpy.props.BoolProperty(name = "DVM Export Material Indices", default = True)
    bpy.types.Object.dvm_args = bpy.props.CollectionProperty(name = "DVM Arguments", type = DVMArgPropertyGroup, options = {'HIDDEN'})
    bpy.types.Object.dvm_args_active_index = bpy.props.IntProperty(options = {'HIDDEN', 'SKIP_SAVE'})
 
def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_export.remove(menu_export)

if __name__ == "__main__":
    register()