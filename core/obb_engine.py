"""OBB (Oriented Bounding Box) decomposition engine

Uses face-normal clustering + PCA to approximate a mesh
with a set of oriented cubes.
"""

import bpy
import bmesh
import math
import numpy as np
from collections import deque
from mathutils import Vector, Matrix
from typing import List, Tuple, Dict, Set, Optional
from .base_engine import ConversionEngine
from ..utils.helpers import apply_color_to_cube


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
    OBB 分解引擎

    通过面法线聚类 + PCA 拟合，用多个可旋转的立方体
    来概括源模型的体积和形状。不修改源模型。
    """

    def execute(
        self,
        cube_count: int = 20,
        min_cube_size: float = 0.05,
        cube_gap: float = 0.05,
        color_mode: str = 'ORIGINAL',
        uniform_color: Tuple[float, float, float] = (0.5, 0.5, 0.5),
        base_color: Tuple[float, float, float] = (0.8, 0.6, 0.4),
        color_variation: float = 0.3,
        **kwargs,
    ) -> List[bpy.types.Object]:
        """
        执行 OBB 分解

        Args:
            cube_count: 目标立方体数量（近似值）
            min_cube_size: 最小立方体边长约束
            cube_gap: 立方体间隙比例 (0-0.5)
            color_mode: 颜色模式
            uniform_color: 统一颜色
            base_color: 随机颜色基础色
            color_variation: 随机颜色变化范围

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

        # 2. 构建邻接图
        adjacency = self._build_adjacency_graph(face_verts)

        # 3. 面太少时直接用一整个包围盒
        if face_count <= max(cube_count, 3):
            all_indices = list(range(face_count))
            unique_verts = vertices[np.unique(face_verts[all_indices].ravel())]
            obb = self._pca_obb(unique_verts, all_indices)
            obbs = [obb] if obb else []
        else:
            # 4. 通过二分搜索找到合适的法线阈值
            threshold = self._find_threshold_for_count(
                face_normals, adjacency, cube_count, face_count
            )

            # 5. 聚类
            clusters = self._cluster_faces(
                face_normals, adjacency, threshold, vertices, face_verts
            )

            # 6. PCA 拟合每个簇
            obbs = []
            for cluster in clusters:
                unique_vert_indices = np.unique(
                    face_verts[cluster].ravel()
                )
                cluster_verts = vertices[unique_vert_indices]
                obb = self._pca_obb(cluster_verts, cluster)
                if obb:
                    obbs.append(obb)

        # 7. 尺寸约束
        obbs = self._enforce_size_constraints(obbs, min_cube_size)

        if not obbs:
            raise RuntimeError("无法生成任何包围盒")

        # 8. 获取/创建 Collection
        collection = self._get_or_create_collection()

        # 9. 获取源模型的边界框（用于颜色计算）
        obj_bbox = self.obj.bound_box
        min_z = min(p[2] for p in obj_bbox)
        max_z = max(p[2] for p in obj_bbox)
        original_materials = list(self.obj.data.materials)

        # 10. 生成立方体
        cube_objects = []
        for i, obb in enumerate(obbs):
            cube = self._create_cube_from_obb(
                obb, cube_gap, collection, i
            )
            if not cube:
                continue

            # 应用颜色
            center_tuple = tuple(obb.center)
            apply_color_to_cube(
                cube, center_tuple, i, len(obbs), color_mode,
                uniform_color, color_variation, base_color,
                original_materials, min_z, max_z,
            )

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

    # ─── 邻接图 ──────────────────────────────────────

    def _build_adjacency_graph(
        self, face_verts: np.ndarray
    ) -> Dict[int, Set[int]]:
        """
        构建面邻接图（共享边 = 相邻）

        Returns:
            {face_index: {neighbor_indices}}
        """
        edge_to_faces: Dict[frozenset, List[int]] = {}

        for fi in range(len(face_verts)):
            v0, v1, v2 = face_verts[fi]
            for edge in ((v0, v1), (v1, v2), (v2, v0)):
                key = frozenset((edge[0], edge[1]))
                edge_to_faces.setdefault(key, []).append(fi)

        adjacency: Dict[int, Set[int]] = {
            i: set() for i in range(len(face_verts))
        }
        for faces_list in edge_to_faces.values():
            if len(faces_list) == 2:
                a, b = faces_list
                adjacency[a].add(b)
                adjacency[b].add(a)
            elif len(faces_list) > 2:
                # 非流形边：所有共享的面互为邻居
                for i in range(len(faces_list)):
                    for j in range(i + 1, len(faces_list)):
                        adjacency[faces_list[i]].add(faces_list[j])
                        adjacency[faces_list[j]].add(faces_list[i])

        return adjacency

    # ─── 阈值搜索 ────────────────────────────────────

    def _find_threshold_for_count(
        self,
        face_normals: np.ndarray,
        adjacency: Dict[int, Set[int]],
        target_count: int,
        face_count: int,
    ) -> float:
        """
        通过二分搜索找到产生约 target_count 个簇的法线角度阈值

        Returns:
            法线角度阈值（弧度）
        """
        low = 5.0    # 度
        high = 80.0  # 度

        # 预计算法线点积矩阵的近似（用于加速）
        for _ in range(8):
            mid = (low + high) / 2.0
            clusters = self._cluster_faces(
                face_normals, adjacency, math.radians(mid),
                None, None, skip_spatial=True,
            )
            if len(clusters) > target_count:
                low = mid   # 簇太多 → 提高阈值来合并更多面
            else:
                high = mid  # 簇太少 → 降低阈值来产生更多簇

        return math.radians((low + high) / 2.0)

    # ─── 聚类 ────────────────────────────────────────

    def _cluster_faces(
        self,
        face_normals: np.ndarray,
        adjacency: Dict[int, Set[int]],
        threshold: float,
        vertices: np.ndarray = None,
        face_verts: np.ndarray = None,
        skip_spatial: bool = False,
    ) -> List[List[int]]:
        """
        BFS 区域生长聚类

        Args:
            face_normals: (F, 3) 面法线
            adjacency: 面邻接图
            threshold: 法线角度阈值（弧度）
            vertices: 顶点坐标（用于空间距离检查）
            face_verts: 面索引（用于空间距离检查）
            skip_spatial: 跳过空间距离检查（阈值搜索时用）

        Returns:
            簇列表，每簇为面索引列表
        """
        face_count = len(face_normals)
        assigned = set()
        clusters = []

        # 预计算模型对角线长度（用于空间距离检查）
        spatial_limit = float('inf')
        if vertices is not None and not skip_spatial:
            bbox_min = vertices.min(axis=0)
            bbox_max = vertices.max(axis=0)
            diagonal = np.linalg.norm(bbox_max - bbox_min)
            spatial_limit = diagonal * 0.5

        for seed in range(face_count):
            if seed in assigned:
                continue

            cluster = []
            queue = deque([seed])
            seed_normal = face_normals[seed]

            # 簇的质心（用于空间检查）
            cluster_center = np.zeros(3)
            cluster_count = 0

            while queue:
                fi = queue.popleft()
                if fi in assigned:
                    continue

                # 法线角度检查
                dot = np.clip(
                    np.dot(seed_normal, face_normals[fi]), -1.0, 1.0
                )
                angle = math.acos(dot)

                if angle >= threshold:
                    continue

                # 空间距离检查
                if not skip_spatial and face_verts is not None:
                    face_center = vertices[face_verts[fi]].mean(axis=0)
                    if cluster_count > 0:
                        mean_center = cluster_center / cluster_count
                        dist = np.linalg.norm(face_center - mean_center)
                        if dist > spatial_limit:
                            continue
                    cluster_center += face_center
                    cluster_count += 1

                assigned.add(fi)
                cluster.append(fi)

                # 将未分配的邻居加入队列
                for neighbor in adjacency.get(fi, set()):
                    if neighbor not in assigned:
                        queue.append(neighbor)

            if cluster:
                clusters.append(cluster)

        # 合并过小的簇（< 3 面）到最近的空间邻居
        if not skip_spatial and vertices is not None and face_verts is not None:
            clusters = self._merge_tiny_clusters(
                clusters, vertices, face_verts
            )

        return clusters

    def _merge_tiny_clusters(
        self,
        clusters: List[List[int]],
        vertices: np.ndarray,
        face_verts: np.ndarray,
        min_faces: int = 3,
    ) -> List[List[int]]:
        """
        合并面数过少的簇到最近的空间邻居簇
        """
        if len(clusters) <= 1:
            return clusters

        # 计算每个簇的质心
        def cluster_center(cluster):
            all_verts = np.unique(face_verts[cluster].ravel())
            return vertices[all_verts].mean(axis=0)

        centers = [cluster_center(c) for c in clusters]

        # 找到小簇和大簇
        small_indices = [
            i for i, c in enumerate(clusters) if len(c) < min_faces
        ]
        large_indices = [
            i for i, c in enumerate(clusters) if len(c) >= min_faces
        ]

        if not large_indices:
            return clusters

        # 合并：小簇归入最近的大簇
        merged = set()
        for si in small_indices:
            best_dist = float('inf')
            best_li = large_indices[0]
            for li in large_indices:
                dist = np.linalg.norm(centers[si] - centers[li])
                if dist < best_dist:
                    best_dist = dist
                    best_li = li
            clusters[best_li].extend(clusters[si])
            merged.add(si)

        return [c for i, c in enumerate(clusters) if i not in merged]

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

    # ─── 尺寸约束 ────────────────────────────────────

    def _enforce_size_constraints(
        self, obbs: List[OBB], min_cube_size: float
    ) -> List[OBB]:
        """
        强制最小边长约束：
        1. 膨胀过薄的轴向至 min_cube_size / 2
        2. 合并三个轴向都过小的 OBB
        """
        min_half = min_cube_size / 2.0

        # 第一步：膨胀薄轴
        for obb in obbs:
            for i in range(3):
                if obb.half_extents[i] < min_half:
                    obb.half_extents[i] = min_half

        # 第二步：合并所有轴向都过小的 OBB
        changed = True
        while changed and len(obbs) > 1:
            changed = False
            for i in range(len(obbs)):
                if obbs[i] is None:
                    continue
                # 检查是否所有轴向都过小
                if all(obb.half_extents[j] <= min_half for j in range(3)):
                    # 找最近的其他 OBB
                    best_dist = float('inf')
                    best_j = -1
                    for j in range(len(obbs)):
                        if j == i or obbs[j] is None:
                            continue
                        dist = np.linalg.norm(
                            obbs[i].center - obbs[j].center
                        )
                        if dist < best_dist:
                            best_dist = dist
                            best_j = j

                    if best_j >= 0:
                        # 合并：取两个 OBB 的面索引，重新 PCA
                        merged_faces = (
                            obbs[i].face_indices + obbs[best_j].face_indices
                        )
                        # 用合并后的中心作为近似
                        new_center = (
                            obbs[i].center + obbs[best_j].center
                        ) / 2.0
                        # 取两个 OBB 中较大的半长
                        for k in range(3):
                            obbs[best_j].half_extents[k] = max(
                                obbs[i].half_extents[k],
                                obbs[best_j].half_extents[k],
                            )
                        obbs[best_j].center = new_center
                        obbs[best_j].face_indices = merged_faces
                        obbs[i] = None
                        changed = True

            obbs = [o for o in obbs if o is not None]

        return obbs

    # ─── Collection 管理 ─────────────────────────────

    def _get_or_create_collection(self) -> bpy.types.Collection:
        """
        获取或创建输出 Collection

        命名规则: Blockblend_{源对象名}
        再次生成时清空重建
        """
        coll_name = f"Blockblend_{self.obj.name}"

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
