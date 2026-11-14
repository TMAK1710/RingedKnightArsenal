"""UE 5.7 Python commandlet: import the selected DS3 combat one-shots."""

import hashlib
import json
from pathlib import Path
import re
import wave

import unreal


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "reports/ds3-audio-selection.json"
RECEIPT = ROOT / "reports/ds3-audio-import.json"
DESTINATION = "/HuaShira/Mods/RingedKnight/Audio"
ATTENUATION_NAME = "SA_RKA_DS3"
INNER_RADIUS_CM = 250.0
FALLOFF_CM = 1200.0


def load_selection():
    raw = SELECTION.read_bytes()
    assets = json.loads(raw.decode("utf-8-sig"))["assets"]
    if not isinstance(assets, list) or not assets:
        raise ValueError("The DS3 audio selection has no assets.")

    validated = []
    names = {ATTENUATION_NAME.casefold()}
    for asset in assets:
        name = asset["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name):
            raise ValueError(f"Invalid SoundWave name: {name!r}")
        if name.casefold() in names:
            raise ValueError(f"Duplicate sound asset name: {name}")
        names.add(name.casefold())

        source = (ROOT / asset["wav"]).resolve(strict=True)
        if source.drive.casefold() != ROOT.drive.casefold() or source.suffix.casefold() != ".wav":
            raise ValueError(f"Expected a WAV on {ROOT.drive}: {source}")
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != asset["sha256"].casefold():
                raise ValueError(f"Selected WAV changed: {source}")
            stream.seek(0)
            with wave.open(stream, "rb") as wav:
                frames = wav.getnframes()
                sample_rate = wav.getframerate()
                if (wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (1, 2, "NONE"):
                    raise ValueError(f"Expected mono PCM16: {source}")
                if not frames or not sample_rate or len(wav.readframes(frames)) != frames * 2:
                    raise ValueError(f"Empty or truncated WAV: {source}")

        entry = {
            "name": name,
            "wav": str(source),
            "sha256": digest,
            "sample_rate": sample_rate,
            "duration_seconds": frames / sample_rate,
        }
        if "provenance" in asset:
            if not isinstance(asset["provenance"], dict):
                raise ValueError(f"Invalid audio provenance: {name}")
            entry["provenance"] = asset["provenance"]
        validated.append(entry)
    return hashlib.sha256(raw).hexdigest(), validated


def get_attenuation(tools):
    path = f"{DESTINATION}/{ATTENUATION_NAME}.{ATTENUATION_NAME}"
    attenuation = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if attenuation is None:
        attenuation = tools.create_asset(
            ATTENUATION_NAME, DESTINATION, unreal.SoundAttenuation, unreal.SoundAttenuationFactory()
        )
    if not isinstance(attenuation, unreal.SoundAttenuation):
        raise RuntimeError(f"Expected SoundAttenuation at {path}")

    settings = attenuation.get_editor_property("attenuation")
    settings.set_editor_property("attenuate", True)
    settings.set_editor_property("spatialize", True)
    settings.set_editor_property("attenuation_shape", unreal.AttenuationShape.SPHERE)
    settings.set_editor_property("attenuation_shape_extents", unreal.Vector(INNER_RADIUS_CM, 0, 0))
    settings.set_editor_property("falloff_distance", FALLOFF_CM)
    attenuation.set_editor_property("attenuation", settings)
    if not unreal.EditorAssetLibrary.save_loaded_asset(attenuation):
        raise RuntimeError(f"Unable to save {path}")
    return attenuation


def import_wave(tools, attenuation, asset):
    name = asset["name"]
    path = f"{DESTINATION}/{name}.{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        if not isinstance(unreal.load_asset(path), unreal.SoundWave):
            raise RuntimeError(f"Refusing to overwrite a non-SoundWave asset at {path}")

    factory = unreal.SoundFactory()
    factory.set_editor_property("auto_create_cue", False)
    task = unreal.AssetImportTask()
    task.filename = asset["wav"]
    task.destination_path = DESTINATION
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    task.factory = factory
    tools.import_asset_tasks([task])

    objects = list(task.get_objects())
    if len(objects) != 1 or not isinstance(objects[0], unreal.SoundWave):
        raise RuntimeError(f"SoundFactory did not import exactly one SoundWave from {asset['wav']}")
    sound = objects[0]
    if sound.get_path_name() != path:
        raise RuntimeError(f"SoundFactory imported {sound.get_path_name()} instead of {path}")

    sound.set_editor_property("looping", False)
    sound.set_editor_property("loading_behavior", unreal.SoundWaveLoadingBehavior.FORCE_INLINE)
    sound.set_editor_property("attenuation_settings", attenuation)
    sound.set_sound_asset_compression_type(unreal.SoundAssetCompressionType.PCM)

    duration = float(sound.get_editor_property("duration"))
    channels = sound.get_editor_property("num_channels")
    sample_rate = sound.get_editor_property("imported_sample_rate")
    if (channels != 1 or sample_rate != asset["sample_rate"]
            or abs(duration - asset["duration_seconds"]) > 0.01):
        raise RuntimeError(f"Imported SoundWave format differs from the selected WAV: {path}")
    if not unreal.EditorAssetLibrary.save_loaded_asset(sound):
        raise RuntimeError(f"Unable to save {path}")
    return {**asset, "path": path, "duration_seconds": duration, "channels": channels}


def main():
    selection_sha256, assets = load_selection()
    unreal.AssetRegistryHelpers.get_asset_registry().search_all_assets(True)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    attenuation = get_attenuation(tools)
    imported = [import_wave(tools, attenuation, asset) for asset in assets]
    receipt = {
        "ok": True,
        "scope": "UE 5.7 editor asset import and format readback",
        "selection_sha256": selection_sha256,
        "attenuation": {
            "name": ATTENUATION_NAME,
            "path": attenuation.get_path_name(),
            "inner_radius_cm": INNER_RADIUS_CM,
            "falloff_cm": FALLOFF_CM,
        },
        "assets": imported,
    }
    RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    unreal.log(f"RK_DS3_WEAPON_AUDIO_IMPORTED assets={len(imported)} selection_sha256={selection_sha256}")


if __name__ == "__main__":
    main()
