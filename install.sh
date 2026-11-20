#!/usr/bin/env bash
# KDE Roomba – installatie voor Fedora KDE (Plasma 6)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/.local/share/kde-roomba"
BIN="${HOME}/.local/bin"
APPS="${HOME}/.local/share/applications"
AUTOSTART="${HOME}/.config/autostart"
MODEL="${KDE_ROOMBA_MODEL:-qwen2.5:1.5b}"

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*"; }
ask() { local a; read -r -p "$1 [J/n] " a || true; [[ -z "$a" || "$a" =~ ^[JjYy] ]]; }

# 1. Afhankelijkheden ---------------------------------------------------
# python3-pyqt6 (systeem-Qt) en layer-shell-qt (zit al in Plasma) – geen
# wijzigingen aan je desktopinstellingen.
missing=()
rpm -q python3-pyqt6 >/dev/null 2>&1 || missing+=(python3-pyqt6)
rpm -q layer-shell-qt >/dev/null 2>&1 || missing+=(layer-shell-qt)
if [ ${#missing[@]} -gt 0 ]; then
    say "Pakketten installeren: ${missing[*]}"
    sudo dnf install -y "${missing[@]}"
fi
if python3 -c 'import PyQt6, os, sys; sys.exit(0 if os.path.isdir(os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "lib")) else 1)' 2>/dev/null; then
    warn "Er is ook een PyQt6 via pip geïnstalleerd; die gaat voor en kan geen layer-shell gebruiken."
    warn "Verwijder hem met:  pip uninstall PyQt6 PyQt6-Qt6 PyQt6-sip"
fi

# 2. Programma kopiëren -------------------------------------------------
say "Programma installeren in ${PREFIX}"
mkdir -p "$PREFIX" "$BIN" "$APPS" "$AUTOSTART"
rm -rf "${PREFIX}/kde_roomba"
cp -r "${SRC}/kde_roomba" "$PREFIX/"
find "$PREFIX" -name '__pycache__' -prune -exec rm -rf {} +

cat > "${BIN}/kde-roomba" <<LAUNCHER
#!/usr/bin/env bash
if [ "\$(id -u)" -eq 0 ]; then
    echo "KDE Roomba hoort bij jouw bureaublad: start hem ZONDER sudo, gewoon:  kde-roomba" >&2
    exit 1
fi
cd "${PREFIX}" && exec python3 -m kde_roomba "\$@"
LAUNCHER
chmod +x "${BIN}/kde-roomba"

sed "s|@BIN@|${BIN}|g" "${SRC}/kde-roomba.desktop" > "${APPS}/kde-roomba.desktop"
if ask "Automatisch starten bij inloggen?"; then
    cp "${APPS}/kde-roomba.desktop" "${AUTOSTART}/kde-roomba.desktop"
fi
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true

# 3. Lokale AI (Ollama) -------------------------------------------------
if ask "Lokaal AI-model installeren via Ollama (model: ${MODEL}, ±1 GB)?"; then
    if ! command -v ollama >/dev/null; then
        say "Ollama installeren…"
        if ! sudo dnf install -y ollama; then
            warn "Niet in dnf gevonden; officiële installer van ollama.com gebruiken."
            curl -fsSL https://ollama.com/install.sh | sh
        fi
    fi
    if ! curl -fs http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        say "Ollama-service starten…"
        sudo systemctl enable --now ollama 2>/dev/null || (nohup ollama serve >/dev/null 2>&1 &)
        sleep 3
    fi
    say "Model ${MODEL} downloaden…"
    ollama pull "$MODEL"
else
    warn "Geen AI: de roomba gebruikt dan zijn ingebouwde regels (heuristiek)."
fi

# 4. Meteen starten en controleren ----------------------------------------
LOG="${XDG_STATE_HOME:-$HOME/.local/state}/kde-roomba/roomba.log"
pkill -f "python3 -m kde_roomba" 2>/dev/null || true
sleep 0.5
rm -f "$LOG"
say "Roomba starten…"
setsid "${BIN}/kde-roomba" >/dev/null 2>&1 < /dev/null &
for _ in $(seq 1 20); do
    grep -q "Venster getoond" "$LOG" 2>/dev/null && break
    sleep 0.5
done
if grep -q "Venster getoond" "$LOG" 2>/dev/null; then
    say "De roomba staat rechtsonder op je bureaublad. Dubbelklik erop om op te ruimen!"
    grep "Vensterlaag" "$LOG" | sed 's/^[^ ]* [^ ]* INFO /    /'
else
    warn "De roomba lijkt niet gestart. Laatste regels van $LOG:"
    tail -n 25 "$LOG" 2>/dev/null || warn "(geen logbestand – start hem handmatig met: ${BIN}/kde-roomba)"
fi
say "Later opnieuw starten: kde-roomba (zonder sudo) of via het menu: 'KDE Roomba'"
case ":$PATH:" in *":${BIN}:"*) ;; *) warn "${BIN} staat niet in je PATH; start met ${BIN}/kde-roomba";; esac
