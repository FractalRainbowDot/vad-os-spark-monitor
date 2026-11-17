# Выпуск новой версии

1. Измените `VERSION` в `updater.py` (например, `1.9.1`). Версия обязана расти,
   иначе клиенты не увидят обновление.
2. Соберите архивы одной командой:

   ```bash
   python3 build.py
   ```

   Скрипт создаёт в `dist/`:

   - `spark-monitor-windows.pyz` и `.sha256` — без shebang, запускается как
     `python spark-monitor-windows.pyz`;
   - `spark-monitor-linux.pyz` и `.sha256`;
   - `spark-monitor-macos.pyz` и `.sha256`;

   и обновляет универсальный `spark-monitor.pyz` и `.sha256` в корне репозитория.

   В каждый архив попадают только: `__main__.py`, `credentials.py`,
   `litellm_usage.py`, `discovery.py`, `hosts.py`, `settings.py`, `updater.py`,
   `banner.py`, `preferences.py`, `platform_utils.py`, `themes.py`, `README.md`,
   `LICENSE` и `build-info.json` (платформа и версия сборки).
3. Проверьте, что в сборке нет `.env`, ключей и адресов кластера.
4. Закоммитьте файлы и создайте GitHub Release с тегом `vX.Y.Z`.
5. Приложите к релизу:
   - `dist/spark-monitor-windows.pyz` + `.sha256`;
   - `dist/spark-monitor-linux.pyz` + `.sha256`;
   - `dist/spark-monitor-macos.pyz` + `.sha256`;
   - `spark-monitor.pyz` + `spark-monitor.pyz.sha256` — универсальный архив,
     который остаётся fallback для старых установок и незнакомых платформ;
   - `install.sh` — установщик для Linux и macOS;
   - `install.ps1` — нативный установщик для Windows;
   - `README-Windows.md`;
   - при необходимости обновлённый macOS ZIP.

Клиенты выбирают asset по системе (`updater.platform_asset`: `win32` →
`spark-monitor-windows.pyz`, `linux` → `spark-monitor-linux.pyz`, `darwin` →
`spark-monitor-macos.pyz`), скачивают только его, проверяют SHA-256 и заменяют
локальный `spark-monitor.pyz`. Если платформенного архива в релизе нет,
используется универсальный. Приватные ключи, `.env` и встроенный Python
macOS не обновляются.

Пример одиночной сборки без `build.py`:

```bash
mkdir -p build
cp __main__.py credentials.py litellm_usage.py discovery.py hosts.py settings.py updater.py banner.py preferences.py platform_utils.py themes.py README.md LICENSE build/
python3 -c "import zipapp; zipapp.create_archive('build', 'spark-monitor.pyz', interpreter='/usr/bin/env python3', compressed=True)"
python3 -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('spark-monitor.pyz').read_bytes()).hexdigest() + '  spark-monitor.pyz')" > spark-monitor.pyz.sha256
```
