#!/usr/bin/env python3
"""Meta Quest Group Manager — PyQt5 desktop app for managing groups of Quest devices via ADB over WiFi."""

import sys
import os
import threading
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QGridLayout,
    QFrame, QLabel, QLineEdit, QTextEdit, QProgressBar, QDialog,
    QDialogButtonBox, QCheckBox, QMenu, QAction, QInputDialog,
    QMessageBox, QSizePolicy, QSplitter, QFileDialog, QComboBox,
    QToolBar, QTreeWidget, QTreeWidgetItem, QHeaderView,
)

import adb_manager
import scanner
import storage

POLL_INTERVAL_MS = 3000


# ---------------------------------------------------------------------------
# Device tile widget
# ---------------------------------------------------------------------------
class DeviceTile(QFrame):
    """A card representing a single device in the group view."""

    command_requested = pyqtSignal(str, str)  # ip, command

    def __init__(self, device: storage.Device, group_name: str, parent=None):
        super().__init__(parent)
        self.device = device
        self.group_name = group_name
        self.is_online = False
        self.battery = -1
        self._expanded = False

        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumSize(220, 140)
        self.setMaximumSize(280, 300)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Top row: name + menu button
        top = QHBoxLayout()
        self.name_label = QLabel(device.custom_name or device.mac)
        self.name_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.name_label.setWordWrap(True)
        top.addWidget(self.name_label, 1)

        self.menu_btn = QPushButton("\u22ef")
        self.menu_btn.setFixedSize(28, 28)
        self.menu_btn.setFlat(True)
        self.menu_btn.setFont(QFont("Segoe UI", 14))
        self.menu_btn.clicked.connect(self._show_menu)
        top.addWidget(self.menu_btn)
        layout.addLayout(top)

        # IP label
        self.ip_label = QLabel(f"IP: {device.last_known_ip}")
        self.ip_label.setStyleSheet("color: #888;")
        layout.addWidget(self.ip_label)

        # Battery row
        self.battery_label = QLabel("Battery: —")
        layout.addWidget(self.battery_label)

        # Status indicator
        self.status_label = QLabel("Offline")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Expandable command area (hidden by default)
        self.cmd_widget = QWidget()
        self.cmd_widget.setVisible(False)
        cmd_layout = QVBoxLayout(self.cmd_widget)
        cmd_layout.setContentsMargins(0, 4, 0, 0)

        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("adb shell command...")
        self.cmd_input.returnPressed.connect(self._run_command)
        cmd_row.addWidget(self.cmd_input)

        self.cmd_run_btn = QPushButton("Run")
        self.cmd_run_btn.setFixedWidth(50)
        self.cmd_run_btn.clicked.connect(self._run_command)
        cmd_row.addWidget(self.cmd_run_btn)
        cmd_layout.addLayout(cmd_row)

        self.cmd_output = QTextEdit()
        self.cmd_output.setReadOnly(True)
        self.cmd_output.setMaximumHeight(80)
        self.cmd_output.setStyleSheet("background: #1e1e1e; color: #ddd; font-family: monospace; font-size: 10px;")
        cmd_layout.addWidget(self.cmd_output)

        layout.addWidget(self.cmd_widget)
        layout.addStretch()

        self._apply_style(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self.cmd_widget.setVisible(self._expanded)
        super().mousePressEvent(event)

    def _run_command(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        self.cmd_output.setPlainText("Running...")
        self.command_requested.emit(self.device.last_known_ip, cmd)

    def set_command_result(self, result: str):
        self.cmd_output.setPlainText(result)

    def update_status(self, online: bool, battery: int):
        self.is_online = online
        self.battery = battery
        self._apply_style(online)

        if online:
            self.status_label.setText("Online")
            bat_text = f"Battery: {battery}%" if battery >= 0 else "Battery: —"
            self.battery_label.setText(bat_text)
        else:
            self.status_label.setText("Offline")
            self.battery_label.setText("Battery: —")

    def update_ip(self, new_ip: str):
        self.device.last_known_ip = new_ip
        self.ip_label.setText(f"IP: {new_ip}")

    def _apply_style(self, online: bool):
        if online:
            self.setStyleSheet("""
                DeviceTile {
                    background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                DeviceTile {
                    background: #e0e0e0; border: 1px solid #bdbdbd; border-radius: 8px;
                    color: #888;
                }
            """)

    def _show_menu(self):
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        remove_action = menu.addAction("Remove from group")
        action = menu.exec_(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))
        if action == rename_action:
            self._rename()
        elif action == remove_action:
            self._remove()

    def _rename(self):
        new_name, ok = QInputDialog.getText(self, "Rename device", "New name:", text=self.device.custom_name)
        if ok and new_name.strip():
            storage.rename_device(self.group_name, self.device.mac, new_name.strip())
            self.device.custom_name = new_name.strip()
            self.name_label.setText(new_name.strip())

    def _remove(self):
        reply = QMessageBox.question(
            self, "Remove device",
            f"Remove '{self.device.custom_name}' from group '{self.group_name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            storage.remove_device_from_group(self.group_name, self.device.mac)
            parent = self.parent()
            while parent and not isinstance(parent, MainWindow):
                parent = parent.parent()
            if parent:
                parent.load_group_devices(self.group_name)


# ---------------------------------------------------------------------------
# Create group dialog with scanning
# ---------------------------------------------------------------------------
class CreateGroupDialog(QDialog):
    """Dialog: enter group name -> scan network -> pick devices -> save."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Group")
        self.setMinimumSize(500, 450)
        self.found_devices: list[scanner.FoundDevice] = []
        self.selected_devices: list[scanner.FoundDevice] = []

        layout = QVBoxLayout(self)

        # Group name
        layout.addWidget(QLabel("Group name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Classroom A")
        layout.addWidget(self.name_input)

        # Subnet override
        subnet_row = QHBoxLayout()
        subnet_row.addWidget(QLabel("Subnet:"))
        self.subnet_input = QLineEdit()
        self.subnet_input.setPlaceholderText(scanner.get_local_subnet())
        self.subnet_input.setText(scanner.get_local_subnet())
        subnet_row.addWidget(self.subnet_input)
        layout.addLayout(subnet_row)

        # Scan button + progress
        self.scan_btn = QPushButton("Scan Network")
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Device checkboxes area
        self.device_area = QVBoxLayout()
        self.device_container = QWidget()
        self.device_container.setLayout(self.device_area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.device_container)
        layout.addWidget(scroll, 1)

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(self.buttons)

        self._scan_worker = None
        self._checkboxes: list[tuple[QCheckBox, scanner.FoundDevice]] = []

    def _start_scan(self):
        self.scan_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        for cb, _ in self._checkboxes:
            cb.setParent(None)
        self._checkboxes.clear()

        subnet = self.subnet_input.text().strip()
        self._scan_worker = scanner.ScanWorker(subnet, parent=self)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished_signal.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_progress(self, scanned: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(scanned)

    def _on_scan_done(self, devices: list):
        self.found_devices = devices
        self.scan_btn.setEnabled(True)
        self.progress.setVisible(False)

        if not devices:
            lbl = QLabel("No devices found. Make sure ADB over TCP is enabled on the devices.")
            self.device_area.addWidget(lbl)
            return

        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        for dev in devices:
            cb = QCheckBox(f"{dev.name}  |  {dev.ip}")
            cb.setChecked(True)
            self.device_area.addWidget(cb)
            self._checkboxes.append((cb, dev))

    def _accept(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a group name.")
            return

        if storage.get_group(name):
            QMessageBox.warning(self, "Error", f"Group '{name}' already exists.")
            return

        self.selected_devices = [dev for cb, dev in self._checkboxes if cb.isChecked()]
        if not self.selected_devices:
            QMessageBox.warning(self, "Error", "Select at least one device.")
            return

        self.accept()


# ---------------------------------------------------------------------------
# Command execution workers
# ---------------------------------------------------------------------------
class SingleCommandWorker(QThread):
    """Run a single ADB command on one device."""
    result_ready = pyqtSignal(str, str)  # ip, result

    def __init__(self, ip: str, cmd: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.cmd = cmd

    def run(self):
        out = adb_manager.exec_command(self.ip, self.cmd)
        self.result_ready.emit(self.ip, out)


class GlobalCommandWorker(QThread):
    """Run a command on all online devices in parallel."""
    result_ready = pyqtSignal(str, str)  # ip, result
    all_done = pyqtSignal()

    def __init__(self, devices: list[storage.Device], cmd: str, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.cmd = cmd

    def run(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {
                pool.submit(adb_manager.exec_command, d.last_known_ip, self.cmd): d
                for d in self.devices
            }
            for future in as_completed(futures):
                dev = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = f"Error: {e}"
                self.result_ready.emit(dev.last_known_ip, result)
        self.all_done.emit()


# ---------------------------------------------------------------------------
# Transfer worker — handles push/pull/install with progress
# ---------------------------------------------------------------------------
class TransferWorker(QThread):
    """Runs a file transfer (push/pull/install) on one device with progress."""
    progress_update = pyqtSignal(str, int)    # ip, percent
    transfer_done = pyqtSignal(str, bool, str)  # ip, success, message

    def __init__(self, ip: str, operation: str, **kwargs):
        super().__init__()
        self.ip = ip
        self.operation = operation
        self.kwargs = kwargs
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        cb = lambda pct: self.progress_update.emit(self.ip, pct)
        try:
            if self.operation == "push":
                ok, msg = adb_manager.push(
                    self.ip, self.kwargs["local_path"], self.kwargs["remote_path"],
                    progress_callback=cb, cancel_event=self._cancel)
            elif self.operation == "pull":
                ok, msg = adb_manager.pull(
                    self.ip, self.kwargs["remote_path"], self.kwargs["local_path"],
                    progress_callback=cb, cancel_event=self._cancel)
            elif self.operation == "install":
                ok, msg = adb_manager.install(
                    self.ip, self.kwargs["apk_path"],
                    progress_callback=cb, cancel_event=self._cancel)
            else:
                ok, msg = False, f"Unknown operation: {self.operation}"
        except Exception as e:
            ok, msg = False, str(e)
        self.transfer_done.emit(self.ip, ok, msg)


class MultiTransferWorker(QThread):
    """Runs transfer on multiple devices sequentially, reporting per-device progress."""
    device_progress = pyqtSignal(str, int)       # ip, percent
    device_done = pyqtSignal(str, bool, str)     # ip, success, message
    all_done = pyqtSignal()

    def __init__(self, devices: list[storage.Device], operation: str, **kwargs):
        super().__init__()
        self.devices = devices
        self.operation = operation
        self.kwargs = kwargs
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        for dev in self.devices:
            if self._cancel.is_set():
                break
            ip = dev.last_known_ip
            cb = lambda pct, _ip=ip: self.device_progress.emit(_ip, pct)
            try:
                if self.operation == "push":
                    ok, msg = adb_manager.push(
                        ip, self.kwargs["local_path"], self.kwargs["remote_path"],
                        progress_callback=cb, cancel_event=self._cancel)
                elif self.operation == "pull":
                    ok, msg = adb_manager.pull(
                        ip, self.kwargs["remote_path"], self.kwargs["local_path"],
                        progress_callback=cb, cancel_event=self._cancel)
                elif self.operation == "install":
                    ok, msg = adb_manager.install(
                        ip, self.kwargs["apk_path"],
                        progress_callback=cb, cancel_event=self._cancel)
                else:
                    ok, msg = False, f"Unknown operation: {self.operation}"
            except Exception as e:
                ok, msg = False, str(e)
            self.device_done.emit(ip, ok, msg)
        self.all_done.emit()


# ---------------------------------------------------------------------------
# Polling worker
# ---------------------------------------------------------------------------
class PollWorker(QThread):
    """Polls status for all devices in the current group."""
    device_status = pyqtSignal(str, bool, int)  # mac, online, battery
    device_ip_changed = pyqtSignal(str, str)    # mac, new_ip

    def __init__(self, group_name: str, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        group = storage.get_group(self.group_name)
        if not group:
            return
        for dev in group.devices:
            if not self._running:
                return
            ip = dev.last_known_ip
            online = adb_manager.is_online(ip)

            if not online:
                new_ip = scanner.resolve_ip_by_mac(dev.mac)
                if new_ip and new_ip != ip:
                    adb_manager.connect(new_ip)
                    if adb_manager.is_online(new_ip):
                        storage.update_device_ip(self.group_name, dev.mac, new_ip)
                        self.device_ip_changed.emit(dev.mac, new_ip)
                        ip = new_ip
                        online = True

            battery = adb_manager.get_battery(ip) if online else -1
            self.device_status.emit(dev.mac, online, battery)


# ---------------------------------------------------------------------------
# Global command results dialog
# ---------------------------------------------------------------------------
class CommandResultsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Results")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("background: #1e1e1e; color: #ddd; font-family: monospace;")
        layout.addWidget(self.text)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def append_result(self, ip: str, result: str):
        self.text.append(f"--- {ip} ---\n{result}\n")


# ---------------------------------------------------------------------------
# Transfer progress dialog
# ---------------------------------------------------------------------------
class TransferProgressDialog(QDialog):
    """Shows progress for file transfers across one or multiple devices."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 300)
        self.setModal(False)

        layout = QVBoxLayout(self)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("background: #1e1e1e; color: #ddd; font-family: monospace; font-size: 11px;")
        layout.addWidget(self.log, 1)

        self._progress_bars: dict[str, QProgressBar] = {}
        self._progress_layout = QVBoxLayout()
        layout.addLayout(self._progress_layout)

        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

        self.close_btn.clicked.connect(self.accept)
        self._worker = None

    def set_worker(self, worker):
        self._worker = worker
        self.cancel_btn.clicked.connect(worker.cancel)

    def add_device_bar(self, ip: str):
        bar = QProgressBar()
        bar.setFormat(f"{ip}: %p%")
        bar.setValue(0)
        self._progress_layout.addWidget(bar)
        self._progress_bars[ip] = bar

    def update_progress(self, ip: str, percent: int):
        bar = self._progress_bars.get(ip)
        if bar:
            bar.setValue(percent)

    def on_device_done(self, ip: str, success: bool, message: str):
        status = "OK" if success else "FAIL"
        self.log.append(f"[{ip}] {status}: {message}")
        bar = self._progress_bars.get(ip)
        if bar:
            bar.setValue(100)

    def on_all_done(self):
        self.log.append("\n=== All transfers complete ===")
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# File browser dialog
# ---------------------------------------------------------------------------
class FileBrowserDialog(QDialog):
    """Browse files and folders on a device."""

    def __init__(self, ip: str, device_name: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.setWindowTitle(f"File Browser — {device_name} ({ip})")
        self.setMinimumSize(700, 500)
        self.current_path = "/sdcard"

        layout = QVBoxLayout(self)

        # Navigation bar
        nav = QHBoxLayout()
        self.path_input = QLineEdit(self.current_path)
        self.path_input.returnPressed.connect(self._navigate)
        nav.addWidget(self.path_input, 1)

        go_btn = QPushButton("Go")
        go_btn.clicked.connect(self._navigate)
        nav.addWidget(go_btn)

        up_btn = QPushButton("Up")
        up_btn.clicked.connect(self._go_up)
        nav.addWidget(up_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        nav.addWidget(refresh_btn)
        layout.addLayout(nav)

        # File tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type", "Size"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 100)
        self.tree.itemDoubleClicked.connect(self._on_item_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.tree, 1)

        # Action buttons
        actions = QHBoxLayout()

        mkdir_btn = QPushButton("New Folder")
        mkdir_btn.clicked.connect(self._mkdir)
        actions.addWidget(mkdir_btn)

        push_btn = QPushButton("Upload File")
        push_btn.clicked.connect(self._push_file)
        actions.addWidget(push_btn)

        pull_btn = QPushButton("Download File")
        pull_btn.clicked.connect(self._pull_file)
        actions.addWidget(pull_btn)

        actions.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

        self._refresh()

    def _navigate(self):
        path = self.path_input.text().strip()
        if path:
            self.current_path = path
            self._refresh()

    def _go_up(self):
        parent = os.path.dirname(self.current_path.rstrip("/"))
        if parent:
            self.current_path = parent
            self.path_input.setText(self.current_path)
            self._refresh()

    def _refresh(self):
        self.tree.clear()
        self.path_input.setText(self.current_path)

        worker = SingleCommandWorker(self.ip, f"ls -la {self.current_path}", parent=self)
        worker.result_ready.connect(self._on_ls_result)
        worker.start()
        self._ls_worker = worker

    def _on_ls_result(self, ip: str, result: str):
        self.tree.clear()
        for line in result.splitlines():
            line = line.strip()
            if not line or line.startswith("total"):
                continue
            parts = line.split(None, 7)
            if len(parts) < 7:
                continue
            perms = parts[0]
            name = parts[-1] if len(parts) >= 8 else parts[-1]
            if name in (".", ".."):
                continue
            entry_type = "dir" if perms.startswith("d") else "file"
            try:
                size = parts[4]
            except (IndexError):
                size = ""
            item = QTreeWidgetItem([name, entry_type, size if entry_type == "file" else ""])
            if entry_type == "dir":
                item.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
            self.tree.addTopLevelItem(item)

    def _on_item_double_click(self, item: QTreeWidgetItem, column: int):
        if item.text(1) == "dir":
            name = item.text(0)
            self.current_path = f"{self.current_path.rstrip('/')}/{name}"
            self.path_input.setText(self.current_path)
            self._refresh()

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        if item.text(1) == "file":
            dl_action = menu.addAction("Download")
            del_action = menu.addAction("Delete")
            action = menu.exec_(self.tree.viewport().mapToGlobal(pos))
            if action == dl_action:
                self._pull_selected(item)
            elif action == del_action:
                self._delete_item(item)
        else:
            enter_action = menu.addAction("Open")
            del_action = menu.addAction("Delete")
            action = menu.exec_(self.tree.viewport().mapToGlobal(pos))
            if action == enter_action:
                self._on_item_double_click(item, 0)
            elif action == del_action:
                self._delete_item(item)

    def _mkdir(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            remote = f"{self.current_path.rstrip('/')}/{name.strip()}"
            adb_manager.mkdir(self.ip, remote)
            self._refresh()

    def _push_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        if not paths:
            return
        self._do_push(paths)

    def _do_push(self, local_paths: list[str]):
        main_win = self._find_main_window()
        if not main_win:
            return
        for local_path in local_paths:
            remote = f"{self.current_path.rstrip('/')}/{os.path.basename(local_path)}"
            main_win.start_transfer("push", [self.ip],
                                    local_path=local_path, remote_path=remote)
        QTimer.singleShot(1000, self._refresh)

    def _pull_file(self):
        item = self.tree.currentItem()
        if not item or item.text(1) != "file":
            QMessageBox.information(self, "Info", "Select a file to download.")
            return
        self._pull_selected(item)

    def _pull_selected(self, item: QTreeWidgetItem):
        name = item.text(0)
        remote = f"{self.current_path.rstrip('/')}/{name}"
        local_dir = QFileDialog.getExistingDirectory(self, "Save to folder")
        if not local_dir:
            return
        local_path = os.path.join(local_dir, name)
        main_win = self._find_main_window()
        if main_win:
            main_win.start_transfer("pull", [self.ip],
                                    remote_path=remote, local_path=local_path)

    def _delete_item(self, item: QTreeWidgetItem):
        name = item.text(0)
        reply = QMessageBox.question(
            self, "Delete", f"Delete '{name}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            remote = f"{self.current_path.rstrip('/')}/{name}"
            flag = "-rf" if item.text(1) == "dir" else ""
            adb_manager.exec_command(self.ip, f"rm {flag} {remote}")
            self._refresh()

    def _find_main_window(self):
        parent = self.parent()
        while parent and not isinstance(parent, MainWindow):
            parent = parent.parent()
        return parent


# ---------------------------------------------------------------------------
# Package list dialog
# ---------------------------------------------------------------------------
class PackageListDialog(QDialog):
    """View/uninstall packages on a device."""

    def __init__(self, ip: str, device_name: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.setWindowTitle(f"Installed Apps — {device_name} ({ip})")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # Filter
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Type to filter packages...")
        self.filter_input.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_input)
        layout.addLayout(filter_row)

        self.pkg_list = QListWidget()
        layout.addWidget(self.pkg_list, 1)

        btn_row = QHBoxLayout()
        uninstall_btn = QPushButton("Uninstall Selected")
        uninstall_btn.clicked.connect(self._uninstall)
        btn_row.addWidget(uninstall_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_packages)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._all_packages: list[str] = []
        self._load_packages()

    def _load_packages(self):
        self.pkg_list.clear()
        self.pkg_list.addItem("Loading...")

        worker = SingleCommandWorker(self.ip, "pm list packages", parent=self)
        worker.result_ready.connect(self._on_packages_loaded)
        worker.start()
        self._worker = worker

    def _on_packages_loaded(self, ip: str, result: str):
        self.pkg_list.clear()
        self._all_packages = []
        for line in result.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                self._all_packages.append(line[8:])
        self._all_packages.sort()
        for pkg in self._all_packages:
            self.pkg_list.addItem(pkg)

    def _apply_filter(self, text: str):
        text = text.lower()
        self.pkg_list.clear()
        for pkg in self._all_packages:
            if text in pkg.lower():
                self.pkg_list.addItem(pkg)

    def _uninstall(self):
        item = self.pkg_list.currentItem()
        if not item:
            return
        pkg = item.text()
        reply = QMessageBox.question(
            self, "Uninstall", f"Uninstall '{pkg}'?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            ok, msg = adb_manager.uninstall(self.ip, pkg)
            if ok:
                QMessageBox.information(self, "Success", f"Uninstalled {pkg}")
                self._load_packages()
            else:
                QMessageBox.warning(self, "Error", f"Failed to uninstall: {msg}")


# ---------------------------------------------------------------------------
# Video launcher dialog
# ---------------------------------------------------------------------------
class VideoLauncherDialog(QDialog):
    """Browse video files on device and launch them."""

    def __init__(self, ip: str, device_name: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.setWindowTitle(f"Video Player — {device_name} ({ip})")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select video file to play:"))

        # Path selector
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Scan folder:"))
        self.folder_input = QLineEdit("/sdcard/Movies")
        path_row.addWidget(self.folder_input, 1)
        scan_btn = QPushButton("Scan")
        scan_btn.clicked.connect(self._scan_videos)
        path_row.addWidget(scan_btn)
        layout.addLayout(path_row)

        self.video_list = QListWidget()
        layout.addWidget(self.video_list, 1)

        btn_row = QHBoxLayout()
        play_btn = QPushButton("Play Selected")
        play_btn.clicked.connect(self._play)
        btn_row.addWidget(play_btn)

        play_all_btn = QPushButton("Play on All Devices")
        play_all_btn.clicked.connect(self._play_all)
        btn_row.addWidget(play_all_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._videos: list[str] = []
        self._scan_videos()

    def _scan_videos(self):
        self.video_list.clear()
        self.video_list.addItem("Scanning...")
        folder = self.folder_input.text().strip()
        cmd = f"find {folder} -type f \\( -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' -o -name '*.mov' -o -name '*.webm' \\) 2>/dev/null"
        worker = SingleCommandWorker(self.ip, cmd, parent=self)
        worker.result_ready.connect(self._on_scan_result)
        worker.start()
        self._scan_worker = worker

    def _on_scan_result(self, ip: str, result: str):
        self.video_list.clear()
        self._videos = []
        for line in result.splitlines():
            line = line.strip()
            if line:
                self._videos.append(line)
                self.video_list.addItem(os.path.basename(line))
        if not self._videos:
            self.video_list.addItem("(no videos found)")

    def _play(self):
        idx = self.video_list.currentRow()
        if idx < 0 or idx >= len(self._videos):
            return
        video_path = self._videos[idx]
        ok, msg = adb_manager.launch_video(self.ip, video_path)
        if not ok:
            QMessageBox.warning(self, "Error", f"Failed to launch video: {msg}")

    def _play_all(self):
        idx = self.video_list.currentRow()
        if idx < 0 or idx >= len(self._videos):
            QMessageBox.information(self, "Info", "Select a video first.")
            return
        video_path = self._videos[idx]
        main_win = self._find_main_window()
        if main_win:
            main_win.launch_video_all(video_path)

    def _find_main_window(self):
        parent = self.parent()
        while parent and not isinstance(parent, MainWindow):
            parent = parent.parent()
        return parent


# ---------------------------------------------------------------------------
# Device action selector dialog
# ---------------------------------------------------------------------------
class DeviceActionDialog(QDialog):
    """Choose target: single device or all online devices."""

    def __init__(self, action_name: str, online_devices: list[storage.Device], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{action_name} — Select Target")
        self.setMinimumWidth(350)
        self.selected_devices: list[storage.Device] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Apply '{action_name}' to:"))

        self.combo = QComboBox()
        self.combo.addItem("All online devices")
        for dev in online_devices:
            label = f"{dev.custom_name} ({dev.last_known_ip})"
            self.combo.addItem(label)
        layout.addWidget(self.combo)

        self._online_devices = online_devices

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        idx = self.combo.currentIndex()
        if idx == 0:
            self.selected_devices = list(self._online_devices)
        else:
            self.selected_devices = [self._online_devices[idx - 1]]
        self.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quest Group Manager")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        self.current_group: str | None = None
        self.tiles: dict[str, DeviceTile] = {}  # mac -> tile
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_devices)
        self._poll_worker: PollWorker | None = None
        self._cmd_workers: list[QThread] = []

        self._build_ui()
        self._refresh_group_list()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # --- Left panel: groups ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("Groups")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        left_layout.addWidget(lbl)

        self.group_list = QListWidget()
        self.group_list.currentItemChanged.connect(self._on_group_selected)
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(self._group_context_menu)
        left_layout.addWidget(self.group_list)

        self.add_group_btn = QPushButton("+ New Group")
        self.add_group_btn.clicked.connect(self._create_group)
        left_layout.addWidget(self.add_group_btn)

        left.setMaximumWidth(250)
        splitter.addWidget(left)

        # --- Right: device tiles + action toolbar ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.group_title = QLabel("Select a group")
        self.group_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        right_layout.addWidget(self.group_title)

        # Action toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_push = QPushButton("Upload File")
        self.btn_push.setToolTip("Push files to devices")
        self.btn_push.clicked.connect(self._action_push)
        toolbar.addWidget(self.btn_push)

        self.btn_install = QPushButton("Install APK")
        self.btn_install.setToolTip("Install APK on devices")
        self.btn_install.clicked.connect(self._action_install)
        toolbar.addWidget(self.btn_install)

        self.btn_browse = QPushButton("File Browser")
        self.btn_browse.setToolTip("Browse files on a device")
        self.btn_browse.clicked.connect(self._action_browse)
        toolbar.addWidget(self.btn_browse)

        self.btn_video = QPushButton("Play Video")
        self.btn_video.setToolTip("Launch video on devices")
        self.btn_video.clicked.connect(self._action_video)
        toolbar.addWidget(self.btn_video)

        self.btn_packages = QPushButton("Installed Apps")
        self.btn_packages.setToolTip("View installed apps on a device")
        self.btn_packages.clicked.connect(self._action_packages)
        toolbar.addWidget(self.btn_packages)

        self.btn_mkdir = QPushButton("Create Folder")
        self.btn_mkdir.setToolTip("Create a folder on devices")
        self.btn_mkdir.clicked.connect(self._action_mkdir)
        toolbar.addWidget(self.btn_mkdir)

        toolbar.addStretch()
        right_layout.addLayout(toolbar)

        # Device tiles scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.tile_container = QWidget()
        self.tile_layout = QGridLayout(self.tile_container)
        self.tile_layout.setSpacing(12)
        self.tile_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.tile_container)
        right_layout.addWidget(self.scroll, 1)

        splitter.addWidget(right)
        splitter.setSizes([220, 680])

        main_layout.addWidget(splitter, 1)

        # --- Bottom: global command bar ---
        bottom = QHBoxLayout()
        self.global_cmd = QLineEdit()
        self.global_cmd.setPlaceholderText("Run ADB command on all online devices in group...")
        self.global_cmd.returnPressed.connect(self._run_global_command)
        bottom.addWidget(self.global_cmd)

        self.global_run_btn = QPushButton("Run All")
        self.global_run_btn.setFixedWidth(80)
        self.global_run_btn.clicked.connect(self._run_global_command)
        bottom.addWidget(self.global_run_btn)

        main_layout.addLayout(bottom)

    # --- Helper: get online devices ---
    def _get_online_devices(self) -> list[storage.Device]:
        if not self.current_group:
            return []
        group = storage.get_group(self.current_group)
        if not group:
            return []
        return [d for d in group.devices
                if self.tiles.get(d.mac) and self.tiles[d.mac].is_online]

    def _pick_target(self, action_name: str) -> list[storage.Device] | None:
        """Show device selector. Returns list of devices or None if cancelled."""
        online = self._get_online_devices()
        if not online:
            QMessageBox.information(self, "No devices", "No online devices in this group.")
            return None
        if len(online) == 1:
            return online
        dlg = DeviceActionDialog(action_name, online, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.selected_devices
        return None

    # --- Actions ---
    def _action_push(self):
        if not self.current_group:
            return
        devices = self._pick_target("Upload File")
        if not devices:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        if not paths:
            return
        remote_dir, ok = QInputDialog.getText(
            self, "Remote path", "Upload to folder on device:",
            text="/sdcard/Movies/")
        if not ok or not remote_dir.strip():
            return
        for local_path in paths:
            remote = f"{remote_dir.rstrip('/')}/{os.path.basename(local_path)}"
            ips = [d.last_known_ip for d in devices]
            self.start_transfer("push", ips,
                                local_path=local_path, remote_path=remote)

    def _action_install(self):
        if not self.current_group:
            return
        devices = self._pick_target("Install APK")
        if not devices:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select APK", "", "APK Files (*.apk)")
        if not path:
            return
        ips = [d.last_known_ip for d in devices]
        self.start_transfer("install", ips, apk_path=path)

    def _action_browse(self):
        if not self.current_group:
            return
        online = self._get_online_devices()
        if not online:
            QMessageBox.information(self, "No devices", "No online devices.")
            return
        if len(online) == 1:
            dev = online[0]
        else:
            dlg = DeviceActionDialog("File Browser", online, parent=self)
            if dlg.exec_() != QDialog.Accepted or not dlg.selected_devices:
                return
            dev = dlg.selected_devices[0]
        fb = FileBrowserDialog(dev.last_known_ip, dev.custom_name, parent=self)
        fb.exec_()

    def _action_video(self):
        if not self.current_group:
            return
        online = self._get_online_devices()
        if not online:
            QMessageBox.information(self, "No devices", "No online devices.")
            return
        dev = online[0]
        dlg = VideoLauncherDialog(dev.last_known_ip, dev.custom_name, parent=self)
        dlg.exec_()

    def _action_packages(self):
        if not self.current_group:
            return
        online = self._get_online_devices()
        if not online:
            QMessageBox.information(self, "No devices", "No online devices.")
            return
        if len(online) == 1:
            dev = online[0]
        else:
            dlg = DeviceActionDialog("Installed Apps", online, parent=self)
            if dlg.exec_() != QDialog.Accepted or not dlg.selected_devices:
                return
            dev = dlg.selected_devices[0]
        pkg_dlg = PackageListDialog(dev.last_known_ip, dev.custom_name, parent=self)
        pkg_dlg.exec_()

    def _action_mkdir(self):
        if not self.current_group:
            return
        devices = self._pick_target("Create Folder")
        if not devices:
            return
        folder, ok = QInputDialog.getText(
            self, "Create Folder", "Full path for new folder:",
            text="/sdcard/Movies/NewFolder")
        if not ok or not folder.strip():
            return
        results = []
        for dev in devices:
            ok, msg = adb_manager.mkdir(dev.last_known_ip, folder.strip())
            status = "OK" if ok else f"FAIL: {msg}"
            results.append(f"[{dev.last_known_ip}] {status}")
        QMessageBox.information(self, "Create Folder", "\n".join(results))

    # --- Transfer execution ---
    def start_transfer(self, operation: str, ips: list[str], **kwargs):
        """Start a file transfer operation on given IPs with a progress dialog."""
        title_map = {"push": "Uploading", "pull": "Downloading", "install": "Installing"}
        title = title_map.get(operation, operation)

        dlg = TransferProgressDialog(title, parent=self)
        dlg.show()

        group = storage.get_group(self.current_group) if self.current_group else None
        devices = []
        for ip in ips:
            if group:
                for d in group.devices:
                    if d.last_known_ip == ip:
                        devices.append(d)
                        break
                else:
                    devices.append(storage.Device(mac=ip, custom_name=ip, last_known_ip=ip))
            else:
                devices.append(storage.Device(mac=ip, custom_name=ip, last_known_ip=ip))

        for dev in devices:
            dlg.add_device_bar(dev.last_known_ip)

        worker = MultiTransferWorker(devices, operation, **kwargs)
        dlg.set_worker(worker)
        worker.device_progress.connect(dlg.update_progress)
        worker.device_done.connect(dlg.on_device_done)
        worker.all_done.connect(dlg.on_all_done)
        worker.finished.connect(lambda: self._cmd_workers.remove(worker) if worker in self._cmd_workers else None)
        self._cmd_workers.append(worker)
        worker.start()

    def launch_video_all(self, video_path: str):
        """Launch video on all online devices."""
        online = self._get_online_devices()
        if not online:
            return
        results_dlg = CommandResultsDialog(self)
        results_dlg.setWindowTitle("Video Launch Results")
        results_dlg.show()
        for dev in online:
            ok, msg = adb_manager.launch_video(dev.last_known_ip, video_path)
            status = "OK" if ok else "FAIL"
            results_dlg.append_result(dev.last_known_ip, f"{status}: {msg}")

    # --- Group management ---
    def _refresh_group_list(self):
        self.group_list.clear()
        groups = storage.load_groups()
        for g in groups:
            self.group_list.addItem(g.name)

    def _on_group_selected(self, current: QListWidgetItem, _previous):
        if current is None:
            return
        name = current.text()
        self.load_group_devices(name)

    def load_group_devices(self, group_name: str):
        self.current_group = group_name
        self.group_title.setText(group_name)
        self.tiles.clear()

        while self.tile_layout.count():
            item = self.tile_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        group = storage.get_group(group_name)
        if not group:
            return

        cols = 3
        for i, dev in enumerate(group.devices):
            tile = DeviceTile(dev, group_name)
            tile.command_requested.connect(self._run_single_command)
            self.tile_layout.addWidget(tile, i // cols, i % cols)
            self.tiles[dev.mac] = tile

        self._start_polling()

    def _create_group(self):
        dlg = CreateGroupDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            devices = [
                storage.Device(mac=d.mac, custom_name=d.name, last_known_ip=d.ip)
                for d in dlg.selected_devices
            ]
            storage.create_group(dlg.name_input.text().strip(), devices)
            self._refresh_group_list()
            for i in range(self.group_list.count()):
                if self.group_list.item(i).text() == dlg.name_input.text().strip():
                    self.group_list.setCurrentRow(i)
                    break

    def _group_context_menu(self, pos):
        item = self.group_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec_(self.group_list.mapToGlobal(pos))
        if action == rename_action:
            self._rename_group(item.text())
        elif action == delete_action:
            self._delete_group(item.text())

    def _rename_group(self, old_name: str):
        new_name, ok = QInputDialog.getText(self, "Rename group", "New name:", text=old_name)
        if ok and new_name.strip():
            storage.rename_group(old_name, new_name.strip())
            self._refresh_group_list()

    def _delete_group(self, name: str):
        reply = QMessageBox.question(
            self, "Delete group",
            f"Delete group '{name}' and all its device assignments?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            storage.delete_group(name)
            self._refresh_group_list()
            if self.current_group == name:
                self.current_group = None
                self.group_title.setText("Select a group")
                while self.tile_layout.count():
                    item = self.tile_layout.takeAt(0)
                    w = item.widget()
                    if w:
                        w.deleteLater()
                self.tiles.clear()

    # --- Polling ---
    def _start_polling(self):
        self._stop_polling()
        self._poll_timer.start(POLL_INTERVAL_MS)
        self._poll_devices()

    def _stop_polling(self):
        self._poll_timer.stop()
        if self._poll_worker and self._poll_worker.isRunning():
            self._poll_worker.stop()
            self._poll_worker.wait(2000)

    def _poll_devices(self):
        if not self.current_group:
            return
        if self._poll_worker and self._poll_worker.isRunning():
            return

        self._poll_worker = PollWorker(self.current_group, parent=self)
        self._poll_worker.device_status.connect(self._on_device_status)
        self._poll_worker.device_ip_changed.connect(self._on_device_ip_changed)
        self._poll_worker.start()

    def _on_device_status(self, mac: str, online: bool, battery: int):
        tile = self.tiles.get(mac)
        if tile:
            tile.update_status(online, battery)

    def _on_device_ip_changed(self, mac: str, new_ip: str):
        tile = self.tiles.get(mac)
        if tile:
            tile.update_ip(new_ip)

    # --- Commands ---
    def _run_single_command(self, ip: str, cmd: str):
        worker = SingleCommandWorker(ip, cmd, parent=self)
        worker.result_ready.connect(self._on_single_cmd_result)
        worker.finished.connect(lambda: self._cmd_workers.remove(worker) if worker in self._cmd_workers else None)
        self._cmd_workers.append(worker)
        worker.start()

    def _on_single_cmd_result(self, ip: str, result: str):
        for tile in self.tiles.values():
            if tile.device.last_known_ip == ip:
                tile.set_command_result(result)
                break

    def _run_global_command(self):
        cmd = self.global_cmd.text().strip()
        if not cmd or not self.current_group:
            return

        group = storage.get_group(self.current_group)
        if not group or not group.devices:
            return

        online_devices = [d for d in group.devices if self.tiles.get(d.mac) and self.tiles[d.mac].is_online]
        if not online_devices:
            QMessageBox.information(self, "No devices", "No online devices in this group.")
            return

        dlg = CommandResultsDialog(self)
        dlg.setWindowTitle(f"Results: {cmd}")
        dlg.show()

        worker = GlobalCommandWorker(online_devices, cmd, parent=self)
        worker.result_ready.connect(dlg.append_result)
        worker.all_done.connect(lambda: dlg.text.append("\n=== Done ==="))
        worker.finished.connect(lambda: self._cmd_workers.remove(worker) if worker in self._cmd_workers else None)
        self._cmd_workers.append(worker)
        worker.start()

    def closeEvent(self, event):
        self._stop_polling()
        for w in self._cmd_workers:
            w.wait(1000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
