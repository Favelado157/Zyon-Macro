import json, os, sys, time, threading, subprocess, queue, math
from PIL import Image, ImageTk, ImageOps
from panel_art import control_texture, logo, shaded_art
from update import download_installer, find_update
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
try:
    from pynput import mouse, keyboard
except ImportError:
    mouse = keyboard = None

APP_NAME = "GhosttzzKBot"
VERSION = "1.4.0"
BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR))) / APP_NAME if sys.platform == "win32" else BASE_DIR
CONFIG_DIR = DATA_DIR / "config"
RECORDINGS_DIR = DATA_DIR / "recordings"
ASSETS = BASE_DIR / "assets"
BRUSH_FONT = ASSETS / "RoadRage-Regular.ttf"
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEFAULTS = {
    "hotkeys": {"record": "<f5>", "pause": "<f6>", "play": "<f7>", "stop": "<f8>"},
    "record_mouse_movement": True, "record_mouse_clicks": True, "record_scroll": True, "record_keyboard": False,
    "show_mouse_path": True, "repeat_playback": False, "click_delay_ms": 50,
    "mode": "Normal", "repeat_interval_ms": 100
}
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

def load_settings():
    data = {}
    try:
        source = CONFIG_FILE if CONFIG_FILE.exists() else BASE_DIR / "config" / "settings.json"
        if source.exists():
            data = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    cfg = dict(DEFAULTS)
    cfg.update({k:v for k,v in data.items() if k != "hotkeys"})
    for key, limit in (("repeat_interval_ms", 60000), ("click_delay_ms", 2000)):
        try:
            cfg[key] = max(0, min(limit, int(cfg[key])))
        except (ValueError, TypeError, OverflowError):
            cfg[key] = DEFAULTS[key]
    if cfg["mode"] not in ("Normal", "Preciso", "Leve"):
        cfg["mode"] = "Normal"
    cfg["hotkeys"] = {**DEFAULTS["hotkeys"], **(data.get("hotkeys") if isinstance(data.get("hotkeys"), dict) else {})}
    return cfg

def save_settings(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(CONFIG_FILE)

def encode_key(key):
    if isinstance(key, keyboard.Key):
        return "special", key.name
    if isinstance(key, keyboard.KeyCode):
        if sys.platform == "win32" and key.vk:
            return "vk", key.vk
        if key.char:
            return ("dead" if key.is_dead else "char"), key.char
        if key.vk:
            return "vk", key.vk
    return None


def decode_key(kind, value):
    if kind == "special" and isinstance(value, str) and value in keyboard.Key.__members__:
        return keyboard.Key[value]
    if kind == "vk" and type(value) is int and 0 < value <= (255 if sys.platform == "win32" else 0xFFFFFFFF):
        return keyboard.KeyCode.from_vk(value)
    if kind in ("char", "dead") and isinstance(value, str) and len(value) == 1 and not 0xD800 <= ord(value) <= 0xDFFF:
        return (keyboard.KeyCode.from_dead if kind == "dead" else keyboard.KeyCode.from_char)(value)
    raise ValueError("Tecla inválida na gravação.")


def validate_events(events):
    if not isinstance(events, list):
        raise ValueError("O arquivo exige uma lista de eventos.")
    previous = 0
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Evento inválido.")
        stamp = event.get("t")
        if type(stamp) not in {int, float} or not math.isfinite(stamp) or stamp < previous:
            raise ValueError("Tempo inválido na gravação.")
        previous = stamp
        if event.get("type") == "key":
            if type(event.get("pressed")) is not bool:
                raise ValueError("Estado inválido da tecla.")
            decode_key(event.get("encoding"), event.get("key"))
            continue
        if any(type(event.get(axis)) is not int or not -(2**31) <= event[axis] < 2**31 for axis in ("x", "y")):
            raise ValueError("Coordenadas inválidas na gravação.")
        kind = event.get("type")
        if kind == "click":
            if event.get("button") not in mouse.Button.__members__ or type(event.get("pressed")) is not bool:
                raise ValueError("Clique inválido na gravação.")
        elif kind == "scroll":
            if any(type(event.get(axis)) is not int or abs(event[axis]) > 10000 for axis in ("dx", "dy")):
                raise ValueError("Rolagem inválida na gravação.")
        elif kind != "move":
            raise ValueError("A gravação contém um tipo de ação desconhecido.")


class GhosttzzKBot:
    def __init__(self, root):
        self.root = root
        self.cfg = load_settings()
        self.events = []
        self.ui_queue = queue.SimpleQueue()
        self.closing = False
        self.update_busy = False
        self.pending_installer = None
        self.editing_shortcuts = False
        self.capture_keys = False
        self.recorded_keys = {}
        self.record_options = (True, True, True, 0)
        self.paused_at = None
        self.recording = False
        self.playing = False
        self.stop_event = threading.Event()
        self.resume_event = threading.Event(); self.resume_event.set()
        self.lock = threading.Lock()
        self.record_start = 0.0
        self.mouse_listener = None
        self.hotkey_listener = None
        self.status = tk.StringVar(value="Nenhuma gravação ativa. Pressione Gravar para começar.")
        self.count = tk.StringVar(value="0")
        self.duration = tk.StringVar(value="00:00:00")
        self.size = tk.StringVar(value="0 KB")
        self.mode = tk.StringVar(value=self.cfg.get("mode", "Normal"))
        self.interval = tk.IntVar(value=self.cfg.get("repeat_interval_ms", 100))
        self.filename = tk.StringVar(value="Nenhum")
        self.click_delay = tk.IntVar(value=int(self.cfg.get("click_delay_ms", 0)))
        self.repeat_var = tk.BooleanVar(value=bool(self.cfg.get("repeat_playback", False)))
        self.move_var = tk.BooleanVar(value=bool(self.cfg.get("record_mouse_movement", True)))
        self.click_var = tk.BooleanVar(value=bool(self.cfg.get("record_mouse_clicks", True)))
        self.keyboard_var = tk.BooleanVar(value=bool(self.cfg["record_keyboard"]))
        self.capture_status = tk.StringVar(value="●  Sistema online")
        self.scroll_var = tk.BooleanVar(value=bool(self.cfg.get("record_scroll", True)))
        self.path_var = tk.BooleanVar(value=bool(self.cfg.get("show_mouse_path", False)))
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("1024x785")
        self.root.minsize(960, 680)
        self.custom_chrome()
        self.root.configure(bg="#020914")
        try:
            icon = CONFIG_DIR / "icone.ico"
            if not icon.exists():
                icon = ASSETS / "GhosttzzKBot.ico"
            self.root.iconbitmap(str(icon))
        except Exception:
            pass
        self.build_ui()
        self.sync_options()
        self.start_mouse_listener()
        self.start_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()
        self.root.after(500, self.check_update)
        if not CONFIG_FILE.exists():
            save_settings(self.cfg)

    def custom_chrome(self):
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes

        self.root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(self.root.winfo_id())
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        style = user32.GetWindowLongW(hwnd, -16)
        user32.SetWindowLongW(hwnd, -16, style & ~0x00C00000)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)
        self.root.after(100, self.ensure_chrome)

    def ensure_chrome(self):
        if self.root.winfo_ismapped() and not getattr(self, "chrome_mapped", False):
            self.chrome_mapped = True
            self.custom_chrome()

    def maximize(self):
        self.root.state("normal" if self.root.state() == "zoomed" else "zoomed")

    def drag_start(self, event):
        self.drag_position = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def drag_move(self, event):
        if self.root.state() == "normal":
            x, y = self.drag_position
            self.root.geometry(f"{event.x_root-x:+d}{event.y_root-y:+d}")

    def label(self, parent, text="", **options):
        style = dict(bg=parent.cget("bg"), fg="#daeaff", font=("Segoe UI", 10))
        style.update(options)
        return tk.Label(parent, text=text, **style)

    def btn(self, parent, text, color, command, pady=4, font=10, **options):
        style = dict(bg=color, fg="#ecf6ff", activebackground="#0a5489", activeforeground="white",
                     relief="flat", font=("Segoe UI", font, "bold"), padx=7, pady=pady,
                     cursor="hand2", bd=0, highlightthickness=0)
        style.update(options)
        return tk.Button(parent, text=text, command=command, **style)

    def card(self, parent, title):
        frame = tk.Frame(parent, bg="#041020", highlightbackground="#07528a", highlightthickness=1)
        self.label(frame, title, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(6, 4))
        return frame

    def art(self, parent, role, width, height, title="", subtitle=""):
        canvas = tk.Canvas(parent, height=height, width=width, bg="#020917", highlightthickness=0)
        custom = CONFIG_DIR / f"{role}.png"
        source = custom if custom.exists() else ASSETS / ("GhosttzzKBot_icon.png" if role == "icone" else "painel.jpg")
        try:
            with Image.open(source) as file:
                art = file.convert("RGB")
        except (OSError, ValueError):
            with Image.open(ASSETS / "GhosttzzKBot_icon.png") as file:
                art = file.convert("RGB")

        def draw(event):
            w, h = event.width, event.height
            if w < 2 or h < 2:
                return
            canvas.delete("all")
            if custom.exists() or role == "icone":
                back = ImageOps.fit(art, (w, h), centering=(0.5, 0.43))
            else:
                back = shaded_art(art, (w, h), role)
            if role == "banner":
                logo(back, title, BRUSH_FONT, (round(w * .40), 7, round(w * .57), round(h * .61)))
            elif role == "lateral":
                logo(back, APP_NAME, BRUSH_FONT, (3, round(h * .72), w - 6, round(h * .21)))
            canvas.photo = ImageTk.PhotoImage(back)
            canvas.create_image(0, 0, image=canvas.photo, anchor="nw")
            if subtitle:
                canvas.create_text(w * .71, h * .81, text=subtitle, fill="#b8ebff",
                                   font=("Segoe UI", 9, "bold"))
            if role == "lateral":
                canvas.create_text(w / 2, h * .95, text="SUA MACRO, DO SEU JEITO!", fill="#06caff",
                                   font=("Segoe UI", 8, "bold italic"))
            if role != "cabecalho":
                canvas.create_rectangle(0, 0, w - 1, h - 1, outline="#07528a")
        canvas.bind("<Configure>", draw)
        return canvas

    def brand_image(self, parent, width, height):
        background = Image.new("RGB", (width, height), parent.cget("bg"))
        logo(background, APP_NAME, BRUSH_FONT, (0, 0, width, height))
        photo = ImageTk.PhotoImage(background)
        label = self.label(parent, image=photo)
        label.photo = photo
        return label

    def macro_button(self, parent, key, palette, action):
        canvas = tk.Canvas(parent, width=99, height=95, bg=parent.cget("bg"), highlightthickness=0,
                           takefocus=True, cursor="hand2")
        canvas.hovered = False
        canvas.shortcut = ""

        def paint(event=None):
            w, h = canvas.winfo_width(), canvas.winfo_height()
            if w < 22 or h < 22:
                return
            if getattr(canvas, "face_key", None) != (w, h, canvas.hovered):
                canvas.photo = ImageTk.PhotoImage(control_texture(self.texture, (w, h), palette, canvas.hovered))
                canvas.face_key = w, h, canvas.hovered
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=canvas.photo)
            center = w / 2
            y = h * .31
            if key == "record":
                canvas.create_oval(center - 13, y - 13, center + 13, y + 13, fill="white", outline="")
            elif key == "pause":
                for dx in (-7, 5):
                    canvas.create_line(center + dx, y - 10, center + dx, y + 10, fill="white", width=6, capstyle="round")
            elif key == "play":
                canvas.create_polygon(center - 9, y - 13, center + 13, y, center - 9, y + 13, fill="white")
            else:
                canvas.create_rectangle(center - 11, y - 11, center + 11, y + 11, fill="white", outline="")
            canvas.create_text(center, h * .65, text=self.labels[key], fill="white", font=("Segoe UI", 11, "bold"))
            canvas.create_text(center, h * .84, text=canvas.shortcut, fill="#e4f5ff", font=("Segoe UI", 9))
            if self.root.focus_get() == canvas:
                canvas.create_rectangle(5, 5, w - 6, h - 6, outline="white", dash=(2, 3))

        def hover(active):
            canvas.hovered = active
            paint()

        canvas.repaint = paint
        for sequence in ("<Configure>", "<FocusIn>", "<FocusOut>"):
            canvas.bind(sequence, paint)
        canvas.bind("<Enter>", lambda event: hover(True))
        canvas.bind("<Leave>", lambda event: hover(False))
        for sequence in ("<ButtonRelease-1>", "<Return>", "<space>"):
            canvas.bind(sequence, lambda event: self.run_control(action))
        return canvas

    def build_ui(self):
        bg = "#020914"
        top = tk.Frame(self.root, bg="#030a18", height=86, highlightbackground="#0875bd", highlightthickness=1)
        top.pack(fill="x")
        top.pack_propagate(False)
        header_art = self.art(top, "cabecalho", 1000, 86)
        header_art.place(relwidth=1, relheight=1)
        self.art(top, "icone", 82, 80).pack(side="left", padx=(5, 11), pady=3)
        brand = tk.Frame(top, bg="#030a18")
        brand.pack(side="left", pady=7)
        name_row = tk.Frame(brand, bg=brand.cget("bg"))
        name_row.pack(anchor="w")
        name = self.brand_image(name_row, 236, 48)
        name.pack(side="left")
        version = self.label(name_row, f"v{VERSION}", fg="#b8dcff", font=("Segoe UI", 9, "bold"))
        version.pack(side="left", anchor="s", pady=5, padx=4)
        tagline = self.label(brand, "Automatize seus movimentos. Domine seu jogo.", fg="#63dbff",
                             font=("Segoe UI", 10, "italic"))
        tagline.pack(anchor="w")
        for widget in (top, header_art, brand, name, version, tagline):
            widget.bind("<Button-1>", self.drag_start)
            widget.bind("<B1-Motion>", self.drag_move)
            widget.bind("<Double-Button-1>", lambda event: self.maximize())
        actions = tk.Frame(top, bg="#030a18")
        actions.pack(side="right", anchor="n", padx=7, pady=6)
        for caption, action in (("−", self.root.iconify), ("□", self.maximize), ("×", self.close)):
            self.btn(actions, caption, "#09203a", action, pady=0, font=13, width=2).pack(side="left", padx=2)
        self.btn(top, "⚙", "#061322", self.open_settings, pady=0, font=15).place(relx=1, x=-14, y=46, anchor="ne")
        self.label(top, "MAIS PRECISÃO\nMAIS CONTROLE\nMAIS RESULTADOS", fg="#10bfff",
                   font=("Segoe UI", 9, "bold italic")).pack(side="right", padx=(0, 19))

        footer = tk.Frame(self.root, bg="#030a18", highlightbackground="#07528a", highlightthickness=1)
        footer.pack(side="bottom", fill="x")
        self.brand_image(footer, 114, 24).pack(side="left", padx=9, pady=3)
        self.label(footer, f"│  v{VERSION}  │   Automatize seus movimentos. Domine seu jogo.", fg="#66b6ec",
                   font=("Segoe UI", 8)).pack(side="left")
        self.label(footer, "♛", fg="#c6e8ff", font=("Segoe UI Symbol", 16)).pack(side="right", padx=9)
        self.capture_indicator = self.label(footer, textvariable=self.capture_status, fg="#00ecc0")
        self.capture_indicator.pack(side="right", padx=12)
        body = tk.Frame(self.root, bg=bg)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        for column, (minimum, weight) in enumerate(((158, 0), (452, 5), (279, 3))):
            body.columnconfigure(column, minsize=minimum, weight=weight)
        body.rowconfigure(0, weight=1)
        nav = tk.Frame(body, bg="#040c18", highlightbackground="#07528a", highlightthickness=1)
        nav.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        for index, (caption, action) in enumerate((
            ("⌂   Início", self.focus_home), ("▣   Gravações", self.open_recordings_folder),
            ("⌨   Atalhos", self.edit_hotkeys),
            ("◉   Temas", self.edit_theme), ("ⓘ   Sobre", self.about),
        )):
            color = "#0948ad" if index == 0 else "#040c18"
            self.btn(nav, caption, color, action, pady=9, anchor="w").pack(fill="x", padx=3, pady=2)
        self.art(nav, "lateral", 150, 245).pack(fill="both", expand=True, padx=2, pady=(10, 2))

        center = tk.Frame(body, bg=bg)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self.art(center, "banner", 470, 131, APP_NAME, "MACRO  •  GRAVAÇÃO  •  AUTOMAÇÃO").pack(fill="x")
        controls = self.card(center, "◎   Controles Principais")
        controls.pack(fill="x", pady=(8, 0))
        buttons = tk.Frame(controls, bg=controls["bg"])
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        self.controls = {}
        self.labels = {"record": "Gravar", "pause": "Pausar", "play": "Play", "stop": "Parar"}
        self.symbols = {"record": "●", "pause": "Ⅱ", "play": "▶", "stop": "■"}
        with Image.open(ASSETS / "painel.jpg") as source:
            self.texture = source.convert("RGB")
        for key, palette, action in (
            ("record", ("#ff1645", "#4c020d", "#ff2e58"), self.start_record),
            ("pause", ("#ffb714", "#633400", "#ffc34e"), self.pause_toggle),
            ("play", ("#0abb86", "#003a2f", "#30ffb8"), self.play_record),
            ("stop", ("#0874ff", "#001a5b", "#43a2ff"), self.stop_all),
        ):
            self.controls[key] = self.macro_button(buttons, key, palette, action)
            self.controls[key].pack(side="left", expand=True, fill="x", padx=4)

        info = self.card(center, "▣   Informações da Gravação")
        info.pack(fill="both", expand=True, pady=(8, 0))
        details = tk.Frame(info, bg=info["bg"])
        details.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        stats = tk.Frame(details, bg="#030c19", highlightbackground="#074675", highlightthickness=1)
        stats.pack(side="left", fill="both", expand=True, padx=(0, 6))
        for title, var in (("◷   Duração", self.duration), ("⊕   Ações gravadas", self.count),
                           ("▤   Tamanho", self.size), ("▣   Arquivo", self.filename)):
            row = tk.Frame(stats, bg=stats["bg"])
            row.pack(fill="x", padx=6, pady=2)
            self.label(row, title, font=("Segoe UI", 9)).pack(side="left")
            self.label(row, textvariable=var, font=("Segoe UI", 9), wraplength=80).pack(side="right")
        visual = tk.Frame(details, bg="#030c19", width=185, highlightbackground="#074675", highlightthickness=1)
        visual.pack(side="right", fill="both", expand=True)
        self.path_canvas = tk.Canvas(visual, height=50, width=145, bg=visual["bg"], highlightthickness=0)
        self.path_canvas.pack(fill="both", expand=True)
        self.label(visual, textvariable=self.status, fg="#8bcfff", wraplength=168, font=("Segoe UI", 9)).pack(padx=3, pady=4)

        settings = self.card(center, "⚙   Configurações")
        self.settings_card = settings
        settings.pack(fill="x", pady=(8, 0))
        columns = tk.Frame(settings, bg=settings["bg"])
        columns.pack(fill="x", padx=8, pady=(0, 7))
        left = tk.Frame(columns, bg="#06182b")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        for caption, var in (("Gravar movimento do mouse", self.move_var), ("Gravar cliques do mouse", self.click_var),
                             ("Gravar rolagem da roda", self.scroll_var), ("Gravar teclas digitadas", self.keyboard_var),
                             ("Exibir caminho do mouse", self.path_var)):
            self.toggle(left, caption, var)
        options = tk.Frame(columns, bg=settings["bg"])
        options.pack(side="right", fill="both", expand=True)
        self.label(options, "Modo de gravação", font=("Segoe UI", 9)).pack(anchor="w")
        menu = tk.OptionMenu(options, self.mode, "Normal", "Preciso", "Leve", command=lambda _: self.save_quick())
        menu.configure(bg="#0a2440", fg="white", activebackground="#105490", highlightthickness=0, bd=0)
        menu.pack(fill="x")
        self.spin(options, "Intervalo de repetição (ms)", self.interval, 60000)
        self.toggle(options, "Repetir gravação", self.repeat_var)
        self.spin(options, "Velocidade dos cliques (ms)", self.click_delay, 2000)
        self.btn(options, "⚙  Avançado", "#0a305a", self.show_config_path, pady=1, font=9).pack(fill="x", pady=(3, 0))

        right = tk.Frame(body, bg=bg)
        right.grid(row=0, column=2, sticky="nsew")
        hot = self.card(right, "⌨   Atalhos de Teclado")
        hot.pack(fill="x")
        self.btn(hot, "Editar", "#073765", self.edit_hotkeys, pady=1, font=9).place(relx=1, x=-7, y=4, anchor="ne")
        self.key_labels = {}
        for key, color in zip(self.labels, ("#ff2351", "#ffaf17", "#00e8a0", "#35aaff")):
            row = tk.Frame(hot, bg="#051222", highlightbackground="#07365a", highlightthickness=1)
            row.pack(fill="x", padx=8, pady=2)
            self.label(row, self.symbols[key], fg=color, font=("Segoe UI", 14, "bold"), width=2).pack(side="left")
            self.label(row, self.labels[key], font=("Segoe UI", 10)).pack(side="left")
            self.btn(row, "✎", "#051222", lambda k=key: self.edit_hotkeys(k), pady=1).pack(side="right")
            self.key_labels[key] = self.label(row, bg="#0b2541", width=10, font=("Segoe UI", 9, "bold"))
            self.key_labels[key].pack(side="right", padx=5, pady=2)
        self.refresh_hotkey_labels()

        files = self.card(right, "▰   Gerenciamento de Gravações")
        files.pack(fill="x", pady=(8, 0))
        for caption, action in (("▣    Salvar Gravação", self.save_recording), ("▰    Carregar Gravação", self.load_recording),
                                ("▤    Excluir Gravação", self.delete_recording), ("▰    Abrir Pasta de Gravações", self.open_recordings_folder)):
            self.btn(files, caption, "#071b34", action, pady=6, anchor="w",
                     highlightthickness=1, highlightbackground="#0875b9").pack(fill="x", padx=8, pady=3)

        quick = self.card(right, "ϟ   Atalhos Rápidos")
        quick.pack(fill="x", pady=(8, 0))
        for title, key in (("Abrir / Fechar Painel", "G"), ("Mostrar Pasta de Gravações", "F"), ("Configurações", "C")):
            row = tk.Frame(quick, bg="#071930")
            row.pack(fill="x", padx=8, pady=2)
            self.label(row, title, font=("Segoe UI", 8)).pack(side="left", padx=4)
            self.label(row, f"Ctrl + Alt + {key}", bg="#0b2541", font=("Segoe UI", 8, "bold")).pack(side="right", padx=3, pady=3)
        tip = self.card(right, "ⓘ   Dica")
        tip.pack(fill="x", pady=(8, 0))
        self.label(tip, "Edite os atalhos de teclado na aba Atalhos.", fg="#86caff", wraplength=220).pack(anchor="w", padx=10, pady=(0, 6))

    def open_settings(self):
        self.settings_card.focus_set()
        self.settings_card.configure(highlightbackground="#42caff")
        self.root.after(700, lambda: self.settings_card.configure(highlightbackground="#07528a"))

    def focus_home(self):
        self.controls["record"].focus_set()

    def toggle(self, parent, caption, var):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", padx=4, pady=2)
        self.label(row, caption, font=("Segoe UI", 8)).pack(side="left")
        switch = tk.Canvas(row, width=36, height=19, bg=row.cget("bg"), highlightthickness=0,
                           takefocus=True, cursor="hand2")
        switch.pack(side="right", padx=(4, 0))

        def refresh(*_):
            switch.delete("all")
            color = "#0799ed" if var.get() else "#1b3c5c"
            switch.create_line(9, 9, 27, 9, width=17, fill=color, capstyle="round")
            x = 26 if var.get() else 10
            switch.create_oval(x - 7, 2, x + 7, 16, fill="#f1faff", outline="")

        def change(event):
            var.set(not var.get())
            self.save_quick()

        for sequence in ("<ButtonRelease-1>", "<Return>", "<space>"):
            switch.bind(sequence, change)
        var.trace_add("write", refresh)
        refresh()

    def spin(self, parent, caption, var, maximum):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", pady=2)
        self.label(row, caption, font=("Segoe UI", 8)).pack(side="left")
        field = tk.Spinbox(row, from_=0, to=maximum, increment=5, textvariable=var, width=6,
                           bg="#08223d", fg="white", buttonbackground="#13689a", command=self.save_quick)
        field.pack(side="right")
        field.bind("<FocusOut>", lambda _: self.save_quick())
        field.bind("<Return>", lambda _: self.save_quick())

    def refresh_hotkey_labels(self):
        for key, label in self.labels.items():
            shortcut = self.key_display(self.cfg["hotkeys"][key])
            self.key_labels[key].configure(text=shortcut)
            self.controls[key].shortcut = shortcut
            self.controls[key].repaint()

    def key_display(self,key):
        return key.replace("<","").replace(">","").replace("+","+").upper()

    def start_mouse_listener(self):
        if mouse is None: return
        self.mouse_listener=mouse.Listener(on_move=self.on_move,on_click=self.on_click,on_scroll=self.on_scroll)
        self.mouse_listener.daemon=True; self.mouse_listener.start()

    def record_event(self, kind, x, y, **details):
        movement, clicks, scroll, interval = self.record_options
        if not {"move": movement, "click": clicks, "scroll": scroll}[kind]:
            return
        with self.lock:
            if not self.recording or self.paused_at is not None:
                return
            elapsed = round(time.perf_counter() - self.record_start, 4)
            if kind == "move" and self.events and self.events[-1]["type"] == "move":
                if elapsed - self.events[-1]["t"] < interval:
                    return
            self.events.append(dict(type=kind, x=int(x), y=int(y), t=elapsed, **details))

    def on_move(self, x, y):
        self.record_event("move", x, y)

    def on_click(self, x, y, button, pressed):
        self.record_event("click", x, y, button=button.name, pressed=pressed)

    def on_scroll(self, x, y, dx, dy):
        self.record_event("scroll", x, y, dx=int(dx), dy=int(dy))

    def start_record(self):
        if self.playing:
            self.status.set("Pare a reprodução antes de gravar.")
            return
        if self.recording:
            return
        with self.lock:
            self.events = []
            self.record_start = time.perf_counter()
            self.paused_at = None
            self.recorded_keys.clear()
            self.capture_keys = self.keyboard_var.get()
            self.recording = True
        self.file_size = 0
        self.filename.set("Gravação nova")
        self.status.set("Gravando mouse e teclado…" if self.capture_keys else "Gravando mouse…")
        self.refresh_capture_indicator()
        self.update_info()

    def pause_toggle(self):
        if self.recording:
            with self.lock:
                if self.paused_at is None:
                    self.paused_at = time.perf_counter()
                    self.release_recorded_keys(self.paused_at)
                else:
                    self.record_start += time.perf_counter() - self.paused_at
                    self.paused_at = None
            self.status.set("Gravação pausada." if self.paused_at else "Gravação retomada.")
            self.refresh_capture_indicator()
        elif self.playing:
            if self.resume_event.is_set():
                self.resume_event.clear()
                self.status.set("Reprodução pausada.")
            else:
                self.resume_event.set()
                self.status.set("Reprodução retomada.")

    def recording_snapshot(self):
        with self.lock:
            events = list(self.events)
        return [event for event in events if not event.get("panel")]

    def mark_control_click(self):
        # A ação do botão ocorre após o pressionamento e a soltura registrados pelo hook.
        with self.lock:
            if not self.recording or not self.events:
                return
            now = time.perf_counter() - self.record_start
            for event in reversed(self.events):
                if now - event["t"] > 0.6:
                    break
                if event["type"] == "click" and event["button"] == "left":
                    event["panel"] = True
                    if event["pressed"]:
                        break

    def run_control(self, action):
        self.mark_control_click()
        action()

    def refresh_capture_indicator(self):
        if self.recording and self.paused_at is not None:
            text, color = "●  Gravação pausada", "#ffb347"
        elif self.recording:
            text = "●  Gravando mouse e teclado" if self.capture_keys else "●  Gravando mouse"
            color = "#ff476b"
        else:
            text, color = "●  Sistema online", "#00ecc0"
        self.capture_status.set(text)
        self.capture_indicator.configure(fg=color)

    def release_recorded_keys(self, now):
        elapsed = round(now - self.record_start, 4)
        for _, presses in reversed(list(self.recorded_keys.values())):
            if not presses[0].get("panel"):
                self.events.append({**presses[0], "pressed": False, "t": elapsed})
        self.recorded_keys.clear()

    def finish_record(self):
        with self.lock:
            if self.recording:
                self.release_recorded_keys(time.perf_counter())
            self.recording = False
            self.capture_keys = False
            self.paused_at = None
        self.refresh_capture_indicator()

    def play_record(self):
        if self.playing:
            return
        self.finish_record()
        events = self.recording_snapshot()
        if not events:
            self.status.set("Nenhuma gravação ativa. Grave ou carregue um arquivo.")
            return
        self.stop_event.clear()
        self.resume_event.set()
        self.playing = True
        repeat = bool(self.cfg["repeat_playback"])
        interval = self.cfg["repeat_interval_ms"] / 1000
        click_delay = self.cfg["click_delay_ms"] / 1000
        self.status.set("Reproduzindo gravação…")
        threading.Thread(target=self.play_worker, args=(events, repeat, interval, click_delay), daemon=True).start()

    def playback_wait(self, delay):
        remaining = delay
        while not self.stop_event.is_set():
            self.resume_event.wait()
            if self.stop_event.is_set():
                break
            if remaining <= 0:
                return True
            start = time.perf_counter()
            self.stop_event.wait(min(remaining, 0.016))
            remaining -= time.perf_counter() - start
        return False

    def play_worker(self, events, repeat, interval, click_delay):
        pressed = {}
        controller = None
        keys = None
        held_keys = {}
        result = "Reprodução concluída."
        try:
            controller = mouse.Controller()
            while not self.stop_event.is_set():
                previous = 0.0
                for event in events:
                    if not self.playback_wait(event["t"] - previous):
                        break
                    previous = event["t"]
                    kind = event["type"]
                    if kind == "key":
                        if keys is None:
                            keys = keyboard.Controller()
                        identity = event["encoding"], event["key"]
                        if event["pressed"]:
                            key = held_keys.get(identity) or decode_key(*identity)
                            keys.press(key)
                            held_keys[identity] = key
                        elif identity in held_keys:
                            keys.release(held_keys[identity])
                            del held_keys[identity]
                        continue
                    controller.position = event["x"], event["y"]
                    if kind == "click":
                        button = getattr(mouse.Button, event["button"])
                        if event["pressed"] and button not in pressed:
                            controller.press(button)
                            pressed[button] = None
                        elif not event["pressed"] and button in pressed:
                            controller.release(button)
                            del pressed[button]
                            if not self.playback_wait(click_delay):
                                break
                    elif kind == "scroll":
                        controller.scroll(event["dx"], event["dy"])
                while pressed:
                    button = next(iter(pressed))
                    controller.release(button)
                    del pressed[button]
                while held_keys:
                    identity = next(reversed(held_keys))
                    keys.release(held_keys[identity])
                    del held_keys[identity]
                if not repeat or not self.playback_wait(interval):
                    break
            if self.stop_event.is_set():
                result = "Reprodução parada."
        except Exception as error:
            result = f"Erro na reprodução: {error}"
        finally:
            for button in pressed:
                try:
                    controller.release(button)
                except OSError:
                    pass
            for key in reversed(held_keys.values()):
                try:
                    keys.release(key)
                except Exception:
                    pass
            self.ui_queue.put(lambda: self.play_finished(result))

    def play_finished(self, result):
        self.playing = False
        self.status.set(result)
        if self.pending_installer:
            self.launch_installer(self.pending_installer)
        elif self.closing:
            self.close()

    def stop_all(self):
        self.finish_record()
        self.stop_event.set()
        self.resume_event.set()
        self.status.set("Gravação/reprodução parada.")
        self.update_info()

    def update_info(self):
        with self.lock:
            count = len(self.events)
            last = self.events[-1]["t"] if count else 0
            points = [(event["x"], event["y"]) for event in self.events[-1500:] if event["type"] == "move"] if self.path_var.get() else []
        if self.recording:
            last = max(last, (self.paused_at or time.perf_counter()) - self.record_start)
        hours, remainder = divmod(int(last), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.duration.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        self.count.set(str(count))
        self.size.set(f"{getattr(self, 'file_size', 0) / 1024:.1f} KB" if getattr(self, "file_size", 0) else
                      (f"≈ {count * 61 / 1024:.1f} KB" if count else "0 KB"))
        canvas = self.path_canvas
        canvas.delete("all")
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        if len(points) < 2:
            canvas.create_text(width / 2, height / 2, text="▤", fill="#00aeff", font=("Segoe UI", 21))
            return
        xs, ys = zip(*points)
        left, top = min(xs), min(ys)
        scale = min(max(1, width - 16) / max(1, max(xs) - left), max(1, height - 12) / max(1, max(ys) - top))
        coords = [(8 + (x - left) * scale, 6 + (y - top) * scale) for x, y in points]
        canvas.create_line(coords, fill="#12c6ff", width=2)

    def save_quick(self):
        self.cfg.update(record_mouse_movement=self.move_var.get(), record_mouse_clicks=self.click_var.get(),
                        record_scroll=self.scroll_var.get(), show_mouse_path=self.path_var.get(),
                        repeat_playback=self.repeat_var.get(), mode=self.mode.get(),
                        record_keyboard=self.keyboard_var.get())
        for var, key, maximum in ((self.click_delay, "click_delay_ms", 2000),
                                  (self.interval, "repeat_interval_ms", 60000)):
            try:
                value = max(0, min(maximum, var.get()))
            except (tk.TclError, ValueError):
                value = self.cfg[key]
            self.cfg[key] = value
            var.set(value)
        self.sync_options()
        try:
            save_settings(self.cfg)
        except OSError as error:
            self.status.set(str(error))

    def sync_options(self):
        interval = {"Normal": 0.012, "Preciso": 0, "Leve": 0.035}.get(self.cfg["mode"], 0.012)
        self.record_options = self.move_var.get(), self.click_var.get(), self.scroll_var.get(), interval

    def save_recording(self):
        self.mark_control_click()
        self.finish_record()
        events = self.recording_snapshot()
        if not events:
            self.status.set("Não há eventos para salvar.")
            return
        path=filedialog.asksaveasfilename(initialdir=RECORDINGS_DIR,title="Salvar gravação",defaultextension=".json",filetypes=[("Gravação GhosttzzKBot","*.json")],initialfile="gravacao.json")
        if path:
            try:
                Path(path).write_text(json.dumps({"app":APP_NAME,"events":events},indent=2,ensure_ascii=False),encoding="utf-8")
                self.file_size = Path(path).stat().st_size
                self.filename.set(Path(path).name); self.status.set("Gravação salva.")
            except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def load_recording(self):
        if self.playing:
            self.status.set("Pare a reprodução antes de carregar outra gravação.")
            return
        self.finish_record()
        path=filedialog.askopenfilename(initialdir=RECORDINGS_DIR,title="Carregar gravação",filetypes=[("Gravação GhosttzzKBot","*.json")])
        if not path:return
        try:
            data=json.loads(Path(path).read_text(encoding="utf-8")); events=data.get("events",[])
            validate_events(events)
            self.file_size = Path(path).stat().st_size
            self.events=events; self.filename.set(Path(path).name); self.update_info(); self.status.set("Gravação carregada.")
        except Exception as e: messagebox.showerror(APP_NAME,f"Falha ao carregar: {e}")

    def delete_recording(self):
        path=filedialog.askopenfilename(initialdir=RECORDINGS_DIR,title="Excluir gravação",filetypes=[("Gravação GhosttzzKBot","*.json")])
        if path and messagebox.askyesno(APP_NAME,f"Excluir {Path(path).name}?"):
            try: os.remove(path); self.status.set("Arquivo excluído.")
            except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def edit_hotkeys(self, selected=None):
        win = tk.Toplevel(self.root)
        win.title("Editar atalhos")
        win.configure(bg="#061426")
        win.transient(self.root)
        win.grab_set()
        self.editing_shortcuts = True

        def close_dialog():
            self.editing_shortcuts = False
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_dialog)
        self.label(win, "Clique no campo e pressione o novo atalho.").pack(padx=18, pady=12)
        values = {}
        fields = {}

        def capture(event, key):
            name = event.keysym.lower()
            if name in {"tab", "iso_left_tab"}:
                return None
            if name.startswith(("control_", "shift_", "alt_", "meta_", "super_", "win_")):
                return "break"
            modifiers = [token for mask, token in ((4, "<ctrl>"), (1, "<shift>"), (0x20000, "<alt>"))
                         if event.state & mask]
            names = {"escape": "esc", "return": "enter", "prior": "page_up", "next": "page_down",
                     "backspace": "backspace", "delete": "delete", "space": "space"}
            base = f"<{names.get(name, name)}>" if len(name) > 1 else name
            shortcut = "+".join([*modifiers, base])
            try:
                keyboard.HotKey.parse(shortcut)
            except ValueError:
                return "break"
            values[key].set(self.key_display(shortcut))
            fields[key].shortcut = shortcut
            return "break"

        for key, label in self.labels.items():
            line = tk.Frame(win, bg="#061426")
            line.pack(fill="x", padx=18, pady=5)
            self.label(line, label, width=15, anchor="w").pack(side="left")
            shortcut = self.cfg["hotkeys"][key]
            values[key] = tk.StringVar(value=self.key_display(shortcut))
            field = tk.Entry(line, textvariable=values[key], width=24, state="readonly",
                             readonlybackground="#0a2545", fg="white", relief="flat")
            field.shortcut = shortcut
            field.bind("<KeyPress>", lambda event, name=key: capture(event, name))
            field.pack(side="right")
            fields[key] = field
        fields[selected or "record"].focus_set()

        def save():
            shortcuts = {key: field.shortcut for key, field in fields.items()}
            try:
                self.validate_shortcuts(shortcuts)
                config = {**self.cfg, "hotkeys": shortcuts}
                save_settings(config)
            except (OSError, ValueError) as error:
                messagebox.showerror(APP_NAME, str(error), parent=win)
                return
            self.cfg = config
            self.start_hotkeys()
            self.refresh_hotkey_labels()
            close_dialog()
            self.status.set("Atalhos atualizados.")

        self.btn(win, "Salvar atalhos", "#075aa4", save, pady=6).pack(pady=13)

    def validate_shortcuts(self, shortcuts):
        reserved = ["<ctrl>+<alt>+" + key for key in "gfc"]
        parsed = [frozenset(keyboard.HotKey.parse(value)) for value in (*shortcuts.values(), *reserved)]
        if len(set(parsed)) != len(parsed):
            raise ValueError("Escolha combinações diferentes dos outros atalhos do painel.")

    def dispatch_hotkey(self, action, shortcut):
        if self.editing_shortcuts:
            return
        with self.lock:
            for canonical, presses in self.recorded_keys.values():
                if canonical in shortcut:
                    for event in presses:
                        event["panel"] = True
        self.ui_queue.put(action)

    def record_key(self, key, canonical, pressed):
        identity = encode_key(key)
        if identity is None:
            return
        with self.lock:
            if not self.recording or not self.capture_keys or self.paused_at is not None:
                return
            if identity[0] == "char" and identity[1].isascii() and identity[1].isalpha():
                identity = "char", identity[1].lower()
            active = self.recorded_keys.get(identity)
            if not pressed and active is None:
                return
            if active is None:
                active = canonical, []
                self.recorded_keys[identity] = active
            encoding, value = identity
            event = dict(type="key", encoding=encoding, key=value, pressed=pressed,
                         t=round(time.perf_counter() - self.record_start, 4))
            presses = active[1]
            if presses and presses[0].get("panel"):
                event["panel"] = True
            self.events.append(event)
            if pressed:
                presses.append(event)
            else:
                del self.recorded_keys[identity]

    def start_hotkeys(self):
        try:
            self.validate_shortcuts(self.cfg["hotkeys"])
        except (AttributeError, TypeError, ValueError):
            self.cfg["hotkeys"] = dict(DEFAULTS["hotkeys"])
            self.refresh_hotkey_labels()
            self.status.set("Atalhos inválidos em settings.json. Foram usados F5 a F8.")
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        actions = {
            self.cfg["hotkeys"]["record"]: self.start_record,
            self.cfg["hotkeys"]["pause"]: self.pause_toggle,
            self.cfg["hotkeys"]["play"]: self.play_record,
            self.cfg["hotkeys"]["stop"]: self.stop_all,
            "<ctrl>+<alt>+g": self.toggle_window,
            "<ctrl>+<alt>+f": self.open_recordings_folder,
            "<ctrl>+<alt>+c": self.open_settings,
        }
        hotkeys = []
        for shortcut, action in actions.items():
            keys = keyboard.HotKey.parse(shortcut)
            hotkeys.append(keyboard.HotKey(keys, lambda fn=action, chord=keys: self.dispatch_hotkey(fn, chord)))

        def handle(key, injected, pressed):
            if key is None or injected:
                return
            canonical = listener.canonical(key)
            if not self.editing_shortcuts:
                self.record_key(key, canonical, pressed)
            for hotkey in hotkeys:
                if pressed:
                    hotkey.press(canonical)
                else:
                    hotkey.release(canonical)

        listener = keyboard.Listener(on_press=lambda key, injected: handle(key, injected, True),
                                     on_release=lambda key, injected: handle(key, injected, False))
        self.hotkey_listener = listener
        listener.start()

    def toggle_window(self):
        if self.root.state() in {"withdrawn", "iconic"}:self.root.deiconify();self.root.lift()
        else:self.root.withdraw()
    def open_folder(self, folder):
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.root)

    def open_recordings_folder(self):
        self.open_folder(RECORDINGS_DIR)

    def show_config_path(self):
        self.open_folder(CONFIG_DIR)

    def edit_theme(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Temas")
        dialog.configure(bg="#041020")
        dialog.transient(self.root)
        self.label(dialog, "Imagens do painel", font=("Segoe UI", 13, "bold")).pack(padx=20, pady=14)
        for role, caption in (("banner", "Banner central"), ("lateral", "Barra lateral"),
                              ("cabecalho", "Cabeçalho"), ("icone", "Imagem do ícone")):
            self.btn(dialog, caption, "#0a3155", lambda name=role: self.import_art(name), anchor="w").pack(fill="x", padx=15, pady=3)
        self.btn(dialog, "Abrir pasta config", "#0a3155", self.show_config_path).pack(fill="x", padx=15, pady=10)

    def import_art(self, role):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp")])
        if not path:
            return
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
                image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                image.save(CONFIG_DIR / f"{role}.png")
                if role == "icone":
                    image.thumbnail((256, 256), Image.Resampling.LANCZOS)
                    icon = Image.new("RGBA", (256, 256))
                    icon.alpha_composite(image, ((256 - image.width) // 2, (256 - image.height) // 2))
                    icon.save(CONFIG_DIR / "icone.ico")
            messagebox.showinfo(APP_NAME, "Imagem salva. Reabra o painel para aplicar.", parent=self.root)
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.root)

    def about(self):
        messagebox.showinfo("Sobre GhosttzzKBot", f"{APP_NAME} v{VERSION}\nGravador e reprodutor de mouse.", parent=self.root)
        self.check_update(interactive=True)

    def check_update(self, interactive=False):
        if self.update_busy:
            return
        self.update_busy = True

        def worker():
            try:
                result = find_update(CONFIG_DIR, VERSION)
            except Exception as error:
                self.ui_queue.put(lambda message=str(error): self.update_checked(None, interactive, message))
            else:
                self.ui_queue.put(lambda: self.update_checked(result, interactive))

        threading.Thread(target=worker, daemon=True).start()

    def update_checked(self, result, interactive, error=None):
        self.update_busy = False
        if result:
            self.offer_update(*result)
        elif interactive:
            text = f"Não foi possível consultar a atualização.\n{error}" if error else "Você está na versão mais recente."
            messagebox.showinfo(APP_NAME, text, parent=self.root)

    def offer_update(self, version, target):
        if not messagebox.askyesno(APP_NAME, f"A versão {version} está disponível. Atualizar agora?", parent=self.root):
            return
        if isinstance(target, Path):
            self.prepare_install(target)
            return
        self.update_busy = True
        dialog = tk.Toplevel(self.root)
        dialog.title("Atualizando GhosttzzKBot")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        dialog.configure(bg="#041020")
        self.label(dialog, f"Baixando a versão {version}…").pack(padx=30, pady=(18, 8))
        bar = ttk.Progressbar(dialog, length=275, maximum=100)
        bar.pack(padx=24, pady=(0, 18))

        def worker():
            def progress(percent):
                self.ui_queue.put(lambda: bar.configure(value=percent))

            try:
                installer = download_installer(target, DATA_DIR / "updates", progress)
            except Exception as error:
                self.ui_queue.put(lambda message=str(error): self.download_finished(dialog, None, message))
            else:
                self.ui_queue.put(lambda: self.download_finished(dialog, installer))

        threading.Thread(target=worker, daemon=True).start()

    def download_finished(self, dialog, installer, error=None):
        dialog.destroy()
        self.update_busy = False
        if error:
            messagebox.showerror(APP_NAME, f"Falha ao baixar a atualização.\n{error}", parent=self.root)
        else:
            self.prepare_install(installer)

    def prepare_install(self, installer):
        self.stop_all()
        if self.playing:
            self.pending_installer = installer
        else:
            self.launch_installer(installer)

    def launch_installer(self, installer):
        self.pending_installer = None
        try:
            subprocess.Popen([str(installer), "/SILENT", "/NORESTART", "/GHOST_UPDATE"],
                             cwd=installer.parent)
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Falha ao abrir o instalador.\n{error}", parent=self.root)
            return
        self.close()

    def tick(self):
        for _ in range(100):
            try:
                action = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            action()
            if self.closing and not self.playing:
                return
        self.update_info()
        self.root.after(140, self.tick)

    def close(self):
        self.closing = True
        self.stop_all()
        for listener in (self.mouse_listener, self.hotkey_listener):
            if listener:
                listener.stop()
        if not self.playing:
            self.root.destroy()

def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    root=tk.Tk()
    if mouse is None or keyboard is None:
        root.withdraw(); messagebox.showerror(APP_NAME,"Instale as dependências com:\npython -m pip install -r requirements.txt"); root.destroy(); return
    GhosttzzKBot(root); root.mainloop()
if __name__=="__main__":main()
