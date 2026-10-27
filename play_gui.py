#!/usr/bin/env python3
"""
pygame 图形前端（新版引擎配套）
================================
复用 engine.py 的全部逻辑，提供：全屏背景、场景图、逐句对话推进、背景音乐、
音效、序列帧动画、章节标题、鼠标/键盘交互、存读档、重开。

用法：
    python play_gui.py                 # 跑 sample_game.json
    python play_gui.py prologue.json   # 跑你的剧情

操作：
    对话中：点击画面 / 空格 / 回车 / 点“▶ 继续” —— 推进到下一句
    选项时：鼠标点击，或数字键 1-9 选择
    F5 存档界面（6 槽）  F9 读档界面  C 章节选择  M 开关BGM  R 重新开始  Esc 退出/返回

【依赖的引擎接口】（若你改过 engine.py，请对照）
    Engine(game_data)                     构造
    engine.current_scene() -> dict
    engine.current_chapter_title() -> str|None
    engine.current_chapter_index() -> int|None
    engine.render() -> str                （非对话场景的正文；本前端也直接读 scene['text']）
    engine.dialogue_active() -> bool
    engine.dialogue_line() -> {'who','say'}|None
    engine.advance() -> bool
    engine.choices() -> [{'index','text','enabled','reason','choice'}]
    engine.choose(index)
    engine.is_ending() -> bool
    engine.media() -> {'image','background','music','music_changed','sfx','animations'}
    engine.interp.render_text(text) -> str
    engine.save(path) / Engine.load(game, path)
    engine.state (.inventory, .vars)

【素材目录】
    assets/img/     背景、场景图（png/jpg）
    assets/audio/   音乐、音效（wav/ogg/mp3）
    assets/anim/<name>/  序列帧动画：该目录下按文件名排序的 png 逐帧播放一遍
      —— play('x') 或 场景 animation:'x' 里的 'x' 对应 assets/anim/x/
    assets/video/   视频文件（mp4/webm 等）
      —— play('x.mp4') 或 animation:'x.mp4' 播放视频，播放时暂停剧情、盖住画面，
         播完自动继续，中途点击/空格/回车可跳过。需要 ffpyplayer；缺失则自动跳过。
"""
import os
import sys

os.environ.setdefault("SDL_VIDEO_CENTERED", "1")  # 窗口居中，避免标题栏开到屏幕外

import pygame

from engine import Engine, GameError, load_game

# 让程序优先使用“项目自带的 ffmpeg”，无需系统全局安装：
# 把项目根目录、根目录下的 bin/ 和 ffmpeg/bin/ 都加进 PATH，
# 这样 ffpyplayer 能找到放在项目里的 ffmpeg.exe（Windows）/ ffmpeg（Linux/Mac）。
_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, os.path.join(_ROOT, "bin"), os.path.join(_ROOT, "ffmpeg", "bin")):
    if os.path.isdir(_p):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")

try:
    from ffpyplayer.player import MediaPlayer
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False

ROOT = _ROOT
IMG_DIR = os.path.join(ROOT, "assets", "img")
AUD_DIR = os.path.join(ROOT, "assets", "audio")
ANIM_DIR = os.path.join(ROOT, "assets", "anim")
VIDEO_DIR = os.path.join(ROOT, "assets", "video")
VOICE_DIR = os.path.join(ROOT, "assets", "voice")
SAVE_PATH = os.path.join(ROOT, "save.json")  # 旧单槽（保留兼容）
SAVE_SLOTS = 6
SAVE_DIR = ROOT
def slot_path(i):
    return os.path.join(SAVE_DIR, f"save_{i}.json")
PROGRESS_PATH = os.path.join(ROOT, "progress.json")  # 已通关章节记录（章节选择解锁用）

DEFAULT_W, DEFAULT_H = 960, 800
MIN_W, MIN_H = 640, 560
MARGIN = 40

# 配色
BG = (18, 18, 22)
FG = (233, 233, 238)
DIM = (140, 140, 150)
TITLE_C = (255, 214, 120)
CHAPTER_C = (180, 170, 210)
SPEAKER_C = (150, 210, 240)
BTN = (44, 46, 58)
BTN_HOVER = (66, 70, 92)
BTN_DISABLED = (30, 30, 36)
BTN_TXT = (235, 235, 240)
BTN_TXT_OFF = (110, 110, 120)
STATUS_C = (150, 200, 170)
BOX_BG = (12, 12, 16)


def find_font(explicit=None):
    """返回一个可渲染中文的字体文件路径。"""
    if explicit and os.path.exists(explicit):
        return explicit
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return pygame.font.match_font(
        "notosanscjksc,microsoftyahei,pingfangsc,simhei,msgothic,hiraginosansgb"
    )


def wrap(text, font, max_w):
    """按像素宽度换行；中文逐字断行，兼顾 \\n 段落。"""
    lines = []
    for para in text.split("\n"):
        if para == "":
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if font.size(cur + ch)[0] <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


class Game:
    def __init__(self, game_data, font_path=None):
        pygame.init()
        try:
            pygame.mixer.init()
            self.audio = True
        except pygame.error:
            self.audio = False

        # 按屏幕可用尺寸夹住初始窗口，避免窗口比屏幕大、标题栏被顶出屏幕外
        try:
            info = pygame.display.Info()
            screen_w, screen_h = info.current_w, info.current_h
        except pygame.error:
            screen_w, screen_h = DEFAULT_W, DEFAULT_H
        # 留出任务栏/标题栏余量：宽最多屏幕的 95%，高最多屏幕的 88%
        win_w = min(DEFAULT_W, int(screen_w * 0.95)) if screen_w > 0 else DEFAULT_W
        win_h = min(DEFAULT_H, int(screen_h * 0.88)) if screen_h > 0 else DEFAULT_H
        self.WIN_W = max(win_w, MIN_W)
        self.WIN_H = max(win_h, MIN_H)
        self.screen = pygame.display.set_mode((self.WIN_W, self.WIN_H), pygame.RESIZABLE)
        self._recompute_layout()
        pygame.display.set_caption(game_data.get("title", "文字冒险"))

        fp = find_font(font_path)
        self._font_path = fp
        self._font_by_size = {}
        self.f_title = pygame.font.Font(fp, 32)
        self.f_body = pygame.font.Font(fp, 24)
        self.f_btn = pygame.font.Font(fp, 24)
        self.f_small = pygame.font.Font(fp, 20)
        self.f_chapter = pygame.font.Font(fp, 22)

        self.game_data = game_data
        self._img_cache = {}
        self._snd_cache = {}
        self._anim_cache = {}
        self._portrait_cache = {}
        self._voice_cache = {}
        self.voice_channel = None   # 专用语音声道（延迟到 mixer 就绪时取）
        # 说话人 -> 头像文件名（放 assets/img/）；写在剧情 JSON 顶层 "portraits"
        self.portraits = game_data.get("portraits", {})
        self.current_music = None
        self.muted = False           # BGM 静音开关（M 键切换）
        self._audit_bgm()

        # 当前呈现状态
        self.bg_surf = None          # 全屏背景（bg() 设的持续背景，或场景 image）
        self.buttons = []            # [(rect, index, enabled)]
        self.anim_frames = None      # 正在播的序列帧动画
        self.cutscene = False        # 当前序列帧是否为“过场模式”（阻塞+音轨）
        self.cutscene_channel = None
        self.anim_idx = 0
        self.anim_timer = 0
        self.ANIM_FPS = 12

        # 视频播放状态
        self.video = None            # 当前 MediaPlayer（None=没在播视频）
        self.video_surf = None       # 当前视频帧 surface

        # UI 模式："play"（正常游戏）/"save"（存档槽）/"load"（读档槽）/"chapters"（章节选择）
        self.ui_mode = "play"
        self.ch_scroll = 0  # 章节选择滚动偏移(像素)
        self.menu_buttons = []       # 覆盖层界面的可点区域 [(rect, action, payload, enabled)]
        self.toast = None            # 短暂提示文字
        self.toast_timer = 0
        self.cleared_chapters = self._load_progress()  # 已通关章节 id 集合

        self.new_game()

    # ---------------- 进度记录（章节解锁） ---------------- #
    def _load_progress(self):
        try:
            with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
                import json as _json
                return set(_json.load(f).get("cleared", []))
        except Exception:
            return set()

    def _save_progress(self):
        try:
            import json as _json
            with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                _json.dump({"cleared": sorted(self.cleared_chapters)}, f, ensure_ascii=False)
        except Exception:
            pass

    def _mark_chapter_cleared(self, cid):
        """把某章标记为已通关（进入下一章或到结局时调用），解锁章节选择。"""
        if cid and cid not in self.cleared_chapters:
            self.cleared_chapters.add(cid)
            self._save_progress()

    def _resolve_portrait_name(self, who, portrait=None, state=None):
        """按优先级链决定用哪张立绘文件：
          1) 行内 portrait（直接指定文件名，最高优先）
          2) 行内 state → 去 portraits[who] 状态表里查
          3) 角色 default（状态表里的 "default"）
          4) 旧格式：portraits[who] 直接是字符串（唯一立绘）
          5) 都没有 → None（不显示）
        兼容方案一（行内直接图）、方案二（状态表）与旧的字符串格式。
        """
        # 1) 行内直接指定
        if portrait:
            return portrait
        entry = self.portraits.get(who)
        if entry is None:
            return None
        # 4) 旧格式：字符串 = 唯一立绘
        if isinstance(entry, str):
            return entry
        # entry 是状态表（dict）
        if isinstance(entry, dict):
            # 2) 行内 state
            if state and state in entry:
                return entry[state]
            # 3) default
            if "default" in entry:
                return entry["default"]
            # 状态表非空但无 default：取任意一个，保证有图
            if entry:
                return next(iter(entry.values()))
        return None

    def get_portrait(self, who, portrait=None, state=None, target_h=None):
        """取说话人立绘（半身像，等比缩放、保留透明）。

        who/portrait/state 来自当前对话行；按 _resolve_portrait_name 的优先级选图。
        """
        name = self._resolve_portrait_name(who, portrait, state)
        if not name:
            return None
        if target_h is None:
            target_h = int(self.WIN_H * 0.42)   # 半身像高度约窗口的 42%
        key = (name, target_h)
        if key not in self._portrait_cache:
            path = os.path.join(IMG_DIR, name)
            try:
                im = pygame.image.load(path).convert_alpha()   # 保留透明通道
                w, h = im.get_size()
                scale = target_h / h
                im = pygame.transform.smoothscale(im, (max(1, int(w * scale)), target_h))
            except (pygame.error, FileNotFoundError):
                im = None
            self._portrait_cache[key] = im
        return self._portrait_cache[key]

    def _body_font(self, size):
        if size not in self._font_by_size:
            self._font_by_size[size] = pygame.font.Font(self._font_path, size)
        return self._font_by_size[size]

    def _blit_fit_line(self, text, color, x, y, max_w, base_size, min_size=14):
        """单行文字：先逐级缩小字号；到最小仍放不下则截断加省略号。返回行高。"""
        size = base_size
        while size > min_size:
            f = self._body_font(size)
            if f.size(text)[0] <= max_w:
                break
            size -= 1
        f = self._body_font(size)
        # 到最小字号仍超宽 -> 截断加省略号
        if f.size(text)[0] > max_w:
            while text and f.size(text + "…")[0] > max_w:
                text = text[:-1]
            text = text + "…"
        self.screen.blit(f.render(text, True, color), (x, y))
        return size + 8

    # ----------------------- 布局 / 缩放 ----------------------- #
    def _recompute_layout(self):
        """按当前窗口尺寸重算布局关键值。

        文字区（章节名+标题+正文+选项+状态栏）需要足够的竖直空间；
        窗口不高时，不再死守 58%，而是保证文字区至少有 MIN_TEXT_H 的高度，
        必要时把文字区顶端上移（背景相应变矮），避免标题/正文被挤出屏幕底部。
        """
        MIN_TEXT_H = 320
        top_by_ratio = int(self.WIN_H * 0.58)
        top_by_min = self.WIN_H - MIN_TEXT_H
        self.TEXT_TOP = max(0, min(top_by_ratio, top_by_min))
        self.TEXT_BOX_H = self.WIN_H - self.TEXT_TOP

    def on_resize(self, w, h):
        w = max(w, MIN_W)
        h = max(h, MIN_H)
        self.WIN_W, self.WIN_H = w, h
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self._recompute_layout()
        # 预缩放到旧窗口尺寸的图像缓存作废，让它们按新尺寸重新加载
        self._img_cache.clear()
        self._anim_cache.clear()
        self._portrait_cache.clear()
        self.anim_frames = None
        # 重新拉取当前场景的背景（按新尺寸缩放）
        self.sync_media(fire_sfx=False)

    # ----------------------- 资源 ----------------------- #
    def _load_img_fullscreen(self, name):
        if not name:
            return None
        # 缓存按 (文件名, 窗口尺寸) 存，窗口缩放后会重新按新尺寸生成
        key = (name, self.WIN_W, self.WIN_H)
        if key not in self._img_cache:
            path = os.path.join(IMG_DIR, name)
            try:
                img = pygame.image.load(path).convert()
                iw, ih = img.get_size()
                # 等比 cover：缩放到刚好盖住窗口，保持原比例不变形
                scale = max(self.WIN_W / iw, self.WIN_H / ih)
                sw, sh = max(1, int(iw * scale)), max(1, int(ih * scale))
                img = pygame.transform.smoothscale(img, (sw, sh))
                # 居中裁切出窗口大小
                surf = pygame.Surface((self.WIN_W, self.WIN_H))
                surf.blit(img, ((self.WIN_W - sw) // 2, (self.WIN_H - sh) // 2))
                img = surf
            except (pygame.error, FileNotFoundError):
                img = None
            self._img_cache[key] = img
        return self._img_cache[key]

    def play_sound(self, name):
        if not self.audio or not name:
            return
        if name not in self._snd_cache:
            path = os.path.join(AUD_DIR, name)
            try:
                self._snd_cache[name] = pygame.mixer.Sound(path)
            except (pygame.error, FileNotFoundError):
                self._snd_cache[name] = None
        snd = self._snd_cache[name]
        if snd:
            snd.play()

    def play_voice(self, name):
        """播放对话行配音（assets/voice/）。切句时先停上一句，用专用声道。"""
        if not self.audio:
            return
        # 取/建专用语音声道
        if self.voice_channel is None:
            try:
                self.voice_channel = pygame.mixer.Channel(5)
            except pygame.error:
                return
        # 无论有没有新语音，先停掉上一句
        self.voice_channel.stop()
        if not name:
            return
        if name not in self._voice_cache:
            path = os.path.join(VOICE_DIR, name)
            try:
                self._voice_cache[name] = pygame.mixer.Sound(path)
            except (pygame.error, FileNotFoundError):
                self._voice_cache[name] = None
        snd = self._voice_cache[name]
        if snd:
            self.voice_channel.play(snd)

    def _audit_bgm(self):
        """启动时检查剧情里用到的 BGM 文件是否都存在，缺的直接报出来。"""
        want = set()
        for ch in self.game_data.get("chapters", []):
            for sc in ch.get("scenes", []):
                m = sc.get("music")
                if isinstance(m, str):
                    want.add(m)
                elif isinstance(m, list):
                    for item in m:
                        v = item.get("music") if isinstance(item, dict) else item
                        if isinstance(v, str):
                            want.add(v)
        missing = [m for m in sorted(want)
                   if not os.path.exists(os.path.join(AUD_DIR, m))]
        if missing:
            print("[BGM] 以下音乐文件缺失（将无声）：")
            for m in missing:
                print(f"       {os.path.join(AUD_DIR, m)}")
        elif want:
            print(f"[BGM] {len(want)} 首音乐文件齐全。")

    def toggle_mute(self):
        """M 键：BGM 静音 / 恢复。"""
        if not self.audio:
            self._show_toast("音频不可用")
            return
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.music.stop()
            self._playing = None
            self._show_toast("BGM 已关闭")
        else:
            self._show_toast("BGM 已开启")
            # 恢复当前场景该播的曲子
            name = self.current_music
            if name:
                path = os.path.join(AUD_DIR, name)
                if os.path.exists(path):
                    try:
                        pygame.mixer.music.load(path)
                        pygame.mixer.music.set_volume(0.5)
                        pygame.mixer.music.play(-1)
                        self._playing = name
                    except (pygame.error, FileNotFoundError):
                        self._playing = None

    def set_music(self, name, changed):
        """由 media() 的 music/music_changed 驱动。

        不能只信 changed：跳章/读档/刚启动时，引擎里的 music 可能"逻辑上没变"，
        但 pygame 那边其实根本没在播。所以这里以"实际播放状态"为准。
        """
        if not self.audio:
            return
        if not name:
            if self.current_music is not None:
                pygame.mixer.music.stop()
                self.current_music = None
            return
        # 记住"当前该播哪首"，即使静音也要记，解除静音时才知道播什么
        self.current_music = name
        if self.muted:
            pygame.mixer.music.stop()
            return
        # 已经在播这首，且确实还在响 -> 不打断
        if pygame.mixer.music.get_busy() and getattr(self, "_playing", None) == name:
            return
        path = os.path.join(AUD_DIR, name)
        if not os.path.exists(path):
            print(f"[BGM] 文件不存在，跳过：{path}")
            self._playing = None
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.5)
            pygame.mixer.music.play(-1)
            self._playing = name
        except (pygame.error, FileNotFoundError) as e:
            print(f"[BGM] 播放失败：{path}  ({e})")
            self._playing = None

    _VIDEO_EXT = (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".ogv")

    def is_video(self, name):
        return name.lower().endswith(self._VIDEO_EXT)

    def start_video(self, name):
        """播放 assets/video/<name> 视频；缺库或缺文件则忽略（不阻塞剧情）。"""
        path = os.path.join(VIDEO_DIR, name)
        if not HAS_VIDEO or not os.path.exists(path):
            return
        self.stop_video()
        try:
            self.video = MediaPlayer(path)
            self.video_surf = None
        except Exception:
            self.video = None

    def stop_video(self):
        if self.video is not None:
            try:
                self.video.close_player()
            except Exception:
                pass
        self.video = None
        self.video_surf = None

    def video_playing(self):
        return self.video is not None

    def update_video(self):
        """抽取一帧视频；返回 False 表示播放结束。"""
        if self.video is None:
            return False
        frame, val = self.video.get_frame()
        if val == "eof":
            self.stop_video()
            return False
        if frame is not None:
            img, t = frame
            w, h = img.get_size()
            buf = bytes(img.to_bytearray()[0])
            try:
                surf = pygame.image.frombuffer(buf, (w, h), "RGB")
                self.video_surf = pygame.transform.smoothscale(surf, (self.WIN_W, self.WIN_H))
            except Exception:
                pass
        return True

    _AUDIO_EXT = (".ogg", ".wav", ".mp3", ".flac")

    def _find_audio(self, name):
        """在 assets/audio/ 下找与动画同名的音轨（任意支持的扩展名）；无则 None。"""
        for ext in self._AUDIO_EXT:
            p = os.path.join(AUD_DIR, name + ext)
            if os.path.exists(p):
                return name + ext
        return None

    def start_anim(self, name):
        """播放 assets/anim/<name>/ 下的序列帧。

        若 assets/audio/ 下有同名音轨（name.ogg/.wav/...），则进“过场模式”：
        全屏、暂停剧情、同步播放音轨、播完或点击/空格跳过。
        否则为普通非阻塞覆盖层动画。
        """
        if name not in self._anim_cache:
            frames = []
            d = os.path.join(ANIM_DIR, name)
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.lower().endswith((".png", ".jpg", ".jpeg")):
                        try:
                            im = pygame.image.load(os.path.join(d, fn)).convert_alpha()
                            im = pygame.transform.smoothscale(im, (self.WIN_W, self.WIN_H))
                            frames.append(im)
                        except (pygame.error, FileNotFoundError):
                            pass
            self._anim_cache[name] = frames
        frames = self._anim_cache[name]
        if not frames:
            return
        self.anim_frames = frames
        self.anim_idx = 0
        self.anim_timer = 0
        # 过场模式：有同名音轨则阻塞+播音轨
        audio = self._find_audio(name)
        self.cutscene = bool(audio)
        if audio:
            self._play_cutscene_audio(audio)

    def _play_cutscene_audio(self, name):
        """过场音轨用专用声道（6）播放，便于跳过时单独停。"""
        if not self.audio:
            return
        if getattr(self, "cutscene_channel", None) is None:
            try:
                self.cutscene_channel = pygame.mixer.Channel(6)
            except pygame.error:
                return
        if name not in self._snd_cache:
            path = os.path.join(AUD_DIR, name)
            try:
                self._snd_cache[name] = pygame.mixer.Sound(path)
            except (pygame.error, FileNotFoundError):
                self._snd_cache[name] = None
        snd = self._snd_cache[name]
        if snd:
            self.cutscene_channel.play(snd)

    def cutscene_playing(self):
        return getattr(self, "cutscene", False) and self.anim_frames is not None

    def stop_cutscene(self):
        """跳过/结束过场：停动画、停音轨。"""
        self.anim_frames = None
        self.cutscene = False
        if self.audio and getattr(self, "cutscene_channel", None) is not None:
            self.cutscene_channel.stop()

    # ----------------------- 媒体同步 ----------------------- #
    def sync_media(self, fire_sfx=True):
        """读 engine.media()，更新背景/音乐，触发音效与动画。"""
        m = self.engine.media()
        # 背景：优先持续背景 background，其次场景级 image
        bg_name = m.get("background") or m.get("image")
        self.bg_surf = self._load_img_fullscreen(bg_name)
        # 音乐
        self.set_music(m.get("music"), m.get("music_changed", False))
        # 音效
        if fire_sfx:
            for s in m.get("sfx", []):
                self.play_sound(s)
        # 动画（取最后一个触发的）：视频扩展名走视频，否则走序列帧
        anims = m.get("animations", [])
        if anims:
            name = anims[-1]
            if self.is_video(name):
                self.start_video(name)
            else:
                self.start_anim(name)

    def _speak_current_line(self):
        """播放当前对话行的配音（若有）。切句会先停上一句。"""
        if self.engine.dialogue_active():
            ln = self.engine.dialogue_line()
            self.play_voice(ln.get("voice"))
        else:
            # 对话结束/非对话场景：停掉残留语音
            self.play_voice(None)

    # ----------------------- 流程 ----------------------- #
    def new_game(self):
        self.engine = Engine(self.game_data)
        self.anim_frames = None
        self._last_chapter = self.engine.current_chapter()
        self.sync_media()
        self._speak_current_line()

    def _track_progress(self):
        """章节变化时把上一章标记为已通关；到结局时把当前章也标记。"""
        cur = self.engine.current_chapter()
        last = getattr(self, "_last_chapter", None)
        if last and cur != last:
            self._mark_chapter_cleared(last)
        self._last_chapter = cur
        if self.engine.is_ending():
            self._mark_chapter_cleared(cur)

    def advance_or_nothing(self):
        """对话推进；若已在选项阶段则忽略。"""
        if self.engine.dialogue_active():
            self.engine.advance()
            self.sync_media()
            self._speak_current_line()
            self._track_progress()

    def choose(self, index):
        opts = self.engine.choices()
        if not (0 <= index < len(opts)) or not opts[index]["enabled"]:
            return
        self.play_sound(opts[index]["choice"].get("sound"))
        try:
            self.engine.choose(index)
        except GameError:
            return
        self.sync_media()
        self._speak_current_line()
        self._track_progress()

    def jump_to_chapter(self, start_scene):
        """章节选择：跳到某章开头。"""
        try:
            self.engine.jump_to_scene(start_scene)
            self.anim_frames = None
            self._last_chapter = self.engine.current_chapter()
            self.sync_media(fire_sfx=False)
            self._speak_current_line()
        except Exception:
            self._show_toast("无法跳转到该章节")

    # ---------------- 多存档槽 ---------------- #
    def slot_info(self, i):
        """读取某槽的元信息，供界面显示；空槽返回 None。"""
        import json as _json
        p = slot_path(i)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = _json.load(f)
            return {
                "chapter": d.get("_chapter", ""),
                "scene_title": d.get("_scene_title", ""),
                "time": d.get("_time", ""),
            }
        except Exception:
            return {"chapter": "(存档损坏)", "scene_title": "", "time": ""}

    def save_to_slot(self, i):
        import json as _json, time as _time
        try:
            # 用引擎自带 save 生成基本数据，再补元信息写回
            self.engine.save(slot_path(i))
            with open(slot_path(i), "r", encoding="utf-8") as f:
                d = _json.load(f)
            d["_chapter"] = self.engine.current_chapter_title() or ""
            sc = self.engine.current_scene()
            d["_scene_title"] = sc.get("title", "")
            d["_time"] = _time.strftime("%m-%d %H:%M")
            with open(slot_path(i), "w", encoding="utf-8") as f:
                _json.dump(d, f, ensure_ascii=False, indent=2)
            self._show_toast(f"已存档到槽 {i}")
        except Exception:
            self._show_toast("存档失败")

    def load_from_slot(self, i):
        p = slot_path(i)
        if not os.path.exists(p):
            self._show_toast("该槽为空")
            return False
        try:
            self.engine = Engine.load(self.game_data, p)
            self.anim_frames = None
            self.sync_media(fire_sfx=False)
            self._speak_current_line()
            self._show_toast(f"已读取槽 {i}")
            return True
        except Exception:
            self._show_toast("读档失败（存档可能已失效）")
            return False

    def _show_toast(self, text):
        self.toast = text
        self.toast_timer = 1600  # 毫秒

    # ----------------------- 渲染 ----------------------- #
    def render(self):
        self.screen.fill(BG)

        # 视频模式：全屏视频盖住一切，只提示跳过
        if self.video_playing():
            if self.video_surf:
                self.screen.blit(self.video_surf, (0, 0))
            hint = self.f_small.render("▶ 点击 / 空格 跳过", True, DIM)
            self.screen.blit(hint, (self.WIN_W - hint.get_width() - 20, self.WIN_H - 34))
            pygame.display.flip()
            return

        # 过场动画模式：全屏序列帧盖住一切，只提示跳过（和视频一致）
        if self.cutscene_playing():
            self.screen.blit(self.anim_frames[self.anim_idx], (0, 0))
            hint = self.f_small.render("▶ 点击 / 空格 跳过", True, DIM)
            self.screen.blit(hint, (self.WIN_W - hint.get_width() - 20, self.WIN_H - 34))
            pygame.display.flip()
            return

        # 覆盖层界面：存档 / 读档 / 章节选择
        if self.ui_mode != "play":
            self._render_overlay()
            self._render_toast()
            pygame.display.flip()
            return

        # 背景铺满
        if self.bg_surf:
            self.screen.blit(self.bg_surf, (0, 0))
        else:
            pygame.draw.rect(self.screen, (28, 28, 34), (0, 0, self.WIN_W, self.TEXT_TOP))

        # 动画覆盖层（播放中盖住背景）
        if self.anim_frames:
            self.screen.blit(self.anim_frames[self.anim_idx], (0, 0))

        # 文字底板（半透明深色框，保证文字可读）—— 先画，之后立绘压在它上面
        box = pygame.Surface((self.WIN_W, self.TEXT_BOX_H), pygame.SRCALPHA)
        box.fill((*BOX_BG, 210))
        self.screen.blit(box, (0, self.TEXT_TOP))

        # ---- 说话人半身像：画在文字框之上（不被闷暗），但在标题/正文之下（不遮挡文字）----
        in_dialogue = self.engine.dialogue_active()
        speaker = None
        line_portrait = None
        line_state = None
        if in_dialogue:
            _ln = self.engine.dialogue_line()
            if _ln["who"] and _ln["who"] != "旁白":
                speaker = _ln["who"]
                line_portrait = _ln.get("portrait")
                line_state = _ln.get("state")
        portrait = self.get_portrait(speaker, line_portrait, line_state) if speaker else None
        portrait_w = 0
        if portrait:
            pw, ph = portrait.get_size()
            self.screen.blit(portrait, (MARGIN, self.WIN_H - ph))   # 底部贴窗口底升起
            portrait_w = pw

        y = self.TEXT_TOP + 18
        scene = self.engine.current_scene()

        max_w = self.WIN_W - 2 * MARGIN
        # 章节名
        ch = self.engine.current_chapter_title()
        if ch:
            idx = self.engine.current_chapter_index()
            if idx is None:
                num = ""
            elif idx == 0:
                num = "序章  "
            else:
                num = f"第{idx}章  "
            self._blit_fit_line(f"◆ {num}{ch}", CHAPTER_C, MARGIN, y, max_w, 22)
            y += 30

        # 场景标题
        title = scene.get("title", "")
        if title:
            self._blit_fit_line(title, TITLE_C, MARGIN, y, max_w, 32)
            y += 42

        ending = self.engine.is_ending()
        self.buttons = []
        mouse = pygame.mouse.get_pos()

        # ---- 先算交互区（选项/继续/结局），从窗口底部往上锚定 ----
        STATUS_Y = self.WIN_H - 40          # 状态栏所在行
        BTN_H, BTN_GAP = 46, 12
        if in_dialogue:
            # 对话中底部要放“继续”提示，正文下界留出一行的空间
            interact_top = STATUS_Y - 8
        elif ending:
            interact_top = STATUS_Y - (BTN_H + 12)
        else:
            n = len(self.engine.choices())
            interact_top = STATUS_Y - (n * (BTN_H + BTN_GAP)) - 8

        # ---- 正文 / 对话行：在 [y, interact_top) 内显示；放不下则自动缩小字号 ----
        speaker2 = None
        if in_dialogue:
            ln = self.engine.dialogue_line()
            who, say = ln["who"], ln["say"]
            if who and who != "旁白":
                speaker2 = who
            body = say
        else:
            body = self.engine.interp.render_text(scene.get("text", ""))

        text_y = y
        # 文字向右缩进，避开半身像所占的左侧宽度
        text_left = MARGIN + portrait_w + 20 if portrait_w else MARGIN
        if speaker2:
            self.screen.blit(self.f_body.render(speaker2, True, SPEAKER_C), (text_left, text_y))
            text_y += 34

        avail_w = self.WIN_W - text_left - MARGIN
        avail_h = interact_top - 6 - text_y
        # 从正常字号往下试，直到整段文字的高度能放进 avail_h（有最小字号下限）
        size = 24
        while size >= 15:
            font = self._body_font(size)
            lh = size + 8
            lines = wrap(body, font, avail_w)
            if len(lines) * lh <= avail_h or size == 15:
                break
            size -= 1
        for line in lines:
            if text_y + lh > interact_top - 6:
                break
            self.screen.blit(font.render(line, True, FG), (text_left, text_y))
            text_y += lh

        # ---- 画交互区（用锚定好的 interact_top）----
        by = interact_top
        if in_dialogue:
            hint = self.f_small.render("▶ 点击 / 空格 / 回车 继续", True, DIM)
            self.screen.blit(hint, (self.WIN_W - hint.get_width() - MARGIN, self.WIN_H - 40))
        elif ending:
            self._draw_button("重新开始（R）", by, index=-1, enabled=True, mouse=mouse)
        else:
            for o in self.engine.choices():
                label = f"{o['index'] + 1}. {o['text']}"
                if not o["enabled"]:
                    label += f"   —— {o['reason']}"
                self._draw_button(label, by, o["index"], o["enabled"], mouse)
                by += BTN_H + BTN_GAP

        # 状态栏
        st = self.engine.state
        inv = "、".join(st.inventory) if st.inventory else "空"
        shown = {k: v for k, v in st.vars.items() if not k.startswith("_")}
        stat = "  ".join(f"{k}:{v}" for k, v in shown.items())
        bar = f"背包[{inv}]   {stat}   [F5存档 F9读档 F7章节 M音乐{'关' if self.muted else '开'}]"
        self.screen.blit(self.f_small.render(bar, True, STATUS_C), (MARGIN, self.WIN_H - 40))

        if not self.audio:
            warn = self.f_small.render("（无音频设备，已静音）", True, DIM)
            self.screen.blit(warn, (self.WIN_W - warn.get_width() - MARGIN, self.WIN_H - 68))

        self._render_toast()
        pygame.display.flip()

    # ---------------- 覆盖层界面渲染 ---------------- #
    def _render_toast(self):
        if not self.toast:
            return
        surf = self.f_body.render(self.toast, True, (255, 255, 255))
        w, h = surf.get_size()
        pad = 16
        bx = (self.WIN_W - w) // 2 - pad
        by = self.WIN_H - 120
        box = pygame.Surface((w + pad * 2, h + pad), pygame.SRCALPHA)
        box.fill((0, 0, 0, 200))
        self.screen.blit(box, (bx, by))
        self.screen.blit(surf, (bx + pad, by + pad // 2))

    def _overlay_buttons(self):
        """计算当前覆盖层的可点区域列表 [(rect, action, payload, enabled)]，
        不依赖渲染——点击时实时调用，避免时序问题。"""
        btns = []
        if self.ui_mode in ("save", "load"):
            top = 130
            row_h = min((self.WIN_H - top - 60) // SAVE_SLOTS, 84)
            for i in range(1, SAVE_SLOTS + 1):
                y = top + (i - 1) * (row_h + 8)
                rect = pygame.Rect(MARGIN, y, self.WIN_W - 2 * MARGIN, row_h)
                btns.append((rect, self.ui_mode, i, True))
        elif self.ui_mode == "chapters":
            top = 130
            view_bottom = self.WIN_H - 30
            for idx, ch in enumerate(self.engine.chapters_list()):
                y = top + idx * 70 - self.ch_scroll
                rect = pygame.Rect(MARGIN, y, self.WIN_W - 2 * MARGIN, 60)
                unlocked = ch["id"] in self.cleared_chapters or idx == 0
                # 只有落在可视区内的按钮才可点击
                if rect.bottom > top - 10 and rect.top < view_bottom:
                    btns.append((rect, "chapter", ch["start"], unlocked))
                else:
                    btns.append((None, "chapter", ch["start"], unlocked))
        return btns

    def _ch_scroll_max(self):
        """章节列表可滚动的最大偏移。"""
        top = 130
        view_bottom = self.WIN_H - 30
        n = len(self.engine.chapters_list())
        content_h = n * 70
        visible_h = view_bottom - top
        return max(0, content_h - visible_h)

    def _render_overlay(self):
        # 半透明黑幕
        veil = pygame.Surface((self.WIN_W, self.WIN_H), pygame.SRCALPHA)
        veil.fill((8, 8, 12, 235))
        self.screen.blit(veil, (0, 0))
        mouse = pygame.mouse.get_pos()
        btns = self._overlay_buttons()

        if self.ui_mode in ("save", "load"):
            title = "存档" if self.ui_mode == "save" else "读档"
            self.screen.blit(self.f_title.render(title, True, FG), (MARGIN, 40))
            hint = "点击槽位" + ("存档" if self.ui_mode == "save" else "读档") + "　F5/F9 切换　M 音乐" + ("关" if self.muted else "开") + "　Esc 返回"
            self.screen.blit(self.f_small.render(hint, True, DIM), (MARGIN, 84))
            for rect, action, i, enabled in btns:
                info = self.slot_info(i)
                hover = rect.collidepoint(mouse)
                pygame.draw.rect(self.screen, (40, 40, 50) if hover else (28, 28, 36), rect, border_radius=8)
                pygame.draw.rect(self.screen, (90, 90, 110), rect, width=1, border_radius=8)
                self.screen.blit(self.f_btn.render(f"槽 {i}", True, FG), (rect.x + 16, rect.y + 10))
                if info:
                    line1 = f"{info['chapter']} · {info['scene_title']}"
                    self.screen.blit(self.f_small.render(line1, True, FG), (rect.x + 90, rect.y + 8))
                    self.screen.blit(self.f_small.render(info["time"], True, DIM), (rect.x + 90, rect.y + 34))
                else:
                    self.screen.blit(self.f_small.render("（空）", True, DIM), (rect.x + 90, rect.y + 18))

        elif self.ui_mode == "chapters":
            self.screen.blit(self.f_title.render("章节选择", True, FG), (MARGIN, 40))
            hint = "已通关的章节可重新进入　滚轮/↑↓ 滚动　M 音乐" + ("关" if self.muted else "开") + "　Esc 返回"
            self.screen.blit(self.f_small.render(hint, True, DIM), (MARGIN, 84))
            top = 130
            view_bottom = self.WIN_H - 30
            # 裁剪：只在可视区内绘制，避免画到标题/提示上
            clip_prev = self.screen.get_clip()
            self.screen.set_clip(pygame.Rect(0, top - 10, self.WIN_W, view_bottom - (top - 10)))
            chapters = self.engine.chapters_list()
            for (rect, action, start, unlocked), (idx, ch) in zip(btns, enumerate(chapters)):
                if rect is None:
                    continue  # 滚动出可视区，不绘制
                hover = rect.collidepoint(mouse) and unlocked
                base = (20, 20, 24) if not unlocked else ((40, 40, 50) if hover else (28, 28, 36))
                pygame.draw.rect(self.screen, base, rect, border_radius=8)
                pygame.draw.rect(self.screen, (90, 90, 110) if unlocked else (50, 50, 58), rect, width=1, border_radius=8)
                num = f"第{idx}章" if idx > 0 else "序章"
                col = FG if unlocked else (80, 80, 90)
                self.screen.blit(self.f_btn.render(num, True, col), (rect.x + 16, rect.y + 16))
                name = ch["title"] if unlocked else "？？？（未解锁）"
                self.screen.blit(self.f_body.render(name, True, col), (rect.x + 130, rect.y + 14))
            self.screen.set_clip(clip_prev)
            # 滚动条指示（内容超出时）
            smax = self._ch_scroll_max()
            if smax > 0:
                track_x = self.WIN_W - 14
                track_top = top
                track_h = view_bottom - top
                pygame.draw.rect(self.screen, (40, 40, 48), (track_x, track_top, 5, track_h), border_radius=3)
                total = len(chapters) * 70
                thumb_h = max(30, int(track_h * (track_h / total)))
                thumb_y = track_top + int((track_h - thumb_h) * (self.ch_scroll / smax))
                pygame.draw.rect(self.screen, (110, 110, 130), (track_x, thumb_y, 5, thumb_h), border_radius=3)


    def _draw_button(self, text, y, index, enabled, mouse):
        rect = pygame.Rect(MARGIN, y, self.WIN_W - 2 * MARGIN, 46)
        hover = rect.collidepoint(mouse) and enabled
        color = BTN_HOVER if hover else (BTN if enabled else BTN_DISABLED)
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        txt_c = BTN_TXT if enabled else BTN_TXT_OFF
        self.screen.blit(self.f_btn.render(text, True, txt_c), (rect.x + 16, rect.y + 10))
        self.buttons.append((rect, index, enabled))

    # ----------------------- 主循环 ----------------------- #
    def update_anim(self, dt):
        if not self.anim_frames:
            return
        self.anim_timer += dt
        if self.anim_timer >= 1000 / self.ANIM_FPS:
            self.anim_timer = 0
            self.anim_idx += 1
            if self.anim_idx >= len(self.anim_frames):
                if getattr(self, "cutscene", False):
                    self.stop_cutscene()   # 过场播完：停动画+音轨
                else:
                    self.anim_frames = None   # 普通动画播完

    def _menu_action(self, action, payload):
        if action == "save":
            self.save_to_slot(payload)
            # 存完留在界面，方便看到"已存档"提示
        elif action == "load":
            if self.load_from_slot(payload):
                self.ui_mode = "play"
        elif action == "chapter":
            self.jump_to_chapter(payload)
            self.ui_mode = "play"

    def _click(self, pos):
        # 覆盖层界面（存档/读档/章节）：实时计算按钮区，不依赖上一帧渲染
        if self.ui_mode != "play":
            for rect, action, payload, enabled in self._overlay_buttons():
                if rect is None:
                    continue  # 滚动出可视区，不可点
                if rect.collidepoint(pos) and enabled:
                    self._menu_action(action, payload)
                    break
            return
        # 视频播放中：任意点击 = 跳过
        if self.video_playing():
            self.stop_video()
            return
        # 过场动画中：任意点击 = 跳过
        if self.cutscene_playing():
            self.stop_cutscene()
            return
        # 对话中：点画面任意处推进；点按钮区也算推进
        if self.engine.dialogue_active():
            self.advance_or_nothing()
            return
        for rect, index, enabled in self.buttons:
            if rect.collidepoint(pos) and enabled:
                if index == -1:
                    self.new_game()
                else:
                    self.choose(index)
                break

    def run(self):
        clock = pygame.time.Clock()
        running = True
        while running:
            dt = clock.tick(60)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.VIDEORESIZE:
                    self.on_resize(e.w, e.h)
                elif self.video_playing():
                    # 视频模式：只响应“跳过”和退出，屏蔽其它操作
                    if e.type == pygame.KEYDOWN and e.key in (
                        pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE
                    ):
                        self.stop_video()
                    elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                        self.stop_video()
                elif self.cutscene_playing():
                    # 过场动画模式：只响应“跳过”，屏蔽其它操作
                    if e.type == pygame.KEYDOWN and e.key in (
                        pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE
                    ):
                        self.stop_cutscene()
                    elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                        self.stop_cutscene()
                elif self.ui_mode != "play":
                    # 覆盖层界面：Esc 返回；F5/F9/C 可直接切换界面；点击由 _click 处理
                    if e.type == pygame.MOUSEWHEEL and self.ui_mode == "chapters":
                        # 滚轮滚动章节列表（e.y>0 上滚）
                        self.ch_scroll = max(0, min(self._ch_scroll_max(),
                                                    self.ch_scroll - e.y * 50))
                    elif e.type == pygame.KEYDOWN:
                        if e.key == pygame.K_ESCAPE:
                            self.ui_mode = "play"
                            self.toast = None
                        elif self.ui_mode == "chapters" and e.key == pygame.K_DOWN:
                            self.ch_scroll = min(self._ch_scroll_max(), self.ch_scroll + 60)
                        elif self.ui_mode == "chapters" and e.key == pygame.K_UP:
                            self.ch_scroll = max(0, self.ch_scroll - 60)
                        elif e.key == pygame.K_F5:
                            self.ui_mode = "save"; self.toast = None
                        elif e.key == pygame.K_F9:
                            self.ui_mode = "load"; self.toast = None
                        elif e.key == pygame.K_c or e.key == pygame.K_F7:
                            self.ui_mode = "chapters"; self.toast = None
                            self.ch_scroll = 0
                        elif e.key == pygame.K_m:
                            self.toggle_mute()
                        elif pygame.K_1 <= e.key <= pygame.K_9:
                            # 数字键快速选槽/章
                            btns = self._overlay_buttons()
                            k = e.key - pygame.K_1
                            if 0 <= k < len(btns):
                                r, action, payload, enabled = btns[k]
                                if enabled:
                                    self._menu_action(action, payload)
                    elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                        self._click(e.pos)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        running = False
                    elif e.key == pygame.K_m:
                        self.toggle_mute()
                    elif e.key == pygame.K_r:
                        self.new_game()
                    elif e.key == pygame.K_F5:
                        self.ui_mode = "save"      # 打开存档界面
                        self.toast = None
                    elif e.key == pygame.K_F9:
                        self.ui_mode = "load"      # 打开读档界面
                        self.toast = None
                    elif e.key == pygame.K_c or e.key == pygame.K_F7:
                        self.ui_mode = "chapters"  # 打开章节选择（C 或 F7）
                        self.ch_scroll = 0
                        self.toast = None
                    elif e.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.advance_or_nothing()
                    elif pygame.K_1 <= e.key <= pygame.K_9:
                        if not self.engine.dialogue_active():
                            self.choose(e.key - pygame.K_1)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self._click(e.pos)

            if self.video_playing():
                self.update_video()
            else:
                self.update_anim(dt)
            # toast 计时
            if self.toast:
                self.toast_timer -= dt
                if self.toast_timer <= 0:
                    self.toast = None
            self.render()
        pygame.quit()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "game.json")
    if not os.path.exists(path):
        print(f"找不到剧情文件：{path}")
        sys.exit(1)
    font = None
    if "--font" in sys.argv:
        i = sys.argv.index("--font")
        if i + 1 < len(sys.argv):
            font = sys.argv[i + 1]
    Game(load_game(path), font_path=font).run()


if __name__ == "__main__":
    main()
