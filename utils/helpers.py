"""Helper functions for Blockblend plugin"""

import bpy
import random
from mathutils import Vector


def calculate_voxel_size(obj: bpy.types.Object, detail_level: float = 1.0) -> float:
    """
    根据细节级别计算体素大小

    Args:
        obj: Blender对象
        detail_level: 细节级别（0.1-10.0）

    Returns:
        计算出的体素大小
    """
    if not obj or not obj.bound_box:
        return 0.1

    bbox = obj.bound_box
    max_dimension = max(
        bbox[6][0] - bbox[0][0],  # X轴
        bbox[6][1] - bbox[0][1],  # Y轴
        bbox[6][2] - bbox[0][2]   # Z轴
    )

    # detail_level越大，体素越小（细节越多）
    voxel_size = max_dimension / (20 * detail_level)

    # 确保体素大小在合理范围内
    return max(0.001, min(voxel_size, 10.0))


def validate_mesh_object(obj: bpy.types.Object) -> tuple[bool, str]:
    """
    验证对象是否为有效的网格对象

    Args:
        obj: 要验证的对象

    Returns:
        (是否有效, 错误消息)元组
    """
    if not obj:
        return False, "未选择对象"

    if obj.type != 'MESH':
        return False, f"对象类型为'{obj.type}'，必须是'MESH'类型"

    if not obj.data:
        return False, "对象没有网格数据"

    if len(obj.data.polygons) == 0:
        return False, "网格没有面"

    return True, ""


def get_selected_mesh_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    """
    获取当前选中的所有网格对象

    Args:
        context: Blender上下文

    Returns:
        选中的网格对象列表
    """
    selected_objects = context.selected_objects

    return [
        obj for obj in selected_objects
        if obj.type == 'MESH'
    ]


def count_voxels(obj: bpy.types.Object) -> int:
    """
    计算对象的体素数量估计

    Args:
        obj: Blender对象

    Returns:
        估计的体素数量
    """
    if not obj or not obj.data:
        return 0

    # 使用面数作为粗略估计
    return len(obj.data.polygons)


def get_object_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    """
    获取对象的边界框

    Args:
        obj: Blender对象

    Returns:
        (最小点, 最大点)元组
    """
    if not obj or not obj.bound_box:
        return Vector((0, 0, 0)), Vector((0, 0, 0))

    bbox = obj.bound_box

    min_point = Vector((
        min(p[0] for p in bbox),
        min(p[1] for p in bbox),
        min(p[2] for p in bbox)
    ))

    max_point = Vector((
        max(p[0] for p in bbox),
        max(p[1] for p in bbox),
        max(p[2] for p in bbox)
    ))

    return min_point, max_point


def create_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    """
    创建一个简单的材质

    Args:
        name: 材质名称
        color: RGBA颜色值

    Returns:
        新创建的材质
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    if bsdf:
        bsdf.inputs["Base Color"].default_value = color

    return mat


def apply_material_to_object(obj: bpy.types.Object, mat: bpy.types.Material):
    """
    将材质应用到对象

    Args:
        obj: Blender对象
        mat: 材质
    """
    if obj and obj.data and mat:
        # 清除现有材质
        obj.data.materials.clear()
        # 添加新材质
        obj.data.materials.append(mat)


def set_smooth_shading(obj: bpy.types.Object, smooth: bool = True):
    """
    设置对象的着色模式

    Args:
        obj: Blender对象
        smooth: 是否平滑着色
    """
    if obj and obj.data:
        for poly in obj.data.polygons:
            poly.use_smooth = smooth


def report_error(operator: bpy.types.Operator, message: str):
    """
    向用户报告错误

    Args:
        operator: Blender操作符
        message: 错误消息
    """
    operator.report({'ERROR'}, message)


def report_info(operator: bpy.types.Operator, message: str):
    """
    向用户报告信息

    Args:
        operator: Blender操作符
        message: 信息消息
    """
    operator.report({'INFO'}, message)


def report_warning(operator: bpy.types.Operator, message: str):
    """
    向用户报告警告

    Args:
        operator: Blender操作符
        message: 警告消息
    """
    operator.report({'WARNING'}, message)


def apply_color_to_cube(
    cube: bpy.types.Object,
    center: tuple,
    index: int,
    total: int,
    color_mode: str,
    uniform_color: tuple = (0.5, 0.5, 0.5),
    color_variation: float = 0.3,
    base_color: tuple = (0.8, 0.6, 0.4),
    original_materials: list = None,
    min_z: float = 0.0,
    max_z: float = 1.0,
):
    """
    根据颜色模式为立方体应用颜色或材质

    Args:
        cube: 立方体对象
        center: 中心点坐标 (x, y, z)
        index: 当前索引
        total: 总数
        color_mode: 颜色模式
        uniform_color: 统一颜色RGB
        color_variation: 随机颜色变化范围
        base_color: 随机颜色基础色
        original_materials: 原始材质列表
        min_z: 最小Z值（高度着色用）
        max_z: 最大Z值（高度着色用）
    """
    if original_materials is None:
        original_materials = []

    if color_mode == 'ORIGINAL' and original_materials:
        for mat in original_materials:
            cube.data.materials.append(mat)
        return

    mat = bpy.data.materials.new(name=f"BB_Mat_{cube.name}")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    if not bsdf:
        cube.data.materials.append(mat)
        return

    if color_mode == 'ORIGINAL':
        color = uniform_color
    elif color_mode == 'UNIFORM':
        color = uniform_color
    elif color_mode == 'RANDOM':
        color = (
            max(0.0, min(1.0, base_color[0] + (random.random() - 0.5) * color_variation)),
            max(0.0, min(1.0, base_color[1] + (random.random() - 0.5) * color_variation)),
            max(0.0, min(1.0, base_color[2] + (random.random() - 0.5) * color_variation)),
        )
    elif color_mode == 'HEIGHT':
        t = (center[2] - min_z) / (max_z - min_z) if max_z > min_z else 0.5
        if t < 0.5:
            lt = t * 2
            color = (0.2, 0.2 + lt * 0.6, 0.8 - lt * 0.6)
        else:
            lt = (t - 0.5) * 2
            color = (0.2 + lt * 0.6, 0.8 - lt * 0.2, 0.2 - lt * 0.1)
    elif color_mode == 'POSITION':
        x_factor = (center[0] + 5) / 10
        y_factor = (center[1] + 5) / 10
        z_factor = (center[2] - min_z) / (max_z - min_z) if max_z > min_z else 0.5
        color = (
            max(0.0, min(1.0, x_factor)),
            max(0.0, min(1.0, y_factor)),
            max(0.0, min(1.0, z_factor)),
        )
    else:
        color = uniform_color

    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    cube.data.materials.append(mat)
