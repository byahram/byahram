#!/usr/bin/env python3
import argparse
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

W, H, FPS, DUR = 1960, 1340, 30, 13.0
CX, HORIZON, SUN_R = W // 2, 790, 62
RNG = np.random.default_rng(2027)
FONT_NAMES = ["/System/Library/Fonts/Menlo.ttc", "consola.ttf", "Menlo.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "DejaVuSansMono.ttf"]
_fonts = {}


def font(size):
    if size not in _fonts:
        for name in FONT_NAMES:
            try:
                _fonts[size] = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            _fonts[size] = ImageFont.load_default(size=size)
    return _fonts[size]


def smooth(value):
    value = min(max(value, 0.0), 1.0)
    return value * value * (3 - 2 * value)


def mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


STARS = [(RNG.uniform(40, W - 40), RNG.uniform(50, 760),
          RNG.uniform(1, 2.5), RNG.uniform(0, math.tau)) for _ in range(100)]
# 각 물결의 위치와 위상은 고정하고, 시간에 따라 좌우로 흐르게 합니다.
WAVES = [(RNG.uniform(0, W), RNG.uniform(0.02, 1), RNG.uniform(0, math.tau),
          RNG.uniform(0.5, 1.0)) for _ in range(900)]
REFLECTION = [(RNG.uniform(0.65, 1.0), RNG.uniform(0, math.tau)) for _ in range(180)]

# 여러 크기의 고정 노이즈를 겹쳐, 흐트러진 구름과 금빛 가장자리를 만듭니다.
cloud_noise = np.zeros((HORIZON, W), dtype=np.float32)
for columns, rows, weight in [(16, 18, 0.42), (40, 48, 0.30), (110, 100, 0.18), (260, 190, 0.10)]:
    noise = Image.fromarray((RNG.random((rows, columns)) * 255).astype(np.uint8))
    cloud_noise += np.asarray(noise.resize((W, HORIZON), Image.Resampling.BICUBIC), dtype=np.float32) / 255 * weight
cy, cx = np.mgrid[:HORIZON, :W]
wisps = np.sin(cx * 0.006 + cy * 0.038 + cloud_noise * 9) * 0.09
cloud_density = np.clip((cloud_noise + wisps - 0.47) * 5, 0, 1)
cloud_density *= np.clip((HORIZON - cy - 65) / 180, 0, 1)
cloud_density *= 1 - 0.82 * np.exp(-((cx - CX) / 370) ** 2 - ((cy - 620) / 300) ** 2)
CLOUD_MASK = Image.fromarray((cloud_density * 150).astype(np.uint8))
rim = np.clip(np.roll(cloud_density, 12, axis=0) - cloud_density, 0, 1)
rim[:12] = 0
CLOUD_RIM = Image.fromarray((rim * 180).astype(np.uint8))
CLOUD_COLORS = np.empty((HORIZON, 1, 3), dtype=np.uint8)
for channel, values in enumerate([(51, 157, 210), (57, 66, 70), (76, 39, 24)]):
    CLOUD_COLORS[:, 0, channel] = np.interp(np.arange(HORIZON), [0, 430, HORIZON], values)
CLOUDS = Image.fromarray(CLOUD_COLORS).resize((W, HORIZON))
CLOUD_GOLD = Image.new("RGB", (W, HORIZON), (255, 169, 65))

# 검정 바탕의 빛을 스크린 합성해 흰 태양과 강한 금빛 광채를 표현합니다.
GLOW_SIZE = 1400
gy, gx = np.mgrid[:GLOW_SIZE, :GLOW_SIZE]
distance = np.sqrt((gx - GLOW_SIZE / 2) ** 2 + (gy - GLOW_SIZE / 2) ** 2)
broad = np.exp(-((distance / 345) ** 2))
inner = np.exp(-((distance / 110) ** 2))
glow = np.empty((GLOW_SIZE, GLOW_SIZE, 3), dtype=np.uint8)
for c, (outer, core) in enumerate([(180, 160), (62, 220), (4, 90)]):
    glow[:, :, c] = np.clip(broad * outer + inner * core, 0, 255)
GLOW = Image.fromarray(glow)
del cloud_noise, cloud_density, rim, cy, cx, gy, gx, distance, broad, inner, glow


def render(t):
    progress = min(max(t / DUR, 0.0), 1.0)
    daylight = smooth((progress - 0.08) / 0.8)
    sunrise = smooth((progress - 0.12) / 0.76)
    sun_y = round(HORIZON + SUN_R + 24 - 210 * sunrise)

    # 남색 새벽에서 주황빛 수평선과 푸른 아침 하늘로 전환합니다.
    top = mix((13, 19, 49), (43, 77, 114), daylight)
    middle = mix((47, 39, 74), (233, 112, 52), daylight)
    horizon = mix((109, 62, 88), (255, 161, 39), daylight)
    rows = np.empty((H, 1, 3), dtype=np.uint8)
    for channel in range(3):
        rows[:, 0, channel] = np.interp(np.arange(H), [0, HORIZON * 0.58, HORIZON, H],
                                       [top[channel], middle[channel], horizon[channel], horizon[channel]])
    img = Image.fromarray(rows).resize((W, H))
    d = ImageDraw.Draw(img)

    star_visibility = 1 - smooth(progress / 0.58)
    for x, y, radius, phase in STARS:
        if star_visibility < 0.02:
            break
        brightness = star_visibility * (0.65 + 0.35 * math.sin(t * 1.1 + phase) ** 2)
        local_bg = mix(top, middle, min(y / (HORIZON * 0.58), 1))
        color = mix(local_bg, (255, 237, 215), brightness)
        d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    # 금빛으로 물든 구름을 먼저 그리고, 태양의 빛이 그 위로 번지게 합니다.
    # 새벽의 구름은 유지하고, 밝아진 뒤에만 가장 옅은 구름을 조금 덜어냅니다.
    cloud_clear = smooth((daylight - 0.45) / 0.55)
    cloud_mask = CLOUD_MASK.point(lambda value: round(max(0, value - 4 * cloud_clear)
                                                     * (0.2 + daylight * 0.8) * (1 - 0.05 * cloud_clear)))
    img.paste(CLOUDS, (0, 0), cloud_mask)
    img.paste(CLOUD_GOLD, (0, 0), CLOUD_RIM.point(lambda value: round(value * daylight * (1 - 0.08 * cloud_clear))))
    light = Image.new("RGB", (W, H))
    light.paste(GLOW, (CX - GLOW_SIZE // 2, sun_y - GLOW_SIZE // 2))
    light = light.point(lambda value: round(value * (0.2 + daylight * 0.8)))
    img = ImageChops.screen(img, light)
    d = ImageDraw.Draw(img)
    # 작고 선명한 흰 중심과 노란 외곽으로 눈부신 태양을 표현합니다.
    d.ellipse((CX - SUN_R, sun_y - SUN_R, CX + SUN_R, sun_y + SUN_R),
              fill=mix((255, 190, 80), (255, 247, 174), daylight))
    core = SUN_R * 0.78
    d.ellipse((CX - core, sun_y - core, CX + core, sun_y + core),
              fill=mix((255, 222, 135), (255, 255, 239), daylight))

    # 멀리 보이는 수면은 밝게, 가까운 바다는 깊은 푸른색으로 표현합니다.
    water_top = mix((35, 34, 63), (173, 128, 90), daylight)
    water_bottom = mix((8, 19, 40), (32, 54, 70), daylight)
    sea_height = H - HORIZON
    for y in range(HORIZON, H):
        depth = (y - HORIZON) / sea_height
        d.line((0, y, W, y), fill=mix(water_top, water_bottom, depth ** 0.65))

    # 가까운 물결일수록 길고 두껍게 그려 원근감을 만듭니다.
    for x, depth, phase, brightness in WAVES:
        y = HORIZON + 5 + depth ** 1.7 * (sea_height - 10)
        length = 5 + depth * 110
        drift = math.sin(t * 0.75 + phase) * (5 + depth * 22)
        base = mix(water_top, water_bottom, depth ** 1.1)
        color = mix(base, mix((61, 63, 90), (237, 174, 103), daylight),
                    brightness * (0.14 + depth * 0.18))
        d.line((x - length / 2 + drift, y, x + length / 2 + drift, y),
               fill=color, width=max(1, int(1 + depth * 3)))

    # 해 아래에서 시작해 앞쪽으로 길게 이어지는 금빛 반사광.
    sun_visible = smooth((HORIZON - (sun_y - SUN_R)) / (SUN_R * 1.4))
    for i, (variation, phase) in enumerate(REFLECTION):
        depth = (i + 1) / len(REFLECTION)
        y = HORIZON + 3 + depth * (sea_height - 6)
        spread = (10 + depth ** 0.8 * 165) * variation
        drift = math.sin(t * 1.6 + phase) * (3 + depth * 22)
        base = mix(water_top, water_bottom, depth ** 0.65)
        shimmer = 0.83 + 0.17 * math.sin(t * 2.1 + phase) ** 2
        color = mix(base, (255, 228, 125), sun_visible * shimmer * (1.0 - depth * 0.08))
        gap = (1 + depth * 3) * (0.5 + 0.5 * math.sin(t + phase))
        d.line((CX - spread + drift, y, CX - gap + drift, y), fill=color,
               width=max(1, int(1 + depth * 3)))
        d.line((CX + gap + drift, y, CX + spread * 0.85 + drift, y), fill=color,
               width=max(1, int(1 + depth * 3)))
        if i % 3 != 0:
            core_width = spread * (0.22 + 0.12 * math.sin(t * 1.3 + phase) ** 2)
            d.line((CX - core_width + drift, y, CX + core_width + drift, y),
                   fill=mix(base, (255, 255, 219), sun_visible * 0.98),
                   width=max(1, int(1 + depth * 2)))

    # 전경의 긴 잔물결은 조금씩 움직이며 바다 표면을 이어줍니다.
    for i in range(6):
        depth = 0.35 + i * 0.12
        y = HORIZON + depth * sea_height
        points = [(x, y + math.sin(x * 0.006 + t * 0.7 + i) * (2 + depth * 4))
                  for x in range(0, W + 1, 10)]
        base = mix(water_top, water_bottom, depth ** 0.65)
        d.line(points, fill=mix(base, (103, 145, 166), 0.13 * daylight), width=2)

    text_color = mix((242, 225, 218), (255, 241, 214), daylight)
    d.text((CX, 145), "H A P P Y   N E W   Y E A R", font=font(32),
           fill=text_color, anchor="mm")
    goodbye = 1 - smooth((progress - 0.28) / 0.17)
    welcome = smooth((progress - 0.45) / 0.18)
    # 별도 레이어에서 문구를 페이드해 하늘의 그라데이션을 유지합니다.
    for label, opacity in [("GOODBYE 2026", goodbye), ("WELCOME 2027", welcome)]:
        if opacity <= 0:
            continue
        overlay = Image.new("RGBA", (W, H))
        ImageDraw.Draw(overlay).text((CX, 260), label, font=font(72),
                                    fill=(*text_color, round(255 * opacity)), anchor="mm")
        img.paste(overlay, (0, 0), overlay)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "output/happy-new-year.mp4")
    ap.add_argument("--still", type=float, help="지정 시각의 PNG 저장 (0 이상 13 미만)")
    a = ap.parse_args()
    if a.still is not None and not 0 <= a.still < DUR:
        ap.error(f"--still은 0 이상 {DUR} 미만이어야 합니다.")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.still is not None:
        path = a.out.with_name(f"{a.out.stem}_{a.still:.1f}s.png")
        render(a.still).save(path)
        print(f"저장: {path}")
        return
    ffmpeg = os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("FFmpeg를 설치하거나 FFMPEG_BINARY를 설정해주세요.")
    ff = subprocess.Popen([ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                           "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.out)],
                          stdin=subprocess.PIPE)
    try:
        for n in range(int(DUR * FPS)):
            ff.stdin.write(render(n / FPS).tobytes())
            if (n + 1) % FPS == 0:
                print(f"{n + 1}/{int(DUR * FPS)}", file=sys.stderr)
    finally:
        ff.stdin.close()
        status = ff.wait()
    if status:
        sys.exit(f"FFmpeg 변환 실패 (종료 코드 {status})")
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
