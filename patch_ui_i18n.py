#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_ui_i18n.py —— 把 play_gui.py 的 UI 中文字面量换成 t("key")

用法:
    py patch_ui_i18n.py              # 生成 play_gui_i18n.py（不动原文件）
    py patch_ui_i18n.py --inplace    # 直接改 play_gui.py（先自行备份）

原理: 用 tokenize 逐个取出 Python 字符串字面量，把它「解码后的文本」和
i18n/ui.zh.json 的 value 比对——所以源码里写 "▶ 点击…" 还是 "\u25b6 点击…"
都能命中。f-string 走 FSTRINGS 表。

跑完打印未命中清单。未命中 = 引擎里那句话改过措辞，需要人工看一眼；
脚本不会瞎猜、不会动没把握的行。
"""
import ast
import io
import json
import os
import sys
import tokenize

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "play_gui.py")
DST = os.path.join(ROOT, "play_gui_i18n.py")
ZH = os.path.join(ROOT, "i18n", "ui.zh.json")

FSTRINGS = {
    'f"槽 {i}"': 't("save.slot_n", i=i)',
    'f"已存档到槽 {i}"': 't("toast.saved_slot", i=i)',
    'f"已读取槽 {i}"': 't("toast.loaded_slot", i=i)',
}
FSTRING_KEYS = {"save.slot_n", "toast.saved_slot", "toast.loaded_slot"}

IMPORT_LINE = "from i18n import t, set_lang\n"


def splice(src, edits):
    """按 (start,end) 行列坐标替换，从后往前，避免坐标位移。跨行字符串不动。"""
    lines = src.splitlines(keepends=True)
    for (sr, sc), (er, ec), new in sorted(edits, reverse=True):
        if sr != er:
            continue
        line = lines[sr - 1]
        lines[sr - 1] = line[:sc] + new + line[ec:]
    return "".join(lines)


def main():
    if not os.path.exists(SRC):
        sys.exit("找不到 play_gui.py，请在 text_engine 目录下运行。")
    with open(ZH, encoding="utf-8") as f:
        zh = json.load(f)
    rev = {v: k for k, v in zh.items() if "{" not in v}

    src = open(SRC, encoding="utf-8").read()

    fhit = []
    for a, b in FSTRINGS.items():
        if a in src:
            src = src.replace(a, b)
            fhit.append(a)

    hit, edits = [], []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.STRING:
            continue
        try:
            val = ast.literal_eval(tok.string)
        except Exception:
            continue
        if isinstance(val, str) and val in rev:
            key = rev[val]
            edits.append((tok.start, tok.end, f't("{key}")'))
            hit.append(key)
    src = splice(src, edits)

    if "from i18n import" not in src:
        lines = src.splitlines(keepends=True)
        idx = max((i for i, l in enumerate(lines)
                   if l.startswith("import ") or l.startswith("from ")), default=0)
        lines.insert(idx + 1, IMPORT_LINE)
        src = "".join(lines)

    dst = SRC if "--inplace" in sys.argv else DST
    open(dst, "w", encoding="utf-8").write(src)

    covered = set(hit) | {k for k in FSTRING_KEYS
                          if any(FSTRINGS[a] for a in fhit)}
    miss = sorted(set(zh) - set(hit) - FSTRING_KEYS)

    print(f"已写出 {os.path.basename(dst)}")
    print(f"字符串命中 {len(set(hit))} 条｜f-string 命中 {len(fhit)}/{len(FSTRINGS)} 条")
    if miss:
        print("\n未命中（请手动核对这几句在 play_gui.py 里的写法）：")
        for k in miss:
            print(f"  {k:24} = {zh[k]!r}")
    print("\n运行：")
    print("  PowerShell:  $env:CHENGZAI_LANG='ja'; py play_gui_i18n.py game.json")
    print("  cmd:         set CHENGZAI_LANG=ja && py play_gui_i18n.py game.json")


if __name__ == "__main__":
    main()
