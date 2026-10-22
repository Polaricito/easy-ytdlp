"""Simple yt-dlp GUI built with tkinter + Sun Valley theme.

Windows notes:
- Child processes are started without a console window.
- yt-dlp.exe / ffmpeg.exe are looked up next to the app (and in a ``bin``
  subfolder), then on PATH.  When running from source, a pip-installed
  ``yt_dlp`` module is used as a fallback.
- History is stored in ``%APPDATA%\\ytdlp-gui\\history.json``.
"""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

import sv_ttk

APP_NAME = "yt-dlp GUI"
APP_ID = "ytdlp-gui"
IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROGRESS_RE = re.compile(r"^\[download\]\s+(\d+(?:\.\d+)?)%")

QUALITIES = [
    ("Best", "best"),
    ("Best video + audio", "bestvideo+bestaudio/best"),
    ("1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
    ("360p", "bestvideo[height<=360]+bestaudio/best[height<=360]"),
    ("Audio only", "bestaudio/best"),
]
QUALITY_MAP = dict(QUALITIES)
AUDIO_FORMATS = {"mp3", "wav", "flac", "opus"}


# ── Platform helpers ─────────────────────────────────────────────────


def app_dir() -> Path:
    """Directory containing the script or bundled executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Directory containing bundled resources (PyInstaller temp dir)."""
    return Path(getattr(sys, "_MEIPASS", str(app_dir())))


def config_dir() -> Path:
    """Per-user configuration directory."""
    if IS_WINDOWS:
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / APP_ID


def history_path() -> Path:
    return config_dir() / "history.json"


def legacy_history_path() -> Path:
    return Path.home() / ".ytdlp_gui_history.json"


def default_download_dir() -> Path:
    """Use the real Windows Downloads folder when possible."""
    if IS_WINDOWS:
        try:
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as reg_key:
                value, _ = winreg.QueryValueEx(
                    reg_key, "{374DE290-123F-4565-9164-39C4925E467B}"
                )
            return Path(os.path.expandvars(value))
        except (OSError, ImportError):
            pass
    return Path.home() / "Downloads"


def _enable_dpi_awareness() -> None:
    """Make Tk crisp on high-DPI Windows displays."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _set_app_user_model_id() -> None:
    """Group the app under its own taskbar icon on Windows."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "meowl.ytdlp-gui"
        )
    except (AttributeError, OSError):
        pass


def _startupinfo() -> Optional[subprocess.STARTUPINFO]:
    if not IS_WINDOWS:
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return info


def _dedupe_paths(paths: List[Path]) -> List[Path]:
    seen = set()
    result = []
    for path in paths:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _binary_names(stem: str) -> Tuple[str, ...]:
    if IS_WINDOWS:
        return (f"{stem}.exe", f"{stem}.cmd", f"{stem}.bat", stem)
    return (stem,)


def _app_binary_dirs() -> List[Path]:
    # An external bin folder next to the exe wins over the bundled copy so
    # users can drop in an updated yt-dlp.exe without rebuilding.
    dirs = [app_dir() / "bin", app_dir()]
    if getattr(sys, "frozen", False):
        resource = resource_dir()
        dirs.extend([resource / "bin", resource])
    return _dedupe_paths(dirs)


def find_local_binary(stem: str) -> Optional[Path]:
    for directory in _app_binary_dirs():
        for name in _binary_names(stem):
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def find_binary(stem: str) -> Optional[Path]:
    local = find_local_binary(stem)
    if local is not None:
        return local
    found = shutil.which(stem)
    if found:
        return Path(found)
    for name in _binary_names(stem):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _exec_command(path: Path) -> List[str]:
    if IS_WINDOWS and path.suffix.lower() in (".cmd", ".bat"):
        return ["cmd", "/c", str(path)]
    return [str(path)]


def resolve_ytdlp() -> Optional[List[str]]:
    """Return the command prefix used to invoke yt-dlp, if available."""
    local = find_local_binary("yt-dlp")
    if local is not None:
        return _exec_command(local)
    if not getattr(sys, "frozen", False):
        if importlib.util.find_spec("yt_dlp") is not None:
            return [sys.executable, "-m", "yt_dlp"]
    on_path = find_binary("yt-dlp")
    if on_path is not None:
        return _exec_command(on_path)
    return None


def resolve_ffmpeg() -> Optional[Path]:
    return find_binary("ffmpeg")


def format_command(cmd: List[str]) -> str:
    if IS_WINDOWS:
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def split_extra_args(text: str) -> List[str]:
    """Split the extra-options field, respecting quoted Windows paths."""
    text = text.strip()
    if not text:
        return []
    try:
        parts = shlex.split(text, posix=not IS_WINDOWS)
    except ValueError as exc:
        raise ValueError(f"Could not parse extra options: {exc}") from exc
    if IS_WINDOWS:
        # shlex with posix=False keeps the quotes; remove them.
        cleaned = []
        for part in parts:
            if len(part) >= 2 and part[0] == part[-1] and part[0] in ("'", '"'):
                part = part[1:-1]
            cleaned.append(part)
        return cleaned
    return parts


def needs_ffmpeg(quality: str, fmt: str) -> bool:
    return fmt in AUDIO_FORMATS or "+" in quality


def pip_install_hint() -> str:
    command = "py" if IS_WINDOWS else "python3"
    return f"{command} -m pip install -U yt-dlp"


def ffmpeg_install_hint() -> str:
    if IS_WINDOWS:
        return "winget install Gyan.FFmpeg"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg  (or your package manager)"


# ── Application ──────────────────────────────────────────────────────


class YTDlpGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.minsize(680, 600)
        self.root.resizable(True, True)

        self._downloading = False
        self._cancelled = False
        self._closing = False
        self._process: Optional[subprocess.Popen] = None
        self._history: List[str] = []
        self._active_url = ""
        self._ui_queue: "queue.Queue[Tuple[object, tuple]]" = queue.Queue()
        self._syncing_formats = False

        sv_ttk.set_theme("dark")
        self._set_window_icon()
        self._build_ui()
        self._load_history()
        self._center_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._check_dependencies()
        self._poll_ui_queue()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        # --- URL ---
        url_frame = ttk.LabelFrame(main, text="Video / audio URL", padding=6)
        url_frame.grid(row=0, column=0, sticky="ew")
        url_frame.columnconfigure(0, weight=1)

        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=2)
        self._attach_edit_menu(self.url_entry)

        ttk.Button(url_frame, text="Paste", width=9, command=self._paste_url).grid(
            row=0, column=1, pady=2
        )

        # --- Options ---
        opt_frame = ttk.LabelFrame(main, text="Download options", padding=6)
        opt_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        opt_frame.columnconfigure(1, weight=1)

        ttk.Label(opt_frame, text="Quality:").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=3
        )
        self.quality_var = tk.StringVar(value=QUALITIES[0][0])
        ttk.Combobox(
            opt_frame,
            textvariable=self.quality_var,
            values=[label for label, _ in QUALITIES],
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(opt_frame, text="Format:").grid(
            row=0, column=2, sticky="w", padx=(16, 6), pady=3
        )
        self.format_var = tk.StringVar(value="mp4")
        ttk.Combobox(
            opt_frame,
            textvariable=self.format_var,
            values=["mp4", "mkv", "mp3", "wav", "flac", "opus"],
            state="readonly",
            width=8,
        ).grid(row=0, column=3, sticky="w", pady=3)

        # Keep "Audio only" and audio formats in sync.
        self.quality_var.trace_add("write", self._quality_changed)
        self.format_var.trace_add("write", self._format_changed)

        ttk.Label(opt_frame, text="Save to:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=3
        )
        self.dir_var = tk.StringVar(value=str(default_download_dir()))
        ttk.Entry(opt_frame, textvariable=self.dir_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=3
        )
        ttk.Button(opt_frame, text="Browse…", command=self._browse_dir).grid(
            row=1, column=3, sticky="w", padx=(6, 0), pady=3
        )
        ttk.Button(opt_frame, text="Open", width=7, command=self._open_output_folder).grid(
            row=1, column=4, sticky="w", padx=(6, 0), pady=3
        )

        ttk.Label(opt_frame, text="Extra opts:").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=3
        )
        self.extra_var = tk.StringVar()
        extra_entry = ttk.Entry(opt_frame, textvariable=self.extra_var)
        extra_entry.grid(row=2, column=1, columnspan=4, sticky="ew", pady=3)
        self._attach_edit_menu(extra_entry)

        # --- Buttons ---
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.download_btn = ttk.Button(
            btn_frame,
            text="Download",
            style="Accent.TButton",
            command=self._start_download,
        )
        self.download_btn.pack(side="left")
        ttk.Button(btn_frame, text="Cancel", command=self._cancel_download).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(btn_frame, text="Clear log", command=self._clear_log).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(btn_frame, text="History", command=self._show_history).pack(
            side="right"
        )

        # --- Progress ---
        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.progress.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # --- Log ---
        log_frame = ttk.LabelFrame(main, text="Log", padding=6)
        log_frame.grid(row=4, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        log_font = ("Consolas", 9) if IS_WINDOWS else "TkFixedFont"
        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            state="disabled",
            height=10,
            font=log_font,
            relief="flat",
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # --- Status bar ---
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w",
            padding=(6, 3),
        )
        status_bar.grid(row=1, column=0, sticky="ew")

    def _set_window_icon(self) -> None:
        ico_candidates = [
            app_dir() / "assets" / "icon.ico",
            resource_dir() / "assets" / "icon.ico",
        ]
        for candidate in _dedupe_paths(ico_candidates):
            if candidate.is_file():
                try:
                    self.root.iconbitmap(default=str(candidate))
                    return
                except tk.TclError:
                    pass

        png_candidates = [
            app_dir() / "assets" / "icon.png",
            resource_dir() / "assets" / "icon.png",
        ]
        for candidate in _dedupe_paths(png_candidates):
            if candidate.is_file():
                try:
                    self._icon_image = tk.PhotoImage(file=str(candidate))
                    self.root.iconphoto(True, self._icon_image)
                    return
                except tk.TclError:
                    pass

    def _attach_edit_menu(self, widget: tk.Widget) -> None:
        """Standard right-click menu for entries on Windows."""
        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(
            label="Paste", command=lambda: widget.event_generate("<<Paste>>")
        )
        menu.add_separator()
        menu.add_command(
            label="Select all", command=lambda: widget.event_generate("<<SelectAll>>")
        )

        def popup(event: tk.Event) -> None:
            try:
                widget.focus_set()
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", popup)

    def _center_window(self) -> None:
        self.root.update_idletasks()
        width = max(self.root.winfo_reqwidth(), 780)
        height = max(self.root.winfo_reqheight(), 650)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, screen_w - 40)
        height = min(height, screen_h - 80)
        x = max((screen_w - width) // 2, 0)
        y = max((screen_h - height) // 2 - 20, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    # ── Helpers ──────────────────────────────────────────────────────

    def _ui(self, func, *args) -> None:
        """Queue a UI callback; safe to call from worker threads."""
        if self._closing:
            return
        self._ui_queue.put((func, args))

    def _poll_ui_queue(self) -> None:
        """Run queued UI callbacks on the Tk main thread."""
        if self._closing:
            return
        while True:
            try:
                func, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args)  # type: ignore[operator]
            except tk.TclError:
                pass
            except Exception as exc:  # keep the poll loop alive
                try:
                    self._log_now(f"UI error: {exc}")
                except tk.TclError:
                    pass
        try:
            self.root.after(50, self._poll_ui_queue)
        except tk.TclError:
            pass

    def _log(self, msg: str) -> None:
        self._ui(self._log_now, msg)

    def _log_now(self, msg: str) -> None:
        try:
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        except tk.TclError:
            pass

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)

    def _set_progress(self, value: float) -> None:
        self.progress["value"] = value

    def _apply_progress(self, value: float) -> None:
        self._set_progress(value)
        self._set_status(f"Downloading… {value:.1f}%")

    def _check_dependencies(self) -> None:
        ytdlp = resolve_ytdlp()
        ffmpeg = resolve_ffmpeg()

        if ytdlp is not None:
            self._log(f"yt-dlp: {format_command(ytdlp)}")
        else:
            self._log("WARNING: yt-dlp was not found.")
            self._log(f"  Install it with: {pip_install_hint()}")
            self._log("  or place yt-dlp.exe in the bin folder next to this app.")
            self._set_status("Ready — yt-dlp not found")

        if ffmpeg is not None:
            self._log(f"ffmpeg: {ffmpeg}")
        else:
            self._log(
                "WARNING: ffmpeg was not found. Merging video+audio and audio "
                "conversion will fail."
            )
            self._log(f"  Install it with: {ffmpeg_install_hint()}")
            self._log("  or place ffmpeg.exe in the bin folder next to this app.")

    def _paste_url(self) -> None:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        text = text.strip()
        if text:
            self.url_var.set(text)

    def _quality_changed(self, *args) -> None:
        """Select a sensible output format for the chosen quality."""
        if self._syncing_formats:
            return
        self._syncing_formats = True
        try:
            if self.quality_var.get() == "Audio only":
                if self.format_var.get() not in AUDIO_FORMATS:
                    self.format_var.set("mp3")
            elif self.format_var.get() in AUDIO_FORMATS:
                self.format_var.set("mp4")
        finally:
            self._syncing_formats = False

    def _format_changed(self, *args) -> None:
        """Select audio-only quality when an audio format is chosen."""
        if self._syncing_formats:
            return
        self._syncing_formats = True
        try:
            if self.format_var.get() in AUDIO_FORMATS:
                if self.quality_var.get() != "Audio only":
                    self.quality_var.set("Audio only")
            elif self.quality_var.get() == "Audio only":
                self.quality_var.set("Best")
        finally:
            self._syncing_formats = False

    def _browse_dir(self) -> None:
        initial = self.dir_var.get().strip() or str(default_download_dir())
        directory = filedialog.askdirectory(
            parent=self.root, title="Select download folder", initialdir=initial
        )
        if directory:
            self.dir_var.set(directory)

    def _open_output_folder(self) -> None:
        raw = self.dir_var.get().strip() or str(default_download_dir())
        target = Path(os.path.expandvars(raw)).expanduser()
        try:
            target.mkdir(parents=True, exist_ok=True)
            if IS_WINDOWS:
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except OSError as exc:
            messagebox.showerror(
                "Cannot open folder", f"Could not open:\n{target}\n\n{exc}", parent=self.root
            )

    # ── Download ─────────────────────────────────────────────────────

    def _start_download(self) -> None:
        if self._downloading:
            messagebox.showinfo(
                "Already downloading",
                "A download is already in progress.",
                parent=self.root,
            )
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(
                "Missing URL", "Please enter a URL.", parent=self.root
            )
            return

        ytdlp = resolve_ytdlp()
        if ytdlp is None:
            messagebox.showerror(
                "yt-dlp not found",
                "yt-dlp is required but was not found.\n\n"
                "Install it with:\n"
                f"  {pip_install_hint()}\n\n"
                'or place yt-dlp.exe in a "bin" folder next to this app.',
                parent=self.root,
            )
            return

        quality = QUALITY_MAP.get(self.quality_var.get(), "best")
        fmt = self.format_var.get()
        ffmpeg = resolve_ffmpeg()

        if needs_ffmpeg(quality, fmt) and ffmpeg is None:
            proceed = messagebox.askyesno(
                "ffmpeg not found",
                "This download needs ffmpeg to merge streams or convert audio, "
                "but ffmpeg was not found.\n\n"
                "Install it with:\n"
                f"  {ffmpeg_install_hint()}\n\n"
                'or place ffmpeg.exe in a "bin" folder next to this app.\n\n'
                "Continue anyway?",
                parent=self.root,
            )
            if not proceed:
                return

        raw_dir = self.dir_var.get().strip() or str(default_download_dir())
        out_dir = Path(os.path.expandvars(raw_dir)).expanduser()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Invalid folder",
                f"Cannot use this download folder:\n{out_dir}\n\n{exc}",
                parent=self.root,
            )
            return

        try:
            extra = split_extra_args(self.extra_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid extra options", str(exc), parent=self.root)
            return

        out_tmpl = str(out_dir / "%(title)s.%(ext)s")
        cmd = list(ytdlp)
        cmd.extend(["-f", quality, "-o", out_tmpl, "--newline", "--no-mtime"])

        if IS_WINDOWS:
            # Keep filenames valid even on restrictive/network drives.
            cmd.append("--windows-filenames")
        if ffmpeg is not None:
            cmd.extend(["--ffmpeg-location", str(ffmpeg.parent)])
        if fmt in AUDIO_FORMATS:
            cmd.extend(["-x", "--audio-format", fmt])
        cmd.extend(extra)
        cmd.append(url)

        self._downloading = True
        self._cancelled = False
        self._active_url = url
        self.download_btn.config(text="Downloading…", state="disabled")
        self._clear_log()
        self._set_progress(0)
        self._set_status("Downloading…")
        self._log(f"Downloading: {url}")
        self._log(f"Command: {format_command(cmd)}")

        thread = threading.Thread(
            target=self._run_ytdlp, args=(cmd, out_dir), daemon=True
        )
        thread.start()

    def _run_ytdlp(self, cmd: List[str], cwd: Path) -> None:
        if self._cancelled:
            self._ui(self._download_finished, 1, True, None)
            return

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["NO_COLOR"] = "1"

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(cwd),
                env=env,
                creationflags=CREATE_NO_WINDOW,
                startupinfo=_startupinfo(),
            )
        except OSError as exc:
            self._ui(self._download_finished, None, False, str(exc))
            return

        self._process = process
        if self._cancelled:
            self._kill_process(process)

        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self._handle_output(line.rstrip("\r\n"))
            return_code = process.wait()
            error = None
        except Exception as exc:  # pragma: no cover - defensive
            self._kill_process(process)
            return_code = process.wait()
            error = str(exc)
        finally:
            self._process = None

        self._ui(self._download_finished, return_code, self._cancelled, error)

    def _handle_output(self, line: str) -> None:
        if not line:
            return
        self._log(line)
        match = PROGRESS_RE.match(line)
        if match:
            try:
                percent = float(match.group(1))
            except ValueError:
                return
            self._ui(self._apply_progress, percent)

    def _download_finished(
        self, return_code: Optional[int], cancelled: bool, error: Optional[str]
    ) -> None:
        if self._closing:
            return

        self._downloading = False
        self._cancelled = False
        self.download_btn.config(text="Download", state="normal")

        if cancelled:
            self._set_progress(0)
            self._log("\nDownload cancelled.")
            self._set_status("Cancelled")
            return

        if return_code == 0 and not error:
            self._set_progress(100)
            self._log("\nDownload complete.")
            self._set_status("Download complete")
            self._add_to_history(self._active_url or self.url_var.get().strip())
            messagebox.showinfo("Done", "Download completed!", parent=self.root)
            return

        self._set_progress(0)
        detail = error or f"yt-dlp exited with code {return_code}"
        self._log(f"\nERROR: Download failed: {detail}")
        self._set_status("Download failed")
        messagebox.showerror(
            "Download failed", f"Download failed.\n\n{detail}", parent=self.root
        )

    def _cancel_download(self) -> None:
        if not self._downloading:
            return
        self._cancelled = True
        self._log("\nCancelling download…")
        self._set_status("Cancelling…")
        process = self._process
        if process is not None:
            self._kill_process(process)

    def _kill_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if IS_WINDOWS:
                # yt-dlp spawns ffmpeg; terminate the whole process tree.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    check=False,
                )
            else:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        except OSError:
            try:
                process.kill()
            except OSError:
                pass

    # ── History ──────────────────────────────────────────────────────

    def _load_history(self) -> None:
        self._history = []
        current = history_path()
        legacy = legacy_history_path()

        for path in (current, legacy):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, list):
                continue
            self._history = [item for item in data if isinstance(item, str)][:50]
            if path == legacy and not current.exists():
                self._save_history()
            break

    def _save_history(self) -> None:
        path = history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self._history, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temp, path)
        except OSError as exc:
            self._log(f"Could not save history: {exc}")

    def _add_to_history(self, url: str) -> None:
        if not url:
            return
        if url in self._history:
            self._history.remove(url)
        self._history.insert(0, url)
        self._history = self._history[:50]
        self._save_history()

    def _show_history(self) -> None:
        self._load_history()

        hist_win = tk.Toplevel(self.root)
        hist_win.title("Download history")
        hist_win.geometry("640x360")
        hist_win.transient(self.root)
        hist_win.grab_set()

        frame = ttk.Frame(hist_win, padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.grid(row=0, column=1, sticky="ns")

        listbox = tk.Listbox(
            frame,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9) if IS_WINDOWS else "TkFixedFont",
            activestyle="none",
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=listbox.yview)

        for url in self._history:
            listbox.insert("end", url)

        def use_selected(event: Optional[tk.Event] = None) -> None:
            selection = listbox.curselection()
            if selection:
                self.url_var.set(listbox.get(selection[0]))
                hist_win.destroy()

        listbox.bind("<Double-Button-1>", use_selected)

        buttons = ttk.Frame(hist_win, padding=(8, 0, 8, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Use selected", command=use_selected).pack(
            side="left"
        )

        def clear_history() -> None:
            if messagebox.askyesno(
                "Clear history",
                "Remove all saved URLs?",
                parent=hist_win,
            ):
                self._history = []
                self._save_history()
                listbox.delete(0, "end")

        ttk.Button(buttons, text="Clear history", command=clear_history).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(buttons, text="Close", command=hist_win.destroy).pack(
            side="right"
        )

        if self._history:
            listbox.selection_set(0)

    # ── Shutdown ─────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._downloading:
            quit_now = messagebox.askyesno(
                "Quit",
                "A download is in progress. Cancel it and quit?",
                parent=self.root,
            )
            if not quit_now:
                return
            self._cancelled = True
            if self._process is not None:
                self._kill_process(self._process)

        self._closing = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main() -> None:
    _enable_dpi_awareness()
    _set_app_user_model_id()

    root = tk.Tk()
    app = YTDlpGUI(root)

    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        app.url_var.set(sys.argv[1])

    root.mainloop()


if __name__ == "__main__":
    main()
