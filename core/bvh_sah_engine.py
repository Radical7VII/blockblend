"""BVH + SAH 引擎（简化版）

使用简化的表面面积启发式构建包围盒层次结构。
为了避免性能问题，使用中位数分割而不是遍历所有分割点。

算法管线：
1. 计算每个三角形的包围盒和中心
2. 使用 SAH 启发式选择分割轴
3. 沿中位数分割递归构建
4. 叶子节点输出为立方体
"""

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
from typing import List, Tuple, Optional
from .base_engine import ConversionEngine


class BVHSAHEngine(ConversionEngine):
    """
    BVH + SAH 引擎（简化版）

    使用简化的 SAH 策略，避免复杂的遍历。
    """

    def execute(
        self,
        max_leaf_size: int = 20,
        max_depth: int = 15,
        sah_alpha: float = 1.0,
        cube_gap: float = 0.05,
        collection_name: str = "Blockblend",
        **kwargs,
    ) -> List[bpy.types.Object]:
        """
        执行 BVH + SAH 分解

        Args:
            max_leaf_size: 叶子节点最大三角形数
            max_depth: 最大递归深度
            sah_alpha: SAH 成本系数
            cube_gap: 方块间隙比例 (0-0.5)
            collection_name: 输出 Collection 名称

        Returns:
            创建的立方体对象列表
        """
        if not self.validate_object():
            raise ValueError("对象必须是网格类型")

        # 提取三角形数据
        tris, bounds, centers = self._extract_triangles()

        # 递归构建 BVH
        leaves = self._build_bvh(
            tris, bounds, centers,
            max_leaf_size=max_leaf_size,
            max_depth=max_depth,
            sah_alpha=sah_alpha,
            depth=0
        )

        if not leaves:
            raise RuntimeError("无法生成任何方块")

        # 创建 Collection
        collection = self._get_or_create_collection(collection_name)

        # 为每个叶子创建立方体
        cube_objects = []
        for i, leaf in enumerate(leaves):
            cube = self._create_cube_from_bounds(
                leaf['bounds'], cube_gap, collection, i
            )
            if cube:
                cube_objects.append(cube)

        return cube_objects

    def _extract_triangles(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        提取三角形数据

        Returns:
            tris: (N, 3, 3) 三角形顶点坐标
            bounds: (N, 2, 3) 每个三角形的包围盒 [min, max]
            centers: (N, 3) 每个三角形的中心
        """
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = self.obj.evaluated_get(depsgraph)

        bm = bmesh.new()
        bm.from_object(obj_eval, depsgraph)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bmesh.ops.transform(bm, matrix=self.obj.matrix_world, verts=bm.verts)

        # 提取三角形
        tris = []
        for face in bm.faces:
            tri_verts = [v.co for v in face.verts]
            tris.append(tri_verts)

        bm.free()

        tris = np.array(tris, dtype=np.float64)

        # 计算每个三角形的包围盒和中心
        bounds = np.stack([tris.min(axis=1), tris.max(axis=1)], axis=1)
        centers = tris.mean(axis=1)

        return tris, bounds, centers

    def _build_bvh(
        self,
        tris: np.ndarray,
        bounds: np.ndarray,
        centers: np.ndarray,
        max_leaf_size: int,
        max_depth: int,
        sah_alpha: float,
        depth: int,
    ) -> List[dict]:
        """
        递归构建 BVH（简化版）

        Returns:
            叶子节点列表
        """
        n_tris = len(tris)

        # 收敛条件
        if n_tris <= max_leaf_size or depth >= max_depth:
            return [{'bounds': self._compute_bounds(bounds)}]

        # 计算当前节点的包围盒
        node_bounds = self._compute_bounds(bounds)
        node_size = node_bounds[1] - node_bounds[0]

        # 选择分割轴（使用简化的 SAH：选择跨度最大的轴）
        split_axis = np.argmax(node_size)

        # 按中心点在分割轴排序
        sorted_indices = np.argsort(centers[:, split_axis])

        # 使用中位数分割（避免尝试多个分割点）
        median_idx = n_tris // 2
        left_indices = sorted_indices[:median_idx]
        right_indices = sorted_indices[median_idx:]

        # 确保两边都有三角形
        if len(left_indices) == 0 or len(right_indices) == 0:
            return [{'bounds': node_bounds}]

        # 递归构建子树（传递子数组而不是索引）
        leaves = []
        leaves.extend(self._build_bvh(
            tris[left_indices], bounds[left_indices], centers[left_indices],
            max_leaf_size, max_depth, sah_alpha, depth + 1
        ))
        leaves.extend(self._build_bvh(
            tris[right_indices], bounds[right_indices], centers[right_indices],
            max_leaf_size, max_depth, sah_alpha, depth + 1
        ))

        return leaves

    def _compute_bounds(self, bounds: np.ndarray) -> np.ndarray:
        """
        计算一组包围盒的联合包围盒

        Args:
            bounds: (N, 2, 3) 包围盒数组

        Returns:
            (2, 3) 联合包围盒 [min, max]
        """
        return np.stack([
            bounds[:, 0, :].min(axis=0),
            bounds[:, 1, :].max(axis=0)
        ], axis=0)

    def _create_cube_from_bounds(
        self,
        bounds: np.ndarray,
        cube_gap: float,
        collection: bpy.types.Collection,
        index: int,
    ) -> Optional[bpy.types.Object]:
        """从包围盒创建立方体"""
        # 计算中心
        center = (bounds[0] + bounds[1]) / 2

        # 计算尺寸
        size = bounds[1] - bounds[0]

        # 应用间隙
        gap_factor = 1.0 - cube_gap
        actual_size = size * gap_factor

        # 创建立方体
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        cube = bpy.context.active_object
        cube.name = f"BB_Cube_{index:04d}"

        # 设置缩放
        cube.scale = (actual_size[0], actual_size[1], actual_size[2])

        # 设置位置
        cube.location = center

        # 应用变换
        bpy.ops.object.select_all(action='DESELECT')
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        bpy.ops.object.transform_apply(
            location=False, rotation=False, scale=True
        )

        # 移动到 Collection
        for coll in cube.users_collection:
            coll.objects.unlink(cube)
        collection.objects.link(cube)

        return cube

    def _get_or_create_collection(self, coll_name: str) -> bpy.types.Collection:
        """获取或创建 Collection"""
        obj_name = self.obj.name
        full_name = f"{coll_name}_{obj_name}"

        if full_name in bpy.data.collections:
            coll = bpy.data.collections[full_name]
            for obj in list(coll.objects):
                mesh = obj.data
                coll.objects.unlink(obj)
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh, do_unlink=True)
        else:
            coll = bpy.data.collections.new(full_name)
            bpy.context.scene.collection.children.link(coll)

        return coll
