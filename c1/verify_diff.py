#!/usr/bin/env python3
"""验证「立绘常驻 + 任务区局刷」的省电效果 —— 纯逻辑，不需要真机。

模拟 ai-desk-card 的 _compute_diff：前帧 vs 后帧做差 → 脏矩形 bbox。
两种方案对比：
  A. 单窗口全刷：每次任务变化都推整屏（1072×1448 4bpp = 775 KB）
  B. 分层局刷：立绘一次全刷常驻，之后只推任务区脏矩形（DU|RECT）

跑法：python3 verify_diff.py
"""
from __future__ import annotations
from PIL import Image, ImageChops

W, H = 1072, 1448
FRAME_BYTES = W * H // 2          # 4bpp：2 像素/字节
AVATAR_W = int(W * 0.42)          # 立绘占左 42%
TASK_X = AVATAR_W                 # 任务区起点

# 任务区里文字实际占用的范围（从 y=100 到 y=1000，x 从任务区起点+margin）
TASK_BBOX = (TASK_X + 28, 100, W - 28, 1000)


def make_frame(task_state: int) -> Image.Image:
    """构造一帧：左侧立绘区填固定图案（永不改变），右侧任务区随 state 变。"""
    img = Image.new("L", (W, H), 255)
    # 立绘区：固定的深色块代表彩色立绘（像素内容恒定）
    img.paste(90, (0, 0, AVATAR_W, H))
    # 任务区：白底 + 随 state 变化的两行"文字"（用深浅块模拟）
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    y = 200
    for i in range(4):
        if i < task_state:      # 已完成项：浅灰 + 划线
            d.rectangle((TASK_X + 40, y, TASK_X + 500, y + 20), fill=180)
        else:                   # 未完成：深色
            d.rectangle((TASK_X + 40, y, TASK_X + 700, y + 20), fill=20)
        y += 150
    # 进展条随 state 增长
    d.rectangle((TASK_X + 40, 1200, TASK_X + 40 + task_state * 120, 1240), fill=0)
    return img


def diff_region(a: Image.Image, b: Image.Image):
    """复刻 ai-desk-card _compute_diff 的核心：difference → getbbox。"""
    bbox = ImageChops.difference(a, b).getbbox()
    if bbox is None:
        return None, 0
    x0, y0, x1, y1 = bbox
    area = (x1 - x0) * (y1 - y0)
    return bbox, area


def main():
    print("=" * 62)
    print(f"C1 屏 {W}×{H} · 全帧 4bpp = {FRAME_BYTES/1024:.0f} KB")
    print("=" * 62)

    prev = make_frame(0)
    total_full = 0
    total_region = 0
    pushes = 0

    for state in range(1, 5):
        cur = make_frame(state)
        bbox, area = diff_region(prev, cur)
        if bbox is None:
            continue
        pushes += 1
        region_bytes = area // 2
        total_full += FRAME_BYTES
        total_region += region_bytes
        pct = area / (W * H) * 100
        in_avatar = bbox[0] < AVATAR_W
        print(f"\n推进到第 {state} 项：")
        print(f"  脏矩形 bbox      = {bbox}")
        print(f"  覆盖范围         = {pct:.1f}% 全屏")
        print(f"  是否碰立绘区     = {'是 ❌' if in_avatar else '否 ✓（立绘 0 次重驱）'}")
        print(f"  全刷传输         = {FRAME_BYTES/1024:.0f} KB")
        print(f"  局刷传输(DU|RECT)= {region_bytes/1024:.1f} KB")
        print(f"  本次节省         = {(1-region_bytes/FRAME_BYTES)*100:.1f}%")
        prev = cur

    print("\n" + "=" * 62)
    print(f"累计 {pushes} 次任务推进：")
    print(f"  方案 A 全刷      = {total_full/1024:.0f} KB")
    print(f"  方案 B 分层局刷  = {total_region/1024:.1f} KB")
    print(f"  总节省           = {(1-total_region/total_full)*100:.1f}%")
    print("=" * 62)

    # 硬断言：立绘区在任意一次推进中都不能进脏矩形
    prev = make_frame(0)
    for state in range(1, 5):
        cur = make_frame(state)
        bbox, _ = diff_region(prev, cur)
        assert bbox[0] >= AVATAR_W, (
            f"第 {state} 次推进的脏矩形 bbox={bbox} 侵入了立绘区(x<{AVATAR_W})！"
        )
        prev = cur
    print("✓ 断言通过：4 次推进的脏矩形全部未触及立绘区")


if __name__ == "__main__":
    main()
