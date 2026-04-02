"""高度场方块分解引擎

将网格体素化后，用贪心合并算法找出覆盖所有体素的最少轴对齐矩形块集合。
输出为轴对齐的长方体，天然满足"高度场"约束，适合 Minecraft 风格转换。

算法管线：voxelize() → greedy_merge_3d() → create_blender_cubes()
"""

import bpy
import bmesh
import numpy as np
from mathutils import Vector, bvhtree
from typing import List, Tuple, Optional
from .base_engine import ConversionEngine


# 一个矩形块：(网格坐标原点, 尺寸)
# 原点 = 左下角 (x, y, z)，尺寸 = (dx, dy, dz) 体素数
Block = Tuple[int, int, int, int, int, int]


class HeightFieldEngine(ConversionEngine):
    """
    高度场方块分解引擎

    将网格体素化，再用逐层贪心合并生成最少轴对齐方块。
    """

    def execute(
        self,
        voxel_size: float = 0.1,
        cube_gap: float = 0.05,
        collection_name: str = "Blockblend",
        **kwargs,
    ) -> List[bpy.types.Object]:
        """
        执行高度场方块分解

        Args:
            voxel_size: 体素边长（越小越精细）
            cube_gap: 方块间隙比例 (0-0.5)
            collection_name: 输出 Collection 名称

        Returns:
            创建的立方体对象列表
        """
        if not self.validate_object():
            raise ValueError("对象必须是网格类型")

        if voxel_size <= 0:
            raise ValueError("体素大小必须大于 0")

        # 1. 体素化
        grid, origin, actual_size = self._voxelize_mesh(voxel_size)

        occupied = int(grid.sum())
        if occupied == 0:
            raise RuntimeError("体素化后没有占据任何体素，请尝试减小体素大小")

        # 2. 贪心合并
        blocks = self._greedy_merge(grid)

        if not blocks:
            raise RuntimeError("无法生成任何方块")

        # 3. 获取/创建 Collection
        collection = self._get_or_create_collection(collection_name)

        # 4. 创建 Blender 方块
        cube_objects = []
        for i, block in enumerate(blocks):
            cube = self._create_block_cube(
                block, origin, actual_size, cube_gap, collection, i
            )
            if cube:
                cube_objects.append(cube)

        return cube_objects

    # ─── 体素化 ──────────────────────────────────────

    def _voxelize_mesh(
        self,
        voxel_size: float,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        将网格体素化为 3D 占据网格

        使用射线投射沿三个轴扫描，根据交点奇偶性判断体素内部/外部。

        Args:
            voxel_size: 体素边长

        Returns:
            grid: (nx, ny, nz) bool 数组，True = 被占据
            origin: (3,) 世界坐标网格原点（最小角）
            actual_size: 实际体素边长
        """
        # 获取世界坐标下的三角面
        verts, tris = self._get_world_triangles()

        # 计算包围盒
        bb_min = verts.min(axis=0)
        bb_max = verts.max(axis=0)
        dims = bb_max - bb_min

        # 网格尺寸（至少 1 个体素）
        nx = max(1, int(np.ceil(dims[0] / voxel_size)))
        ny = max(1, int(np.ceil(dims[1] / voxel_size)))
        nz = max(1, int(np.ceil(dims[2] / voxel_size)))

        # 调整体素大小使网格恰好覆盖包围盒
        actual = np.array([
            dims[0] / nx if nx > 0 else voxel_size,
            dims[1] / ny if ny > 0 else voxel_size,
            dims[2] / nz if nz > 0 else voxel_size,
        ])
        actual_size = float(actual[0])  # 用于后续计算

        # 网格原点 = 包围盒最小角（稍向内缩半个体素以对齐体素中心）
        origin = bb_min

        # 构建 BVH 树用于射线检测
        tree = self._build_bvh_tree(verts, tris)

        # 占据网格
        grid = np.zeros((nx, ny, nz), dtype=bool)

        # 沿 Z 轴做射线扫描：对每个 (x, y)，沿 Z 方向投射射线
        # 交点成对出现，交点之间的体素在网格内部
        for ix in range(nx):
            for iy in range(ny):
                # 体素中心的世界坐标 (x, y)
                cx = origin[0] + (ix + 0.5) * actual[0]
                cy = origin[1] + (iy + 0.5) * actual[1]

                # 射线从 z 下方远处射向 +Z
                ray_origin = Vector((cx, cy, bb_min[2] - dims[2]))
                ray_dir = Vector((0.0, 0.0, 1.0))

                # 收集所有交点的 t 值
                t_values = []
                loc, normal, idx, t = tree.ray_cast(ray_origin, ray_dir)
                max_t = dims[2] * 3  # 最大搜索距离

                while loc is not None and t < max_t:
                    t_values.append(t)
                    # 从交点处微偏移继续搜索下一个交点
                    ray_origin = loc + ray_dir * 0.0001
                    loc, normal, idx, t = tree.ray_cast(ray_origin, ray_dir)

                # 交点成对标记：第 1-2 个之间在内部，第 3-4 个之间在内部，...
                # 转换 t 值为 z 坐标，再转换为体素索引
                z_base = bb_min[2] - dims[2]  # 射线起始 z
                for pair_idx in range(0, len(t_values) - 1, 2):
                    z_enter = z_base + t_values[pair_idx]
                    z_exit = z_base + t_values[pair_idx + 1]

                    # 转换为体素索引范围
                    iz_min = max(0, int(np.floor((z_enter - origin[2]) / actual[2])))
                    iz_max = min(nz, int(np.ceil((z_exit - origin[2]) / actual[2])))

                    for iz in range(iz_min, iz_max):
                        grid[ix, iy, iz] = True

        return grid, origin, actual_size

    def _get_world_triangles(
        self,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        获取世界坐标下的三角形顶点

        Returns:
            verts: (V, 3) 顶点坐标
            tris: (F, 3) 三角形顶点索引
        """
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = self.obj.evaluated_get(depsgraph)

        bm = bmesh.new()
        bm.from_object(obj_eval, depsgraph)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bmesh.ops.transform(bm, matrix=self.obj.matrix_world, verts=bm.verts)

        verts = np.array([v.co for v in bm.verts], dtype=np.float64)
        tris = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int32)

        bm.free()
        return verts, tris

    def _build_bvh_tree(
        self, verts: np.ndarray, tris: np.ndarray
    ) -> bvhtree.BVHTree:
        """
        从顶点和三角形构建 BVH 树

        Args:
            verts: (V, 3) 顶点坐标
            tris: (F, 3) 三角形索引

        Returns:
            BVHTree 实例
        """
        # BVHTree.FromPolygons 需要 Vector 列表和面索引
        vert_list = [Vector(v) for v in verts]
        poly_list = [tuple(t) for t in tris]
        return bvhtree.BVHTree.FromPolygons(vert_list, poly_list)

    # ─── 贪心 3D 合并 ─────────────────────────────────

    def _greedy_merge(self, grid: np.ndarray) -> List[Block]:
        """
        贪心 3D 合并：将占据的体素合并为最少的轴对齐矩形块

        算法：
        1. 逐 Z 层处理
        2. 在每层内用 2D 贪心找矩形
        3. 尝试向上扩展矩形（跨层合并）

        Args:
            grid: (nx, ny, nz) bool 占据网格

        Returns:
            Block 列表，每个为 (x, y, z, dx, dy, dz)
        """
        nx, ny, nz = grid.shape
        # 标记已处理的体素
        consumed = np.zeros_like(grid, dtype=bool)

        blocks: List[Block] = []

        for iz in range(nz):
            layer = grid[:, :, iz] & ~consumed[:, :, iz]

            if not layer.any():
                continue

            # 在当前层找 2D 矩形
            layer_consumed = np.zeros((nx, ny), dtype=bool)

            while True:
                # 找第一个未处理的占据体素
                remaining = layer & ~layer_consumed
                if not remaining.any():
                    break

                # 找起始点
                start = np.argwhere(remaining)
                sx, sy = start[0]

                # 向右扩展
                dx = 1
                while (sx + dx < nx and
                       remaining[sx + dx, sy]):
                    dx += 1

                # 向下扩展（每行都满足相同的 X 范围）
                dy = 1
                while (sy + dy < ny):
                    row_ok = True
                    for xi in range(sx, sx + dx):
                        if not remaining[xi, sy + dy]:
                            row_ok = False
                            break
                    if not row_ok:
                        break
                    dy += 1

                # 标记当前层的矩形为已处理
                layer_consumed[sx:sx + dx, sy:sy + dy] = True

                # 尝试向上扩展（跨 Z 层合并）
                dz = 1
                while (iz + dz < nz):
                    # 检查上方层对应区域是否全部被占据且未被消耗
                    above_slice = grid[sx:sx + dx, sy:sy + dy, iz + dz]
                    above_consumed = consumed[sx:sx + dx, sy:sy + dy, iz + dz]
                    if above_slice.all() and not above_consumed.any():
                        dz += 1
                    else:
                        break

                # 标记所有涉及的体素为已消耗
                consumed[sx:sx + dx, sy:sy + dy, iz:iz + dz] = True

                blocks.append((sx, sy, iz, dx, dy, dz))

        return blocks

    # ─── Collection 管理 ─────────────────────────────

    def _get_or_create_collection(self, coll_name: str) -> bpy.types.Collection:
        """获取或创建输出 Collection（再次生成时清空重建）"""

        # 构造带对象名的 collection 名称
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
            for mat in bpy.data.materials:
                if mat.name.startswith("BB_Mat_") and mat.users == 0:
                    bpy.data.materials.remove(mat, do_unlink=True)
        else:
            coll = bpy.data.collections.new(full_name)
            bpy.context.scene.collection.children.link(coll)

        return coll

    # ─── 创建 Blender 方块 ─────────────────────────────

    def _create_block_cube(
        self,
        block: Block,
        origin: np.ndarray,
        voxel_size: float,
        cube_gap: float,
        collection: bpy.types.Collection,
        index: int,
    ) -> Optional[bpy.types.Object]:
        """
        从一个 Block 数据创建 Blender 立方体对象

        Args:
            block: (x, y, z, dx, dy, dz) 网格坐标
            origin: 网格世界坐标原点
            voxel_size: 体素边长
            cube_gap: 间隙比例
            collection: 目标 Collection
            index: 序号

        Returns:
            创建的立方体对象
        """
        bx, by, bz, dx, dy, dz = block

        # 间隙因子
        gap_factor = 1.0 - cube_gap

        # 世界坐标中的尺寸（应用间隙）
        size_x = dx * voxel_size * gap_factor
        size_y = dy * voxel_size * gap_factor
        size_z = dz * voxel_size * gap_factor

        # 世界坐标中心
        cx = origin[0] + (bx + dx / 2.0) * voxel_size
        cy = origin[1] + (by + dy / 2.0) * voxel_size
        cz = origin[2] + (bz + dz / 2.0) * voxel_size

        # 创建立方体
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(cx, cy, cz),
        )
        cube = bpy.context.active_object
        cube.name = f"BB_Cube_{index:04d}"

        # 设置缩放（不旋转 — 轴对齐）
        cube.scale = (size_x, size_y, size_z)

        # 应用缩放
        bpy.ops.object.select_all(action='DESELECT')
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        bpy.ops.object.transform_apply(
            location=False, rotation=False, scale=True
        )

        # 移动到目标 Collection
        for coll in cube.users_collection:
            coll.objects.unlink(cube)
        collection.objects.link(cube)

        return cube
