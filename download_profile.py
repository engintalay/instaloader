#!/usr/bin/env python3
"""CLI downloader backed by the same user-folder architecture as the GUI."""

import sys

from app_backend import FileIndexDB, download_instagram_profile, ensure_user_dirs


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Kullanım: {sys.argv[0]} <profil_adı> [kaynak] [kullanıcı_adı]")
        print("Kaynak: file | chrome | firefox | <cookie_json_yolu>")
        print("Kullanıcı adı verilmezse profil adı kullanılır")
        sys.exit(1)

    profile = sys.argv[1].strip()
    source = sys.argv[2].strip() if len(sys.argv) > 2 else "file"
    user_name = sys.argv[3].strip() if len(sys.argv) > 3 else profile

    db = FileIndexDB()
    ensure_user_dirs(user_name)

    result = download_instagram_profile(
        user_name=user_name,
        profile=profile,
        source=source,
        db=db,
        log=print,
    )
    if not result.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
