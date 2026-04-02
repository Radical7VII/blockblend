# Property modules

def register():
    """注册属性"""
    from . import scene_props
    scene_props.register()


def unregister():
    """注销属性"""
    from . import scene_props
    scene_props.unregister()


__all__ = ['register', 'unregister']
