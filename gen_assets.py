#!/usr/bin/env python3
"""
生成占位资源：场景图片(PNG) + 环境音/音效(WAV)。
这些只是让引擎开箱即跑的占位素材，你可以把 assets/ 下的文件替换成自己的。

用法：python gen_assets.py
"""
import math
import os
import struct
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, "assets", "img")
AUD_DIR = os.path.join(ROOT, "assets", "audio")
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(AUD_DIR, exist_ok=True)

W, H = 960, 360
SR = 44100


# --------------------------- 图片 --------------------------- #
def gradient(top, bottom):
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(H):
        t = y / (H - 1)
        arr[y, :] = [int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)]
    return Image.fromarray(arr, "RGB")


def label(img, text, color=(255, 255, 255)):
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    bb = d.textbbox((0, 0), text, font=font)
    d.text(((W - (bb[2] - bb[0])) / 2, H - 70), text, font=font, fill=color)
    return img


SCENES = {
    # 场景id : (顶色, 底色, 英文标签, 装饰函数名)
    "forest":   ((30, 60, 40), (10, 25, 18), "FOREST"),
    "creek":    ((40, 70, 90), (12, 30, 45), "CREEK"),
    "cave":     ((25, 22, 30), (5, 4, 8), "CAVE"),
    "door":     ((45, 35, 28), (18, 14, 10), "IRON DOOR"),
    "guard":    ((70, 25, 25), (25, 8, 8), "GOBLIN!"),
    "treasure": ((90, 78, 30), (40, 32, 8), "TREASURE"),
    "dead":     ((15, 15, 18), (2, 2, 3), "GAME OVER"),
}


def decorate(img, sid):
    d = ImageDraw.Draw(img, "RGBA")
    rng = np.random.default_rng(hash(sid) % (2**32))
    if sid in ("forest", "creek"):
        for _ in range(60):
            x = rng.integers(0, W)
            h = rng.integers(60, 220)
            d.line([(x, H), (x, H - h)], fill=(0, 0, 0, 80), width=rng.integers(2, 8))
    if sid == "cave" or sid == "door":
        d.ellipse([W / 2 - 120, 40, W / 2 + 120, 260], fill=(0, 0, 0, 120))
    if sid == "guard":
        d.ellipse([W / 2 - 60, 120, W / 2 + 60, 260], fill=(20, 200, 60, 200))
        d.ellipse([W / 2 - 30, 160, W / 2 - 10, 180], fill=(255, 255, 255, 255))
        d.ellipse([W / 2 + 10, 160, W / 2 + 30, 180], fill=(255, 255, 255, 255))
    if sid == "treasure":
        for _ in range(120):
            x, y = rng.integers(0, W), rng.integers(60, H - 80)
            r = rng.integers(2, 6)
            d.ellipse([x, y, x + r, y + r], fill=(255, 230, 120, 200))
    return img


for sid, (top, bot, text) in SCENES.items():
    im = gradient(top, bot)
    im = decorate(im, sid)
    im = label(im, text)
    im.save(os.path.join(IMG_DIR, f"{sid}.png"))
print(f"[img] {len(SCENES)} 张场景图 -> {IMG_DIR}")


# --------------------------- 音频 --------------------------- #
def write_wav(name, samples):
    """samples: float32 数组，范围[-1,1]，单声道。"""
    data = np.clip(samples, -1, 1)
    pcm = (data * 32767).astype("<i2").tobytes()
    path = os.path.join(AUD_DIR, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def tone(freq, dur, vol=0.2, decay=False):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    s = np.sin(2 * math.pi * freq * t)
    if decay:
        s *= np.exp(-t / (dur * 0.35))
    return s * vol


def pad(freqs, dur, vol=0.15):
    """多个正弦叠成的柔和 pad，首尾做淡入淡出以便无缝循环。"""
    out = np.zeros(int(SR * dur))
    for f in freqs:
        out += tone(f, dur, vol / len(freqs))
    # 轻微颤音
    t = np.linspace(0, dur, len(out), endpoint=False)
    out *= 1 + 0.05 * np.sin(2 * math.pi * 0.3 * t)
    fade = int(SR * 0.15)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


# 平静环境（C 大调三音）
write_wav("ambient.wav", pad([130.81, 164.81, 196.00], 6.0, vol=0.18))
# 紧张战斗（小二度不谐 + 低音）
write_wav("tension.wav", pad([98.00, 103.83, 146.83], 4.0, vol=0.20))
# 胜利短曲（琶音）
vic = np.concatenate([tone(f, 0.22, 0.25, decay=True)
                      for f in [261.63, 329.63, 392.00, 523.25]])
write_wav("victory.wav", vic)
# 点击音效
write_wav("click.wav", tone(880, 0.06, 0.25, decay=True))
# 攻击音效（噪声爆发）
n = np.random.default_rng(0).standard_normal(int(SR * 0.18))
n *= np.exp(-np.linspace(0, 1, len(n)) * 6) * 0.3
write_wav("hit.wav", n)
print(f"[audio] 5 个音频 -> {AUD_DIR}")
print("完成。")
