"""
文字冒险游戏引擎 —— 数据驱动核心
====================================

设计目标：引擎与剧情彻底分离。剧情写在一份数据（dict / JSON）里，
引擎负责：渲染文本、判断分支条件、执行效果、管理状态与背包、存读档。

依赖：仅标准库，Python 3.8+，可在任何环境直接运行。

【游戏数据格式】（见 sample_game.json）
{
  "title": "游戏名",
  "start": "起始场景id",
  "vars": {"hp": 12, "gold": 0},        # 初始状态变量
  "scenes": [
    {
      "id": "scene_id",
      "title": "可选标题",
      "on_enter": ["hp += 1"],           # 进入场景时执行的效果（每次进入都跑）
      "text": "正文，可用 {hp} 插值，也可写条件段落见下",
      "choices": [
        {
          "text": "选项文字，也支持 {gold} 插值",
          "goto": "目标场景id",
          "show_if": "has('钥匙')",       # 满足才显示该选项（可选）
          "enable_if": "gold >= 5",       # 满足才可选，否则灰掉（可选）
          "disabled_text": "你没有足够的金币",# 灰掉时的说明（可选）
          "effects": ["gold -= 5", "add('剑')"],  # 选择后执行（可选）
          "once": true,                   # 只能选一次（cid 稳定，可不写 id）
          "id": "buy_sword"               # once 建议显式给 id（便于脚本按 id 匹配）
        }
      ],
      "image": "vessels/core.png",        # 场景配图（可选，见下）
      "music": "bgm/shrine.mp3",          # 背景音乐（可选，见下）
      "sound": "sfx/bell.mp3",            # 进入场景时的一次性音效（可选）
      "animation": "anim/intro.webm",     # 进入场景时播放一次的动画片段（可选）
      "end": false                        # true 或没有任何“可选”项 => 结局
    }
  ]
}

【媒体字段：图片与音乐】
引擎本身不播放任何图形/音频，它只**管理“此刻该呈现什么”**，把结果通过 media()
交给前端（网页/GUI/终端预览）去实际显示或播放。这样保持“逻辑与呈现分离”。

  image  场景配图。可以是：
           - 字符串： "path/or/url.png"
           - 条件式： 和 text 一样，写成列表，元素是字符串或 {"if":条件,"image":"..."}，
                     命中的**第一个**生效（图片只取一张，不像文本那样拼接）。
         选项 choice 也可以带 "image"，一旦某选项设了图，选择后该图会覆盖场景图，
         直到进入下一个场景（用于“选择后立刻展示一张结果图”）。

  music  背景音乐，带“延续”语义：进入新场景时，如果 music 和正在播放的相同，
         **不重启**（音乐连续）；不同才切换；显式写 "music": null 表示停止音乐；
         不写这个字段表示“沿用上一首”（不打断）。music 同样支持条件式列表（取命中的第一个）。

  sound  进入场景时触发一次的音效（一次性，不循环）。选项的 effects 里也能触发音效：
         在效果代码里调用  sfx('sfx/hit.mp3')  即可（见内置函数）。

media() 返回：{"image": 当前图或None, "music": 当前应播放的曲或None,
              "music_changed": 本回合音乐是否发生切换(bool),
              "sfx": [本回合触发的音效列表],
              "animations": [本回合触发的动画片段列表]}

【条件表达式】求值为真/假，例：  hp > 0 and has('剑')
【效果语句】  可执行赋值与函数调用，例：  hp -= 10 ; add('金币', 3)
【文本插值】  {表达式} 会被求值后替换，例：  你还有 {hp} 点血。
【条件段落】  text 可以是一个列表，元素是字符串或 {"if": 条件, "text": "..."}，
             命中的段落按顺序拼接（自己在文本里加换行/空格控制排版）。

可用的内置函数（条件与效果里都能用）：
  has(item, n=1)   背包里是否至少有 n 个 item
  lacks(item)      背包里没有 item
  count(item)      背包里 item 的数量
  add(item, n=1)   往背包加 item
  remove(item, n=1)从背包移除 item
  visited(sid)     是否到过某场景
  roll(sides=6)    掷一个 1..sides 的骰子
  chance(p)        以概率 p(0~1) 返回 True
  sfx(path)        在 effects 里触发一次音效（选择该选项时播放）
  bg(path=None)    随时切换“持续背景图”，切了就一直保留到下次切换；bg() 或 bg(None) 清空。
                   可在 on_enter 或选项 effects 里调用。背景跨场景保留、进存档。
  play(path)       触发播放一段动画片段（一次性）。可在 on_enter 或选项 effects 里调用。
                   引擎只发指令、不阻塞、不记录；实际播放与是否挡住操作由前端决定。
  min max abs int len str  常用工具

【剧情组织：章节】（可选）
剧情可以按章节组织。两种方式二选一：
  A) 章节式：
     {
       "title": "...", "start": "...", "vars": {...},
       "chapters": [
         {"id": "ch1", "title": "第一章·浅参与", "scenes": [ ...场景... ]},
         {"id": "ch2", "title": "第二章·峰值",   "scenes": [ ...场景... ]}
       ]
     }
  B) 平铺式（旧格式，仍支持）：直接给顶层 "scenes": [...]。
章节式下所有场景会被摊平，**场景 id 需全局唯一**，goto 可跨章跳转（章节只是组织与
展示单位，不限制跳转）。引擎按场景所属章节自动显示章名，可用 current_chapter() 等查询。
进入哪一章由“当前在哪个场景”决定，无需手动切章。

【对话推进：dialogue】（可选，做视觉小说式逐句演出）
场景可以用 dialogue 取代/并存于 text，做成一行行推进的对话：
  "dialogue": [
    {"say": "那天的午后，和别的午后没有两样。"},          # who 缺省 = 旁白
    {"who": "宫司", "say": "……这次的事，你们都听好。", "bg": "bg/shamusho.png"},
    {"who": "主角", "say": "（他这个样子，我认得。）", "sfx": "sfx/heart.mp3"},
    {"if": "visited('xxx')", "who": "旁白", "say": "满足条件才出现的一行。"},
    {"who": "核心容器", "say": "……你来了。", "play": "anim/turn.webm"}
  ]
每行：who（缺省=旁白）、say（支持 {} 插值）、if（条件行，不满足则跳过）、
      以及行级媒体 bg/sfx/play（走到该行即触发，可同时多个；复用已有机制）。
推进方式（前端交互）：
  - dialogue_line() 取当前应显示的行 {who, say}；
  - 玩家点“继续” -> advance()，推进到下一有效行并触发其行级媒体；
    advance() 返回 False 表示对话走完，此时才 choices() 出选项。
  - dialogue_active() 判断是否还在对话中；对话中 choices() 返回空、is_ending() 为假。
只在场景末尾出选项（对话中途不分支）；要中途分岔就拆成多个场景用 goto。
无 dialogue、只有 text 的旧场景行为完全不变。

【变量持久化约定】（重要，见下方 exec_effects）
  * 普通名字的变量（hp / gold / goblin_hp ...）会写回状态、进存档。
  * 下划线开头的变量（_dmg / _tmp ...）是“临时量”，只在同一个选项的
    多条 effects 之间共享，不写回状态、不进存档。战斗里的中间值请用下划线。
  * 特殊控制变量 _goto：在效果里给它赋值可以覆盖该选项的 goto
    （用于战斗循环等动态跳转），例：  if goblin_hp <= 0: _goto = 'treasure'
    它同样是下划线临时量，不会污染状态。
"""

from __future__ import annotations

import copy
import json
import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BRACE_RE = re.compile(r"\{([^{}]+)\}")
# 用于静态校验：从 effect 字符串里扒出 _goto = 'xxx' / "xxx" 的字面目标
GOTO_LITERAL_RE = re.compile(r"""_goto\s*=\s*['"]([^'"]+)['"]""")


class GameError(Exception):
    """引擎运行期错误（多半是剧情数据里的表达式写错了）。"""


class GameDataError(GameError):
    """剧情数据静态校验错误（加载期就能发现的死链/错别字等）。"""


# --------------------------------------------------------------------------- #
# 运行时状态
# --------------------------------------------------------------------------- #
@dataclass
class State:
    current: str
    vars: Dict[str, Any] = field(default_factory=dict)
    inventory: List[str] = field(default_factory=list)
    visited: set = field(default_factory=set)
    used: set = field(default_factory=set)  # 已用掉的 once 选项 id
    music: Optional[str] = None             # 当前正在播放的背景音乐（用于延续判断/存档）
    scene_image: Optional[str] = None       # 由选项设置的、覆盖场景图的临时图（进入新场景即清空）
    background: Optional[str] = None         # 当前持续背景图，由 bg() 随时切换，跨场景保留、进存档
    line: int = 0                            # 当前对话行游标（指向 dialogue 里第几行；无对话的场景恒为 0）

    # 背包操作（供效果/条件里的 add/remove 调用）
    def add_item(self, item: str, n: int = 1) -> None:
        for _ in range(int(n)):
            self.inventory.append(item)

    def remove_item(self, item: str, n: int = 1) -> None:
        for _ in range(int(n)):
            if item in self.inventory:
                self.inventory.remove(item)


# --------------------------------------------------------------------------- #
# 表达式 / 效果解释器
# --------------------------------------------------------------------------- #
class Interpreter:
    """把状态变量暴露成命名空间，求值条件、执行效果、做文本插值。

    注意：这是给“你自己写的、可信的剧情文件”用的。namespace 里禁用了
    __builtins__，无法 import 或访问内建危险函数，但**不是**对抗恶意输入
    的沙箱。别跑陌生人的剧情文件。
    """

    #: 这些 key 不写回状态（都是内置工具函数）
    _HELPERS = {
        "has", "lacks", "count", "add", "remove", "visited",
        "roll", "chance", "sfx", "bg", "play", "min", "max", "abs", "int", "len", "str",
    }

    def __init__(self, state: State):
        self.state = state
        self.sfx_buffer: List[str] = []  # effects 里 sfx() 触发的音效，engine 每回合读取并清空
        self.anim_buffer: List[str] = []  # play() 触发的动画片段，engine 每回合读取并清空

    def _namespace(self) -> Dict[str, Any]:
        st = self.state
        ns: Dict[str, Any] = {}
        ns.update(st.vars)                 # 状态变量直接按名字暴露
        ns["__builtins__"] = {}            # 关掉内建，禁止 import 等
        ns["has"] = lambda item, n=1: st.inventory.count(item) >= n
        ns["lacks"] = lambda item: item not in st.inventory
        ns["count"] = lambda item: st.inventory.count(item)
        ns["add"] = st.add_item
        ns["remove"] = st.remove_item
        ns["visited"] = lambda sid: sid in st.visited
        ns["roll"] = lambda sides=6: random.randint(1, int(sides))
        ns["chance"] = lambda p: random.random() < p
        ns["sfx"] = lambda path: self.sfx_buffer.append(path)
        ns["play"] = lambda path: self.anim_buffer.append(path)

        def _set_bg(path=None):
            st.background = path
        ns["bg"] = _set_bg
        ns["min"] = min
        ns["max"] = max
        ns["abs"] = abs
        ns["int"] = int
        ns["len"] = len
        ns["str"] = str
        return ns

    def eval(self, expr: str) -> Any:
        try:
            return eval(expr, self._namespace())  # noqa: S307 (受控命名空间)
        except GameError:
            raise
        except Exception as e:  # noqa: BLE001
            raise GameError(f"条件/表达式求值失败: {expr!r} -> {e}") from e

    def _writeback(self, ns: Dict[str, Any]) -> None:
        """把命名空间里的“持久变量”写回状态。

        规则：跳过内建、工具函数、可调用对象，以及所有下划线开头的名字
        （下划线 = 临时量 / 控制信号，不进状态、不进存档）。
        """
        for k, v in ns.items():
            if k.startswith("_") or k in self._HELPERS or callable(v):
                continue
            self.state.vars[k] = v

    def exec_effects(self, codes: List[str]) -> Dict[str, Any]:
        """在**同一个**命名空间里连续执行一个选项的所有 effects。

        返回执行后的命名空间（供调用方读取 _goto 之类的控制信号）。
        这样多条 effects 之间可以共享 _dmg 等临时量，而临时量不会泄漏到状态里。
        """
        ns = self._namespace()
        for code in codes:
            try:
                exec(code, ns)  # noqa: S102 (受控命名空间)
            except GameError:
                raise
            except Exception as e:  # noqa: BLE001
                raise GameError(f"效果执行失败: {code!r} -> {e}") from e
        self._writeback(ns)
        return ns

    def interpolate(self, text: str) -> str:
        return BRACE_RE.sub(lambda m: str(self.eval(m.group(1))), text)

    def resolve_media(self, spec, key: str):
        """解析 image/music 这类“单值媒体”字段。

        spec 可以是：
          - None / 缺省          -> 返回 None（对 music 另有“沿用”语义，见 engine）
          - 字符串                -> 直接返回（支持 {} 插值，便于按变量拼路径）
          - 列表 [str | {'if':.., key:..}] -> 按顺序取**第一个命中**：带 if 的看条件，
                    纯字符串视为“无条件命中”（=兜底/默认，应写在列表**最后**）。
        key 是列表元素里存放值的键名（"image" 或 "music"）。
        （与 text 的差异：text 拼接所有命中段落，媒体只取第一个命中。）
        """
        if spec is None:
            return None
        if isinstance(spec, str):
            return self.interpolate(spec)
        if isinstance(spec, list):
            for b in spec:
                if isinstance(b, dict):
                    cond = b.get("if")
                    if cond is not None and not self.eval(cond):
                        continue
                    val = b.get(key)
                    return self.interpolate(val) if isinstance(val, str) else val
                else:
                    return self.interpolate(b)
            return None
        return spec

    def render_text(self, text) -> str:
        """text 可以是字符串，或 [字符串 | {'if':条件,'text':...}] 列表。"""
        blocks = text if isinstance(text, list) else [text]
        parts: List[str] = []
        for b in blocks:
            if isinstance(b, dict):
                cond = b.get("if")
                if cond is not None and not self.eval(cond):
                    continue
                s = b.get("text", "")
            else:
                s = b
            parts.append(self.interpolate(s))
        return "".join(parts)


# --------------------------------------------------------------------------- #
# 引擎
# --------------------------------------------------------------------------- #
class Engine:
    def __init__(self, game: Dict[str, Any], state: Optional[State] = None):
        self.game = game
        self.scenes: Dict[str, Dict[str, Any]] = {}
        # 场景 id -> 所属章节 id；章节顺序与标题
        self.scene_chapter: Dict[str, str] = {}
        self.chapter_order: List[str] = []
        self.chapter_titles: Dict[str, str] = {}
        self.chapter_first_scene: Dict[str, str] = {}  # 章 id -> 该章第一个场景 id

        # 两种组织方式，二选一：
        #   A) 章节式： game["chapters"] = [{id, title, scenes:[...]}, ...]
        #   B) 平铺式： game["scenes"] = [...]（旧格式，仍支持）
        # 章节式会把所有章节的场景摊平进 self.scenes（场景 id 需全局唯一），
        # 同时记录每个场景属于哪一章、以及章节的顺序与标题。
        raw_scenes: List[Dict[str, Any]] = []
        if game.get("chapters"):
            for ch in game["chapters"]:
                cid = ch["id"]
                if cid in self.chapter_titles:
                    raise GameDataError(f"章节 id 重复: {cid!r}")
                self.chapter_order.append(cid)
                self.chapter_titles[cid] = ch.get("title", cid)
                ch_scenes = ch.get("scenes", [])
                if ch_scenes:
                    self.chapter_first_scene[cid] = ch_scenes[0]["id"]
                for s in ch_scenes:
                    self.scene_chapter[s["id"]] = cid
                    raw_scenes.append(s)
        else:
            raw_scenes = game.get("scenes", [])

        for s in raw_scenes:
            if s["id"] in self.scenes:
                raise GameDataError(f"场景 id 重复: {s['id']!r}")
            self.scenes[s["id"]] = s
        if not self.scenes:
            raise GameDataError("游戏里没有任何场景。")

        # 加载期静态校验：死链、start 不存在等，一次性全部报出来
        self.validate()

        # 一回合内缓存当前场景的可见选项，避免同一回合内多次求值
        # （render / is_ending / choices / choose 会各调用一次，
        #  若 show_if 里用了 roll()/chance() 就会“闪烁”，缓存可消除该问题）
        self._choices_cache: Optional[List[Dict[str, Any]]] = None

        if state is None:
            start = game.get("start") or raw_scenes[0]["id"]
            if start not in self.scenes:
                raise GameDataError(f"起始场景不存在: {start!r}")
            self.state = State(current=start, vars=copy.deepcopy(game.get("vars", {})))
            self.interp = Interpreter(self.state)
            self._enter(start)
        else:
            self.state = state
            self.interp = Interpreter(self.state)

    # -- 静态校验 ---------------------------------------------------------- #
    def validate(self) -> None:
        """加载期检查剧情数据的静态错误，收集齐后一次性抛出。"""
        errors: List[str] = []

        start = self.game.get("start")
        if start is not None and start not in self.scenes:
            errors.append(f"start 指向不存在的场景: {start!r}")

        for sid, scene in self.scenes.items():
            for i, c in enumerate(scene.get("choices", [])):
                label = c.get("id", f"{sid}#{i}")
                # 1) 选项 goto 字面目标
                goto = c.get("goto")
                if goto is not None and goto not in self.scenes:
                    errors.append(f"[{label}] goto 指向不存在的场景: {goto!r}")
                # 2) effects 里 _goto = '字面量' 的目标
                for eff in c.get("effects", []):
                    for m in GOTO_LITERAL_RE.finditer(eff):
                        tgt = m.group(1)
                        if tgt not in self.scenes:
                            errors.append(
                                f"[{label}] effect 里 _goto 指向不存在的场景: {tgt!r}")

        if errors:
            raise GameDataError("剧情数据校验未通过：\n  - " + "\n  - ".join(errors))

    # -- 场景流转 ---------------------------------------------------------- #
    def _invalidate(self) -> None:
        self._choices_cache = None

    def _enter(self, sid: str) -> None:
        if sid not in self.scenes:
            raise GameError(f"跳转到不存在的场景: {sid!r}")
        self.state.current = sid
        self.state.scene_image = None      # 上一场景里由选项设置的临时图，进入新场景即失效
        self._invalidate()
        scene = self.scenes[sid]
        # on_enter 里若设了 _goto 会被忽略（仅选项的 effects 支持动态跳转）
        self.interp.exec_effects(scene.get("on_enter", []))
        # 进场音效：一次性，压进本回合 sfx 缓冲（media() 会读取并清空）
        snd = self.interp.resolve_media(scene.get("sound"), "sound")
        if snd:
            self.interp.sfx_buffer.append(snd)
        # 进场动画：一次性，压进本回合 anim 缓冲
        anim = self.interp.resolve_media(scene.get("animation"), "animation")
        if anim:
            self.interp.anim_buffer.append(anim)
        self.state.visited.add(sid)
        # 对话游标复位：定位到首个满足条件的对话行，并触发该行的行级媒体
        self.state.line = 0
        self._seek_valid_line(forward=True)
        self._fire_line_media()

    # -- 对话推进 ---------------------------------------------------------- #
    def _dialogue(self) -> List[Dict[str, Any]]:
        """当前场景的对话行列表；没有则空列表。"""
        return self.current_scene().get("dialogue", []) or []

    def _line_ok(self, ln: Dict[str, Any]) -> bool:
        """对话行的 if 条件是否满足（无 if 视为满足）。"""
        cond = ln.get("if")
        return cond is None or bool(self.interp.eval(cond))

    def _seek_valid_line(self, forward: bool = True) -> None:
        """把游标停在一个满足条件的行上；若越过末尾则停在 len（表示对话结束）。

        从当前 self.state.line 开始向前找第一个 if 满足的行。
        """
        dlg = self._dialogue()
        i = self.state.line
        while i < len(dlg) and not self._line_ok(dlg[i]):
            i += 1
        self.state.line = i

    def _fire_line_media(self) -> None:
        """触发当前对话行上的行级媒体（bg / sfx / play），可同时多个。"""
        dlg = self._dialogue()
        if 0 <= self.state.line < len(dlg):
            ln = dlg[self.state.line]
            if "bg" in ln:
                self.state.background = self.interp.resolve_media(ln["bg"], "bg")
            snd = ln.get("sfx")
            if snd:
                self.interp.sfx_buffer.append(self.interp.interpolate(snd))
            anim = ln.get("play")
            if anim:
                self.interp.anim_buffer.append(self.interp.interpolate(anim))

    def dialogue_active(self) -> bool:
        """当前场景是否处于“对话尚未走完”的状态（还有行要显示）。"""
        return self.state.line < len(self._dialogue())

    def dialogue_line(self) -> Optional[Dict[str, Any]]:
        """返回当前应显示的对话行 {who, say}；对话已走完或无对话时返回 None。

        who 缺省视为“旁白”；say 会做 {} 插值。
        """
        dlg = self._dialogue()
        if not (0 <= self.state.line < len(dlg)):
            return None
        ln = dlg[self.state.line]
        return {
            "who": ln.get("who", "旁白"),
            "say": self.interp.interpolate(ln.get("say", "")),
            "portrait": ln.get("portrait"),   # 方案一：行内直接指定立绘文件（最高优先）
            "state": ln.get("state"),         # 方案二：行内状态名，去 portraits[who] 查
            "voice": ln.get("voice"),         # 该行台词的配音文件（放 assets/voice/），可选
        }

    def advance(self) -> bool:
        """推进到下一行有效对话。返回 True 表示还有对话行可显示，
        False 表示对话已走完（该进入选项阶段）。

        无对话的场景：始终返回 False（直接进选项阶段）。
        """
        dlg = self._dialogue()
        if not dlg:
            return False
        if self.state.line >= len(dlg):
            return False
        # 从下一行开始找下一个满足条件的行
        self.state.line += 1
        self._seek_valid_line(forward=True)
        self._invalidate()  # 对话状态变了，选项缓存作废
        if self.dialogue_active():
            self._fire_line_media()
            return True
        return False

    def current_scene(self) -> Dict[str, Any]:
        return self.scenes[self.state.current]

    # -- 章节 -------------------------------------------------------------- #
    def current_chapter(self) -> Optional[str]:
        """当前场景所属章节 id；平铺式（无章节）返回 None。"""
        return self.scene_chapter.get(self.state.current)

    def current_chapter_title(self) -> Optional[str]:
        cid = self.current_chapter()
        return self.chapter_titles.get(cid) if cid else None

    def current_chapter_index(self) -> Optional[int]:
        """当前章在 chapter_order 里的序号（从 0 起）；无章节返回 None。"""
        cid = self.current_chapter()
        return self.chapter_order.index(cid) if cid in self.chapter_order else None

    def chapters_list(self) -> List[Dict[str, str]]:
        """返回章节列表：[{'id','title','start'}...]，供章节选择用。"""
        out = []
        for cid in self.chapter_order:
            out.append({
                "id": cid,
                "title": self.chapter_titles.get(cid, cid),
                "start": self.chapter_first_scene.get(cid),
            })
        return out

    def jump_to_scene(self, scene_id: str) -> None:
        """跳到指定场景开头（用于章节选择）。触发进入逻辑。"""
        self._enter(scene_id)

    def render(self) -> str:
        scene = self.current_scene()
        title = scene.get("title")
        head = ""
        ch_title = self.current_chapter_title()
        if ch_title:
            idx = self.current_chapter_index()
            num = f"第{idx + 1}章 " if idx is not None else ""
            head = f"◆ {num}{ch_title} ◆\n"

        # 对话模式：若本场景有 dialogue 且尚未走完，显示当前对话行
        if self._dialogue() and self.dialogue_active():
            ln = self.dialogue_line()
            who = ln["who"]
            say = ln["say"]
            # 旁白不加名字前缀；角色行加“名字：”
            body = say if who == "旁白" else f"{who}：{say}"
        else:
            body = self.interp.render_text(scene.get("text", ""))

        if title:
            return f"{head}【{title}】\n{body}"
        return f"{head}{body}" if head else body

    def media(self) -> Dict[str, Any]:
        """返回当前该呈现的媒体，供前端渲染。引擎不亲自播放。

        返回 {
          "image": 当前图片路径或 None,
          "music": 当前应播放的背景音乐或 None,
          "music_changed": 本次音乐是否发生切换（True 时前端才需要重新加载/换曲）,
          "sfx": [本回合触发的一次性音效路径...],
        }

        音乐延续语义：
          - 场景没写 music 字段  -> 沿用上一首（music_changed=False）
          - music 与当前相同      -> 不重启（music_changed=False）
          - music 不同           -> 切换（music_changed=True）
          - music 显式为 null     -> 停止（music_changed=True, music=None）
        图片优先级：选项设置的临时图(scene_image) > 场景自身 image。
        """
        scene = self.current_scene()

        # -- 图片 --
        if self.state.scene_image is not None:
            image = self.state.scene_image
        else:
            image = self.interp.resolve_media(scene.get("image"), "image")

        # -- 音乐（区分“字段缺省=沿用”与“显式 null=停止”）--
        music_changed = False
        if "music" in scene:
            new_music = self.interp.resolve_media(scene.get("music"), "music")
            if new_music != self.state.music:
                self.state.music = new_music
                music_changed = True
        # 字段缺省则 self.state.music 保持不变（沿用）

        # -- 音效：读取并清空本回合缓冲 --
        sfx = list(self.interp.sfx_buffer)
        self.interp.sfx_buffer.clear()

        # -- 动画片段：读取并清空本回合缓冲（一次性播放，引擎只发指令）--
        animations = list(self.interp.anim_buffer)
        self.interp.anim_buffer.clear()

        return {
            "image": image,
            "background": self.state.background,
            "music": self.state.music,
            "music_changed": music_changed,
            "sfx": sfx,
            "animations": animations,
        }

    def is_ending(self) -> bool:
        """结局判定：显式 end=true，或**没有任何可选（enabled）选项**。

        注意：只被 enable_if 灰掉的选项不算“可选”，因此“全部灰掉”的场景
        会被判为结局，而不是让玩家卡在一堆点不动的选项上（软锁）。
        """
        scene = self.current_scene()
        # 对话尚未走完：既不出选项、也不算结局，还在“讲话”
        if self._dialogue() and self.dialogue_active():
            return False
        if scene.get("end"):
            return True
        return not any(c["enabled"] for c in self.choices())

    # -- 选项 -------------------------------------------------------------- #
    def choices(self) -> List[Dict[str, Any]]:
        """返回当前可见选项：[{index, cid, text, enabled, reason, choice}]。

        结果在同一回合内缓存；进入新场景或做出选择后自动失效。
        """
        if self._choices_cache is not None:
            return self._choices_cache

        # 对话尚未走完时不出选项（前端应显示“继续”来 advance）
        if self._dialogue() and self.dialogue_active():
            self._choices_cache = []
            return []

        scene = self.current_scene()
        out: List[Dict[str, Any]] = []
        for i, c in enumerate(scene.get("choices", [])):
            # cid 用原始下标，稳定：不受 show_if 隐藏、once 消失影响，适合脚本按 id 匹配
            cid = c.get("id", f"{scene['id']}#{i}")
            if c.get("once") and cid in self.state.used:
                continue
            if "show_if" in c and not self.interp.eval(c["show_if"]):
                continue
            enabled = True
            if "enable_if" in c and not self.interp.eval(c["enable_if"]):
                enabled = False
            out.append({
                "index": len(out),
                "cid": cid,
                "text": self.interp.interpolate(c.get("text", "")),
                "enabled": enabled,
                "reason": c.get("disabled_text", "（现在无法选择）"),
                "choice": c,
            })
        self._choices_cache = out
        return out

    def choose(self, index: int) -> None:
        opts = self.choices()  # 用缓存：正是玩家当前看到的那一份列表
        if not (0 <= index < len(opts)):
            raise GameError(f"选项序号越界: {index}")
        entry = opts[index]
        if not entry["enabled"]:
            raise GameError(entry["reason"])
        c = entry["choice"]

        # 一个选项的所有 effects 在同一命名空间里执行，临时量（下划线）可共享
        ns = self.interp.exec_effects(c.get("effects", []))
        if c.get("once"):
            self.state.used.add(entry["cid"])

        # 动态跳转：effect 里显式设了“非空”的 _goto 才覆盖选项的 goto。
        # None 或空串都视为“无覆盖”，回退到 c["goto"]（场景 id 恒为非空字符串）。
        goto = ns.get("_goto")
        target = goto if (goto is not None and goto != "") else c.get("goto")
        if target is not None:
            self._enter(target)          # _enter 内部会 _invalidate（并清空 scene_image）
        else:
            # 留在原场景：若该选项带图，用它覆盖场景图（展示“选择的结果画面”）
            if "image" in c:
                self.state.scene_image = self.interp.resolve_media(c["image"], "image")
            self._invalidate()           # 状态已变，刷新选项缓存

    # -- 存读档 ------------------------------------------------------------ #
    def save(self, path: str) -> None:
        # 存档里剔除下划线临时/控制变量，保持存档干净
        clean_vars = {k: v for k, v in self.state.vars.items()
                      if not k.startswith("_")}
        data = {
            "current": self.state.current,
            "vars": clean_vars,
            "inventory": self.state.inventory,
            "visited": sorted(self.state.visited),
            "used": sorted(self.state.used),
            "music": self.state.music,          # 保留当前背景音乐，读档后不打断
            "background": self.state.background, # 保留当前持续背景图
            "line": self.state.line,             # 保留对话游标，读档回到同一行
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, game: Dict[str, Any], path: str) -> "Engine":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        state = State(
            current=d["current"],
            vars=d.get("vars", {}),
            inventory=d.get("inventory", []),
            visited=set(d.get("visited", [])),
            used=set(d.get("used", [])),
            music=d.get("music"),
            background=d.get("background"),
            line=d.get("line", 0),
        )
        # 构造引擎会摊平章节并建立 self.scenes；用它来校验存档场景是否存在
        engine = cls(game, state=state)
        if state.current not in engine.scenes:
            raise GameError(f"存档里的当前场景在本剧情中不存在: {state.current!r}")
        return engine


def load_game(path: str) -> Dict[str, Any]:
    """从 JSON 文件读取游戏数据。

    支持两种 chapters 写法：
      1) 内联（老格式）：chapters 是章节对象列表 [{id,title,scenes}, ...]，直接用。
      2) 分文件（新格式）：chapters 是文件名列表 ["prologue.json", "chapter1.json"]，
         主文件放全局配置（title/start/portraits/vars 等），每个章节文件各放一章。
         引擎按顺序加载每个章节文件、把它们的章节合并进来。
    章节文件本身也是 JSON，其 chapters 里放一个或多个章节对象；
    也允许章节文件顶层直接就是一个章节对象（含 id/scenes）。
    """
    import os
    with open(path, "r", encoding="utf-8") as f:
        game = json.load(f)

    chapters = game.get("chapters")
    # 新格式：chapters 是字符串（文件名）列表
    if isinstance(chapters, list) and chapters and all(isinstance(c, str) for c in chapters):
        base = os.path.dirname(os.path.abspath(path))
        # 章节文件按顺序在这些目录里找：scenario/ 优先，其次主文件同级（兼容旧布局）
        search_dirs = [os.path.join(base, "scenario"), base]

        def _resolve(fname):
            if os.path.isabs(fname):
                return fname
            for d in search_dirs:
                p = os.path.join(d, fname)
                if os.path.exists(p):
                    return p
            looked = "、".join(os.path.join(d, fname) for d in search_dirs)
            raise GameError(f"章节文件 {fname!r} 找不到。已查找：{looked}")

        merged = []
        for fname in chapters:
            fpath = _resolve(fname)
            with open(fpath, "r", encoding="utf-8") as cf:
                cdata = json.load(cf)
            if isinstance(cdata, dict) and cdata.get("chapters"):
                # 章节文件里用 chapters 数组包着一个/多个章节
                merged.extend(cdata["chapters"])
            elif isinstance(cdata, dict) and (cdata.get("scenes") or cdata.get("id")):
                # 章节文件顶层直接就是一个章节对象
                merged.append(cdata)
            elif isinstance(cdata, list):
                # 章节文件顶层直接是章节对象列表
                merged.extend(cdata)
            else:
                raise GameError(f"章节文件 {fname!r} 格式无法识别（需含 chapters/scenes/id）")
        game["chapters"] = merged
    return game
