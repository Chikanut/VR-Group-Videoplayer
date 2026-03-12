from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .controller import QuestUpdaterController
from .models import UpdaterSettings


class QuestUpdaterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VR Quest Updater")
        self.geometry("1480x920")
        self.minsize(1200, 760)

        self.controller = QuestUpdaterController()

        self.settings_vars = {
            "package_id": tk.StringVar(value=self.controller.settings.package_id),
            "app_config_path": tk.StringVar(value=self.controller.settings.app_config_path),
            "apk_path": tk.StringVar(value=self.controller.settings.apk_path),
            "content_root": tk.StringVar(value=self.controller.settings.content_root),
            "player_http_port": tk.StringVar(value=str(self.controller.settings.player_http_port)),
            "max_concurrent_installs": tk.StringVar(value=str(self.controller.settings.max_concurrent_installs)),
            "max_concurrent_uploads": tk.StringVar(value=str(self.controller.settings.max_concurrent_uploads)),
            "prefer_wifi": tk.BooleanVar(value=self.controller.settings.prefer_wifi),
            "verify_http": tk.BooleanVar(value=self.controller.settings.verify_http),
            "launch_after_install": tk.BooleanVar(value=self.controller.settings.launch_after_install),
            "auto_scan_media": tk.BooleanVar(value=self.controller.settings.auto_scan_media),
            "force_reinstall_apk": tk.BooleanVar(value=self.controller.settings.force_reinstall_apk),
        }

        self._build_layout()
        self._populate_required_files()
        self._poll_events()

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        settings_frame = ttk.LabelFrame(self, text="Settings")
        settings_frame.grid(row=0, column=0, sticky="ns", padx=12, pady=12)
        settings_frame.columnconfigure(1, weight=1)

        row = 0
        row = self._settings_row(settings_frame, row, "Package ID", "package_id")
        row = self._settings_row(settings_frame, row, "App config", "app_config_path", browse="file")
        row = self._settings_row(settings_frame, row, "APK path", "apk_path", browse="file")
        row = self._settings_row(settings_frame, row, "Content root", "content_root", browse="dir")
        row = self._settings_row(settings_frame, row, "Player HTTP port", "player_http_port")
        row = self._settings_row(settings_frame, row, "Install concurrency", "max_concurrent_installs")
        row = self._settings_row(settings_frame, row, "Upload concurrency", "max_concurrent_uploads")

        options = ttk.LabelFrame(settings_frame, text="Behavior")
        options.grid(row=row, column=0, columnspan=3, sticky="ew", padx=8, pady=(12, 8))
        options.columnconfigure(0, weight=1)
        ttk.Checkbutton(options, text="Prefer Wi-Fi after pairing", variable=self.settings_vars["prefer_wifi"]).grid(
            row=0, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(options, text="Verify inventory over player HTTP", variable=self.settings_vars["verify_http"]).grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(options, text="Launch player after install", variable=self.settings_vars["launch_after_install"]).grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(options, text="Trigger media scan after upload", variable=self.settings_vars["auto_scan_media"]).grid(
            row=3, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Checkbutton(options, text="Force reinstall APK on every apply", variable=self.settings_vars["force_reinstall_apk"]).grid(
            row=4, column=0, sticky="w", padx=8, pady=4
        )

        buttons = ttk.Frame(settings_frame)
        buttons.grid(row=row + 1, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))
        buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(buttons, text="Save Settings", command=self._save_settings).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="Reload Files", command=self._reload_required_files).grid(row=0, column=1, sticky="ew")

        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=2)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        devices_frame = ttk.LabelFrame(right, text="Devices")
        devices_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        devices_frame.columnconfigure(0, weight=1)
        devices_frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(devices_frame)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for idx in range(5):
            toolbar.columnconfigure(idx, weight=1)
        ttk.Button(toolbar, text="Discover", command=self._discover).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(toolbar, text="Pair Wi-Fi", command=self._pair_wifi).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(toolbar, text="Plan", command=self._plan_selected).grid(row=0, column=2, sticky="ew", padx=(0, 6))
        ttk.Button(toolbar, text="Apply", command=self._apply_selected).grid(row=0, column=3, sticky="ew", padx=(0, 6))
        ttk.Button(toolbar, text="Select All", command=self._select_all_devices).grid(row=0, column=4, sticky="ew")

        self.devices_tree = ttk.Treeview(
            devices_frame,
            columns=("serial", "transport", "model", "ip", "app", "player", "stage", "plan", "note"),
            show="headings",
            selectmode="extended",
        )
        for key, heading, width in (
            ("serial", "Serial", 180),
            ("transport", "Transport", 75),
            ("model", "Model", 130),
            ("ip", "IP", 120),
            ("app", "Installed App", 140),
            ("player", "Player HTTP", 100),
            ("stage", "Stage", 100),
            ("plan", "Plan", 240),
            ("note", "Note", 220),
        ):
            self.devices_tree.heading(key, text=heading)
            self.devices_tree.column(key, width=width, anchor="w")
        self.devices_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        devices_scroll = ttk.Scrollbar(devices_frame, orient="vertical", command=self.devices_tree.yview)
        devices_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 8), padx=(0, 8))
        self.devices_tree.configure(yscrollcommand=devices_scroll.set)

        files_frame = ttk.LabelFrame(right, text="Required Files")
        files_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(1, weight=1)

        files_toolbar = ttk.Frame(files_frame)
        files_toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        files_toolbar.columnconfigure((0, 1), weight=1)
        ttk.Button(files_toolbar, text="Browse Selected Override", command=self._browse_selected_file_override).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(files_toolbar, text="Clear Selected Override", command=self._clear_selected_file_override).grid(
            row=0, column=1, sticky="ew"
        )

        self.files_tree = ttk.Treeview(
            files_frame,
            columns=("filename", "path", "size", "status", "note"),
            show="headings",
            selectmode="browse",
        )
        for key, heading, width in (
            ("filename", "Filename", 260),
            ("path", "Local Path", 420),
            ("size", "Size", 110),
            ("status", "Status", 90),
            ("note", "Note", 160),
        ):
            self.files_tree.heading(key, text=heading)
            self.files_tree.column(key, width=width, anchor="w")
        self.files_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        files_scroll = ttk.Scrollbar(files_frame, orient="vertical", command=self.files_tree.yview)
        files_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 8), padx=(0, 8))
        self.files_tree.configure(yscrollcommand=files_scroll.set)

        jobs_frame = ttk.LabelFrame(right, text="Transfer Progress")
        jobs_frame.grid(row=2, column=0, sticky="nsew")
        jobs_frame.columnconfigure(0, weight=1)
        jobs_frame.rowconfigure(0, weight=1)
        jobs_frame.rowconfigure(1, weight=0)

        self.jobs_tree = ttk.Treeview(
            jobs_frame,
            columns=("device", "file", "percent", "transferred", "speed", "state", "note"),
            show="headings",
            selectmode="browse",
        )
        for key, heading, width in (
            ("device", "Device", 180),
            ("file", "File", 260),
            ("percent", "Percent", 80),
            ("transferred", "Transferred", 160),
            ("speed", "Speed", 110),
            ("state", "State", 90),
            ("note", "Note", 180),
        ):
            self.jobs_tree.heading(key, text=heading)
            self.jobs_tree.column(key, width=width, anchor="w")
        self.jobs_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        jobs_scroll = ttk.Scrollbar(jobs_frame, orient="vertical", command=self.jobs_tree.yview)
        jobs_scroll.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 8))
        self.jobs_tree.configure(yscrollcommand=jobs_scroll.set)

        transfer_detail = ttk.Frame(jobs_frame)
        transfer_detail.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        transfer_detail.columnconfigure(0, weight=1)
        self.current_transfer_var = tk.StringVar(value="No active transfer")
        self.current_transfer_note_var = tk.StringVar(value="")
        ttk.Label(transfer_detail, textvariable=self.current_transfer_var).grid(row=0, column=0, sticky="w")
        self.current_transfer_bar = ttk.Progressbar(transfer_detail, maximum=100)
        self.current_transfer_bar.grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Label(transfer_detail, textvariable=self.current_transfer_note_var).grid(row=2, column=0, sticky="w")

        footer = ttk.Frame(self)
        footer.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12))
        footer.columnconfigure(0, weight=1)
        footer.rowconfigure(1, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.log_text = ScrolledText(footer, height=10, wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.log_text.configure(state="disabled")

    def _settings_row(self, parent, row: int, label: str, key: str, browse: str | None = None) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(parent, textvariable=self.settings_vars[key], width=42).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        if browse == "file":
            ttk.Button(parent, text="Browse", command=lambda current=key: self._browse_file(current)).grid(
                row=row, column=2, sticky="ew", padx=(0, 8), pady=4
            )
        elif browse == "dir":
            ttk.Button(parent, text="Browse", command=lambda current=key: self._browse_directory(current)).grid(
                row=row, column=2, sticky="ew", padx=(0, 8), pady=4
            )
        return row + 1

    def _browse_file(self, key: str) -> None:
        initial = self.settings_vars[key].get().strip() or str(Path.cwd())
        initial_path = Path(initial)
        directory = str(initial_path.parent if initial_path.exists() else Path.cwd())
        path = filedialog.askopenfilename(initialdir=directory)
        if path:
            self.settings_vars[key].set(path)

    def _browse_directory(self, key: str) -> None:
        initial = self.settings_vars[key].get().strip() or str(Path.cwd())
        path = filedialog.askdirectory(initialdir=initial if Path(initial).exists() else str(Path.cwd()))
        if path:
            self.settings_vars[key].set(path)

    def _save_settings(self) -> None:
        try:
            settings = UpdaterSettings(
                package_id=self.settings_vars["package_id"].get(),
                app_config_path=self.settings_vars["app_config_path"].get(),
                apk_path=self.settings_vars["apk_path"].get(),
                content_root=self.settings_vars["content_root"].get(),
                player_http_port=int(self.settings_vars["player_http_port"].get() or "8080"),
                max_concurrent_installs=int(self.settings_vars["max_concurrent_installs"].get() or "8"),
                max_concurrent_uploads=int(self.settings_vars["max_concurrent_uploads"].get() or "4"),
                prefer_wifi=self.settings_vars["prefer_wifi"].get(),
                verify_http=self.settings_vars["verify_http"].get(),
                launch_after_install=self.settings_vars["launch_after_install"].get(),
                auto_scan_media=self.settings_vars["auto_scan_media"].get(),
                force_reinstall_apk=self.settings_vars["force_reinstall_apk"].get(),
                local_path_overrides=self.controller.settings.local_path_overrides,
            ).normalized()
        except ValueError:
            messagebox.showerror("Invalid settings", "Numeric fields must contain valid numbers.")
            return

        self.controller.set_settings(settings)
        self.status_var.set("Settings saved")

    def _reload_required_files(self) -> None:
        self._save_settings()
        self.controller.refresh_required_files()

    def _discover(self) -> None:
        self._save_settings()
        self.controller.discover_async()

    def _pair_wifi(self) -> None:
        serials = self._selected_device_serials()
        self._save_settings()
        self.controller.pair_wifi_async(serials)

    def _plan_selected(self) -> None:
        serials = self._selected_device_serials()
        self._save_settings()
        self.controller.plan_async(serials)

    def _apply_selected(self) -> None:
        serials = self._selected_device_serials()
        if not serials:
            messagebox.showinfo("No devices selected", "Select one or more devices first.")
            return
        self._save_settings()
        self.controller.apply_async(serials)

    def _selected_device_serials(self) -> list[str]:
        return list(self.devices_tree.selection())

    def _select_all_devices(self) -> None:
        self.devices_tree.selection_set(self.devices_tree.get_children())

    def _selected_required_filename(self) -> str:
        selection = self.files_tree.selection()
        return selection[0] if selection else ""

    def _browse_selected_file_override(self) -> None:
        filename = self._selected_required_filename()
        if not filename:
            messagebox.showinfo("No file selected", "Select a required file row first.")
            return
        path = filedialog.askopenfilename(title=f"Select local source for {filename}")
        if path:
            self.controller.set_required_file_override(filename, path)

    def _clear_selected_file_override(self) -> None:
        filename = self._selected_required_filename()
        if filename:
            self.controller.set_required_file_override(filename, "")

    def _populate_required_files(self) -> None:
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        for file_spec in self.controller.required_files:
            self.files_tree.insert(
                "",
                "end",
                iid=file_spec.filename,
                values=(
                    file_spec.filename,
                    file_spec.source_path,
                    self._format_bytes(file_spec.size_bytes),
                    file_spec.status,
                    file_spec.note,
                ),
            )

    def _poll_events(self) -> None:
        while not self.controller.events.empty():
            event = self.controller.events.get()
            event_type = event.get("type")
            if event_type == "log":
                self._append_log(event["ts"], event["message"])
            elif event_type == "devices_updated":
                self._refresh_devices(event["devices"])
            elif event_type == "device_updated":
                self._upsert_device(event["device"])
            elif event_type == "required_files_updated":
                self._refresh_required_files(event["files"])
            elif event_type == "upload_reset":
                for item in self.jobs_tree.get_children():
                    self.jobs_tree.delete(item)
                self.current_transfer_var.set("No active transfer")
                self.current_transfer_note_var.set("")
                self.current_transfer_bar["value"] = 0
            elif event_type == "upload_updated":
                self._upsert_upload(event["job"])
            elif event_type == "busy":
                self.status_var.set(event.get("label") or "Ready")
        self.after(150, self._poll_events)

    def _append_log(self, ts: str, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _refresh_devices(self, devices: list[dict]) -> None:
        existing = set(self.devices_tree.get_children())
        incoming = {device["serial"] for device in devices}
        for stale in existing - incoming:
            self.devices_tree.delete(stale)
        for device in devices:
            self._upsert_device(device)

    def _upsert_device(self, device: dict) -> None:
        serial = device["serial"]
        values = (
            serial,
            device.get("transport", ""),
            device.get("model", ""),
            device.get("ip", ""),
            self._app_version_text(device),
            "online" if device.get("player_http_ok") else "offline",
            device.get("stage", ""),
            device.get("plan_summary", ""),
            device.get("note", ""),
        )
        if serial in self.devices_tree.get_children():
            self.devices_tree.item(serial, values=values)
        else:
            self.devices_tree.insert("", "end", iid=serial, values=values)

    def _app_version_text(self, device: dict) -> str:
        if not device.get("package_installed"):
            return "not installed"
        name = device.get("installed_version_name") or "?"
        code = device.get("installed_version_code") or "?"
        return f"{name} ({code})"

    def _refresh_required_files(self, files: list[dict]) -> None:
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        for file_spec in files:
            self.files_tree.insert(
                "",
                "end",
                iid=file_spec["filename"],
                values=(
                    file_spec["filename"],
                    file_spec.get("source_path", ""),
                    self._format_bytes(file_spec.get("size_bytes", 0)),
                    file_spec.get("status", ""),
                    file_spec.get("note", ""),
                ),
            )

    def _upsert_upload(self, job: dict) -> None:
        job_id = job["job_id"]
        values = (
            job.get("device_label", ""),
            job.get("filename", ""),
            f"{job.get('percent', 0.0):.1f}%",
            f"{self._format_bytes(job.get('transferred_bytes', 0))} / {self._format_bytes(job.get('total_bytes', 0))}",
            self._format_speed(job.get("speed_bps", 0.0)),
            job.get("state", ""),
            job.get("note", ""),
        )
        if job_id in self.jobs_tree.get_children():
            self.jobs_tree.item(job_id, values=values)
        else:
            self.jobs_tree.insert("", "end", iid=job_id, values=values)
        self.current_transfer_var.set(
            f"{job.get('device_label', '')} - {job.get('filename', '')} - {job.get('percent', 0.0):.1f}%"
        )
        self.current_transfer_bar["value"] = float(job.get("percent", 0.0))
        self.current_transfer_note_var.set(
            f"{self._format_bytes(job.get('transferred_bytes', 0))} / "
            f"{self._format_bytes(job.get('total_bytes', 0))} at {self._format_speed(job.get('speed_bps', 0.0))} "
            f"({job.get('state', '')})"
        )

    @staticmethod
    def _format_bytes(size: int | float) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size or 0)
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return "0 B"

    @staticmethod
    def _format_speed(speed_bps: float) -> str:
        if not speed_bps:
            return "-"
        return f"{speed_bps / (1024 * 1024):.2f} MB/s"


def main() -> None:
    app = QuestUpdaterApp()
    app.mainloop()
