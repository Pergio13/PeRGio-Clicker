#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PeRGio Clicker — Core App (Ελληνικά)
- Διάστημα σε ΛΕΠΤΑ (interval_minutes) στο coords_minutes.json δίπλα στο exe/py.
- ΜΟΝΟ αριστερό κλικ.
- Scroll & τυχαία μετακίνηση σε ΤΥΧΑΙΕΣ στιγμές ανάμεσα στα κλικ.
- Start delay και αυτόματη ελαχιστοποίηση στην έναρξη.
- Ttk theme για πιο όμορφο UI.
"""
import json, os, random, threading, time, sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# auto-install dependencies only when running as .py
import importlib.util, subprocess
def _ensure(pkg):
    if importlib.util.find_spec(pkg) is None and not getattr(sys, "frozen", False):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        except Exception:
            pass

_ensure("pyautogui")
import pyautogui

pyautogui.FAILSAFE = True  # πάνω-αριστερή γωνία = stop

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "coords_minutes.json"
ICON_PATH = APP_DIR / "icon.ico"

DEFAULTS = {
    "x": None,
    "y": None,
    "interval_minutes": 1.0,
    "scroll": -200,
    "move_jitter": 20,
    "start_delay_sec": 5
}

class Config:
    def __init__(self, path: Path):
        self.path = path
        self._mtime = None
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        d = {}
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        merged = dict(DEFAULTS)
        merged.update(d)
        # migration από interval (δευτ.) -> interval_minutes
        if "interval_minutes" not in merged and "interval" in merged:
            try:
                secs = float(merged.get("interval", 60))
                merged["interval_minutes"] = max(0.01, secs/60.0)
            except Exception:
                merged["interval_minutes"] = DEFAULTS["interval_minutes"]
        self.data = merged
        try:
            self._mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._mtime = None
            self.save()

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self._mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._mtime = None

    def reload_if_changed(self):
        try:
            m = self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if self._mtime is None:
            self._mtime = m
            return False
        if m != self._mtime:
            self.load()
            return True
        return False

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PeRGio Clicker")
        try:
            if ICON_PATH.exists():
                self.root.iconbitmap(str(ICON_PATH))
        except Exception:
            pass

        # ttk theme
        try:
            style = ttk.Style()
            if "vista" in style.theme_names():
                style.theme_use("vista")
            else:
                style.theme_use(style.theme_names()[0])
            style.configure("TButton", padding=6)
            style.configure("TLabel", padding=2)
            style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        except Exception:
            pass

        self.cfg = Config(CONFIG_PATH)
        self.running = False
        self.watcher_run = True

        # UI
        container = ttk.Frame(root, padding=10)
        container.pack(fill="both", expand=True)

        header = ttk.Label(container, text="Ρυθμίσεις PeRGio Clicker", style="Header.TLabel")
        header.pack(anchor="w", pady=(0,6))

        self.coord_lbl = ttk.Label(container, text=self._coord_text())
        self.coord_lbl.pack(anchor="w", pady=(0,6))

        btn_row = ttk.Frame(container)
        btn_row.pack(anchor="w", pady=(0,8))
        ttk.Button(btn_row, text="Ορισμός Σημείου Κλικ", command=self.set_point).grid(row=0, column=0, padx=(0,8))

        form = ttk.Frame(container)
        form.pack(anchor="w", pady=(0,8))

        ttk.Label(form, text="Διάστημα (λεπτά):").grid(row=0, column=0, sticky="e", padx=(0,6), pady=3)
        self.interval_entry = ttk.Entry(form, width=8)
        self.interval_entry.grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(form, text="Scroll:").grid(row=1, column=0, sticky="e", padx=(0,6), pady=3)
        self.scroll_entry = ttk.Entry(form, width=8)
        self.scroll_entry.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(form, text="Τυχαία Μετακίνηση (px):").grid(row=2, column=0, sticky="e", padx=(0,6), pady=3)
        self.jitter_entry = ttk.Entry(form, width=8)
        self.jitter_entry.grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(form, text="Καθυστέρηση εκκίνησης (sec):").grid(row=3, column=0, sticky="e", padx=(0,6), pady=3)
        self.delay_entry = ttk.Entry(form, width=8)
        self.delay_entry.grid(row=3, column=1, sticky="w", pady=3)

        self._refresh_form()

        run_row = ttk.Frame(container)
        run_row.pack(anchor="w", pady=(8,0))
        self.start_btn = ttk.Button(run_row, text="Έναρξη", command=self.start)
        self.start_btn.grid(row=0, column=0, padx=(0,8))
        self.stop_btn  = ttk.Button(run_row, text="Παύση", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=1)

        self.status = ttk.Label(container, text="Έτοιμο")
        self.status.pack(anchor="w", pady=(8,0))

        # JSON watcher
        threading.Thread(target=self._watcher, daemon=True).start()

        # καθάρισμα
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _coord_text(self):
        x, y = self.cfg.data.get("x"), self.cfg.data.get("y")
        if x is None or y is None:
            return "Συντεταγμένες κλικ: δεν ορίστηκαν"
        return f"Συντεταγμένες κλικ: ({x}, {y})"

    def _refresh_form(self):
        self.coord_lbl.config(text=self._coord_text())
        self.interval_entry.delete(0, tk.END)
        self.interval_entry.insert(0, str(self.cfg.data.get("interval_minutes", 1.0)))
        self.scroll_entry.delete(0, tk.END)
        self.scroll_entry.insert(0, str(self.cfg.data.get("scroll", -200)))
        self.jitter_entry.delete(0, tk.END)
        self.jitter_entry.insert(0, str(self.cfg.data.get("move_jitter", 20)))
        self.delay_entry.delete(0, tk.END)
        self.delay_entry.insert(0, str(self.cfg.data.get("start_delay_sec", 5)))

    def _save_form(self):
        try:
            minutes = float(self.interval_entry.get())
            scroll  = int(self.scroll_entry.get())
            jitter  = int(self.jitter_entry.get())
            delay   = int(self.delay_entry.get())
        except Exception:
            messagebox.showerror("Λάθος τιμές", "Έλεγξε ότι τα πεδία περιέχουν σωστούς αριθμούς.")
            return False
        self.cfg.data.update({
            "interval_minutes": minutes,
            "scroll": scroll,
            "move_jitter": jitter,
            "start_delay_sec": delay
        })
        self.cfg.save()
        return True

    def set_point(self):
        self.status.config(text="Μετακίνησε το ποντίκι. Καταγραφή σε 5δ")
        self.root.after(5000, self._capture)

    def _capture(self):
        x, y = pyautogui.position()
        self.cfg.data["x"] = int(x)
        self.cfg.data["y"] = int(y)
        self.cfg.save()
        self._refresh_form()
        self.status.config(text=f"Αποθηκεύτηκε σημείο: ({x}, {y})")

    def start(self):
        if self.cfg.data.get("x") is None or self.cfg.data.get("y") is None:
            messagebox.showwarning("Έλλειψη στοιχείων", "Ορίστε πρώτα σημείο κλικ.")
            return
        if not self._save_form():
            return
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status.config(text="Ξεκινάει...")
        # ελαχιστοποίηση και καθυστέρηση
        try:
            self.root.iconify()
        except Exception:
            pass
        delay = int(self.cfg.data.get("start_delay_sec", 5))
        threading.Thread(target=self._run_loop, args=(delay,), daemon=True).start()

    def stop(self):
        self.running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status.config(text="Παύση")

    def on_close(self):
        self.watcher_run = False
        self.running = False
        self.root.after(100, self.root.destroy)

    def _run_loop(self, start_delay):
        time.sleep(max(0, start_delay))
        self.running = True
        interval_sec = max(0.1, float(self.cfg.data.get("interval_minutes", 1.0)) * 60.0)
        jitter = int(self.cfg.data.get("move_jitter", 20))
        scroll_amt = int(self.cfg.data.get("scroll", -200))
        x = int(self.cfg.data.get("x"))
        y = int(self.cfg.data.get("y"))

        def click_safe(cx, cy):
            try:
                if self.root.state() == "iconic":
                    pyautogui.click(x=cx, y=cy, button="left")
                    return
                wx = self.root.winfo_rootx()
                wy = self.root.winfo_rooty()
                ww = self.root.winfo_width()
                wh = self.root.winfo_height()
                if wx <= cx <= wx+ww and wy <= cy <= wy+wh:
                    return
                pyautogui.click(x=cx, y=cy, button="left")
            except Exception:
                pyautogui.click(x=cx, y=cy, button="left")

        while self.running:
            t0 = time.time()
            did_scroll = False
            did_move = False

            click_safe(x, y)

            # τυχαίες στιγμές για scroll & μετακίνηση
            t_scroll = random.uniform(0.2, max(0.3, interval_sec * 0.6)) if scroll_amt != 0 else None
            t_move   = random.uniform(0.2, max(0.3, interval_sec * 0.9)) if jitter > 0 else None

            while self.running:
                elapsed = time.time() - t0
                remaining = interval_sec - elapsed
                if remaining <= 0:
                    break

                if t_scroll is not None and (not did_scroll) and elapsed >= t_scroll:
                    try:
                        pyautogui.scroll(scroll_amt)
                    except Exception:
                        pass
                    did_scroll = True

                if t_move is not None and (not did_move) and elapsed >= t_move:
                    try:
                        ox = random.randint(-jitter, jitter)
                        oy = random.randint(-jitter, jitter)
                        pyautogui.moveRel(ox, oy, duration=0.2)
                    except Exception:
                        pass
                    did_move = True

                time.sleep(0.05)

        self.root.after(0, lambda: (self.start_btn.config(state="normal"), self.stop_btn.config(state="disabled"), self.status.config(text="Παύση")))

    def _watcher(self):
        while self.watcher_run:
            time.sleep(2.0)
            try:
                if self.cfg.reload_if_changed():
                    self.root.after(0, self._refresh_form)
                    self.root.after(0, lambda: self.status.config(text="Οι ρυθμίσεις ενημερώθηκαν."))
            except Exception:
                pass

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
