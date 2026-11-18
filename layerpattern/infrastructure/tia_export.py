"""Siemens TIA Portal V21 sources: one type source (.udt) and one DB source (.db).

Conventions taken from the sources that already imported fine (V2): plain ASCII,
CRLF line ends, optimized DB access, start values after BEGIN. All Siemens syntax
lives in the Jinja2 templates next to this module.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from layerpattern import APP_NAME, APP_VERSION
from layerpattern.domain.export_model import FORMAT_NAME, FORMAT_VERSION, ExportSnapshot
from layerpattern.domain.model import MAX_PATTERN_ID
from layerpattern.domain.rational import real_literal

TEMPLATES = Path(__file__).with_name("templates")
BLOCK_VERSION = "1.0"


def ascii_text(text: str) -> str:
    """Comments must stay ASCII: transliterate umlauts, drop what has no equivalent."""
    for src, dst in (("ß", "ss"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ä", "ae"),
                     ("ö", "oe"), ("ü", "ue"), ("–", "-"), ("—", "-"), ("„", '"'),
                     ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
        text = text.replace(src, dst)
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in plain if ch.isprintable())


def _environment():
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
                      undefined=StrictUndefined)
    env.filters["real"] = real_literal
    return env


def render(snapshot: ExportSnapshot) -> tuple[str, str]:
    """(type source, DB source) with LF line ends; `write` converts to CRLF."""
    env = _environment()
    common = {
        "generator": f"{APP_NAME} {APP_VERSION}",
        "format_name": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "generated": snapshot.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "project": ascii_text(snapshot.project_name),
        "names": snapshot.names,
        "block_version": BLOCK_VERSION,
        "max_pattern_id": MAX_PATTERN_ID,
        "snapshot": snapshot,
    }
    types = env.get_template("types.udt.j2").render(
        content="PLC data types for the layer pattern parameters", **common)
    db = env.get_template("patterns.db.j2").render(
        content="Layer pattern parameters (start values)", **common)
    return types, db


def encode(text: str) -> bytes:
    """ASCII with CRLF; raises if anything non-ASCII slipped through."""
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii")
