#!/usr/bin/env python3
"""Instagram profil indirici - cookie dosyasından veya tarayıcıdan."""

import json
import os
import sys
import instaloader

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.json")


def get_cookies_from_file():
    with open(COOKIE_FILE) as f:
        return json.load(f)


def get_cookies_chrome():
    from pycookiecheat import chrome_cookies
    return chrome_cookies("https://www.instagram.com")


def get_cookies_firefox():
    import browser_cookie3
    cj = browser_cookie3.firefox(domain_name=".instagram.com")
    return {c.name: c.value for c in cj if "instagram" in c.domain}


BROWSERS = {
    "file": get_cookies_from_file,
    "chrome": get_cookies_chrome,
    "firefox": get_cookies_firefox,
}


def main():
    if len(sys.argv) < 2:
        print(f"Kullanım: {sys.argv[0]} <profil_adı> [kaynak]")
        print(f"Kaynaklar: {', '.join(BROWSERS)}, veya cookie dosya yolu")
        sys.exit(1)

    profile = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else "file"

    if source not in BROWSERS and os.path.isfile(source):
        with open(source) as f:
            cookies = json.load(f)
    elif source in BROWSERS:
        cookies = BROWSERS[source]()
    else:
        print(f"Desteklenmeyen kaynak veya dosya bulunamadı: {source}")
        print(f"Seçenekler: {', '.join(BROWSERS)}, veya cookie dosya yolu")
        sys.exit(1)

    print(f"[*] {source} cookie'leri alınıyor...")

    if "sessionid" not in cookies:
        print("[!] Instagram oturumu bulunamadı.")
        sys.exit(1)

    L = instaloader.Instaloader(
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
    )
    L.load_session("_temp_", cookies)
    username = L.test_login()
    if not username:
        print("[!] Cookie'ler geçersiz veya süresi dolmuş.")
        sys.exit(1)

    L.load_session(username, cookies)
    print(f"[+] {username} olarak giriş yapıldı.")

    print(f"[*] {profile} profili indiriliyor...")
    try:
        prof = instaloader.Profile.from_username(L.context, profile)
        L.download_profile(profile, profile_pic_only=False, fast_update=True)
        print(f"[*] Highlights indiriliyor...")
        L.download_highlights(prof)
        print(f"[+] {profile} başarıyla indirildi.")
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"[!] Profil bulunamadı: {profile}")
    except instaloader.exceptions.PrivateProfileNotFollowedException:
        print(f"[!] Gizli profil, takip etmiyorsunuz: {profile}")
    except instaloader.exceptions.LoginRequiredException:
        print(f"[!] Bu profil için giriş gerekli.")


if __name__ == "__main__":
    main()
