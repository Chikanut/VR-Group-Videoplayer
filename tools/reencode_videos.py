"""Re-encode videos for the Quest player in place: same folder, same file name.

    python tools/reencode_videos.py "D:\\path\\VR Videos"            # whole folder tree
    python tools/reencode_videos.py "D:\\path\\video.mp4"            # one file
    python tools/reencode_videos.py "D:\\path\\VR Videos" --dry-run  # only show the plan

Originals are never deleted: each is moved to "<folder>\\_originals\\..." (same sub-path)
and the new file takes its name. A file that already has a copy in _originals is skipped,
so the script can be re-run after an interruption.

What gets re-encoded (HEVC, NVIDIA encoder, audio untouched):
  - wider than 4096 px (8K / 6K 360 video) -> 4096x4096. The player caps its texture at
    4096 px per side, so 7680x3840 is shown as 4096x3840 anyway; this keeps that picture
    and gives the decoder ~43% fewer pixels;
  - up to 4096 px wide but over 45 Mbit/s    -> same size, lower bitrate.
Everything else is left alone.
No NVIDIA GPU: replace ENCODER with ["-c:v", "libx265", "-preset", "medium", "-crf", "21"].
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

MAX_SIDE = 4096
MAX_BITRATE = 45_000_000
EXTENSIONS = {".mp4", ".mkv", ".mov", ".m4v"}
BACKUP_DIR = "_originals"
ENCODER = ["-c:v", "hevc_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "24", "-b:v", "0"]


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,width,height:format=bit_rate", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    return {"codec": stream["codec_name"], "width": int(stream["width"]), "height": int(stream["height"]),
            "bitrate": int(data["format"].get("bit_rate") or 0)}


def plan(info: dict):
    """Returns (scale filter or None, reason) or None when the file is fine as it is."""
    if info["width"] > MAX_SIDE:
        return f"scale={MAX_SIDE}:{MAX_SIDE}:flags=lanczos,setsar=1", f"-> {MAX_SIDE}x{MAX_SIDE} HEVC"
    if info["bitrate"] > MAX_BITRATE:
        return None, "-> same size, HEVC at a lower bitrate"
    return None


def reencode(src: Path, backup: Path, scale, bitrate: int) -> None:
    tmp = src.with_name(src.stem + ".reencoding" + src.suffix)
    maxrate = min(bitrate or 40_000_000, 40_000_000)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y", "-i", str(src)]
    if scale:
        cmd += ["-vf", scale]
    cmd += ENCODER + ["-maxrate", str(maxrate), "-bufsize", str(maxrate * 2),
                      "-profile:v", "main", "-pix_fmt", "yuv420p", "-g", "30", "-tag:v", "hvc1",
                      "-c:a", "copy", "-movflags", "+faststart", str(tmp)]
    try:
        subprocess.run(cmd, check=True)
    except BaseException:  # also Ctrl+C: never leave a half-written file behind
        tmp.unlink(missing_ok=True)
        raise
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(backup))  # the original is kept, only moved
    tmp.rename(src)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if len(args) != 1 or not Path(args[0]).exists():
        print(__doc__)
        return 1
    target = Path(args[0])
    root = target if target.is_dir() else target.parent
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in EXTENSIONS) if target.is_dir() else [target]

    for src in files:
        relative = src.relative_to(root)
        if BACKUP_DIR in relative.parts or ".reencoding" in src.name:
            continue
        backup = root / BACKUP_DIR / relative
        try:
            info = probe(src)
        except Exception as exc:
            print(f"SKIP  {relative}: cannot read ({exc})")
            continue
        label = f"{relative}  [{info['codec']} {info['width']}x{info['height']}, {info['bitrate'] / 1e6:.0f} Mbit/s]"
        todo = plan(info)
        if backup.exists():
            print(f"DONE  {label} (original is in {BACKUP_DIR})")
        elif todo is None:
            print(f"OK    {label}")
        elif dry_run:
            print(f"TODO  {label} {todo[1]}")
        else:
            print(f"ENCODE {label} {todo[1]}", flush=True)
            reencode(src, backup, todo[0], info["bitrate"])
            print(f"      done: {src.stat().st_size / 1e9:.2f} GB (was {backup.stat().st_size / 1e9:.2f} GB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
