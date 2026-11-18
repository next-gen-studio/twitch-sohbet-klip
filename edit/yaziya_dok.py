#!/usr/bin/env python3
"""yaziya_dok.py - Klibi kelime kelime zamanli yaziya doker (faster-whisper).

Kullanim: python3 yaziya_dok.py klip.mp4 cikti.json [--model small.en]
Cikti: {"dil": "en", "kelimeler": [{"w": "hello", "s": 0.12, "e": 0.40}, ...]}
"""
import argparse
import json
import subprocess

import numpy as np

from faster_whisper import WhisperModel


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("cikti")
    p.add_argument("--model", default="small")
    p.add_argument("--dil", default=None, help="or. en (bos = otomatik)")
    a = p.parse_args()

    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    # sesi ffmpeg ile 16 kHz mono olarak oku (PyAV surum sorunlarindan kacinmak icin)
    ham = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", a.video, "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    ses = np.frombuffer(ham, np.int16).astype(np.float32) / 32768.0
    parcalar, bilgi = model.transcribe(
        ses, language=a.dil, word_timestamps=True, vad_filter=True,
        condition_on_previous_text=False)
    kelimeler = []
    for parca in parcalar:
        for w in parca.words or []:
            t = w.word.strip()
            if t:
                kelimeler.append({"w": t, "s": round(w.start, 2), "e": round(w.end, 2)})
    with open(a.cikti, "w", encoding="utf-8") as f:
        json.dump({"dil": bilgi.language, "kelimeler": kelimeler}, f, ensure_ascii=False, indent=1)
    print(f"{len(kelimeler)} kelime ({bilgi.language}) -> {a.cikti}")
    print(" ".join(k["w"] for k in kelimeler))


if __name__ == "__main__":
    main()
