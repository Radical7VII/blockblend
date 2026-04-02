"""Block conversion operator — dispatches to selected engine"""

import bpy
from ..core.obb_engine import OBBEngine
from ..core.heightfield_engine import HeightFieldEngine


class OBJECT_OT_blockblend_convert(bpy.types.Operator):
    """用多个立方体概括模型形状"""
    bl_idname = "object.blockblend_convert"
    bl_label = "生成立方体"
    bl_description = "用多个立方体来概括选中模型的体积和形状"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """检查操作是否可以执行"""
        return (
            context.active_object and
            context.active_object.type == 'MESH'
        )

    def execute(self, context):
        """根据引擎模式执行分解"""
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格对象")
            return {'CANCELLED'}

        props = context.scene.blockblend_props

        try:
            if props.engine_mode == 'HEIGHTFIELD':
                result = self._run_heightfield(obj, props)
            else:
                result = self._run_obb(obj, props)

            if isinstance(result, list):
                props.generated_cube_count = len(result)
                self.report(
                    {'INFO'},
                    f"成功创建了 {len(result)} 个立方体"
                )
            else:
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

    def _run_obb(self, obj, props):
        """执行 OBB 分解"""
        engine = OBBEngine(obj)
        result = engine.execute(
            cube_count=props.cube_count,
            min_cube_size=props.min_cube_size,
            cube_gap=props.cube_gap,
            collection_name=props.collection_name,
        )
        if isinstance(result, list):
            props.last_cube_count_setting = props.cube_count
            if len(result) < props.cube_count:
                self.report(
                    {'WARNING'},
                    f"面数不足，仅生成 {len(result)} 个立方体 "
                    f"(目标 {props.cube_count})"
                )
        return result

    def _run_heightfield(self, obj, props):
        """执行高度场方块分解"""
        engine = HeightFieldEngine(obj)
        return engine.execute(
            voxel_size=props.voxel_size,
            cube_gap=props.cube_gap,
            collection_name=props.collection_name,
        )


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
