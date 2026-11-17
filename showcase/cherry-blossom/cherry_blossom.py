#!/usr/bin/env python3
import argparse
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, DUR = 1960, 1340, 30, 13.0
CX, VANISH_Y = W // 2, 795
RNG = np.random.default_rng(26)
PINKS = [(255, 221, 231), (255, 235, 240), (249, 193, 213),
         (255, 244, 246), (241, 161, 190)]
_fonts = {}


def font(size):
    if size not in _fonts:
        for name in ["/System/Library/Fonts/Menlo.ttc", "consola.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
            try:
                _fonts[size] = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            _fonts[size] = ImageFont.load_default(size=size)
    return _fonts[size]


def petal(d, x, y, color, angle, size=13, landed=False):
    shape = [(0, -1), (.55, -.7), (.65, -.1), (.25, .7), (0, 1), (-.3, .6), (-.6, -.2), (-.5, -.7)]
    ca, sa = math.cos(angle), math.sin(angle)
    points = []
    for px, py in shape:
        px, py = px * size, py * size * (0.25 if landed else 1)
        points.append((x + px * ca - py * sa, y + px * sa + py * ca))
    d.polygon(points, fill=PINKS[color])


def flower_sprite(color, radius):
    extent = radius * 3
    im = Image.new("RGBA", (extent * 2 + 1, extent * 2 + 1))
    d = ImageDraw.Draw(im)
    for k in range(5):
        a = k * math.tau / 5 - math.pi / 2
        x, y = extent + math.cos(a) * radius, extent + math.sin(a) * radius
        r = radius * .88
        d.ellipse((x-r, y-r, x+r, y+r), fill=PINKS[color])
    d.ellipse((extent-1.5, extent-1.5, extent+1.5, extent+1.5), fill=(220, 132, 155))
    return im


FLOWERS = {(c, r): flower_sprite(c, r) for c in range(len(PINKS)) for r in [3, 5, 7]}


def flower(im, x, y, color, radius):
    sprite = FLOWERS[color, radius]
    im.paste(sprite, (round(x-sprite.width/2), round(y-sprite.height/2)), sprite)


def branch(d, points, width):
    # 모서리를 부드럽게 다듬고 끝으로 갈수록 가지를 가늘게 만듭니다.
    path=points
    for _ in range(3):
        rounded=[path[0]]
        for a,b in zip(path,path[1:]):
            rounded.extend([(a[0]*.75+b[0]*.25,a[1]*.75+b[1]*.25),
                            (a[0]*.25+b[0]*.75,a[1]*.25+b[1]*.75)])
        path=rounded+[path[-1]]
    for i,(a,b) in enumerate(zip(path,path[1:])):
        thickness=max(2,round(width*(1-i/len(path))**1.2))
        d.line([a,b],fill=(107,84,80),width=thickness)
        r=thickness/2
        d.ellipse((a[0]-r,a[1]-r,a[0]+r,a[1]+r),fill=(107,84,80))



# 분홍빛 하늘과 원근감 있는 길. 바닥의 꽃잎은 처음부터 쌓여 있습니다.
rows = np.empty((H,1,3),dtype=np.uint8)
for c,values in enumerate([(255,255,251),(231,246,218),(239,243,231)]):
    rows[:,0,c]=np.interp(np.arange(H),[0,VANISH_Y,H],values)
BASE=Image.fromarray(rows).resize((W,H))
d=ImageDraw.Draw(BASE)
d.polygon([(0,920),(900,VANISH_Y),(CX,850),(250,H),(0,H)],fill=(140,163,113))
d.polygon([(W,920),(1060,VANISH_Y),(CX,850),(1710,H),(W,H)],fill=(147,167,119))
d.polygon([(900,VANISH_Y),(1060,VANISH_Y),(W,H),(0,H)],fill=(248,218,230))
d.line([(900,VANISH_Y),(0,H)],fill=(221,199,199),width=5)
d.line([(1060,VANISH_Y),(W,H)],fill=(221,199,199),width=5)

# 길 가장자리를 따라 나무가 소실점까지 이어지도록 14쌍을 배치합니다.
DISTANT_RNG=np.random.default_rng(2607)
DISTANT_TREE=Image.new("RGBA",(1000,1250))
back_d=ImageDraw.Draw(DISTANT_TREE)
branch(back_d,[(160,1230),(240,950),(280,690),(430,480),(700,310),(940,220)],42)
branch(back_d,[(280,690),(180,470),(60,310)],24)
branch(back_d,[(430,480),(550,270),(570,80)],22)
branch(back_d,[(240,950),(480,740),(770,620)],20)
for _ in range(2400):
    angle=DISTANT_RNG.uniform(0,math.tau);radius=math.sqrt(DISTANT_RNG.random())
    x=510+math.cos(angle)*radius*480
    y=335+math.sin(angle)*radius*300
    flower(DISTANT_TREE,x,y,int(DISTANT_RNG.integers(0,5)),int(DISTANT_RNG.choice([3,5])))

DISTANT_ROOTS=[]
for depth in reversed(range(14)):
    scale=.83*(.77**depth)
    root_y=VANISH_Y+500*scale
    # 먼 나무는 하늘색에 조금 섞어 가까운 나무와 구분합니다.
    haze=.12+.48*(1-scale)
    tinted=Image.blend(DISTANT_TREE.convert("RGB"),Image.new("RGB",DISTANT_TREE.size,(255,243,246)),haze).convert("RGBA")
    tinted.putalpha(DISTANT_TREE.getchannel("A"))
    small=tinted.resize((max(1,round(1000*scale)),max(1,round(1250*scale))),Image.Resampling.LANCZOS)
    for side in [-1,1]:
        root_x=CX+side*(90+850*scale)
        sprite=small if side==-1 else small.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        origin_x=160 if side==-1 else 840
        BASE.paste(sprite,(round(root_x-origin_x*scale),round(root_y-1230*scale)),sprite)
        DISTANT_ROOTS.append((root_x,root_y,scale,side))

# 길에는 멀수록 작은 꽃잎을 깔고 앞쪽으로 갈수록 크게 표현합니다.
for _ in range(4500):
    depth=RNG.random()**.55
    y=VANISH_Y+depth*(H-VANISH_Y)
    half=80+depth*(W/2-80)
    x=RNG.uniform(CX-half,CX+half)
    petal(d,x,y,int(RNG.integers(0,5)),RNG.uniform(0,math.tau),size=2+depth*11,landed=True)

TREE_LAYERS=[]
BLOSSOMS=[]
for side in [-1,1]:
    layer=Image.new("RGBA",(W,H));td=ImageDraw.Draw(layer)
    def xy(points):
        return [(x if side==-1 else W-x,y) for x,y in points]
    branch(td,xy([(-40,1320),(100,1080),(180,790),(250,560),(435,380),(660,240),(940,130)]),62)
    branch(td,xy([(180,790),(100,580),(40,380),(-80,220)]),37)
    branch(td,xy([(250,560),(500,530),(720,430),(920,360)]),30)
    branch(td,xy([(435,380),(370,200),(280,30)]),27)
    branch(td,xy([(660,240),(720,100),(900,-80)]),19)
    branch(td,xy([(100,1080),(340,900),(510,730),(680,650)]),27)
    for center_x,center_y,rx,ry,count in [(200,160,800,260,3000),(100,410,430,340,1800),(590,120,550,235,2200)]:
        for _ in range(count):
            angle=RNG.uniform(0,math.tau);radius=math.sqrt(RNG.random())
            x=center_x+math.cos(angle)*radius*rx
            y=center_y+math.sin(angle)*radius*ry
            if side==1:x=W-x
            if not (-30<x<W+30 and -30<y<790):continue
            color=int(RNG.integers(0,5));size=int(RNG.choice([3,5,7],p=[.2,.5,.3]))
            flower(layer,x,y,color,size)
            if 80<x<W-80 and 120<y<720:
                BLOSSOMS.append((x,y,color,side))
    # 길 위로 뻗은 안쪽 가지에도 꽃송이를 채워 꽃 터널을 이어줍니다.
    for _ in range(850):
        u=RNG.random()
        x=420+u*500+RNG.normal(0,42)
        y=535-u*185+RNG.normal(0,35)
        if side==1:x=W-x
        color=int(RNG.integers(0,5))
        flower(layer,x,y,color,int(RNG.choice([3,5])))
        BLOSSOMS.append((x,y,color,side))
    TREE_LAYERS.append((side,layer))

# 떨어지는 꽃잎은 양쪽 수관에서 출발하고 길에 닿으면 그 자리에 남습니다.
FALLING=[]
for side in [-1,1]:
    candidates=[b for b in BLOSSOMS if b[3]==side]
    for index in RNG.choice(len(candidates),160,replace=False):
        x,y,color,_=candidates[index]
        release=RNG.uniform(.1,8)
        floor=RNG.uniform(1000,H-40)
        speed=RNG.uniform(105,165)
        phase=RNG.uniform(0,math.tau)
        x+=math.sin(release*.6)*side*3
        FALLING.append((x,y,color,side,release,floor,speed,phase,RNG.uniform(12,21)))


def render(t):
    img=BASE.copy()
    for side,layer in TREE_LAYERS:
        img.paste(layer,(round(math.sin(t*.6)*side*3),0),layer)
    d=ImageDraw.Draw(img)
    for x,y,color,side,release,floor,speed,phase,size in FALLING:
        age=t-release
        if age<0:continue
        flight=(floor-y)/speed
        travel=min(age,flight)
        px=x-side*24*travel+34*(math.sin(travel*1.1+phase)-math.sin(phase))
        py=y+travel*speed
        petal(d,px,py,color,phase+travel*.9,size=size,landed=age>=flight)
    d.text((CX,1270),"C H E R R Y   B L O S S O M",font=font(32),
           fill=(137,79,109),anchor="mm",stroke_width=2,stroke_fill=(255,238,245))
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "output/cherry-blossom.mp4")
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
