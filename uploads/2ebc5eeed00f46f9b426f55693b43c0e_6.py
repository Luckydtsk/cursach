import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(5, 10))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

def box(x, y, w, h, text, fc="#f0f4ff", ec="#2f3b52", fs=11):
    FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.25,rounding_size=0.7",
        linewidth=1.8, edgecolor=ec, facecolor=fc,
    )
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.25,rounding_size=0.7",
        linewidth=1.8, edgecolor=ec, facecolor=fc,
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

def arrow(x1, y1, x2, y2):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle="->", mutation_scale=18, linewidth=2, color="#2f3b52",
        )
    )

cx = 50  # центр по X
bw, bh = 52, 9

# --- блоки сверху вниз (y убывает в matplotlib снизу вверх — ставим снизу вверх по координатам)
ys = [72, 58, 44, 30, 16]  # центры блоков по Y

box(cx - bw / 2, ys[0] - bh / 2, bw, bh, "Patches", fc="#fff8e6")
arrow(cx, ys[0] - bh / 2 - 1, cx, ys[1] + bh / 2 + 1)

box(cx - bw / 2, ys[1] - bh / 2, bw, bh, "Embedding", fc="#eaf2ff")
arrow(cx, ys[1] - bh / 2 - 1, cx, ys[2] + bh / 2 + 1)

# Encoder — чуть выше по высоте
enc_h = 11
box(cx - bw / 2, ys[2] - enc_h / 2, bw, enc_h,
    "Encoder blocks", fc="#e9f8ef")
arrow(cx, ys[2] - enc_h / 2 - 1, cx, ys[3] + bh / 2 + 1)

box(cx - bw / 2, ys[3] - bh / 2, bw, bh, "Linear head", fc="#fce8f6")
arrow(cx, ys[3] - bh / 2 - 1, cx, ys[4] + bh / 2 + 1)

box(cx - bw / 2, ys[4] - bh / 2, bw, bh, "Forecast", fc="#f5f5f5")

# Подписи сбоку / сверху
ax.text(cx + bw / 2 + 6, ys[2], "Encoder-only\narchitecture",
        ha="left", va="center", fontsize=10, fontweight="bold", color="#2f3b52")
ax.text(cx + bw / 2 + 6, ys[2] - 10,
        "Main building block:\nMulti-Head Self-Attention + FFN",
        ha="left", va="top", fontsize=9, style="italic", color="#444")

plt.tight_layout()
plt.savefig("patchtst_arch_vertical.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.show()