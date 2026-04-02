"""UI panels for Blockblend plugin"""

import bpy
from bpy.types import Panel


# ============================================================
# 主面板：对象信息
# ============================================================

class VIEW3D_PT_blockblend_main_panel(Panel):
    """Blockblend 主面板 — 显示当前对象信息"""
    bl_label = "Blockblend"
    bl_idname = "VIEW3D_PT_blockblend_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blockblend'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if obj and obj.type == 'MESH':
            box = layout.box()
            row = box.row(align=True)
            row.label(text=obj.name, icon='OBJECT_DATAMODE')

            row = box.row(align=True)
            row.label(text=f"面: {len(obj.data.polygons):,}", icon='MESH_DATA')
            row.label(text=f"顶点: {len(obj.data.vertices):,}")

            dimensions = obj.dimensions
            row = box.row(align=True)
            row.label(text=f"尺寸: {dimensions.x:.2f} x {dimensions.y:.2f} x {dimensions.z:.2f}")
        else:
            box = layout.box()
            box.label(text="请选择一个网格对象", icon='ERROR')


# ============================================================
# 子面板 1：生成立方体包围盒
# ============================================================

class VIEW3D_PT_blockblend_convert_panel(Panel):
    """生成立方体包围盒子面板"""
    bl_label = "生成立方体包围盒"
    bl_idname = "VIEW3D_PT_blockblend_convert_panel"
    bl_parent_id = "VIEW3D_PT_blockblend_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blockblend'

    def draw(self, context):
        layout = self.layout
        props = context.scene.blockblend_props

        # --- 引擎选择 ---
        box = layout.box()
        box.label(text="分解模式", icon='MOD_REMESH')

        row = box.row(align=True)
        row.prop(props, "engine_mode", text="")

        # --- 引擎特定参数 ---
        box = layout.box()

        if props.engine_mode == 'OBB':
            box.label(text="OBB 设置", icon='ORIENTATION_LOCAL')
            row = box.row(align=True)
            row.prop(props, "cube_count", slider=True)
            row = box.row(align=True)
            row.prop(props, "min_cube_size", slider=True)

        elif props.engine_mode == 'HEIGHTFIELD':
            box.label(text="高度场设置", icon='GRID')
            row = box.row(align=True)
            row.prop(props, "voxel_size", slider=True)

        # --- 立方体设置 ---
        box = layout.box()
        box.label(text="立方体设置", icon='CUBE')

        row = box.row(align=True)
        row.prop(props, "collection_name")

        row = box.row(align=True)
        row.prop(props, "cube_gap", slider=True)

        # --- 材质和颜色 ---
        box = layout.box()
        box.label(text="材质和颜色", icon='MATERIAL')

        row = box.row()
        row.prop(props, "preserve_materials")

        row = box.row(align=True)
        row.label(text="颜色模式:")
        row.prop(props, "color_mode", text="")

        if props.color_mode == 'UNIFORM':
            row = box.row(align=True)
            row.prop(props, "uniform_color")
        elif props.color_mode == 'RANDOM':
            row = box.row(align=True)
            row.prop(props, "base_color")
            row = box.row(align=True)
            row.prop(props, "color_variation", slider=True)

        # --- 操作按钮 ---
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5

        btn_text = (
            "生成高度场方块" if props.engine_mode == 'HEIGHTFIELD'
            else "生成 OBB 包围盒"
        )
        row.operator(
            "object.blockblend_convert",
            text=btn_text,
            icon='GRID' if props.engine_mode == 'HEIGHTFIELD' else 'MESH_MONKEY',
        )

        # 统计信息
        if props.generated_cube_count > 0:
            row = layout.row()
            row.label(
                text=f"上次: {props.generated_cube_count} 个立方体 "
                     f"(目标 {props.last_cube_count_setting})",
                icon='INFO',
            )


# ============================================================
# 子面板 2：烘焙贴图
# ============================================================

class VIEW3D_PT_blockblend_bake_panel(Panel):
    """烘焙贴图子面板"""
    bl_label = "烘焙贴图"
    bl_idname = "VIEW3D_PT_blockblend_bake_panel"
    bl_parent_id = "VIEW3D_PT_blockblend_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blockblend'

    def draw(self, context):
        layout = self.layout
        props = context.scene.blockblend_props

        # --- 对象选择 ---
        box = layout.box()
        box.label(text="烘焙对象", icon='OBJECT_DATA')

        row = box.row(align=True)
        row.prop(props, "bake_source_object", text="源 (高模)")

        row = box.row(align=True)
        row.prop(props, "bake_target_object", text="目标 (LOD)")

        # 验证提示
        source = props.bake_source_object
        target = props.bake_target_object

        if source and target:
            if source == target:
                row = box.row()
                row.label(text="源和目标不能是同一对象!", icon='ERROR')
            elif not target.data.uv_layers.active:
                row = box.row()
                row.label(text="目标没有UV贴图!", icon='ERROR')
        elif not source and not target:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text="请在上方选择源模型和目标模型", icon='INFO')

        # --- 烘焙设置 ---
        box = layout.box()
        box.label(text="烘焙设置", icon='NODE_MATERIAL')

        row = box.row(align=True)
        row.prop(props, "bake_type", text="类型")
        row = box.row(align=True)
        row.prop(props, "bake_resolution", text="分辨率")
        row = box.row(align=True)
        row.prop(props, "bake_margin", text="边距")

        if props.bake_type in {'AO', 'COMBINED'}:
            row = box.row(align=True)
            row.prop(props, "bake_samples", text="采样")

        # --- 操作按钮 ---
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator(
            "object.blockblend_bake",
            text="烘焙贴图到目标模型",
            icon='RENDER_STILL',
        )


# ============================================================
# 关于面板
# ============================================================

class VIEW3D_PT_blockblend_info_panel(Panel):
    """Blockblend 信息面板"""
    bl_label = "关于"
    bl_idname = "VIEW3D_PT_blockblend_info_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blockblend'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.blockblend_props

        col = layout.column(align=True)
        col.label(text="Blockblend v1.0.0", icon='PLUGIN')
        col.separator()
        col.label(text="用多个立方体概括模型形状", icon='INFO')

        if props.generated_cube_count > 0:
            layout.separator()
            box = layout.box()
            box.label(text="转换统计", icon='TRACKER')
            col = box.column(align=True)
            col.label(text=f"立方体数量: {props.generated_cube_count:,}")
            col.label(text=f"目标数量: {props.last_cube_count_setting}")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="使用方法:", icon='QUESTION')
        col = layout.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. 选择一个网格对象")
        col.label(text="2. 设置立方体数量和最小尺寸")
        col.label(text="3. 点击'生成立方体包围盒'")
        col.label(text="4. 再次点击可替换之前的结果")
        col.label(text="5. 按Ctrl+Z撤销重试")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="烘焙贴图:", icon='QUESTION')
        col = layout.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. 在烘焙面板选择源模型 (高模)")
        col.label(text="2. 选择目标模型 (LOD)")
        col.label(text="3. 选择烘焙类型和分辨率")
        col.label(text="4. 点击'烘焙贴图到目标模型'")


# ============================================================
# 注册
# ============================================================

_classes = [
    VIEW3D_PT_blockblend_main_panel,
    VIEW3D_PT_blockblend_convert_panel,
    VIEW3D_PT_blockblend_bake_panel,
    VIEW3D_PT_blockblend_info_panel,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
