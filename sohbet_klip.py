#!/usr/bin/env python3
"""sohbet_klip.py - Twitch sohbetinin patladigi anlardan dikey klip keser.

Yalnizca standart kutuphane ve ffmpeg kullanir.

Iki kullanim sekli var:

  1) Videonun tamami elinizdeyse:
       python3 sohbet_klip.py chat.json yayin.mp4

  2) Videoyu hic indirmeden, sadece kliplik parcalari indirerek
     (TwitchDownloaderCLI gerekir, GitHub Actions bunu kullanir):
       python3 sohbet_klip.py chat.json --vod 2345678901

Ayarlar:
  --adet 10    en fazla kac klip
  --dilim 10   sohbet kac saniyelik dilimlerde sayilsin
  --once 20    klip bulunan andan kac saniye once baslasin
  --sure 40    klip kac saniye olsun
  --esik 2     ortalamanin kac standart sapma ustu "patlama" sayilsin
  --aralik 60  birbirine bundan yakin anlardan sadece en yogunu kalsin
  --atla 1200  yayinin ilk kac saniyesi yok sayilsin (acilis/bekleme ekrani)
  --duzen tam|orta|kamera
               tam   : oyunun tamami ortada, arkasi bulanik (varsayilan)
               orta  : goruntunun ortasindan 9:16 kirpar
               kamera: ustte yayincinin kamerasi, altta oyun
  --kamera x,y,g,y  kamera kutusu, kaynak goruntunun orani olarak
               (or. 0.75,0.70,0.25,0.30 = sag alt kose)
"""

import argparse
import json
import re
import math
import os
import shutil
import statistics
import subprocess
import sys

GENISLIK, YUKSEKLIK = 1080, 1920
KAMERA_YUKSEKLIK = 640  # kamera duzeninde ust bolum


def zaman_yazi(sn):
    sn = int(sn)
    return f"{sn // 60}m{sn % 60:02d}s"


def saat_yazi(sn):
    sn = int(sn)
    return f"{sn // 3600:d}:{(sn % 3600) // 60:02d}:{sn % 60:02d}"


KOMIK = re.compile(
    r"(KEKW|OMEGALUL|LULW?|ICANT|LMAO+|LMFAO|ROFL|\bLOL+\b|\bXD+\b|(?:ha){2,}|(?:ah){2,}|"
    r"(?:ja){2,}|(?:sj){2,}|(?:js){2,}|\bkk{2,}|ajsk|asdf|pfff|😂|🤣|💀|☠|ölüyorum|oldum|"
    r"gülmekten|komik|aşırı iyi)", re.I)
AKSIYON = re.compile(
    r"(POG|POGGERS|PogU|\bWTF\b|\bOMG\b|HOLY|\bW+\b|CLIP|KLİP|KLIP|monkaS|NOO+|\bEZ+\b|"
    r"INSANE|CRAZY|\bGG\b|😱|🔥|😳|🤯|yok art[ıi]k|efsane|vay|helal|inanılmaz|nasıl ya|"
    r"aaa+|ooo+)", re.I)


def tepki(metin):
    if not metin:
        return None
    if KOMIK.search(metin):
        return "komik"
    if AKSIYON.search(metin):
        return "aksiyon"
    return None


def sohbeti_oku(yol):
    with open(yol, encoding="utf-8") as f:
        veri = json.load(f)
    ofsetler = []
    for c in veri.get("comments", []):
        t = c.get("content_offset_seconds")
        if isinstance(t, (int, float)) and t >= 0:
            msg = c.get("message") or {}
            metin = msg.get("body") or " ".join(
                fr.get("text", "") for fr in (msg.get("fragments") or []))
            ofsetler.append((float(t), tepki(metin)))
    uzunluk = None
    video = veri.get("video") or {}
    for anahtar in ("length", "end"):
        if isinstance(video.get(anahtar), (int, float)) and video[anahtar] > 0:
            uzunluk = float(video[anahtar])
            break
    return ofsetler, uzunluk


def anlari_bul(ofsetler, dilim, esik, aralik, adet, uzunluk=None, atla=0, mod="tepki"):
    """Her dilime puan verir. mod=tepki: komik/aksiyon tepkileri 3 kat sayilir,
    boylece sadece yogun degil, gulme ve heyecan patlamalari one cikar."""
    ofsetler = [o for o in ofsetler if o[0] >= atla]
    if not ofsetler:
        return []
    son = max(max(t for t, _ in ofsetler), uzunluk or 0)
    n_dilim = int(son // dilim) + 1
    ilk = int(atla // dilim)
    toplam = [0] * n_dilim
    komik = [0] * n_dilim
    aksiyon = [0] * n_dilim
    for t, tur in ofsetler:
        i = int(t // dilim)
        toplam[i] += 1
        if tur == "komik":
            komik[i] += 1
        elif tur == "aksiyon":
            aksiyon[i] += 1
    if mod == "tepki":
        puan = [toplam[i] + 2 * (komik[i] + aksiyon[i]) for i in range(n_dilim)]
    else:
        puan = toplam
    hesap = puan[ilk:] or [0]
    ort = statistics.fmean(hesap)
    sapma = statistics.pstdev(hesap)
    if sapma == 0:
        return []
    adaylar = []
    for i in range(ilk, n_dilim):
        z = (puan[i] - ort) / sapma
        if z < esik:
            continue
        tepki_say = komik[i] + aksiyon[i]
        if mod == "tepki" and tepki_say < max(3, 0.15 * toplam[i]):
            continue  # sadece kalabalik, ama kimse gulmuyor/sasirmiyor
        tur = "komik" if komik[i] >= aksiyon[i] else "aksiyon"
        adaylar.append({"an": i * dilim, "mesaj": toplam[i], "puan": puan[i],
                        "komik": komik[i], "aksiyon": aksiyon[i], "tur": tur,
                        "z": round(z, 2)})
    adaylar.sort(key=lambda a: (-a["puan"], a["an"]))
    secilen = []
    for a in adaylar:
        if all(abs(a["an"] - s["an"]) >= aralik for s in secilen):
            secilen.append(a)
            if len(secilen) >= adet:
                break
    return secilen


def filtre(duzen, kamera):
    if duzen == "tam":
        return (
            "[0:v]split=2[a][b];"
            f"[a]scale={GENISLIK}:{YUKSEKLIK}:force_original_aspect_ratio=increase,"
            f"crop={GENISLIK}:{YUKSEKLIK},boxblur=30:3,eq=brightness=-0.08[arka];"
            f"[b]scale={GENISLIK}:-2[on];"
            "[arka][on]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]"
        )
    if duzen == "kamera":
        x, y, g, h = kamera
        return (
            "[0:v]split=2[k][o];"
            f"[k]crop=iw*{g}:ih*{h}:iw*{x}:ih*{y},"
            f"scale={GENISLIK}:{KAMERA_YUKSEKLIK}:force_original_aspect_ratio=increase,"
            f"crop={GENISLIK}:{KAMERA_YUKSEKLIK}[kam];"
            f"[o]crop='min(iw,ih*{GENISLIK}/{YUKSEKLIK - KAMERA_YUKSEKLIK})':ih,"
            f"scale={GENISLIK}:{YUKSEKLIK - KAMERA_YUKSEKLIK}[oyun];"
            "[kam][oyun]vstack=inputs=2,setsar=1,format=yuv420p[v]"
        )
    return (
        f"[0:v]crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',"
        f"scale={GENISLIK}:{YUKSEKLIK},setsar=1,format=yuv420p[v]"
    )


def ffmpeg_kes(kaynak, baslangic, sure, cikti, duzen, kamera):
    komut = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if baslangic > 0:
        komut += ["-ss", f"{baslangic:.3f}"]
    komut += [
        "-i", kaynak, "-t", f"{sure:.3f}",
        "-filter_complex", filtre(duzen, kamera),
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", cikti,
    ]
    subprocess.run(komut, check=True)


def parca_indir(tdl, vod, baslangic, sure, hedef, kalite):
    """Once TwitchDownloaderCLI, olmazsa yt-dlp ile sadece o parcayi indirir."""
    bitis = int(math.ceil(baslangic + sure))
    denemeler = []
    if shutil.which(tdl) or os.path.exists(tdl):
        k = [tdl, "videodownload", "--id", str(vod),
             "-b", f"{int(baslangic)}s", "-e", f"{bitis}s",
             "-o", hedef, "--ffmpeg-path", shutil.which("ffmpeg") or "ffmpeg"]
        if kalite:
            k += ["-q", kalite]
        oauth = os.environ.get("TWITCH_OAUTH", "").strip()
        if oauth:
            k += ["--oauth", oauth]
        denemeler.append(("TwitchDownloaderCLI", k))
    if shutil.which("yt-dlp"):
        ek = []
        oauth = os.environ.get("TWITCH_OAUTH", "").strip()
        if oauth:
            cerez = os.path.join(os.path.dirname(hedef) or ".", ".twitch_cerez.txt")
            with open(cerez, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write(f".twitch.tv\tTRUE\t/\tTRUE\t0\tauth-token\t{oauth}\n")
            ek = ["--cookies", cerez]
        denemeler.append(("yt-dlp", [
            "yt-dlp", "-q", "--no-warnings", "--force-overwrites", *ek,
            "--download-sections", f"*{int(baslangic)}-{bitis}",
            "-f", "best[height<=1080]/best", "--merge-output-format", "mp4",
            "-o", hedef, f"https://www.twitch.tv/videos/{vod}"]))
    for ad, komut in denemeler:
        if os.path.exists(hedef):
            os.remove(hedef)
        r = subprocess.run(komut)
        if r.returncode == 0 and os.path.exists(hedef) and os.path.getsize(hedef) > 0:
            return
        print(f"   {ad} ile indirilemedi (kod {r.returncode}).")
    raise RuntimeError("parca indirilemedi")


def main():
    p = argparse.ArgumentParser(description="Sohbet patlamalarindan dikey klip keser.")
    p.add_argument("chat", help="TwitchDownloaderCLI ile indirilmis chat.json")
    p.add_argument("video", nargs="?", help="yayinin videosu (or. yayin.mp4)")
    p.add_argument("--vod", help="video yerine sadece parcalari indirmek icin VOD ID")
    p.add_argument("--adet", type=int, default=10)
    p.add_argument("--dilim", type=float, default=10)
    p.add_argument("--once", type=float, default=20)
    p.add_argument("--sure", type=float, default=40)
    p.add_argument("--esik", type=float, default=2)
    p.add_argument("--aralik", type=float, default=60)
    p.add_argument("--cikti", default="klipler")
    p.add_argument("--duzen", choices=["tam", "orta", "kamera"], default="tam")
    p.add_argument("--atla", type=float, default=0, help="ilk kac saniye yok sayilsin")
    p.add_argument("--mod", choices=["tepki", "yogunluk"], default="tepki",
                   help="tepki: gulme/heyecan mesajlarini one cikarir; yogunluk: sadece mesaj sayisi")
    p.add_argument("--kamera", default="0.75,0.70,0.25,0.30",
                   help="x,y,genislik,yukseklik (0-1 arasi oran)")
    p.add_argument("--tdl", default=os.environ.get("TDL", "TwitchDownloaderCLI"))
    p.add_argument("--kalite", default="", help="or. 1080p60 (bos = en iyi)")
    p.add_argument("--sadece-bul", action="store_true",
                   help="klip kesmeden sadece anlari yazdir")
    a = p.parse_args()

    if not a.video and not a.vod and not a.sadece_bul:
        p.error("video dosyasi ya da --vod ID verin")
    kamera = [float(v) for v in a.kamera.split(",")]
    if len(kamera) != 4:
        p.error("--kamera dort sayi olmali: x,y,genislik,yukseklik")

    ofsetler, uzunluk = sohbeti_oku(a.chat)
    print(f"{len(ofsetler)} mesaj okundu, "
          f"{sum(1 for _, t in ofsetler if t)} tanesi gulme/heyecan tepkisi.")
    anlar = anlari_bul(ofsetler, a.dilim, a.esik, a.aralik, a.adet, uzunluk, a.atla, a.mod)
    if not anlar:
        print("Esigi gecen bir sohbet patlamasi bulunamadi.")
    os.makedirs(a.cikti, exist_ok=True)

    kayitlar = []
    for sira, an in enumerate(anlar, 1):
        baslangic = max(0.0, an["an"] - a.once)
        sure = a.sure
        if uzunluk:
            sure = max(1.0, min(sure, uzunluk - baslangic))
        ad = f"klip_{sira:02d}_{an['tur']}_{zaman_yazi(baslangic)}.mp4"
        yol = os.path.join(a.cikti, ad)
        print(f"{sira:2d}. an {saat_yazi(an['an'])}  |  {an['mesaj']} mesaj/{int(a.dilim)} sn, "
              f"{an['komik']} gulme, {an['aksiyon']} heyecan  (z={an['z']})  ->  {ad}")
        if a.sadece_bul:
            continue
        try:
            if a.video:
                ffmpeg_kes(a.video, baslangic, sure, yol, a.duzen, kamera)
            else:
                ham = os.path.join(a.cikti, f".ham_{sira:02d}.mp4")
                parca_indir(a.tdl, a.vod, baslangic, sure, ham, a.kalite)
                ffmpeg_kes(ham, 0, sure, yol, a.duzen, kamera)
                os.remove(ham)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            print(f"   ATLANDI: {e}")
            if not kayitlar and sira >= 2:
                print("Ilk iki parca da indirilemedi; VOD abonelere ozel ya da erisilemiyor "
                      "olabilir. Bu VOD birakildi.")
                break
            continue
        kayitlar.append({
            "dosya": ad, "an_sn": an["an"], "an": saat_yazi(an["an"]),
            "baslangic_sn": baslangic, "sure_sn": sure,
            "mesaj": an["mesaj"], "komik": an["komik"], "aksiyon": an["aksiyon"],
            "tur": an["tur"], "z": an["z"], "vod": a.vod,
        })

    with open(os.path.join(a.cikti, "klipler.json"), "w", encoding="utf-8") as f:
        json.dump(kayitlar, f, ensure_ascii=False, indent=2)
    print(f"Bitti: {len(kayitlar)} klip -> {a.cikti}/")
    if anlar and not kayitlar and not a.sadece_bul:
        sys.exit("Hicbir klip uretilemedi.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"Komut basarisiz oldu: {e}")
