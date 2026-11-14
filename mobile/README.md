# Mobile клиент вынесен

Исходники Flutter: sibling **`../punzh-dict-mobile`**
(`~/Projects/KRL/punzh-dict-mobile`).

В этом monorepo остаются:

- контракт пакета — [`docs/plans/mobile-pack-contract.md`](../docs/plans/mobile-pack-contract.md)
- экспортёр — `app/dict/mobile/`, `manage.py export_mobile_db`
- publish данных — [`scripts/publish_mobile_pack.sh`](../scripts/publish_mobile_pack.sh) → `/mobile-pack/`
- publish APK — [`scripts/publish_apk.sh`](../scripts/publish_apk.sh) → `/downloads/punzh-dict.apk`
- баннер Android на сайте (RuStore + APK) — `partials/android_app_banner.html`
- план/бэклог — [`docs/plans/mobile-offline.md`](../docs/plans/mobile-offline.md)

Семантика словаря для приложения: `punzh-dict-mobile/docs/DICTIONARY.md`.
