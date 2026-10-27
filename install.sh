#!/bin/sh
# Install or update VAD-OS Spark Monitor from the latest GitHub Release.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/FractalRainbowDot/vad-os-spark-monitor/main/install.sh | sh
#
# Optional environment variables:
#   SPARK_MONITOR_HOME  data directory (default: ~/.local/share/vad-os-spark-monitor)
#   SPARK_MONITOR_BIN   launcher directory (default: ~/.local/bin)
#   PYTHON              Python interpreter (default: python3)

set -eu

REPO="${SPARK_MONITOR_REPO:-FractalRainbowDot/vad-os-spark-monitor}"
ASSET="spark-monitor.pyz"
BASE="${SPARK_MONITOR_RELEASE_URL:-https://github.com/$REPO/releases/latest/download}"
DATA_DIR="${SPARK_MONITOR_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/vad-os-spark-monitor}"
BIN_DIR="${SPARK_MONITOR_BIN:-$HOME/.local/bin}"
PYTHON="${PYTHON:-python3}"

die() {
    printf 'Ошибка: %s\n' "$*" >&2
    exit 1
}

path_block() {
    "$PYTHON" - "$1" <<'PY'
import shlex
import sys

bin_dir = sys.argv[1]
print('# >>> VAD-OS Spark Monitor >>>')
print('spark_monitor_bin=' + shlex.quote(bin_dir))
print('case ":$PATH:" in')
print('    *":$spark_monitor_bin:"*) ;;')
print('    *) PATH="$spark_monitor_bin:$PATH"; export PATH ;;')
print('esac')
print('unset spark_monitor_bin')
print('# <<< VAD-OS Spark Monitor <<<')
PY
}

command -v curl >/dev/null 2>&1 || die 'не найден curl'
command -v "$PYTHON" >/dev/null 2>&1 || die "не найден $PYTHON"
command -v uname >/dev/null 2>&1 || die 'не найден uname'

case "$(uname -s)" in
    Linux|Darwin) ;;
    *) die 'поддерживаются Linux и macOS' ;;
esac

if ! "$PYTHON" -c 'import sys, curses; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    die "нужен Python 3.10+ с модулем curses; на macOS можно использовать ZIP из Releases"
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/spark-monitor-install.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

printf 'Скачиваю последний релиз…\n'
curl -fsSL --retry 3 --connect-timeout 10 "$BASE/$ASSET" -o "$tmp/$ASSET" \
    || die 'не удалось скачать spark-monitor.pyz'
curl -fsSL --retry 3 --connect-timeout 10 "$BASE/$ASSET.sha256" -o "$tmp/$ASSET.sha256" \
    || die 'не удалось скачать checksum'

expected="$(awk 'NR == 1 { print $1 }' "$tmp/$ASSET.sha256")"
case "$expected" in
    ''|*[!0-9a-fA-F]*) die 'checksum имеет неверный формат' ;;
esac
[ "${#expected}" -eq 64 ] || die 'checksum имеет неверную длину'

if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$tmp/$ASSET" | awk '{ print $1 }')"
elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$tmp/$ASSET" | awk '{ print $1 }')"
else
    die 'нужен sha256sum или shasum'
fi
[ "$actual" = "$expected" ] || die 'SHA-256 не совпал; установка отменена'

if ! "$PYTHON" - "$tmp/$ASSET" <<'PY'
import sys
import zipfile

path = sys.argv[1]
with zipfile.ZipFile(path) as archive:
    names = archive.namelist()
    if '__main__.py' not in names or archive.testzip() is not None:
        raise SystemExit(1)
    if any(name.startswith(('/', '../')) or '/../' in name for name in names):
        raise SystemExit(1)
PY
then
    die 'скачанный файл не является программой монитора'
fi

mkdir -p "$DATA_DIR" "$BIN_DIR"
chmod 700 "$DATA_DIR" 2>/dev/null || true

target="$DATA_DIR/$ASSET"
if [ -f "$target" ]; then
    cp -p "$target" "$target.prev" 2>/dev/null || true
fi
install -m 755 "$tmp/$ASSET" "$target" || die "не удалось записать $target"

launcher="$BIN_DIR/spark-monitor"
launcher_tmp="$BIN_DIR/.spark-monitor-launcher.$$"
"$PYTHON" - "$launcher_tmp" "$PYTHON" "$target" <<'PY'
import shlex
import sys

path, python, archive = sys.argv[1:4]
with open(path, 'w', encoding='utf-8') as stream:
    stream.write('#!/bin/sh\nexec ' + shlex.quote(python) + ' '
                 + shlex.quote(archive) + ' "$@"\n')
PY
chmod 755 "$launcher_tmp"
mv "$launcher_tmp" "$launcher"

version="$("$PYTHON" "$target" --version 2>/dev/null || true)"
printf '\nУстановлено: %s\n' "$target"
[ -n "$version" ] && printf 'Версия: %s\n' "$version"
printf 'Команда: %s\n' "$launcher"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        if [ "${SPARK_MONITOR_NO_PATH_UPDATE:-0}" = '1' ]; then
            printf 'Добавьте в PATH вручную:\n  export PATH="%s:$PATH"\n' "$BIN_DIR"
        else
            case "$(basename "${SHELL:-}")" in
                zsh) rc="$HOME/.zshrc" ;;
                bash)
                    if [ "$(uname -s)" = 'Darwin' ]; then
                        rc="$HOME/.bash_profile"
                    else
                        rc="$HOME/.bashrc"
                    fi
                    ;;
                sh|dash) rc="$HOME/.profile" ;;
                *) rc='' ;;
            esac
            if [ -n "$rc" ] && mkdir -p "$(dirname "$rc")" && touch "$rc"; then
                if grep -Fq '# >>> VAD-OS Spark Monitor >>>' "$rc"; then
                    printf 'PATH уже настроен в %s\n' "$rc"
                elif block="$(path_block "$BIN_DIR")" && printf '\n%s\n' "$block" >> "$rc"; then
                    printf 'PATH добавлен в %s\n' "$rc"
                    printf 'Откройте новый терминал или выполните: source %s\n' "$rc"
                else
                    printf 'Не удалось изменить %s; добавьте вручную:\n' "$rc"
                    printf '  export PATH="%s:$PATH"\n' "$BIN_DIR"
                fi
            else
                printf 'Добавьте в PATH вручную:\n  export PATH="%s:$PATH"\n' "$BIN_DIR"
            fi
        fi
        ;;
esac

if [ -s "$DATA_DIR/.env" ]; then
    printf 'Ключ уже сохранён рядом: %s\n' "$DATA_DIR/.env"
else
    printf 'Сохраните ключ LiteLLM: %s --save-key\n' "$launcher"
fi
printf 'Запуск: %s\n' "$launcher"
printf 'Если монитор уже запущен, перезапустите его.\n'
