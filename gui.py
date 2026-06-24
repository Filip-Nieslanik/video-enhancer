"""Desktop front-end for Video Enhancer.

A single-window Tk app: drop a clip in, pick a preset (or open the
custom panel), watch it run. All heavy lifting lives in core; this file
only deals with widgets, layout and marshalling worker-thread events
back onto the Tk main loop.
"""
from __future__ import annotations

import os
import json
import queue
import threading
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAVE_DND = True
except Exception:
    HAVE_DND = False

from core import VideoProcessor, EnhanceConfig, VideoInfo, Cancelled, BASE_DIR

# Two palettes. The active one is copied into module globals by
# apply_theme() so the widget code can keep referring to plain BG/FG/etc.
DARK = dict(
    BG="#15151f", BG_CARD="#1e1e2e", BG_CARD2="#262638", BG_INPUT="#0f0f17",
    FG="#e7e7ef", FG_MUTED="#9a9ab0", FG_DIM="#62627a",
    ACCENT="#8b5cf6", ACCENT_HI="#a78bfa", ACCENT_LO="#6d28d9",
    GREEN="#34d399", RED="#f87171", BORDER="#2e2e44")
LIGHT = dict(
    BG="#f4f4f7", BG_CARD="#ffffff", BG_CARD2="#ece9f5", BG_INPUT="#f1eff8",
    FG="#1c1c28", FG_MUTED="#5a5a72", FG_DIM="#9a9ab0",
    ACCENT="#7c3aed", ACCENT_HI="#8b5cf6", ACCENT_LO="#6d28d9",
    GREEN="#059669", RED="#dc2626", BORDER="#dcdae6")

# placeholders; real values filled in by apply_theme()
BG = BG_CARD = BG_CARD2 = BG_INPUT = FG = FG_MUTED = FG_DIM = ""
ACCENT = ACCENT_HI = ACCENT_LO = GREEN = RED = BORDER = ""


# Accent options (base, hover, pressed). Swapped into the active palette
# on top of the light/dark base so the user can recolour the UI.
ACCENTS = {
    "purple": ("#8b5cf6", "#a78bfa", "#6d28d9"),
    "blue":   ("#3b82f6", "#60a5fa", "#2563eb"),
    "teal":   ("#14b8a6", "#2dd4bf", "#0d9488"),
    "pink":   ("#ec4899", "#f472b6", "#db2777"),
    "amber":  ("#f59e0b", "#fbbf24", "#d97706"),
}

DEFAULT_SETTINGS = {
    "theme": "system",
    "accent": "purple",
    "default_mode": "best",
    "output_dir": "",          # empty = next to the source file
    "suffix": "_enhanced",
    "open_folder_after": False,
    "play_after": False,
    "tile": 0,                 # 0 = auto; lower values use less VRAM
}


def apply_theme(name: str, accent: str = "purple"):
    pal = dict(LIGHT if name == "light" else DARK)
    pal["ACCENT"], pal["ACCENT_HI"], pal["ACCENT_LO"] = ACCENTS.get(
        accent, ACCENTS["purple"])
    globals().update(pal)


def system_theme() -> str:
    """Read the Windows light/dark preference; default dark elsewhere."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value else "dark"
    except Exception:
        return "dark"


def effective_theme(setting: str) -> str:
    return system_theme() if setting == "system" else setting


CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "VideoEnhancer"
CONFIG_FILE = CONFIG_DIR / "settings.json"


def load_settings() -> dict:
    try:
        return {**DEFAULT_SETTINGS, **json.loads(CONFIG_FILE.read_text("utf-8"))}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(data: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2), "utf-8")
    except Exception:
        pass

FONT, FONT_SM = ("Segoe UI", 10), ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_H1 = ("Segoe UI Semibold", 18)
FONT_TITLE = ("Segoe UI", 11, "bold")

VIDEO_EXT = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv",
             ".flv", ".mpg", ".mpeg", ".ts", ".3gp")

PRESETS = {
    "quick": dict(
        label="Quick",
        desc="2x upscale, light denoise, fast",
        config=dict(use_ai=True, scale=2, denoise=2.0, crf=18, preset="fast"),
    ),
    "best": dict(
        label="Best",
        desc="2x upscale, strong denoise, recommended",
        config=dict(use_ai=True, scale=2, denoise=4.0, crf=16, preset="slow"),
    ),
    "max": dict(
        label="Maximum",
        desc="4x upscale, strong denoise, slow",
        config=dict(use_ai=True, scale=4, denoise=4.0, crf=16, preset="slow"),
    ),
    "denoise": dict(
        label="Denoise only",
        desc="no upscale, clean up noise and grain",
        config=dict(use_ai=False, scale=1, denoise=5.0, sharpen=0.3,
                    crf=18, preset="medium"),
    ),
    "custom": dict(
        label="Custom",
        desc="set every parameter by hand",
        config=dict(),
    ),
}


class Switch(tk.Canvas):
    """A small rounded toggle, since Tk has no native switch widget."""

    def __init__(self, parent, value=False, command=None):
        super().__init__(parent, width=46, height=26, bg=parent["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.value = value
        self.command = command
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _draw(self):
        self.delete("all")
        track = ACCENT if self.value else BG_INPUT
        self.create_oval(2, 3, 22, 23, fill=track, outline=track)
        self.create_oval(24, 3, 44, 23, fill=track, outline=track)
        self.create_rectangle(12, 3, 34, 23, fill=track, outline=track)
        kx = 25 if self.value else 4
        self.create_oval(kx, 5, kx + 17, 22, fill="#ffffff", outline="")

    def _toggle(self, _):
        self.value = not self.value
        self._draw()
        if self.command:
            self.command(self.value)


class App:
    def __init__(self, root, settings: dict | None = None):
        self.root = root
        self.settings = settings if settings is not None else load_settings()
        self.proc = VideoProcessor(on_progress=self._on_progress)
        self.input_path: str | None = None
        self.output_path: str | None = None
        self.info: VideoInfo | None = None
        self.mode = tk.StringVar(value=self.settings.get("default_mode", "best"))
        self.worker: threading.Thread | None = None
        self.events: queue.Queue = queue.Queue()
        self.mode_cards: dict[str, tk.Frame] = {}
        self.running = False
        self._alive = True
        self._stage = ""
        self._peak = 0.0

        self._init_style()
        self._build()
        self.root.after(80, self._pump_events)
        self._refresh_cards()

    # -- styling ------------------------------------------------------------
    def _init_style(self):
        self.root.configure(bg=BG)
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TScale", background=BG_CARD2, troughcolor=BG_INPUT,
                    bordercolor=BG_CARD2)
        s.configure("Horizontal.TProgressbar", background=ACCENT,
                    troughcolor=BG_INPUT, bordercolor=BG_INPUT,
                    lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)

    # -- layout -------------------------------------------------------------
    def _build(self):
        header = tk.Frame(self.root, bg=BG_CARD, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Video Enhancer", bg=BG_CARD, fg=FG,
                 font=FONT_H1).pack(side="left", padx=24)
        gear = tk.Label(header, text="⚙", bg=BG_CARD, fg=FG_MUTED,
                        font=("Segoe UI", 16), cursor="hand2")
        gear.pack(side="right", padx=(0, 22))
        gear.bind("<Button-1>", lambda e: self._open_settings())
        gear.bind("<Enter>", lambda e: gear.configure(fg=FG))
        gear.bind("<Leave>", lambda e: gear.configure(fg=FG_MUTED))
        tk.Label(header, text=self._gpu_label(), bg=BG_CARD, fg=FG_MUTED,
                 font=FONT_SM).pack(side="right", padx=12)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        self._build_dropzone(body)

        self.info_card = tk.Frame(body, bg=BG_CARD, highlightthickness=1,
                                  highlightbackground=BORDER)
        self.info_lbl = tk.Label(self.info_card, bg=BG_CARD, fg=FG_MUTED,
                                 font=FONT_SM, justify="left", anchor="w")
        self.info_lbl.pack(fill="x", padx=16, pady=12)

        self._build_modes(body)
        self._build_custom(body)
        self._build_output(body)
        self._build_action(body)

    def _titled_card(self, parent, title):
        c = tk.Frame(parent, bg=BG_CARD, highlightthickness=1,
                     highlightbackground=BORDER)
        tk.Label(c, text=title.upper(), bg=BG_CARD, fg=FG_DIM,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=16, pady=(12, 0))
        return c

    def _build_dropzone(self, parent):
        self.dz = tk.Frame(parent, bg=BG_CARD, height=130,
                           highlightthickness=2, highlightbackground=BORDER)
        self.dz.pack(fill="x")
        self.dz.pack_propagate(False)
        inner = tk.Frame(self.dz, bg=BG_CARD)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        self.dz_icon = tk.Label(inner, text="+", bg=BG_CARD, fg=ACCENT,
                                font=("Segoe UI", 28))
        self.dz_icon.pack()
        self.dz_text = tk.Label(
            inner, text="Drop a video here" if HAVE_DND else "Choose a video",
            bg=BG_CARD, fg=FG, font=FONT_TITLE)
        self.dz_text.pack()
        self.dz_sub = tk.Label(inner, text="or click to browse  ·  MP4, MOV, AVI, MKV",
                               bg=BG_CARD, fg=FG_DIM, font=FONT_SM)
        self.dz_sub.pack()

        for w in (self.dz, inner, self.dz_icon, self.dz_text, self.dz_sub):
            w.bind("<Button-1>", lambda e: self._browse())
            w.bind("<Enter>", lambda e: self._hover_dz(True))
            w.bind("<Leave>", lambda e: self._hover_dz(False))

        if HAVE_DND:
            self.dz.drop_target_register(DND_FILES)
            self.dz.dnd_bind("<<Drop>>", self._on_drop)

    def _hover_dz(self, on):
        if not self.running:
            self.dz.configure(highlightbackground=ACCENT if on else BORDER)

    def _build_modes(self, parent):
        card = self._titled_card(parent, "Enhancement mode")
        card.pack(fill="x", pady=(14, 0))
        grid = tk.Frame(card, bg=BG_CARD)
        grid.pack(fill="x", padx=12, pady=12)
        for i, key in enumerate(PRESETS):
            r, c = divmod(i, 2)
            self._mode_card(grid, key).grid(row=r, column=c, sticky="ew",
                                            padx=4, pady=4)
            grid.columnconfigure(c, weight=1)

    def _mode_card(self, parent, key):
        p = PRESETS[key]
        card = tk.Frame(parent, bg=BG_CARD2, highlightthickness=2,
                        highlightbackground=BG_CARD2, cursor="hand2")
        t = tk.Label(card, text=p["label"], bg=BG_CARD2, fg=FG,
                     font=FONT_BOLD, anchor="w")
        t.pack(fill="x", padx=12, pady=(10, 0))
        d = tk.Label(card, text=p["desc"], bg=BG_CARD2, fg=FG_MUTED,
                     font=FONT_SM, anchor="w", justify="left", wraplength=270)
        d.pack(fill="x", padx=12, pady=(2, 10))
        for w in (card, t, d):
            w.bind("<Button-1>", lambda e, k=key: self._pick_mode(k))
        self.mode_cards[key] = card
        return card

    def _pick_mode(self, key):
        if self.running:
            return
        self.mode.set(key)
        self._refresh_cards()
        self.custom_card.pack_forget()
        if key == "custom":
            self.custom_card.pack(fill="x", pady=(14, 0), before=self.output_card)

    def _refresh_cards(self):
        cur = self.mode.get()
        for key, card in self.mode_cards.items():
            card.configure(highlightbackground=ACCENT if key == cur else BG_CARD2)

    def _build_custom(self, parent):
        self.custom_card = self._titled_card(parent, "Custom settings")
        body = tk.Frame(self.custom_card, bg=BG_CARD)
        body.pack(fill="x", padx=16, pady=12)

        self.v_scale = tk.IntVar(value=2)
        self.v_denoise = tk.DoubleVar(value=4.0)
        self.v_sharpen = tk.DoubleVar(value=0.0)
        self.v_contrast = tk.DoubleVar(value=1.0)
        self.v_bright = tk.DoubleVar(value=0.0)
        self.v_sat = tk.DoubleVar(value=1.0)
        self.v_crf = tk.IntVar(value=16)
        self.v_stab = tk.BooleanVar(value=False)

        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x", pady=(0, 10))
        tk.Label(row, text="AI upscale", bg=BG_CARD, fg=FG, font=FONT,
                 width=14, anchor="w").pack(side="left")
        self.scale_btns = {}
        for val, txt in [(1, "Off"), (2, "2x"), (3, "3x"), (4, "4x")]:
            b = tk.Label(row, text=txt, bg=BG_INPUT, fg=FG_MUTED, font=FONT_SM,
                         padx=14, pady=4, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, v=val: self._set_scale(v))
            self.scale_btns[val] = b
        self._set_scale(2)

        self._slider(body, "Denoise", self.v_denoise, 0, 10)
        self._slider(body, "Sharpen", self.v_sharpen, 0, 3)
        self._slider(body, "Contrast", self.v_contrast, 0.5, 1.6)
        self._slider(body, "Brightness", self.v_bright, -0.3, 0.3)
        self._slider(body, "Saturation", self.v_sat, 0.5, 2.0)
        self._slider(body, "Quality (CRF, lower=better)", self.v_crf, 12, 30)

        stab = tk.Frame(body, bg=BG_CARD)
        stab.pack(fill="x", pady=(4, 0))
        tk.Checkbutton(stab, text="Stabilize shaky footage", variable=self.v_stab,
                       bg=BG_CARD, fg=FG, selectcolor=BG_INPUT,
                       activebackground=BG_CARD, activeforeground=FG,
                       font=FONT, highlightthickness=0, bd=0).pack(side="left")

    def _set_scale(self, val):
        self.v_scale.set(val)
        for v, b in self.scale_btns.items():
            on = v == val
            b.configure(bg=ACCENT if on else BG_INPUT,
                        fg="#ffffff" if on else FG_MUTED)

    def _slider(self, parent, label, var, lo, hi):
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG_CARD, fg=FG, font=FONT,
                 width=22, anchor="w").pack(side="left")
        out = tk.Label(row, text=self._fmt(var.get()), bg=BG_CARD, fg=ACCENT_HI,
                       font=FONT_BOLD, width=6, anchor="e")
        out.pack(side="right")
        ttk.Scale(row, from_=lo, to=hi, variable=var,
                  command=lambda e, v=var, l=out: l.configure(text=self._fmt(v.get()))
                  ).pack(side="left", fill="x", expand=True, padx=10)

    @staticmethod
    def _fmt(v):
        if abs(v - round(v)) < 1e-6:
            return str(int(round(v)))
        return f"{v:.2f}".rstrip("0").rstrip(".")

    def _build_output(self, parent):
        self.output_card = self._titled_card(parent, "Output")
        self.output_card.pack(fill="x", pady=(14, 0))
        row = tk.Frame(self.output_card, bg=BG_CARD)
        row.pack(fill="x", padx=16, pady=12)
        self.out_lbl = tk.Label(row, text="(saved next to the original)",
                                bg=BG_INPUT, fg=FG_MUTED, font=FONT_SM,
                                anchor="w", padx=12, pady=8)
        self.out_lbl.pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Change...", command=self._pick_output, bg=BG_CARD2,
                  fg=FG, font=FONT_SM, relief="flat", activebackground=BORDER,
                  activeforeground=FG, cursor="hand2", padx=14, pady=6,
                  bd=0).pack(side="left", padx=(10, 0))

    def _build_action(self, parent):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x", pady=(16, 0))

        self.btn = tk.Button(wrap, text="Drop a video to start",
                             command=self._start, fg="#ffffff",
                             font=("Segoe UI Semibold", 12), relief="flat",
                             activebackground=ACCENT_LO, activeforeground="#ffffff",
                             disabledforeground=FG_MUTED,
                             cursor="hand2", pady=12, bd=0)
        self.btn.pack(fill="x")
        self.btn.bind("<Enter>", lambda e: self._btn_color(ACCENT_HI))
        self.btn.bind("<Leave>", lambda e: self._btn_color(ACCENT))
        self._enable_btn(False)

        self.prog = tk.Frame(wrap, bg=BG)
        self.stage_lbl = tk.Label(self.prog, text="", bg=BG, fg=FG,
                                  font=FONT_BOLD, anchor="w")
        self.stage_lbl.pack(fill="x", pady=(14, 4))
        self.pbar = ttk.Progressbar(self.prog, mode="determinate", maximum=100,
                                    style="Horizontal.TProgressbar")
        self.pbar.pack(fill="x")
        self.detail_lbl = tk.Label(self.prog, text="", bg=BG, fg=FG_MUTED,
                                   font=FONT_SM, anchor="w")
        self.detail_lbl.pack(fill="x", pady=(4, 0))
        self.cancel_btn = tk.Button(self.prog, text="Cancel", command=self._cancel,
                                    bg=BG_CARD2, fg=RED, font=FONT_SM, relief="flat",
                                    activebackground=BORDER, cursor="hand2",
                                    padx=14, pady=6, bd=0)
        self.cancel_btn.pack(anchor="e", pady=(8, 0))

        self.result = tk.Frame(wrap, bg=BG_CARD, highlightthickness=1,
                               highlightbackground=GREEN)
        self.result_lbl = tk.Label(self.result, text="", bg=BG_CARD, fg=GREEN,
                                   font=FONT_BOLD, anchor="w")
        self.result_lbl.pack(fill="x", padx=16, pady=(12, 6))
        rb = tk.Frame(self.result, bg=BG_CARD)
        rb.pack(fill="x", padx=16, pady=(0, 12))
        tk.Button(rb, text="Play", command=self._open_file, bg=ACCENT, fg="#fff",
                  font=FONT_SM, relief="flat", cursor="hand2", padx=14, pady=6,
                  bd=0, activebackground=ACCENT_LO,
                  activeforeground="#fff").pack(side="left")
        tk.Button(rb, text="Open folder", command=self._open_folder, bg=BG_CARD2,
                  fg=FG, font=FONT_SM, relief="flat", cursor="hand2", padx=14,
                  pady=6, bd=0, activebackground=BORDER,
                  activeforeground=FG).pack(side="left", padx=8)

    def _btn_color(self, color):
        if str(self.btn["state"]) == "normal":
            self.btn.configure(bg=color)

    def _enable_btn(self, on):
        if on:
            self.btn.configure(state="normal", bg=ACCENT, text="Enhance video")
        else:
            # muted, clearly inactive, but the label stays readable
            self.btn.configure(state="disabled", bg=BG_CARD2,
                               text="Drop a video to start")

    # -- file selection -----------------------------------------------------
    def _browse(self):
        if self.running:
            return
        path = filedialog.askopenfilename(
            title="Choose a video",
            filetypes=[("Video", " ".join("*" + e for e in VIDEO_EXT)),
                       ("All files", "*.*")])
        if path:
            self._load(path)

    def _on_drop(self, event):
        if self.running:
            return
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        self._load(raw.split("} {")[0].strip("{}"))

    def _load(self, path):
        if not os.path.isfile(path):
            return
        if Path(path).suffix.lower() not in VIDEO_EXT:
            messagebox.showwarning("Unsupported file",
                                   "That does not look like a video.")
            return
        self.input_path = path
        self.output_path = None
        self.result.pack_forget()
        self.dz_text.configure(text=Path(path).name)
        self.dz_icon.configure(text=">")
        self.dz_sub.configure(text="reading details...")
        self._enable_btn(False)
        threading.Thread(target=self._probe, args=(path,), daemon=True).start()

    def _probe(self, path):
        try:
            self.events.put(("probe_ok", self.proc.probe(path)))
        except Exception as e:
            self.events.put(("probe_err", str(e)))

    def _show_info(self, info: VideoInfo):
        self.info = info
        warn = ""
        if info.duration > 180:
            warn = "   (long clip: AI mode takes a while and needs disk space)"
        self.info_lbl.configure(
            text=(f"Resolution {info.resolution}     Length {info.duration_str}"
                  f"     {info.fps:.0f} fps     {info.size_mb:.0f} MB"
                  f"     {info.codec or '?'}{warn}"))
        self.info_card.pack(fill="x", pady=(10, 0), after=self.dz)
        self.dz_sub.configure(text="click to pick a different file")
        self._enable_btn(True)

    def _pick_output(self):
        if not self.input_path:
            return
        path = filedialog.asksaveasfilename(
            title="Save as", defaultextension=".mp4",
            initialfile=Path(self.input_path).stem + "_enhanced.mp4",
            filetypes=[("MP4 video", "*.mp4")])
        if path:
            self.output_path = path
            self.out_lbl.configure(text=path, fg=FG)

    # -- run ----------------------------------------------------------------
    def _config(self) -> EnhanceConfig:
        if self.mode.get() == "custom":
            cfg = EnhanceConfig(
                use_ai=self.v_scale.get() > 1,
                scale=self.v_scale.get(),
                denoise=round(self.v_denoise.get(), 2),
                sharpen=round(self.v_sharpen.get(), 2),
                contrast=round(self.v_contrast.get(), 3),
                brightness=round(self.v_bright.get(), 3),
                saturation=round(self.v_sat.get(), 3),
                stabilize=self.v_stab.get(),
                crf=int(self.v_crf.get()),
                preset="slow",
            )
        else:
            cfg = EnhanceConfig()
            for k, v in PRESETS[self.mode.get()]["config"].items():
                setattr(cfg, k, v)
        cfg.tile = int(self.settings.get("tile", 0))
        return cfg

    def _default_output(self) -> str:
        suffix = self.settings.get("suffix") or "_enhanced"
        out_dir = self.settings.get("output_dir") or str(Path(self.input_path).parent)
        return str(Path(out_dir) / (Path(self.input_path).stem + suffix + ".mp4"))

    def _start(self):
        if self.running or not self.input_path:
            return
        cfg = self._config()
        if cfg.use_ai and not VideoProcessor.ai_available():
            messagebox.showerror(
                "AI not available",
                "Real-ESRGAN was not found. Pick 'Denoise only' or run "
                "scripts/download_models.py.")
            return
        if not self.output_path:
            self.output_path = self._default_output()
        if os.path.exists(self.output_path) and not messagebox.askyesno(
                "Overwrite?", f"{Path(self.output_path).name} already exists.\n"
                              "Overwrite it?"):
            return

        self.running = True
        self.btn.pack_forget()
        self.result.pack_forget()
        self.prog.pack(fill="x")
        self.pbar["value"] = 0
        self._stage, self._peak = "", 0.0
        self.stage_lbl.configure(text="Preparing...")
        self.detail_lbl.configure(text="")
        self.worker = threading.Thread(target=self._work, args=(cfg,), daemon=True)
        self.worker.start()

    def _work(self, cfg):
        try:
            self.proc.process(self.input_path, self.output_path, cfg, self.info)
            self.events.put(("done", None))
        except Cancelled:
            self.events.put(("cancelled", None))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _cancel(self):
        self.cancel_btn.configure(state="disabled", text="Cancelling...")
        self.proc.cancel()

    # -- worker -> UI bridge ------------------------------------------------
    def _on_progress(self, pct, stage, detail=""):
        self.events.put(("progress", (pct, stage, detail)))

    def _pump_events(self):
        if not self._alive:
            return  # a rebuild replaced this App; stop the old loop
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._dispatch(kind, payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump_events)

    def _dispatch(self, kind, payload):
        if kind == "probe_ok":
            self._show_info(payload)
        elif kind == "probe_err":
            self.dz_sub.configure(text="could not read that video")
        elif kind == "progress":
            pct, stage, detail = payload
            if stage != self._stage:
                self._stage, self._peak = stage, pct
            self._peak = max(self._peak, pct)
            self.pbar["value"] = self._peak
            self.stage_lbl.configure(text=f"{stage}   {self._peak:.0f}%")
            self.detail_lbl.configure(text=detail)
        elif kind == "done":
            self._on_done()
        elif kind == "cancelled":
            self._on_cancelled()
        elif kind == "error":
            self._on_error(payload)

    def _reset(self):
        self.running = False
        self.prog.pack_forget()
        self.cancel_btn.configure(state="normal", text="Cancel")
        self._enable_btn(True)
        self.btn.pack(fill="x")

    def _on_done(self):
        self._reset()
        try:
            size = f"   {os.path.getsize(self.output_path) / 1024 / 1024:.0f} MB"
        except OSError:
            size = ""
        self.result_lbl.configure(text=f"Done   {Path(self.output_path).name}{size}")
        self.result.pack(fill="x", pady=(14, 0))
        if self.settings.get("play_after"):
            self._open_file()
        elif self.settings.get("open_folder_after"):
            self._open_folder()

    def _on_cancelled(self):
        self._reset()
        try:
            if self.output_path and os.path.exists(self.output_path):
                os.remove(self.output_path)
        except OSError:
            pass

    def _on_error(self, msg):
        self._reset()
        messagebox.showerror("Processing failed", msg)

    # -- settings -----------------------------------------------------------
    def _save(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)

    def _open_settings(self):
        if self.running:
            messagebox.showinfo("Settings",
                                "Finish or cancel the current job first.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Settings")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._settings_dlg = dlg

        wrap = tk.Frame(dlg, bg=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=18)

        # Appearance ------------------------------------------------------
        self._group(wrap, "Appearance")
        self._segment_row(
            wrap, "Theme",
            [("system", "System"), ("light", "Light"), ("dark", "Dark")],
            self.settings.get("theme", "system"), self._on_theme)
        self._accent_row(wrap)

        # Defaults --------------------------------------------------------
        self._group(wrap, "Defaults")
        self._segment_row(
            wrap, "Start in mode",
            [(k, PRESETS[k]["label"]) for k in PRESETS],
            self.settings.get("default_mode", "best"), self._on_default_mode)
        self._suffix_row(wrap)
        self._outdir_row(wrap)

        # After processing ------------------------------------------------
        self._group(wrap, "After processing")
        self._switch_row(wrap, "Open output folder", "open_folder_after")
        self._switch_row(wrap, "Play the result", "play_after")

        # Performance -----------------------------------------------------
        self._group(wrap, "Performance")
        self._segment_row(
            wrap, "AI tile size",
            [(0, "Auto"), (128, "128"), (256, "256"), (512, "512")],
            self.settings.get("tile", 0), lambda v: self._save("tile", v))
        tk.Label(wrap, text="Lower values use less video memory on weak GPUs.",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 8), anchor="w").pack(
            fill="x", pady=(0, 4))

        # About -----------------------------------------------------------
        self._group(wrap, "About")
        tk.Label(wrap, text=f"Video Enhancer 1.0     {self._gpu_label()}",
                 bg=BG, fg=FG_MUTED, font=FONT_SM, anchor="w").pack(fill="x")
        foot = tk.Frame(wrap, bg=BG)
        foot.pack(fill="x", pady=(14, 0))
        tk.Button(foot, text="Reset to defaults", command=self._reset_settings,
                  bg=BG_CARD2, fg=FG, font=FONT_SM, relief="flat", cursor="hand2",
                  padx=14, pady=6, bd=0, activebackground=BORDER,
                  activeforeground=FG).pack(side="left")
        tk.Button(foot, text="Done", command=dlg.destroy, bg=ACCENT, fg="#ffffff",
                  font=FONT_SM, relief="flat", cursor="hand2", padx=20, pady=6,
                  bd=0, activebackground=ACCENT_LO,
                  activeforeground="#ffffff").pack(side="right")

        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + 80
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    # settings widgets --------------------------------------------------
    def _group(self, parent, title):
        tk.Label(parent, text=title.upper(), bg=BG, fg=FG_DIM,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(14, 8))

    def _segment_row(self, parent, label, options, current, on_select):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT, width=14,
                 anchor="w").pack(side="left")
        seg = tk.Frame(row, bg=BG_INPUT)
        seg.pack(side="left")
        chips = {}

        def paint(val):
            for v, c in chips.items():
                on = v == val
                c.configure(bg=ACCENT if on else BG_INPUT,
                            fg="#ffffff" if on else FG_MUTED)

        def select(val):
            paint(val)
            on_select(val)

        for val, text in options:
            c = tk.Label(seg, text=text, bg=BG_INPUT, fg=FG_MUTED, font=FONT_SM,
                         padx=12, pady=4, cursor="hand2")
            c.pack(side="left", padx=1, pady=1)
            c.bind("<Button-1>", lambda e, v=val: select(v))
            chips[val] = c
        paint(current)  # initial state only, do not fire the handler

    def _accent_row(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="Accent", bg=BG, fg=FG, font=FONT, width=14,
                 anchor="w").pack(side="left")
        dots = {}

        def paint(name):
            for n, d in dots.items():
                d.configure(text="●" if n == name else "○")

        def pick(name):
            paint(name)
            self._on_accent(name)

        for name, (base, _, _) in ACCENTS.items():
            d = tk.Label(row, text="○", fg=base, bg=BG,
                         font=("Segoe UI", 18), cursor="hand2")
            d.pack(side="left", padx=3)
            d.bind("<Button-1>", lambda e, n=name: pick(n))
            dots[name] = d
        paint(self.settings.get("accent", "purple"))  # initial state only

    def _switch_row(self, parent, label, key):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT, anchor="w").pack(
            side="left")
        sw = Switch(row, value=bool(self.settings.get(key, False)),
                    command=lambda v: self._save(key, v))
        sw.pack(side="right")

    def _suffix_row(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="Filename suffix", bg=BG, fg=FG, font=FONT, width=14,
                 anchor="w").pack(side="left")
        var = tk.StringVar(value=self.settings.get("suffix", "_enhanced"))
        e = tk.Entry(row, textvariable=var, bg=BG_INPUT, fg=FG, font=FONT_SM,
                     relief="flat", insertbackground=FG, width=18)
        e.pack(side="left", ipady=4, padx=(0, 0))
        var.trace_add("write", lambda *_: self._save("suffix", var.get() or "_enhanced"))

    def _outdir_row(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="Output folder", bg=BG, fg=FG, font=FONT, width=14,
                 anchor="w").pack(side="left")
        cur = self.settings.get("output_dir") or "Same as source"
        self._outdir_lbl = tk.Label(row, text=cur, bg=BG, fg=FG_MUTED,
                                    font=("Segoe UI", 8), anchor="w")
        self._outdir_lbl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def choose():
            d = filedialog.askdirectory(title="Output folder")
            if d:
                self._save("output_dir", d)
                self._outdir_lbl.configure(text=d)

        def reset():
            self._save("output_dir", "")
            self._outdir_lbl.configure(text="Same as source")

        tk.Button(row, text="...", command=choose, bg=BG_CARD2, fg=FG,
                  font=FONT_SM, relief="flat", cursor="hand2", padx=10, pady=2,
                  bd=0).pack(side="right")
        tk.Button(row, text="Reset", command=reset, bg=BG_CARD2, fg=FG_MUTED,
                  font=("Segoe UI", 8), relief="flat", cursor="hand2", padx=8,
                  pady=2, bd=0).pack(side="right", padx=4)

    # settings handlers -------------------------------------------------
    def _on_theme(self, value):
        self._save("theme", value)
        apply_theme(effective_theme(value), self.settings.get("accent", "purple"))
        self._rebuild(reopen_settings=True)

    def _on_accent(self, value):
        self._save("accent", value)
        apply_theme(effective_theme(self.settings.get("theme", "system")), value)
        self._rebuild(reopen_settings=True)

    def _on_default_mode(self, value):
        self._save("default_mode", value)
        self.mode.set(value)
        self._refresh_cards()
        self.custom_card.pack_forget()
        if value == "custom":
            self.custom_card.pack(fill="x", pady=(14, 0), before=self.output_card)

    def _reset_settings(self):
        self.settings = dict(DEFAULT_SETTINGS)
        save_settings(self.settings)
        apply_theme(effective_theme("system"), "purple")
        self._rebuild(reopen_settings=True)

    def _rebuild(self, reopen_settings=False):
        """Rebuild the window with the active palette, keeping the loaded
        clip and chosen mode."""
        if getattr(self, "_settings_dlg", None):
            try:
                self._settings_dlg.destroy()
            except tk.TclError:
                pass
        state = (self.input_path, self.info, self.output_path, self.mode.get())
        self._alive = False
        for child in self.root.winfo_children():
            child.destroy()
        self.root.configure(bg=BG)
        new = App(self.root, self.settings)
        new._restore(*state)
        if reopen_settings:
            new.root.after(60, new._open_settings)

    def _restore(self, input_path, info, output_path, mode):
        self.mode.set(mode)
        self._refresh_cards()
        if mode == "custom":
            self.custom_card.pack(fill="x", pady=(14, 0), before=self.output_card)
        if input_path and info:
            self.input_path = input_path
            self.output_path = output_path
            self.dz_text.configure(text=Path(input_path).name)
            self.dz_icon.configure(text=">")
            if output_path:
                self.out_lbl.configure(text=output_path, fg=FG)
            self._show_info(info)

    # -- result actions -----------------------------------------------------
    def _open_file(self):
        if self.output_path and os.path.exists(self.output_path):
            os.startfile(self.output_path)

    def _open_folder(self):
        if self.output_path and os.path.exists(self.output_path):
            subprocess.run(["explorer", "/select,", os.path.normpath(self.output_path)])

    @staticmethod
    def _gpu_label():
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name",
                                "--format=csv,noheader"],
                               capture_output=True, text=True, timeout=3,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            name = (r.stdout or "").strip().splitlines()
            if name and name[0]:
                return f"GPU: {name[0]}"
        except Exception:
            pass
        return "CPU mode"


def _apply_icon(root):
    ico = BASE_DIR / "assets" / "icon.ico"
    if ico.exists():
        try:
            root.iconbitmap(str(ico))
        except tk.TclError:
            pass
    png = BASE_DIR / "assets" / "icon.png"
    if png.exists():
        try:
            root._icon = tk.PhotoImage(file=str(png))
            root.iconphoto(True, root._icon)
        except tk.TclError:
            pass


def main():
    settings = load_settings()
    apply_theme(effective_theme(settings.get("theme", "system")),
                settings.get("accent", "purple"))

    root = TkinterDnD.Tk() if HAVE_DND else tk.Tk()
    root.title("Video Enhancer")
    root.geometry("680x900")
    root.minsize(640, 760)
    root.configure(bg=BG)
    _apply_icon(root)
    App(root, settings)
    root.mainloop()


if __name__ == "__main__":
    main()
