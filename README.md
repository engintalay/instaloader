# 📸 Instagram Profile Downloader

Tarayıcı cookie'lerini kullanarak Instagram profillerini indiren konsol uygulaması.

## Özellikler

- 🖼️ Fotoğraf, video ve carousel postları indirir
- 🏷️ **Etiketli postları** indirir (profilin etiketlendiği resimler)
- 🎯 Highlights (öne çıkan hikayeler) indirir
- 📱 Stories (hikayeler) indirir
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

# Belirli bir kullanıcı klasörüne çek
./run.sh <profil_adı> file <kullanıcı_adı>
```

## GUI (Görsel Arayüz)

```bash
./run_gui.sh
```

GUI ile:

- Kullanıcı bazlı klasör oluşturma (`users/<kullanıcı>/`)
- Arka planda indirme kuyruğu
- Manuel dosya ekleme (silinen/mevcut dosyaları geri eklemek için)
- Kullanıcı klasörü altındaki tüm dosyaları SQLite ile indeksleme
- Çoklu cookie dosyası yönetimi (listele, ekle, seç, varsayılan yap)
- Uygulama içinde resim/video önizleme
- Resimler için thumbnail, videolar için ffmpeg varsa otomatik thumbnail
- Dosya tablosuna ek olarak tıklanabilir thumbnail galeri (grid görünüm)

SQLite dosyası: `file_index.db`

Cookie yönetimi:

- Mevcut cookie dosyaları otomatik algılanır (`cookies.json`, `*_cookies.json`, `cookie_files/*.json`)
- GUI içinden yeni cookie JSON dosyası eklenebilir
- Seçili cookie dosyası `selected-cookie` kaynağı ile indirme kuyruğunda kullanılabilir
- Seçili cookie tek tıkla varsayılan `cookies.json` dosyası yapılabilir

Not: Video thumbnail üretimi için sistemde `ffmpeg` kurulu olmalıdır. `ffmpeg` yoksa video için placeholder önizleme gösterilir.

## Dosya Yapısı

```
.
├── install.sh              # Kurulum scripti
├── run.sh                  # Çalıştırma scripti
├── run_gui.sh              # GUI başlatma scripti
├── download_profile.py     # Ana uygulama
├── gui_app.py              # Görsel arayüz
├── app_backend.py          # Ortak backend + SQLite indeks
├── cookies.json            # Cookie dosyası (gitignore'da)
├── cookies.example.json    # Örnek cookie dosyası
├── file_index.db           # File-based SQL index (SQLite)
└── users/
    └── <kullanıcı>/
        ├── downloads/      # İndirilen medya
        ├── manual/         # Elle eklenen dosyalar
        └── ...
```

## ⚠️ Uyarılar

- Kısa sürede çok fazla profil indirmekten kaçının (rate limiting)
- Script çalışırken tarayıcıda Instagram'ı aktif kullanmayın
- Cookie'lerin süresi dolabilir, gerektiğinde yenileyin
- **Etiketli postları indirmek için giriş yapılmış olması gerekir**
