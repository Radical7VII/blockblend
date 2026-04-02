# UI modules

def register():
    """注册UI面板"""
    from . import panels
    panels.register()


def unregister():
    """注销UI面板"""
    from . import panels
    panels.unregister()


__all__ = ['register', 'unregister']
