"""Texture baking operator for LOD workflow"""

import bpy


class OBJECT_OT_blockblend_bake(bpy.types.Operator):
    """将活动对象的贴图烘焙到另一个选中的模型（LOD烘焙）"""
    bl_idname = "object.blockblend_bake"
    bl_label = "烘焙贴图"
    bl_description = (
        "选中两个对象：活动对象为源（高模），另一个为目标（低模/LOD）。"
        "将源模型的材质/纹理烘焙到目标模型上。"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """需要已指定源和目标网格对象"""
        props = context.scene.blockblend_props
        source = props.bake_source_object
        target = props.bake_target_object
        return (
            source is not None
            and target is not None
            and source.type == 'MESH'
            and target.type == 'MESH'
            and source != target
        )

    def execute(self, context):
        props = context.scene.blockblend_props

        # === 从属性获取源和目标 ===
        source = props.bake_source_object
        target = props.bake_target_object

        if source == target:
            self.report({'ERROR'}, "源对象和目标对象不能相同")
            return {'CANCELLED'}

        # === 验证 ===
        if not source.data.materials:
            self.report({'WARNING'},
                        f"源对象 '{source.name}' 没有材质，烘焙结果可能为空")

        # === 自动展开目标UV ===
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        context.view_layer.objects.active = target
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=1.15192)
        bpy.ops.object.mode_set(mode='OBJECT')

        # === 保存当前渲染引擎 ===
        orig_engine = context.scene.render.engine
        bake_type = props.bake_type

        try:
            # 切换到 Cycles（烘焙必须使用 Cycles）
            context.scene.render.engine = 'CYCLES'

            # 根据烘焙类型设置采样数
            if bake_type in {'DIFFUSE', 'NORMAL'}:
                context.scene.cycles.samples = 1
            else:
                context.scene.cycles.samples = props.bake_samples

            # === 创建烘焙图片 ===
            res = props.bake_resolution
            is_normal = (bake_type == 'NORMAL')

            img_name = f"{target.name}_{bake_type.lower()}"
            img = bpy.data.images.new(
                img_name,
                width=res,
                height=res,
                alpha=False,
            )
            img.colorspace_settings.name = (
                'Non-Color' if is_normal else 'sRGB'
            )

            # === 为目标设置烘焙材质 ===
            self._setup_target_material(target, img, bake_type)

            # === 选择对象 ===
            # Blender 烘焙约定：selected=源, active=目标（接收烘焙结果）
            bpy.ops.object.select_all(action='DESELECT')
            source.select_set(True)
            target.select_set(True)
            context.view_layer.objects.active = target

            # === 配置烘焙参数 ===
            bake_settings = context.scene.render.bake
            bake_settings.margin = props.bake_margin
            bake_settings.use_selected_to_active = True
            bake_settings.use_clear = True

            if bake_type == 'DIFFUSE':
                # 只烘焙颜色，不烘焙光照
                bake_settings.use_pass_color = True
                bake_settings.use_pass_direct = False
                bake_settings.use_pass_indirect = False

            # === 执行烘焙 ===
            bpy.ops.object.bake(type=bake_type)

            # === 保存图片到磁盘 ===
            # 使用绝对路径，避免 blend 文件未保存时的问题
            import os
            import tempfile

            # 优先使用 blend 文件所在目录，否则使用临时目录
            if bpy.data.is_saved:
                bake_dir = os.path.dirname(bpy.data.filepath)
            else:
                bake_dir = tempfile.gettempdir()

            filepath = os.path.join(bake_dir, f"baked_{img_name}.png")
            img.filepath_raw = filepath
            img.file_format = 'PNG'
            if is_normal:
                img.file_format = 'PNG'
            img.save()

            # 恢复选择状态
            bpy.ops.object.select_all(action='DESELECT')
            source.select_set(True)
            target.select_set(True)
            context.view_layer.objects.active = source

            self.report({'INFO'},
                        f"已将 '{source.name}' 的"
                        f"{self._bake_type_label(bake_type)}"
                        f"烘焙到 '{target.name}'\n"
                        f"贴图已保存至: {filepath}")
            return {'FINISHED'}

        except RuntimeError as e:
            self.report({'ERROR'}, f"烘焙失败: {str(e)}")
            return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"未知错误: {str(e)}")
            return {'CANCELLED'}

        finally:
            # 恢复原始渲染引擎
            context.scene.render.engine = orig_engine

    def _setup_target_material(self, target, img, bake_type):
        """
        为目标对象创建烘焙材质（含 Image Texture 节点）

        烘焙时，Blender 将结果写入 node tree 中**活动**的
        Image Texture 节点。因此必须创建该节点并设为 active。

        Args:
            target: 目标网格对象
            img: 烘焙目标图片
            bake_type: 烘焙类型
        """
        mat_name = f"Bake_{target.name}"
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # 清空默认节点
        nodes.clear()

        # --- 创建节点 ---

        # Image Texture（烘焙目标节点）
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = img
        tex_node.interpolation = 'Closest'
        tex_node.location = (-200, 300)
        # 关键：设为 active 节点，烘焙结果会写入此节点
        nodes.active = tex_node

        # Principled BSDF
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (200, 300)

        # Material Output
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (500, 300)

        # --- 连接节点 ---
        if bake_type == 'NORMAL':
            # 法线贴图：Image → Normal Map → BSDF Normal
            normal_map = nodes.new('ShaderNodeNormalMap')
            normal_map.location = (0, 300)
            links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
            links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])
        else:
            # 颜色类：Image → BSDF Base Color
            links.new(tex_node.outputs['Color'],
                      bsdf.inputs['Base Color'])

        # BSDF → Output
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        # 分配材质到目标
        target.data.materials.clear()
        target.data.materials.append(mat)

    @staticmethod
    def _bake_type_label(bake_type):
        """烘焙类型的中文标签"""
        labels = {
            'DIFFUSE': '漫反射颜色',
            'NORMAL': '法线贴图',
            'AO': '环境光遮蔽',
            'COMBINED': '合成贴图',
        }
        return labels.get(bake_type, bake_type)


_classes = [OBJECT_OT_blockblend_bake]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
