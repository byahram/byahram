#!/usr/bin/env python3
"""christmas_tree.py - ASCII 크리스마스 트리 + 좌측 상단 ASCII 인물 초상 (1080x1340, 30fps)

사용법:  python christmas_tree.py --photo me.jpg --out christmas_tree.mp4
python christmas_tree.py --photo me.jpg --still 12.5     (한 장만 PNG로 저장)
필요:    numpy, pillow, ffmpeg  (opencv-python 이 있으면 얼굴 위치를 자동으로 찾음)
"""
import argparse, math, os, re, shutil, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

# ───────────────────────────── 설정 ─────────────────────────────

W, H, FPS, DUR = 1080, 1920, 30, 13.0
SCENE_H = 1340                       # ASCII 장면 높이
H = SCENE_H                         # 패널 복원 시 이 줄을 주석 처리하면 H=1920으로 복귀
TITLE = ""                           # 코드 패널 위 큰 제목 ("" 이면 생략)
HANDLE = ""                          # 예: "@my_account" (비우면 표시 안 함)
GREETING = "M E R R Y   C H R I S T M A S   2 0 2 6"
TAU = math.tau
rng = np.random.default_rng(7)

BG, PANEL = (6, 8, 18), (12, 14, 21)
GOLD, WHITE = (255, 205, 90), (240, 240, 245)
PALETTE = [(255, 70, 70), (255, 200, 60), (90, 160, 255), (200, 110, 255),
(255, 255, 255), (255, 120, 190), (80, 230, 200)]
MONO = ["consola.ttf", "consolab.ttf", "/System/Library/Fonts/Menlo.ttc", "Menlo.ttc", "DejaVuSansMono-Bold.ttf",
"/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "cour.ttf"]
HANGUL = ["malgunbd.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc", "AppleSDGothicNeo.ttc", "NotoSansCJK-Black.ttc",
"/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", "NanumGothicBold.ttf"]
_fonts = {}

def font(size, names=MONO):
    key = (size, names[0])
    if key not in _fonts:
        for n in names:
            try:
                _fonts[key] = ImageFont.truetype(n, size)
                break
            except OSError:
                continue
        else:
            _fonts[key] = None if names is HANGUL else ImageFont.load_default()
    return _fonts[key]

def ease(p):                          # 0..1 부드러운 감속
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3

def bounce(p):                        # 0..1 통통 튀며 착지
    p = min(max(p, 0.0), 1.0)
    if p < 1 / 2.75:
        return 7.5625 * p * p
    if p < 2 / 2.75:
        p -= 1.5 / 2.75
        return 7.5625 * p * p + 0.75
    if p < 2.5 / 2.75:
        p -= 2.25 / 2.75
        return 7.5625 * p * p + 0.9375
    p -= 2.625 / 2.75
    return 7.5625 * p * p + 0.984375

# ───────────────────────────── 트리 ─────────────────────────────

CX, Y_TOP, TREE_H, R_BASE = 560, 335, 775, 330
T_BUILD = 4.6
LEAF = np.array(list("xo*#%&WM@=+-~^v"))

def profile(f):
    """높이 비율 f(0=꼭대기, 1=바닥)에서의 가지 반지름 - 층이 진 원뿔."""
    return R_BASE * (0.05 + 0.95 * f) * (0.80 + 0.20 * ((f * 5) % 1.0))

N = 3000
leaf_f = rng.random(N) ** 0.62
leaf_r = profile(leaf_f) * rng.random(N) ** 0.42
leaf_phi = rng.random(N) * TAU
leaf_y = Y_TOP + leaf_f * TREE_H + rng.normal(0, 4, N)
leaf_ch = LEAF[rng.integers(0, len(LEAF), N)]
leaf_col = np.stack([rng.uniform(20, 95, N), rng.uniform(135, 225, N), rng.uniform(55, 135, N)], 1)
leaf_col[rng.random(N) < 0.06] = (225, 245, 225)

NL = 170                               # 전구
light_f = rng.random(NL) ** 0.62
light_r = profile(light_f) * 1.02
light_phi = rng.random(NL) * TAU
light_col = np.array(PALETTE, float)[rng.integers(0, len(PALETTE), NL)]
light_ch = np.array(list("oO@*"))[rng.integers(0, 4, NL)]
light_on = 3.6 + rng.random(NL) * 2.0
light_spd, light_ph = rng.uniform(2, 6, NL), rng.random(NL) * TAU

NG = 420                               # 금빛 갈런드(나선)
gar_f = np.linspace(0.08, 1.0, NG)
gar_r = profile(gar_f) * 1.04
gar_phi = gar_f * 5 * TAU
gar_ch = np.array(list("~=*"))[rng.integers(0, 3, NG)]

def star_cells(r_out=82, r_in=34, cw=8.4, lh=12):
    pts = []
    for k in range(10):
        r, a = (r_out if k % 2 == 0 else r_in), -math.pi / 2 + k * math.pi / 5
        pts.append((100 + r * math.cos(a), 100 + r * math.sin(a)))
    mask = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    m = np.asarray(mask)
    out = []
    for gy in np.arange(-84, 85, lh):
        for gx in np.arange(-84, 85, cw):
            if m[int(100 + gy), int(100 + gx)]:
                d = math.hypot(gx, gy)
                out.append((gx, gy, "*" if d > 22 else "@"))
    return out

STAR = star_cells()

GIFTS = []                             # (중심x, 열, 행, 상자색, 리본색, 등장시각, 글자)
for i, (gx, c, r, col, rib) in enumerate([(262, 10, 6, (225, 50, 60), GOLD), (372, 7, 5, (170, 90, 230), WHITE),
(742, 8, 5, (70, 130, 240), WHITE), (852, 7, 8, (235, 235, 240), (225, 50, 60)),
(640, 6, 4, (225, 50, 60), WHITE)]):
    GIFTS.append((gx, c, r, col, rib, 6.0 + 0.35 * i, np.array(list("x*o%#&"))[rng.integers(0, 6, (r, c))]))

NS = 230                               # 눈
snow_x, snow_y = rng.random(NS) * W, rng.random(NS) * SCENE_H
snow_v, snow_w = rng.uniform(25, 90, NS), rng.uniform(0.5, 2.0, NS)
snow_ch = np.array(list("*+.·"))[rng.integers(0, 4, NS)]

BURSTS = [(t0, x, y, c, rng.random(70) * TAU, rng.uniform(40, 150, 70))    # 불꽃
for t0, x, y, c in [(10.0, 845, 380, (190, 120, 255)), (10.7, 760, 300, (80, 230, 200)),
(11.4, 880, 520, (255, 120, 190)), (12.1, 800, 400, (255, 200, 60))]]

# ───────────────────────────── 초상 ─────────────────────────────

PX, PY, PR_ = 292, 565, 200            # 원 중심과 반지름
PCW, PLH, PFS = 7.2, 13, 12            # 초상 글자 칸 크기
PC, PRW = int(2 * PR_ / PCW), int(2 * PR_ / PLH)
RAMP = " .:-~=+xoK#%&$WM@"
T_RING, T_FACE, T_HAT, T_HO = 8.8, 9.3, 10.5, 11.1

def face_box(im):
    """얼굴 위치 (cx, cy, 한 변). opencv 가 없으면 증명사진 기준 추정값."""
    w, h = im.size
    try:
        import cv2
        g = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
        xml = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        faces = cv2.CascadeClassifier(xml).detectMultiScale(g, 1.1, 5) if os.path.exists(xml) else []
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda b: b[2] * b[3])
            return x + fw / 2, y + fh * 0.45, fw * 1.25
    except Exception:
        pass
    return w * 0.52, h * 0.315, w * 0.50

def build_portrait(path):
    im = Image.open(path).convert("RGB")
    cx, cy, s = face_box(im)
    crop = im.crop((int(cx - s / 2), int(cy - s / 2), int(cx + s / 2), int(cy + s / 2)))
    a = np.asarray(crop.resize((PC, PRW), Image.LANCZOS), float)
    # 배경 제거: 모서리 색과 비슷하고 가장자리와 이어진 칸
    ref = np.median(np.concatenate([a[:3, :3].reshape(-1, 3), a[:3, -3:].reshape(-1, 3)]), 0)
    cand = np.linalg.norm(a - ref, axis=2) < 70
    bg = np.zeros_like(cand)
    stack = [(0, c) for c in range(PC)] + [(r, 0) for r in range(PRW)] + [(r, PC - 1) for r in range(PRW)]
    while stack:
        r, c = stack.pop()
        if 0 <= r < PRW and 0 <= c < PC and cand[r, c] and not bg[r, c]:
            bg[r, c] = True
            stack += [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
    lum = a @ [0.299, 0.587, 0.114] / 255
    if not (~bg).any():
        raise ValueError("사진에서 초상화 영역을 찾지 못했습니다. 다른 사진을 사용해주세요.")
    lo, hi = np.percentile(lum[~bg], [3, 98])
    lin = np.clip((lum - lo) / max(hi - lo, 1e-8), 0, 1)
    rank = np.searchsorted(np.sort(lum[~bg]), lum) / max((~bg).sum(), 1)   # 히스토그램 평활화
    lum = (0.55 * rank + 0.45 * lin) ** 1.25                              # 이목구비 대비 강화
    col = a / np.maximum(a.max(2), 1)[..., None] * (55 + 200 * lum)[..., None]
    cells = []
    for r in range(PRW):
        for c in range(PC):
            x, y = (c + 0.5) * PCW - PR_, (r + 0.5) * PLH - PR_
            ch = RAMP[int(lum[r, c] * (len(RAMP) - 1))]
            if math.hypot(x, y) < PR_ - 6 and not bg[r, c] and ch != " ":
                cells.append((PX + x, PY + y, ch, tuple(int(v) for v in col[r, c]),
                T_FACE + 0.9 * r / PRW + rng.random() * 0.3))
    return cells

def build_hat():
    hc, hr = 62, 16
    w, h = int(hc * PCW) * 2, hr * PLH * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    P = lambda *xy: [(x * w, y * h) for x, y in zip(xy[::2], xy[1::2])]
    d.polygon(P(.10, .78, .20, .34, .40, .07, .64, .02, .84, .12, .93, .40, .80, .34, .74, .78), fill=(220, 38, 52, 255))
    d.rounded_rectangle((.03 * w, .68 * h, .80 * w, .99 * h), radius=.14 * h, fill=(188, 190, 204, 255))
    d.ellipse((.86 * w, .36 * h, 1.0 * w, .36 * h + .14 * w), fill=(188, 190, 204, 255))
    a = np.asarray(img.resize((hc, hr), Image.BOX), float)
    cells, x0, y0 = [], PX - hc * PCW / 2 + 40, PY - PR_ - 124
    for r in range(hr):
        for c in range(hc):
            if a[r, c, 3] > 110:
                red = a[r, c, 1] < 150
                k = rng.uniform(0.72, 1.0)
                ch = rng.choice(list("%&#%") if red else list("M@WM"))
                cells.append((x0 + (c + .5) * PCW, y0 + (r + .5) * PLH, ch, tuple(int(v * k) for v in a[r, c, :3])))
    return cells

# ───────────────────────────── 코드 패널 ─────────────────────────────

SRC = open(__file__, encoding="utf-8").read().splitlines()
KW = set("def return for in if else elif while import from as class try except lambda and or not pass "
"continue break None True False with global".split())
TOKEN = re.compile(r"(#.*$)|(\"[^\"]*\"|'[^']*')|(\b\d[\d_.]*\b)|([A-Za-z_]\w*)|(\s+)|(.)")
CODE_FS, CODE_LH, CODE_Y = 20, 30, SCENE_H + 62
_lines = {}

def code_line(i):
    if i not in _lines:
        img = Image.new("RGB", (W, CODE_LH), PANEL)
        d, f, x = ImageDraw.Draw(img), font(CODE_FS), 132
        d.text((70, 3), f"{i + 1:>3}", font=f, fill=(70, 76, 96))
        for m in TOKEN.finditer(SRC[i].replace("\t", "    ")[:78]):
            com, s, num, name, sp, other = m.groups()
            tok = m.group(0)
            col = ((98, 110, 135) if com else (160, 210, 140) if s else (240, 170, 110) if num else
            (215, 130, 220) if name in KW else (130, 185, 250) if name and SRC[i][m.end():m.end() + 1] == "("
            else (205, 210, 225))
            ft = f if tok.isascii() else (font(CODE_FS - 2, HANGUL) or f)     # 한글 주석용 글꼴
            if not sp:
                d.text((x, 3), tok, font=ft, fill=col)
            x += d.textlength(tok, font=ft)
        _lines[i] = img
    return _lines[i]

def draw_panel(img, d, t):
    d.rectangle((0, SCENE_H, W, H), fill=PANEL)
    d.text((70, SCENE_H + 16), "christmas_tree.py", font=font(22), fill=(225, 228, 238))
    d.text((920, SCENE_H + 16), f"running · {FPS} fps", font=font(20), fill=(230, 190, 110), anchor="ra")
    d.ellipse((686, SCENE_H + 23, 698, SCENE_H + 35), fill=(90, 220, 130))
    d.line((0, SCENE_H + 54, W, SCENE_H + 54), fill=(34, 38, 52), width=2)
    cur = min(int(t / DUR * len(SRC)), len(SRC) - 1)          # 현재 '실행 중'인 줄
    for row in range((H - CODE_Y) // CODE_LH + 1):
        i, y = cur - 4 + row, CODE_Y + row * CODE_LH
        if 0 <= i < len(SRC):
            img.paste(code_line(i), (0, y))
            if i == cur:
                d.rectangle((0, y, W, y + CODE_LH), outline=(60, 66, 90))
                d.rectangle((0, y, 4, y + CODE_LH), fill=GOLD)
    f = font(68, HANGUL)
    if TITLE and f:
        d.text((W // 2, CODE_Y + 62), TITLE, font=f, fill=(255, 255, 255), anchor="mm",
        stroke_width=6, stroke_fill=(8, 9, 14))

# ───────────────────────────── 한 프레임 ─────────────────────────────

def render(t, face, hat):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    rot = t * 0.55
    f15, f14, f20 = font(15), font(14), font(20)

    # 눈
    sy = (snow_y + snow_v * t) % SCENE_H
    sx = (snow_x + 14 * np.sin(t * snow_w + snow_y)) % W
    for x, y, ch in zip(sx.tolist(), sy.tolist(), snow_ch.tolist()):
        d.text((x, y), ch, font=f15, fill=(200, 205, 225), anchor="mm")

    # 잎: 바닥부터 하얗게 솟아올라 초록으로 식는다
    age = t - (1 - leaf_f) * T_BUILD
    hot = np.clip(1 - age / 0.7, 0, 1)
    ang = leaf_phi + rot
    z = leaf_r * np.sin(ang)
    x = CX + leaf_r * np.cos(ang) * (1 + 0.5 * hot)
    y = leaf_y + z * 0.10 + 40 * hot
    shade = 0.42 + 0.58 * (z / R_BASE * 0.5 + 0.5)
    col = (leaf_col * (1 - hot[:, None]) + 255 * hot[:, None]) * shade[:, None]
    order = np.argsort(z)
    order = order[age[order] > 0]
    for px, py, ch, c in zip(x[order].tolist(), y[order].tolist(), leaf_ch[order].tolist(),
                             col[order].astype(int).tolist()):
        d.text((px, py), ch, font=f15, fill=tuple(c), anchor="mm")
    letters = len(order)

    # 줄기
    if t > 0.2:
        for r in range(4):
            d.text((CX, Y_TOP + TREE_H + 12 + r * 14), "#|H|#", font=f15, fill=(120, 80, 50), anchor="mm")

    # 갈런드
    ang = gar_phi + rot
    gz = gar_r * np.sin(ang)
    vis = (gz > -20) & (t > 4.0 + gar_f * 1.6)
    for px, py, ch in zip((CX + gar_r * np.cos(ang))[vis].tolist(),
                          (Y_TOP + gar_f * TREE_H + gz * 0.10)[vis].tolist(), gar_ch[vis].tolist()):
        d.text((px, py), ch, font=f14, fill=GOLD, anchor="mm")

    # 전구
    ang = light_phi + rot
    lz = light_r * np.sin(ang)
    vis = (lz > -0.2 * light_r) & (t > light_on)
    tw = 0.5 + 0.5 * np.sin(t * light_spd + light_ph)
    lc = np.clip(light_col * (0.45 + 0.75 * tw)[:, None], 0, 255).astype(int)
    for px, py, ch, c in zip((CX + light_r * np.cos(ang))[vis].tolist(),
                             (Y_TOP + light_f * TREE_H + lz * 0.10)[vis].tolist(),
                             light_ch[vis].tolist(), lc[vis].tolist()):
        d.text((px, py), ch, font=f20, fill=tuple(c), anchor="mm")
    lights = int(vis.sum())

    # 별
    if t > 5.0:
        s, k = ease((t - 5.0) / 0.6), 0.8 + 0.2 * math.sin(t * 6)
        for gx, gy, ch in STAR:
            d.text((CX + gx * s, Y_TOP - 52 + gy * s), ch, font=font(14),
                   fill=tuple(int(v * k) for v in (255, 225, 110)), anchor="mm")

    # 선물 상자
    ground = Y_TOP + TREE_H + 72
    for gx, c, r, col, rib, t0, chars in GIFTS:
        if t < t0:
            continue
        dy = -(1 - bounce((t - t0) / 0.9)) * 520
        for rr in range(r):
            for cc in range(c):
                ribbon = cc == c // 2 or rr == r // 2
                d.text((gx + (cc - c / 2 + .5) * 9.4, ground - (r - rr - .5) * 15 + dy), chars[rr, cc],
                       font=f15, fill=rib if ribbon else col, anchor="mm")
        d.text((gx, ground - r * 15 - 8 + dy), "%&%", font=f15, fill=rib, anchor="mm")

    # 인사말
    if t > 8.0:
        n, f22 = int((t - 8.0) * 22), font(22)
        x = W / 2 - d.textlength(GREETING, font=f22) / 2
        for wi, word in enumerate(GREETING.split("   ")):
            wl = d.textlength(word, font=f22)
            c = [(90, 220, 130), (235, 70, 80), GOLD][wi % 3]
            if n > 0:
                d.rectangle((x - 10, 1270, x + wl + 10, 1304), fill=tuple(v // 6 for v in c))
                d.text((x, 1274), word[:n], font=f22, fill=c)
            n -= len(word) + 3
            x += wl + d.textlength("   ", font=f22)

    # 불꽃
    for t0, bx, by, c, angs, spd in BURSTS:
        a = t - t0
        if 0 < a < 1.5:
            k, fade = 1 - math.exp(-3 * a), max(0.0, 1 - a / 1.5)
            for an, sp in zip(angs.tolist(), spd.tolist()):
                d.text((bx + math.cos(an) * sp * k, by + math.sin(an) * sp * k + 40 * a * a), "+" if sp > 90 else "*",
                       font=f15, fill=tuple(int(v * fade) for v in c), anchor="mm")

    # 좌측 상단 초상: 원판 -> 링 -> 얼굴 해독 -> 산타 모자
    if face and t > T_RING:
        p = ease((t - T_RING) / 0.9)
        d.ellipse((PX - PR_ - 8, PY - PR_ - 8, PX + PR_ + 8, PY + PR_ + 8), fill=(7, 9, 20))
        for k in range(int(96 * p)):
            a = -math.pi / 2 + TAU * k / 96
            d.text((PX + (PR_ + 14) * math.cos(a), PY + (PR_ + 14) * math.sin(a)), "o", font=font(13),
                   fill=(215, 215, 225), anchor="mm")
        for k in range(14):                                   # 링을 도는 금빛 불티
            a = t * 0.9 + k * 0.09
            d.text((PX + (PR_ + 30) * math.cos(a), PY + (PR_ + 30) * math.sin(a)), "*", font=font(13),
                   fill=tuple(int(v * (k + 4) / 18) for v in GOLD), anchor="mm")
        fp = font(PFS)
        flick = rng.random(len(face))
        for (x, y, ch, c, t0), fl in zip(face, flick.tolist()):
            if t < t0:
                continue
            if t - t0 < 0.25 or fl < 0.012:                   # 해독 중: 무작위 글자
                ch, c = RAMP[1 + int(fl * 997) % (len(RAMP) - 1)], (170, 255, 200)
            d.text((x, y), ch, font=fp, fill=c, anchor="mm")
    if face and t > T_HAT:
        dy = -(1 - bounce((t - T_HAT) / 0.7)) * 320
        fp = font(PFS)
        for x, y, ch, c in hat:                               # 모자 뒤의 얼굴·링을 가린다
            d.rectangle((x - PCW / 2, y + dy - PLH / 2, x + PCW / 2, y + dy + PLH / 2), fill=(7, 9, 20))
        for x, y, ch, c in hat:
            d.text((x, y + dy), ch, font=fp, fill=c, anchor="mm")
    if face and t > T_HO:
        d.text((PX, PY + PR_ + 52), "HO HO HO!"[:int((t - T_HO) * 14)], font=font(24), fill=GOLD, anchor="mm")

    # HUD
    f16 = font(16)
    d.text((920, 250), f"t {t:5.2f}s", font=f16, fill=(200, 180, 120), anchor="ra")
    hud = [HANDLE] * bool(HANDLE) + [f"rotation {math.degrees(rot) % 360:6.2f}°", f"lights   {lights}",
                                     f"letters  {letters:,}"]
    for i, s in enumerate(hud):
        d.text((70, 1196 + i * 20), s, font=f16, fill=(120, 126, 150))

    # 번짐(글로우)
    scene = img.crop((0, 0, W, SCENE_H))
    glow = scene.resize((W // 4, SCENE_H // 4)).filter(ImageFilter.GaussianBlur(5)).resize(scene.size)
    img.paste(ImageChops.add(scene, glow.point(lambda v: int(v * 0.6))), (0, 0))
    # 코드 패널 복원: 위의 H = SCENE_H를 주석 처리하고 아래 호출의 주석을 해제합니다.
    # draw_panel(img, ImageDraw.Draw(img), t)
    return img

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", help="좌측 상단에 넣을 인물 사진 (생략하면 초상화 없이 생성)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "output", "christmas-tree.mp4"))
    ap.add_argument("--still", type=float, help="이 시각(초)의 한 장만 PNG로 저장")
    a = ap.parse_args()
    if a.still is not None and not 0 <= a.still < DUR:
        ap.error(f"--still은 0 이상 {DUR} 미만이어야 합니다.")
    face, hat = (build_portrait(a.photo), build_hat()) if a.photo else ([], [])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if a.still is not None:
        render(a.still, face, hat).save(os.path.splitext(a.out)[0] + f"_{a.still:.1f}s.png")
        return
    ffmpeg = os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg이 필요합니다. PATH 또는 FFMPEG_BINARY를 설정해주세요.")
    ff = subprocess.Popen([ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
    total = int(DUR * FPS)
    try:
        for n in range(total):
            ff.stdin.write(render(n / FPS, face, hat).tobytes())
            if (n + 1) % FPS == 0:
                print(f"{n + 1}/{total}", file=sys.stderr)
    finally:
        ff.stdin.close()
        status = ff.wait()
    if status:
        sys.exit(f"FFmpeg 변환 실패 (종료 코드 {status})")
    print(f"저장: {a.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
