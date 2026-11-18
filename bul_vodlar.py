#!/usr/bin/env python3
"""bul_vodlar.py - Islenecek Twitch VOD'larini bulur (GitHub Actions icin).

Kaynaklar:
  istek.txt       elle eklenen VOD ID'leri (her satira bir tane) - anahtar gerektirmez
  yayincilar.txt  takip edilen yayincilar (Twitch kullanici adlari)
                  TWITCH_CLIENT_ID ve TWITCH_CLIENT_SECRET secret'lari gerekir
  islenenler.txt  daha once islenmis VOD'lar (tekrar islenmez)

Cikti: GITHUB_OUTPUT'a  vodlar=["123","456"]  ve  sayi=2
"""

import argparse
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request


def satirlar(yol):
    if not os.path.exists(yol):
        return []
    out = []
    with open(yol, encoding="utf-8") as f:
        for s in f:
            s = s.split("#", 1)[0].strip()
            if s:
                out.append(s)
    return out


def vod_id(s):
    m = re.search(r"(\d{6,})", s)
    return m.group(1) if m else None


def istek(url, veri=None, baslik=None):
    req = urllib.request.Request(url, data=veri, headers=baslik or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def helix_vodlari(yayincilar, en_fazla, son_saat):
    cid = os.environ.get("TWITCH_CLIENT_ID", "").strip()
    sec = os.environ.get("TWITCH_CLIENT_SECRET", "").strip()
    if not yayincilar:
        return []
    if not cid or not sec:
        print("UYARI: yayincilar.txt dolu ama TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET yok; "
              "otomatik tarama atlandi.")
        return []
    tok = istek("https://id.twitch.tv/oauth2/token", urllib.parse.urlencode({
        "client_id": cid, "client_secret": sec, "grant_type": "client_credentials"}).encode())
    b = {"Client-Id": cid, "Authorization": f"Bearer {tok['access_token']}"}
    api = "https://api.twitch.tv/helix"
    q = "&".join("login=" + urllib.parse.quote(y.lower()) for y in yayincilar[:100])
    kullanicilar = istek(f"{api}/users?{q}", baslik=b)["data"]
    sinir = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=son_saat)
    bulunan = []
    for k in kullanicilar:
        canli = istek(f"{api}/streams?user_id={k['id']}", baslik=b)["data"]
        canli_id = canli[0]["id"] if canli else None
        vids = istek(f"{api}/videos?user_id={k['id']}&type=archive&first={en_fazla}",
                     baslik=b)["data"]
        for v in vids:
            olusma = dt.datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
            if olusma < sinir:
                continue
            if canli_id and v.get("stream_id") == canli_id:
                print(f"{k['login']}: {v['id']} hala canli, yayin bitince islenecek.")
                continue
            print(f"{k['login']}: {v['id']}  {v['duration']}  {v['title'][:60]}")
            bulunan.append(v["id"])
    return bulunan


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ek", default="", help="elle verilen VOD ID ya da linki")
    p.add_argument("--en-fazla", type=int, default=2, help="yayinci basina en fazla VOD")
    p.add_argument("--son-saat", type=int, default=48, help="bu kadar saatten eski VOD'lari atla")
    p.add_argument("--limit", type=int, default=6, help="bir calismada toplam en fazla VOD")
    a = p.parse_args()

    islenen = set(filter(None, map(vod_id, satirlar("islenenler.txt"))))
    adaylar = []  # (vod, ek ayarlar)
    for s in [a.ek] + satirlar("istek.txt"):
        v = vod_id(s) if s else None
        if v:
            # satirda VOD'dan sonra yazilan ayarlar: or. "--atla 3600 --duzen kamera"
            ayar = s.split(v, 1)[1].strip()
            if not re.fullmatch(r"[A-Za-z0-9.,=\- ]*", ayar):
                print(f"UYARI: {v} icin gecersiz ayar yok sayildi: {ayar}")
                ayar = ""
            adaylar.append((v, ayar))
    adaylar += [(v, "") for v in helix_vodlari(satirlar("yayincilar.txt"), a.en_fazla, a.son_saat)]

    sonuc, gorulen = [], set()
    for v, ayar in adaylar:
        if v not in islenen and v not in gorulen:
            gorulen.add(v)
            sonuc.append({"vod": v, "ayar": ayar})
    sonuc = sonuc[: a.limit]
    print("Islenecek VOD'lar:", sonuc or "yok")

    cikti = os.environ.get("GITHUB_OUTPUT")
    if cikti:
        with open(cikti, "a", encoding="utf-8") as f:
            f.write(f"vodlar={json.dumps(sonuc)}\n")
            f.write(f"sayi={len(sonuc)}\n")


if __name__ == "__main__":
    main()
