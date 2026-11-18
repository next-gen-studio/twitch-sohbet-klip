# Twitch Sohbet Klip

Twitch yayınlarında sohbetin patladığı anları bulur ve her birinden dikey (1080x1920) bir klip keser. Her şey GitHub Actions'ta çalışır, bilgisayarın açık olması gerekmez.

**Yöntem:** Sohbet 10 saniyelik dilimlerde sayılır. Ortalamanın 2 standart sapma üstünde kalan dilimler "patlama" kabul edilir. Birbirine 60 saniyeden yakın patlamalardan sadece en yoğunu tutulur ve en fazla 10 an seçilir. Sohbet olaya geç tepki verdiği için her klip bulunan andan 20 saniye önce başlar ve 40 saniye sürer.

**Fark:** 8 saatlik yayının tamamı indirilmez. Önce sadece sohbet indirilir (birkaç MB). Sonra yalnızca kliplik 40 saniyelik parçalar indirilir.

## Önce yapılması gereken: Twitch girişi (zorunlu)
Twitch, GitHub sunucularından giriş yapmadan gelen video isteklerini reddediyor ("Insufficient access to VOD, OAuth may be required"). Sohbet indirmesi giriş olmadan da çalışıyor, ama video parçaları için bir Twitch hesabının giriş anahtarı gerekiyor:
1. Bilgisayarınızdaki tarayıcıda twitch.tv'ye giriş yapın. Bunun için ayrı, ikinci bir hesap kullanmanız önerilir.
2. F12 tuşuyla geliştirici araçlarını açın, ardından **Application → Cookies → https://www.twitch.tv** yolunu izleyin ve `auth-token` değerini kopyalayın.
3. Bu değeri repoda **Settings → Secrets and variables → Actions → New repository secret** altına `TWITCH_OAUTH` adıyla ekleyin.

Bu anahtar hesabınıza erişim sağlar, kimseyle paylaşmayın. Twitch'ten çıkış yaparsanız anahtar geçersiz olur ve yenisini eklemeniz gerekir.

## Kullanım

### 1. Elle bir yayın işletmek (anahtar gerekmez)
- **Yol A:** `istek.txt` dosyasına VOD linkini ekleyip kaydedin (ör. `https://www.twitch.tv/videos/2345678901`). İş hemen başlar.
- **Yol B:** **Actions → Sohbet klipleri → Run workflow** seçip VOD ID'sini yazın.

Klipler **Releases** bölümünde `vod-<ID>` adıyla çıkar. Her klibin anı ve mesaj sayısı `klipler.json` dosyasında listelenir.

### 2. Yayıncıları otomatik takip etmek
1. https://dev.twitch.tv/console/apps adresinden ücretsiz bir uygulama oluşturun. OAuth Redirect URL alanına `http://localhost` yazın.
2. Uygulamanın Client ID ve Client Secret değerlerini repoda **Settings → Secrets and variables → Actions** altına ekleyin:
   `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`
3. `yayincilar.txt` dosyasına her satıra bir yayıncı adı yazın.

Tarama günde 4 kez yapılır: İstanbul saatiyle 03:17, 09:17, 15:17 ve 21:17. Son 48 saatin bitmiş yayınları işlenir. Hâlâ canlı olan yayınlar atlanır ve yayın bitince işlenir. Daha önce işlenen yayınlar (`islenenler.txt`) tekrar işlenmez.

### Ayarlar (Settings → Variables → Actions)
| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `KLIP_ADET` | 10 | Yayın başına en fazla kaç klip çıkacağı |
| `KLIP_SURE` | 40 | Klibin süresi (saniye) |
| `KLIP_ONCE` | 20 | Klibin, bulunan andan kaç saniye önce başlayacağı |
| `KLIP_DUZEN` | orta | `orta`: görüntünün ortasından 9:16 kırpar. `kamera`: üstte yayıncının kamerası, altta oyun |
| `KLIP_KAMERA` | 0.75,0.70,0.25,0.30 | Kamera kutusunun yeri: x,y,genişlik,yükseklik (görüntünün oranı olarak). Örnekteki değer sağ alt köşeyi gösterir |

## Bilgisayarda çalıştırmak
```bash
TwitchDownloaderCLI chatdownload --id VOD_ID -o chat.json
TwitchDownloaderCLI videodownload --id VOD_ID -o yayin.mp4
python3 sohbet_klip.py chat.json yayin.mp4
# ya da videonun tamamını indirmeden:
python3 sohbet_klip.py chat.json --vod VOD_ID
# ayarlarla:
python3 sohbet_klip.py chat.json yayin.mp4 --adet 10 --dilim 10 --once 20 --sure 40 --duzen kamera
```
Gerekenler: Python 3 (yalnızca standart kütüphane), ffmpeg ve [TwitchDownloader](https://github.com/lay295/TwitchDownloader).

## Not
Başka yayıncıların görüntülerini paylaşmak telif şikâyetine yol açabilir. Klipleri paylaşmadan önce yayıncının iznini alın.
