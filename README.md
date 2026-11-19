# VAD-OS Spark Monitor

Терминальный монитор Spark-машин: GPU/RAM, запущенные модели и статистика
LiteLLM. Находит машины через Tailscale, не требует установки агента на Spark.

## Что нужно

- **Tailscale**: войти в ту же сеть, где находятся Spark.
- **OpenSSH Client**: команда `ssh` должна быть доступна.
- Доступ к Spark: готовый SSH-ключ или пароль пользователя (по умолчанию `nvidia`).
- **Python 3.10+**. Исключение — macOS Apple Silicon ZIP: Python уже внутри.
- Ключ LiteLLM — только для статистики LiteLLM; остальные экраны работают без него.

## Windows 10/11

### Установка одной командой (с ярлыком)

Нужен установленный Python 3.10+ (при установке отметьте **Add Python to PATH**).
Git не нужен. Откройте **PowerShell** и вставьте:

```powershell
irm https://raw.githubusercontent.com/FractalRainbowDot/vad-os-spark-monitor/main/install.ps1 | iex
```

Установщик скачает Windows-сборку, установит `windows-curses` и создаст
**VAD-OS Spark Monitor** с иконкой на рабочем столе. Откройте ярлык:
настройка SSH и ввод ключа LiteLLM пройдут в том же окне.
Программа хранится в `%LOCALAPPDATA%\vad-os-spark-monitor`.
Повторный запуск команды обновляет программу и ярлык, сохраняя ключ и настройки.
Если загрузка иконки недоступна, ярлык получит стандартную иконку терминала.

### Альтернатива: из репозитория

Установите Python 3.10+ (отметьте **Add Python to PATH**) и Git.
Откройте **PowerShell** и выполните:

```powershell
git clone https://github.com/FractalRainbowDot/vad-os-spark-monitor.git
cd vad-os-spark-monitor
powershell -NoProfile -ExecutionPolicy Bypass -File .\make-shortcut.ps1
```

На рабочем столе появится **VAD-OS Spark Monitor** с иконкой-молнией.
Откройте ярлык — зависимость `windows-curses` установится автоматически.
Не перемещайте папку репозитория после создания ярлыка.

Также доступна команда `spark-monitor`. Если команда не найдена сразу после
установки, откройте новый терминал.

## macOS

**Apple Silicon (M1 и новее), без установки Python:**

1. Скачайте [macOS Apple Silicon ZIP](https://github.com/FractalRainbowDot/vad-os-spark-monitor/releases/latest/download/VAD-OS-Spark-Monitor-macOS-Apple-Silicon.zip).
2. Распакуйте архив целиком.
3. Откройте `Start Spark Monitor.command`. Не удаляйте папку `runtime`.

Сборка не подписана Apple. Если macOS блокирует запуск, следуйте
`README-Mac.md` внутри архива. ZIP не подходит для Intel Mac.

**Intel или Apple Silicon с Python 3.10+:** используйте установщик ниже.

## Linux / macOS с Python

Нужен Python 3.10+ с модулем `curses`.

```bash
curl -fsSL https://raw.githubusercontent.com/FractalRainbowDot/vad-os-spark-monitor/main/install.sh | sh
spark-monitor
```

Если команда не найдена после установки, откройте новый терминал.
Установщики скачивают сборку для вашей ОС и проверяют SHA-256.
Скрипты можно предварительно изучить: [Windows](install.ps1), [Linux/macOS](install.sh).

## Первый запуск

Всё происходит **в том же окне**, без копирования команд:

1. Монитор находит включённые Linux-машины `spark-*` в Tailscale.
2. Проверяет SSH. При необходимости предлагает подтвердить отпечаток сервера
   (сверьте с администратором), ввести пароль и разрешить добавление публичного
   ключа на Spark. Пароли не сохраняются.
3. Предлагает ввести ключ LiteLLM скрытым вводом. Enter — пропустить.
4. Открывает монитор. Рабочие SSH-подключения и сохранённый ключ повторной настройки не требуют.

Ключ LiteLLM хранится в `.env` рядом с программой. **Не передавайте этот файл
или приватный SSH-ключ другим людям.** Новый ключ можно сохранить через `--save-key`;
`--no-setup` отключает мастер.

## Управление

| Клавиша | Действие |
|---|---|
| `v` | Модели и метрики |
| `l` | Статистика LiteLLM |
| `s` | Настройки провайдеров и Spark (Static) |
| `m` | Тема и имя в шапке |
| `Tab` | Переключить вкладку |
| `h` | Пояснения |
| `-` / `+` | Частота обновления |
| `r` | Перезапустить после обновления |
| `q` | Выход |

## Обновления и справка

- Установленные `.pyz` проверяют релизы автоматически. После обновления нажмите
  `r` или перезапустите монитор. Ключ и настройки сохраняются.
- Запуск из клона (`run.cmd`) использует исходники: обновляйте их через `git pull`.
- [Все сборки и версии](https://github.com/FractalRainbowDot/vad-os-spark-monitor/releases).
- [Windows: подробности и диагностика](README-Windows.md).
- [Расширенная справка: SSH, LiteLLM 403, параметры, управление](docs/REFERENCE.md).
- [Сборка и выпуск релиза](RELEASING.md).

## Лицензия

[MIT](LICENSE), © 2026 VAD-OS. Встроенный Python в macOS ZIP распространяется
по собственной лицензии PSF (текст находится в `runtime/lib/python3.13/LICENSE.txt`).
