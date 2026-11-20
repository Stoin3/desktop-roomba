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
if ! python3 -c 'import PyQt6.QtWidgets' 2>/dev/null; then
    say "PyQt6 installeren (sudo dnf install python3-pyqt6)…"
    sudo dnf install -y python3-pyqt6
fi

# 2. Programma kopiëren -------------------------------------------------
say "Programma installeren in ${PREFIX}"
mkdir -p "$PREFIX" "$BIN" "$APPS" "$AUTOSTART"
rm -rf "${PREFIX}/kde_roomba"
cp -r "${SRC}/kde_roomba" "$PREFIX/"
find "$PREFIX" -name '__pycache__' -prune -exec rm -rf {} +

cat > "${BIN}/kde-roomba" <<LAUNCHER
#!/usr/bin/env bash
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

say "Klaar! Start met:  kde-roomba   (of via het menu: 'KDE Roomba')"
case ":$PATH:" in *":${BIN}:"*) ;; *) warn "${BIN} staat niet in je PATH; start met ${BIN}/kde-roomba";; esac
