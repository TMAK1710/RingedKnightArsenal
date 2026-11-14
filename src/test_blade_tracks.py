"""Check baked blade endpoints against source animation poses without Unreal."""

import json
import math
from pathlib import Path

from export_blade_tracks import ENDPOINTS, MAX_DUMMY_ERROR_CM, generate


ROOT = Path(__file__).resolve().parents[1]
PROFILES = (ROOT / "src/runtime/RingedKnightArsenal/Scripts/combat-profile.json", ROOT / "build/combat-profile.json")


def main():
    count = 0
    for path in PROFILES:
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
        expected, checks = generate(profile)
        for name, curves in expected.items():
            clip = profile["clips"][name]
            actual = clip["blade_tracks"]
            assert set(actual) == set(ENDPOINTS), f"{name}: unexpected blade endpoints"
            for endpoint in ENDPOINTS:
                assert len(actual[endpoint]) == clip["frames"]
                assert all(len(point) == 3 and all(math.isfinite(value) for value in point) for point in actual[endpoint])
                assert max(math.dist(a, b) for a, b in zip(actual[endpoint], curves[endpoint], strict=True)) < 1e-9
            assert all(abs(math.dist(base, tip) - 81.028) < MAX_DUMMY_ERROR_CM
                       for base, tip in zip(actual["base"], actual["steel_tip"], strict=True))
            count += 1
        assert len(expected) == sum(bool(clip["hits"]) for clip in profile["clips"].values())
        print(f"PASS {path.relative_to(ROOT)}: {len(checks)} hit clips; max authored dummy error "
              f"{max(check['max_dummy_error_cm'] for check in checks):.9f} cm; blade length 81.028 +/- .002 cm")
    print(f"PASS {count} clip/profile validations (source SHA, full dummy curves, blade endpoints and length)")


if __name__ == "__main__":
    main()
