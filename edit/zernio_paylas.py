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
import urllib.error
import urllib.request

import paylas as P

API = "https://zernio.com/api/v1"

# Zernio'nun gonderemedigi videolar; paylas.py bunlari ayni calismada Buffer ile dener.
BASARISIZ = []


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

    adaylar = []
    for yol in sorted(glob.glob(os.path.join(P.REPO, "duzenle", "*.json"))):
        with open(yol, encoding="utf-8") as f:
            sen = json.load(f)
        ad = f"{sen['vod']}/{sen['klip']}"
        if ad in paylasilan or not (sen.get("hemen") or sen.get("plan") or sen.get("zaman")):
            continue
        if sen.get("servis") == "buffer":  # bu senaryo Buffer ile gonderilir (paylas.py)
            continue
        if "edit_" + sen["klip"] not in P.release_dosyalari(f"edit-{sen['vod']}"):
            continue
        adaylar.append((ad, sen))
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
    for ad, sen in adaylar:
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
        idem = hashlib.sha256(f"wlc-{ad}-{saat or 'hemen'}".encode()).hexdigest()[:40]
        kod, cevap = istek(anahtar, "/posts", govde, idem)
        post = cevap.get("post") or {} if isinstance(cevap, dict) else {}
        pid = post.get("_id") or post.get("id") or (cevap.get("details", {}) or {}).get("existingPostId")
        durum = post.get("status")
        link = ""
        for p in post.get("platforms", []) or []:
            link = p.get("platformPostUrl") or link
        if kod in (200, 201) and durum not in ("failed",):
            P.log(f"OK {ad} -> Zernio post {pid} ({mod}), durum: {durum}, link: {link or '-'}, baslik: {baslik}")
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
            P.log(f"HATA {ad}: Zernio HTTP {kod}, durum: {durum}, {str(msg)[:300]}" + (f" | YouTube: {pmsg[:300]}" if pmsg else ""))
            BASARISIZ.append(ad)
            if os.environ.get("BUFFER_API_KEY", "").strip():
                pass  # Buffer yedegi denenecek; kaydi Buffer basarili olursa o yazar
            elif kod == 207 and pid:  # kismen basarisiz ama post olustu; tekrar gondermeyelim
                with open(P.PAYLASILANLAR, "a", encoding="utf-8") as f:
                    f.write(f"{ad}\t{pid}\t{saat or simdi.isoformat()}\tzernio-207\n")
            hata += 1
    return 1 if hata else 0
