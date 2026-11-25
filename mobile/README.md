# Mobile клиент вынесен

Исходники Flutter: sibling **`../punzh-dict-mobile`**
(`~/Projects/KRL/punzh-dict-mobile`).

В этом monorepo остаются:

- контракт пакета — [`docs/plans/mobile-pack-contract.md`](../docs/plans/mobile-pack-contract.md)
- экспортёр — `app/dict/mobile/`, `manage.py export_mobile_db`
- publish данных — [`scripts/publish_mobile_pack.sh`](../scripts/publish_mobile_pack.sh) → `/mobile-pack/`
- publish APK — sibling `punzh-dict-mobile/scripts/publish_downloads.sh` → `/mobile-pack/punzh-dict-latest.apk`
- страница «О приложении» — `/app/` (`staticPages/mobile_app.html`); версия из `app-manifest.json`
- баннер Android на сайте (RuStore + APK + версия) — `partials/android_app_banner.html`
- счётчик APK: клик идёт на `/app/apk/` → `ApkDownloadStat` → редирект на файл;
  админка / `manage.py set_apk_download_count`; исторические хиты —
  `scripts/count_apk_nginx_hits.sh`

Функции v1: `punzh-dict-mobile/docs/FEATURES-V1.md`.  
Беклог следующей версии: `punzh-dict-mobile/docs/BACKLOG.md`.  
Семантика словаря: `punzh-dict-mobile/docs/DICTIONARY.md`.
