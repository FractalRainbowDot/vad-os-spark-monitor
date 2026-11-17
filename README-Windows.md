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

## Запуск из клона репозитория

Отдельный шаг установки зависимостей не нужен:

```powershell
git clone https://github.com/FractalRainbowDot/vad-os-spark-monitor.git
cd vad-os-spark-monitor
.\run.cmd
```

`run.cmd` — обёртка над `run.ps1`, которая:

- находит Python 3.10+ (`py -3`, затем `python`, `python3`);
- при первом запуске ставит `windows-curses` через pip: в user site, а внутри
  виртуального окружения — без `--user`;
- включает `PYTHONUTF8=1`, чтобы рамки и кириллица рисовались правильно;
- запускает монитор из исходников (`__main__.py`).

Зависимости описаны в `requirements.txt`. Ключ LiteLLM сохраняется один раз:

```powershell
.\run.ps1 --save-key
.\run.cmd
```

`.env` и `.spark-monitor.json` создаются рядом с исходниками и исключены из git.
Монитор, запущенный из исходников, не проверяет автообновление: обновляется
только файл `.pyz`. Для постоянного использования поставьте релиз через
`install.ps1` ниже.

## Установка

В PowerShell:

```powershell
irm https://raw.githubusercontent.com/FractalRainbowDot/vad-os-spark-monitor/main/install.ps1 | iex
```

Установщик:

- находит Python 3.10+;
- при необходимости устанавливает пакет `windows-curses`;
- проверяет, что OpenSSH и Tailscale доступны;
- скачивает windows-сборку `spark-monitor-windows.pyz` (если её нет в релизе —
  универсальный `spark-monitor.pyz`);
- проверяет SHA-256;
- устанавливает программу в `%LOCALAPPDATA%\vad-os-spark-monitor` под именем
  `spark-monitor.pyz`;
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

Если установщик не подходит, скачайте из Releases `spark-monitor-windows.pyz`
и запустите:

```powershell
py -3 spark-monitor-windows.pyz --save-key
py -3 spark-monitor-windows.pyz
```

`windows-curses` можно не ставить вручную: при первом интерактивном запуске
монитор сам вызовет pip, если модуля нет. Файл можно переименовать в
`spark-monitor.pyz` — имя не влияет на работу.

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
