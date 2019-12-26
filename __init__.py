    bpy.types.Mesh.dvm_exp_mat_inds = bpy.props.BoolProperty(name = "DVM Export Material Indices", default = True)
    bpy.types.Object.dvm_args = bpy.props.CollectionProperty(name = "DVM Arguments", type = DVMArgPropertyGroup, options = {'HIDDEN'})
