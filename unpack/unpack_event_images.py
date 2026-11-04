import re
from dataclasses import dataclass, field
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import UnityPy
from PIL import Image
from UnityPy.enums import ClassIDType
from UnityPy.files import ObjectReader

from unpack.unpack_model import _bundle_cabs, get_cab_index
from unpack.unpack_paths import data_dir
from unpack.unpack_utils import get_unity3d_files

ROOT_SIZE = (2400.0, 1700.0)
MIN_SPRITE_AREA = 500_000
MIN_OUTPUT_AREA = 800_000

SpriteKey = tuple[str, int]


@dataclass
class RectNode:
    path_id: int
    game_object_id: int
    name: str
    active: bool
    rect: dict[str, Any]
    parent_id: int | None
    child_ids: list[int] = field(default_factory=list)


@dataclass
class SpriteInfo:
    name: str
    width: int
    height: int
    obj: ObjectReader
    _image: Image.Image | None = None
    _opaque_fraction: float | None = None
    _grayscale: bool | None = None

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def image(self) -> Image.Image:
        if self._image is None:
            self._image = self.obj.read().image.convert("RGBA")
        return self._image

    @property
    def opaque_fraction(self) -> float:
        if self._opaque_fraction is None:
            histogram = self.image.getchannel("A").histogram()
            self._opaque_fraction = sum(histogram[250:]) / max(1, self.image.width * self.image.height)
        return self._opaque_fraction

    @property
    def grayscale(self) -> bool:
        if self._grayscale is None:
            _, max_saturation = self.image.convert("RGB").convert("HSV").getchannel("S").getextrema()
            self._grayscale = max_saturation == 0
        return self._grayscale

    @property
    def is_art(self) -> bool:
        if self.name.lower().startswith(("db_", "btn_", "zs_", "fx_")):
            return False
        return self.area >= MIN_SPRITE_AREA and self.opaque_fraction >= 0.9 and not self.grayscale

    @property
    def is_background(self) -> bool:
        if self.is_art:
            return True
        return self.name.lower().startswith("bg_") and self.area >= MIN_SPRITE_AREA and self.opaque_fraction >= 0.1


@dataclass
class ImageNode:
    game_object_id: int
    sprite: SpriteInfo
    enabled: bool
    sliced: bool
    color: tuple[float, float, float, float]


@dataclass
class Layout:
    left: float
    top: float
    width: float
    height: float
    pivot_x: float
    pivot_y: float


class _BorrowedTypeTrees:
    """Old bundles ship MonoBehaviours without type trees; borrow them from a current bundle."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], Any] | None = None

    def _harvest(self) -> dict[tuple[str, str], Any]:
        nodes: dict[tuple[str, str], Any] = {}
        for bundle in _activity_bundles():
            if bundle.parent.name == "OldAssets":
                continue
            env = UnityPy.load(str(bundle))
            for obj in env.objects:
                if obj.type != ClassIDType.MonoBehaviour or not obj.serialized_type or not obj.serialized_type.node:
                    continue
                try:
                    script = obj.parse_monobehaviour_head().m_Script.deref_parse_as_object()
                except Exception:
                    continue
                full_name = f"{script.m_Namespace}.{script.m_ClassName}" if script.m_Namespace else script.m_ClassName
                nodes.setdefault((script.m_AssemblyName, full_name), obj.serialized_type.node)
            if nodes:
                break
        return nodes

    def get_nodes_up(self, assembly: str, full_name: str) -> Any:
        if self.nodes is None:
            self.nodes = self._harvest()
        return self.nodes.get((assembly, full_name))


_borrowed_type_trees = _BorrowedTypeTrees()


@cache
def _cab_index() -> dict[str, str]:
    index = dict(get_cab_index())
    for bundle in _old_asset_bundles():
        path, cabs = _bundle_cabs(str(bundle))
        for cab in cabs:
            index.setdefault(cab, path)
    return index


@lru_cache(maxsize=8)
def _load_env(path: str) -> UnityPy.Environment:
    return UnityPy.load(path)


def _ptr_id(value: dict[str, Any] | None) -> int | None:
    if not value:
        return None
    path_id = value.get("m_PathID")
    return path_id if path_id else None


def _vec2(value: dict[str, Any], default_x: float = 0.0, default_y: float = 0.0) -> tuple[float, float]:
    return float(value.get("x", default_x)), float(value.get("y", default_y))


def _color(value: dict[str, Any] | None) -> tuple[float, float, float, float]:
    if not value:
        return 1.0, 1.0, 1.0, 1.0
    return (
        float(value.get("r", 1.0)),
        float(value.get("g", 1.0)),
        float(value.get("b", 1.0)),
        float(value.get("a", 1.0)),
    )


def _safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip("/"))
    return value.strip("_") or "background"


def _sprite_key(obj: ObjectReader, pointer: dict[str, Any]) -> SpriteKey | None:
    path_id = _ptr_id(pointer)
    if path_id is None:
        return None
    file_id = pointer.get("m_FileID", 0)
    if file_id == 0:
        return obj.assets_file.name.lower(), path_id
    externals = obj.assets_file.externals
    if file_id > len(externals):
        return None
    return externals[file_id - 1].path.rsplit("/", 1)[-1].lower(), path_id


def _load_sprite(env: UnityPy.Environment, key: SpriteKey) -> SpriteInfo | None:
    cab, path_id = key
    file = env.get_cab(cab)
    if file is None and cab in _cab_index():
        file = _load_env(_cab_index()[cab]).get_cab(cab)
    obj = getattr(file, "objects", {}).get(path_id)
    if obj is None or obj.type != ClassIDType.Sprite:
        return None
    try:
        sprite = obj.read()
    except Exception as e:
        print(f"WARNING: Could not read sprite {path_id} from {cab}: {e}")
        return None
    return SpriteInfo(
        name=sprite.m_Name,
        width=round(sprite.m_Rect.width),
        height=round(sprite.m_Rect.height),
        obj=obj,
    )


def _read_bundle(bundle: Path) -> tuple[dict[int, RectNode], dict[int, ImageNode], list[SpriteInfo]]:
    env = UnityPy.load(str(bundle))
    env.typetree_generator = _borrowed_type_trees
    game_objects: dict[int, dict[str, Any]] = {}
    rects: dict[int, RectNode] = {}
    images: dict[int, ImageNode] = {}
    sprites: dict[SpriteKey, SpriteInfo | None] = {}

    for obj in env.objects:
        if obj.type == ClassIDType.GameObject:
            game_objects[obj.path_id] = obj.read_typetree()

    for obj in env.objects:
        if obj.type == ClassIDType.RectTransform:
            data = obj.read_typetree()
            game_object_id = _ptr_id(data.get("m_GameObject"))
            if game_object_id is None:
                continue
            game_object = game_objects.get(game_object_id, {})
            child_ids = [_ptr_id(child) for child in data.get("m_Children", [])]
            rects[obj.path_id] = RectNode(
                path_id=obj.path_id,
                game_object_id=game_object_id,
                name=game_object.get("m_Name", ""),
                active=bool(game_object.get("m_IsActive", True)),
                rect=data,
                parent_id=_ptr_id(data.get("m_Father")),
                child_ids=[child_id for child_id in child_ids if child_id is not None],
            )

    for obj in env.objects:
        if obj.type != ClassIDType.MonoBehaviour:
            continue
        try:
            data = obj.read_typetree()
        except Exception:
            continue
        key = _sprite_key(obj, data.get("m_Sprite"))
        game_object_id = _ptr_id(data.get("m_GameObject"))
        if key is None or game_object_id is None:
            continue
        if key not in sprites:
            sprites[key] = _load_sprite(env, key)
        sprite = sprites[key]
        if sprite is None:
            continue
        images[game_object_id] = ImageNode(
            game_object_id=game_object_id,
            sprite=sprite,
            enabled=bool(data.get("m_Enabled", 1)),
            sliced=data.get("m_Type") == 1,
            color=_color(data.get("m_Color")),
        )

    for obj in env.objects:
        if obj.type == ClassIDType.Sprite:
            key = (obj.assets_file.name.lower(), obj.path_id)
            if key not in sprites:
                sprites[key] = _load_sprite(env, key)

    bundle_cabs = {file.name.lower() for file in env.assets}
    bundle_sprites = [sprite for (cab, _), sprite in sprites.items() if sprite and cab in bundle_cabs]
    return rects, images, bundle_sprites


def _node_path(node_id: int, rects: dict[int, RectNode]) -> str:
    parts: list[str] = []
    current_id: int | None = node_id
    while current_id in rects:
        node = rects[current_id]
        if node.name:
            parts.append(node.name)
        current_id = node.parent_id
    return "/".join(reversed(parts))


def _subtree_ids(root_id: int, rects: dict[int, RectNode]) -> list[int]:
    result: list[int] = []

    def visit(node_id: int) -> None:
        if node_id not in rects:
            return
        result.append(node_id)
        for child_id in rects[node_id].child_ids:
            visit(child_id)

    visit(root_id)
    return result


def _has_large_background(root_id: int, rects: dict[int, RectNode], images: dict[int, ImageNode]) -> bool:
    for node_id in _subtree_ids(root_id, rects):
        image = images.get(rects[node_id].game_object_id)
        if image and image.sprite.is_background:
            return True
    return False


def _is_background_root(node_id: int, rects: dict[int, RectNode]) -> bool:
    name = rects[node_id].name.lower()
    path = _node_path(node_id, rects).lower()
    if name in {"bg", "imgbg", "bgroot"}:
        return True
    if "----bg----" in name or "---bg---" in name:
        return True
    return "/bg" in path or "bgroot" in path


def _find_roots(rects: dict[int, RectNode], images: dict[int, ImageNode]) -> list[int]:
    candidates = [
        node_id
        for node_id in rects
        if _is_background_root(node_id, rects) and _has_large_background(node_id, rects, images)
    ]
    candidate_set = set(candidates)
    roots: list[int] = []
    for node_id in candidates:
        parent_id = rects[node_id].parent_id
        has_candidate_parent = False
        while parent_id in rects:
            if parent_id in candidate_set:
                has_candidate_parent = True
                break
            parent_id = rects[parent_id].parent_id
        if not has_candidate_parent:
            roots.append(node_id)
    return sorted(roots, key=lambda root_id: _node_path(root_id, rects))


def _root_size(root: RectNode) -> tuple[float, float]:
    width, height = _vec2(root.rect.get("m_SizeDelta", {}), *ROOT_SIZE)
    if width < 1000 or height < 700:
        return ROOT_SIZE
    return width, height


def _child_layout(parent_layout: Layout, child: RectNode) -> Layout:
    anchor_min_x, anchor_min_y = _vec2(child.rect.get("m_AnchorMin", {}), 0.5, 0.5)
    anchor_max_x, anchor_max_y = _vec2(child.rect.get("m_AnchorMax", {}), 0.5, 0.5)
    anchored_x, anchored_y = _vec2(child.rect.get("m_AnchoredPosition", {}))
    size_delta_x, size_delta_y = _vec2(child.rect.get("m_SizeDelta", {}))
    pivot_x, pivot_y = _vec2(child.rect.get("m_Pivot", {}), 0.5, 0.5)
    scale_x, scale_y = _vec2(child.rect.get("m_LocalScale", {}), 1.0, 1.0)

    width = parent_layout.width * (anchor_max_x - anchor_min_x) + size_delta_x
    height = parent_layout.height * (anchor_max_y - anchor_min_y) + size_delta_y
    width = abs(width * scale_x)
    height = abs(height * scale_y)

    parent_pivot_x = parent_layout.left + parent_layout.pivot_x * parent_layout.width
    parent_pivot_y = parent_layout.top + (1.0 - parent_layout.pivot_y) * parent_layout.height
    anchor_ref_x = ((anchor_min_x + anchor_max_x) / 2.0 - parent_layout.pivot_x) * parent_layout.width
    anchor_ref_y = ((anchor_min_y + anchor_max_y) / 2.0 - parent_layout.pivot_y) * parent_layout.height
    child_pivot_x = parent_pivot_x + anchor_ref_x + anchored_x
    child_pivot_y = parent_pivot_y - anchor_ref_y - anchored_y

    return Layout(
        left=child_pivot_x - pivot_x * width,
        top=child_pivot_y - (1.0 - pivot_y) * height,
        width=width,
        height=height,
        pivot_x=pivot_x,
        pivot_y=pivot_y,
    )


def _all_layouts(rects: dict[int, RectNode]) -> dict[int, Layout]:
    layouts: dict[int, Layout] = {}

    def visit(node_id: int, layout: Layout) -> None:
        layouts[node_id] = layout
        for child_id in rects[node_id].child_ids:
            if child_id in rects:
                visit(child_id, _child_layout(layout, rects[child_id]))

    for node_id, node in rects.items():
        if node.parent_id not in rects:
            width, height = _root_size(node)
            pivot_x, pivot_y = _vec2(node.rect.get("m_Pivot", {}), 0.5, 0.5)
            visit(node_id, Layout(0.0, 0.0, width, height, pivot_x, pivot_y))
    return layouts


def _tint(image: Image.Image, color: tuple[float, float, float, float]) -> Image.Image:
    r, g, b, a = color
    if (r, g, b, a) == (1.0, 1.0, 1.0, 1.0):
        return image
    tinted = image.copy()
    red, green, blue, alpha = tinted.split()
    red = red.point(lambda value: round(value * r))
    green = green.point(lambda value: round(value * g))
    blue = blue.point(lambda value: round(value * b))
    alpha = alpha.point(lambda value: round(value * a))
    return Image.merge("RGBA", (red, green, blue, alpha))


def _draw_node(
    canvas: Image.Image,
    node_id: int,
    layout: Layout,
    rects: dict[int, RectNode],
    images: dict[int, ImageNode],
    drawn: set[str],
) -> None:
    node = rects[node_id]
    image_node = images.get(node.game_object_id)
    if (
        image_node
        and image_node.enabled
        and not image_node.sliced
        and not (image_node.sprite.name.lower().startswith("fx_") and image_node.sprite.grayscale)
        and layout.width > 1
        and layout.height > 1
    ):
        width = max(1, round(layout.width))
        height = max(1, round(layout.height))
        image = image_node.sprite.image.resize((width, height), Image.Resampling.LANCZOS)
        image = _tint(image, image_node.color)
        _, max_alpha = image.getchannel("A").getextrema()
        if max_alpha >= 200:
            canvas.alpha_composite(image, (round(layout.left), round(layout.top)))
            drawn.add(image_node.sprite.name)
    for child_id in node.child_ids:
        if child_id in rects and rects[child_id].active:
            _draw_node(canvas, child_id, _child_layout(layout, rects[child_id]), rects, images, drawn)


def _render(
    node_id: int,
    width: float,
    height: float,
    rects: dict[int, RectNode],
    images: dict[int, ImageNode],
) -> tuple[Image.Image, frozenset[str]]:
    canvas = Image.new("RGBA", (round(width), round(height)), (0, 0, 0, 0))
    pivot_x, pivot_y = _vec2(rects[node_id].rect.get("m_Pivot", {}), 0.5, 0.5)
    drawn: set[str] = set()
    _draw_node(canvas, node_id, Layout(0.0, 0.0, width, height, pivot_x, pivot_y), rects, images, drawn)
    return canvas, frozenset(drawn)


def _export_bundle(bundle: Path, output_dir: Path) -> list[Path]:
    rects, images, bundle_sprites = _read_bundle(bundle)
    written: list[Path] = []
    seen: set[frozenset[str]] = set()

    def save(canvas: Image.Image, drawn: frozenset[str], name: str) -> None:
        if not drawn or drawn in seen or not canvas.getbbox():
            return
        seen.add(drawn)
        output_path = output_dir / f"{_safe_name(name)}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path)
        written.append(output_path)

    for root_id in _find_roots(rects, images):
        width, height = _root_size(rects[root_id])
        if width * height >= MIN_OUTPUT_AREA:
            save(*_render(root_id, width, height, rects, images), _node_path(root_id, rects))

    drawn_sprites = set().union(*seen)
    layouts = _all_layouts(rects)
    for node_id in sorted(rects, key=lambda node_id: _node_path(node_id, rects)):
        image_node = images.get(rects[node_id].game_object_id)
        if not image_node or image_node.sprite.name in drawn_sprites or not image_node.sprite.is_art:
            continue
        layout = layouts.get(node_id)
        if layout is None or layout.width < 1 or layout.height < 1:
            continue
        canvas, drawn = _render(node_id, layout.width, layout.height, rects, images)
        drawn_sprites.update(drawn)
        if image_node.sprite.name in drawn:
            save(image_node.sprite.image, frozenset({image_node.sprite.name}), image_node.sprite.name)
        save(canvas, drawn, _node_path(node_id, rects))

    referenced = {image_node.sprite.name for image_node in images.values()}
    for sprite in sorted(bundle_sprites, key=lambda sprite: sprite.name):
        if sprite.name not in referenced and sprite.is_background:
            save(sprite.image, frozenset({sprite.name}), sprite.name)
    return written


def _old_asset_bundles() -> list[Path]:
    """Bundles from a manually curated archive of old .unity3d files, if one exists."""
    old_assets_dir = data_dir.parent / "OldAssets"
    if not old_assets_dir.is_dir():
        print(f"WARNING: {old_assets_dir} not found; event images that only exist in "
              f"removed game content will be skipped.")
        return []
    return list(old_assets_dir.glob("*.unity3d"))


@cache
def _activity_bundles() -> list[Path]:
    bundles = [
        bundle
        for bundle in get_unity3d_files() + _old_asset_bundles()
        if (bundle.name.startswith("ui_activity") or bundle.name.startswith("ui_play_"))
        and bundle.suffix == ".unity3d"
        and not bundle.name.endswith(".en.unity3d")
    ]
    return sorted(bundles, key=lambda path: path.name)


def export_event_images(overwrite: bool = False) -> list[Path]:
    output_dir = Path("assets") / "event_bgs"
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    bundles = _activity_bundles()
    print(f"Processing {len(bundles)} ui_activity bundles...")
    for index, bundle in enumerate(bundles, start=1):
        bundle_output_dir = output_dir / bundle.stem
        marker_path = bundle_output_dir / ".processed"
        if not overwrite and marker_path.exists():
            written.extend(sorted(bundle_output_dir.glob("*.png")))
            print(f"[{index}/{len(bundles)}] {bundle.name}: skipped (already processed, use --overwrite to regenerate)")
            continue
        for stale in bundle_output_dir.glob("*.png"):
            stale.unlink()
        try:
            bundle_written = _export_bundle(bundle, bundle_output_dir)
            written.extend(bundle_written)
            if bundle_written:
                print(f"[{index}/{len(bundles)}] {bundle.name}: wrote {len(bundle_written)} images")
            else:
                print(f"[{index}/{len(bundles)}] {bundle.name}: no large backgrounds found")
            bundle_output_dir.mkdir(parents=True, exist_ok=True)
            marker_path.touch()
        except Exception as e:
            print(f"WARNING: Failed to process {bundle.name}: {e}")
    print(f"Wrote {len(written)} images to {output_dir}")
    return written


def _parse_args() -> Any:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true", help="Re-export even if output already exists")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    export_event_images(overwrite=args.overwrite)


if __name__ == "__main__":
    main()
