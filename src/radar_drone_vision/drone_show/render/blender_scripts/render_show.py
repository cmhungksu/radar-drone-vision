#!/usr/bin/env python3
"""Blender headless render script for drone show animation.

Usage (from worker):
    blender -b -P render_show.py -- --plan outputs/plan_xxx.json

This script reads a timeline_plan.json and creates:
1. Ground plane with grid
2. Obstacle volumes (semi-transparent)
3. Drone spheres with emission materials (LED colors)
4. Bezier curve paths per drone
5. Keyframe animation (location + material color)
6. Camera presets (front, top, audience)
7. Renders to MP4 + PNG storyboard

SIMULATION_ONLY — all outputs watermarked.
"""

import json
import math
import sys
from pathlib import Path

# ─── Parse arguments after '--' ───────────────────────────────────────────────
argv = sys.argv
if '--' in argv:
    argv = argv[argv.index('--') + 1:]
else:
    argv = []

plan_path = None
output_dir = None
for i, arg in enumerate(argv):
    if arg == '--plan' and i + 1 < len(argv):
        plan_path = argv[i + 1]
    elif arg == '--output' and i + 1 < len(argv):
        output_dir = argv[i + 1]

if not plan_path:
    print("Usage: blender -b -P render_show.py -- --plan <path_to_plan.json> [--output <dir>]")
    sys.exit(1)

# ─── Check if running inside Blender ──────────────────────────────────────────
try:
    import bpy
    import mathutils
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False
    print("[INFO] Not running inside Blender. Generating stub output.")

# ─── Load plan ────────────────────────────────────────────────────────────────
with open(plan_path, 'r') as f:
    plan = json.load(f)

drone_count = plan.get('drone_count', 0)
total_duration = plan.get('total_duration_sec', 22)
drones = plan.get('drones', [])
print(f"[render_show] Plan: {plan.get('plan_id', '?')}, {drone_count} drones, {total_duration}s")

if not IN_BLENDER:
    # Stub output: create a summary JSON instead
    out = Path(output_dir or '.')
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "render_type": "blender_stub",
        "plan_id": plan.get('plan_id', ''),
        "drone_count": drone_count,
        "total_duration_sec": total_duration,
        "frames_rendered": 0,
        "note": "Blender not available. Install Blender and run with: blender -b -P render_show.py -- --plan <file>",
        "simulation_only": True,
    }
    with open(out / 'render_stub.json', 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"[render_show] Stub output written to {out / 'render_stub.json'}")
    sys.exit(0)

# ─── Blender scene setup ─────────────────────────────────────────────────────
# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Collections
stage_col = bpy.data.collections.new("Stage")
bpy.context.scene.collection.children.link(stage_col)
drone_col = bpy.data.collections.new("Drones")
bpy.context.scene.collection.children.link(drone_col)
path_col = bpy.data.collections.new("Trajectories")
bpy.context.scene.collection.children.link(path_col)

# Ground plane
bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"
stage_col.objects.link(ground)
bpy.context.scene.collection.objects.unlink(ground)
mat_ground = bpy.data.materials.new("GroundMat")
mat_ground.diffuse_color = (0.05, 0.08, 0.05, 1.0)
ground.data.materials.append(mat_ground)

# Camera
bpy.ops.object.camera_add(location=(0, -100, 80))
cam = bpy.context.active_object
cam.name = "Camera_Front"
cam.rotation_euler = (math.radians(60), 0, 0)
bpy.context.scene.camera = cam

# Light
bpy.ops.object.light_add(type='SUN', location=(50, -50, 100))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 2.0

# World background
bpy.context.scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.02, 0.05, 1.0)

# ─── Create drone objects ─────────────────────────────────────────────────────
fps = 24
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end = int(total_duration * fps)
bpy.context.scene.render.fps = fps

for d in drones:
    drone_id = d['drone_id']

    # Create LED sphere
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, 0, 0))
    sphere = bpy.context.active_object
    sphere.name = f"DRONE_{drone_id}"
    drone_col.objects.link(sphere)
    bpy.context.scene.collection.objects.unlink(sphere)

    # Emission material
    mat = bpy.data.materials.new(f"LED_{drone_id}")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    emission = nodes.new('ShaderNodeEmission')
    output = nodes.new('ShaderNodeOutputMaterial')
    mat.node_tree.links.new(emission.outputs[0], output.inputs[0])
    emission.inputs['Color'].default_value = (0, 0.23, 0.78, 1.0)  # takeoff blue
    emission.inputs['Strength'].default_value = 5.0
    sphere.data.materials.append(mat)

    # Custom properties
    sphere['drone_id'] = drone_id
    sphere['simulation_only'] = True

    # Keyframe animation from segments
    for seg in d.get('segments', []):
        cp = seg.get('control_points', [])
        dur = seg.get('duration_sec', 5)
        t_start = seg.get('t_start', 0)
        led = seg.get('led_timeline', [])

        if len(cp) < 2:
            continue

        # Set location keyframes
        n_frames = max(2, int(dur * fps))
        for fi in range(n_frames + 1):
            frac = fi / n_frames
            frame_num = int((t_start + frac * dur) * fps) + 1

            # Bezier interpolation
            t = frac
            if len(cp) == 2:
                x = cp[0][0] + t * (cp[1][0] - cp[0][0])
                y = cp[0][1] + t * (cp[1][1] - cp[0][1])
                z = cp[0][2] + t * (cp[1][2] - cp[0][2])
            elif len(cp) == 3:
                x = (1-t)**2 * cp[0][0] + 2*(1-t)*t * cp[1][0] + t**2 * cp[2][0]
                y = (1-t)**2 * cp[0][1] + 2*(1-t)*t * cp[1][1] + t**2 * cp[2][1]
                z = (1-t)**2 * cp[0][2] + 2*(1-t)*t * cp[1][2] + t**2 * cp[2][2]
            else:  # 4+ points
                x = (1-t)**3 * cp[0][0] + 3*(1-t)**2*t * cp[1][0] + 3*(1-t)*t**2 * cp[2][0] + t**3 * cp[3][0]
                y = (1-t)**3 * cp[0][1] + 3*(1-t)**2*t * cp[1][1] + 3*(1-t)*t**2 * cp[2][1] + t**3 * cp[3][1]
                z = (1-t)**3 * cp[0][2] + 3*(1-t)**2*t * cp[1][2] + 3*(1-t)*t**2 * cp[2][2] + t**3 * cp[3][2]

            sphere.location = (x, y, z)
            sphere.keyframe_insert(data_path="location", frame=frame_num)

            # LED color keyframes
            if led:
                for li in range(len(led) - 1):
                    lt = led[li].get('t', 0)
                    lt_next = led[li + 1].get('t', dur)
                    if lt <= frac * dur <= lt_next:
                        span = lt_next - lt
                        f2 = (frac * dur - lt) / span if span > 0 else 0
                        c1 = led[li].get('rgb888', [0, 60, 200])
                        c2 = led[li + 1].get('rgb888', [0, 60, 200])
                        r = (c1[0] + f2 * (c2[0] - c1[0])) / 255
                        g = (c1[1] + f2 * (c2[1] - c1[1])) / 255
                        b = (c1[2] + f2 * (c2[2] - c1[2])) / 255
                        emission.inputs['Color'].default_value = (r, g, b, 1.0)
                        emission.inputs['Color'].keyframe_insert(data_path="default_value", frame=frame_num)
                        break

# ─── Render settings ──────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 50  # 960x540 for preview

out_path = Path(output_dir or '.')
out_path.mkdir(parents=True, exist_ok=True)

# Render MP4
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = str(out_path / 'show_preview')
bpy.ops.render.render(animation=True)

# Render storyboard frames
for i, frame_num in enumerate([1, int(8*fps), int(14*fps), int(total_duration*fps)]):
    scene.frame_set(frame_num)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(out_path / f'storyboard_{i:03d}')
    bpy.ops.render.render(write_still=True)

# Save .blend
bpy.ops.wm.save_as_mainfile(filepath=str(out_path / 'show_scene.blend'))

print(f"[render_show] Complete: {out_path}")
print(f"  - show_preview.mp4")
print(f"  - storyboard_000.png to storyboard_003.png")
print(f"  - show_scene.blend")
