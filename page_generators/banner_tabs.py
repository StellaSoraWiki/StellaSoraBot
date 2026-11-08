from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from typing import Any

from character_info.characters import get_id_to_char
from page_generators.events import _event_start_dt, get_all_events, get_event_group_rows
from page_generators.items import get_all_items
from utils.data_utils import assets_root, autoload
from utils.upload_utils import UploadRequest, process_uploads
from utils.wiki_utils import PageCreationRequest, process_page_creation_requests

# Copied from events.py, should probably be put into a constant somewhere
WIKI_TIMEZONE = timezone(timedelta(hours=-7))

def find_tab_file(res: str | None) -> Path | None:
    if not res:
        return None
    res = res.replace("\\", "/")
    parts = res.split("/")
    filename = parts[-1]
    subpath = "/".join(p.lower() for p in parts[:-1])

    # Older banner images are not suffixed with _lang
    candidates = [
        assets_root / f"assetbundles_en/{subpath}/{filename}.png",
        assets_root / f"assetbundles/{subpath}/{filename}.png",
        assets_root / f"assetbundles_en/{subpath}/{filename}_lang.png",
        assets_root / f"assetbundles/{subpath}/{filename}_lang.png",
        Path(f"assets/assetbundles_en/{subpath}/{filename}.png"),
        Path(f"assets/assetbundles/{subpath}/{filename}.png"),
        Path(f"assets/assetbundles_en/{subpath}/{filename}_lang.png"),
        Path(f"assets/assetbundles/{subpath}/{filename}_lang.png"),
    ]
    if filename.endswith("_lang"):
        base = filename[:-5]
        candidates.extend([
            assets_root / f"assetbundles_en/{subpath}/{base}.png",
            assets_root / f"assetbundles/{subpath}/{base}.png",
            Path(f"assets/assetbundles_en/{subpath}/{base}.png"),
            Path(f"assets/assetbundles/{subpath}/{base}.png"),
        ])
    for c in candidates:
        if c.exists():
            return c
    return None

# Couldn't find an equiv to this looking around the code,
# should likely be replaced
def _clean_title(name: str) -> str:
    # MediaWiki file names cannot contain: : / \ [ ] { } | # < >
    cleaned = re.sub(r'[:/\\\[\]{}|#<>]', ' ', name)
    return re.sub(r'\s+', ' ', cleaned).strip()

# Copied from events.py
def _wiki_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

@cache
def _get_pkg_to_item_name() -> dict[int, str]:
    items = get_all_items()
    pkg_data = autoload("GachaPkg")
    mapping: dict[int, str] = {}
    for entry in pkg_data.values():
        pkg_id = entry.get("PkgId")
        goods_id = entry.get("GoodsId")
        if pkg_id is not None and goods_id in items:
            mapping[pkg_id] = items[goods_id].title
    return mapping


def get_gacha_banner_entries() -> list[dict[str, Any]]:
    gacha_data = autoload("Gacha")
    chars = get_id_to_char()
    pkg_to_item = _get_pkg_to_item_name()

    entries: list[dict[str, Any]] = []
    for gacha_id, v in sorted(gacha_data.items(), key=lambda x: int(x[0])):
        raw_name = v.get("Name")
        if not raw_name:
            continue
        name = _clean_title(raw_name)
        icon_res = v.get("Icon")
        source_file = find_tab_file(icon_res)
        if not source_file:
            continue

        start_time = v.get("StartTime")
        date_str = _wiki_date(datetime.fromisoformat(start_time))

        # Determine target file name and aliases/redirects
        redirects: list[str] = []

        if name == "A Fateful Encounter" or name == "A Heart-Tuned Melody":
            if name == "A Fateful Encounter":
                target_obj = chars.get(v.get("GuaranteeTid"))
                target_name if target_obj else None
            else:
                target_name = pkg_to_item.get(v.get("ATypeUpPkg"))
            if target_name:
                target_title = f"File:Tab Banner {name} {banner_target_name} EN.png"
                redirects.append(f"File:Tab Banner {name} {banner_target_name}.png")
                if date_str:
                    redirects.append(f"File:Tab Banner {name} {date_str} EN.png")
                    redirects.append(f"File:Tab Banner {name} {date_str}.png")
            else:
                target_title = f"File:Tab Banner {name} {date_str} EN.png" if date_str else f"File:Tab Banner {name} EN.png"
                if date_str:
                    redirects.append(f"File:Tab Banner {name} {date_str}.png")
        else:
            if date_str:
                target_title = f"File:Tab Banner {name} {date_str} EN.png"
                redirects.append(f"File:Tab Banner {name} {date_str}.png")
                redirects.append(f"File:Tab Banner {name}.png")
            else:
                target_title = f"File:Tab Banner {name} EN.png"
                redirects.append(f"File:Tab Banner {name}.png")

        entries.append({
            "id": gacha_id,
            "name": name,
            "source_file": source_file,
            "target_title": target_title,
            "redirects": redirects,
        })

    return entries


def get_activity_banner_entries() -> list[dict[str, Any]]:
    events = get_all_events()
    rows = get_event_group_rows()

    entries: list[dict[str, Any]] = []
    for event_id, event in events.items():
        if not event.name:
            continue
        event_name = _clean_title(event.name)
        row = rows.get(event_id, {})
        tab_res = row.get("TabBgRes")
        if not tab_res:
            continue
        source_file = find_tab_file(tab_res)
        if not source_file:
            continue

        start_dt = _event_start_dt(event)
        date_str = start_dt.strftime("%Y-%m-%d")

        target_title = f"File:Tab Banner {event_name} {date_str} EN.png"
        redirects = [
            f"File:Tab Banner {event_name} {date_str}.png",
            f"File:Tab Banner {event_name}.png",
        ]

        entries.append({
            "id": event_id,
            "name": event.name,
            "source_file": source_file,
            "target_title": target_title,
            "redirects": redirects,
        })

    return entries


def build_banner_tab_requests() -> tuple[list[UploadRequest], list[PageCreationRequest]]:
    seen_targets: set[str] = set()
    upload_requests: list[UploadRequest] = []
    redirect_map: dict[str, str] = {}

    all_entries = get_gacha_banner_entries() + get_activity_banner_entries()

    for entry in all_entries:
        target = entry["target_title"]
        source = entry["source_file"]
        if target not in seen_targets:
            seen_targets.add(target)
            upload_requests.append(UploadRequest(
                source=source,
                target=target,
                text="[[Category:English images]][[Category:Banner tab images]]",
                summary="batch upload banner tab image",
            ))
        for r in entry["redirects"]:
            if r != target and r not in redirect_map:
                redirect_map[r] = target

    redirect_requests = [
        PageCreationRequest(
            page=src,
            text=f"#REDIRECT [[{dst}]]",
            summary="redirect to banner tab image",
        )
        for src, dst in redirect_map.items()
    ]

    return upload_requests, redirect_requests


def upload_banner_tabs(overwrite: bool = False, force: bool = False) -> None:
    uploads, redirects = build_banner_tab_requests()
    print(f"Processing {len(uploads)} banner tab image uploads...")
    process_uploads(uploads, overwrite=overwrite, force=force)
    print(f"Processing {len(redirects)} banner tab redirects...")
    process_page_creation_requests(redirects, overwrite=False)


def main() -> None:
    upload_banner_tabs()


if __name__ == "__main__":
    main()
