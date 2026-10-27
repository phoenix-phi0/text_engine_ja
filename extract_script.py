#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_script.py —— 从 game.json 列出的所有章节里抽出可译词条

用法:
    py extract_script.py --stats    # 只统计工作量，不写文件
    py extract_script.py            # 生成 / 增量更新 i18n/ja/*.json

产物:
    i18n/ja/chapter5.json           待译表 {"s0.dlg3.say": "", ...}
    i18n/ja/_source/chapter5.json   同 key 的中文原文，对照用

留空 = 游戏里回落中文。所以可以一章一章、一行一行慢慢填，随时能跑。

增量规则:
    已填的译文不会被覆盖；剧本新增的行追加空词条；剧本删掉的行从表里移除，
    但若该行已有译文，会留档到 i18n/ja/_removed.json，不静默丢弃。
"""
import json
import os
import sys

from i18n import dump_chapter_keys

ROOT = os.path.dirname(os.path.abspath(__file__))
LANG = "ja"
OUT = os.path.join(ROOT, "i18n", LANG)
SRC_DIR = os.path.join(OUT, "_source")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    stats_only = "--stats" in sys.argv
    game = load(os.path.join(ROOT, "game.json"))
    chapters = game.get("chapters") or []

    total_keys = total_chars = total_todo = 0
    removed_all = {}
    missing = []

    for cf in chapters:
        path = os.path.join(ROOT, cf)
        if not os.path.exists(path):
            missing.append(cf)
            continue
        ch = load(path)
        fresh = dump_chapter_keys(ch)
        base = os.path.splitext(cf)[0]

        total_keys += len(fresh)
        total_chars += sum(len(v) for v in fresh.values())

        tgt = os.path.join(OUT, base + ".json")
        old = load(tgt) if os.path.exists(tgt) else {}

        merged = {k: old.get(k, "") for k in fresh}
        removed = {k: v for k, v in old.items()
                   if k not in fresh and isinstance(v, str) and v.strip()}
        if removed:
            removed_all[base] = removed
        total_todo += sum(1 for v in merged.values() if not v.strip())

        if not stats_only:
            dump(tgt, merged)
            dump(os.path.join(SRC_DIR, base + ".json"), fresh)

    if missing:
        print("! game.json 列了但目录里没有的章节：", ", ".join(missing))
    if removed_all and not stats_only:
        dump(os.path.join(OUT, "_removed.json"), removed_all)
        print("! 有已译词条对应的剧本行已不存在，留档在 i18n/ja/_removed.json")

    print(f"章节 {len(chapters) - len(missing)} 个｜可译词条 {total_keys} 条｜中文原文 {total_chars} 字")
    print(f"待译 {total_todo} 条（已译 {total_keys - total_todo} 条）")


if __name__ == "__main__":
    main()
