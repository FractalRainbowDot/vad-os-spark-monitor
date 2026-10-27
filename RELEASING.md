# Выпуск новой версии

1. Измените `VERSION` в `updater.py` (например, `1.0.2`). Версия обязана расти,
   иначе клиенты не увидят обновление.
2. Соберите `.pyz` из исходников. В архив должны попасть только:
   `__main__.py`, `credentials.py`, `litellm_usage.py`, `discovery.py`, `hosts.py`,
   `settings.py`, `updater.py`, `README.md`, `LICENSE`.
3. Проверьте, что в сборке нет `.env`, ключей и адресов кластера.
4. Закоммитьте файлы и создайте GitHub Release с тегом `vX.Y.Z`.
5. Приложите к релизу:
   - `spark-monitor.pyz`;
   - `spark-monitor.pyz.sha256` — строка `<sha256>  spark-monitor.pyz`;
   - `install.sh` — установщик для `curl | sh`;
   - при необходимости обновлённый macOS ZIP.

Клиенты скачивают только asset `spark-monitor.pyz`, проверяют SHA-256 и
заменяют файл. Приватные ключи, `.env` и встроенный Python macOS не обновляются.

Пример сборки:

```bash
mkdir -p build
cp __main__.py credentials.py litellm_usage.py discovery.py hosts.py settings.py updater.py README.md LICENSE build/
python3 -c "import zipapp; zipapp.create_archive('build', 'spark-monitor.pyz', interpreter='/usr/bin/env python3', compressed=True)"
python3 -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('spark-monitor.pyz').read_bytes()).hexdigest() + '  spark-monitor.pyz')" > spark-monitor.pyz.sha256
```
