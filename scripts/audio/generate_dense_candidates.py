"""Derive original, dense auditions from the supplied ORIGINAL wood prototype.

Uses only the standard library. Does not read or embed ChessReps reference audio.
Run from any directory; writes only the six named WAVs and their manifest.
"""

import hashlib
import json
import math
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "apps/web/public/audio"
SOURCE = AUDIO / "chess-lounge-wood-prototype.wav"
SOURCE_SHA256 = "45bea7b0a9c90b28ea4e07d12621cb3173e3f1cf7ecace0218cb6a69459cbc00"
RATE = 48000
PROFILES = [
    (14, "compact", 1.00, 1800, 180, 0.014, 0.00010, 1.0, 0.080),
    (15, "felted", 0.94, 1150, 190, 0.008, 0.00045, 1.0, 0.075),
    (16, "firm", 1.10, 2300, 250, 0.010, 0.00008, 1.8, 0.080),
    (17, "weighted", 0.82, 1450, 160, 0.017, 0.00016, 1.4, 0.095),
    (18, "dry", 1.06, 1850, 360, 0.005, 0.00008, 1.0, 0.060),
    (19, "padded", 0.90, 1000, 210, 0.010, 0.00065, 1.3, 0.085),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(values):
    energy = sum(x * x for x in values)
    running = 0.0
    energy95_ms = 0.0
    for i, value in enumerate(values):
        running += value * value
        if running >= 0.95 * energy:
            energy95_ms = i / RATE * 1000
            break
    return {
        "duration_ms": len(values) / RATE * 1000,
        "peak": max(abs(x) for x in values),
        "rms": math.sqrt(energy / len(values)),
        "energy_seconds": energy / RATE,
        "energy95_ms": energy95_ms,
        "energy_after_20ms_fraction": sum(x * x for x in values[int(0.02 * RATE) :]) / energy,
    }


def main():
    if digest(SOURCE) != SOURCE_SHA256:
        raise ValueError("Expected the unchanged supplied original prototype")
    with wave.open(str(SOURCE), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (RATE, 1, 2)
        data = wav.readframes(wav.getnframes())
    original = [x / 32768 for x in struct.unpack("<" + "h" * (len(data) // 2), data)]
    target_energy = sum(x * x for x in original) * 0.85
    manifest = {
        "source_file": SOURCE.name,
        "source_sha256": SOURCE_SHA256,
        "source_metrics": metrics(original),
        "candidates": [],
    }
    for number, name, speed, lowpass, highpass, damping, onset, saturation, duration in PROFILES:
        values = []
        low = bass = 0.0
        low_alpha = 1 - math.exp(-2 * math.pi * lowpass / RATE)
        bass_alpha = 1 - math.exp(-2 * math.pi * highpass / RATE)
        for i in range(round(duration * RATE)):
            position = i * speed
            index = int(position)
            fraction = position - index
            value = (
                original[index] * (1 - fraction) + original[index + 1] * fraction
                if index + 1 < len(original)
                else 0.0
            )
            low += low_alpha * (value - low)
            bass += bass_alpha * (low - bass)
            # Remove bass/cavity bloom; damp the actual original contact rather
            # than adding a sustained oscillator, reverb, or a second tap.
            value = math.tanh((low - bass) * saturation) / saturation
            t = i / RATE
            envelope = (1 - math.exp(-t / onset)) * math.exp(-max(0, t - 0.004) / damping)
            envelope *= min(1, (duration - t) / 0.004)
            values.append(value * envelope)
        energy = sum(x * x for x in values)
        peak = max(abs(x) for x in values)
        # Match impact energy near the supplied quiet prototype, not the louder
        # old family. Bound compensation to 3.5dB and retain ample peak headroom.
        gain = min(math.sqrt(target_energy / energy), 1.5, 0.30 / peak)
        quantized = [round(x * gain * 32767) for x in values]
        path = AUDIO / f"dense-{number}-{name}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            wav.writeframes(struct.pack("<" + "h" * len(quantized), *quantized))
        manifest["candidates"].append(
            {
                "sound": number,
                "file": path.name,
                "sha256": digest(path),
                "parameters": {
                    "speed": speed,
                    "lowpass_hz": lowpass,
                    "highpass_hz": highpass,
                    "damping_seconds": damping,
                    "onset_seconds": onset,
                    "saturation": saturation,
                    "bounded_gain": gain,
                },
                **metrics([x / 32768 for x in quantized]),
            }
        )
    (AUDIO / "dense-provenance.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
