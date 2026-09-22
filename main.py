"""Simple yt-dlp GUI built with tkinter + Sun Valley theme."""

import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import sv_ttk
from typing import Optional


class YTDlpGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("yt-dlp GUI")
        self.root.geometry("680x580")
        self.root.resizable(True, True)

        self._downloading = False
        self._process: Optional[subprocess.Popen] = None

        self._build_ui()
        self._load_history()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        # --- Top frame: URL ---
        url_frame = ttk.LabelFrame(self.root, text="URL")
        url_frame.pack(fill="x", padx=8, pady=(8, 4))

        self.url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.url_var, width=70).pack(
            side="left", fill="x", expand=True, padx=(4, 2), pady=4
        )
        ttk.Button(url_frame, text="Browse", command=self._browse_url).pack(
            side="right", padx=4, pady=4
        )

        # --- Options frame ---
        opt_frame = ttk.LabelFrame(self.root, text="Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        # Quality
        ttk.Label(opt_frame, text="Quality:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.quality_var = tk.StringVar(value="best")
        qualities = [
            ("Best", "best"),
            ("Best Video+Audio", "bestvideo+bestaudio"),
            ("1080p", "bestvideo[height<=1080]+bestaudio"),
            ("720p", "bestvideo[height<=720]+bestaudio"),
            ("480p", "bestvideo[height<=480]+bestaudio"),
            ("360p", "bestvideo[height<=360]+bestaudio"),
            ("Audio only", "bestaudio"),
        ]
        ttk.Combobox(
            opt_frame, textvariable=self.quality_var, values=[q[0] for q in qualities],
            state="readonly", width=18,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=4)
        self.quality_var.trace_add("write", self._quality_changed)

        # Format
        ttk.Label(opt_frame, text="Format:").grid(row=0, column=2, sticky="w", padx=(16, 4), pady=4)
        self.format_var = tk.StringVar(value="mp4")
        ttk.Combobox(
            opt_frame, textvariable=self.format_var,
            values=["mp4", "mkv", "mp3", "wav", "flac", "opus"],
            state="readonly", width=8,
        ).grid(row=0, column=3, sticky="w", padx=4, pady=4)

        # Output dir
        ttk.Label(opt_frame, text="Save to:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.dir_var = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        ttk.Entry(opt_frame, textvariable=self.dir_var, width=50).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=4, pady=4
        )
        ttk.Button(opt_frame, text="…", command=self._browse_dir).grid(
            row=1, column=3, padx=4, pady=4
        )

        # Extra options
        ttk.Label(opt_frame, text="Extra opts:").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self.extra_var = tk.StringVar()
        ttk.Entry(opt_frame, textvariable=self.extra_var, width=60).grid(
            row=2, column=1, columnspan=3, sticky="w", padx=4, pady=4
        )

        # --- Buttons ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=8, pady=4)

        self.download_btn = ttk.Button(btn_frame, text="Download", command=self._start_download)
        self.download_btn.pack(side="left", padx=4)

        ttk.Button(btn_frame, text="Cancel", command=self._cancel_download).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Clear Log", command=self._clear_log).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="History", command=self._show_history).pack(side="right", padx=4)

        # --- Log / progress ---
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=10,
                                font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                               anchor="w", font=("Sans", 9))
        status_bar.pack(fill="x", padx=8, pady=(0, 6))

    # ── Helpers ──────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        """Append a line to the log text widget (thread-safe)."""
        self.root.after(0, lambda: self._log_now(msg))

    def _log_now(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _set_status(self, msg: str) -> None:
        self.root.after(0, lambda: self.status_var.set(msg))

    def _browse_url(self) -> None:
        url = filedialog.askopenfilename(title="Select a URL file")
        if url:
            with open(url, "r") as f:
                self.url_var.set(f.read().strip())

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _quality_changed(self, *args) -> None:
        pass

    # ── Download ─────────────────────────────────────────────────────

    def _start_download(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a URL.")
            return

        if self._downloading:
            messagebox.showinfo("Already Downloading", "A download is already in progress.")
            return

        self._downloading = True
        self.download_btn.config(text="Downloading…", state="disabled")
        self._clear_log()
        self._log(f"Starting download: {url}")
        self.status_var.set("Downloading…")

        quality_label = self.quality_var.get()
        quality_map = {q[0]: q[1] for q in [
            ("Best", "best"), ("Best Video+Audio", "bestvideo+bestaudio"),
            ("1080p", "bestvideo[height<=1080]+bestaudio"), ("720p", "bestvideo[height<=720]+bestaudio"),
            ("480p", "bestvideo[height<=480]+bestaudio"), ("360p", "bestvideo[height<=360]+bestaudio"),
            ("Audio only", "bestaudio"),
        ]}
        fmt = self.format_var.get()
        quality = quality_map.get(quality_label, "best")
        out_dir = self.dir_var.get()
        extra = self.extra_var.get().strip()

        # Build output template
        out_tmpl = os.path.join(out_dir, "%(title)s.%(ext)s")
        if fmt in ("mp3", "wav", "flac", "opus"):
            post = f"-x --audio-format {fmt}"
        else:
            post = ""

        cmd = [
            "yt-dlp",
            "-f", quality,
            "-o", out_tmpl,
            "--no-mtime",
        ]
        if post:
            cmd.extend(post.split())
        if extra:
            cmd.extend(extra.split())
        cmd.append(url)

        self._log(f"Command: {' '.join(cmd)}")

        thread = threading.Thread(target=self._run_ytdlp, args=(cmd,), daemon=True)
        thread.start()

    def _run_ytdlp(self, cmd: list[str]) -> None:
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=os.path.expanduser("~"),
            )
            for line in iter(self._process.stdout.readline, ""):
                self._log(line.rstrip())
            self._process.stdout.close()
            self._process.wait()

            if self._process.returncode == 0:
                self.root.after(0, lambda: self._download_done(True))
            else:
                self.root.after(0, lambda: self._download_done(False, f"Exit code {self._process.returncode}"))
        except FileNotFoundError:
            self.root.after(0, lambda: self._download_done(False, "yt-dlp not found"))
        except Exception as e:
            self.root.after(0, lambda: self._download_done(False, str(e)))
        finally:
            self._process = None

    def _download_done(self, success: bool, msg: str = "") -> None:
        self._downloading = False
        self.download_btn.config(text="Download", state="normal")
        if success:
            self._log("\n✅ Download completed successfully!")
            self.status_var.set("Download complete")
            self._add_to_history(self.url_var.get())
            messagebox.showinfo("Done", "Download completed!")
        else:
            self._log(f"\n❌ Download failed: {msg}")
            self.status_var.set("Download failed")
            messagebox.showerror("Failed", f"Download failed.\n{msg}")

    def _cancel_download(self) -> None:
        if self._downloading and self._process:
            self._process.terminate()
            self._log("\nCancelled by user.")
            self._downloading = False
            self.download_btn.config(text="Download", state="normal")
            self.status_var.set("Cancelled")

    # ── History ──────────────────────────────────────────────────────

    HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".ytdlp_gui_history.json")

    def _load_history(self) -> None:
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE) as f:
                    self._history = json.load(f)
            except Exception:
                self._history = []
        else:
            self._history = []

    def _save_history(self) -> None:
        with open(self.HISTORY_FILE, "w") as f:
            json.dump(self._history, f, indent=2)

    def _add_to_history(self, url: str) -> None:
        if url not in self._history:
            self._history.insert(0, url)
        if len(self._history) > 50:
            self._history = self._history[:50]
        self._save_history()

    def _show_history(self) -> None:
        self._load_history()
        hist_win = tk.Toplevel(self.root)
        hist_win.title("Download History")
        hist_win.geometry("500x300")
        hist_win.transient(self.root)

        frame = ttk.Frame(hist_win)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set, font=("Consolas", 9))
        listbox.pack(fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        for url in self._history:
            listbox.insert("end", url)

        def on_select(event):
            sel = listbox.curselection()
            if sel:
                self.url_var.set(listbox.get(sel[0]))

        listbox.bind("<<ListboxSelect>>", on_select)

        ttk.Button(hist_win, text="Close", command=hist_win.destroy).pack(pady=4)


def main() -> None:
    root = tk.Tk()
    root.geometry("680x580")
    sv_ttk.set_theme("dark")
    app = YTDlpGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
