"""Scene properties for Blockblend plugin"""

import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    FloatProperty,
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)


def _is_mesh_object(self, obj):
    """只允许选择网格对象"""
    return obj.type == 'MESH'


class BlockblendProperties(PropertyGroup):
    """Blockblend场景属性组"""

    # === 引擎选择 ===

    engine_mode: EnumProperty(
        name="分解模式",
        description="选择形状分解算法",
        items=[
            ('OBB', 'OBB 分解', '有向包围盒层次化拆分，方块可旋转'),
            ('HEIGHTFIELD', '高度场方块', '轴对齐方块组合，Minecraft 风格'),
            ('BVH_SAH', 'BVH 简化版', '快速二分包围盒，基于最大跨度轴分割（推荐）'),
        ],
        default='BVH_SAH'
    )

    voxel_size: FloatProperty(
        name="体素大小",
        description="高度场模式的体素分辨率（越小越精细，方块越多）",
        min=0.01,
        max=1.0,
        default=0.1,
        step=0.01,
        precision=3,
        unit='LENGTH'
    )

    # === OBB 分解参数 ===

    cube_count: IntProperty(
        name="立方体数量",
        description="目标立方体数量（精确值），指定多少就生成多少",
        min=1,
        max=500,
        default=20,
        step=1
    )

    min_cube_size: FloatProperty(
        name="最小立方体尺寸",
        description="立方体最小边长，确保方块不会过薄",
        min=0.001,
        max=10.0,
        default=0.05,
        step=0.01,
        precision=3,
        unit='LENGTH'
    )

    # === K-Means + PCA 参数 ===

    # === BVH + SAH 参数 ===

    bvh_max_leaf_size: IntProperty(
        name="最大叶子大小",
        description="叶子节点的最大三角形数（增大此值可提高性能）",
        min=1,
        max=200,
        default=50,
        step=5
    )

    bvh_max_depth: IntProperty(
        name="最大深度",
        description="BVH树的最大递归深度（减小此值可提高性能）",
        min=1,
        max=20,
        default=12,
        step=1
    )

    bvh_sah_alpha: FloatProperty(
        name="SAH系数",
        description="SAH成本系数（控制分割激进程度）",
        min=0.1,
        max=10.0,
        default=1.0,
        step=0.1,
        precision=1
    )

    # === 立方体设置 ===

    cube_gap: FloatProperty(
        name="立方体间隙",
        description="立方体之间的间隙比例（0=无间隙，0.5=较大间隙）",
        min=0.0,
        max=0.5,
        default=0.05,
        step=0.01,
        precision=2
    )

    # === 输出设置 ===

    collection_name: StringProperty(
        name="Collection 名称",
        description="生成立方体所放入的 Collection 名称，再次生成时会清空该 Collection",
        default="Blockblend",
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

    # === 材质烘焙设置 ===

    bake_type: EnumProperty(
        name="烘焙类型",
        description="选择要烘焙的贴图类型",
        items=[
            ('DIFFUSE', '漫反射颜色', '烘焙基础颜色和纹理'),
            ('NORMAL', '法线贴图', '烘焙表面法线细节（推荐用于LOD）'),
            ('AO', '环境光遮蔽', '烘焙AO阴影'),
            ('COMBINED', '合成', '烘焙所有通道（颜色+光照+阴影）'),
        ],
        default='DIFFUSE'
    )

    bake_resolution: IntProperty(
        name="烘焙分辨率",
        description="烘焙贴图的分辨率（像素）",
        min=1,
        max=32768,
        default=1024,
        step=1
    )

    bake_samples: IntProperty(
        name="烘焙采样数",
        description="烘焙时的采样数量（AO和合成模式需要较高采样）",
        min=1,
        max=256,
        default=64,
        step=1
    )

    bake_margin: IntProperty(
        name="烘焙边距",
        description="烘焙贴图UV边缘的扩展像素数（防止接缝漏色）",
        min=0,
        max=64,
        default=4,
        step=1
    )

    # === 烘焙对象选择 ===

    bake_source_object: bpy.props.PointerProperty(
        name="源模型 (高模)",
        description="选择要烘焙纹理的源模型（高精度模型）",
        type=bpy.types.Object,
        poll=_is_mesh_object,
    )

    bake_target_object: bpy.props.PointerProperty(
        name="目标模型 (LOD)",
        description="选择烘焙目标模型（低精度/LOD模型，需要UV贴图）",
        type=bpy.types.Object,
        poll=_is_mesh_object,
    )

    # === 统计信息（只读）===

    generated_cube_count: IntProperty(
        name="已生成立方体数量",
        description="转换后创建的立方体数量",
        default=0,
        min=0
    )

    last_cube_count_setting: IntProperty(
        name="上次设置数量",
        description="上次转换时设置的目标数量",
        default=0,
        min=0
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
