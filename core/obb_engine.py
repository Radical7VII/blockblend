"""OBB (Oriented Bounding Box) decomposition engine

Uses top-down hierarchical binary splitting (BVH-style) to decompose
a mesh into exactly N oriented cubes, splitting largest volumes first.
"""

import bpy
import bmesh
import heapq
import numpy as np
from mathutils import Vector, Matrix
from typing import List, Tuple, Dict, Optional
from .base_engine import ConversionEngine


class OBB:
    """一个有向包围盒的结果数据"""

    __slots__ = ('center', 'axes', 'half_extents', 'face_indices')

    def __init__(
        self,
        center: np.ndarray,
        axes: np.ndarray,
        half_extents: np.ndarray,
        face_indices: List[int],
    ):
        self.center = center          # shape (3,) 世界坐标中心
        self.axes = axes              # shape (3,3) 列=正交基向量
        self.half_extents = half_extents  # shape (3,) 各轴半长
        self.face_indices = face_indices


class OBBEngine(ConversionEngine):
    """
    OBB 分解引擎（层次化二分拆分）

    从 1 个覆盖整 mesh 的大 OBB 开始，每次拆分体积最大的 OBB，
    拆 N-1 次得到恰好 N 个 OBB。天然具有"从大到小"的层次化优先级。
    """

    def execute(
        self,
        cube_count: int = 20,
        min_cube_size: float = 0.05,
        cube_gap: float = 0.05,
        collection_name: str = "Blockblend",
        **kwargs,
    ) -> List[bpy.types.Object]:
        """
        执行 OBB 分解

        Args:
            cube_count: 目标立方体数量（精确值）
            min_cube_size: 最小立方体边长约束
            cube_gap: 立方体间隙比例 (0-0.5)
            collection_name: 输出 Collection 名称

        Returns:
            创建的立方体对象列表
        """
        if not self.validate_object():
            raise ValueError("对象必须是网格类型")

        # 1. 提取网格数据
        vertices, face_verts, face_normals = self._extract_mesh_data()
        face_count = len(face_verts)

        if face_count == 0:
            raise RuntimeError("网格没有面")

        # 2. 预计算所有面的中心点
        face_centers = vertices[face_verts].mean(axis=1)

        # 3. 对整个 mesh 拟合初始 OBB
        all_indices = list(range(face_count))
        root_obb = self._fit_obb_for_faces(all_indices, vertices, face_verts)

        if root_obb is None:
            raise RuntimeError("无法生成初始包围盒")

        # 4. 层次化二分拆分
        obbs = self._hierarchical_split(
            root_obb, cube_count, vertices, face_verts, face_centers
        )

        if not obbs:
            raise RuntimeError("无法生成任何包围盒")

        # 5. 膨胀薄轴（不合并，保持数量不变）
        obbs = self._inflate_thin_axes(obbs, min_cube_size)

        # 6. 获取/创建 Collection
        collection = self._get_or_create_collection(collection_name)

        # 7. 生成立方体
        cube_objects = []
        for i, obb in enumerate(obbs):
            cube = self._create_cube_from_obb(
                obb, cube_gap, collection, i
            )
            if cube:
                cube_objects.append(cube)

        return cube_objects

    # ─── 数据提取 ────────────────────────────────────

    def _extract_mesh_data(
        self,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        提取世界坐标下的网格数据（支持修饰器求值）

        Returns:
            vertices: (V, 3) 世界坐标顶点
            face_verts: (F, 3) 三角面索引
            face_normals: (F, 3) 世界坐标面法线
        """
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = self.obj.evaluated_get(depsgraph)

        bm = bmesh.new()
        bm.from_object(obj_eval, depsgraph)
        bmesh.ops.triangulate(bm, faces=bm.faces)

        # 应用世界变换
        bmesh.ops.transform(bm, matrix=self.obj.matrix_world, verts=bm.verts)

        num_verts = len(bm.verts)
        num_faces = len(bm.faces)

        vertices = np.empty((num_verts, 3), dtype=np.float64)
        for i, v in enumerate(bm.verts):
            vertices[i] = v.co

        face_verts = np.empty((num_faces, 3), dtype=np.int32)
        face_normals = np.empty((num_faces, 3), dtype=np.float64)
        for i, f in enumerate(bm.faces):
            verts = f.verts
            face_verts[i] = [verts[0].index, verts[1].index, verts[2].index]
            face_normals[i] = f.normal.normalized()

        bm.free()
        return vertices, face_verts, face_normals

    # ─── PCA 拟合 OBB ────────────────────────────────

    def _pca_obb(
        self, vertices: np.ndarray, face_indices: List[int]
    ) -> Optional[OBB]:
        """
        用 PCA 为一组顶点拟合有向包围盒

        Args:
            vertices: (N, 3) 顶点坐标
            face_indices: 对应的面索引

        Returns:
            OBB 实例，或 None（顶点不足时）
        """
        if len(vertices) < 3:
            return None

        center = vertices.mean(axis=0)
        centered = vertices - center

        # 协方差矩阵
        cov = (centered.T @ centered) / len(vertices)

        try:
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
        except np.linalg.LinAlgError:
            return None

        # 确保右手坐标系
        if np.linalg.det(eigenvectors) < 0:
            eigenvectors[:, -1] *= -1

        # 投影到主轴，计算半长
        projections = centered @ eigenvectors
        proj_min = projections.min(axis=0)
        proj_max = projections.max(axis=0)

        half_extents = (proj_max - proj_min) / 2.0

        # 修正中心（PCA 中心可能与质心不同）
        center = center + eigenvectors @ ((proj_max + proj_min) / 2.0)

        return OBB(
            center=center,
            axes=eigenvectors,
            half_extents=half_extents,
            face_indices=face_indices,
        )

    # ─── 层次化二分拆分 ──────────────────────────────

    def _hierarchical_split(
        self,
        root_obb: OBB,
        target_count: int,
        vertices: np.ndarray,
        face_verts: np.ndarray,
        face_centers: np.ndarray,
    ) -> List[OBB]:
        """
        层次化二分拆分

        用最大堆（按 OBB 体积排序）驱动，每次拆分体积最大的 OBB，
        执行 target_count - 1 次拆分后恰好得到 target_count 个 OBB。

        Args:
            root_obb: 覆盖整个 mesh 的初始 OBB
            target_count: 目标 OBB 数量
            vertices: 全部顶点坐标
            face_verts: 面顶点索引
            face_centers: 预计算的面中心点

        Returns:
            OBB 列表
        """
        if target_count <= 1:
            return [root_obb]

        # 最大堆：存 (-volume, counter, obb)
        # counter 用于打破体积相同时的比较
        counter = 0
        heap = []
        vol = float(np.prod(root_obb.half_extents))
        heapq.heappush(heap, (-vol, counter, root_obb))
        counter += 1

        splits_done = 0
        max_splits = target_count - 1

        # 保存无法继续拆分的 OBB
        unsplittable = []

        while splits_done < max_splits and heap:
            neg_vol, _, obb = heapq.heappop(heap)

            # 面数不足，无法继续拆分
            if len(obb.face_indices) < 2:
                unsplittable.append(obb)
                continue

            # 尝试沿最优轴拆分
            result = self._split_obb(
                obb, vertices, face_verts, face_centers
            )

            if result is None:
                # 拆分失败（如所有面投影到同一点）
                unsplittable.append(obb)
                continue

            obb_a, obb_b = result
            vol_a = float(np.prod(obb_a.half_extents))
            vol_b = float(np.prod(obb_b.half_extents))
            heapq.heappush(heap, (-vol_a, counter, obb_a))
            counter += 1
            heapq.heappush(heap, (-vol_b, counter, obb_b))
            counter += 1
            splits_done += 1

        # 收集堆中剩余 + 无法拆分的 OBB
        result = unsplittable + [entry[2] for entry in heap]
        return result

    def _split_obb(
        self,
        obb: OBB,
        vertices: np.ndarray,
        face_verts: np.ndarray,
        face_centers: np.ndarray,
    ) -> Optional[Tuple[OBB, OBB]]:
        """
        将一个 OBB 沿最优 PCA 轴一分为二

        尝试 3 个 PCA 轴，选取拆分后总容量最小的方案

        Returns:
            (obb_a, obb_b) 成功时，或 None 拆分失败时
        """
        face_indices = obb.face_indices

        if len(face_indices) < 2:
            return None

        # 提取这些面的中心点
        centers = face_centers[face_indices]

        best_result = None
        best_total_volume = float('inf')

        for axis_idx in range(3):
            axis = obb.axes[:, axis_idx]

            # 投影面中心到该轴
            projections = centers @ axis

            # 按投影值排序，在中位数处切割
            sorted_order = np.argsort(projections)
            mid = len(sorted_order) // 2

            if mid == 0:
                continue  # 所有面投影到同一点

            group_a = [face_indices[i] for i in sorted_order[:mid]]
            group_b = [face_indices[i] for i in sorted_order[mid:]]

            # PCA 拟合每组
            obb_a = self._fit_obb_for_faces(group_a, vertices, face_verts)
            obb_b = self._fit_obb_for_faces(group_b, vertices, face_verts)

            if obb_a is None or obb_b is None:
                continue

            total_vol = float(
                np.prod(obb_a.half_extents) + np.prod(obb_b.half_extents)
            )

            if total_vol < best_total_volume:
                best_total_volume = total_vol
                best_result = (obb_a, obb_b)

        return best_result

    def _fit_obb_for_faces(
        self,
        face_indices: List[int],
        vertices: np.ndarray,
        face_verts: np.ndarray,
    ) -> Optional[OBB]:
        """
        为一组面索引拟合 OBB

        Args:
            face_indices: 面索引列表
            vertices: 全部顶点坐标 (V, 3)
            face_verts: 面顶点索引 (F, 3)

        Returns:
            OBB 实例或 None
        """
        if not face_indices:
            return None

        unique_vert_indices = np.unique(face_verts[face_indices].ravel())
        cluster_verts = vertices[unique_vert_indices]
        return self._pca_obb(cluster_verts, face_indices)

    # ─── 薄轴膨胀 ──────────────────────────────────

    def _inflate_thin_axes(
        self, obbs: List[OBB], min_cube_size: float
    ) -> List[OBB]:
        """
        膨胀过薄的轴向至最小尺寸（不合并，保持数量不变）
        """
        min_half = min_cube_size / 2.0
        for obb in obbs:
            for i in range(3):
                if obb.half_extents[i] < min_half:
                    obb.half_extents[i] = min_half
        return obbs

    # ─── Collection 管理 ─────────────────────────────

    def _get_or_create_collection(self, coll_name: str) -> bpy.types.Collection:
        """
        获取或创建输出 Collection

        再次生成时清空重建
        """

        if coll_name in bpy.data.collections:
            coll = bpy.data.collections[coll_name]
            # 清空已有对象
            for obj in list(coll.objects):
                mesh = obj.data
                coll.objects.unlink(obj)
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh, do_unlink=True)
                # 清理自动生成的材质
                for mat in bpy.data.materials:
                    if mat.name.startswith("BB_Mat_") and mat.users == 0:
                        bpy.data.materials.remove(mat, do_unlink=True)
        else:
            coll = bpy.data.collections.new(coll_name)
            bpy.context.scene.collection.children.link(coll)

        return coll

    # ─── 生成立方体 ──────────────────────────────────

    def _create_cube_from_obb(
        self,
        obb: OBB,
        cube_gap: float,
        collection: bpy.types.Collection,
        index: int,
    ) -> Optional[bpy.types.Object]:
        """
        从 OBB 创建 Blender 立方体对象

        Args:
            obb: 有向包围盒数据
            cube_gap: 间隙比例
            collection: 目标 Collection
            index: 序号

        Returns:
            创建的立方体对象
        """
        # 计算缩放（考虑间隙）
        gap_factor = 1.0 - cube_gap
        full_extents = obb.half_extents * 2.0 * gap_factor

        # 从 OBB 轴构建旋转矩阵
        # axes 的列是 OBB 的基向量 → 需要转置为 Blender 的行主序
        rot_matrix = Matrix(obb.axes.T.tolist())

        # 创建立方体
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(0, 0, 0),
        )
        cube = bpy.context.active_object
        cube.name = f"BB_Cube_{index:04d}"

        # 设置变换
        cube.location = Vector(obb.center.tolist())
        cube.rotation_euler = rot_matrix.to_euler()
        cube.scale = Vector(full_extents.tolist())

        # 应用旋转和缩放（让用户看到正确的尺寸）
        bpy.ops.object.select_all(action='DESELECT')
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        bpy.ops.object.transform_apply(
            location=False, rotation=True, scale=True
        )

        # 移动到目标 Collection
        for coll in cube.users_collection:
            coll.objects.unlink(cube)
        collection.objects.link(cube)

        return cube
