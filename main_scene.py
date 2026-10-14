import os
import sys
import json
import argparse
import bpy

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.compat import configure_render_engine
from src.materials import create_lemmino_materials, setup_freestyle_outlines
from src.aircraft_builder import build_boeing_727
from src.character_builder import build_db_cooper_rigged
from src.environment_builder import build_forest_canopy, build_city_bokeh_cluster, build_rain_and_birds
from src.animation_director import animate_scene, setup_cinematic_cameras

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def setup_world_background(scene, bg_color):
    world = bpy.data.worlds.new("LEMMiNO_Night_Void")
    scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs[0].default_value = tuple(bg_color)
        bg_node.inputs[1].default_value = 1.0

def build_full_scene(config, profile_name):
    clear_scene()
    scene = bpy.context.scene
    profile = config["profiles"][profile_name]

    scene.render.resolution_x = profile["resolution_x"]
    scene.render.resolution_y = profile["resolution_y"]
    scene.render.resolution_percentage = profile["resolution_percentage"]
    scene.render.fps = profile["fps"]
    scene.frame_start = profile["frame_start"]
    scene.frame_end = profile["frame_end"]
    scene.frame_step = profile["frame_step"]

    configure_render_engine(scene, samples=profile["eevee_samples"], use_motion_blur=profile["motion_blur"])
    setup_world_background(scene, config["colors"]["background_void"])

    col_aircraft = bpy.data.collections.new("01_Aircraft_B727")
    col_character = bpy.data.collections.new("02_Character_Cooper")
    col_env = bpy.data.collections.new("03_Environment")
    col_cams = bpy.data.collections.new("04_Cameras")
    for c in [col_aircraft, col_character, col_env, col_cams]:
        scene.collection.children.link(c)

    mats = create_lemmino_materials(config)
    aircraft_root, stair_pivot = build_boeing_727(col_aircraft, mats)
    cooper_root, pivots = build_db_cooper_rigged(col_character, mats)
    forest_root = build_forest_canopy(col_env, mats, tree_count=profile["forest_tree_count"])
    bokeh_root = build_city_bokeh_cluster(col_env, mats)
    rain_root, birds = build_rain_and_birds(
        col_env, mats,
        rain_count=profile["rain_particle_count"],
        bird_count=profile["bird_count"]
    )

    setup_freestyle_outlines(scene, thickness=profile["freestyle_thickness"])
    for vl in scene.view_layers:
        if vl.freestyle_settings.linesets:
            ls = vl.freestyle_settings.linesets[0]
            ls.select_by_collection = True
            ls.collection = col_aircraft
            ls.collection_negation = 'INCLUSIVE'

    animate_scene(scene, aircraft_root, stair_pivot, cooper_root, pivots, bokeh_root, birds)
    setup_cinematic_cameras(scene, col_cams, aircraft_root, cooper_root, bokeh_root)

    blend_path = os.path.join(PROJECT_ROOT, config["paths"]["blend_file"])
    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[SceneBuilder] Saved Blender project to: {blend_path}")
    return scene

def render_sample_keyframes(scene, config):
    samples_dir = os.path.join(PROJECT_ROOT, config["paths"]["samples_dir"])
    os.makedirs(samples_dir, exist_ok=True)
    # حذف العينات القديمة لضمان فحص العينات الجديدة فقط
    for old_f in os.listdir(samples_dir):
        if old_f.endswith(".png"):
            os.remove(os.path.join(samples_dir, old_f))

    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'

    for frame in config["sample_keyframes"]:
        out_file = os.path.join(samples_dir, f"sample_{frame:04d}.png")
        scene.frame_set(frame)
        active_cam = None
        for m in sorted(scene.timeline_markers, key=lambda x: x.frame):
            if m.frame <= frame and m.camera:
                active_cam = m.camera
        if active_cam:
            scene.camera = active_cam
        scene.render.filepath = out_file
        print(f"[Renderer] Rendering sample keyframe {frame} (Camera: {scene.camera.name}) -> {out_file}")
        bpy.ops.render.render(write_still=True)

def render_animation_resumable(scene, config, frame_start=None, frame_end=None, frame_step=None):
    frames_dir = os.path.join(PROJECT_ROOT, config["paths"]["frames_dir"])
    os.makedirs(frames_dir, exist_ok=True)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'

    f_start = frame_start if frame_start is not None else scene.frame_start
    f_end   = frame_end if frame_end is not None else scene.frame_end
    f_step  = frame_step if frame_step is not None else scene.frame_step

    for frame in range(f_start, f_end + 1, f_step):
        out_file = os.path.join(frames_dir, f"frame_{frame:04d}.png")
        scene.frame_set(frame)
        active_cam = None
        for m in sorted(scene.timeline_markers, key=lambda x: x.frame):
            if m.frame <= frame and m.camera:
                active_cam = m.camera
        if active_cam:
            scene.camera = active_cam
        scene.render.filepath = out_file
        print(f"[Renderer] Rendering frame {frame:04d}/{f_end:04d} [{scene.camera.name}]")
        bpy.ops.render.render(write_still=True)

def main():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="LEMMiNO D.B. Cooper 3D Scene Builder & Renderer")
    parser.add_argument("--profile", default=None, choices=["preview", "production"])
    parser.add_argument("--mode", default="samples_and_video", choices=["build_only", "samples", "samples_and_video"])
    parser.add_argument("--frame-step", type=int, default=None)
    args = parser.parse_args(argv)

    with open(os.path.join(PROJECT_ROOT, "config.json"), "r", encoding="utf-8") as f:
        config = json.load(f)

    profile_name = args.profile or config.get("active_profile", "preview")
    scene = build_full_scene(config, profile_name)

    if args.mode in ["samples", "samples_and_video"]:
        render_sample_keyframes(scene, config)

    if args.mode == "samples_and_video":
        step = args.frame_step if args.frame_step is not None else config["profiles"][profile_name]["frame_step"]
        render_animation_resumable(scene, config, frame_step=step)

if __name__ == "__main__":
    main()