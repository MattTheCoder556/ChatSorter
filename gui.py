#!/usr/bin/env python3
"""Cross-platform desktop UI for ChatSorter (Windows / Linux / macOS).

One window to organize a vault: pick the folder, see exactly what gets sorted
where, run a one-shot pass (or preview it), and start/stop the live watcher — with
a streaming activity log. Pure standard library (Tkinter), so it runs anywhere
Python does (on Linux install the Tk binding once: the system `python3-tk` pkg).

    python gui.py            # opens the window

Settings (vault, model, options) persist to config.json next to this file. The
API key is read from MINIMAX_API_KEY (or the field) and is never saved to disk.
"""
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import sort_vault as sv   # for the type-map / doc-map shown in the legend

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
PY = sys.executable or "python3"
NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0  # hide child console on Windows

DEFAULTS = {"vault": "", "model": "MiniMax-M2", "use_ai": True, "include_docs": True}


def load_cfg() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_cfg(cfg: dict) -> None:
    try:
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass


def invert_doc_map(doc_map: dict) -> dict:
    """{'.pdf':'Documents', ...} -> {'Documents': ['.pdf', ...]} preserving order."""
    out: dict = {}
    for ext, folder in doc_map.items():
        out.setdefault(folder, []).append(ext)
    return out


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_cfg()
        self.proc = None
        self.q: queue.Queue = queue.Queue()

        root.title("ChatSorter — vault organizer")
        root.minsize(720, 640)
        PAD = {"padx": 10, "pady": (4, 0)}

        ttk.Label(root, wraplength=690, foreground="#444",
                  text="Files in the top level of your vault get filed into folders. "
                       "Markdown notes are sorted by their type:, documents by file type. "
                       "Nothing is ever deleted or overwritten.").pack(fill="x", **PAD)

        # ---- 1. vault ----
        box1 = ttk.LabelFrame(root, text=" 1. Vault folder ")
        box1.pack(fill="x", **PAD)
        self.vault = tk.StringVar(value=self.cfg.get("vault", ""))
        row = ttk.Frame(box1); row.pack(fill="x", padx=8, pady=8)
        ttk.Entry(row, textvariable=self.vault).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self.browse).pack(side="left", padx=(6, 0))

        # ---- 2. what goes where (legend) ----
        box2 = ttk.LabelFrame(root, text=" 2. What gets sorted where ")
        box2.pack(fill="both", expand=True, **PAD)
        self._build_legend(box2)

        # ---- 3. options ----
        box3 = ttk.LabelFrame(root, text=" 3. Options ")
        box3.pack(fill="x", **PAD)
        self.include_docs = tk.BooleanVar(value=bool(self.cfg.get("include_docs", True)))
        ttk.Checkbutton(box3, text="Include documents (PDF, DOCX, PPTX, XLSX, CSV…)",
                        variable=self.include_docs).pack(anchor="w", padx=8, pady=(8, 0))
        self.use_ai = tk.BooleanVar(value=bool(self.cfg.get("use_ai", True)))
        ttk.Checkbutton(box3, text="Use AI to classify untyped notes (MiniMax — needs an API key)",
                        variable=self.use_ai).pack(anchor="w", padx=8)
        airow = ttk.Frame(box3); airow.pack(fill="x", padx=8, pady=(2, 8))
        ttk.Label(airow, text="Model:").pack(side="left")
        self.model = tk.StringVar(value=self.cfg.get("model", "MiniMax-M2"))
        ttk.Entry(airow, textvariable=self.model, width=16).pack(side="left", padx=(4, 12))
        ttk.Label(airow, text="API key:").pack(side="left")
        self.apikey = tk.StringVar(value=os.environ.get("MINIMAX_API_KEY", ""))
        ttk.Entry(airow, textvariable=self.apikey, width=22, show="•").pack(side="left", padx=4)

        # ---- 4. actions ----
        box4 = ttk.Frame(root); box4.pack(fill="x", **PAD)
        ttk.Button(box4, text="▶ Sort now", command=lambda: self.sort_now(dry=False)).pack(side="left")
        ttk.Button(box4, text="Preview (dry run)", command=lambda: self.sort_now(dry=True)).pack(side="left", padx=4)
        self.btn_start = ttk.Button(box4, text="Start watcher", command=self.start_watch)
        self.btn_start.pack(side="left", padx=(16, 4))
        self.btn_stop = ttk.Button(box4, text="Stop watcher", command=self.stop_watch, state="disabled")
        self.btn_stop.pack(side="left")
        self.status = ttk.Label(box4, text="● STOPPED", foreground="#b00")
        self.status.pack(side="right")

        # ---- log ----
        self.out = scrolledtext.ScrolledText(root, height=12, wrap="word",
                                             state="disabled", font=("monospace", 9))
        self.out.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_queue()

    # ---------- legend ----------
    def _build_legend(self, parent):
        tree = ttk.Treeview(parent, columns=("dest",), height=12)
        tree.heading("#0", text="File")
        tree.heading("dest", text="Goes to folder")
        tree.column("#0", width=420, anchor="w")
        tree.column("dest", width=200, anchor="w")
        tree.pack(fill="both", expand=True, padx=8, pady=8)

        md = tree.insert("", "end", text="📝  Markdown notes — by  type:  frontmatter", open=True)
        for label, folder in sv.DEFAULT_MAP.items():
            tree.insert(md, "end", text=f"     type: {label}", values=(folder + "/",))

        doc = tree.insert("", "end", text="📄  Documents — by file extension", open=True)
        for folder, exts in invert_doc_map(sv.DEFAULT_DOC_MAP).items():
            tree.insert(doc, "end", text="     " + "  ".join(exts), values=(folder + "/",))

        tree.insert("", "end", text="🖼  Images, untyped notes, anything else",
                    values=("(left in place)",))

    # ---------- log plumbing ----------
    def log(self, msg: str):
        self.q.put(msg)

    def poll_queue(self):
        try:
            while True:
                line = self.q.get_nowait()
                self.out.configure(state="normal")
                self.out.insert("end", line + "\n")
                self.out.see("end")
                self.out.configure(state="disabled")
        except queue.Empty:
            pass
        if self.proc is not None and self.proc.poll() is not None:
            self._mark_stopped()
        self.root.after(150, self.poll_queue)

    def _stream(self, proc):
        for line in iter(proc.stdout.readline, ""):
            self.q.put(line.rstrip())
        proc.stdout.close()

    # ---------- shared ----------
    def browse(self):
        d = filedialog.askdirectory(initialdir=self.vault.get() or str(Path.home()))
        if d:
            self.vault.set(d)

    def _env(self) -> dict:
        env = dict(os.environ)
        if self.apikey.get().strip():
            env["MINIMAX_API_KEY"] = self.apikey.get().strip()
        if self.model.get().strip():
            env["MINIMAX_MODEL"] = self.model.get().strip()
        return env

    def _persist(self):
        save_cfg({"vault": self.vault.get().strip(),
                  "model": self.model.get().strip() or "MiniMax-M2",
                  "use_ai": bool(self.use_ai.get()),
                  "include_docs": bool(self.include_docs.get())})

    def _valid_vault(self):
        v = self.vault.get().strip()
        if not v or not Path(v).expanduser().is_dir():
            messagebox.showerror("ChatSorter", "Pick a valid vault folder first.")
            return None
        self._persist()
        return str(Path(v).expanduser())

    def _common_flags(self):
        flags = []
        if not self.use_ai.get():
            flags.append("--no-llm")
        if not self.include_docs.get():
            flags.append("--no-docs")
        return flags

    def _need_key_ok(self, what: str) -> bool:
        if self.use_ai.get() and not self._env().get("MINIMAX_API_KEY"):
            messagebox.showerror(
                "ChatSorter",
                f"{what} the AI pass needs an API key. Enter one, set MINIMAX_API_KEY, "
                "or untick 'Use AI' to sort by existing type / extension only.")
            return False
        return True

    def _spawn(self, cmd, track=False):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1, env=self._env(),
                                    creationflags=NO_WINDOW)
        except OSError as e:
            self.log(f"! failed to launch: {e}")
            return None
        if track:
            self.proc = proc
        threading.Thread(target=self._stream, args=(proc,), daemon=True).start()
        return proc

    # ---------- actions ----------
    def sort_now(self, dry: bool):
        vault = self._valid_vault()
        if not vault or not self._need_key_ok("To sort,"):
            return
        cmd = [PY, str(HERE / "auto_sort.py"), vault] + self._common_flags()
        if dry:
            cmd.append("--dry-run")
        self.log(f"$ {'PREVIEW ' if dry else ''}sort {vault}")
        self._spawn(cmd)

    def start_watch(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        vault = self._valid_vault()
        if not vault or not self._need_key_ok("To watch,"):
            return
        cmd = [PY, str(HERE / "watch_vault.py"), vault,
               "--interval", "5", "--log", "off"] + self._common_flags()
        if self._spawn(cmd, track=True) is None:
            return
        self.status.configure(text="● RUNNING", foreground="#0a0")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def stop_watch(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._mark_stopped()

    def _mark_stopped(self):
        self.proc = None
        self.status.configure(text="● STOPPED", foreground="#b00")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def on_close(self):
        if self.proc is not None and self.proc.poll() is None:
            self.stop_watch()
        self._persist()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
