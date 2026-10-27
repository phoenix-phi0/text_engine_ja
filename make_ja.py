#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
play_gui.py -> play_gui_ja.py

引擎 UI 的日文化补丁。
用法:
    py make_ja.py
    py play_gui_ja.py game.json
"""
import sys, os

SRC = "play_gui.py"
DST = "play_gui_ja.py"

# 面向玩家的 UI 字符串。剧情 JSON 不动。
REPL = [
    ('"文字冒险"', '"テキストアドベンチャー"'),
    ('"\u25b6 点击 / 空格 跳过"', '"\u25b6 \u30af\u30ea\u30c3\u30af / \u30b9\u30da\u30fc\u30b9 \u3067\u30b9\u30ad\u30c3\u30d7"'),
    ('"\u25b6 点击 / 空格 / 回车 继续"', '"\u25b6 \u30af\u30ea\u30c3\u30af / \u30b9\u30da\u30fc\u30b9 / Enter \u3067\u9032\u3080"'),
    ('"重新开始（R）"', '"\u6700\u521d\u304b\u3089\uff08R\uff09"'),
    ('"(存档损坏)"', '"(\u30bb\u30fc\u30d6\u30c7\u30fc\u30bf\u7834\u640d)"'),
    ('"（无音频设备，已静音）"', '"\uff08\u30aa\u30fc\u30c7\u30a3\u30aa\u30c7\u30d0\u30a4\u30b9\u306a\u3057\u30fb\u6d88\u97f3\u4e2d\uff09"'),
    ('"存档" if self.ui_mode == "save" else "读档"',
     '"\u30bb\u30fc\u30d6" if self.ui_mode == "save" else "\u30ed\u30fc\u30c9"'),
    ('"点击槽位"', '"\u30b9\u30ed\u30c3\u30c8\u3092\u30af\u30ea\u30c3\u30af\u3057\u3066"'),
    ('"\u3000F5/F9 切换\u3000M 音乐"', '"\u3000F5/F9 \u5207\u66ff\u3000M \u97f3\u697d"'),
    ('"\u3000Esc 返回"', '"\u3000Esc \u623b\u308b"'),
    ('f"槽 {i}"', 'f"\u30b9\u30ed\u30c3\u30c8 {i}"'),
    ('"章节选择"', '"\u30c1\u30e3\u30d7\u30bf\u30fc\u9078\u629e"'),
    ('"已通关的章节可重新进入\u3000滚轮/↑↓ 滚动\u3000M 音乐"',
     '"\u30af\u30ea\u30a2\u6e08\u30c1\u30e3\u30d7\u30bf\u30fc\u306b\u518d\u5165\u5834\u3067\u304d\u307e\u3059\u3000\u30db\u30a4\u30fc\u30eb/\u2191\u2193 \u30b9\u30af\u30ed\u30fc\u30eb\u3000M \u97f3\u697d"'),
    ('"？？？（未解锁）"', '"\uff1f\uff1f\uff1f\uff08\u672a\u89e3\u653e\uff09"'),
    ('"关"', '"OFF"'),
    ('"开"', '"ON"'),
    ('"空"', '"\u306a\u3057"'),
    ('"BGM 已关闭"', '"BGM OFF"'),
    ('"BGM 已开启"', '"BGM ON"'),
    ('"已存档"', '"\u30bb\u30fc\u30d6\u3057\u307e\u3057\u305f"'),
    ('"存档失败"', '"\u30bb\u30fc\u30d6\u5931\u6557"'),
    ('f"已存档到槽 {i}"', 'f"\u30b9\u30ed\u30c3\u30c8 {i} \u306b\u30bb\u30fc\u30d6\u3057\u307e\u3057\u305f"'),
    ('f"已读取槽 {i}"', 'f"\u30b9\u30ed\u30c3\u30c8 {i} \u3092\u30ed\u30fc\u30c9\u3057\u307e\u3057\u305f"'),
    ('self._show_toast("音频不可用")',
     'self._show_toast("\u30aa\u30fc\u30c7\u30a3\u30aa\u304c\u5229\u7528\u3067\u304d\u307e\u305b\u3093")'),
    ('self._show_toast("无法跳转到该章节")',
     'self._show_toast("\u3053\u306e\u30c1\u30e3\u30d7\u30bf\u30fc\u306b\u306f\u79fb\u52d5\u3067\u304d\u307e\u305b\u3093")'),
    ('self._show_toast("该槽为空")',
     'self._show_toast("\u3053\u306e\u30b9\u30ed\u30c3\u30c8\u306f\u7a7a\u3067\u3059")'),
    ('self._show_toast("读档失败（存档可能已失效）")',
     'self._show_toast("\u30ed\u30fc\u30c9\u5931\u6557\uff08\u30bb\u30fc\u30d6\u30c7\u30fc\u30bf\u304c\u7121\u52b9\u306e\u53ef\u80fd\u6027\uff09")'),
]


def main():
    if not os.path.exists(SRC):
        print(f"找不到 {SRC}，请在 text_engine 目录下运行。")
        sys.exit(1)

    src = open(SRC, encoding="utf-8").read()

    hit, miss = 0, []
    for a, b in REPL:
        if a in src:
            src = src.replace(a, b)
            hit += 1
        else:
            miss.append(a)

    open(DST, "w", encoding="utf-8").write(src)

    print(f"已生成 {DST}   （替换 {hit}/{len(REPL)} 条）")
    if miss:
        print("未命中（引擎可能改过，需要手动看一眼）：")
        for m in miss:
            print("   ", m)
    print()
    print("运行：  py play_gui_ja.py game.json")


if __name__ == "__main__":
    main()
