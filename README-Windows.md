# VAD-OS Spark Monitor · Windows 10/11

Нативная Windows-установка. Python, `windows-curses`, OpenSSH и Tailscale нужны
только на компьютере оператора; на Spark ничего устанавливать не нужно.

## Что должно быть установлено

- Windows 10/11 и Windows Terminal (рекомендуется для Unicode-рамок).
- Python 3.10+ с сайта python.org.
- OpenSSH Client — компонент Windows:
  ```powershell
  Get-WindowsCapability -Online -Name OpenSSH.Client*
  ```
  Если компонента нет, установите его в «Дополнительных компонентах Windows»
  или выполните в PowerShell от администратора:
  ```powershell
  Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
  ```
- Tailscale для Windows, вход в тот же tailnet, где находятся Spark.
- SSH-ключ, разрешённый на Spark. Монитор не копирует ключи и не хранит пароль.

## Установка

В PowerShell:

```powershell
irm https://raw.githubusercontent.com/FractalRainbowDot/vad-os-spark-monitor/main/install.ps1 | iex
```

Установщик:

- находит Python 3.10+;
- при необходимости устанавливает пакет `windows-curses`;
- проверяет, что OpenSSH и Tailscale доступны;
- скачивает последний `spark-monitor.pyz`;
- проверяет SHA-256;
- устанавливает программу в `%LOCALAPPDATA%\vad-os-spark-monitor`;
- создаёт команду `spark-monitor` и добавляет её в PATH пользователя.

Если команда `spark-monitor` не видна сразу, откройте новый терминал.

Проверить SSH до Spark (адрес подставьте свой):

```powershell
ssh -o BatchMode=yes nvidia@100.x.y.z hostname
```

Если SSH-ключ ещё не разрешён на Spark, сначала добавьте его. Например, из
PowerShell:

```powershell
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh nvidia@100.x.y.z "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

Затем сохраните ключ LiteLLM и запустите монитор:

```powershell
spark-monitor --save-key
spark-monitor
```

## Ручная установка

Если установщик не подходит:

```powershell
py -3 -m pip install --user windows-curses
py -3 spark-monitor.pyz --save-key
py -3 spark-monitor.pyz
```

Для полноценной команды `spark-monitor` используйте `install.ps1`. Автообновление
работает при запуске `.pyz`; после обновления нажмите `[r]` в мониторе.

## Файлы и права

- `.env` и `.spark-monitor.json` лежат рядом с `spark-monitor.pyz`.
- Ключ LiteLLM хранится только в `.env`; не передавайте этот файл другим.
- Установщик размещает программу в `%LOCALAPPDATA%` и ограничивает доступ к
  каталогу текущему пользователю.
- Tailscale и SSH-ключи остаются в вашем профиле Windows и не попадают в релиз.

## Если что-то не работает

```powershell
py -3 -c "import curses; print('curses OK')"
ssh -V
tailscale status
py -3 "$env:LOCALAPPDATA\vad-os-spark-monitor\spark-monitor.pyz" --version
```

- `curses` не импортируется — повторите установку `windows-curses`.
- `ssh` не найден — включите OpenSSH Client.
- Tailscale не найден — установите Tailscale; программа также проверяет
  `C:\Program Files\Tailscale\tailscale.exe`.
- SSH просит пароль или зависает — монитор работает в `BatchMode=yes` и ждёт
  уже настроенный ключ/агент, а не вводит пароль.
