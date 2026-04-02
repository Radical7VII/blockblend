# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Blockblend is a Blender 4.2+ add-on (GPL-3.0) that converts high-poly mesh models into Minecraft-style blocky representations. It appears in the 3D Viewport sidebar under "Blockblend".

## Development Setup

This is a pure Blender add-on with no external dependencies or build system. To test:
1. Symlink or copy this folder into Blender's scripts/addons directory, or install via `Edit > Preferences > Add-ons > Install`
2. No tests, linter, or CI are configured

## Architecture

Registration order (defined in `__init__.py`): `properties` → `operators` → `ui`. Unregister reverses this.

### Module Responsibilities

- **`core/base_engine.py`** — Abstract `ConversionEngine` base class. Provides object validation, voxel size calculation, backup/restore. All engines inherit from this.
- **`core/obb_engine.py`** — `OBBEngine`: The primary engine. Decomposes a mesh into oriented bounding boxes using face-normal clustering + PCA. Output goes into a dedicated `Blockblend_{object_name}` collection (cleared on re-run). Cubes are generated without materials.
- **`core/voxel_remesh_engine.py`** — `VoxelRemeshEngine`: Alternative approach using Blender's built-in voxel remesh modifier. Creates individual cubes at voxel centers with color/material options.
- **`operators/block_convert.py`** — `OBJECT_OT_blockblend_convert`: Triggers OBB decomposition. Reads params from `context.scene.blockblend_props`.
- **`operators/texture_bake.py`** — `OBJECT_OT_blockblend_bake`: Handles high-to-low poly texture baking (normal, AO, diffuse, combined). Manages Cycles render engine switching and automatic UV unwrapping.
- **`properties/scene_props.py`** — `BlockblendProperties`: PropertyGroup registered on `bpy.types.Scene`. Holds all UI parameters, color mode settings, bake settings, and statistics.
- **`ui/panels.py`** — Sidebar panels: object info, conversion parameters, bake settings, usage instructions.
- **`utils/helpers.py`** — Shared utilities: `apply_color_to_cube()` (used by voxel engine), material creation, object bounds calculation.

### Key Data Flow

`UI panel` → `Operator.execute()` → reads `scene.blockblend_props` → `Engine(obj).execute(**params)` → creates cubes in collection

### OBB Algorithm Pipeline

`_extract_mesh_data()` → `_build_adjacency_graph()` → `_find_threshold_for_count()` (binary search) → `_cluster_faces()` → `_pca_obb()` per cluster → `_enforce_size_constraints()` → `_create_cube_from_obb()` into collection

## Conventions

- All code comments and docstrings are in Chinese
- Add-on prefix for generated objects: `BB_Cube_`, for materials: `BB_Mat_`, for collections: `Blockblend_`
- Uses `numpy` and `mathutils` extensively in the OBB engine
