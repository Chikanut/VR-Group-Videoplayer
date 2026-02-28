import socket
import sys
from dataclasses import dataclass

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from adb_manager import AdbManager
from scanner import scan_subnet
from storage import Storage


@dataclass
class DeviceStatus:
    online: bool
    battery: int
    ip: str


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)


class ScanWorker(QRunnable):
    def __init__(self, subnet: str, adb: AdbManager):
        super().__init__()
        self.subnet = subnet
        self.adb = adb
        self.signals = WorkerSignals()

    def run(self):
        try:
            devices = scan_subnet(
                self.subnet,
                self.adb,
                progress_callback=lambda done, total: self.signals.progress.emit(done, total),
            )
            self.signals.finished.emit(devices)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class DeviceStatusWorker(QRunnable):
    def __init__(self, adb: AdbManager, device: dict):
        super().__init__()
        self.adb = adb
        self.device = device
        self.signals = WorkerSignals()

    def run(self):
        try:
            mac = self.device["mac"]
            ip = self.device.get("last_known_ip", "")
            online = False
            battery = -1

            if ip and self.adb.connect(ip):
                online = self.adb.is_online(ip)

            if not online:
                resolved = self.adb.resolve_ip_by_mac_arp(mac)
                if resolved and self.adb.connect(resolved):
                    ip = resolved
                    online = self.adb.is_online(ip)

            if online and ip:
                battery = self.adb.get_battery(ip)

            self.signals.finished.emit({"mac": mac, "status": DeviceStatus(online=online, battery=battery, ip=ip)})
        except Exception as exc:
            self.signals.error.emit(str(exc))


class GlobalCommandWorker(QRunnable):
    def __init__(self, adb: AdbManager, ip: str, cmd: str, name: str):
        super().__init__()
        self.adb = adb
        self.ip = ip
        self.cmd = cmd
        self.name = name
        self.signals = WorkerSignals()

    def run(self):
        try:
            output = self.adb.exec_command(self.ip, self.cmd)
            self.signals.finished.emit({"name": self.name, "ip": self.ip, "output": output})
        except Exception as exc:
            self.signals.error.emit(f"{self.name}: {exc}")


class CreateGroupDialog(QDialog):
    def __init__(self, adb: AdbManager, thread_pool: QThreadPool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Group")
        self.adb = adb
        self.thread_pool = thread_pool
        self.found_devices = []

        layout = QVBoxLayout(self)
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Group name")
        self.subnet_input = QLineEdit(self)
        self.subnet_input.setPlaceholderText("Subnet (e.g. 192.168.1.0/24)")
        self.subnet_input.setText(self._default_subnet())
        self.scan_button = QPushButton("Scan", self)
        self.progress = QProgressBar(self)
        self.progress.setValue(0)
        self.device_list = QListWidget(self)

        buttons = QHBoxLayout()
        self.ok_btn = QPushButton("Create", self)
        self.cancel_btn = QPushButton("Cancel", self)
        buttons.addWidget(self.ok_btn)
        buttons.addWidget(self.cancel_btn)

        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.name_input)
        layout.addWidget(QLabel("Subnet"))
        layout.addWidget(self.subnet_input)
        layout.addWidget(self.scan_button)
        layout.addWidget(self.progress)
        layout.addWidget(self.device_list)
        layout.addLayout(buttons)

        self.scan_button.clicked.connect(self.start_scan)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def _default_subnet(self) -> str:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            parts = local_ip.split(".")
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        except Exception:
            return "192.168.1.0/24"

    def start_scan(self):
        subnet = self.subnet_input.text().strip()
        if not subnet:
            QMessageBox.warning(self, "Validation", "Please enter subnet")
            return
        self.scan_button.setEnabled(False)
        self.progress.setValue(0)
        self.device_list.clear()
        worker = ScanWorker(subnet, self.adb)
        worker.signals.progress.connect(self.on_scan_progress)
        worker.signals.finished.connect(self.on_scan_finished)
        worker.signals.error.connect(self.on_scan_error)
        self.thread_pool.start(worker)

    def on_scan_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def on_scan_finished(self, devices: list[dict]):
        self.scan_button.setEnabled(True)
        self.found_devices = devices
        for device in devices:
            item = QListWidgetItem(f"{device['ip']} | {device['mac']} | {device['name']}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, device)
            self.device_list.addItem(item)

    def on_scan_error(self, message: str):
        self.scan_button.setEnabled(True)
        QMessageBox.critical(self, "Scan Error", message)

    def selected_devices(self) -> list[dict]:
        selected = []
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected


class DeviceTile(QWidget):
    run_requested = pyqtSignal(dict, str)
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, device: dict):
        super().__init__()
        self.device = device
        self.status = DeviceStatus(online=False, battery=-1, ip=device.get("last_known_ip", ""))

        self.frame = QWidget(self)
        self.frame_layout = QVBoxLayout(self.frame)

        self.name_label = QLabel(device.get("custom_name") or device["mac"], self)
        self.battery_label = QLabel("🔋 --%", self)
        self.ip_label = QLabel(device.get("last_known_ip", ""), self)
        self.more_btn = QPushButton("⋯", self)
        self.cmd_input = QLineEdit(self)
        self.cmd_input.setPlaceholderText("adb shell command")
        self.run_btn = QPushButton("Run", self)
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)

        top = QHBoxLayout()
        top.addWidget(self.name_label)
        top.addWidget(self.more_btn)

        command_layout = QHBoxLayout()
        command_layout.addWidget(self.cmd_input)
        command_layout.addWidget(self.run_btn)

        self.frame_layout.addLayout(top)
        self.frame_layout.addWidget(self.battery_label)
        self.frame_layout.addWidget(self.ip_label)
        self.frame_layout.addLayout(command_layout)
        self.frame_layout.addWidget(self.output)

        outer = QVBoxLayout(self)
        outer.addWidget(self.frame)

        self.more_btn.clicked.connect(self.show_menu)
        self.run_btn.clicked.connect(self.request_run)
        self.apply_status()

    def show_menu(self):
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Remove from group")
        action = menu.exec_(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))
        if action == rename_action:
            self.rename_requested.emit(self.device["mac"])
        elif action == delete_action:
            self.delete_requested.emit(self.device["mac"])

    def request_run(self):
        cmd = self.cmd_input.text().strip()
        if cmd:
            self.run_requested.emit(self.device, cmd)

    def append_output(self, text: str):
        self.output.append(text)

    def update_status(self, status: DeviceStatus):
        self.status = status
        self.apply_status()

    def apply_status(self):
        self.battery_label.setText(f"🔋 {self.status.battery if self.status.battery >= 0 else '--'}%")
        self.ip_label.setText(self.status.ip or "No IP")
        color = QColor("#d4f7d4") if self.status.online else QColor("#d3d3d3")
        palette = self.frame.palette()
        palette.setColor(QPalette.Window, color)
        self.frame.setAutoFillBackground(True)
        self.frame.setPalette(palette)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meta Quest Group Manager")
        self.resize(1200, 700)

        self.storage = Storage()
        self.adb = AdbManager()
        self.thread_pool = QThreadPool.globalInstance()
        self.current_group: str | None = None
        self.tiles: dict[str, DeviceTile] = {}
        self.global_results = []

        self._build_ui()
        self._load_groups()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_devices)
        self.poll_timer.start(3000)

    def _build_ui(self):
        root = QWidget(self)
        main_layout = QVBoxLayout(root)

        content = QHBoxLayout()

        left_panel = QVBoxLayout()
        self.groups_list = QListWidget(self)
        self.groups_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.add_group_btn = QPushButton("+", self)
        left_panel.addWidget(QLabel("Groups"))
        left_panel.addWidget(self.groups_list)
        left_panel.addWidget(self.add_group_btn)

        self.scroll_content = QWidget(self)
        self.grid = QGridLayout(self.scroll_content)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.scroll_content)

        content.addLayout(left_panel, 1)
        content.addWidget(self.scroll, 4)

        bottom = QHBoxLayout()
        self.global_cmd_input = QLineEdit(self)
        self.global_cmd_input.setPlaceholderText("Global adb shell command")
        self.global_run_btn = QPushButton("Run", self)
        bottom.addWidget(self.global_cmd_input)
        bottom.addWidget(self.global_run_btn)

        main_layout.addLayout(content)
        main_layout.addLayout(bottom)
        self.setCentralWidget(root)

        self.add_group_btn.clicked.connect(self.create_group)
        self.groups_list.itemClicked.connect(self.select_group)
        self.groups_list.customContextMenuRequested.connect(self.group_context_menu)
        self.global_run_btn.clicked.connect(self.run_global_command)

    def _load_groups(self):
        self.groups_list.clear()
        for group in self.storage.list_groups():
            self.groups_list.addItem(group["name"])

    def create_group(self):
        dialog = CreateGroupDialog(self.adb, self.thread_pool, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        name = dialog.name_input.text().strip()
        devices = dialog.selected_devices()
        if not name:
            QMessageBox.warning(self, "Validation", "Group name is required")
            return
        if not devices:
            QMessageBox.warning(self, "Validation", "Select at least one device")
            return
        try:
            self.storage.create_group(name, devices)
        except ValueError as exc:
            QMessageBox.warning(self, "Create group", str(exc))
            return
        self._load_groups()

    def group_context_menu(self, pos):
        item = self.groups_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        action = menu.exec_(self.groups_list.mapToGlobal(pos))
        if action == delete_action:
            self.storage.delete_group(item.text())
            if self.current_group == item.text():
                self.current_group = None
                self.clear_tiles()
            self._load_groups()

    def select_group(self, item: QListWidgetItem):
        self.current_group = item.text()
        group = self.storage.get_group(self.current_group)
        self.render_devices(group["devices"] if group else [])

    def clear_tiles(self):
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.tiles.clear()

    def render_devices(self, devices: list[dict]):
        self.clear_tiles()
        for idx, device in enumerate(devices):
            tile = DeviceTile(device)
            tile.run_requested.connect(self.run_single_command)
            tile.rename_requested.connect(self.rename_device)
            tile.delete_requested.connect(self.remove_device)
            row, col = divmod(idx, 3)
            self.grid.addWidget(tile, row, col)
            self.tiles[device["mac"]] = tile

    def rename_device(self, mac: str):
        if not self.current_group:
            return
        name, ok = QInputDialog.getText(self, "Rename Device", "Custom name")
        if ok and name.strip():
            self.storage.rename_device(self.current_group, mac, name.strip())
            group = self.storage.get_group(self.current_group)
            self.render_devices(group["devices"] if group else [])

    def remove_device(self, mac: str):
        if not self.current_group:
            return
        self.storage.remove_device(self.current_group, mac)
        group = self.storage.get_group(self.current_group)
        self.render_devices(group["devices"] if group else [])

    def run_single_command(self, device: dict, cmd: str):
        ip = device.get("last_known_ip", "")
        if not ip:
            self.tiles[device["mac"]].append_output("No IP known")
            return
        output = self.adb.exec_command(ip, cmd)
        self.tiles[device["mac"]].append_output(output)

    def run_global_command(self):
        if not self.current_group:
            return
        cmd = self.global_cmd_input.text().strip()
        if not cmd:
            return
        group = self.storage.get_group(self.current_group)
        if not group:
            return

        self.global_results = []
        for device in group["devices"]:
            tile = self.tiles.get(device["mac"])
            if not tile or not tile.status.online or not tile.status.ip:
                continue
            worker = GlobalCommandWorker(self.adb, tile.status.ip, cmd, device.get("custom_name") or device["mac"])
            worker.signals.finished.connect(self.collect_global_result)
            worker.signals.error.connect(self.collect_global_error)
            self.thread_pool.start(worker)

    def collect_global_result(self, payload: dict):
        self.global_results.append(f"{payload['name']} ({payload['ip']}):\n{payload['output']}")
        self.show_global_results()

    def collect_global_error(self, message: str):
        self.global_results.append(f"ERROR: {message}")
        self.show_global_results()

    def show_global_results(self):
        if not self.global_results:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Global command results")
        msg.setText("\n\n".join(self.global_results))
        msg.show()

    def poll_devices(self):
        if not self.current_group:
            return
        group = self.storage.get_group(self.current_group)
        if not group:
            return
        for device in group["devices"]:
            worker = DeviceStatusWorker(self.adb, device)
            worker.signals.finished.connect(self.on_status_ready)
            worker.signals.error.connect(self.on_status_error)
            self.thread_pool.start(worker)

    def on_status_ready(self, payload: dict):
        if not self.current_group:
            return
        mac = payload["mac"]
        status: DeviceStatus = payload["status"]
        tile = self.tiles.get(mac)
        if tile:
            tile.update_status(status)
        if status.ip:
            self.storage.update_device_ip(self.current_group, mac, status.ip)

    def on_status_error(self, message: str):
        print(f"Status polling error: {message}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
