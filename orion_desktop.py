import ctypes
import math
import queue
import random
import threading
import time
import tkinter as tk
from ctypes import wintypes

from main import run_orion
from utils import interface_bridge


PROGMAN_SPAWN_WORKER = 0x052C
GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
SPI_GETWORKAREA = 0x0030
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
HWND_BOTTOM = 1

BG = "#060402"
PANEL = "#140b04"
LINE = "#6e3c18"
ACCENT = "#ffb14b"
TEXT = "#ffe1b3"
MUTED = "#9f6f43"
LEFT_SAFE_MARGIN = 240
TOP_SAFE_MARGIN = 8
BOTTOM_SAFE_MARGIN = 18
RIGHT_SAFE_MARGIN = 18

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _start_backend():
    thread = threading.Thread(target=run_orion, daemon=True, name="orion-backend")
    thread.start()
    return thread


def _get_work_area() -> tuple[int, int, int, int]:
    rect = RECT()
    success = user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    if success:
        return rect.left, rect.top, rect.right, rect.bottom
    root = tk.Tk()
    root.withdraw()
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    root.destroy()
    return 0, 0, width, height


def _spawn_workerw():
    progman = user32.FindWindowW("Progman", None)
    if progman:
        result = wintypes.DWORD()
        user32.SendMessageTimeoutW(
            progman,
            PROGMAN_SPAWN_WORKER,
            0,
            0,
            0,
            1000,
            ctypes.byref(result),
        )


def _find_desktop_workerw() -> int:
    _spawn_workerw()
    workerw = 0

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, lparam):
        nonlocal workerw
        shell_view = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if shell_view:
            candidate = user32.FindWindowExW(0, hwnd, "WorkerW", None)
            if candidate:
                workerw = candidate
                return False
        return True

    user32.EnumWindows(callback, 0)
    if workerw:
        return workerw

    progman = user32.FindWindowW("Progman", None)
    return progman or 0


class OrionWallpaper:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ORION Wallpaper")
        self.root.configure(bg=BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", False)

        work_left, work_top, work_right, work_bottom = _get_work_area()
        self.screen_x = work_left + LEFT_SAFE_MARGIN
        self.screen_y = work_top + TOP_SAFE_MARGIN
        self.screen_w = max(900, (work_right - work_left) - LEFT_SAFE_MARGIN - RIGHT_SAFE_MARGIN)
        self.screen_h = max(620, (work_bottom - work_top) - TOP_SAFE_MARGIN - BOTTOM_SAFE_MARGIN)
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+{self.screen_x}+{self.screen_y}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_w,
            height=self.screen_h,
            bg=BG,
            bd=0,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.state_queue: queue.Queue = queue.Queue()
        self.state = "idle"
        self.message = "Sistema em espera."
        self.angle = 0.0
        self.sweep_angle = 0.0
        self.particles = self._seed_particles()

        self._draw_static()
        interface_bridge.register_listener(self._on_state)

        self.root.after(40, self._tick)
        self.root.after(300, self._embed_into_desktop)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _seed_particles(self):
        cx = self.screen_w * 0.5
        cy = self.screen_h * 0.52
        base_radius = min(self.screen_w, self.screen_h) * 0.22
        particles = []
        for _ in range(260):
            particles.append({
                "angle": random.random() * math.pi * 2,
                "radius": base_radius + random.uniform(-120, 120),
                "speed": random.uniform(0.002, 0.008),
                "size": random.uniform(0.8, 2.6),
                "alpha": random.uniform(0.18, 0.7),
                "cx": cx,
                "cy": cy,
            })
        return particles

    def _draw_static(self):
        self.canvas.delete("static")
        pad = 28
        self.canvas.create_rectangle(
            pad,
            pad,
            self.screen_w - pad,
            self.screen_h - pad,
            outline="#5f3312",
            width=1,
            tags="static",
        )

        header_x1 = self.screen_w * 0.18
        header_x2 = self.screen_w * 0.84
        header_y1 = 34
        header_y2 = 102
        self.canvas.create_rectangle(header_x1, header_y1, header_x2, header_y2, outline=LINE, width=1, fill=PANEL, tags="static")
        self.canvas.create_oval(header_x1 + 18, header_y1 + 24, header_x1 + 34, header_y1 + 40, fill=ACCENT, outline="", tags="static")
        self.canvas.create_text(header_x1 + 46, header_y1 + 38, text="ORION CORE", fill=TEXT, anchor="w", font=("Orbitron", 22, "bold"), tags="static")
        self.canvas.create_text(header_x2 - 210, header_y1 + 38, text="STATE", fill=TEXT, anchor="w", font=("Orbitron", 20, "bold"), tags="static")
        self.state_box = self.canvas.create_rectangle(header_x2 - 126, header_y1 + 18, header_x2 - 18, header_y2 - 14, outline="#88511f", width=1, fill="#2a1809")
        self.state_text = self.canvas.create_text(header_x2 - 72, header_y1 + 38, text="IDLE", fill=TEXT, font=("Orbitron", 22, "bold"))

        footer_x1 = self.screen_w * 0.18
        footer_x2 = self.screen_w * 0.84
        footer_y1 = self.screen_h - 110
        footer_y2 = self.screen_h - 22
        self.canvas.create_rectangle(footer_x1, footer_y1, footer_x2, footer_y2, outline=LINE, width=1, fill=PANEL, tags="static")
        self.canvas.create_text(footer_x1 + 20, footer_y1 + 30, text="VISUAL LINK", fill=TEXT, anchor="w", font=("Orbitron", 22, "bold"), tags="static")
        self.message_text = self.canvas.create_text(footer_x1 + 20, footer_y1 + 68, text=self.message, fill=MUTED, anchor="w", font=("Rajdhani", 20))
        self.connection_box = self.canvas.create_rectangle(footer_x2 - 126, footer_y1 + 14, footer_x2 - 18, footer_y1 + 46, outline="#88511f", width=1, fill="#2a1809")
        self.connection_text = self.canvas.create_text(footer_x2 - 72, footer_y1 + 30, text="ONLINE", fill=TEXT, font=("Orbitron", 18, "bold"))

        cx = self.screen_w * 0.5
        cy = self.screen_h * 0.52
        self.canvas.create_line(cx - 470, cy, cx + 470, cy, fill="#5a3111", width=1, tags="static")
        self.canvas.create_line(cx, cy - 300, cx, cy + 300, fill="#5a3111", width=1, tags="static")

        self.ring_ids = []
        for radius, color in [
            (330, "#2e190b"),
            (286, "#4a2810"),
            (244, "#613616"),
            (202, "#6d3b16"),
            (162, "#7f4819"),
            (124, "#8f541f"),
        ]:
            ring = self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=color, width=1)
            self.ring_ids.append(ring)

        self.spoke_ids = [self.canvas.create_line(0, 0, 0, 0, fill="#70401b", width=1) for _ in range(24)]
        self.sweep_ids = [
            self.canvas.create_arc(
                cx - 300, cy - 300, cx + 300, cy + 300,
                start=0, extent=18, outline="#a86424", style=tk.ARC, width=3
            ),
            self.canvas.create_arc(
                cx - 250, cy - 250, cx + 250, cy + 250,
                start=120, extent=14, outline="#d38a34", style=tk.ARC, width=2
            ),
        ]
        self.particle_ids = [self.canvas.create_oval(0, 0, 0, 0, fill=ACCENT, outline="") for _ in self.particles]
        self.core_glow_outer = self.canvas.create_oval(cx - 126, cy - 126, cx + 126, cy + 126, fill="#7d4f1b", outline="", stipple="gray25")
        self.core_glow = self.canvas.create_oval(cx - 100, cy - 100, cx + 100, cy + 100, fill="#f8bb5a", outline="", stipple="gray50")
        self.core_outer = self.canvas.create_oval(cx - 44, cy - 44, cx + 44, cy + 44, outline="#ffd777", width=8)
        self.core_inner = self.canvas.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, outline="#ffe39e", fill="", width=7, joinstyle=tk.ROUND)

    def _embed_into_desktop(self):
        host = _find_desktop_workerw()
        if not host:
            return

        hwnd = self.root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        user32.SetParent(hwnd, host)
        user32.SetWindowPos(
            hwnd,
            HWND_BOTTOM,
            0,
            0,
            self.screen_w,
            self.screen_h,
            SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED,
        )

    def _on_state(self, payload: dict):
        self.state_queue.put(payload)

    def _consume_state(self):
        changed = False
        while not self.state_queue.empty():
            payload = self.state_queue.get_nowait()
            self.state = payload.get("estado", "idle")
            self.message = payload.get("mensagem") or "Sistema em espera."
            changed = True
        if changed:
            self.canvas.itemconfigure(self.state_text, text=self.state.upper())
            self.canvas.itemconfigure(self.message_text, text=self.message[:110])

    def _energy(self):
        if self.state == "falando":
            return 1.35
        if self.state == "pensando":
            return 1.12
        if self.state == "ouvindo":
            return 1.22
        if self.state == "erro":
            return 0.8
        return 0.95

    def _tick(self):
        self._consume_state()
        self.angle += 0.034 * self._energy()
        self.sweep_angle += 1.8 * self._energy()
        cx = self.screen_w * 0.5
        cy = self.screen_h * 0.52
        energy = self._energy()

        for index, spoke in enumerate(self.spoke_ids):
            angle = self.angle + (index * (math.pi * 2 / len(self.spoke_ids)))
            radius = 330 + math.sin(self.angle * 1.2 + index) * 22
            x2 = cx + math.cos(angle) * radius
            y2 = cy + math.sin(angle) * radius
            self.canvas.coords(spoke, cx, cy, x2, y2)

        for idx, sweep in enumerate(self.sweep_ids):
            start = (self.sweep_angle + idx * 110) % 360
            extent = 20 if idx == 0 else 14
            self.canvas.itemconfigure(sweep, start=start, extent=extent)

        for particle, item in zip(self.particles, self.particle_ids):
            particle["angle"] += particle["speed"] * energy
            wobble = math.sin(self.angle * 2.6 + particle["radius"] * 0.03) * 16 * energy
            x = particle["cx"] + math.cos(particle["angle"]) * (particle["radius"] + wobble)
            y = particle["cy"] + math.sin(particle["angle"]) * (particle["radius"] + wobble)
            size = particle["size"] * energy
            self.canvas.coords(item, x - size, y - size, x + size, y + size)

        glow_size = 126 + math.sin(self.angle * 1.8) * 20 * energy
        self.canvas.coords(self.core_glow_outer, cx - glow_size, cy - glow_size, cx + glow_size, cy + glow_size)
        inner_glow = 100 + math.sin(self.angle * 2.2) * 14 * energy
        self.canvas.coords(self.core_glow, cx - inner_glow, cy - inner_glow, cx + inner_glow, cy + inner_glow)

        core_size = 34 + math.sin(self.angle * 3.2) * 10 * energy
        self.canvas.coords(self.core_outer, cx - core_size, cy - core_size, cx + core_size, cy + core_size)

        square = 26 + math.sin(self.angle * 3.2) * 6
        points = []
        for idx in range(4):
            angle = self.angle * 1.4 + math.pi / 4 + idx * math.pi / 2
            points.extend([
                cx + math.cos(angle) * square,
                cy + math.sin(angle) * square,
            ])
        self.canvas.coords(self.core_inner, *points)

        if self.state == "falando":
            fill = "#3b220e"
        elif self.state == "pensando":
            fill = "#2c1a0b"
        elif self.state == "ouvindo":
            fill = "#33200d"
        elif self.state == "erro":
            fill = "#3a120d"
        else:
            fill = "#2a1809"
        self.canvas.itemconfigure(self.state_box, fill=fill)

        self.root.after(33, self._tick)

    def close(self):
        interface_bridge.unregister_listener(self._on_state)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    _start_backend()
    time.sleep(1.8)
    OrionWallpaper().run()


if __name__ == "__main__":
    main()
