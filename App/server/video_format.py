"""Canonical video format identifiers shared by config, API and the /open payload.

A format is two orthogonal axes:

* projection: ``flat`` | ``180`` | ``360``
* stereo:     ``mono`` | ``sbs`` | ``tb``

They are joined into one canonical ``formatId`` string (``2d``, ``360``, ``360_sbs``,
``360_tb``, ``180``, ``180_sbs``, ``180_tb``). ``auto`` is only valid in the config and
means "detect when the video is added / opened".

Backward compatibility rules live here too:

* ``legacy_mode_for()`` collapses any format into the ``"360"`` / ``"2d"`` value that
  players built before stereo support understand.
* ``normalize_format_id()`` accepts every alias that has been used in the project or
  that is common in the industry (``_LR``, ``_OU``, ``3dh`` ...).
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional, Tuple

PROJECTION_FLAT = "flat"
PROJECTION_180 = "180"
PROJECTION_360 = "360"
PROJECTIONS = (PROJECTION_FLAT, PROJECTION_180, PROJECTION_360)

STEREO_MONO = "mono"
STEREO_SBS = "sbs"
STEREO_TB = "tb"
STEREO_LAYOUTS = (STEREO_MONO, STEREO_SBS, STEREO_TB)

FORMAT_AUTO = "auto"
DEFAULT_FORMAT = "360"

# formatId -> (projection, stereo)
CANONICAL_FORMATS: Dict[str, Tuple[str, str]] = {
    "2d": (PROJECTION_FLAT, STEREO_MONO),
    "360": (PROJECTION_360, STEREO_MONO),
    "360_sbs": (PROJECTION_360, STEREO_SBS),
    "360_tb": (PROJECTION_360, STEREO_TB),
    "180": (PROJECTION_180, STEREO_MONO),
    "180_sbs": (PROJECTION_180, STEREO_SBS),
    "180_tb": (PROJECTION_180, STEREO_TB),
}

VALID_FORMAT_IDS = frozenset(CANONICAL_FORMATS) | {FORMAT_AUTO}

# Tokens that identify a projection or stereo layout inside a formatId or a filename.
_PROJECTION_TOKENS: Dict[str, str] = {
    "2d": PROJECTION_FLAT,
    "flat": PROJECTION_FLAT,
    "180": PROJECTION_180,
    "vr180": PROJECTION_180,
    "hemisphere180": PROJECTION_180,
    "360": PROJECTION_360,
    "sphere": PROJECTION_360,
    "sphere360": PROJECTION_360,
}

_STEREO_TOKENS: Dict[str, str] = {
    "mono": STEREO_MONO,
    "sbs": STEREO_SBS,
    "lr": STEREO_SBS,
    "3dh": STEREO_SBS,
    "sidebyside": STEREO_SBS,
    "tb": STEREO_TB,
    "ou": STEREO_TB,
    "3dv": STEREO_TB,
    "topbottom": STEREO_TB,
    "overunder": STEREO_TB,
}

_SPLIT_RE = re.compile(r"[\s_\-.]+")

# Human readable labels (English, the frontend localizes on its own).
FORMAT_LABELS: Dict[str, str] = {
    "2d": "2D",
    "360": "360°",
    "360_sbs": "360° 3D SBS",
    "360_tb": "360° 3D TB",
    "180": "180°",
    "180_sbs": "180° 3D SBS",
    "180_tb": "180° 3D TB",
    FORMAT_AUTO: "Auto",
}


def make_format_id(projection: str, stereo: str) -> str:
    """Join a projection and stereo layout into a canonical formatId."""
    projection = (projection or "").strip().lower()
    stereo = (stereo or "").strip().lower() or STEREO_MONO
    if projection == PROJECTION_FLAT:
        return "2d"
    if projection not in PROJECTIONS:
        projection = PROJECTION_360
    if stereo not in STEREO_LAYOUTS:
        stereo = STEREO_MONO
    return projection if stereo == STEREO_MONO else f"{projection}_{stereo}"


def _tokens(value: str) -> List[str]:
    return [token for token in _SPLIT_RE.split((value or "").strip().lower()) if token]


def _scan_tokens(tokens: Iterable[str]) -> Tuple[Optional[str], Optional[str]]:
    projection = None
    stereo = None
    for token in tokens:
        if token in _PROJECTION_TOKENS and projection is None:
            projection = _PROJECTION_TOKENS[token]
        elif token in _STEREO_TOKENS and stereo is None:
            stereo = _STEREO_TOKENS[token]
    return projection, stereo


def normalize_format_id(value: object) -> Optional[str]:
    """Return the canonical formatId for `value`, or None when it cannot be understood.

    Accepts canonical ids, ``auto`` and all aliases: ``flat``, ``sphere``, ``360_mono``,
    ``180_lr``, ``180_3dh``, ``360_ou``, ``360_3dv``, ``180_mono`` and so on. Token order is
    irrelevant (``sbs_180`` == ``180_sbs``).
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text == FORMAT_AUTO:
        return FORMAT_AUTO
    if text in CANONICAL_FORMATS:
        return text

    projection, stereo = _scan_tokens(_tokens(text))
    if projection is None:
        return None
    return make_format_id(projection, stereo or STEREO_MONO)


def is_valid_format_id(value: object) -> bool:
    return normalize_format_id(value) is not None


def split_format_id(format_id: str) -> Tuple[str, str]:
    """formatId -> (projection, stereo). Unknown / auto values fall back to 360 mono."""
    normalized = normalize_format_id(format_id)
    if normalized is None or normalized == FORMAT_AUTO:
        normalized = DEFAULT_FORMAT
    return CANONICAL_FORMATS[normalized]


def projection_of(format_id: str) -> str:
    return split_format_id(format_id)[0]


def stereo_of(format_id: str) -> str:
    return split_format_id(format_id)[1]


def is_stereo(format_id: str) -> bool:
    return stereo_of(format_id) != STEREO_MONO


def legacy_mode_for(format_id: str) -> str:
    """The ``mode`` value that pre-stereo players understand: ``"2d"`` or ``"360"``.

    180° content maps to ``"360"`` so an old player shows something sensible (a stretched
    hemisphere) instead of failing.
    """
    return "2d" if projection_of(format_id) == PROJECTION_FLAT else "360"


def format_id_from_legacy_mode(mode: object) -> str:
    """Interpret a legacy ``mode`` string ("360" / "2d" / "sphere" / "flat") as a formatId."""
    normalized = normalize_format_id(mode)
    if normalized is None or normalized == FORMAT_AUTO:
        return DEFAULT_FORMAT
    return normalized


def format_label(format_id: str) -> str:
    normalized = normalize_format_id(format_id) or DEFAULT_FORMAT
    return FORMAT_LABELS.get(normalized, normalized)


# --------------------------------------------------------------------------------------
# Filename convention: <name>_<projection>_<stereo>.<ext>   e.g. reef-dive_180_LR.mp4
# --------------------------------------------------------------------------------------

def detect_format_from_filename(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (projection, stereo) hinted by the filename suffix. Either may be None.

    Examples::

        "clip_180_LR.mp4"        -> ("180", "sbs")
        "tour_360_TB.mov"        -> ("360", "tb")
        "history_360.mp4"        -> ("360", None)
        "intro_2d_MONO.mp4"      -> ("flat", "mono")
        "lesson01.mp4"           -> (None, None)
    """
    if not filename:
        return None, None

    base = os.path.basename(str(filename))
    stem, _ext = os.path.splitext(base)
    tokens = _tokens(stem)
    if not tokens:
        return None, None

    projection = None
    stereo = None

    # Only the very end of the stem counts: "<name>_<proj>_<stereo>", "<name>_<proj>"
    # or "<name>_<stereo>". A "360" in the middle of a title is not a suffix.
    last = tokens[-1]
    if last in _STEREO_TOKENS:
        stereo = _STEREO_TOKENS[last]
        if len(tokens) >= 2 and tokens[-2] in _PROJECTION_TOKENS:
            projection = _PROJECTION_TOKENS[tokens[-2]]
    elif last in _PROJECTION_TOKENS:
        projection = _PROJECTION_TOKENS[last]

    return projection, stereo


def format_id_from_filename(filename: str) -> Optional[str]:
    """Full formatId from the filename convention, or None if the name carries no hint."""
    projection, stereo = detect_format_from_filename(filename)
    if projection is None:
        return None
    return make_format_id(projection, stereo or STEREO_MONO)


def describe_format(format_id: str) -> Dict[str, str]:
    normalized = normalize_format_id(format_id) or DEFAULT_FORMAT
    if normalized == FORMAT_AUTO:
        return {"formatId": FORMAT_AUTO, "projection": "", "stereo": "", "label": FORMAT_LABELS[FORMAT_AUTO]}
    projection, stereo = CANONICAL_FORMATS[normalized]
    return {
        "formatId": normalized,
        "projection": projection,
        "stereo": stereo,
        "legacyMode": legacy_mode_for(normalized),
        "label": FORMAT_LABELS[normalized],
    }


def list_formats() -> List[Dict[str, str]]:
    return [describe_format(format_id) for format_id in CANONICAL_FORMATS]
