"""UI panels for Blockblend plugin"""

import bpy
from bpy.types import Panel


class VIEW3D_PT_blockblend_main_panel(Panel):
    """Blockblend主面板"""
    bl_label = "Blockblend"
    bl_idname = "VIEW3D_PT_blockblend_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blockblend'

    def draw(self, context):
        """
        绘制面板UI

        Args:
            context: Blender上下文
        """
        layout = self.layout
        scene = context.scene
        props = scene.blockblend_props

        # === 对象信息 ===
        obj = context.active_object

        if obj and obj.type == 'MESH':
            box = layout.box()
            box.label(text="当前对象:", icon='OBJECT_DATAMODE')

            row = box.row(align=True)
            row.label(text=obj.name, icon='EDITMODE_HLT')

            # 统计信息
            row = box.row(align=True)
            row.label(text=f"面数: {len(obj.data.polygons):,}", icon='MESH_DATA')
            row.label(text=f"顶点: {len(obj.data.vertices):,}")

            # 显示尺寸
            dimensions = obj.dimensions
            row = box.row(align=True)
            row.label(text=f"尺寸: {dimensions.x:.2f} x {dimensions.y:.2f} x {dimensions.z:.2f}")

        else:
            box = layout.box()
            box.label(text="未选择对象", icon='ERROR')
            row = box.row()
            row.label(text="请选择一个网格对象")
            return

        layout.separator()

        # === 转换设置 ===
        box = layout.box()
        box.label(text="转换设置", icon='MOD_REMESH')

        # 体素大小
        row = box.row(align=True)
        row.prop(props, "voxel_size", slider=True)

        # 自动计算体素大小按钮
        row = box.row(align=True)
        row.label(text="自动计算:")
        row.prop(props, "detail_level", slider=True)

        # 适应性
        row = box.row(align=True)
        row.prop(props, "adaptivity", slider=True)

        layout.separator()

        # === 立方体设置 ===
        box = layout.box()
        box.label(text="立方体设置", icon='CUBE')

        row = box.row()
        row.prop(props, "create_cubes")

        if props.create_cubes:
            row = box.row(align=True)
            row.prop(props, "cube_gap", slider=True)
            row = box.row(align=True)
            row.prop(props, "cube_scale", slider=True)

            row = box.row()
            row.prop(props, "merge_cubes")

        layout.separator()

        # === 材质和颜色 ===
        box = layout.box()
        box.label(text="材质和颜色", icon='MATERIAL')

        row = box.row()
        row.prop(props, "preserve_materials")

        if props.preserve_materials:
            row = box.row(align=True)
            row.label(text="颜色覆盖:")
            row.prop(props, "color_mode", text="")
        else:
            row = box.row(align=True)
            row.label(text="颜色模式:")
            row.prop(props, "color_mode", text="")

        # 根据颜色模式显示相应选项
        if props.color_mode == 'UNIFORM':
            row = box.row(align=True)
            row.prop(props, "uniform_color")
        elif props.color_mode == 'RANDOM':
            row = box.row(align=True)
            row.prop(props, "base_color")
            row = box.row(align=True)
            row.prop(props, "color_variation", slider=True)

        layout.separator()

        # === 高级设置 ===
        box = layout.box()
        box.label(text="高级设置", icon='SETTINGS')

        row = box.row()
        row.prop(props, "smooth_shading")
        row = box.row()
        row.prop(props, "remove_original")

        layout.separator()

        # === 操作按钮 ===
        # 主要转换按钮
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("object.blockblend_convert", text="转换为方块风格", icon='MESH_MONKEY')

        # 如果有统计信息，显示
        if props.cube_count > 0:
            row = layout.row()
            row.label(text=f"上次转换: 创建了 {props.cube_count} 个立方体", icon='INFO')
            if props.last_voxel_size > 0:
                row = layout.row()
                row.label(text=f"体素大小: {props.last_voxel_size:.3f}", icon='DOT')

        layout.separator()

        # === 帮助信息 ===
        box = layout.box()
        box.label(text="提示:", icon='HELP')

        col = box.column(align=True)
        col.label(text="• 较小的体素值 = 更多细节")
        col.label(text="• 适应性0 = 均匀方块")
        col.label(text="• 适应性1 = 自适应细节")
        col.label(text="• 合并立方体可提高性能")
        col.label(text="• 按Ctrl+Z可撤销转换")


class VIEW3D_PT_blockblend_info_panel(Panel):
    """Blockblend信息面板"""
    bl_label = "关于"
    bl_idname = "VIEW3D_PT_blockblend_info_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blockblend'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """
        绘制信息面板

        Args:
            context: Blender上下文
        """
        layout = self.layout
        scene = context.scene
        props = scene.blockblend_props

        # 插件信息
        col = layout.column(align=True)
        col.label(text="Blockblend v1.0.0", icon='PLUGIN')
        col.separator()
        col.label(text="将高模转换为方块风格", icon='INFO')
        col.separator()

        # 统计信息
        if props.cube_count > 0:
            box = layout.box()
            box.label(text="转换统计", icon='TRACKER')
            col = box.column(align=True)
            col.label(text=f"立方体数量: {props.cube_count:,}")
            if props.last_voxel_size > 0:
                col.label(text=f"体素大小: {props.last_voxel_size:.3f}")

        # 说明
        layout.separator()
        col = layout.column(align=True)
        col.label(text="使用方法:", icon='QUESTION')
        col = layout.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. 选择一个网格对象")
        col.label(text="2. 调整参数设置")
        col.label(text="3. 点击'转换为方块风格'")
        col.label(text="4. 按Ctrl+Z撤销重试")


# 注册和注销
_classes = [
    VIEW3D_PT_blockblend_main_panel,
    VIEW3D_PT_blockblend_info_panel
]


def register():
    """注册UI面板"""
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    """注销UI面板"""
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
