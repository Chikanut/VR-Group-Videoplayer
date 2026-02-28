#!/usr/bin/env python3
"""Meta Quest Group Manager — PyQt5 desktop app for managing groups of Quest devices via ADB over WiFi."""

import sys
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QGridLayout,
    QFrame, QLabel, QLineEdit, QTextEdit, QProgressBar, QDialog,
    QDialogButtonBox, QCheckBox, QMenu, QAction, QInputDialog,
    QMessageBox, QSizePolicy, QSplitter,
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
            # Signal parent to refresh
            parent = self.parent()
            while parent and not isinstance(parent, MainWindow):
                parent = parent.parent()
            if parent:
                parent.load_group_devices(self.group_name)


# ---------------------------------------------------------------------------
# Create group dialog with scanning
# ---------------------------------------------------------------------------
class CreateGroupDialog(QDialog):
    """Dialog: enter group name → scan network → pick devices → save."""

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

        # Clear previous results
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
            cb = QCheckBox(f"{dev.name}  |  {dev.ip}  |  {dev.mac}")
            cb.setChecked(True)
            self.device_area.addWidget(cb)
            self._checkboxes.append((cb, dev))

    def _accept(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a group name.")
            return

        # Check duplicates
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
                # Try to resolve new IP by MAC
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

        # --- Center: device tiles ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.group_title = QLabel("Select a group")
        self.group_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        right_layout.addWidget(self.group_title)

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

        # Clear tile grid
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

        # Start polling
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
            # Select the new group
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
            return  # Previous poll still running

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
        worker.finished.connect(lambda: self._cmd_workers.remove(worker))
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

        # Collect online devices
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
        worker.finished.connect(lambda: self._cmd_workers.remove(worker))
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
