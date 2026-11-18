#!/usr/bin/env python3
"""hazirla.py - Klip + yazi dokumu + (istege bagli) senaryo -> Remotion girdileri.

Yaptiklari:
  * kelimeleri 1-3 kelimelik altyazi gruplarina boler, aktif kelimeyi isaretler
  * kufurleri altyazida yildizlar, seste bip ile kapatir (reklam dostu)
  * anahtar kelimelere gore emoji ve ses efekti yerlestirir
  * heyecanli anlara yakinlastirma (zoom) koyar
  * Remotion'un okuyacagi public/girdi/ klasorunu ve props.json'u yazar

Kullanim:
  python3 hazirla.py klip.mp4 kelimeler.json --senaryo senaryo.json --kaynak ham|bilesik
Senaryo (hepsi istege bagli):
  {"baslik": "CHAT PROVED LIRIK WRONG", "baslik_emoji": "😂",
   "yayinci": "LIRIK", "emojiler": [{"t": 3.2, "e": "🤯"}], "zoomlar": [5.1]}
"""
import argparse
import json
import os
import re
import shutil
import subprocess

KUFUR = re.compile(r"^(mother)?f+u+c+k\w*$|^shit\w*$|^bullshit$|^bitch\w*$|^asshole\w*$|"
                   r"^dick\w*$|^goddamn\w*$|^cunt\w*$|^damn$", re.I)

# anahtar kelime -> (emoji, ses efekti)
ESLEME = [
    (r"\b(oh my god|omg|holy|no way|what the)\b", "🤯", "boom"),
    (r"\b(wait|what)\b", "😳", "pop"),
    (r"\b(funny|lol|haha|laugh)\b", "😂", "pop"),
    (r"\b(car|drive|driving|truck)\b", "🚗", "whoosh"),
    (r"\b(stole|steal|stealing|thief)\b", "🦹", "whoosh"),
    (r"\b(shoot|gun|shot|kill)\b", "🔫", "boom"),
    (r"\b(cop|cops|police)\b", "🚔", "pop"),
    (r"\b(water|ocean|sea|swim)\b", "🌊", "pop"),
    (r"\b(cup|drink)\b", "🥤", "pop"),
    (r"\b(window|door)\b", "🪟", "pop"),
    (r"\b(freeze|cold)\b", "🥶", "pop"),
    (r"\b(money|cash|rich)\b", "💰", "ding"),
    (r"\b(right|correct|proud|great job)\b", "✅", "ding"),
    (r"\b(wrong)\b", "❌", "pop"),
    (r"\b(gone|lost|over)\b", "💨", "whoosh"),
    (r"\b(big|huge|insane|crazy)\b", "🔥", "pop"),
    (r"\b(looks good|beautiful|graphics)\b", "😍", "ding"),
    (r"\b(help)\b", "🆘", "pop"),
    (r"\b(chat)\b", "💬", "pop"),
]
ZOOM_KELIME = re.compile(r"\b(oh my god|holy|what the|no way|stop|wait)\b", re.I)


def sure_ol(yol):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", yol], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def sansurle(w):
    yalin = re.sub(r"[^\w]", "", w)
    if yalin and KUFUR.match(yalin):
        bas = yalin[0]
        return w.replace(yalin, bas + "*" * (len(yalin) - 1)), True
    return w, False


def gruplar(kelimeler, en_fazla=3):
    out, cur = [], []
    for i, k in enumerate(kelimeler):
        if cur and (len(cur) >= en_fazla or k["s"] - cur[-1]["e"] > 0.45):
            out.append(cur)
            cur = []
        cur.append(k)
        if re.search(r"[.!?,]$", k["w"]) and len(cur) >= 1:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    sonuc = []
    for i, g in enumerate(out):
        bas = g[0]["s"]
        son = g[-1]["e"]
        sonraki = out[i + 1][0]["s"] if i + 1 < len(out) else son + 0.6
        son = min(max(son + 0.15, bas + 0.35), sonraki)
        sonuc.append({"s": round(bas, 2), "e": round(son, 2), "k": g})
    return sonuc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("kelimeler")
    p.add_argument("--senaryo", default=None)
    p.add_argument("--kaynak", choices=["ham", "bilesik"], default="ham",
                   help="ham: 16:9 yayin goruntusu; bilesik: sohbet_klip 'tam' duzeninde 9:16 klip")
    p.add_argument("--public", default=os.path.join(os.path.dirname(__file__), "remotion", "public"))
    p.add_argument("--props", default="props.json")
    a = p.parse_args()

    senaryo = {}
    if a.senaryo and os.path.exists(a.senaryo):
        with open(a.senaryo, encoding="utf-8") as f:
            senaryo = json.load(f)
    with open(a.kelimeler, encoding="utf-8") as f:
        kelimeler = json.load(f)["kelimeler"]

    girdi = os.path.join(a.public, "girdi")
    os.makedirs(girdi, exist_ok=True)
    sure = sure_ol(a.video)

    # --- kufur: altyazida yildiz, seste bip
    bipler = []
    for k in kelimeler:
        k["w"], kotu = sansurle(k["w"])
        if kotu:
            bipler.append((max(0, k["s"] - 0.03), k["e"] + 0.03))

    # --- video ve ses dosyalari
    shutil.copyfile(a.video, os.path.join(girdi, "video.mp4"))
    if bipler:
        kosul = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in bipler)
        af = f"volume=enable='{kosul}':volume=0"
    else:
        af = "anull"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", a.video, "-vn", "-af", af,
                    "-ar", "48000", "-ac", "2", os.path.join(girdi, "ses.wav")], check=True)

    # --- efektler
    sfx = [{"f": "whoosh.wav", "t": 0.0, "v": 0.7}]
    for s, e in bipler:
        sfx.append({"f": "beep.wav", "t": round(s, 2), "v": 0.55, "sure": round(e - s, 2)})

    metin = [(k["s"], k["w"].lower()) for k in kelimeler]
    emojiler = list(senaryo.get("emojiler", []))
    if not emojiler:
        son_t = -10.0
        kullanilan = set()
        tam = " ".join(w for _, w in metin)
        for desen, emo, ses in ESLEME:
            for m in re.finditer(desen, tam):
                # eslesmenin hangi kelimeye denk geldigini bul
                n = tam[: m.start()].count(" ")
                t = metin[min(n, len(metin) - 1)][0]
                if t < 1.2 or (t - son_t < 1.6 and emo in kullanilan):
                    continue
                emojiler.append({"t": round(t, 2), "e": emo, "ses": ses})
                kullanilan.add(emo)
                son_t = t
                break  # her desenden bir tane
        emojiler.sort(key=lambda x: x["t"])
        # birbirine 1.2 sn'den yakin olanlari seyrelt, en fazla 8
        seyrek = []
        for e in emojiler:
            if not seyrek or e["t"] - seyrek[-1]["t"] >= 1.2:
                seyrek.append(e)
        emojiler = seyrek[:8]
    for e in emojiler:
        sfx.append({"f": f"{e.get('ses', 'pop')}.wav", "t": e["t"], "v": 0.45})

    zoomlar = list(senaryo.get("zoomlar", []))
    if not zoomlar:
        tam = [(k["s"], k["w"]) for k in kelimeler]
        for i, (t, w) in enumerate(tam):
            parca = " ".join(x[1] for x in tam[i:i + 3])
            if ZOOM_KELIME.match(parca.lower()) and (not zoomlar or t - zoomlar[-1] > 4):
                zoomlar.append(round(t, 2))
    zoomlar = zoomlar[:5]

    props = {
        "sure": round(sure, 2),
        "kaynak": a.kaynak,
        "baslik": senaryo.get("baslik", "WAIT FOR IT"),
        "baslikEmoji": senaryo.get("baslik_emoji", "😳"),
        "yayinci": senaryo.get("yayinci", ""),
        "altyazi": [{"s": g["s"], "e": g["e"],
                     "k": [{"w": k["w"], "s": k["s"], "e": k["e"]} for k in g["k"]]}
                    for g in gruplar(kelimeler)],
        "emojiler": emojiler,
        "zoomlar": zoomlar,
        "sfx": sfx,
    }
    with open(a.props, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=1)
    print(f"{len(props['altyazi'])} altyazi grubu, {len(emojiler)} emoji, "
          f"{len(bipler)} bip, {len(zoomlar)} zoom -> {a.props}")


if __name__ == "__main__":
    main()
