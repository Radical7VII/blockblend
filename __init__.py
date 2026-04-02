# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name": "Blockblend",
    "author": "Othniel Su",
    "description": "Convert high-poly models to Minecraft-style blocky meshes",
    "blender": (4, 2, 0),
    "version": (1, 0, 0),
    "location": "View3D > Sidebar > Blockblend",
    "warning": "",
    "category": "Mesh",
}


def register():
    """Register all classes and properties"""
    # Import submodules
    from . import properties
    from . import operators
    from . import ui

    # Register in correct order: properties → operators → UI
    properties.register()
    operators.register()
    ui.register()

    print("Blockblend (1, 0, 0) registered successfully")


def unregister():
    """Unregister all classes and properties"""
    # Import submodules
    from . import properties
    from . import operators
    from . import ui

    # Unregister in reverse order: UI → operators → properties
    ui.unregister()
    operators.unregister()
    properties.unregister()

    print("Blockblend unregistered")
