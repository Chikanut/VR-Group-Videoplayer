"""JSON-based storage for device groups."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groups.json")


@dataclass
class Device:
    mac: str
    custom_name: str
    last_known_ip: str


@dataclass
class Group:
    name: str
    devices: list[Device] = field(default_factory=list)


def _load_raw() -> list[dict]:
    if not os.path.exists(STORAGE_FILE):
        return []
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_raw(data: list[dict]):
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_groups() -> list[Group]:
    raw = _load_raw()
    groups = []
    for g in raw:
        devices = [Device(**d) for d in g.get("devices", [])]
        groups.append(Group(name=g["name"], devices=devices))
    return groups


def save_groups(groups: list[Group]):
    data = [asdict(g) for g in groups]
    _save_raw(data)


def create_group(name: str, devices: Optional[list[Device]] = None) -> Group:
    groups = load_groups()
    group = Group(name=name, devices=devices or [])
    groups.append(group)
    save_groups(groups)
    return group


def delete_group(name: str) -> bool:
    groups = load_groups()
    new_groups = [g for g in groups if g.name != name]
    if len(new_groups) == len(groups):
        return False
    save_groups(new_groups)
    return True


def rename_group(old_name: str, new_name: str) -> bool:
    groups = load_groups()
    for g in groups:
        if g.name == old_name:
            g.name = new_name
            save_groups(groups)
            return True
    return False


def get_group(name: str) -> Optional[Group]:
    groups = load_groups()
    for g in groups:
        if g.name == name:
            return g
    return None


def add_device_to_group(group_name: str, device: Device) -> bool:
    groups = load_groups()
    for g in groups:
        if g.name == group_name:
            # Avoid duplicate MAC
            if any(d.mac == device.mac for d in g.devices):
                return False
            g.devices.append(device)
            save_groups(groups)
            return True
    return False


def remove_device_from_group(group_name: str, mac: str) -> bool:
    groups = load_groups()
    for g in groups:
        if g.name == group_name:
            new_devices = [d for d in g.devices if d.mac != mac]
            if len(new_devices) == len(g.devices):
                return False
            g.devices = new_devices
            save_groups(groups)
            return True
    return False


def rename_device(group_name: str, mac: str, new_name: str) -> bool:
    groups = load_groups()
    for g in groups:
        if g.name == group_name:
            for d in g.devices:
                if d.mac == mac:
                    d.custom_name = new_name
                    save_groups(groups)
                    return True
    return False


def update_device_ip(group_name: str, mac: str, new_ip: str) -> bool:
    groups = load_groups()
    for g in groups:
        if g.name == group_name:
            for d in g.devices:
                if d.mac == mac:
                    d.last_known_ip = new_ip
                    save_groups(groups)
                    return True
    return False
