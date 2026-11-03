from pathlib import Path

from unpack.unpack_image import sprite_export, texture2d_export
from unpack.unpack_utils import asset_map, get_unity3d_files

def get_banner_bundle_files() -> list[Path]:
    files = get_unity3d_files()
    keywords = ("icon-", "gachacover", "sidebanner")
    return [f for f in files if any(k in f.name.lower() for k in keywords)]

def export_banner_assets() -> None:
    files = get_banner_bundle_files()
    print(f"Exporting banner assets from {len(files)} bundles...")
    asset_map(files, texture2d_export)
    asset_map(files, sprite_export)

def main() -> None:
    export_banner_assets()

if __name__ == "__main__":
    main()
