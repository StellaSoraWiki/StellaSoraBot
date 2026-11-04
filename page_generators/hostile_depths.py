import json
import re
import tempfile
from pathlib import Path
from typing import Any

import UnityPy
from PIL import Image
from UnityPy.enums import ClassIDType

from unpack.unpack_utils import get_unity3d_files
from utils.data_utils import assets_root, autoload
from utils.skill_utils import format_desc, parse_params
from utils.upload_utils import UploadRequest, process_uploads
from utils.wiki_utils import save_json_page

RARITY_NAMES = {
    1: "White",
    2: "Green",
    3: "Blue",
    4: "Purple",
    5: "Gold",
}

BLESSING_RARITY_NAMES = {
    3: "Gold",
    4: "Silver",
    5: "Bronze",
}

TRAIT_CATEGORIES = {
    1: "Squad",
    2: "Build",
}


def _process(text: str) -> str:
    text = re.sub(r"<sprite[^>]*>", "", text)
    text = re.sub(r"<color=[^>]*></color>", "", text)
    text = re.sub(r"<color=(#[0-9A-Fa-f]+)>(.*?)</color>", r'<span style="color:\1">\2</span>', text)
    text = re.sub(r"##([^#]+)#\d+#", r"\1", text)
    return text.replace("\n", "<br/>").strip()


def _blessing_icon(card: dict[str, Any]) -> str:
    return "THD blessing " + card["Icon"].removeprefix("Soldier_00_BuffCard_").replace("_", " ") + ".png"


def _trait_icon(group: dict[str, Any]) -> str:
    return f"THD trait {group['Name']}.png"


def _member_icon(skin: dict[str, Any]) -> str:
    return f"THD member {skin['Name']}.png"


def _untrim_sprite(source: Path) -> Path:
    data = json.load(open(source.with_suffix(".json"), encoding="utf-8"))
    frame, rect = data["m_Rect"], data["m_RD"]["textureRect"]
    image = Image.open(source).convert("RGBA")
    canvas = Image.new("RGBA", (int(frame["width"]), int(frame["height"])))
    canvas.paste(image, (round(rect["x"]), int(frame["height"]) - round(rect["y"]) - image.height))
    out = Path(tempfile.gettempdir()) / source.name
    canvas.save(out)
    return out


def _trait_card() -> Path:
    bundle = next(f for f in get_unity3d_files() if f.name == "ui_soldier.unity3d")
    names = {"db_soldier_handbook_strategycard", "zs_soldier_handbook_strategycard", "zs_soldier_handbook_select_star1"}
    sprites: dict[str, Image.Image] = {}
    for obj in UnityPy.load(str(bundle)).objects:
        if obj.type == ClassIDType.Sprite and (sprite := obj.read()).m_Name in names:
            sprites[sprite.m_Name] = sprite.image.convert("RGBA")
    card = sprites["db_soldier_handbook_strategycard"]
    circle = sprites["zs_soldier_handbook_strategycard"].resize((284, 284), Image.LANCZOS)
    card.alpha_composite(circle, ((card.width - circle.width) // 2, 63))
    star_mask = sprites["zs_soldier_handbook_select_star1"].getchannel("A")
    star = Image.new("RGBA", star_mask.size, (60, 71, 88, 255))
    star.putalpha(star_mask)
    card.alpha_composite(star.resize((66, 66), Image.LANCZOS), (27, 39))
    card.alpha_composite(star.resize((42, 42), Image.LANCZOS), (270, 292))
    out = Path(tempfile.gettempdir()) / "THD trait card.png"
    card.save(out)
    return out


def _skill(skill_id: int, max_level: int) -> dict[str, str]:
    skill = autoload("Skill")[str(skill_id)]
    desc = re.sub(r"&Param(\d+)&", lambda m: "{" + m.group(1) + "}", skill["Desc"])
    params = parse_params(skill, desc)
    desc = format_desc(desc, params, level=-1, max_level=max_level)
    return {
        "name": skill["Title"],
        "description": _process(desc),
    }


def get_blessings() -> list[dict[str, Any]]:
    return [
        {
            "id": card["Id"],
            "name": card["Name"],
            "rarity": BLESSING_RARITY_NAMES[card["Rarity"]],
            "icon": _blessing_icon(card),
            "description": _process(card["Desc"]),
        }
        for card in sorted(autoload("SoldierStrategyCard").values(), key=lambda v: v["Id"])
    ]


def get_traits() -> dict[str, dict[str, Any]]:
    skins = autoload("SoldierSkin")
    levels: dict[int, list[dict[str, Any]]] = {}
    for partner in sorted(autoload("SoldierPartner").values(), key=lambda v: v["Id"]):
        levels.setdefault(partner["PartnerType"], []).append({
            "count": partner["Num"],
            "description": _process(partner["Desc"]),
        })
    result: dict[str, dict[str, Any]] = {}
    for group in sorted(autoload("SoldierPartnerGroup").values(), key=lambda v: v["Id"]):
        result[group["Name"]] = {
            "id": group["PartnerType"],
            "name": group["Name"],
            "category": TRAIT_CATEGORIES[group["PartnerCatalogue"]],
            "icon": _trait_icon(group),
            "description": _process(group["Desc"]),
            "levels": levels.get(group["PartnerType"], []),
            "members": [skins[str(char_id)]["Name"] for char_id in group["ChessCharacterIds"]],
        }
    return result


def get_members() -> dict[str, dict[str, Any]]:
    skins = autoload("SoldierSkin")
    chess_types = {v.get("ChessType", 0): v["Name"] for v in autoload("SoldierChessType").values()}
    traits = {v["PartnerType"]: v["Name"] for v in autoload("SoldierPartnerGroup").values()}
    potentials = autoload("SoldierPotential")
    result: dict[str, dict[str, Any]] = {}
    for char in sorted(autoload("SoldierCharacter").values(), key=lambda v: v["Id"]):
        if not char.get("BoardChess"):
            continue
        name = skins[str(char["Skin"])]["Name"]
        result[name] = {
            "id": char["Id"],
            "name": name,
            "rarity": RARITY_NAMES[char["Rarity"]],
            "cost": char["Cost"],
            "position": chess_types[char.get("Type", 0)],
            "traits": [traits[t] for t in char["PartnerType"]],
            "offense_skill": _skill(char["Skill"], char["MaxStar"]),
            "assist_skill": _skill(char["Support"], char["MaxStar"]),
            "potentials": [
                {
                    "star": star,
                    "name": potentials[str(potential_id)]["Name"],
                    "description": _process(potentials[str(potential_id)]["Des"]),
                }
                for star in range(1, 5)
                for potential_id in char.get(f"Potential{star}", [])
            ],
        }
    return result


def upload_icons() -> None:
    requests: dict[str, UploadRequest] = {}
    for card in autoload("SoldierStrategyCard").values():
        requests[_blessing_icon(card)] = UploadRequest(
            assets_root / "icon" / "soldierbuffcard" / (card["Icon"].lower() + ".png"),
            _blessing_icon(card),
            "[[Category:Through Hostile Depths blessing icons]]",
            "Batch upload Through Hostile Depths blessing icons")
    for group in autoload("SoldierPartnerGroup").values():
        requests[_trait_icon(group)] = UploadRequest(
            assets_root / "icon" / "soldierpartner" / (group["Icon"].lower() + "_l.png"),
            _trait_icon(group),
            "[[Category:Through Hostile Depths trait icons]]",
            "Batch upload Through Hostile Depths trait icons")
    skins = autoload("SoldierSkin")
    for char in autoload("SoldierCharacter").values():
        if not char.get("BoardChess"):
            continue
        skin = skins[str(char["Skin"])]
        requests[_member_icon(skin)] = UploadRequest(
            lambda path=assets_root / (skin["Icon"].lower() + "_l.png"): _untrim_sprite(path),
            _member_icon(skin),
            "[[Category:Through Hostile Depths member icons]]",
            "Batch upload Through Hostile Depths member icons")
    for rarity, name in RARITY_NAMES.items():
        requests[f"THD rarity {name}.png"] = UploadRequest(
            assets_root / "icon" / "soldierothericon" / f"chessquality_0{rarity}_l.png",
            f"THD rarity {name}.png",
            "[[Category:Through Hostile Depths images]]",
            "Batch upload Through Hostile Depths rarity frames")
    for rarity, name in BLESSING_RARITY_NAMES.items():
        card = assets_root / "icon" / "soldierothericon" / f"strategycardquality_0{6 - rarity}_m.png"
        requests[f"THD blessing card {name}.png"] = UploadRequest(
            lambda path=card: _untrim_sprite(path),
            f"THD blessing card {name}.png",
            "[[Category:Through Hostile Depths images]]",
            "Batch upload Through Hostile Depths blessing cards")
    requests["THD trait card.png"] = UploadRequest(
        _trait_card,
        "THD trait card.png",
        "[[Category:Through Hostile Depths images]]",
        "Upload Through Hostile Depths trait card")
    process_uploads(list(requests.values()))


def main() -> None:
    upload_icons()
    save_json_page("Module:THD/blessings.json", get_blessings())
    save_json_page("Module:THD/members.json", get_members())
    save_json_page("Module:THD/traits.json", get_traits())


if __name__ == "__main__":
    main()
