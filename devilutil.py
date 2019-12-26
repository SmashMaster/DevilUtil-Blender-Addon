bl_info = {
    "name": "DevilUtil Properties",
    "description": "Allows custom properties to be edited for DevilUtil.",
    "author": "SmashMaster",
    "version": (0, 24),
    "blender": (2, 81, 0),
    "location": "Properties > Object > DevilUtil",
    "warning": "",
    "category": "Interface"}

import imp
import bpy

from bpy.types import (
    Operator,
    Panel,
    UIList,
    PropertyGroup
)
from bpy.props import (
    StringProperty,
    BoolProperty,
    CollectionProperty,
)

class DVMArgPropertyGroup(PropertyGroup):
    value = StringProperty(name = "Value")

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
    bl_label = "DevilUtil"
    
    def draw(self, context):
        layout = self.layout
        obj = context.object
        
        layout.label(text = "Arguments")
        
        row = layout.row()
        row.template_list("DVM_object_args_list", "dvmargs", obj, "dvm_args", obj, "dvm_args_active_index", rows=1)
        
        col = row.column(align=True)
        col.operator("object.dvm_arg_add", icon='ADD', text="")
        col.operator("object.dvm_arg_remove", icon='REMOVE', text="")

classes = (
    DVMArgPropertyGroup,
    DVM_object_args_list,
    OBJECT_OT_dvm_arg_add,
    OBJECT_OT_dvm_arg_remove,
    DVM_object_menu,
    )
        
def register():
    from bpy.utils import register_class
    
    for cls in classes:
        register_class(cls)
    
    bpy.types.Object.dvm_args = CollectionProperty(
        type = DVMArgPropertyGroup,
        name = "DevilUtil Arguments",
        description = "Used to set custom properties for DevilUtil.")
    bpy.types.Object.dvm_args_active_index = bpy.props.IntProperty(options = {'HIDDEN', 'SKIP_SAVE'})
    
def unregister():
    from bpy.utils import unregister_class
    
    del bpy.types.Object.dvm_args
    
    for cls in reversed(classes):
        unregister_class(cls)

if __name__ == "__main__":
    register()