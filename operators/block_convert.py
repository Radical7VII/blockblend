"""Block conversion operator"""

import bpy
from ..core.voxel_remesh_engine import VoxelRemeshEngine


class OBJECT_OT_blockblend_convert(bpy.types.Operator):
    """转换为方块风格"""
    bl_idname = "object.blockblend_convert"
    bl_label = "转换为方块风格"
    bl_description = "将选中的高模对象转换为方块风格的低模"
    bl_options = {'REGISTER', 'UNDO'}  # 启用撤销/重做

    # === Operator属性 ===

    # 基础参数
    voxel_size: bpy.props.FloatProperty(
        name="体素大小",
        description="控制方块大小，值越大方块越大",
        min=0.001,
        max=10.0,
        default=0.1,
        step=0.01,
        precision=3,
        unit='LENGTH'
    )

    adaptivity: bpy.props.FloatProperty(
        name="适应性",
        description="0=均匀分布，1=自适应细节",
        min=0.0,
        max=1.0,
        default=0.0,
        step=0.05,
        precision=2
    )

    # 立方体设置
    create_cubes: bpy.props.BoolProperty(
        name="创建独立立方体",
        description="将每个体素转换为独立的立方体对象",
        default=True
    )

    cube_gap: bpy.props.FloatProperty(
        name="立方体间隙",
        description="立方体之间的间隙比例",
        min=0.0,
        max=0.5,
        default=0.05,
        step=0.01,
        precision=2
    )

    # 材质和颜色
    preserve_materials: bpy.props.BoolProperty(
        name="保留材质",
        description="将原始材质应用到新立方体",
        default=True
    )

    color_mode: bpy.props.EnumProperty(
        name="颜色模式",
        description="如何为立方体着色",
        items=[
            ('ORIGINAL', '原始材质', '保留原始材质'),
            ('UNIFORM', '统一颜色', '所有立方体使用相同颜色'),
            ('RANDOM', '随机颜色', '为每个立方体分配随机颜色'),
            ('HEIGHT', '基于高度', '根据高度渐变着色'),
            ('POSITION', '基于位置', '根据位置着色'),
        ],
        default='ORIGINAL'
    )

    uniform_color: bpy.props.FloatVectorProperty(
        name="统一颜色",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(0.5, 0.5, 0.5)
    )

    color_variation: bpy.props.FloatProperty(
        name="颜色变化",
        description="随机颜色的变化范围",
        min=0.0,
        max=1.0,
        default=0.3,
        step=0.05
    )

    base_color: bpy.props.FloatVectorProperty(
        name="基础颜色",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(0.8, 0.6, 0.4)
    )

    # 高级设置
    smooth_shading: bpy.props.BoolProperty(
        name="平滑着色",
        description="对立方体应用平滑着色",
        default=False
    )

    merge_cubes: bpy.props.BoolProperty(
        name="合并立方体",
        description="将所有立方体合并为单一网格",
        default=False
    )

    remove_original: bpy.props.BoolProperty(
        name="删除原始对象",
        description="转换后删除原始高模对象",
        default=False
    )

    @classmethod
    def poll(cls, context):
        """
        检查操作是否可以执行

        Args:
            context: Blender上下文

        Returns:
            如果可以执行则返回True
        """
        return (
            context.active_object and
            context.active_object.type == 'MESH'
        )

    def invoke(self, context, event):
        """
        显示对话框

        Args:
            context: Blender上下文
            event: 事件

        Returns:
            运行时属性
        """
        # 从场景属性加载默认值
        props = context.scene.blockblend_props

        self.voxel_size = props.voxel_size
        self.adaptivity = props.adaptivity
        self.create_cubes = props.create_cubes
        self.cube_gap = props.cube_gap
        self.preserve_materials = props.preserve_materials
        self.color_mode = props.color_mode
        self.uniform_color = props.uniform_color
        self.color_variation = props.color_variation
        self.base_color = props.base_color
        self.smooth_shading = props.smooth_shading
        self.merge_cubes = props.merge_cubes
        self.remove_original = props.remove_original

        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        """
        执行转换操作

        Args:
            context: Blender上下文

        Returns:
            操作结果
        """
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格对象")
            return {'CANCELLED'}

        # 保存场景属性
        props = context.scene.blockblend_props
        props.voxel_size = self.voxel_size
        props.adaptivity = self.adaptivity
        props.create_cubes = self.create_cubes
        props.cube_gap = self.cube_gap
        props.preserve_materials = self.preserve_materials
        props.color_mode = self.color_mode
        props.uniform_color = self.uniform_color
        props.color_variation = self.color_variation
        props.base_color = self.base_color
        props.smooth_shading = self.smooth_shading
        props.merge_cubes = self.merge_cubes
        props.remove_original = self.remove_original

        # 创建转换引擎
        engine = VoxelRemeshEngine(obj)

        try:
            # 执行转换
            cube_size_factor = 1.0 - self.cube_gap

            result = engine.execute(
                voxel_size=self.voxel_size,
                create_cubes=self.create_cubes,
                cube_size_factor=cube_size_factor,
                adaptivity=self.adaptivity,
                preserve_materials=self.preserve_materials,
                color_mode=self.color_mode,
                uniform_color=self.uniform_color,
                color_variation=self.color_variation,
                base_color=self.base_color,
                smooth_shading=self.smooth_shading,
                merge_cubes=self.merge_cubes,
                remove_original=self.remove_original
            )

            # 更新统计信息
            if isinstance(result, list):
                props.cube_count = len(result)
                self.report({'INFO'}, f"成功创建了 {len(result)} 个立方体")
            else:
                # 计算创建的立方体数量
                if self.create_cubes and not self.merge_cubes:
                    # 统计所有Blockblend_Cube开头的对象
                    cube_count = sum(
                        1 for obj in bpy.data.objects
                        if obj.name.startswith("Blockblend_Cube")
                    )
                    props.cube_count = cube_count
                elif self.merge_cubes:
                    props.cube_count = 0  # 合并后无法准确计数

                props.last_voxel_size = self.voxel_size
                self.report({'INFO'}, "转换完成")

            return {'FINISHED'}

        except ValueError as e:
            self.report({'ERROR'}, f"参数错误: {str(e)}")
            return {'CANCELLED'}

        except RuntimeError as e:
            self.report({'ERROR'}, f"转换失败: {str(e)}")
            return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"未知错误: {str(e)}")
            return {'CANCELLED'}

    def draw(self, context):
        """
        绘制对话框UI

        Args:
            context: Blender上下文
        """
        layout = self.layout
        scene = context.scene

        # 基础转换设置
        box = layout.box()
        box.label(text="转换设置", icon='MOD_REMESH')

        row = box.row()
        row.prop(self, "voxel_size")
        row = box.row()
        row.prop(self, "adaptivity")

        # 立方体设置
        box.separator()
        box.label(text="立方体设置", icon='CUBE')

        row = box.row()
        row.prop(self, "create_cubes")

        if self.create_cubes:
            row = box.row()
            row.prop(self, "cube_gap")
            row = box.row()
            row.prop(self, "merge_cubes")

        # 材质和颜色
        box.separator()
        box.label(text="材质和颜色", icon='MATERIAL')

        row = box.row()
        row.prop(self, "preserve_materials")

        if not self.preserve_materials or True:  # 始终显示颜色模式选项
            row = box.row()
            row.prop(self, "color_mode", text="颜色")

            if self.color_mode == 'UNIFORM':
                row = box.row()
                row.prop(self, "uniform_color")
            elif self.color_mode == 'RANDOM':
                row = box.row()
                row.prop(self, "base_color")
                row = box.row()
                row.prop(self, "color_variation")

        # 高级设置
        box.separator()
        box.label(text="高级设置", icon='SETTINGS')

        row = box.row()
        row.prop(self, "smooth_shading")
        row = box.row()
        row.prop(self, "remove_original")


# 注册和注销
_classes = [OBJECT_OT_blockblend_convert]


def register():
    """注册Operator"""
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    """注销Operator"""
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
