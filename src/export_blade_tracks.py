"""Bake sword endpoints from the same engine-frame poses as authored contacts."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from export_collision_track_data import SKELETON, apply_transform, export_clip


ENDPOINTS = ("base", "steel_tip")
MAX_DUMMY_ERROR_CM = 0.002


def hand_chain():
    bones = json.loads(SKELETON.read_text(encoding="utf-8-sig"))["bones"]
    index = next(i for i, bone in enumerate(bones) if bone["name"].lower() == "hand_r")
    chain = []
    while index >= 0:
        chain.append(bones[index])
        index = bones[index]["parent"]
    return chain


def generate(profile):
    """Validate the source curves and return only additive blade track data."""
    chain = hand_chain()
    attachment = profile["attachments"]["r"]
    assert attachment["bone"] == "hand_r", "Sword attachment is not bound to hand_r"
    volume = profile["art"]["hit_volume"]
    assert volume["space"] == "sword_local_cm"
    local_points = {name: tuple(volume[name][axis] for axis in ("X", "Y", "Z")) for name in ENDPOINTS}
    points = {name: apply_transform(attachment, point) for name, point in local_points.items()}
    points.update({
        name: apply_transform(attachment, (100 * x, -100 * y, 100 * z))
        for name, (x, y, z) in profile["weapon_dummies"].items()
    })
    expected_length = math.dist(local_points["base"], local_points["steel_tip"])
    output, checks = {}, []
    for name, clip in profile["clips"].items():
        if not clip["hits"]:
            continue
        exported = export_clip(name, chain, points)
        assert exported["animation_sha256"] == clip["animation_sha256"], f"{name}: animation SHA mismatch"
        assert exported["frames"] == clip["frames"] and exported["fps"] == clip["fps"], f"{name}: sample grid mismatch"
        tracks = exported["dummy_tracks"]
        max_error = max(
            math.dist(point, previous)
            for dummy in profile["weapon_dummies"]
            for point, previous in zip(tracks[dummy], clip["dummy_tracks"][dummy], strict=True)
        )
        assert max_error < MAX_DUMMY_ERROR_CM, f"{name}: authored dummy drift {max_error} cm"
        lengths = [math.dist(base, tip) for base, tip in zip(tracks["base"], tracks["steel_tip"], strict=True)]
        assert all(abs(length - expected_length) < MAX_DUMMY_ERROR_CM for length in lengths), f"{name}: blade length drift"
        output[name] = {endpoint: [list(point) for point in tracks[endpoint]] for endpoint in ENDPOINTS}
        checks.append({"clip": name, "frames": clip["frames"], "max_dummy_error_cm": max_error,
                       "min_blade_cm": min(lengths), "max_blade_cm": max(lengths)})
    return output, checks


def without_blade_tracks(profile):
    result = copy.deepcopy(profile)
    for clip in result["clips"].values():
        clip.pop("blade_tracks", None)
    return result


def update(path):
    original_bytes = path.read_bytes()
    original = json.loads(original_bytes.decode("utf-8-sig"))
    tracks, checks = generate(original)
    updated = copy.deepcopy(original)
    for name, curves in tracks.items():
        updated["clips"][name]["blade_tracks"] = curves
    assert without_blade_tracks(updated) == without_blade_tracks(original), "Non-blade profile fields changed"
    encoded = json.dumps(updated, separators=(",", ":")).encode("utf-8")
    # Finish all validation before touching the requested profile.
    path.write_bytes(encoded)
    assert json.loads(path.read_text(encoding="utf-8")) == updated
    return {"profile": str(path), "clips": len(checks), "bytes_before": len(original_bytes),
            "bytes_after": len(encoded), "bytes_added": len(encoded) - len(original_bytes),
            "sha256_before": hashlib.sha256(original_bytes).hexdigest(), "sha256_after": hashlib.sha256(encoded).hexdigest(),
            "max_dummy_error_cm": max(check["max_dummy_error_cm"] for check in checks),
            "min_blade_cm": min(check["min_blade_cm"] for check in checks),
            "max_blade_cm": max(check["max_blade_cm"] for check in checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.profiles:
        print(json.dumps(update(path), separators=(",", ":")))


if __name__ == "__main__":
    main()
