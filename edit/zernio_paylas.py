#!/usr/bin/env python3
"""zernio_paylas.py - edit'li Shorts videolarini Zernio API ile YouTube kanalina (Wanted Level Clips) gonderir.

paylas.py, ZERNIO_API_KEY tanimliysa Buffer yerine bunu kullanir.
- "hemen": true          -> hemen yayinlanir (publishNow)
- "plan" / "zaman" (ISO) -> Zernio'da o saate zamanlanir (scheduledFor); saat gecmisse hemen yayinlanir
- Gonderilenler paylasilanlar.txt'ye yazilir, sonuc paylasim_log.txt'ye yazilir.

Ortam degiskenleri:
  ZERNIO_API_KEY     (zorunlu)
  ZERNIO_ACCOUNT_ID  (istege bagli) bos ise adinda "Wanted Level" gecen YouTube hesabi bulunur
  ZERNIO_KANAL_ADI   (istege bagli, varsayilan "wanted level")
"""
import datetime
import glob
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

import paylas as P

API = "https://zernio.com/api/v1"

# Zernio'nun gonderemedigi videolar; paylas.py bunlari ayni calismada Buffer ile dener.
BASARISIZ = []

# YouTube gunluk yukleme limiti (HTTP 429 "daily upload limit") yuzunden yuklenemeyenler.
# KULLANICI KURALI (20 Kas 2026): bunlar silinmez, Buffer'a gonderilmez; limit acilinca otomatik yuklenir.
BEKLEYEN = os.path.join(P.REPO, "bekleyen_yuklemeler.txt")
LIMIT_RE = re.compile(r"resumes after (\d{4}-\d\d-\d\dT[\d:.]+Z?)")


def bekleyenleri_oku():
    """{vod/klip: devam_zamani (datetime veya None)} - dosyadaki sirayla."""
    sonuc = {}
    if not os.path.exists(BEKLEYEN):
        return sonuc
    with open(BEKLEYEN, encoding="utf-8") as f:
        for s in f:
            if not s.strip() or s.startswith("#"):
                continue
            k = s.rstrip("\n").split("\t")
            devam = None
            if len(k) > 4 and k[4].strip():
                try:
                    devam = datetime.datetime.fromisoformat(k[4].strip().replace("Z", "+00:00"))
                except ValueError:
                    devam = None
            sonuc[k[0]] = devam
    return sonuc


def bekleyen_yaz(ad, sen, baslik, devam):
    """Listede yoksa ekler, varsa devam zamanini gunceller."""
    satirlar = []
    if os.path.exists(BEKLEYEN):
        with open(BEKLEYEN, encoding="utf-8") as f:
            satirlar = f.read().splitlines()
    devam_s = devam.strftime("%Y-%m-%dT%H:%M:%SZ") if devam else ""
    simdi = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    yeni = f"{ad}\tedit-{sen['vod']}/edit_{sen['klip']}\t{baslik}\t{simdi}\t{devam_s}"
    for i, s in enumerate(satirlar):
        if s.split("\t")[0] == ad:
            k = s.split("\t")
            while len(k) < 5:
                k.append("")
            k[4] = devam_s
            satirlar[i] = "\t".join(k)
            break
    else:
        satirlar.append(yeni)
    with open(BEKLEYEN, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")


def bekleyenden_cikar(ad):
    if not os.path.exists(BEKLEYEN):
        return
    with open(BEKLEYEN, encoding="utf-8") as f:
        satirlar = f.read().splitlines()
    satirlar = [s for s in satirlar if s.startswith("#") or not s.strip() or s.split("\t")[0] != ad]
    with open(BEKLEYEN, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")


def istek(anahtar, yol, govde=None, idem=None):
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    bas = {"Authorization": f"Bearer {anahtar}", "Accept": "application/json"}
    if veri is not None:
        bas["Content-Type"] = "application/json"
    if idem:
        bas["Idempotency-Key"] = idem
    r = urllib.request.Request(API + yol, data=veri, method="POST" if veri is not None else "GET", headers=bas)
    try:
        with urllib.request.urlopen(r, timeout=300) as c:
            return c.status, json.loads(c.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        metin = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(metin)
        except ValueError:
            return e.code, {"error": metin[:300]}


def youtube_hesabi(anahtar):
    sabit = os.environ.get("ZERNIO_ACCOUNT_ID", "").strip()
    if sabit:
        return sabit
    aranan = (os.environ.get("ZERNIO_KANAL_ADI", "") or "wanted level").strip().lower()
    kod, cevap = istek(anahtar, "/accounts/health?platform=youtube")
    hesaplar = cevap.get("accounts") if isinstance(cevap, dict) else None
    if kod != 200 or hesaplar is None:
        kod2, cevap2 = istek(anahtar, "/accounts")
        hesaplar = cevap2.get("accounts", cevap2) if isinstance(cevap2, dict) else cevap2
        if kod2 != 200 or not isinstance(hesaplar, list):
            raise RuntimeError(f"Zernio hesaplari okunamadi (HTTP {kod}/{kod2}): {str(cevap)[:200]} {str(cevap2)[:200]}")
    yt = [h for h in hesaplar if str(h.get("platform", "")).lower() == "youtube"]
    adlar = []
    for h in yt:
        ad = " / ".join(str(h.get(k, "")) for k in ("displayName", "username", "name") if h.get(k))
        adlar.append(ad)
        if aranan in ad.lower():
            if h.get("canPost") is False or h.get("needsReconnect"):
                raise RuntimeError(f"Zernio YouTube hesabi '{ad}' paylasima hazir degil (yeniden baglanmali)")
            hid = h.get("accountId") or h.get("_id") or h.get("id")
            P.log(f"Zernio YouTube hesabi bulundu: {ad} ({hid})")
            return hid
    raise RuntimeError(f"Zernio'da adinda '{aranan}' gecen YouTube hesabi yok. Bagli YouTube hesaplari: {adlar or 'hic yok'}")


def main():
    anahtar = os.environ.get("ZERNIO_API_KEY", "").strip()
    depo = os.environ.get("GITHUB_REPOSITORY", "next-gen-studio/twitch-sohbet-klip")
    paylasilan = set()
    if os.path.exists(P.PAYLASILANLAR):
        with open(P.PAYLASILANLAR, encoding="utf-8") as f:
            paylasilan = {s.split("\t")[0] for s in f if s.strip()}
    simdi = datetime.datetime.now(datetime.timezone.utc)

    bekleyen = bekleyenleri_oku()
    bekleyen_adaylar, adaylar = [], []
    for yol in sorted(glob.glob(os.path.join(P.REPO, "duzenle", "*.json"))):
        with open(yol, encoding="utf-8") as f:
            sen = json.load(f)
        ad = f"{sen['vod']}/{sen['klip']}"
        if ad in bekleyen:
            devam = bekleyen[ad]
            if devam and devam > simdi:
                continue  # limit henuz acilmadi; saklaniyor
            if "edit_" + sen["klip"] in P.release_dosyalari(f"edit-{sen['vod']}"):
                bekleyen_adaylar.append((ad, sen))
            continue
        if ad in paylasilan or not (sen.get("hemen") or sen.get("plan") or sen.get("zaman")):
            continue
        if sen.get("servis") == "buffer":  # bu senaryo Buffer ile gonderilir (paylas.py)
            continue
        if "edit_" + sen["klip"] not in P.release_dosyalari(f"edit-{sen['vod']}"):
            continue
        adaylar.append((ad, sen))
    # Once limit yuzunden bekleyenler (listedeki sirayla), sonra yeniler.
    sira = list(bekleyen)
    bekleyen_adaylar.sort(key=lambda x: sira.index(x[0]))
    bekleyen_set = {ad for ad, _ in bekleyen_adaylar}
    adaylar = bekleyen_adaylar + adaylar
    if not adaylar:
        P.log("Zernio: paylasilacak yeni video yok")
        return 0

    try:
        hesap = youtube_hesabi(anahtar)
    except Exception as e:  # noqa: BLE001
        P.log(f"HATA Zernio: {e}")
        BASARISIZ.extend(ad for ad, _ in adaylar)
        return 1

    hata = 0
    limit_devam = None  # bu calismada limite takildiysak kalanlar API'ye gonderilmeden saklanir
    for ad, sen in adaylar:
        if limit_devam is not None:
            baslik, _ = P.metinler(sen)
            bekleyen_yaz(ad, sen, baslik, limit_devam or None)
            P.log(f"BEKLIYOR {ad}: YouTube gunluk limiti dolu, video saklandi (silinmedi), limit acilinca yuklenecek")
            continue
        url = f"https://github.com/{depo}/releases/download/edit-{sen['vod']}/edit_{sen['klip']}"
        baslik, aciklama = P.metinler(sen)
        aciklama = P.aciklama_temizle(aciklama)
        govde = {
            "content": aciklama,
            "tags": ["GTA 6", "GTA VI", "GTA 6 gameplay", "GTA 6 funny moments", "shorts"],
            "mediaItems": [{"type": "video", "url": url}],
            "platforms": [{
                "platform": "youtube",
                "accountId": hesap,
                "platformSpecificData": {"title": baslik[:100], "visibility": "public",
                                         "categoryId": "20", "madeForKids": False},
            }],
        }
        saat = None
        zaman_str = sen.get("plan") or sen.get("zaman")
        if zaman_str and not sen.get("hemen"):
            z = datetime.datetime.fromisoformat(zaman_str)
            if z.tzinfo is None:
                z = z.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
            if z > simdi + datetime.timedelta(minutes=5):
                saat = z.isoformat()
        if saat:
            govde["scheduledFor"] = saat
            mod = f"zamanlandi {saat}"
        else:
            govde["publishNow"] = True
            mod = "hemen"
        anah = f"wlc-{ad}-{saat or 'hemen'}"
        if ad in bekleyen_set:  # ilk deneme 429 aldi; ayni idempotency anahtari eski cevabi dondurmesin
            anah += "-tekrar-" + simdi.strftime("%Y%m%d%H")
        idem = hashlib.sha256(anah.encode()).hexdigest()[:40]
        kod, cevap = istek(anahtar, "/posts", govde, idem)
        post = cevap.get("post") or {} if isinstance(cevap, dict) else {}
        pid = post.get("_id") or post.get("id") or (cevap.get("details", {}) or {}).get("existingPostId")
        durum = post.get("status")
        link = ""
        for p in post.get("platforms", []) or []:
            link = p.get("platformPostUrl") or link
        if kod in (200, 201) and durum not in ("failed",):
            ek = " (bekleyen video, limit acildiktan sonra)" if ad in bekleyen_set else ""
            P.log(f"OK {ad} -> Zernio post {pid} ({mod}), durum: {durum}, link: {link or '-'}, baslik: {baslik}{ek}")
            bekleyenden_cikar(ad)
            with open(P.PAYLASILANLAR, "a", encoding="utf-8") as f:
                f.write(f"{ad}\t{pid}\t{saat or simdi.isoformat()}\tzernio\n")
        elif kod == 409 and pid:
            P.log(f"OK {ad} -> Zernio'da zaten var: {pid} (cift gonderim engellendi)")
            with open(P.PAYLASILANLAR, "a", encoding="utf-8") as f:
                f.write(f"{ad}\t{pid}\t{saat or simdi.isoformat()}\tzernio\n")
        else:
            msg = cevap.get("error") or cevap.get("message") or cevap
            pmsg = [str(p.get("errorMessage") or p.get("error") or "") for p in post.get("platforms", []) or []]
            pmsg = "; ".join(m for m in pmsg if m)
            tum = f"{msg} {pmsg}"
            if kod == 429 or "daily upload limit" in tum.lower():
                m = LIMIT_RE.search(tum)
                devam = None
                if m:
                    try:
                        devam = datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                    except ValueError:
                        devam = None
                if devam is None:
                    devam = simdi + datetime.timedelta(hours=6)
                limit_devam = devam
                bekleyen_yaz(ad, sen, baslik, devam)
                P.log(f"BEKLIYOR {ad}: Zernio HTTP {kod}, YouTube gunluk yukleme limiti dolu, devam: "
                      f"{devam.strftime('%Y-%m-%dT%H:%M:%SZ')}. Video saklandi (silinmedi), Buffer'a gonderilmedi, "
                      f"limit acilinca otomatik yuklenecek")
                continue
            P.log(f"HATA {ad}: Zernio HTTP {kod}, durum: {durum}, {str(msg)[:300]}" + (f" | YouTube: {pmsg[:300]}" if pmsg else ""))
            BASARISIZ.append(ad)
            if os.environ.get("BUFFER_API_KEY", "").strip():
                pass  # Buffer yedegi denenecek; kaydi Buffer basarili olursa o yazar
            elif kod == 207 and pid:  # kismen basarisiz ama post olustu; tekrar gondermeyelim
                with open(P.PAYLASILANLAR, "a", encoding="utf-8") as f:
                    f.write(f"{ad}\t{pid}\t{saat or simdi.isoformat()}\tzernio-207\n")
            hata += 1
    return 1 if hata else 0
