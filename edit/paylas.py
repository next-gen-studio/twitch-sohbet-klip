#!/usr/bin/env python3
"""paylas.py - edit'li Shorts videolarini Buffer API ile YouTube kanalina gonderir.

- duzenle/*.json senaryolarini sirayla gezer
- edit-<VOD> release'inde videosu olan ve daha once paylasilmamis olanlari secer
- Buffer'daki YouTube kanalinin kuyruguna (addToQueue) ekler
- paylasilanlar.txt'ye yazar (bir daha gonderilmez), sonucu paylasim_log.txt'ye yazar

Ortam degiskenleri:
  BUFFER_API_KEY      (zorunlu) Buffer kisisel API anahtari
  BUFFER_CHANNEL_ID   (istege bagli) bos ise hesaptaki ilk YouTube kanali kullanilir
  PAYLAS_ADET         bir calismada en fazla kac video gonderilecegi (varsayilan 1)
  GITHUB_REPOSITORY   release linklerini kurmak icin (Actions bunu kendisi verir)
"""
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYLASILANLAR = os.path.join(REPO, "paylasilanlar.txt")
LOG = os.path.join(REPO, "paylasim_log.txt")
SILINENLER = os.path.join(REPO, "silinenler.txt")
PLAN_ERKEN_DK = 15  # "plan" saatinden en fazla bu kadar dakika once gonderilir
API = "https://api.buffer.com"


def log(satir):
    zaman = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(satir, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{zaman}  {satir}\n")


def gql(anahtar, sorgu, degiskenler=None):
    govde = json.dumps({"query": sorgu, "variables": degiskenler or {}}).encode("utf-8")
    istek = urllib.request.Request(API, data=govde, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {anahtar}",
    })
    try:
        with urllib.request.urlopen(istek, timeout=60) as r:
            cevap = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Buffer HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    if cevap.get("errors"):
        raise RuntimeError("Buffer hata: " + "; ".join(x.get("message", "?") for x in cevap["errors"]))
    return cevap["data"]


def youtube_kanali(anahtar):
    kanal = os.environ.get("BUFFER_CHANNEL_ID", "").strip()
    if kanal:
        return kanal
    orglar = gql(anahtar, "query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orglar:
        kanallar = gql(anahtar, "query { channels(input: {organizationId: %s}) { id name service isDisconnected } }"
                       % json.dumps(org["id"]))["channels"]
        for k in kanallar:
            if k["service"] == "youtube" and not k.get("isDisconnected"):
                log(f"YouTube kanali bulundu: {k['name']} ({k['id']}), organizasyon: {org['name']}")
                return k["id"]
    raise RuntimeError("Bu Buffer hesabinda bagli bir YouTube kanali yok")


def release_dosyalari(etiket):
    r = subprocess.run(["gh", "release", "view", etiket, "--json", "assets"], capture_output=True, text=True)
    if r.returncode != 0:
        return set()
    return {a["name"] for a in json.loads(r.stdout)["assets"]}


def yasakli_kelimeler():
    """Aciklamada gecmemesi gerekenler: yayinci adlari, Twitch, yayin/video ifadeleri, linkler."""
    adlar = []
    yol = os.path.join(REPO, "yayincilar.txt")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            for s in f:
                s = s.split("#", 1)[0].strip()
                if s:
                    adlar.append(s.split()[0])
    adlar += ["lirik", "jynxzi", "nickmercs", "darkviperau", "quin69", "vanoss", "vanosscrew",
              "theburntpeanut", "burntpeanut"]
    genel = ["twitch", "stream", "streams", "streamer", "streamers", "streaming", "livestream",
             "vod", "vods", "video", "videos", "clip", "clips", "clipped", "kick", "youtube"]
    return re.compile(r"(?i)(https?://\S+|\b(?:" + "|".join(re.escape(x) for x in set(adlar + genel)) + r")\b)")


def aciklama_temizle(metin):
    yasak = yasakli_kelimeler()
    out = []
    for satir in metin.split("\n"):
        if satir.strip().startswith("#"):
            etiketler = [e for e in satir.split() if not yasak.search(e.lstrip("#"))]
            satir = " ".join(etiketler)
            if satir:
                out.append(satir)
            continue
        if yasak.search(satir):
            log(f"UYARI aciklamadan cikarildi: {satir[:80]}")
            continue
        out.append(satir)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def metinler(sen):
    if sen.get("seo_baslik") and sen.get("seo_aciklama"):
        return sen["seo_baslik"][:100], sen["seo_aciklama"]
    baslik = sen["baslik"].strip()
    emoji = sen.get("baslik_emoji", "").strip()
    yayinci = sen.get("yayinci", "").strip()
    yt_baslik = f"{baslik} {emoji}".strip()
    if len(yt_baslik) > 90:
        yt_baslik = yt_baslik[:90].rstrip()
    yt_baslik += " #shorts"
    satirlar = [f"{baslik} {emoji}".strip(), "",
                 "#GTA6 #GTAVI #GTA6Gameplay #GTA6Funny #GamingShorts #Shorts"]
    return yt_baslik, "\n".join(satirlar)


OLUSTUR = """
mutation($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}
"""


def main():
    # Varsayilan servis Zernio; senaryoda "servis": "buffer" olanlar Buffer ile gonderilir.
    zernio_var = bool(os.environ.get("ZERNIO_API_KEY", "").strip())
    rc = 0
    if zernio_var:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import zernio_paylas
        rc = zernio_paylas.main()
    r = buffer_main(sadece_buffer=zernio_var)
    return 1 if (rc or r) else 0


def buffer_main(sadece_buffer=False):
    anahtar = os.environ.get("BUFFER_API_KEY", "").strip()
    if not anahtar:
        if not sadece_buffer:
            log("BUFFER_API_KEY secret bulunamadi, paylasim atlandi")
        return 0
    adet = int(os.environ.get("PAYLAS_ADET", "1") or "1")
    depo = os.environ.get("GITHUB_REPOSITORY", "next-gen-studio/twitch-sohbet-klip")

    paylasilan = set()
    if os.path.exists(PAYLASILANLAR):
        with open(PAYLASILANLAR, encoding="utf-8") as f:
            paylasilan = {s.split("\t")[0] for s in f if s.strip()}

    silinen = set()
    if os.path.exists(SILINENLER):
        with open(SILINENLER, encoding="utf-8") as f:
            silinen = {s.strip() for s in f if s.strip()}
    simdi = datetime.datetime.now(datetime.timezone.utc)

    adaylar = []
    eski_silinecek = []
    for yol in sorted(glob.glob(os.path.join(REPO, "duzenle", "*.json"))):
        with open(yol, encoding="utf-8") as f:
            sen = json.load(f)
        anahtar_ad = f"{sen['vod']}/{sen['klip']}"
        if anahtar_ad in paylasilan:
            continue
        if sadece_buffer and sen.get("servis") != "buffer":
            continue
        if sen.get("plan"):
            # Kendi planlamamiz: Buffer'da zamanlanmis gonderi tutulmaz, video plan saatinde shareNow ile gider.
            if sen.get("eski_post") and sen["eski_post"] not in silinen:
                eski_silinecek.append(sen["eski_post"])
            p = datetime.datetime.fromisoformat(sen["plan"])
            if p.tzinfo is None:
                p = p.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
            if p > simdi + datetime.timedelta(minutes=PLAN_ERKEN_DK):
                continue
        if "edit_" + sen["klip"] not in release_dosyalari(f"edit-{sen['vod']}"):
            continue
        adaylar.append((anahtar_ad, sen))

    if eski_silinecek:
        try:
            for pid in eski_silinecek:
                try:
                    gql(anahtar, "mutation { deletePost(input: {id: %s}) { __typename } }" % json.dumps(pid))
                    log(f"Eski Buffer zamanlamasi silindi (kendi planimiza gecildi): {pid}")
                except Exception as e:  # noqa: BLE001
                    log(f"Eski Buffer gonderisi silinemedi ({pid}), zaten yok sayiliyor: {e}")
                with open(SILINENLER, "a", encoding="utf-8") as f:
                    f.write(pid + "\n")
                silinen.add(pid)
        except Exception as e:  # noqa: BLE001
            log(f"HATA eski gonderi silme: {e}")

    if not adaylar:
        if not sadece_buffer:
            log("Paylasilacak yeni video yok")
        return 0

    try:
        kanal = youtube_kanali(anahtar)
    except Exception as e:  # noqa: BLE001
        log(f"HATA kanal bulunamadi: {e}")
        return 1

    hata = 0
    def _oncelikli(x):
        return x[1].get("hemen") or x[1].get("zaman") or x[1].get("plan")
    hemen = [x for x in adaylar if _oncelikli(x) and not x[1].get("plan")]
    planli = sorted([x for x in adaylar if x[1].get("plan")], key=lambda x: x[1]["plan"])
    hemen += planli[:1]  # her calismada en fazla 1 planli video (gecikenler sirayla sonraki saatlere kayar)
    sira = hemen + [x for x in adaylar if not _oncelikli(x)][:max(0, adet - len(hemen))]
    for anahtar_ad, sen in sira:
        url = f"https://github.com/{depo}/releases/download/edit-{sen['vod']}/edit_{sen['klip']}"
        yt_baslik, aciklama = metinler(sen)
        aciklama = aciklama_temizle(aciklama)
        mod, zaman = ("shareNow" if (sen.get("hemen") or sen.get("plan")) else "addToQueue"), None
        if sen.get("zaman"):
            z = datetime.datetime.fromisoformat(sen["zaman"])
            if z.tzinfo is None:
                z = z.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=3)))  # Istanbul
            if z > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
                mod, zaman = "customScheduled", z.isoformat()
            else:
                mod = "shareNow"
                log(f"{anahtar_ad}: zamani gecmis ({sen['zaman']}), hemen paylasiliyor")
        girdi = {
            "text": aciklama,
            "channelId": kanal,
            "schedulingType": "automatic",
            "mode": mod,
            "needsApproval": False,
            "assets": [{"video": {"url": url}}],
            "metadata": {"youtube": {"title": yt_baslik, "categoryId": "20"}},
        }
        if zaman:
            girdi["dueAt"] = zaman
        if sen.get("eski_post") and sen["eski_post"] not in silinen:
            try:
                gql(anahtar, "mutation { deletePost(input: {id: %s}) { __typename } }" % json.dumps(sen["eski_post"]))
                log(f"Eski kuyruk gonderisi silindi: {sen['eski_post']}")
            except Exception as e:  # noqa: BLE001
                log(f"HATA eski gonderi silinemedi ({sen['eski_post']}), cift paylasim olmasin diye atlandi: {e}")
                hata += 1
                continue
        try:
            sonuc = gql(anahtar, OLUSTUR, {"input": girdi})["createPost"]
        except Exception as e:  # noqa: BLE001
            log(f"HATA {anahtar_ad}: {e}")
            hata += 1
            continue
        if "post" in sonuc and sonuc["post"]:
            p = sonuc["post"]
            log(f"OK {anahtar_ad} -> Buffer post {p['id']}, zaman: {p.get('dueAt')}, baslik: {yt_baslik}")
            with open(PAYLASILANLAR, "a", encoding="utf-8") as f:
                f.write(f"{anahtar_ad}\t{p['id']}\t{p.get('dueAt')}\n")
        else:
            log(f"HATA {anahtar_ad}: {sonuc.get('message', sonuc)}")
            hata += 1
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
