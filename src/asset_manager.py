import os
import hashlib
import urllib.request
import bpy

def verify_file_sha256(filepath, expected_sha256=""):
    if not os.path.isfile(filepath) or os.path.getsize(filepath) < 128:
        return False
    if not expected_sha256:
        return True
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest().lower() == expected_sha256.lower()

def download_external_asset(url, dest_path, expected_sha256=""):
    """تنزيل آمن للأصول الخارجية مع التحقق من سلامة الملف وتجنب إعادة التنزيل."""
    if not url:
        return None
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if verify_file_sha256(dest_path, expected_sha256):
        print(f"[AssetManager] Using cached verified asset: {dest_path}")
        return dest_path
    try:
        print(f"[AssetManager] Downloading asset from {url} ...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response, open(dest_path, 'wb') as out_file:
            out_file.write(response.read())
        if verify_file_sha256(dest_path, expected_sha256):
            print(f"[AssetManager] Successfully verified asset: {dest_path}")
            return dest_path
        else:
            print(f"[AssetManager] WARNING: Checksum/size check failed for {dest_path}")
            os.remove(dest_path)
            return None
    except Exception as e:
        print(f"[AssetManager] External download skipped/failed ({e}). Falling back to custom procedural model.")
        return None

def import_mesh_asset(filepath, collection):
    """استيراد ملف GLB/OBJ إلى مجموعة محددة داخل Blender."""
    if not filepath or not os.path.isfile(filepath):
        return None
    before_objs = set(bpy.data.objects)
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext in [".glb", ".gltf"]:
            bpy.ops.import_scene.gltf(filepath=filepath)
        elif ext == ".obj":
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=filepath)
            else:
                bpy.ops.import_scene.obj(filepath=filepath)
        else:
            return None
        new_objs = [o for o in (set(bpy.data.objects) - before_objs) if o.type == 'MESH']
        for obj in new_objs:
            for col in obj.users_collection:
                col.objects.unlink(obj)
            collection.objects.link(obj)
        return new_objs
    except Exception as e:
        print(f"[AssetManager] Import error for {filepath}: {e}")
        return None