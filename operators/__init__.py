# Operator modules

def register():
    """注册Operators"""
    from . import block_convert
    from . import texture_bake
    block_convert.register()
    texture_bake.register()


def unregister():
    """注销Operators"""
    from . import block_convert
    from . import texture_bake
    texture_bake.unregister()
    block_convert.unregister()


__all__ = ['register', 'unregister']
