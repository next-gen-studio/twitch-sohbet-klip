#!/usr/bin/env python3
"""duzenle.py - duzenle/*.json senaryolarindan edit'li Shorts videolari uretir (GitHub Actions).

Her senaryo dosyasi:
  {"vod": "2932444934", "klip": "klip_06_komik_94m10s.mp4",
   "baslik": "THIS NPC STOLE HIS CAR", "baslik_emoji": "😭🚗", "yayinci": "LIRIK"}

Adimlar (her senaryo icin):
  1. vod-<ID> release'indeki klipler.json'dan klibin baslangic/suresini okur
  2. yayinin o parcasini 16:9 ham olarak yeniden indirir (olmazsa release'deki 9:16 klibi kullanir)
  3. faster-whisper ile kelime kelime yaziya doker
  4. hazirla.py ile altyazi/emoji/efekt/bip girdilerini hazirlar
  5. Remotion ile 1080x1920 videoyu render eder
  6. edit-<ID> release'ine edit_<klip> adiyla yukler
Zaten yuklenmis olanlari atlar (--zorla ile yeniden yapar).
"""
import argparse
import glob
import json
import os
import subprocess
import sys

KOK = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(KOK)
sys.path.insert(0, REPO)
from sohbet_klip import parca_indir  # noqa: E402


def calis(komut, **kw):
    print("+", " ".join(komut), flush=True)
    return subprocess.run(komut, check=True, **kw)


def release_dosyalari(etiket):
    r = subprocess.run(["gh", "release", "view", etiket, "--json", "assets"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {a["name"] for a in json.loads(r.stdout)["assets"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zorla", action="store_true")
    p.add_argument("--model", default="small")
    a = p.parse_args()

    tdl = os.environ.get("TDL", "TwitchDownloaderCLI")
    is_dizin = os.path.join(REPO, "_is")
    os.makedirs(is_dizin, exist_ok=True)
    yapilan = 0
    hatali = 0
    for yol in sorted(glob.glob(os.path.join(REPO, "duzenle", "*.json"))):
        with open(yol, encoding="utf-8") as f:
            sen = json.load(f)
        vod, klip = str(sen["vod"]), sen["klip"]
        cikti_ad = "edit_" + klip
        etiket = f"edit-{vod}"
        mevcut = release_dosyalari(etiket)
        if mevcut and cikti_ad in mevcut and not a.zorla:
            print(f"atlandi (zaten var): {cikti_ad}")
            continue
        try:
            print(f"\n=== {vod} / {klip}: {sen.get('baslik')}")
            d = os.path.join(is_dizin, os.path.splitext(klip)[0])
            os.makedirs(d, exist_ok=True)

            calis(["gh", "release", "download", f"vod-{vod}", "-p", "klipler.json", "-D", d, "--clobber"])
            with open(os.path.join(d, "klipler.json"), encoding="utf-8") as f:
                bilgi = next(k for k in json.load(f) if k["dosya"] == klip)

            ham = os.path.join(d, "ham.mp4")
            kaynak = "ham"
            try:
                parca_indir(tdl, vod, bilgi["baslangic_sn"], bilgi["sure_sn"], os.path.join(d, "ham_ilk.mp4"), "")
                # tam zamanina kirp, 30 fps'e sabitle
                calis(["ffmpeg", "-loglevel", "error", "-y", "-i", os.path.join(d, "ham_ilk.mp4"),
                       "-t", str(bilgi["sure_sn"]), "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "16", "-c:a", "aac", "-b:a", "192k", ham])
            except Exception as e:  # noqa: BLE001
                print(f"ham parca indirilemedi ({e}); release'deki 9:16 klip kullanilacak")
                calis(["gh", "release", "download", f"vod-{vod}", "-p", klip, "-D", d, "--clobber"])
                ham = os.path.join(d, klip)
                kaynak = "bilesik"

            kelimeler = os.path.join(d, "kelimeler.json")
            calis([sys.executable, os.path.join(KOK, "yaziya_dok.py"), ham, kelimeler,
                   "--model", a.model, "--dil", sen.get("dil", "en")])
            senaryo = os.path.join(d, "senaryo.json")
            with open(senaryo, "w", encoding="utf-8") as f:
                json.dump(sen, f, ensure_ascii=False)
            props = os.path.join(d, "props.json")
            calis([sys.executable, os.path.join(KOK, "hazirla.py"), ham, kelimeler,
                   "--senaryo", senaryo, "--kaynak", kaynak, "--props", props])
            cikti = os.path.join(d, cikti_ad)
            calis(["npx", "remotion", "render", "src/index.ts", "Short", cikti,
                   f"--props={props}", "--log=error", "--crf=20"], cwd=os.path.join(KOK, "remotion"))

            if mevcut is None:
                calis(["gh", "release", "create", etiket, "--title", f"VOD {vod} edit'li Shorts",
                       "--notes", f"Kaynak: https://www.twitch.tv/videos/{vod}"])
            calis(["gh", "release", "upload", etiket, cikti, "--clobber"])
        except Exception as e:  # noqa: BLE001
            print(f"HATA {klip}: {e} - bu senaryo atlandi, digerlerine devam")
            hatali += 1
            continue
        yapilan += 1
    print(f"\nBitti: {yapilan} video uretildi, {hatali} hatali.")


if __name__ == "__main__":
    main()
