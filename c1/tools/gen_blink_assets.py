#!/usr/bin/env python3
"""
从新立绘生成放大立绘 + 睁/闭眼贴图。

  assistant.png     裁掉左右白边的瘦高版（650×1460），fitEnd 后人物更大且抬手指右
  eyes_open.png     睁眼贴图，原图像素，盖回时无缝
  eyes_closed.png   闭眼贴图：肤色圆角框盖掉眼睛 + 黑色闭眼弧线

新立绘（Anime_cel_shading_...2026-11-19.png, 1024×1536）眼睛标定：
  左眼深色 x=420~474 y=198~221 ；右眼 x=550~614 y=198~221
  眉毛下缘 y≈196，覆盖框上缘必须 >=198 才不误伤眉毛
  右眼外侧贴头发，覆盖框右缘 <=612
  眉眼间距极窄，故用窄羽化圆角框 + 采样肤色填充（不用邻域带）
"""
from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SRC = ASSETS / "Anime_cel_shading_illustration_2026-11-19T01-52-46.png"

# 人物包围盒 x=320~916 y=72~1498；裁 x=290~940 (650宽) 居中留边，y=50~1510
CROP = (290, 50, 940, 1510)          # 650×1460
# 眼睛框在原图 (412,195)-(618,228) → 裁剪图内相对坐标
EYE_BOX = (122, 145, 328, 178)       # 裁剪图内；贴图 206×33

# 眼睛覆盖区（贴图内局部坐标，圆角矩形）——上缘 y=3 避开眉毛(贴图y≈1)，下缘盖住睫毛
# (x0,y0,x1,y1, arc_start, arc_ctrl, arc_end)
EYES = [
    (52, 6, 91, 27,  (55, 18), (71, 26), (88, 17)),     # 左眼 x55~88 y8~24
    (114, 6, 154, 27,(117, 17), (134, 25), (151, 16)),  # 右眼 x118~150 y8~24
]
SKIN = (247, 216, 194)   # 采样自新图干净脸颊 (500,225)/(505,214)/(512,222) 均值


def bezier(p0, p1, p2, steps=28):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        pts.append(((1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t*t*p2[0],
                    (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t*t*p2[1]))
    return pts


def main():
    src = Image.open(SRC).convert("RGB")
    assert src.size == (1024, 1536), src.size

    slim = src.crop(CROP)
    slim.save(ASSETS / "assistant.png", optimize=True)
    print(f"assistant.png  {slim.size}")

    open_eye = slim.crop(EYE_BOX).copy()
    open_eye.save(ASSETS / "eyes_open.png", optimize=True)

    closed = open_eye.copy()

    # 1) 羽化蒙版：把眼白+睫毛+高光整块涂成肤色，边缘柔和过渡（避开眉毛）
    mask = Image.new("L", open_eye.size, 0)
    md = ImageDraw.Draw(mask)
    for x0, y0, x1, y1, *_ in EYES:
        md.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1))

    skin_layer = Image.new("RGB", open_eye.size, SKIN)
    closed = Image.composite(skin_layer, closed, mask)

    # 2) 画闭眼弧线（微弧下垂，末端一小撮睫毛）
    d = ImageDraw.Draw(closed)
    for *_, p0, p1, p2 in EYES:
        pts = bezier(p0, p1, p2)
        d.line(pts, fill=(45, 33, 30), width=2, joint="curve")
        ex, ey = pts[-1]
        d.line([(ex-1, ey), (ex+3, ey-4)], fill=(45, 33, 30), width=2)  # 外眼角睫毛
        d.line([(ex-2, ey+1), (ex+2, ey+1)], fill=(45, 33, 30), width=2)

    closed.save(ASSETS / "eyes_closed.png", optimize=True)
    print(f"eyes_open.png/eyes_closed.png  {open_eye.size}")

    cmp = Image.new("RGB", (open_eye.width*5, open_eye.height*10), "white")
    cmp.paste(open_eye.resize((open_eye.width*5, open_eye.height*5)), (0, 0))
    cmp.paste(closed.resize((closed.width*5, closed.height*5)), (0, open_eye.height*5))
    cmp.save("/tmp/eyes_compare.png")
    print("/tmp/eyes_compare.png  (上=睁 下=闭, 5倍)")


if __name__ == "__main__":
    main()
