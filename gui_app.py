#!/usr/bin/env python3
"""Visual interface for user-based Instagram downloads."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except Exception:  # noqa: BLE001
    Image = None
    ImageDraw = None
    ImageOps = None
    ImageTk = None

from app_backend import (
    COOKIE_FILE,
    FileIndexDB,
    USERS_DIR,
    discover_cookie_files,
    DownloadQueueWorker,
    add_manual_files,
    ensure_user_dirs,
    import_cookie_file,
    index_user_tree,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Instagram Downloader GUI")
        self.geometry("1180x760")
        self.minsize(980, 680)

        self.db = FileIndexDB()
        self.worker = DownloadQueueWorker(self.db, log=self.thread_safe_log)

        self.user_var = tk.StringVar()
        self.profile_var = tk.StringVar()
        self.cookie_source_var = tk.StringVar(value="file")
        self.selected_cookie_var = tk.StringVar(value="")
        self.manual_category_var = tk.StringVar(value="restore")
        self.copy_mode_var = tk.BooleanVar(value=True)
        self.media_filter_var = tk.StringVar(value="all")
        self.status_var = tk.StringVar(value="Hazır")
        self.cookie_files: list[Path] = []
        self.file_item_to_abs_path: dict[str, Path] = {}
        self.path_to_file_item: dict[str, str] = {}
        self.preview_photo = None
        self.current_selected_path: Path | None = None
        self.gallery_photo_refs: list = []
        self.gallery_media_items: list[tuple[str, Path]] = []
        self.gallery_render_index = 0
        self.gallery_render_after_id = None
        self.gallery_relayout_after_id = None
        self.log_visible = True
        self.current_file_rows: list[tuple[str, int, str, str, str]] = []
        self.latest_scan_rows: list[tuple[str, int, str, str, str]] = []
        self.sort_column = "modified"
        self.sort_desc = True
        self.latest_content_photo = None
        self.latest_story_photo = None
        self.latest_content_path: Path | None = None
        self.latest_story_path: Path | None = None

        self._build_ui()
        self.refresh_user_list()
        self.refresh_cookie_files()
        self.after(1000, self._refresh_queue_status)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        self.configure(bg="#f0f3f9")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f0f3f9")
        style.configure("Header.TLabel", font=("DejaVu Sans", 14, "bold"), background="#f0f3f9", foreground="#12243a")
        style.configure("Muted.TLabel", font=("DejaVu Sans", 10), background="#f0f3f9", foreground="#49607a")
        style.configure("Primary.TButton", font=("DejaVu Sans", 10, "bold"))

        root = ttk.Frame(self, padding=14)
        root.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(root, padding=(0, 0, 12, 0))
        left.pack(side=tk.LEFT, fill=tk.Y)

        right = ttk.Frame(root)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(left, text="Kullanıcılar", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(left, text="Tüm medya users/<kullanıcı>/ altında tutulur", style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 8))

        self.user_list = tk.Listbox(left, width=32, height=20, font=("DejaVu Sans", 10))
        self.user_list.pack(fill=tk.Y, expand=False)
        self.user_list.bind("<<ListboxSelect>>", self.on_user_selected)

        user_actions = ttk.Frame(left)
        user_actions.pack(fill=tk.X, pady=(8, 0))

        ttk.Entry(user_actions, textvariable=self.user_var).pack(fill=tk.X)
        ttk.Button(user_actions, text="Kullanıcı Oluştur / Seç", command=self.create_or_select_user, style="Primary.TButton").pack(fill=tk.X, pady=(6, 2))
        ttk.Button(user_actions, text="Klasörü Aç", command=self.open_user_folder).pack(fill=tk.X)
        ttk.Button(user_actions, text="Kullanıcıları Yenile", command=self.refresh_user_list).pack(fill=tk.X, pady=(6, 0))

        form = ttk.LabelFrame(right, text="Arka Plan İndirme", padding=12)
        form.pack(fill=tk.X)

        grid = ttk.Frame(form)
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="Kullanıcı").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        ttk.Entry(grid, textvariable=self.user_var).grid(row=0, column=1, sticky=tk.EW, pady=4)

        ttk.Label(grid, text="Instagram Profil").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        ttk.Entry(grid, textvariable=self.profile_var).grid(row=1, column=1, sticky=tk.EW, pady=4)

        ttk.Label(grid, text="Cookie Kaynağı").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        ttk.Combobox(
            grid,
            textvariable=self.cookie_source_var,
            values=("file", "chrome", "firefox", "selected-cookie"),
            state="normal",
        ).grid(row=2, column=1, sticky=tk.EW, pady=4)

        ttk.Label(grid, text="Kayıtlı Cookie").grid(row=3, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.cookie_file_combo = ttk.Combobox(
            grid,
            textvariable=self.selected_cookie_var,
            values=(),
            state="readonly",
        )
        self.cookie_file_combo.grid(row=3, column=1, sticky=tk.EW, pady=4)

        cookie_btns = ttk.Frame(form)
        cookie_btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(cookie_btns, text="Cookie Listesini Yenile", command=self.refresh_cookie_files).pack(side=tk.LEFT)
        ttk.Button(cookie_btns, text="Cookie Dosyası Ekle", command=self.import_cookie_file_ui).pack(side=tk.LEFT, padx=6)
        ttk.Button(cookie_btns, text="Seçileni Varsayılan Yap", command=self.apply_selected_cookie_as_default).pack(side=tk.LEFT)

        buttons = ttk.Frame(form)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="İndirmeyi Kuyruğa Ekle", command=self.enqueue_download, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(buttons, text="Kullanıcı Dosyalarını İndeksle", command=self.index_current_user).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Dosya Tablosunu Yenile", command=self.refresh_file_table).pack(side=tk.LEFT)
        ttk.Label(buttons, text="Filtre").pack(side=tk.LEFT, padx=(14, 6))
        self.media_filter_combo = ttk.Combobox(
            buttons,
            textvariable=self.media_filter_var,
            values=("all", "posts", "stories", "highlights", "reels", "tagged"),
            state="readonly",
            width=12,
        )
        self.media_filter_combo.pack(side=tk.LEFT)
        self.media_filter_combo.bind("<<ComboboxSelected>>", self.on_media_filter_changed)

        manual = ttk.LabelFrame(right, text="Manuel Dosya Ekle (silinen/mevcut dosya geri ekleme)", padding=12)
        manual.pack(fill=tk.X, pady=(10, 0))

        manual_row = ttk.Frame(manual)
        manual_row.pack(fill=tk.X)
        ttk.Label(manual_row, text="Kategori").pack(side=tk.LEFT)
        ttk.Entry(manual_row, textvariable=self.manual_category_var, width=24).pack(side=tk.LEFT, padx=(8, 12))
        ttk.Checkbutton(manual_row, text="Kullanıcı klasörüne kopyala", variable=self.copy_mode_var).pack(side=tk.LEFT)
        ttk.Button(manual_row, text="Dosya Seç ve Ekle", command=self.add_manual_files_ui).pack(side=tk.LEFT, padx=10)

        self.right_split = ttk.Panedwindow(right, orient=tk.VERTICAL)
        self.right_split.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        top_content = ttk.Frame(self.right_split)
        self.right_split.add(top_content, weight=9)

        self.log_container = ttk.Frame(self.right_split)
        self.right_split.add(self.log_container, weight=1)

        content_row = ttk.Frame(top_content)
        content_row.pack(fill=tk.BOTH, expand=True)
        content_row.rowconfigure(0, weight=1)
        content_row.columnconfigure(0, weight=30, minsize=340)
        content_row.columnconfigure(1, weight=42, minsize=460)
        content_row.columnconfigure(2, weight=28, minsize=320)

        table_frame = ttk.LabelFrame(content_row, text="İndekslenen Dosyalar", padding=8)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        table_inner = ttk.Frame(table_frame)
        table_inner.pack(fill=tk.BOTH, expand=True)

        self.file_table = ttk.Treeview(
            table_inner,
            columns=("path", "size", "modified", "source", "profile"),
            show="headings",
            height=12,
        )
        self.file_table.heading("path", text="Relative Path", command=lambda: self.sort_file_table("path"))
        self.file_table.heading("size", text="Boyut", command=lambda: self.sort_file_table("size"))
        self.file_table.heading("modified", text="Modified UTC", command=lambda: self.sort_file_table("modified"))
        self.file_table.heading("source", text="Kaynak", command=lambda: self.sort_file_table("source"))
        self.file_table.heading("profile", text="Profil", command=lambda: self.sort_file_table("profile"))

        self.file_table.column("path", width=220, anchor=tk.W)
        self.file_table.column("size", width=80, anchor=tk.E)
        self.file_table.column("modified", width=140, anchor=tk.W)
        self.file_table.column("source", width=90, anchor=tk.W)
        self.file_table.column("profile", width=100, anchor=tk.W)

        table_v_scroll = ttk.Scrollbar(table_inner, orient=tk.VERTICAL, command=self.file_table.yview)
        table_h_scroll = ttk.Scrollbar(table_inner, orient=tk.HORIZONTAL, command=self.file_table.xview)
        self.file_table.configure(yscrollcommand=table_v_scroll.set, xscrollcommand=table_h_scroll.set)

        self.file_table.grid(row=0, column=0, sticky="nsew")
        table_v_scroll.grid(row=0, column=1, sticky="ns")
        table_h_scroll.grid(row=1, column=0, sticky="ew")
        table_inner.rowconfigure(0, weight=1)
        table_inner.columnconfigure(0, weight=1)
        self.file_table.bind("<<TreeviewSelect>>", self.on_file_selected)

        preview = ttk.LabelFrame(content_row, text="Medya Önizleme", padding=8)
        preview.grid(row=0, column=1, sticky="nsew", padx=(0, 8))

        preview_top = ttk.Frame(preview)
        preview_top.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.preview_label = ttk.Label(preview_top, text="Dosya seçildiğinde thumbnail burada gösterilir", anchor=tk.CENTER)
        self.preview_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        preview_info = ttk.Frame(preview)
        preview_info.pack(fill=tk.X)
        self.preview_meta_var = tk.StringVar(value="")
        ttk.Label(preview_info, textvariable=self.preview_meta_var).pack(side=tk.LEFT)
        ttk.Button(preview_info, text="Dosyayı Aç", command=self.open_selected_media).pack(side=tk.RIGHT)

        latest_wrap = ttk.LabelFrame(preview, text="Seçilen Kullanıcının Son Eklenenleri", padding=6)
        latest_wrap.pack(fill=tk.X, pady=(8, 0))
        latest_wrap.columnconfigure(0, weight=1)
        latest_wrap.columnconfigure(1, weight=1)

        latest_content = ttk.Frame(latest_wrap)
        latest_content.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(latest_content, text="Son İçerik").pack(anchor=tk.W)
        self.latest_content_preview = ttk.Label(latest_content, text="-", anchor=tk.CENTER)
        self.latest_content_preview.pack(fill=tk.X, pady=(4, 2))
        self.latest_content_meta_var = tk.StringVar(value="Yok")
        ttk.Label(latest_content, textvariable=self.latest_content_meta_var).pack(anchor=tk.W)
        ttk.Button(latest_content, text="Aç", command=self.open_latest_content).pack(anchor=tk.E, pady=(4, 0))

        latest_story = ttk.Frame(latest_wrap)
        latest_story.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(latest_story, text="Son Story").pack(anchor=tk.W)
        self.latest_story_preview = ttk.Label(latest_story, text="-", anchor=tk.CENTER)
        self.latest_story_preview.pack(fill=tk.X, pady=(4, 2))
        self.latest_story_meta_var = tk.StringVar(value="Yok")
        ttk.Label(latest_story, textvariable=self.latest_story_meta_var).pack(anchor=tk.W)
        ttk.Button(latest_story, text="Aç", command=self.open_latest_story).pack(anchor=tk.E, pady=(4, 0))

        self.latest_content_preview.bind("<Button-1>", lambda _e: self.open_latest_content())
        self.latest_story_preview.bind("<Button-1>", lambda _e: self.open_latest_story())

        gallery = ttk.LabelFrame(content_row, text="Thumbnail Galeri", padding=8)
        gallery.grid(row=0, column=2, sticky="nsew")

        gallery_inner = ttk.Frame(gallery)
        gallery_inner.pack(fill=tk.BOTH, expand=True)

        self.gallery_canvas = tk.Canvas(gallery_inner, bg="#0e1726", highlightthickness=0)
        self.gallery_scrollbar = ttk.Scrollbar(gallery_inner, orient=tk.VERTICAL, command=self.gallery_canvas.yview)
        self.gallery_h_scrollbar = ttk.Scrollbar(gallery_inner, orient=tk.HORIZONTAL, command=self.gallery_canvas.xview)
        self.gallery_canvas.configure(
            yscrollcommand=self.gallery_scrollbar.set,
            xscrollcommand=self.gallery_h_scrollbar.set,
        )
        self.gallery_canvas.grid(row=0, column=0, sticky="nsew")
        self.gallery_scrollbar.grid(row=0, column=1, sticky="ns")
        self.gallery_h_scrollbar.grid(row=1, column=0, sticky="ew")
        gallery_inner.rowconfigure(0, weight=1)
        gallery_inner.columnconfigure(0, weight=1)

        self.gallery_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_window_id = self.gallery_canvas.create_window((0, 0), window=self.gallery_frame, anchor="nw")
        self.gallery_frame.bind("<Configure>", self._on_gallery_configure)
        self.gallery_canvas.bind("<Configure>", self._on_gallery_canvas_resize)

        log_header = ttk.Frame(self.log_container)
        log_header.pack(fill=tk.X)
        ttk.Label(log_header, text="Log").pack(side=tk.LEFT)
        self.log_toggle_btn = ttk.Button(log_header, text="Gizle", width=10, command=self.toggle_log_panel)
        self.log_toggle_btn.pack(side=tk.RIGHT)

        self.log_body_frame = ttk.Frame(self.log_container)
        self.log_body_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.log_text = tk.Text(self.log_body_frame, height=6, bg="#0e1726", fg="#d8e6ff", insertbackground="#d8e6ff")
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.after(250, self._set_initial_log_height)

        status_bar = ttk.Frame(self, padding=(12, 0, 12, 8))
        status_bar.pack(fill=tk.X)
        ttk.Label(status_bar, textvariable=self.status_var).pack(side=tk.LEFT)

    def thread_safe_log(self, msg: str) -> None:
        self.after(0, lambda: self.log(msg))

    def log(self, msg: str) -> None:
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def _set_initial_log_height(self) -> None:
        try:
            total_h = self.right_split.winfo_height()
            if total_h > 260:
                self.right_split.sashpos(0, total_h - 140)
        except Exception:  # noqa: BLE001
            pass

    def _set_collapsed_log_height(self) -> None:
        try:
            total_h = self.right_split.winfo_height()
            if total_h > 120:
                self.right_split.sashpos(0, total_h - 34)
        except Exception:  # noqa: BLE001
            pass

    def toggle_log_panel(self) -> None:
        try:
            if self.log_visible:
                self.log_body_frame.pack_forget()
                self.log_visible = False
                self.log_toggle_btn.configure(text="Göster")
                self.after(20, self._set_collapsed_log_height)
            else:
                self.log_body_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
                self.log_visible = True
                self.log_toggle_btn.configure(text="Gizle")
                self.after(50, self._set_initial_log_height)
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def selected_user(self) -> str:
        user = self.user_var.get().strip()
        if not user:
            raise ValueError("Kullanıcı adı boş olamaz")
        return user

    def refresh_user_list(self) -> None:
        USERS_DIR.mkdir(parents=True, exist_ok=True)
        db_users = set(self.db.list_users())
        fs_users = {p.name for p in USERS_DIR.iterdir() if p.is_dir()}
        users = sorted(db_users | fs_users)

        self.user_list.delete(0, tk.END)
        for name in users:
            self.user_list.insert(tk.END, name)

        self.status_var.set(f"Kullanıcı sayısı: {len(users)}")

    def refresh_cookie_files(self) -> None:
        self.cookie_files = discover_cookie_files(include_example=False)
        labels = [p.name for p in self.cookie_files]
        self.cookie_file_combo["values"] = labels

        if labels and self.selected_cookie_var.get() not in labels:
            self.selected_cookie_var.set(labels[0])

        self.log(f"[*] Cookie listesi güncellendi: {len(labels)} dosya")

    def selected_cookie_path(self) -> Path:
        selected = self.selected_cookie_var.get().strip()
        if not selected:
            raise ValueError("Seçili cookie dosyası yok")
        for path in self.cookie_files:
            if path.name == selected:
                return path
        raise FileNotFoundError(f"Cookie dosyası bulunamadı: {selected}")

    def import_cookie_file_ui(self) -> None:
        try:
            file_path = filedialog.askopenfilename(
                title="Cookie JSON dosyası seç",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            )
            if not file_path:
                return

            imported = import_cookie_file(Path(file_path))
            self.refresh_cookie_files()
            self.selected_cookie_var.set(imported.name)
            self.log(f"[+] Cookie eklendi: {imported}")
            self.status_var.set(f"Cookie eklendi: {imported.name}")
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def apply_selected_cookie_as_default(self) -> None:
        try:
            selected = self.selected_cookie_path()
            if selected.resolve() == COOKIE_FILE.resolve():
                self.status_var.set("Zaten varsayılan cookie seçili")
                return
            from shutil import copy2

            copy2(selected, COOKIE_FILE)
            self.log(f"[+] Varsayılan cookie güncellendi: {selected.name} -> {COOKIE_FILE.name}")
            self.status_var.set(f"Varsayılan cookie: {selected.name}")
            self.cookie_source_var.set("file")
            self.refresh_cookie_files()
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def create_or_select_user(self) -> None:
        try:
            user = self.selected_user()
            ensure_user_dirs(user)
            self.db.ensure_user(user)
            self.refresh_user_list()
            self.status_var.set(f"Kullanıcı hazır: {user}")
            self.log(f"[+] Kullanıcı hazırlandı: {user}")
            self.refresh_file_table()
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def on_user_selected(self, _event=None) -> None:
        if not self.user_list.curselection():
            return
        idx = self.user_list.curselection()[0]
        user = self.user_list.get(idx)
        self.user_var.set(user)
        self.refresh_file_table()

    def enqueue_download(self) -> None:
        try:
            user = self.selected_user()
            profile = self.profile_var.get().strip() or user
            source = self.cookie_source_var.get().strip() or "file"
            if source == "selected-cookie":
                cookie_path = self.selected_cookie_path()
                source = f"cookie:{cookie_path}"

            ensure_user_dirs(user)
            self.db.ensure_user(user)
            self.worker.enqueue(user, profile, source)
            self.status_var.set(f"Kuyrukta bekleyen iş: {self.worker.pending_jobs()}")
            self.log(f"[q] İndirme kuyruğa alındı: user={user}, profile={profile}, source={source}")
            self.refresh_user_list()
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def index_current_user(self) -> None:
        try:
            user = self.selected_user()
            count = index_user_tree(self.db, user)
            self.refresh_file_table()
            self.status_var.set(f"İndeksleme tamamlandı: {count} dosya")
            self.log(f"[+] İndekslendi: {count} dosya, user={user}")
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def add_manual_files_ui(self) -> None:
        try:
            user = self.selected_user()
            files = filedialog.askopenfilenames(title="Eklenecek dosyaları seç")
            if not files:
                return
            paths = [Path(p) for p in files]
            added = add_manual_files(
                db=self.db,
                user_name=user,
                src_files=paths,
                category=self.manual_category_var.get().strip() or "restore",
                copy_into_user_folder=bool(self.copy_mode_var.get()),
            )
            self.refresh_file_table()
            self.status_var.set(f"Manuel dosya eklendi: {added}")
            self.log(f"[+] Manuel dosya eklendi: {added}, user={user}")
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def refresh_file_table(self) -> None:
        self.file_item_to_abs_path.clear()
        self.path_to_file_item.clear()
        for item in self.file_table.get_children():
            self.file_table.delete(item)

        user = self.user_var.get().strip()
        if not user:
            self.update_latest_user_previews(None, [])
            return
        user_root = ensure_user_dirs(user)

        self.latest_scan_rows = [
            row for row in self.db.list_user_files(user, limit=3000)
            if not self._is_thumb_cache_path(row[0])
        ]
        self.current_file_rows = self._filtered_rows(self.latest_scan_rows)[:1000]
        self.sort_file_table(self.sort_column, keep_direction=True)
        self.status_var.set(
            f"{user}: {len(self.current_file_rows)} dosya | filtre={self.media_filter_var.get()}"
        )
        self.clear_preview()
        self.populate_thumbnail_gallery()
        self.update_latest_user_previews(user_root, self.latest_scan_rows)

    def on_media_filter_changed(self, _event=None) -> None:
        user = self.user_var.get().strip()
        if not user:
            return
        self.current_file_rows = self._filtered_rows(self.latest_scan_rows)[:1000]
        self.sort_file_table(self.sort_column, keep_direction=True)
        self.clear_preview()
        self.populate_thumbnail_gallery()
        self.status_var.set(
            f"{user}: {len(self.current_file_rows)} dosya | filtre={self.media_filter_var.get()}"
        )

    def _render_file_table_rows(self, rows: list[tuple[str, int, str, str, str]], user_root: Path) -> None:
        self.file_item_to_abs_path.clear()
        self.path_to_file_item.clear()
        for item in self.file_table.get_children():
            self.file_table.delete(item)

        for rel_path, size_bytes, modified_at, source_type, profile in rows:
            abs_path = user_root / rel_path
            item_id = self.file_table.insert(
                "",
                tk.END,
                values=(rel_path, self._format_size(size_bytes), modified_at, source_type, profile),
            )
            self.file_item_to_abs_path[item_id] = abs_path
            self.path_to_file_item[str(abs_path.resolve())] = item_id

    def sort_file_table(self, column: str, keep_direction: bool = False) -> None:
        user = self.user_var.get().strip()
        if not user or not self.current_file_rows:
            return

        if not keep_direction:
            if self.sort_column == column:
                self.sort_desc = not self.sort_desc
            else:
                self.sort_column = column
                self.sort_desc = False
        else:
            self.sort_column = column

        if column == "path":
            key_fn = lambda r: r[0].lower()
        elif column == "size":
            key_fn = lambda r: r[1]
        elif column == "modified":
            key_fn = lambda r: r[2]
        elif column == "source":
            key_fn = lambda r: r[3].lower()
        else:
            key_fn = lambda r: r[4].lower()

        self.current_file_rows.sort(key=key_fn, reverse=self.sort_desc)
        self._render_file_table_rows(self.current_file_rows, ensure_user_dirs(user))

    def _refresh_queue_status(self) -> None:
        pending = self.worker.pending_jobs()
        base = self.status_var.get().split("|")[0].strip()
        self.status_var.set(f"{base} | Kuyruk: {pending}")
        self.after(1500, self._refresh_queue_status)

    @staticmethod
    def _format_size(size: int) -> str:
        value = float(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if value < 1024.0:
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{value:.1f} TB"

    def open_user_folder(self) -> None:
        try:
            user = self.selected_user()
            path = ensure_user_dirs(user)
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def clear_preview(self) -> None:
        self.preview_photo = None
        self.current_selected_path = None
        self.preview_label.configure(image="", text="Dosya seçildiğinde thumbnail burada gösterilir")
        self.preview_meta_var.set("")

    @staticmethod
    def _is_story_path(rel_path: str) -> bool:
        p = rel_path.replace("\\", "/").lower()
        return "/stories/" in p or "/:stories/" in p or p.startswith("stories/") or p.startswith(":stories/")

    @staticmethod
    def _is_thumb_cache_path(rel_path: str) -> bool:
        p = rel_path.replace("\\", "/").lower()
        return "/.thumb_cache/" in p or p.startswith(".thumb_cache/") or "/.thumbcache/" in p or p.startswith(".thumbcache/")

    @staticmethod
    def _is_media_path(rel_path: str) -> bool:
        ext = Path(rel_path).suffix.lower()
        return ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS

    @staticmethod
    def _normalized_rel_path(rel_path: str) -> str:
        return rel_path.replace("\\", "/").lower()

    def _is_tagged_path(self, rel_path: str) -> bool:
        p = self._normalized_rel_path(rel_path)
        return ":tagged" in p or "/tagged/" in p

    def _is_highlight_path(self, rel_path: str) -> bool:
        p = self._normalized_rel_path(rel_path)
        highlight_keys = ("/highlights/", "/highlight/", "öne çıkanlar", "one cikanlar")
        return any(k in p for k in highlight_keys)

    def _is_reel_path(self, rel_path: str) -> bool:
        p = self._normalized_rel_path(rel_path)
        return "/reels/" in p or "/reel/" in p or "_reel" in p or p.endswith("reel")

    def _media_category(self, rel_path: str) -> str:
        if self._is_story_path(rel_path):
            return "stories"
        if self._is_tagged_path(rel_path):
            return "tagged"
        if self._is_highlight_path(rel_path):
            return "highlights"
        if self._is_reel_path(rel_path):
            return "reels"
        return "posts"

    def _filtered_rows(self, rows: list[tuple[str, int, str, str, str]]) -> list[tuple[str, int, str, str, str]]:
        selected = self.media_filter_var.get().strip().lower() or "all"
        if selected == "all":
            return list(rows)
        return [row for row in rows if self._media_category(row[0]) == selected]

    def update_latest_user_previews(self, user_root: Path | None, rows: list[tuple[str, int, str, str, str]]) -> None:
        self.latest_content_photo = None
        self.latest_story_photo = None
        self.latest_content_path = None
        self.latest_story_path = None

        if user_root is None or not rows:
            self.latest_content_preview.configure(image="", text="Yok")
            self.latest_story_preview.configure(image="", text="Yok")
            self.latest_content_meta_var.set("Yok")
            self.latest_story_meta_var.set("Yok")
            return

        latest_content = None
        latest_story = None
        for row in rows:
            rel_path = row[0]
            if not self._is_media_path(rel_path):
                continue
            if latest_story is None and self._is_story_path(rel_path):
                latest_story = row
            if latest_content is None and not self._is_story_path(rel_path):
                latest_content = row
            if latest_content is not None and latest_story is not None:
                break

        self._set_latest_card(kind="content", row=latest_content, user_root=user_root)
        self._set_latest_card(kind="story", row=latest_story, user_root=user_root)

    def _set_latest_card(self, kind: str, row: tuple[str, int, str, str, str] | None, user_root: Path) -> None:
        if kind == "content":
            preview_label = self.latest_content_preview
            meta_var = self.latest_content_meta_var
        else:
            preview_label = self.latest_story_preview
            meta_var = self.latest_story_meta_var

        if row is None:
            preview_label.configure(image="", text="Yok")
            meta_var.set("Yok")
            if kind == "content":
                self.latest_content_path = None
                self.latest_content_photo = None
            else:
                self.latest_story_path = None
                self.latest_story_photo = None
            return

        rel_path, size_bytes, _modified_at, _source_type, _profile = row
        media_path = user_root / rel_path
        if not media_path.exists():
            preview_label.configure(image="", text="Dosya yok")
            meta_var.set(self._truncate_name(Path(rel_path).name, 24))
            if kind == "content":
                self.latest_content_path = None
                self.latest_content_photo = None
            else:
                self.latest_story_path = None
                self.latest_story_photo = None
            return

        thumb = self.build_preview_image(media_path, size=(280, 180), for_gallery=True)
        if thumb is None:
            preview_label.configure(image="", text="Önizleme yok")
        else:
            preview_label.configure(image=thumb, text="")

        meta_var.set(f"{self._truncate_name(media_path.name, 24)} | {self._format_size(size_bytes)}")
        if kind == "content":
            self.latest_content_path = media_path
            self.latest_content_photo = thumb
        else:
            self.latest_story_path = media_path
            self.latest_story_photo = thumb

    def open_latest_content(self) -> None:
        self._open_latest_path(self.latest_content_path)

    def open_latest_story(self) -> None:
        self._open_latest_path(self.latest_story_path)

    def _open_latest_path(self, path: Path | None) -> None:
        if path is None:
            messagebox.showinfo("Bilgi", "Uygun dosya bulunamadı")
            return
        key = str(path.resolve())
        item_id = self.path_to_file_item.get(key)
        if item_id:
            self.select_file_table_item(item_id)
            return
        self.current_selected_path = path
        self.open_selected_media()

    def _on_gallery_configure(self, _event=None) -> None:
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def _on_gallery_canvas_resize(self, event) -> None:
        self.gallery_canvas.itemconfigure(self.gallery_window_id, width=event.width)
        if self.gallery_media_items and self.gallery_render_after_id is None:
            if self.gallery_relayout_after_id is not None:
                try:
                    self.after_cancel(self.gallery_relayout_after_id)
                except Exception:  # noqa: BLE001
                    pass
            self.gallery_relayout_after_id = self.after(180, self._relayout_gallery)

    def _relayout_gallery(self) -> None:
        self.gallery_relayout_after_id = None
        self.populate_thumbnail_gallery()

    def clear_thumbnail_gallery(self) -> None:
        if self.gallery_render_after_id is not None:
            try:
                self.after_cancel(self.gallery_render_after_id)
            except Exception:  # noqa: BLE001
                pass
            self.gallery_render_after_id = None
        if self.gallery_relayout_after_id is not None:
            try:
                self.after_cancel(self.gallery_relayout_after_id)
            except Exception:  # noqa: BLE001
                pass
            self.gallery_relayout_after_id = None
        self.gallery_photo_refs.clear()
        self.gallery_media_items = []
        self.gallery_render_index = 0
        for child in self.gallery_frame.winfo_children():
            child.destroy()

    def populate_thumbnail_gallery(self) -> None:
        self.clear_thumbnail_gallery()
        media_items: list[tuple[str, Path]] = []
        for item_id, path in self.file_item_to_abs_path.items():
            ext = path.suffix.lower()
            if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                media_items.append((item_id, path))

        if not media_items:
            ttk.Label(self.gallery_frame, text="Galeride gösterilecek resim/video yok").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
            return

        self.gallery_media_items = media_items[:72]
        self.gallery_render_index = 0
        self.gallery_render_after_id = self.after(1, self._render_gallery_batch)

    def _render_gallery_batch(self) -> None:
        batch_size = 8
        canvas_w = max(1, self.gallery_canvas.winfo_width())
        columns = max(1, canvas_w // 220)
        end_index = min(self.gallery_render_index + batch_size, len(self.gallery_media_items))

        for idx in range(self.gallery_render_index, end_index):
            item_id, path = self.gallery_media_items[idx]
            thumb = self.build_preview_image(path, size=(200, 140), for_gallery=True)
            if thumb is None:
                continue
            self.gallery_photo_refs.append(thumb)

            cell = ttk.Frame(self.gallery_frame, padding=4)
            row = idx // columns
            col = idx % columns
            cell.grid(row=row, column=col, sticky=tk.NW)

            btn = tk.Button(
                cell,
                image=thumb,
                relief=tk.FLAT,
                bg="#0e1726",
                activebackground="#1e2d42",
                command=lambda iid=item_id: self.select_file_table_item(iid),
                cursor="hand2",
            )
            btn.pack()

            ttk.Label(cell, text=self._truncate_name(path.name, 22)).pack(pady=(4, 0))

        self.gallery_render_index = end_index
        if self.gallery_render_index < len(self.gallery_media_items):
            self.gallery_render_after_id = self.after(1, self._render_gallery_batch)
        else:
            self.gallery_render_after_id = None

    def _truncate_name(self, name: str, max_len: int) -> str:
        if len(name) <= max_len:
            return name
        return f"{name[:max_len-3]}..."

    def select_file_table_item(self, item_id: str) -> None:
        if item_id not in self.file_item_to_abs_path:
            return
        self.file_table.selection_set(item_id)
        self.file_table.focus(item_id)
        self.file_table.see(item_id)
        self.on_file_selected()

    def on_file_selected(self, _event=None) -> None:
        selected = self.file_table.selection()
        if not selected:
            self.clear_preview()
            return

        item_id = selected[0]
        media_path = self.file_item_to_abs_path.get(item_id)
        if media_path is None:
            self.clear_preview()
            return

        self.current_selected_path = media_path
        ext = media_path.suffix.lower()
        kind = "Resim" if ext in IMAGE_EXTENSIONS else "Video" if ext in VIDEO_EXTENSIONS else "Dosya"

        if not media_path.exists():
            self.preview_label.configure(image="", text="Dosya bulunamadı")
            self.preview_meta_var.set(f"{kind} | {media_path.name}")
            return

        preview_img = self.build_preview_image(media_path)
        if preview_img is None:
            self.preview_photo = None
            self.preview_label.configure(image="", text=f"Önizleme yok ({ext or 'bilinmeyen uzantı'})")
        else:
            self.preview_photo = preview_img
            self.preview_label.configure(image=self.preview_photo, text="")

        self.preview_meta_var.set(f"{kind} | {media_path.name} | {self._format_size(media_path.stat().st_size)}")

    def build_preview_image(self, media_path: Path, size: tuple[int, int] = (700, 460), for_gallery: bool = False):
        if Image is None or ImageTk is None:
            return None

        ext = media_path.suffix.lower()
        image_path = media_path
        if ext in VIDEO_EXTENSIONS:
            thumb_path = self.generate_video_thumbnail(media_path, create_if_missing=not for_gallery)
            if thumb_path is None:
                return self.create_placeholder_preview(ext, size=size)
            image_path = thumb_path
        elif ext not in IMAGE_EXTENSIONS:
            return self.create_placeholder_preview(ext, size=size)

        try:
            with Image.open(image_path) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail(size)
                canvas = Image.new("RGB", size, color=(17, 22, 32))
                x = (size[0] - img.width) // 2
                y = (size[1] - img.height) // 2
                canvas.paste(img.convert("RGB"), (x, y))
                return ImageTk.PhotoImage(canvas)
        except Exception:  # noqa: BLE001
            return self.create_placeholder_preview(ext, size=size)

    def create_placeholder_preview(self, ext: str, size: tuple[int, int] = (700, 460)):
        if Image is None or ImageTk is None:
            return None
        img = Image.new("RGB", size, color=(18, 26, 40))
        if ImageDraw is not None:
            draw = ImageDraw.Draw(img)
            w, h = size
            draw.rectangle((10, 10, w - 10, h - 10), outline=(70, 94, 122), width=2)
            draw.text((18, max(18, h // 2 - 8)), f"Preview yok: {ext or 'unknown'}", fill=(212, 229, 255))
        return ImageTk.PhotoImage(img)

    def generate_video_thumbnail(self, media_path: Path, create_if_missing: bool = True) -> Path | None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return None

        cache_root = ensure_user_dirs(self.user_var.get().strip() or "default") / ".thumb_cache"
        cache_root.mkdir(parents=True, exist_ok=True)

        stamp = str(media_path.stat().st_mtime_ns)
        key = hashlib.sha256(f"{media_path.resolve()}::{stamp}".encode("utf-8")).hexdigest()[:20]
        out_path = cache_root / f"{key}.png"
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path

        if not create_if_missing:
            return None

        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            "00:00:00.5",
            "-i",
            str(media_path),
            "-frames:v",
            "1",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
        except Exception:  # noqa: BLE001
            return None
        return None

    def open_selected_media(self) -> None:
        if self.current_selected_path is None:
            messagebox.showinfo("Bilgi", "Önce bir dosya seçin")
            return
        path = self.current_selected_path
        if not path.exists():
            messagebox.showerror("Hata", f"Dosya bulunamadı: {path}")
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Hata", str(ex))

    def on_close(self) -> None:
        self.worker.stop()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
