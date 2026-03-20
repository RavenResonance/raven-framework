# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
#
# ================================================================

import ctypes
import os
from math import cos, radians, sin
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from OpenGL.GL import *
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..helpers.logger import get_logger

# Local imports
from ..helpers.utils_light import is_raven_device

IS_RAVEN_DEVICE = is_raven_device()

if IS_RAVEN_DEVICE:
    # Ensure GLES2 symbols when on embedded
    from OpenGL.GLES2 import *


log = get_logger("ModelViewer")

# Constants
DEFAULT_CLEAR_COLOR = 0.12  # Default OpenGL clear color (dark gray)
DEFAULT_VERTEX_COLOR = 0.8  # Default vertex color value (light gray/white)
ROTATION_TIMER_INTERVAL_MS = 16  # Timer interval for rotation animation (~60 FPS)
ROTATION_INCREMENT = 0.01  # Rotation angle increment per frame in radians
AMBIENT_LIGHTING = 0.7  # Ambient lighting value in shaders
EXTRA_LIGHTING = 0.3  # Extra lighting value added to ambient in shaders
VERTEX_STRIDE = 32  # Vertex stride in bytes: 3 floats (pos) + 3 floats (color) + 2 floats (tex) = 8 floats * 4 bytes
POSITION_OFFSET = 0  # Position attribute offset in bytes
COLOR_OFFSET = 12  # Color attribute offset in bytes (3 floats * 4 bytes)
TEXCOORD_OFFSET = (
    24  # Texture coordinate attribute offset in bytes (6 floats * 4 bytes)
)
BYTES_PER_UINT32 = 4  # Bytes per uint32 index
DEFAULT_VIEWER_SIZE = 720  # Default viewer width and height in pixels


# ----- OBJ loader -----
def load_obj_mesh(
    path: str,
) -> Tuple[np.ndarray, List[Dict[str, Any]], np.ndarray, np.ndarray]:
    """
    Load OBJ file with MTL material and texture support.

    Parses OBJ files with associated MTL material files, supporting multiple materials,
    textures, and vertex attributes (positions, normals, texture coordinates).

    Args:
        path (str): Path to the OBJ file.

    Returns:
        Tuple containing:
            - vertices (np.ndarray): Vertex positions as float32 array, shape (N, 3).
            - material_groups (List[Dict[str, Any]]): List of material groups, each containing:
                - 'name': Material name
                - 'indices': Triangle indices for this material
                - 'texture_path': Path to texture file or None
                - 'color': Material diffuse color (Kd) or None
                - 'count': Number of indices in this group
            - vertex_colors (np.ndarray): Vertex colors as float32 array, shape (N, 3).
            - texcoords (np.ndarray): Texture coordinates as float32 array, shape (N, 2).

    Raises:
        FileNotFoundError: If the OBJ file or associated MTL file is not found.
        ValueError: If the OBJ file format is invalid.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"OBJ file not found: {path}")

    file_ext = os.path.splitext(path)[1].lower()
    if file_ext != ".obj":
        raise ValueError(f"Unsupported file format: {file_ext}. Expected .obj")

    vertices = []
    normals = []
    texcoords = []
    faces = []
    materials = {}
    current_material = None

    obj_dir = os.path.dirname(path) if os.path.dirname(path) else "."

    # Parse OBJ file
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if not parts:
                continue

            if parts[0] == "v":
                # Vertex position
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == "vn":
                # Vertex normal
                normals.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == "vt":
                # Texture coordinate
                texcoords.append([float(parts[1]), float(parts[2])])
            elif parts[0] == "f":
                # Face (can be v, v/vt, v/vt/vn, or v//vn)
                face_verts = []
                for part in parts[1:]:
                    indices = part.split("/")
                    # Handle vertex index (can be positive or negative)
                    v_raw = int(indices[0])
                    if v_raw > 0:
                        v_idx = v_raw - 1  # OBJ is 1-indexed
                    else:
                        # Negative index: count from end
                        v_idx = (
                            len(vertices) + v_raw
                        )  # v_raw is negative, so this subtracts

                    # Handle texture coordinate index
                    if len(indices) > 1 and indices[1]:
                        vt_raw = int(indices[1])
                        if vt_raw > 0:
                            vt_idx = vt_raw - 1
                        else:
                            vt_idx = len(texcoords) + vt_raw
                    else:
                        vt_idx = None

                    # Handle normal index
                    if len(indices) > 2 and indices[2]:
                        vn_raw = int(indices[2])
                        if vn_raw > 0:
                            vn_idx = vn_raw - 1
                        else:
                            vn_idx = len(normals) + vn_raw
                    else:
                        vn_idx = None

                    face_verts.append((v_idx, vt_idx, vn_idx))
                faces.append((face_verts, current_material))
            elif parts[0] == "mtllib":
                # Material library file
                mtl_name = " ".join(parts[1:])  # Handle spaces in filename
                mtl_path = os.path.join(obj_dir, mtl_name)

                # If exact path doesn't exist, search for MTL files
                if not os.path.exists(mtl_path):
                    # Search for any .mtl file in the directory
                    for file in os.listdir(obj_dir):
                        if file.lower().endswith(".mtl"):
                            # Try to match by key parts of the name
                            mtl_key_parts = [
                                p.lower()
                                for p in mtl_name.replace(".mtl", "").split()
                                if len(p) > 2
                            ]
                            file_key_parts = [
                                p.lower()
                                for p in file.replace(".mtl", "").split()
                                if len(p) > 2
                            ]
                            if mtl_key_parts and any(
                                part in file.lower() for part in mtl_key_parts
                            ):
                                mtl_path = os.path.join(obj_dir, file)
                                break
                    # If still not found, use first .mtl file found
                    if not os.path.exists(mtl_path):
                        for file in os.listdir(obj_dir):
                            if file.lower().endswith(".mtl"):
                                mtl_path = os.path.join(obj_dir, file)
                                break

                if os.path.exists(mtl_path):
                    materials.update(parse_mtl(mtl_path, obj_dir))
            elif parts[0] == "usemtl":
                # Use material
                mat_name = " ".join(parts[1:])  # Handle spaces in material name
                current_material = mat_name if mat_name in materials else None

    # If no materials were assigned but we have materials, use the first one
    if not materials:
        log.warning("No materials loaded from MTL file")
    elif not any(face[1] for face in faces) and materials:
        # No faces have materials assigned, use first material
        default_mat = list(materials.keys())[0]
        log.info(f"No materials assigned to faces, using first material: {default_mat}")
        faces = [(face_verts, default_mat) for face_verts, _ in faces]

    # Convert to indexed format, grouping by material
    # Use material-specific vertex maps to avoid color conflicts
    material_vertex_maps = {}  # material_name -> vertex_map
    indexed_vertices = []
    indexed_texcoords = []
    indexed_normals = []
    vertex_material = {}  # vertex_index -> material_name (for color assignment)

    # Group faces by material
    material_groups = {}  # material_name -> list of face indices

    for face_idx, (face_verts, mat_name) in enumerate(faces):
        if mat_name not in material_vertex_maps:
            material_vertex_maps[mat_name] = {}

        vertex_map = material_vertex_maps[mat_name]
        face_indices = []
        for v_idx, vt_idx, vn_idx in face_verts:
            key = (v_idx, vt_idx, vn_idx)
            if key not in vertex_map:
                vertex_idx = len(indexed_vertices)
                vertex_map[key] = vertex_idx
                indexed_vertices.append(vertices[v_idx])
                if vt_idx is not None and vt_idx < len(texcoords):
                    indexed_texcoords.append(texcoords[vt_idx])
                else:
                    indexed_texcoords.append([0.0, 0.0])
                if vn_idx is not None and vn_idx < len(normals):
                    indexed_normals.append(normals[vn_idx])
                else:
                    indexed_normals.append([0.0, 0.0, 1.0])
                # Track which material this vertex belongs to
                vertex_material[vertex_idx] = mat_name
            face_indices.append(vertex_map[key])

        # Triangulate if needed
        if len(face_indices) == 3:
            tri_indices = face_indices
        elif len(face_indices) == 4:
            # Quad to two triangles
            tri_indices = [
                face_indices[0],
                face_indices[1],
                face_indices[2],
                face_indices[0],
                face_indices[2],
                face_indices[3],
            ]
        else:
            # Simple fan triangulation for n-gons
            tri_indices = []
            for i in range(1, len(face_indices) - 1):
                tri_indices.extend(
                    [face_indices[0], face_indices[i], face_indices[i + 1]]
                )

        # Add to material group
        if mat_name not in material_groups:
            material_groups[mat_name] = []
        material_groups[mat_name].extend(tri_indices)

    vertices_array = np.array(indexed_vertices, dtype=np.float32)
    texcoords_array = np.array(indexed_texcoords, dtype=np.float32)

    # Create vertex colors based on material Kd colors
    # For materials with textures, use white so texture shows at full brightness
    # For materials without textures, use Kd color
    vertex_colors = np.ones(
        (len(indexed_vertices), 3), dtype=np.float32
    )  # Default white
    for vertex_idx, mat_name in vertex_material.items():
        if mat_name and mat_name in materials:
            mat = materials[mat_name]
            # Only use Kd color if material has no texture
            if "map_Kd" not in mat and "Kd" in mat:
                # Use material's diffuse color (no texture, so use color)
                vertex_colors[vertex_idx] = mat["Kd"]
            # If material has texture, keep white (1,1,1) so texture shows at full brightness

    # Create material groups with index ranges
    material_data = []
    for mat_name, mat_indices in material_groups.items():
        indices_array = np.array(mat_indices, dtype=np.uint32)
        texture_path = None
        material_color = None
        if mat_name and mat_name in materials:
            mat = materials[mat_name]
            if "map_Kd" in mat:
                texture_path = mat["map_Kd"]
                log.debug(
                    f"Material '{mat_name}': found texture path '{texture_path}', exists: {os.path.exists(texture_path) if texture_path else False}"
                )
            else:
                log.debug(
                    f"Material '{mat_name}': no texture (keys: {list(mat.keys())})"
                )
            if "Kd" in mat:
                material_color = mat["Kd"]
        else:
            log.warning(f"Material '{mat_name}': not in materials dict")
        material_data.append(
            {
                "name": mat_name,
                "indices": indices_array,
                "texture_path": texture_path,
                "color": material_color,  # Material's Kd color
                "count": len(indices_array),
            }
        )

    return vertices_array, material_data, vertex_colors, texcoords_array


def find_texture_file(tex_path: str, obj_dir: str) -> Optional[str]:
    """
    Find texture file, handling absolute paths and searching in textures directory.

    Searches for texture files in multiple locations:
    1. Absolute path if provided
    2. Relative to OBJ file directory
    3. In textures/ subdirectory
    4. Case-insensitive and partial matching

    Args:
        tex_path (str): Texture file path from MTL file (may be relative or absolute).
        obj_dir (str): Directory containing the OBJ file.

    Returns:
        Optional[str]: Full path to found texture file, or None if not found.
    """
    if os.path.isabs(tex_path) and os.path.exists(tex_path):
        return tex_path

    if not os.path.isabs(tex_path):
        rel_path = os.path.join(obj_dir, tex_path)
        if os.path.exists(rel_path):
            return rel_path

    tex_filename = os.path.basename(tex_path.replace("\\", "/"))
    tex_name_no_ext = os.path.splitext(tex_filename)[0].lower()

    textures_dir = os.path.join(obj_dir, "textures")
    if os.path.exists(textures_dir):
        tex_path_in_textures = os.path.join(textures_dir, tex_filename)
        if os.path.exists(tex_path_in_textures):
            return tex_path_in_textures

        for file in os.listdir(textures_dir):
            if file.lower() == tex_filename.lower():
                return os.path.join(textures_dir, file)
            file_name_no_ext = os.path.splitext(file)[0].lower()
            if file_name_no_ext == tex_name_no_ext:
                if os.path.splitext(file)[1].lower() in [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".tif",
                    ".tiff",
                ]:
                    return os.path.join(textures_dir, file)
            tex_parts = [part for part in tex_filename.split("_") if len(part) > 3]
            if tex_parts:
                for part in tex_parts:
                    if part.lower() in file.lower():
                        if os.path.splitext(file)[1].lower() in [
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".webp",
                            ".tif",
                            ".tiff",
                        ]:
                            return os.path.join(textures_dir, file)

    if os.path.exists(obj_dir):
        for file in os.listdir(obj_dir):
            if file.lower() == tex_filename.lower():
                return os.path.join(obj_dir, file)
            file_name_no_ext = os.path.splitext(file)[0].lower()
            if file_name_no_ext == tex_name_no_ext:
                if os.path.splitext(file)[1].lower() in [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".tif",
                    ".tiff",
                ]:
                    return os.path.join(obj_dir, file)

    return None


def parse_mtl(mtl_path: str, obj_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse MTL (Material Template Library) file.

    Extracts material definitions including diffuse colors (Kd) and texture maps (map_Kd).
    Handles texture file path resolution and fallback to alternative texture types.

    Args:
        mtl_path (str): Path to the MTL file.
        obj_dir (str): Directory containing the OBJ file (for texture path resolution).

    Returns:
        Dict[str, Dict[str, Any]]: Dictionary mapping material names to their properties:
            - 'Kd': Diffuse color as [R, G, B] list (optional)
            - 'map_Kd': Path to diffuse texture file (optional)

    Raises:
        FileNotFoundError: If the MTL file is not found.
    """
    materials = {}
    current_material = None

    with open(mtl_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if not parts:
                continue

            if parts[0] == "newmtl":
                current_material = parts[1]
                materials[current_material] = {}
            elif current_material:
                if parts[0] == "map_Kd":
                    # Diffuse texture map (preferred)
                    tex_path = " ".join(parts[1:])  # Handle paths with spaces
                    found_path = find_texture_file(tex_path, obj_dir)
                    if found_path:
                        materials[current_material]["map_Kd"] = found_path
                    elif not os.path.isabs(tex_path):
                        fallback_path = os.path.join(obj_dir, tex_path)
                        materials[current_material]["map_Kd"] = fallback_path
                elif parts[0] == "map_Ke":
                    # Emissive texture map (use as diffuse if no map_Kd)
                    tex_path = " ".join(parts[1:])
                    found_path = find_texture_file(tex_path, obj_dir)
                    if found_path and "map_Kd" not in materials[current_material]:
                        materials[current_material]["map_Kd"] = found_path
                elif parts[0] == "map_Ns":
                    # Normal/specular map (use as diffuse if no map_Kd)
                    tex_path = " ".join(parts[1:])
                    found_path = find_texture_file(tex_path, obj_dir)
                    if found_path and "map_Kd" not in materials[current_material]:
                        materials[current_material]["map_Kd"] = found_path
                elif parts[0] == "Kd":
                    # Diffuse color
                    materials[current_material]["Kd"] = [
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                    ]

    return materials


def load_texture(path: str) -> Optional[int]:
    """
    Load texture image and create OpenGL texture.

    Loads an image file using PIL, converts it to RGBA format, flips it vertically
    (OpenGL expects bottom-left origin), and uploads it to OpenGL as a 2D texture.

    Args:
        path (str): Path to the texture image file (supports common formats: PNG, JPG, etc.).

    Returns:
        Optional[int]: OpenGL texture ID if successful, None if loading fails.

    Note:
        The texture is configured with linear filtering and repeat wrapping.
    """
    if not os.path.exists(path):
        return None

    try:
        img = Image.open(path)

        # Convert to RGBA if needed
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # Flip image vertically (OpenGL expects bottom-left origin)
        img = img.transpose(Image.FLIP_TOP_BOTTOM)

        img_data = np.array(img, dtype=np.uint8)
        width, height = img.size

        # Ensure array is contiguous
        if not img_data.flags["C_CONTIGUOUS"]:
            img_data = np.ascontiguousarray(img_data)

        # Create OpenGL texture
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)

        # Upload texture data
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            width,
            height,
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            img_data,
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)

        # Unbind texture
        glBindTexture(GL_TEXTURE_2D, 0)

        return texture
    except Exception as e:
        log.error(f"Failed to load texture {path}: {e}", exc_info=True)
        return None


# ----- Basic shaders with texture support -----
if not IS_RAVEN_DEVICE:
    VERT_SHADER = """
    #version 330 core
    layout(location = 0) in vec3 position;
    layout(location = 1) in vec3 color;
    layout(location = 2) in vec2 texcoord;
    uniform mat4 mvp;
    out vec3 vColor;
    out vec2 vTexcoord;
    void main() {
        vColor = color;
        vTexcoord = texcoord;
        gl_Position = mvp * vec4(position, 1.0);
    }
    """
    FRAG_SHADER = """
    #version 330 core
    in vec3 vColor;
    in vec2 vTexcoord;
    uniform sampler2D texture0;
    uniform int useTexture;
    out vec4 FragColor;
    void main() {
        if (useTexture == 1) {
            vec4 texColor = texture(texture0, vTexcoord);
            // Add ambient lighting to brighten textures
            float ambient = 0.7;
            float lighting = ambient + 0.3; // Ambient + some extra brightness
            FragColor = texColor * vec4(vColor, 1.0) * lighting;
        } else {
            // Add ambient lighting for non-textured materials too
            float ambient = 0.7;
            float lighting = ambient + 0.3;
            FragColor = vec4(vColor * lighting, 1.0);
        }
    }
    """
else:
    VERT_SHADER = """
    attribute vec3 position;
    attribute vec3 color;
    attribute vec2 texcoord;
    uniform mat4 mvp;
    varying vec3 vColor;
    varying vec2 vTexcoord;
    void main() {
        vColor = color;
        vTexcoord = texcoord;
        gl_Position = mvp * vec4(position, 1.0);
    }
    """
    FRAG_SHADER = """
    precision mediump float;
    varying vec3 vColor;
    varying vec2 vTexcoord;
    uniform sampler2D texture0;
    uniform int useTexture;
    void main() {
        if (useTexture == 1) {
            vec4 texColor = texture2D(texture0, vTexcoord);
            // Add ambient lighting to brighten textures
            float ambient = 0.7;
            float lighting = ambient + 0.3; // Ambient + some extra brightness
            gl_FragColor = texColor * vec4(vColor, 1.0) * lighting;
        } else {
            // Add ambient lighting for non-textured materials too
            float ambient = 0.7;
            float lighting = ambient + 0.3;
            gl_FragColor = vec4(vColor * lighting, 1.0);
        }
    }
    """


# ----- Widget -----
class ModelRenderer(QOpenGLWidget):
    """
    OpenGL widget for rendering 3D models from OBJ files.

    Supports OBJ file format with material and texture support.
    Provides automatic rotation animation and manual rotation control.

    Args:
        obj_path (str): Path to the 3D model file (.obj format).
        is_rotating (bool): If True, automatically rotates the model. Defaults to False.
        model_scale (float): Scale factor for the model. Defaults to 1.0.
        parent (Optional[QWidget]): Parent widget. Defaults to None.

    Attributes:
        obj_path (str): Path to the loaded model file.
        is_rotating (bool): Whether automatic rotation is enabled.
        model_scale (float): Scale factor applied to the model.
        angle (float): Current rotation angle in radians.

    Note:
        The model is automatically centered and normalized to fit approximately in a unit cube
        before scaling. Supports multiple materials and textures for OBJ files.
    """

    def __init__(
        self,
        obj_path: str,
        is_rotating: bool = False,
        model_scale: float = 1.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        if not os.path.exists(obj_path):
            raise FileNotFoundError(f"Model file not found: {obj_path}")
        self.obj_path = obj_path
        self.is_rotating = is_rotating
        self.model_scale = model_scale
        self.angle = 0.0
        self.program: Optional[int] = None
        self.vbo: Optional[int] = None
        self.ibo: Optional[int] = None
        self.vao: Optional[int] = None
        self.texture: Optional[int] = None
        self.material_groups: List[Dict[str, Any]] = []
        self.timer: Optional[QTimer] = None
        self._load_mesh_data()

    def _load_mesh_data(self) -> None:
        """Load OBJ file, center/normalize, build interleaved vertex data. CPU-only; no OpenGL."""
        file_path = self.obj_path
        file_ext = os.path.splitext(file_path)[1].lower()

        positions = None
        material_groups_raw = None
        indices = None
        colors = None
        texcoords = None
        texture_path = None
        is_obj_multi_material = False

        try:
            if file_ext == ".obj":
                result = load_obj_mesh(file_path)
                if isinstance(result[1], list):
                    positions, material_groups_raw, colors, texcoords = result
                    is_obj_multi_material = True
                else:
                    positions, indices, colors, texcoords, texture_path = result
            else:
                log.error(
                    f"Unsupported file format: {file_ext}. Only .obj files are supported."
                )
                raise ValueError(
                    f"Unsupported file format: {file_ext}. Only .obj files are supported."
                )
        except Exception as e:
            log.error(f"Failed to load {file_path}: {e}", exc_info=True)
            positions = np.array([[0, 0, 0]], dtype=np.float32)
            indices = np.array([], dtype=np.uint32)
            colors = None
            texcoords = None
            texture_path = None

        if positions.ndim == 1:
            positions = positions.reshape(-1, 3)

        mins = positions.min(axis=0)
        maxs = positions.max(axis=0)
        center = (mins + maxs) / 2.0
        scale = (maxs - mins).max()
        if scale == 0:
            scale = 1.0
        positions = (positions - center) / scale * self.model_scale

        num_vertices = len(positions)
        if colors is None:
            colors = np.ones((num_vertices, 3), dtype=np.float32) * DEFAULT_VERTEX_COLOR
        else:
            if colors.ndim == 1:
                colors = colors.reshape(-1, 3)
            if len(colors) != num_vertices:
                colors = (
                    np.ones((num_vertices, 3), dtype=np.float32) * DEFAULT_VERTEX_COLOR
                )

        if is_obj_multi_material and material_groups_raw:
            # Ensure colors are (N, 3): one RGB triple per vertex (flat [r,g,b,r,g,b,...] -> rows)
            if colors.ndim == 1:
                colors = colors.reshape(-1, 3)
            if len(colors) != num_vertices:
                colors = np.ones((num_vertices, 3), dtype=np.float32)
            if texcoords is None:
                texcoords = np.zeros((num_vertices, 2), dtype=np.float32)
            else:
                if texcoords.ndim == 1:
                    texcoords = texcoords.reshape(-1, 2)
                if len(texcoords) != num_vertices:
                    texcoords = np.zeros((num_vertices, 2), dtype=np.float32)

            interleaved = np.hstack(
                [
                    positions.astype(np.float32),
                    colors.astype(np.float32),
                    texcoords.astype(np.float32),
                ]
            )
            self._interleaved_flat = interleaved.ravel().astype(np.float32)
            self._is_multi_material = True
            index_offset = 0
            self._material_groups_data = []
            for mat_data in material_groups_raw:
                self._material_groups_data.append(
                    {
                        "indices": mat_data["indices"],
                        "count": mat_data["count"],
                        "texture_path": mat_data.get("texture_path"),
                        "name": mat_data["name"],
                        "index_offset": index_offset,
                    }
                )
                index_offset += mat_data["count"]
        else:
            has_texture = texcoords is not None and texture_path is not None
            if texcoords is None:
                texcoords = np.zeros((num_vertices, 2), dtype=np.float32)
            else:
                if texcoords.ndim == 1:
                    texcoords = texcoords.reshape(-1, 2)
                if len(texcoords) != num_vertices:
                    texcoords = np.zeros((num_vertices, 2), dtype=np.float32)
                    has_texture = False

            interleaved = np.hstack(
                [
                    positions.astype(np.float32),
                    colors.astype(np.float32),
                    texcoords.astype(np.float32),
                ]
            )
            self._interleaved_flat = interleaved.ravel().astype(np.float32)
            self._is_multi_material = False
            self._indices_uint32 = (
                indices.astype(np.uint32)
                if indices is not None
                else np.array([], dtype=np.uint32)
            )
            self._index_count = len(self._indices_uint32)
            self._texture_path = texture_path if has_texture else None
            self._has_texture = has_texture and texture_path is not None

    def initializeGL(self) -> None:
        """Upload preloaded mesh to VBO/IBO, load textures. Called once by Qt when widget is first shown."""
        glClearColor(DEFAULT_CLEAR_COLOR, DEFAULT_CLEAR_COLOR, DEFAULT_CLEAR_COLOR, 1.0)
        glEnable(GL_DEPTH_TEST)

        self.program = glCreateProgram()
        vs = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vs, VERT_SHADER)
        glCompileShader(vs)
        ok = glGetShaderiv(vs, GL_COMPILE_STATUS)
        if not ok:
            log.error(f"Vertex Shader Error: {glGetShaderInfoLog(vs).decode()}")

        fs = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fs, FRAG_SHADER)
        glCompileShader(fs)
        ok = glGetShaderiv(fs, GL_COMPILE_STATUS)
        if not ok:
            log.error(f"Fragment Shader Error: {glGetShaderInfoLog(fs).decode()}")

        glAttachShader(self.program, vs)
        glAttachShader(self.program, fs)
        glLinkProgram(self.program)
        glUseProgram(self.program)

        # Upload preloaded vertex data to VBO
        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(
            GL_ARRAY_BUFFER,
            self._interleaved_flat.nbytes,
            self._interleaved_flat.tobytes(),
            GL_STATIC_DRAW,
        )

        self.is_multi_material = self._is_multi_material

        if self._is_multi_material:
            default_texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, default_texture)
            white_pixel = np.array([255, 255, 255, 255], dtype=np.uint8).reshape(
                1, 1, 4
            )
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA,
                1,
                1,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                white_pixel,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glBindTexture(GL_TEXTURE_2D, 0)

            all_indices = []
            for mat in self._material_groups_data:
                all_indices.extend(mat["indices"].tolist())
            all_indices_array = np.array(all_indices, dtype=np.uint32)
            self.ibo = glGenBuffers(1)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ibo)
            glBufferData(
                GL_ELEMENT_ARRAY_BUFFER,
                all_indices_array.nbytes,
                all_indices_array.tobytes(),
                GL_STATIC_DRAW,
            )

            self.material_groups = []
            for mat_data in self._material_groups_data:
                texture = default_texture
                has_texture = False
                if mat_data["texture_path"]:
                    log.debug(
                        f"Loading texture for '{mat_data['name']}': {mat_data['texture_path']}"
                    )
                    loaded_texture = load_texture(mat_data["texture_path"])
                    if loaded_texture:
                        texture = loaded_texture
                        has_texture = True
                        log.debug(f"Successfully loaded texture ID: {texture}")
                    else:
                        log.warning(
                            f"Failed to load texture for '{mat_data['name']}', using default"
                        )
                else:
                    log.debug(
                        f"Material '{mat_data['name']}' has no texture_path, using default"
                    )
                self.material_groups.append(
                    {
                        "indices": mat_data["indices"],
                        "count": mat_data["count"],
                        "texture": texture,
                        "has_texture": has_texture,
                        "name": mat_data["name"],
                        "index_offset": mat_data["index_offset"],
                    }
                )
        else:
            self.ibo = glGenBuffers(1)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ibo)
            glBufferData(
                GL_ELEMENT_ARRAY_BUFFER,
                self._indices_uint32.nbytes,
                self._indices_uint32.tobytes(),
                GL_STATIC_DRAW,
            )
            self.index_count = self._index_count
            self.texture = None
            self.has_texture = False
            if self._texture_path:
                self.texture = load_texture(self._texture_path)
                if self.texture is not None:
                    self.has_texture = True

        # attribute locations
        if not IS_RAVEN_DEVICE:
            # VAO required on macOS core profile
            self.vao = glGenVertexArrays(1)
            glBindVertexArray(self.vao)
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ibo)

            glVertexAttribPointer(
                0,
                3,
                GL_FLOAT,
                GL_FALSE,
                VERTEX_STRIDE,
                ctypes.c_void_p(POSITION_OFFSET),
            )
            glEnableVertexAttribArray(0)

            glVertexAttribPointer(
                1, 3, GL_FLOAT, GL_FALSE, VERTEX_STRIDE, ctypes.c_void_p(COLOR_OFFSET)
            )
            glEnableVertexAttribArray(1)

            glVertexAttribPointer(
                2,
                2,
                GL_FLOAT,
                GL_FALSE,
                VERTEX_STRIDE,
                ctypes.c_void_p(TEXCOORD_OFFSET),
            )
            glEnableVertexAttribArray(2)
        else:
            # GLES2: query attr locations
            self.pos_loc = glGetAttribLocation(self.program, b"position")
            self.col_loc = glGetAttribLocation(self.program, b"color")
            self.tex_loc = glGetAttribLocation(self.program, b"texcoord")

        self.mvp_loc = glGetUniformLocation(self.program, b"mvp")
        self.texture_loc = glGetUniformLocation(self.program, b"texture0")
        self.use_texture_loc = glGetUniformLocation(self.program, b"useTexture")
        if self.texture_loc != -1:
            glUniform1i(self.texture_loc, 0)  # Using texture unit 0

        # Rotation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(ROTATION_TIMER_INTERVAL_MS)

    def set_rotation(self, angle_degrees: float) -> None:
        """
        Set rotation angle manually.

        Args:
            angle_degrees (float): Rotation angle in degrees (0 to 360).
        """
        self.angle = radians(angle_degrees)
        self.update()

    def paintGL(self) -> None:
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glUseProgram(self.program)

        if not IS_RAVEN_DEVICE:
            glBindVertexArray(self.vao)
        else:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ibo)
            # positions
            glEnableVertexAttribArray(self.pos_loc)
            glVertexAttribPointer(
                self.pos_loc,
                3,
                GL_FLOAT,
                GL_FALSE,
                VERTEX_STRIDE,
                ctypes.c_void_p(POSITION_OFFSET),
            )
            # colors
            glEnableVertexAttribArray(self.col_loc)
            glVertexAttribPointer(
                self.col_loc,
                3,
                GL_FLOAT,
                GL_FALSE,
                VERTEX_STRIDE,
                ctypes.c_void_p(COLOR_OFFSET),
            )
            # texcoords
            glEnableVertexAttribArray(self.tex_loc)
            glVertexAttribPointer(
                self.tex_loc,
                2,
                GL_FLOAT,
                GL_FALSE,
                VERTEX_STRIDE,
                ctypes.c_void_p(TEXCOORD_OFFSET),
            )

        # simple rotation + look-at-ish MVP (no projection, orthographic-ish)
        if self.is_rotating:
            self.angle += ROTATION_INCREMENT
        a = self.angle
        mvp = [
            cos(a),
            0,
            sin(a),
            0,
            0,
            1,
            0,
            0,
            -sin(a),
            0,
            cos(a),
            0,
            0,
            0,
            0,
            1,
        ]
        mvp = (ctypes.c_float * 16)(*mvp)
        glUniformMatrix4fv(self.mvp_loc, 1, GL_FALSE, mvp)

        # Draw based on material type
        if hasattr(self, "is_multi_material") and self.is_multi_material:
            for mat_group in self.material_groups:
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, mat_group["texture"])
                if self.texture_loc != -1:
                    glUniform1i(self.texture_loc, 0)
                use_tex = 1 if mat_group["has_texture"] else 0
                if self.use_texture_loc != -1:
                    glUniform1i(self.use_texture_loc, use_tex)

                offset_ptr = ctypes.c_void_p(
                    mat_group["index_offset"] * BYTES_PER_UINT32
                )
                glDrawElements(
                    GL_TRIANGLES, mat_group["count"], GL_UNSIGNED_INT, offset_ptr
                )
        else:
            # Single texture/material
            if self.has_texture and self.texture:
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, self.texture)
                if self.texture_loc != -1:
                    glUniform1i(self.texture_loc, 0)  # Texture unit 0
                if self.use_texture_loc != -1:
                    glUniform1i(self.use_texture_loc, 1)
            else:
                # Bind a default white texture or disable
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, 0)
                if self.use_texture_loc != -1:
                    glUniform1i(self.use_texture_loc, 0)

            # draw
            glDrawElements(GL_TRIANGLES, self.index_count, GL_UNSIGNED_INT, None)

        if IS_RAVEN_DEVICE:
            glDisableVertexAttribArray(self.pos_loc)
            glDisableVertexAttribArray(self.col_loc)
            glDisableVertexAttribArray(self.tex_loc)

    def cleanup(self) -> None:
        """
        Clean up OpenGL resources.

        Releases all allocated OpenGL resources including buffers, textures, VAOs,
        and shader programs. Should be called before the widget is destroyed.
        """
        try:
            if self.timer and self.timer.isActive():
                self.timer.stop()

            # Clean up textures
            if hasattr(self, "texture") and self.texture:
                glDeleteTextures(1, [self.texture])

            if hasattr(self, "material_groups"):
                for mat_group in self.material_groups:
                    if "texture" in mat_group and mat_group["texture"]:
                        glDeleteTextures(1, [mat_group["texture"]])

            # Clean up buffers
            if hasattr(self, "vbo") and self.vbo:
                glDeleteBuffers(1, [self.vbo])
            if hasattr(self, "ibo") and self.ibo:
                glDeleteBuffers(1, [self.ibo])

            # Clean up VAO (macOS)
            if hasattr(self, "vao") and self.vao and not IS_RAVEN_DEVICE:
                glDeleteVertexArrays(1, [self.vao])

            # Clean up shader program
            if hasattr(self, "program") and self.program:
                glDeleteProgram(self.program)

            log.debug("ModelRenderer resources cleaned up")
        except Exception as e:
            log.error(f"Error during ModelRenderer cleanup: {e}", exc_info=True)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle widget close event and clean up resources."""
        self.cleanup()
        super().closeEvent(event)


# ----- Model Viewer Widget -----
class ModelViewer(QWidget):
    """
    Widget for displaying 3D models with OpenGL rendering.

    A high-level widget that wraps ModelRenderer in a fixed-size container.
    Provides a simple interface for displaying OBJ 3D models with optional
    rotation animation.

    Args:
        obj_path (str): Path to the 3D model file (.obj format).
        width (int): Widget width in pixels. Defaults to 720.
        height (int): Widget height in pixels. Defaults to 720.
        parent (Optional[QWidget]): Parent widget. Defaults to None.
        is_rotating (bool): If True, automatically rotates the model. Defaults to False.
        model_scale (float): Scale factor for the model. Defaults to 1.0.

    Example:
        ```python
        viewer = ModelViewer("model.obj", width=640, height=640, is_rotating=True)
        viewer.set_rotation(45.0)  # Rotate to 45 degrees
        ```
    """

    def __init__(
        self,
        obj_path: str,
        width: int = DEFAULT_VIEWER_SIZE,
        height: int = DEFAULT_VIEWER_SIZE,
        parent: Optional[QWidget] = None,
        is_rotating: bool = False,
        model_scale: float = 1.0,
    ):
        super().__init__(parent)
        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.renderer = ModelRenderer(
            obj_path, is_rotating=is_rotating, model_scale=model_scale
        )
        layout.addWidget(self.renderer)

        self.setLayout(layout)

    def set_rotation(self, angle_degrees: float) -> None:
        """
        Set rotation angle manually.

        Args:
            angle_degrees (float): Rotation angle in degrees (0 to 360).
        """
        self.renderer.set_rotation(angle_degrees)
