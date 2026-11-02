"""Compresses Live2D assets into zip files.
The archives are named corresponding to their respective
characters, NPCs, and skins. (<character> <skin>.zip,
NPC <npc> <skin>.zip, and <model>.zip for createplayer models.)

Inside the ZIP file, the model manifest and related files are
two layers down from the root.

live2d/base/13503_L.moc3
live2d/base/13503_base.model3.json
live2d/base/motions/...
live2d/base/textures/...
"""

from __future__ import annotations

import argparse
import zipfile
from functools import cache
from pathlib import Path
from typing import Callable

from utils.data_utils import assets_root, autoload
from character_info.characters import id_to_char

DEFAULT_OUT = Path("assets") / "live2d_zips"
CHARACTER_ROOT = Path(assets_root / "actor2d/character")
NPC_ROOT = Path(assets_root / "actor2d/npc")
CREATEPLAYER_ROOT = Path(assets_root / "ui/createplayer/l2d")

CREATEPLAYER_NAMES = {
    "createplayer2_f": "Female Tyrant",
    "createplayer2_m": "Male Tyrant",
}

def _character_zip_name(skin_id: str) -> str | None:
    char = id_to_char(int(skin_id[:-2]))
    if char is None:
        print(f"WARNING: No character found for skin {skin_id}")
        return None
    return f"{char.name} {int(skin_id[-2:]):02d}"


@cache
def _npc_names() -> dict[int, str]:
    npc_names: dict[int, str] = {}
    for v in autoload("NPCConfig").values():
        if v['Id'] >= 9000:
            npc_names[v['Id']] = v['Name']
    for v in autoload("BoardNPC").values():
        npc_names.setdefault(v['Id'], v['Name'])
    return npc_names


def _npc_zip_name(skin_id: str) -> str | None:
    npc_names = _npc_names()
    npc_id = int(skin_id)
    name = npc_names.get(npc_id) or npc_names.get(int(skin_id[:-2]))
    if name is None:
        print(f"WARNING: No NPC name found for skin {skin_id}")
        return None
    return f"NPC {name} {int(skin_id[-2:]):02d}"


def _createplayer_zip_name(model_name: str) -> str | None:
    return CREATEPLAYER_NAMES.get(model_name)


def create_zips(
    out: Path = DEFAULT_OUT,
    overwrite: bool = False,
) -> list[Path]:
    out = Path(out)

    zip_sources: list[tuple[Path, Callable[[str], str | None]]] = [
        (CHARACTER_ROOT, _character_zip_name),
        (NPC_ROOT, _npc_zip_name),
        (CREATEPLAYER_ROOT, _createplayer_zip_name),
    ]
    for source_root, _ in zip_sources:
        if not source_root.exists():
            print(f"{source_root} does not exist, you may need to run main2 or main")

    out.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    for source_root, zip_name in zip_sources:
        if not source_root.exists():
            continue

        for skin_dir in sorted(source_root.glob("*/")):
            skin_id = skin_dir.name
            live2d_root = skin_dir / "live2d"
            if not live2d_root.exists():
                print(f"Live2D root is missing for {skin_id}")
                continue

            model_name = zip_name(skin_id)
            if model_name is None:
                continue
            zip_path = out / f"{model_name}.zip"

            # Handle collisions (e.g. two skins mapping to same name)
            if zip_path.exists() and not overwrite:
                print(f"Skipping {zip_path.name}: exists")
                continue

            files = sorted(p for p in live2d_root.rglob("*") if p.is_file())

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                for file in files:
                    arcname = file.relative_to(skin_dir).as_posix()
                    zf.write(file, arcname)

            print(f"Created {zip_path} ({len(files)} files) from {skin_id}")
            created.append(zip_path)

    print(f"Done: {len(created)} zip(s) in {out}" if created else "No zips created")
    return created


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zip Live2D folders into sprite-named archives.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory for zips")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing zips")
    return parser.parse_args()

def main() -> None:
    args = _parse_args()
    create_zips(
        out=args.out,
        overwrite=args.overwrite,
    )

if __name__ == "__main__":
    main()
