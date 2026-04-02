"""Base engine class for all conversion engines"""

from abc import ABC, abstractmethod
from typing import Optional
import bpy
from mathutils import Vector


class ConversionEngine(ABC):
    """
    转换引擎抽象基类

    所有转换引擎必须继承此类并实现execute()方法
    """

    def __init__(self, obj: bpy.types.Object):
        """
        初始化转换引擎

        Args:
            obj: 要转换的Blender对象
        """
        if not obj:
            raise ValueError("对象不能为None")

        self.obj = obj
        self.original_data = None
        self._backup_object()

    def _backup_object(self):
        """备份原始对象数据"""
        if self.obj and self.obj.data:
            self.original_data = self.obj.data.copy()

    @abstractmethod
    def execute(self, **params) -> bpy.types.Object:
        """
        执行转换操作

        Args:
            **params: 转换参数（子类定义具体参数）

        Returns:
            转换后的对象或对象列表

        Raises:
            ValueError: 如果参数无效
            RuntimeError: 如果转换失败
        """
        pass

    def validate_object(self) -> bool:
        """
        验证对象是否为有效的网格类型

        Returns:
            如果对象是有效的网格类型则返回True
        """
        return self.obj.type == 'MESH'

    def calculate_voxel_size(self, detail_level: float = 1.0) -> float:
        """
        根据细节级别计算体素大小

        Args:
            detail_level: 细节级别（0.1-10.0，值越大体素越小）

        Returns:
            计算出的体素大小
        """
        if not self.obj or not self.obj.bound_box:
            return 0.1

        bbox = self.obj.bound_box
        max_dimension = max(
            bbox[6][0] - bbox[0][0],  # X轴
            bbox[6][1] - bbox[0][1],  # Y轴
            bbox[6][2] - bbox[0][2]   # Z轴
        )

        # detail_level越大，体素越小（细节越多）
        # 默认detail_level=1.0时，将对象分成20份
        voxel_size = max_dimension / (20 * detail_level)

        # 确保体素大小在合理范围内
        return max(0.001, min(voxel_size, 10.0))

    def get_object_dimensions(self) -> tuple:
        """
        获取对象的尺寸

        Returns:
            包含(x, y, z)尺寸的元组
        """
        if not self.obj or not self.obj.bound_box:
            return (0.0, 0.0, 0.0)

        bbox = self.obj.bound_box
        dimensions = (
            bbox[6][0] - bbox[0][0],  # X
            bbox[6][1] - bbox[0][1],  # Y
            bbox[6][2] - bbox[0][2]   # Z
        )

        return dimensions

    def get_object_center(self) -> Vector:
        """
        获取对象的中心点

        Returns:
            对象中心点的世界坐标
        """
        if not self.obj:
            return Vector((0.0, 0.0, 0.0))

        bbox = self.obj.bound_box
        center = Vector((
            (bbox[0][0] + bbox[6][0]) / 2,
            (bbox[0][1] + bbox[6][1]) / 2,
            (bbox[0][2] + bbox[6][2]) / 2
        ))

        # 转换为世界坐标
        return self.obj.matrix_world @ center

    def restore_original(self):
        """恢复原始对象（如果需要）"""
        if self.original_data and self.obj:
            # 清理当前数据
            if self.obj.data:
                bpy.data.meshes.remove(self.obj.data)

            # 恢复原始数据
            self.obj.data = self.original_data

    def cleanup(self):
        """清理临时资源"""
        pass
