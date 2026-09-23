import json
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, path: str = "groups.json") -> None:
        self.path = Path(path)
        self._data = {"groups": []}
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.save()
        with self.path.open("r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._data.setdefault("groups", [])
        return self._data

    def save(self) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def list_groups(self) -> list[dict]:
        return self._data["groups"]

    def create_group(self, name: str, devices: list[dict]) -> None:
        if any(g["name"] == name for g in self._data["groups"]):
            raise ValueError("Group already exists")
        normalized_devices = []
        for d in devices:
            normalized_devices.append(
                {
                    "mac": d["mac"].lower(),
                    "custom_name": d.get("custom_name") or d.get("name") or d["mac"],
                    "last_known_ip": d.get("last_known_ip") or d.get("ip") or "",
                }
            )
        self._data["groups"].append({"name": name, "devices": normalized_devices})
        self.save()

    def delete_group(self, name: str) -> None:
        self._data["groups"] = [g for g in self._data["groups"] if g["name"] != name]
        self.save()

    def update_group_name(self, old_name: str, new_name: str) -> None:
        if any(g["name"] == new_name for g in self._data["groups"]):
            raise ValueError("Group already exists")
        for group in self._data["groups"]:
            if group["name"] == old_name:
                group["name"] = new_name
                break
        self.save()

    def get_group(self, name: str) -> dict | None:
        return next((g for g in self._data["groups"] if g["name"] == name), None)

    def add_device(self, group_name: str, device: dict) -> None:
        group = self.get_group(group_name)
        if not group:
            raise ValueError("Group not found")
        mac = device["mac"].lower()
        if any(d["mac"] == mac for d in group["devices"]):
            raise ValueError("Device with this MAC already exists in the group")
        group["devices"].append(
            {
                "mac": mac,
                "custom_name": device.get("custom_name") or device.get("name") or mac,
                "last_known_ip": device.get("last_known_ip") or device.get("ip") or "",
            }
        )
        self.save()

    def remove_device(self, group_name: str, mac: str) -> None:
        group = self.get_group(group_name)
        if not group:
            raise ValueError("Group not found")
        group["devices"] = [d for d in group["devices"] if d["mac"] != mac.lower()]
        self.save()

    def rename_device(self, group_name: str, mac: str, new_name: str) -> None:
        group = self.get_group(group_name)
        if not group:
            raise ValueError("Group not found")
        for device in group["devices"]:
            if device["mac"] == mac.lower():
                device["custom_name"] = new_name
                break
        self.save()

    def update_device_ip(self, group_name: str, mac: str, new_ip: str) -> None:
        group = self.get_group(group_name)
        if not group:
            raise ValueError("Group not found")
        for device in group["devices"]:
            if device["mac"] == mac.lower():
                device["last_known_ip"] = new_ip
                break
        self.save()
