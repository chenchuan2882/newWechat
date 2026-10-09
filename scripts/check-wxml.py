"""Checks tag nesting and controller bindings; not a WeChat compiler."""

import json
import re
from pathlib import Path
from xml.etree import ElementTree

root = Path(__file__).resolve().parents[1] / "miniprogram"
for p in root.rglob("*.wxml"):
    source = p.read_text()
    # Normalize expression syntax to XML for a portable tag-nesting check.
    source = re.sub(
        r"\{\{.*?\}\}",
        lambda m: m.group()
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&", "&amp;")
        .replace("<", "&lt;"),
        source,
        flags=re.S,
    )
    ElementTree.fromstring(
        '<root xmlns:wx="urn:wx" xmlns:bind="urn:bind">' + source + "</root>"
    )
    js = p.with_suffix(".js").read_text()
    for handler in re.findall(
        r'(?:bind\w+|catch\w+|bind:\w+)="([A-Za-z_][\w]*)"', source
    ):
        assert re.search(r"\b" + handler + r"\s*\(", js) or handler in {
            "openPost",
            "openAuthor",
            "likePost",
            "collectPost",
        }, (str(p), handler)
print("WXML tag nesting and controller bindings passed.")
