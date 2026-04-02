"""Scene properties for Blockblend plugin"""

import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    FloatProperty,
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty
)


class BlockblendProperties(PropertyGroup):
    """Blockblend场景属性组"""

    # === 基础转换参数 ===

    voxel_size: FloatProperty(
        name="体素大小",
        description="控制方块大小，值越大方块越大，细节越少",
        min=0.01,
        max=10.0,
        default=0.1,
        step=0.01,
        precision=3,
        unit='LENGTH'
    )

    detail_level: FloatProperty(
        name="细节级别",
        description="自动计算体素大小的级别（0.1=粗糙，10.0=精细）",
        min=0.1,
        max=10.0,
        default=1.0,
        step=0.1,
        precision=1
    )

    adaptivity: FloatProperty(
        name="适应性",
        description="Voxel Remesh适应性（0=均匀分布，1=自适应细节）",
        min=0.0,
        max=1.0,
        default=0.0,
        step=0.05,
        precision=2
    )

    # === 立方体设置 ===

    create_cubes: BoolProperty(
        name="创建独立立方体",
        description="将每个体素转换为独立的立方体对象",
        default=True
    )

    cube_gap: FloatProperty(
        name="立方体间隙",
        description="立方体之间的间隙比例（0=无间隙，0.5=较大间隙）",
        min=0.0,
        max=0.5,
        default=0.05,
        step=0.01,
        precision=2
    )

    cube_scale: FloatProperty(
        name="立方体缩放",
        description="立方体的整体缩放比例",
        min=0.1,
        max=2.0,
        default=1.0,
        step=0.05,
        precision=2
    )

    # === 材质和颜色 ===

    preserve_materials: BoolProperty(
        name="保留材质",
        description="将原始材质应用到新立方体",
        default=True
    )

    color_mode: EnumProperty(
        name="颜色模式",
        description="如何为立方体着色",
        items=[
            ('ORIGINAL', '原始材质', '保留原始材质分配'),
            ('UNIFORM', '统一颜色', '所有立方体使用相同颜色'),
            ('RANDOM', '随机颜色', '为每个立方体分配随机颜色'),
            ('HEIGHT', '基于高度', '根据高度渐变着色'),
            ('POSITION', '基于位置', '根据X/Y/Z位置着色'),
        ],
        default='ORIGINAL'
    )

    uniform_color: FloatVectorProperty(
        name="统一颜色",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(0.5, 0.5, 0.5),
        description="所有立方体使用的统一颜色"
    )

    color_variation: FloatProperty(
        name="颜色变化",
        description="随机颜色的变化范围（0.0=无变化，1.0=完全随机）",
        min=0.0,
        max=1.0,
        default=0.3,
        step=0.05,
        precision=2
    )

    base_color: FloatVectorProperty(
        name="基础颜色",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(0.8, 0.6, 0.4),
        description="随机颜色模式的基础颜色"
    )

    # === 高级设置 ===

    smooth_shading: BoolProperty(
        name="平滑着色",
        description="对立方体应用平滑着色（关闭则产生平坦方块外观）",
        default=False
    )

    merge_cubes: BoolProperty(
        name="合并立方体",
        description="将所有立方体合并为单一网格对象（性能优化）",
        default=False
    )

    remove_original: BoolProperty(
        name="删除原始对象",
        description="转换后删除原始高模对象",
        default=False
    )

    # === 材质烘焙设置 ===

    bake_resolution: IntProperty(
        name="烘焙分辨率",
        description="烘焙贴图的分辨率（像素）",
        min=128,
        max=4096,
        default=1024,
        step=128
    )

    bake_samples: IntProperty(
        name="烘焙采样数",
        description="烘焙时的采样数量（越高越慢但质量更好）",
        min=1,
        max=256,
        default=64,
        step=1
    )

    bake_margin: IntProperty(
        name="烘焙边距",
        description="烘焙贴图的边距（像素）",
        min=0,
        max=64,
        default=4,
        step=1
    )

    # === 统计信息（只读）===

    cube_count: IntProperty(
        name="立方体数量",
        description="转换后创建的立方体数量",
        default=0,
        min=0
    )

    last_voxel_size: FloatProperty(
        name="上次体素大小",
        description="上次转换使用的体素大小",
        default=0.0,
        min=0.0
    )


# === 注册和注销函数 ===

def register():
    """注册场景属性"""
    # 必须先注册PropertyGroup类，然后才能注册PointerProperty
    bpy.utils.register_class(BlockblendProperties)
    bpy.types.Scene.blockblend_props = bpy.props.PointerProperty(
        type=BlockblendProperties
    )


def unregister():
    """注销场景属性"""
    if hasattr(bpy.types.Scene, 'blockblend_props'):
        del bpy.types.Scene.blockblend_props
    bpy.utils.unregister_class(BlockblendProperties)
