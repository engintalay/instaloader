# 📸 Instagram Profile Downloader

Tarayıcı cookie'lerini kullanarak Instagram profillerini indiren konsol uygulaması.

## Özellikler

- 🖼️ Fotoğraf, video ve carousel postları indirir
- 🎯 Highlights (öne çıkan hikayeler) indirir
- 🔄 Fast update — sadece yeni postları çeker
- 🍪 Cookie desteği: dosyadan, Chrome veya Firefox'tan

## Kurulum

```bash
./install.sh
```

Python 3.10 ile sanal ortam oluşturur ve bağımlılıkları kurar.

## Cookie Ayarı

`cookies.example.json` dosyasını `cookies.json` olarak kopyalayıp değerleri doldurun:

```bash
cp cookies.example.json cookies.json
```

Cookie'leri almak için Chrome'da:

1. [instagram.com](https://instagram.com)'a giriş yapın
2. `F12` → **Application** → **Cookies** → `https://www.instagram.com`
3. `sessionid` ve `csrftoken` değerlerini kopyalayın

## Kullanım

```bash
# cookies.json'dan (varsayılan)
./run.sh <profil_adı>

# Chrome cookie'leriyle
./run.sh <profil_adı> chrome

# Firefox cookie'leriyle
./run.sh <profil_adı> firefox
```

## Dosya Yapısı

```
.
├── install.sh              # Kurulum scripti
├── run.sh                  # Çalıştırma scripti
├── download_profile.py     # Ana uygulama
├── cookies.json            # Cookie dosyası (gitignore'da)
├── cookies.example.json    # Örnek cookie dosyası
└── <profil_adı>/           # İndirilen medyalar
```

## ⚠️ Uyarılar

- Kısa sürede çok fazla profil indirmekten kaçının (rate limiting)
- Script çalışırken tarayıcıda Instagram'ı aktif kullanmayın
- Cookie'lerin süresi dolabilir, gerektiğinde yenileyin
