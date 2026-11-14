"""Export collision sidecars directly from the v3 engine-frame animation data."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANIMATIONS = ROOT / "build/animations"
SKELETON = ROOT / (
    "extract/pbz/ProjectPBZ/Plugins/HuaShira/Content/Characters/Hero/Hero_Hun/"
    "Hun_Skin_Skeleton.Hun_Skin_Skeleton.skel.json"
)
PROFILE = ROOT / "src/runtime/RingedKnightArsenal/Scripts/combat-profile.json"


def apply_transform(transform, point):
    x, y, z = (value * scale for value, scale in zip(point, transform["s"], strict=True))
    qx, qy, qz, qw = transform["q"]
    tx, ty, tz = transform["t"]
    # Quaternion rotation: point + w * (2 * q.xyz × point) + q.xyz × (2 * q.xyz × point).
    u, v, w = 2 * (qy * z - qz * y), 2 * (qz * x - qx * z), 2 * (qx * y - qy * x)
    return (
        x + qw * u + qy * w - qz * v + tx,
        y + qw * v + qz * u - qx * w + ty,
        z + qw * w + qx * v - qy * u + tz,
    )


def export_clip(name, chain, weapon_points):
    data = (ANIMATIONS / f"{name}.json").read_bytes()
    clip = json.loads(data)
    assert clip["retarget_revision"] == "gltf-basis-anatomical-v3"
    tracks = {track["name"].lower(): track["keys"] for track in clip["tracks"]}
    frames = clip["frames"]
    curves = {name: [] for name in weapon_points}
    for frame in range(frames):
        for dummy, point in weapon_points.items():
            for bone in chain:
                track = tracks.get(bone["name"].lower())
                point = apply_transform(track[frame] if track else bone, point)
            assert all(map(math.isfinite, point))
            curves[dummy].append(point)
    return {
        "frames": frames,
        "fps": clip["fps"],
        "animation_sha256": hashlib.sha256(data).hexdigest(),
        "dummy_tracks": curves,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("clips", nargs="+")
    args = parser.parse_args()

    skeleton = json.loads(SKELETON.read_text())["bones"]
    profile = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    index = next(i for i, bone in enumerate(skeleton) if bone["name"].lower() == "hand_r")
    chain = []
    while index >= 0:
        chain.append(skeleton[index])
        index = skeleton[index]["parent"]

    # Source dummy positions are reflected-Y Blender meters. The baked pose
    # and native hand attachment use Unreal centimeters, with root motion removed.
    attachment = profile["attachments"]["r"]
    weapon_points = {
        name: apply_transform(attachment, (100 * x, -100 * y, 100 * z))
        for name, (x, y, z) in profile["weapon_dummies"].items()
    }
    baseline = export_clip("RKSS_Ember", chain, weapon_points)
    previous = profile["clips"]["RKSS_Ember"]["dummy_tracks"]
    max_error_cm = max(
        math.dist(point, expected)
        for name, curve in baseline["dummy_tracks"].items()
        for point, expected in zip(curve, previous[name], strict=True)
    )
    assert max_error_cm < 0.002, f"Offline transform disagrees with Blender: {max_error_cm:.6f} cm"
    output = {name: export_clip(name, chain, weapon_points) for name in args.clips}
    args.output.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(f"COLLISION_TRACKS_READY {len(output)} max_reference_error_cm={max_error_cm:.8f}")


if __name__ == "__main__":
    main()
