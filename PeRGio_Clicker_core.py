#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PeRGio Clicker — Core App (V3.0 - Profiles, Sequences, Click Types, Hotkeys)
"""
import json, os, random, threading, time, sys
from pathlib import Path
import tkinter as tk

# ---------- AUTO-INSTALL DEPENDENCIES ----------
import importlib.util, subprocess
def _ensure(pkg):
    if importlib.util.find_spec(pkg) is None:
        try: subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        except Exception: pass

_ensure("pyautogui")
_ensure("customtkinter")
_ensure("keyboard")

import pyautogui
import customtkinter as ctk
import keyboard
from tkinter import messagebox, simpledialog

pyautogui.FAILSAFE = False

# Paths
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "coords_minutes.json"
ICON_PATH = APP_DIR / "icon.ico"

DEFAULTS = {
    "points": [],
    "interval_minutes": 1.0, 
    "use_random_timing": False,
    "scroll": -100, 
    "move_jitter": 15, 
    "start_delay_sec": 5,
    "click_type": "Αριστερό" # Αριστερό, Δεξί, Διπλό
}

# --- TOOLTIP CLASS ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x, y, _cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("tahoma", "9", "normal"), padx=5, pady=2)
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw: tw.destroy()

class Config:
    def __init__(self, path: Path):
        self.path = path
        self._mtime = None
        self.raw_data = {"profiles": {"Default": dict(DEFAULTS)}, "current_profile": "Default"}
        self.load()

    @property
    def data(self):
        cp = self.raw_data.get("current_profile", "Default")
        if cp not in self.raw_data.get("profiles", {}):
            self.raw_data["profiles"][cp] = dict(DEFAULTS)
        return self.raw_data["profiles"][cp]

    def load(self):
        if self.path.exists():
            try: 
                d = json.loads(self.path.read_text(encoding="utf-8"))
                # Migration check from old format to new Multiple-Profiles format
                if "profiles" not in d:
                    old_profile = dict(DEFAULTS)
                    old_profile.update(d)
                    
                    if "x" in old_profile and "y" in old_profile and old_profile["x"] is not None:
                        old_profile["points"] = [{"x": old_profile.pop("x"), "y": old_profile.pop("y")}]
                    elif "points" not in old_profile:
                        old_profile["points"] = []
                    
                    self.raw_data = {"profiles": {"Default": old_profile}, "current_profile": "Default"}
                else:
                    self.raw_data = d
            except Exception: pass
            
        cp = self.raw_data.get("current_profile", "Default")
        if cp not in self.raw_data["profiles"]:
            self.raw_data["profiles"][cp] = dict(DEFAULTS)
        else:
            for k, v in DEFAULTS.items():
                if k not in self.raw_data["profiles"][cp]:
                    self.raw_data["profiles"][cp][k] = v

        try: self._mtime = self.path.stat().st_mtime
        except FileNotFoundError: self._mtime = None; self.save()

    def save(self):
        self.path.write_text(json.dumps(self.raw_data, ensure_ascii=False, indent=2), encoding="utf-8")
        try: self._mtime = self.path.stat().st_mtime
        except FileNotFoundError: self._mtime = None

    def reload_if_changed(self):
        try: m = self.path.stat().st_mtime
        except FileNotFoundError: return False
        if self._mtime is None or m != self._mtime:
            self.load(); return True
        return False

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("PeRGio Clicker")
        self.geometry("520x620")
        
        try:
            if ICON_PATH.exists(): self.iconbitmap(str(ICON_PATH))
        except Exception: pass

        self.cfg = Config(CONFIG_PATH)
        self.running = False; self.watcher_run = True

        self.grid_columnconfigure(0, weight=1)
        
        # Header
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(top_frame, text="PeRGio Clicker", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(top_frame, text="Hotkeys: F6 (Start), F7 (Stop)", font=ctk.CTkFont(size=11), text_color="gray").pack(side="right", padx=10, pady=10)

        # Profiles
        self.prof_frame = ctk.CTkFrame(self)
        self.prof_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(self.prof_frame, text="Προφίλ:").pack(side="left", padx=(10,5), pady=10)
        self.prof_var = ctk.StringVar(value=self.cfg.raw_data["current_profile"])
        self.prof_menu = ctk.CTkOptionMenu(self.prof_frame, variable=self.prof_var, command=self._change_profile)
        self.prof_menu.pack(side="left", padx=5)
        self.prof_menu.configure(values=list(self.cfg.raw_data["profiles"].keys()))
        
        ctk.CTkButton(self.prof_frame, text="Νέο", width=50, command=self._new_profile).pack(side="left", padx=5)
        ctk.CTkButton(self.prof_frame, text="Διαγραφή", width=60, fg_color="#dc3545", hover_color="#c82333", command=self._delete_profile).pack(side="left", padx=5)

        # Points
        self.points_frame = ctk.CTkFrame(self)
        self.points_frame.pack(fill="x", padx=20, pady=10)
        
        self.points_lbl = ctk.CTkLabel(self.points_frame, text="Σημεία: 0", font=ctk.CTkFont(weight="bold"))
        self.points_lbl.pack(pady=(10, 5))
        
        p_btn_frame = ctk.CTkFrame(self.points_frame, fg_color="transparent")
        p_btn_frame.pack(pady=(0, 10))
        btn_add = ctk.CTkButton(p_btn_frame, text="Προσθήκη Σημείου (3s)", width=150, command=self.add_point)
        btn_add.pack(side="left", padx=5)
        ToolTip(btn_add, "Πάτησε το, πήγαινε το ποντίκι στο σημείο και περίμενε.\nΜπορείς να προσθέσεις πολλά σημεία το ένα μετά το άλλο.")
        
        btn_clear = ctk.CTkButton(p_btn_frame, text="Καθαρισμός", width=80, fg_color="#ffc107", text_color="black", hover_color="#e0a800", command=self.clear_points)
        btn_clear.pack(side="left", padx=5)

        # Form
        self.form = ctk.CTkFrame(self)
        self.form.pack(fill="both", expand=True, padx=20, pady=5)

        # Click Type
        type_frame = ctk.CTkFrame(self.form, fg_color="transparent")
        type_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(type_frame, text="Τύπος Κλικ:", width=170, anchor="e").pack(side="left", padx=5)
        self.click_type_var = ctk.StringVar(value="Αριστερό")
        ctk.CTkOptionMenu(type_frame, variable=self.click_type_var, values=["Αριστερό", "Δεξί", "Διπλό"], width=100).pack(side="left", padx=5)

        self.interval_entry = self._add_field("Χρονικό Διάστημα (min):", "Πόση ώρα θα περιμένει το πρόγραμμα ανάμεσα σε κάθε κλικ.")
        
        # Random Switch with Tooltip
        self.rand_frame = ctk.CTkFrame(self.form, fg_color="transparent")
        self.rand_frame.pack(fill="x", pady=10)
        self.rand_switch = ctk.CTkSwitch(self.rand_frame, text="Τυχαίο Διάστημα")
        self.rand_switch.pack(side="left", padx=(60, 5))
        info_i = ctk.CTkLabel(self.rand_frame, text="(i)", font=ctk.CTkFont(size=12, slant="italic"), text_color="gray")
        info_i.pack(side="left")
        ToolTip(info_i, "Αν ενεργοποιηθεί, το κλικ θα γίνεται σε μια τυχαία στιγμή\nαπό 1 δευτερόλεπτο έως το 'Χρονικό Διάστημα' που έβαλες.")

        self.scroll_entry = self._add_field("Scroll:", "Πόσο θα 'ρολάρει' (κυλήσει) η σελίδα ανάμεσα στα κλικ.")
        self.move_jitter_entry = self._add_field("Τυχαία Μετακίνηση (px):", "Πόσα pixels θα κινείται τυχαία το ποντίκι γύρω από το σημείο.")
        self.delay_entry = self._add_field("Καθυστέρηση (sec):", "Πόσα δευτερόλεπτα θα περιμένει το πρόγραμμα πριν ξεκινήσει το πρώτο κλικ.")

        self._refresh_form()

        # Action Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=20, pady=15)
        self.start_btn = ctk.CTkButton(self.btn_frame, text="ΕΝΑΡΞΗ (F6)", command=self.start, fg_color="#28a745", hover_color="#218838", font=ctk.CTkFont(weight="bold"))
        self.start_btn.grid(row=0, column=0, padx=(0,5), sticky="ew")
        self.stop_btn = ctk.CTkButton(self.btn_frame, text="ΠΑΥΣΗ (F7)", command=self.stop, fg_color="#dc3545", hover_color="#c82333", font=ctk.CTkFont(weight="bold"), state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=(5,0), sticky="ew")
        self.btn_frame.grid_columnconfigure((0,1), weight=1)

        self.status_bar = ctk.CTkLabel(self, text="Έτοιμο", font=ctk.CTkFont(size=11), text_color="gray")
        self.status_bar.pack(side="bottom", pady=5)

        # Start background threads
        threading.Thread(target=self._watcher, daemon=True).start()
        
        # Setup Hotkeys
        try:
            keyboard.add_hotkey('F6', self._hotkey_start)
            keyboard.add_hotkey('F7', self._hotkey_stop)
        except Exception: pass
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _add_field(self, label_text, tooltip_text):
        frame = ctk.CTkFrame(self.form, fg_color="transparent")
        frame.pack(fill="x", pady=2)
        ctk.CTkLabel(frame, text=label_text, width=170, anchor="e").pack(side="left", padx=5)
        entry = ctk.CTkEntry(frame, width=70)
        entry.pack(side="left", padx=5)
        info = ctk.CTkLabel(frame, text="(i)", font=ctk.CTkFont(size=12, slant="italic"), text_color="gray")
        info.pack(side="left")
        ToolTip(info, tooltip_text)
        return entry

    def _hotkey_start(self):
        if not self.running: self.after(0, self.start)
        
    def _hotkey_stop(self):
        if self.running: self.after(0, self.stop)

    def _change_profile(self, new_val):
        self.cfg.raw_data["current_profile"] = new_val
        self.cfg.save()
        self._refresh_form()

    def _new_profile(self):
        name = simpledialog.askstring("Νέο Προφίλ", "Όνομα νέου προφίλ:", parent=self)
        if name and name.strip():
            name = name.strip()
            self.cfg.raw_data["profiles"][name] = dict(DEFAULTS)
            self.cfg.raw_data["current_profile"] = name
            self.prof_menu.configure(values=list(self.cfg.raw_data["profiles"].keys()))
            self.prof_var.set(name)
            self.cfg.save()
            self._refresh_form()

    def _delete_profile(self):
        cp = self.cfg.raw_data["current_profile"]
        if cp == "Default":
            messagebox.showwarning("Προσοχή", "Το Προφίλ 'Default' δεν μπορεί να διαγραφεί.")
            return
        if messagebox.askyesno("Επιβεβαίωση", f"Διαγραφή του προφίλ '{cp}';"):
            del self.cfg.raw_data["profiles"][cp]
            new_cp = list(self.cfg.raw_data["profiles"].keys())[0]
            self.cfg.raw_data["current_profile"] = new_cp
            self.prof_menu.configure(values=list(self.cfg.raw_data["profiles"].keys()))
            self.prof_var.set(new_cp)
            self.cfg.save()
            self._refresh_form()

    def _refresh_points_lbl(self):
        pts = self.cfg.data.get("points", [])
        if not pts:
            self.points_lbl.configure(text="Σημεία: 0 (Κενό)")
        else:
            p_strs = [f"({p['x']},{p['y']})" for p in pts]
            title = f"Σημεία: {len(pts)}"
            if len(pts) <= 3: title += f" ({', '.join(p_strs)})"
            else: title += f" ({', '.join(p_strs[:3])}...)"
            self.points_lbl.configure(text=title)

    def _refresh_form(self):
        self._refresh_points_lbl()
        self.interval_entry.delete(0, 'end'); self.interval_entry.insert(0, str(self.cfg.data.get("interval_minutes", 1.0)))
        self.scroll_entry.delete(0, 'end'); self.scroll_entry.insert(0, str(self.cfg.data.get("scroll", -100)))
        self.move_jitter_entry.delete(0, 'end'); self.move_jitter_entry.insert(0, str(self.cfg.data.get("move_jitter", 15)))
        self.delay_entry.delete(0, 'end'); self.delay_entry.insert(0, str(self.cfg.data.get("start_delay_sec", 5)))
        self.click_type_var.set(self.cfg.data.get("click_type", "Αριστερό"))
        if self.cfg.data.get("use_random_timing"): self.rand_switch.select()
        else: self.rand_switch.deselect()

    def _save_form(self):
        try:
            self.cfg.data.update({
                "interval_minutes": float(self.interval_entry.get()),
                "use_random_timing": bool(self.rand_switch.get()),
                "scroll": int(self.scroll_entry.get()),
                "move_jitter": int(self.move_jitter_entry.get()),
                "start_delay_sec": int(self.delay_entry.get()),
                "click_type": self.click_type_var.get()
            })
            self.cfg.save(); return True
        except ValueError: messagebox.showerror("Λάθος", "Ελέγξτε τις τιμές."); return False

    def add_point(self):
        self.status_bar.configure(text="Καταγραφή ποντικιού σε 3s...")
        self.after(3000, self._capture)

    def clear_points(self):
        self.cfg.data["points"] = []
        self.cfg.save()
        self._refresh_points_lbl()

    def _capture(self):
        x, y = pyautogui.position()
        if "points" not in self.cfg.data: self.cfg.data["points"] = []
        self.cfg.data["points"].append({"x": int(x), "y": int(y)})
        self.cfg.save(); self._refresh_form()
        self.status_bar.configure(text=f"Προστέθηκε σημείο: ({x}, {y})")

    def start(self):
        if not self.cfg.data.get("points"):
            messagebox.showwarning("Προσοχή", "Ορίστε τουλάχιστον ένα σημείο κλικ."); return
        if not self._save_form(): return
        
        self.running = True 
        self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal")
        self.iconify()
        self.status_bar.configure(text="Εκτέλεση...")
        threading.Thread(target=self._run_loop, daemon=True).start()

    def stop(self): 
        self.running = False

    def on_close(self): 
        self.watcher_run = False; self.running = False
        try: keyboard.unhook_all()
        except: pass
        self.destroy()

    def _humanized_click(self, tx, ty, click_type):
        if not self.running: return 
        
        # Προσθήκη τυχαίου offset (±20 pixels) για να μην είναι pixel-perfect το σημείο
        tx += random.randint(-20, 20)
        ty += random.randint(-20, 20)
        
        if random.random() > 0.3:
            overshoot_x = tx + random.randint(-15, 15)
            overshoot_y = ty + random.randint(-15, 15)
            pyautogui.moveTo(overshoot_x, overshoot_y, duration=random.uniform(0.15, 0.3), tween=pyautogui.easeOutQuad)
            if not self.running: return
            time.sleep(random.uniform(0.01, 0.05))
        
        if not self.running: return
        pyautogui.moveTo(tx, ty, duration=random.uniform(0.1, 0.25), tween=pyautogui.easeInOutQuad)
        time.sleep(random.uniform(0.05, 0.2))
        
        if not self.running: return
        btn = 'left' if click_type == "Αριστερό" else 'right'
        
        if click_type == "Διπλό":
            # Προσομοίωση Διπλού Κλικ
            pyautogui.mouseDown(button='left')
            time.sleep(random.uniform(0.03, 0.08))
            pyautogui.mouseUp(button='left')
            time.sleep(random.uniform(0.05, 0.15))
            pyautogui.mouseDown(button='left')
            time.sleep(random.uniform(0.03, 0.08))
            pyautogui.mouseUp(button='left')
        else:
            pyautogui.mouseDown(button=btn)
            time.sleep(random.uniform(0.03, 0.12))
            pyautogui.mouseUp(button=btn)

    def _run_loop(self):
        try:
            delay = max(0, self.cfg.data.get("start_delay_sec", 5))
            t_start = time.time()
            while self.running and (time.time() - t_start) < delay:
                time.sleep(0.1)

            pts = self.cfg.data["points"]
            pt_index = 0
            
            while self.running:
                # Επιλογή Σημείου με τη σειρά
                pt = pts[pt_index]
                tx, ty = pt["x"], pt["y"]
                pt_index = (pt_index + 1) % len(pts) # Loop back to 0
                
                cl_type = self.cfg.data.get("click_type", "Αριστερό")
                self._humanized_click(tx, ty, cl_type)
                
                base_min = float(self.cfg.data["interval_minutes"])
                actual_wait = random.uniform(2.0, base_min * 60) if self.cfg.data["use_random_timing"] else max(0.2, base_min * 60)
                
                if not self.cfg.data["use_random_timing"]:
                    actual_wait += random.uniform(-0.5, 0.5)
                    
                t0 = time.time()
                ds = False; dj = False
                while self.running and (time.time() - t0 < actual_wait):
                    el = time.time() - t0
                    if not ds and self.cfg.data["scroll"] != 0 and el > (actual_wait * random.uniform(0.3, 0.6)):
                        scroll_amt = self.cfg.data["scroll"]
                        chunks = [scroll_amt // 2, scroll_amt - (scroll_amt // 2)]
                        for chunk in chunks:
                            pyautogui.scroll(chunk)
                            time.sleep(random.uniform(0.05, 0.15))
                        ds = True
                    if not dj and self.cfg.data["move_jitter"] > 0 and el > (actual_wait * random.uniform(0.6, 0.9)):
                        j = self.cfg.data["move_jitter"]
                        pyautogui.moveRel(random.randint(-j, j), random.randint(-j, j), 
                                          duration=random.uniform(0.2, 0.5), tween=pyautogui.easeInOutSine)
                        dj = True
                    time.sleep(0.1)
        except Exception:
            self.running = False
        finally:
            self.after(0, lambda: (
                self.start_btn.configure(state="normal"), 
                self.stop_btn.configure(state="disabled"),
                self.status_bar.configure(text="Έτοιμο / Σταμάτησε")
            ))

    def _watcher(self):
        while self.watcher_run:
            time.sleep(2.0)
            if self.cfg.reload_if_changed(): self.after(0, self._refresh_form)

if __name__ == "__main__": App().mainloop()
