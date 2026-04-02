"""Voxel Remesh conversion engine"""

import bpy
import bmesh
import random
from mathutils import Vector
from typing import List, Optional, Tuple
from .base_engine import ConversionEngine


class VoxelRemeshEngine(ConversionEngine):
    """
    Voxel Remesh转换引擎

    使用Blender的Voxel Remesh功能将高模转换为方块风格
    """

    def execute(
        self,
        voxel_size: float = 0.1,
        create_cubes: bool = True,
        cube_size_factor: float = 0.95,
        adaptivity: float = 0.0,
        preserve_materials: bool = True,
        color_mode: str = 'ORIGINAL',
        uniform_color: Tuple[float, float, float] = (0.5, 0.5, 0.5),
        color_variation: float = 0.3,
        base_color: Tuple[float, float, float] = (0.8, 0.6, 0.4),
        smooth_shading: bool = False,
        merge_cubes: bool = False,
        remove_original: bool = False,
        **kwargs
    ) -> bpy.types.Object:
        """
        执行Voxel Remesh转换

        Args:
            voxel_size: 体素大小
            create_cubes: 是否创建独立立方体
            cube_size_factor: 立方体大小系数（避免重叠）
            adaptivity: 适应性（0=均匀，1=自适应）
            preserve_materials: 是否保留材质
            color_mode: 颜色模式 ('ORIGINAL', 'UNIFORM', 'RANDOM', 'HEIGHT', 'POSITION')
            uniform_color: 统一颜色RGB值
            color_variation: 随机颜色变化范围
            base_color: 随机颜色的基础色
            smooth_shading: 是否应用平滑着色
            merge_cubes: 是否合并立方体为单一网格
            remove_original: 是否删除原始对象
            **kwargs: 其他参数

        Returns:
            转换后的对象或第一个立方体对象

        Raises:
            ValueError: 如果对象无效或参数错误
            RuntimeError: 如果转换失败
        """
        if not self.validate_object():
            raise ValueError("对象必须是网格类型")

        # 验证参数
        if voxel_size <= 0:
            raise ValueError("体素大小必须大于0")

        if cube_size_factor <= 0 or cube_size_factor > 1.0:
            raise ValueError("立方体大小系数必须在(0, 1.0]范围内")

        # 1. 应用Voxel Remesh修饰器
        self._apply_voxel_remesh(voxel_size, adaptivity)

        # 2. 根据选项处理结果
        if create_cubes:
            result = self._create_independent_cubes(
                cube_size_factor=cube_size_factor,
                preserve_materials=preserve_materials,
                color_mode=color_mode,
                uniform_color=uniform_color,
                color_variation=color_variation,
                base_color=base_color,
                smooth_shading=smooth_shading,
                merge_cubes=merge_cubes
            )

            # 如果需要，删除原始对象
            if remove_original:
                self._remove_original_object()
        else:
            # 不创建独立立方体，只应用remesh
            result = self.obj
            if not smooth_shading:
                self._apply_flat_shading()

        return result

    def _apply_voxel_remesh(self, voxel_size: float, adaptivity: float):
        """
        应用Voxel Remesh修饰器

        Args:
            voxel_size: 体素大小
            adaptivity: 适应性参数
        """
        # 确保在正确的上下文中
        bpy.context.view_layer.objects.active = self.obj

        # 添加Remesh修饰器
        modifier = self.obj.modifiers.new(name="Blockblend_Voxel", type='REMESH')

        # 设置参数
        modifier.mode = 'VOXEL'
        modifier.voxel_size = voxel_size
        modifier.adaptivity = adaptivity

        # 应用修饰器
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except Exception as e:
            raise RuntimeError(f"应用Voxel Remesh失败: {str(e)}")

    def _create_independent_cubes(
        self,
        cube_size_factor: float,
        preserve_materials: bool,
        color_mode: str,
        uniform_color: Tuple[float, float, float],
        color_variation: float,
        base_color: Tuple[float, float, float],
        smooth_shading: bool,
        merge_cubes: bool
    ) -> bpy.types.Object:
        """
        从体素网格创建独立立方体

        Args:
            cube_size_factor: 立方体大小系数
            preserve_materials: 是否保留材质
            color_mode: 颜色模式
            uniform_color: 统一颜色
            color_variation: 颜色变化
            base_color: 基础颜色
            smooth_shading: 平滑着色
            merge_cubes: 是否合并立方体

        Returns:
            第一个立方体对象或合并后的对象
        """
        # 提取体素中心点
        voxel_centers = self._extract_voxel_centers()

        if not voxel_centers:
            raise RuntimeError("无法提取体素中心点")

        # 获取原始材质
        original_materials = self.obj.data.materials if preserve_materials else []

        # 计算立方体大小
        cube_size = self._get_effective_voxel_size() * cube_size_factor

        # 获取对象边界框用于颜色计算
        obj_bbox = self.obj.bound_box
        min_z = min(p[2] for p in obj_bbox)
        max_z = max(p[2] for p in obj_bbox)

        # 创建立方体
        cube_objects = []

        for i, center in enumerate(voxel_centers):
            # 创建立方体
            cube = self._create_cube_at(center, cube_size)

            # 应用着色
            if not smooth_shading:
                self._apply_flat_shading_to_object(cube)

            # 应用颜色/材质
            self._apply_color_to_cube(
                cube,
                center,
                i,
                len(voxel_centers),
                color_mode,
                uniform_color,
                color_variation,
                base_color,
                original_materials,
                min_z,
                max_z
            )

            cube_objects.append(cube)

        # 如果需要合并
        if merge_cubes and len(cube_objects) > 1:
            return self._merge_cubes(cube_objects)

        # 选择所有新创建的立方体
        if cube_objects:
            self._select_objects(cube_objects)

        return cube_objects[0] if cube_objects else self.obj

    def _extract_voxel_centers(self) -> List[Vector]:
        """
        提取体素网格的中心点

        Returns:
            体素中心点列表（世界坐标）
        """
        # 将网格转换为BMesh
        bm = bmesh.new()
        bm.from_mesh(self.obj.data)

        # 应用世界变换矩阵
        bmesh.ops.transform(bm, matrix=self.obj.matrix_world, verts=bm.verts)

        # 提取面的中心点
        centers = []
        for face in bm.faces:
            center = face.calc_center_median()
            centers.append(center)

        # 清理
        bm.free()

        return centers

    def _create_cube_at(self, location: Vector, size: float) -> bpy.types.Object:
        """
        在指定位置创建立方体

        Args:
            location: 位置（世界坐标）
            size: 大小

        Returns:
            新创建的立方体对象
        """
        # 创建立方体
        bpy.ops.mesh.primitive_cube_add(
            location=location,
            size=size,
            rotation=(0, 0, 0)
        )

        cube = bpy.context.active_object

        # 命名
        cube.name = f"Blockblend_Cube_{len(bpy.data.objects)}"

        return cube

    def _apply_color_to_cube(
        self,
        cube: bpy.types.Object,
        center: Vector,
        index: int,
        total: int,
        color_mode: str,
        uniform_color: Tuple[float, float, float],
        color_variation: float,
        base_color: Tuple[float, float, float],
        original_materials: List,
        min_z: float,
        max_z: float
    ):
        """
        应用颜色或材质到立方体

        Args:
            cube: 立方体对象
            center: 中心点
            index: 当前索引
            total: 总数
            color_mode: 颜色模式
            uniform_color: 统一颜色
            color_variation: 颜色变化
            base_color: 基础颜色
            original_materials: 原始材质列表
            min_z: 最小Z值
            max_z: 最大Z值
        """
        if color_mode == 'ORIGINAL' and original_materials:
            # 使用原始材质
            for mat in original_materials:
                cube.data.materials.append(mat)

        else:
            # 创建新材质
            mat = bpy.data.materials.new(name=f"Blockblend_Mat_{cube.name}")
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            bsdf = nodes.get("Principled BSDF")

            if bsdf:
                # 根据模式计算颜色
                if color_mode == 'ORIGINAL':
                    color = uniform_color  # 回退到统一颜色
                elif color_mode == 'UNIFORM':
                    color = uniform_color
                elif color_mode == 'RANDOM':
                    color = self._get_random_color(base_color, color_variation)
                elif color_mode == 'HEIGHT':
                    t = (center[2] - min_z) / (max_z - min_z) if max_z > min_z else 0.5
                    color = self._get_height_gradient_color(t)
                elif color_mode == 'POSITION':
                    color = self._get_position_color(center, (min_z, max_z))
                else:
                    color = uniform_color

                bsdf.inputs["Base Color"].default_value = (
                    color[0], color[1], color[2], 1.0
                )

            # 应用材质
            cube.data.materials.append(mat)

    def _get_random_color(
        self,
        base_color: Tuple[float, float, float],
        variation: float
    ) -> Tuple[float, float, float]:
        """
        生成随机颜色

        Args:
            base_color: 基础颜色
            variation: 变化范围

        Returns:
            随机颜色RGB值
        """
        return (
            max(0.0, min(1.0, base_color[0] + (random.random() - 0.5) * variation)),
            max(0.0, min(1.0, base_color[1] + (random.random() - 0.5) * variation)),
            max(0.0, min(1.0, base_color[2] + (random.random() - 0.5) * variation))
        )

    def _get_height_gradient_color(self, t: float) -> Tuple[float, float, float]:
        """
        获取高度渐变颜色

        Args:
            t: 归一化高度值(0-1)

        Returns:
            颜色RGB值
        """
        # 从蓝色(底部)到绿色(中部)到棕色(顶部)
        if t < 0.5:
            # 蓝色到绿色
            local_t = t * 2
            return (0.2, 0.2 + local_t * 0.6, 0.8 - local_t * 0.6)
        else:
            # 绿色到棕色
            local_t = (t - 0.5) * 2
            return (0.2 + local_t * 0.6, 0.8 - local_t * 0.2, 0.2 - local_t * 0.1)

    def _get_position_color(
        self,
        center: Vector,
        z_range: Tuple[float, float]
    ) -> Tuple[float, float, float]:
        """
        根据位置获取颜色

        Args:
            center: 中心点
            z_range: Z值范围

        Returns:
            颜色RGB值
        """
        # 基于XYZ坐标生成颜色
        x_factor = (center[0] + 5) / 10  # 假设范围约-5到5
        y_factor = (center[1] + 5) / 10
        z_factor = (center[2] - z_range[0]) / (z_range[1] - z_range[0]) if z_range[1] > z_range[0] else 0.5

        return (
            max(0.0, min(1.0, x_factor)),
            max(0.0, min(1.0, y_factor)),
            max(0.0, min(1.0, z_factor))
        )

    def _apply_flat_shading_to_object(self, obj: bpy.types.Object):
        """
        对对象应用平坦着色

        Args:
            obj: Blender对象
        """
        if obj.data:
            for poly in obj.data.polygons:
                poly.use_smooth = False

    def _apply_flat_shading(self):
        """对当前对象应用平坦着色"""
        self._apply_flat_shading_to_object(self.obj)

    def _get_effective_voxel_size(self) -> float:
        """
        获取有效的体素大小

        Returns:
            体素大小
        """
        # 尝试从修饰器获取
        for modifier in self.obj.modifiers:
            if modifier.type == 'REMESH' and modifier.mode == 'VOXEL':
                return modifier.voxel_size

        # 从边界框计算
        bbox = self.obj.bound_box
        avg_size = (
            (bbox[6][0] - bbox[0][0]) +
            (bbox[6][1] - bbox[0][1]) +
            (bbox[6][2] - bbox[0][2])
        ) / 3

        return avg_size / 20

    def _merge_cubes(self, cubes: List[bpy.types.Object]) -> bpy.types.Object:
        """
        合并多个立方体为单一网格

        Args:
            cubes: 要合并的立方体列表

        Returns:
            合并后的对象
        """
        if not cubes:
            return self.obj

        # 选择所有立方体
        self._select_objects(cubes)

        # 执行合并操作
        bpy.ops.object.join()

        # 重命名
        merged = bpy.context.active_object
        if merged:
            merged.name = "Blockblend_Merged"

        return merged

    def _select_objects(self, objects: List[bpy.types.Object]):
        """
        选择多个对象

        Args:
            objects: 要选择的对象列表
        """
        # 取消选择所有对象
        bpy.ops.object.select_all(action='DESELECT')

        # 选择指定对象
        for obj in objects:
            if obj:
                obj.select_set(True)

        # 设置活动对象
        if objects:
            bpy.context.view_layer.objects.active = objects[0]

    def _remove_original_object(self):
        """删除原始对象"""
        if self.obj:
            # 取消选择
            self.obj.select_set(False)

            # 删除对象
            bpy.data.objects.remove(self.obj, do_unlink=True)
            self.obj = None
