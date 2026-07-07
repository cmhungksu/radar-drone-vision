#!/usr/bin/env python3
"""
Generate icon.png (128x128) and logo.png (512x512) for radar-drone-vision.
Uses Pillow to draw a radar sweep with drone silhouette.
"""
import math
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Installing Pillow...")
    os.system(f'{sys.executable} -m pip install Pillow')
    from PIL import Image, ImageDraw, ImageFont


def draw_radar_icon(size=512):
    """Draw radar icon at given size."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: rounded dark green
    margin = int(size * 0.04)
    radius = int(size * 0.18)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill='#1b4332',
    )

    cx, cy = size // 2, int(size * 0.55)  # Center slightly below middle

    # Radar range rings (concentric arcs)
    ring_color_base = (22, 163, 74)  # #16a34a
    num_rings = 4
    max_r = int(size * 0.38)
    for i in range(1, num_rings + 1):
        r = int(max_r * i / num_rings)
        alpha = int(180 - i * 30)
        ring_color = (*ring_color_base, alpha)

        # Draw arc from ~200 to ~340 degrees (upper half sweep)
        bbox = [cx - r, cy - r, cx + r, cy + r]
        # Pillow arc uses degrees: 0=3 o'clock, 90=6 o'clock
        draw.arc(bbox, start=200, end=340, fill=ring_color, width=max(1, size // 128))

    # Radar sweep beam (bright green wedge)
    sweep_angle = 245  # degrees from 3 o'clock
    sweep_width = 15   # degrees
    beam_r = max_r + int(size * 0.02)
    for da in range(-sweep_width, sweep_width + 1):
        angle_rad = math.radians(sweep_angle + da)
        x2 = cx + int(beam_r * math.cos(angle_rad))
        y2 = cy + int(beam_r * math.sin(angle_rad))
        # Fade alpha based on distance from center of beam
        fade = 1.0 - abs(da) / (sweep_width + 1)
        alpha = int(200 * fade)
        line_color = (22, 163, 74, alpha)
        draw.line([(cx, cy), (x2, y2)], fill=line_color, width=max(1, size // 256))

    # Center dot
    dot_r = int(size * 0.02)
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                 fill='#16a34a')

    # Drone silhouette (simple quadcopter shape) in upper portion
    drone_cx = cx + int(size * 0.12)
    drone_cy = cy - int(size * 0.22)
    arm_len = int(size * 0.07)
    body_r = int(size * 0.025)
    prop_r = int(size * 0.03)
    drone_color = '#bbf7d0'

    # Body
    draw.ellipse([drone_cx - body_r, drone_cy - body_r,
                  drone_cx + body_r, drone_cy + body_r],
                 fill=drone_color)

    # Arms and props (4 arms at 45, 135, 225, 315 degrees)
    for angle_deg in [45, 135, 225, 315]:
        angle_rad = math.radians(angle_deg)
        ax = drone_cx + int(arm_len * math.cos(angle_rad))
        ay = drone_cy + int(arm_len * math.sin(angle_rad))
        # Arm line
        draw.line([(drone_cx, drone_cy), (ax, ay)],
                  fill=drone_color, width=max(1, size // 200))
        # Prop circle
        draw.ellipse([ax - prop_r, ay - prop_r, ax + prop_r, ay + prop_r],
                     outline=drone_color, width=max(1, size // 256))

    # Small blip dots on radar (detected targets)
    blips = [
        (cx - int(size * 0.15), cy - int(size * 0.10)),
        (cx + int(size * 0.08), cy - int(size * 0.18)),
        (cx - int(size * 0.05), cy - int(size * 0.25)),
    ]
    blip_r = int(size * 0.012)
    for bx, by in blips:
        draw.ellipse([bx - blip_r, by - blip_r, bx + blip_r, by + blip_r],
                     fill='#4ade80')

    # Bottom text area: "RADAR" in small text
    try:
        font_size = int(size * 0.07)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()

    text = "RADAR"
    bbox_text = draw.textbbox((0, 0), text, font=font)
    tw = bbox_text[2] - bbox_text[0]
    tx = (size - tw) // 2
    ty = int(size * 0.82)
    draw.text((tx, ty), text, fill='#bbf7d0', font=font)

    return img


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Generate 512x512 logo
    logo = draw_radar_icon(512)
    logo_path = os.path.join(project_root, 'logo.png')
    logo_rgb = Image.new('RGB', logo.size, '#1b4332')
    logo_rgb.paste(logo, mask=logo)
    logo_rgb.save(logo_path, 'PNG')
    print(f"Logo saved: {logo_path} (512x512)")

    # Generate 128x128 icon
    icon = draw_radar_icon(128)
    icon_dir = os.path.join(
        project_root, 'addons', 'radar_drone_vision',
        'static', 'description')
    os.makedirs(icon_dir, exist_ok=True)
    icon_path = os.path.join(icon_dir, 'icon.png')
    icon_rgb = Image.new('RGB', icon.size, '#1b4332')
    icon_rgb.paste(icon, mask=icon)
    icon_rgb.save(icon_path, 'PNG')
    print(f"Icon saved: {icon_path} (128x128)")


if __name__ == '__main__':
    main()
