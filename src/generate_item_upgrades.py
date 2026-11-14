"""Export the current PBZ Tang upgrade economy without inventing costs or levels.

Only reads the native extraction and writes mod-owned reports/runtime JSON.
No game, save, install, or original asset is modified.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/current-tang-row.json"


def build():
    raw = SOURCE.read_bytes()
    row = json.loads(raw.decode("utf-8-sig"))
    assert row["ItemId"] == "Tang", "Unexpected native source item"
    native = row["WeaponUpLevelDatas"]
    assert len(native) == 59, "Native upgrade count changed; review level convention"
    levels = []
    materials_total = {}
    for index, value in enumerate(native):
        materials = value["Materials"]
        assert len({entry["Key"] for entry in materials}) == len(materials)
        for entry in materials:
            assert isinstance(entry["Value"], int) and entry["Value"] > 0
            materials_total[entry["Key"]] = materials_total.get(entry["Key"], 0) + entry["Value"]
        multiplier = value["AttackMultipliers"]
        assert abs(multiplier - (1.1 + index / 10)) < 0.0001
        levels.append({
            "array_index": index + 1,
            "from_level": index + 1,
            "to_level": index + 2,
            "Materials": materials,
            "ConsumeDust": value["ConsumeDust"],
            "bNeedInJHSY": value["bNeedInJHSY"],
            "AttackMultipliers": multiplier,
            "removed_foreign_effects": {
                key: len(value[key]) for key in
                ("GEDatas", "SnapSoulGEDatas", "PersistentGEDatas", "GEUIDataArray")
            },
        })
    soul = row["WeaponSnapSoulData"]
    return {
        "schema": "rka-item-upgrades-1",
        "id": "RKA_RingedKnight",
        "source": {
            "row": "黑伤", "item": "Tang", "file": "reports/current-tang-row.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "game_build": "26367565", "executable_version": "CL-302256_JKS-17280",
        },
        "level_convention": {
            "base_level": 1, "base_multiplier": 1.0, "max_level": 60,
            "evidence": "59 sequential native entries; ResetAllWeaponsToLevel1 exists",
            "runtime_verified": False,
        },
        "moves_available_from_base": [
            "light_chain", "heavy_1_tap", "heavy_2_tap", "heavy_1_charge",
            "heavy_2_charge", "shield_guard", "ember", "rope_black_firebomb",
            "first_light_guard_cancel_cosmetic_only",
        ],
        "progression": levels,
        "totals": {"ConsumeDust": sum(v["ConsumeDust"] for v in native),
                   "Materials": materials_total},
        "snap_soul": {
            "name": "环印骑士直剑·余烬",
            "Materials": soul["Materials"], "ConsumeDust": soul["ConsumeDust"],
            "bNeedInJHSY": soul["bNeedInJHSY"],
            "configuration": "mod_owned_variant_required",
            "preserve_item_id": True, "moves": "all_base_moves_retained",
            "foreign_effects_removed": True,
            "attack_multiplier": "native GetWeaponAttackMultipliers remains authoritative",
            "runtime_verified": False,
        },
        "safety": {"original_rows_modified": False, "grant_or_upgrade_called": False,
                   "foreign_tang_abilities_retained": False,
                   "cosmetic_cancel_adds_damage": False},
    }


def main():
    result = build()
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    destinations = [ROOT / "reports/item-upgrades.json",
                    ROOT / "src/runtime/RingedKnightArsenal/Scripts/item-upgrades.json"]
    for destination in destinations:
        destination.write_text(output, encoding="utf-8")
    print(f"Exported {len(result['progression'])} native upgrade entries; original economy retained.")


if __name__ == "__main__":
    main()
