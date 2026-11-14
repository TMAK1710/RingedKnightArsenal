"""Offline coverage of baked blade sweeps; no native damage or live-game claims."""

import hashlib
import json
import math
import sys
import time as clock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/lua-python"))
from lupa.lua54 import LuaRuntime

SCRIPTS = ROOT / "src/runtime/RingedKnightArsenal/Scripts"
MODULE = SCRIPTS / "ArtFlameTrace.lua"
PROFILE = json.loads((SCRIPTS / "combat-profile.json").read_text(encoding="utf-8-sig"))
LUA = LuaRuntime(unpack_returned_tuples=True)
TRACE = LUA.execute(MODULE.read_text(encoding="utf-8"))
LUA.globals().Trace = TRACE


def to_lua(value):
    if isinstance(value, dict):
        return LUA.table_from({key: to_lua(item) for key, item in value.items()})
    if isinstance(value, list):
        return LUA.table_from([to_lua(item) for item in value])
    return value


def point(value):
    return tuple(value[axis] for axis in ("X", "Y", "Z"))


def pose(clip, time, length):
    frame = min(clip["frames"] - 1, max(0, time * clip["fps"]))
    lo, fraction = math.floor(frame), frame % 1
    hi = min(clip["frames"] - 1, lo + 1)
    def sample(track):
        return tuple(a + (b - a) * fraction for a, b in zip(track[lo], track[hi], strict=True))
    base = sample(clip["blade_tracks"]["base"])
    steel = sample(clip["blade_tracks"]["steel_tip"])
    size = math.dist(base, steel)
    return base, tuple(a + length * (b - a) / size for a, b in zip(base, steel, strict=True))


def distance_to_segment(value, start, finish):
    axis = tuple(b - a for a, b in zip(start, finish, strict=True))
    t = max(0, min(1, sum((p - a) * d for p, a, d in zip(value, start, axis, strict=True)) / sum(d * d for d in axis)))
    return math.dist(value, tuple(a + t * d for a, d in zip(start, axis, strict=True)))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def validate(clip, first, last, length, budget=64):
    outputs = TRACE.swept_segments(to_lua(clip), first, last, length, 24, budget)
    segments = [outputs[i] for i in range(1, len(outputs) + 1)]
    assert 1 <= len(segments) <= budget <= 64
    cursor = first
    for segment in segments:
        assert abs(segment.from_time - cursor) < 1e-8
        assert first - 1e-8 <= segment.from_time <= segment.to_time <= last + 1e-8
        assert segment.space == "mesh_local_cm"
        start, finish = point(segment.start), point(segment.finish)
        assert abs(math.dist(start, finish) - length) < 1e-8
        assert segment.radius_cm >= 24
        expected_start, expected_finish = pose(clip, segment.time, length)
        assert math.dist(start, expected_start) < 1e-8 and math.dist(finish, expected_finish) < 1e-8
        # Test a much denser independent time grid than the 60 Hz source curves.
        samples = max(2, math.ceil((segment.to_time - segment.from_time) * 6000))
        for index in range(samples + 1):
            time = segment.from_time + (segment.to_time - segment.from_time) * index / samples
            base, tip = pose(clip, time, length)
            # Endpoint balls enclose the convex capsule along the entire sword.
            assert max(distance_to_segment(base, start, finish), distance_to_segment(tip, start, finish)) + 24 <= segment.radius_cm + 1e-7
            if index % max(1, samples // 12) == 0:
                axis = tuple((b - a) / length for a, b in zip(base, tip, strict=True))
                side = cross(axis, (0, 0, 1) if abs(axis[2]) < .9 else (1, 0, 0))
                norm = math.sqrt(sum(value * value for value in side))
                side = tuple(value / norm for value in side)
                up = cross(axis, side)
                for fraction in (0, .25, .5, .75, 1):
                    center = tuple(a + (b - a) * fraction for a, b in zip(base, tip, strict=True))
                    for direction in (side, up, tuple(-v for v in side), tuple(-v for v in up)):
                        surface = tuple(a + 24 * d for a, d in zip(center, direction, strict=True))
                        assert distance_to_segment(surface, start, finish) <= segment.radius_cm + 1e-7
                for center, sign in ((base, -1), (tip, 1)):
                    cap = tuple(a + sign * 24 * d for a, d in zip(center, axis, strict=True))
                    assert distance_to_segment(cap, start, finish) <= segment.radius_cm + 1e-7
        cursor = segment.to_time
    assert abs(cursor - last) < 1e-8
    return len(segments), max(segment.inflation_cm for segment in segments)


def percentile(values, fraction):
    values = sorted(values)
    return values[int((len(values) - 1) * fraction)]


def distributions():
    measured = []
    for dt in (1 / 60, 1 / 30, .1):
        radii, counts, timings = [], [], []
        worst = None
        for name, clip in PROFILE["clips"].items():
            if not clip["hits"]:
                continue
            length = 362.056 if name.startswith("RKSS_Ember") else 162.056
            converted = to_lua(clip)
            for hit in clip["hits"]:
                first, last = hit["start"], min(hit["finish"], clip["duration"])
                for phase in range(16):
                    previous = first - phase / 16 * dt
                    while previous < last - 1e-8:
                        begin, end = max(first, previous), min(last, previous + dt)
                        started = clock.perf_counter()
                        outputs = TRACE.swept_segments(converted, begin, end, length, 24, 64)
                        timings.append((clock.perf_counter() - started) * 1000)
                        counts.append(len(outputs))
                        assert 1 <= len(outputs) <= 64
                        for index in range(1, len(outputs) + 1):
                            segment = outputs[index]
                            radii.append(segment.radius_cm)
                            assert segment.radius_cm <= 48, f"Unsafe radius: {name} {begin}..{end} {segment.radius_cm}"
                            if worst is None or segment.radius_cm > worst["radius_cm"]:
                                worst = {"radius_cm": segment.radius_cm, "clip": name,
                                         "from_time": segment.from_time, "to_time": segment.to_time}
                        previous += dt
        result = {"dt": dt, "phase_count": 16, "events": len(counts), "worst": worst}
        for field, values in (("radius_cm", radii), ("segments", counts), ("geometry_cpu_ms", timings)):
            result[field] = {key: percentile(values, fraction) for key, fraction in (("p50", .5), ("p95", .95), ("max", 1))}
        measured.append(result)
        print(f"PASS {1 / dt:.0f} Hz x 16 phases: radius {result['radius_cm']}; queries {result['segments']}; CPU ms {result['geometry_cpu_ms']}")
    return measured


def main():
    results, maxima = [], []
    steel = math.dist(tuple(PROFILE["art"]["hit_volume"]["base"].values()), tuple(PROFILE["art"]["hit_volume"]["steel_tip"].values()))
    for name, clip in PROFILE["clips"].items():
        if not clip["hits"]:
            continue
        length = (steel + (100 if name.startswith("RKSS_Ember") else 0)) * 2
        clip_max, tick_max = 0, 0
        for hit in clip["hits"]:
            first, last = hit["start"], min(hit["finish"], clip["duration"])
            for budget in (64,):
                _, inflation = validate(clip, first, last, length, budget)
                if budget == 64:
                    clip_max = max(clip_max, inflation)
            for step in (1 / 120, 1 / 60, .033, .1):
                current = first
                while current < last - 1e-8:
                    finish = min(last, current + step)
                    _, inflation = validate(clip, current, finish, length)
                    tick_max = max(tick_max, inflation)
                    current = finish
            outputs = TRACE.swept_segments(to_lua(clip), first, first, length, 24)
            assert len(outputs) == 1 and outputs[1].radius_cm == 24 and outputs[1].inflation_cm == 0
        results.append({"name": name, "pass": True})
        maxima.append({"clip": name, "full_window_max_inflation_cm": clip_max, "up_to_100ms_max_inflation_cm": tick_max})
        print(f"PASS {name}: full-window inflation {clip_max:.3f} cm; <=100ms inflation {tick_max:.3f} cm")

    synthetic = {"fps": 1, "duration": 1, "frames": 2,
                 "blade_tracks": {"base": [[0, 0, 0], [0, 0, 0]], "steel_tip": [[10, 0, 0], [0, 8, 0]]}}
    validate(synthetic, 0, 1, 160)
    results.append({"name": "normalized_arc_and_unequal_steel_lengths_remain_enclosed", "pass": True})
    LUA.globals().C = to_lua(synthetic)
    LUA.execute("""
for _,bad in ipairs({-1,0,65,1.5,0/0,math.huge})do assert(not pcall(Trace.swept_segments,C,0,1,160,24,bad))end
for _,range in ipairs({{-.01,.2},{.5,.4},{0,1.01}})do assert(not pcall(Trace.swept_segments,C,range[1],range[2],160,24,4))end
assert(not pcall(Trace.swept_segments,{fps=60,duration=1,frames=2},0,.1,160,24,4))
local failed,reason=Trace.swept_segments(C,0,1,160,24,1)
assert(failed==nil and reason=='sweep_budget_exhausted','Over-budget sweeps must fail without an oversized capsule')
local fallback=Trace.swept_segments(C,1,1,160,24,1)
assert(#fallback==1 and fallback[1].radius_cm==24,'Single-pose fallback must remain available')
local first=Trace.swept_segments(C,.1,.2,160,24,4)
local other=Trace.swept_segments(C,.8,.9,360,24,4)
local again=Trace.swept_segments(C,.1,.2,160,24,4)
assert(#first==#again and first[1].finish.X==again[1].finish.X)
first[1].start.X=999;assert(C.blade_tracks.base[1][1]==0 and again[1].start.X==0)
""")
    results.append({"name": "invalid_limits_rejected_and_calls_do_not_mutate_or_bridge", "pass": True})
    event_measurements = distributions()
    results.extend({"name": f"all_clips_{1 / entry['dt']:.0f}Hz_16phases_radius_below_48cm", "pass": True} for entry in event_measurements)
    report = {"scope": __doc__, "module_sha256": hashlib.sha256(MODULE.read_bytes()).hexdigest(),
              "query_budget_per_contact": 64, "target_inflation_cm": 12, "maximum_inflation_cm": 24,
              "radius_policy": "return nil, sweep_budget_exhausted if conservative enclosure needs more than 24 cm inflation",
              "cpu_scope": "Pure Lua geometry plus Python call bridge, excludes native collision and full game frame",
              "runtime_verified": False, "cases": results, "measurements": maxima, "event_distributions": event_measurements}
    (ROOT / "reports/offline-blade-sweep-tests.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"BLADE_SWEEP_READY {len(results)} cases PASS")


if __name__ == "__main__":
    main()
