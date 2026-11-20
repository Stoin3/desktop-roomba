#!/usr/bin/env bash
# KDE Roomba verwijderen (je config en geschiedenis blijven staan, tenzij --purge)
set -euo pipefail
pkill -f "python3 -m kde_roomba" 2>/dev/null || true
if [ -d "${HOME}/.local/share/kde-roomba" ]; then
    (cd "${HOME}/.local/share/kde-roomba" && python3 -c 'from kde_roomba import kwin; kwin.remove_rule_if_present()') || true
fi
rm -rf "${HOME}/.local/share/kde-roomba" "${HOME}/.local/bin/kde-roomba" \
       "${HOME}/.local/share/applications/kde-roomba.desktop" "${HOME}/.config/autostart/kde-roomba.desktop"
if [ "${1:-}" = "--purge" ]; then
    rm -rf "${HOME}/.config/kde-roomba" "${HOME}/.local/state/kde-roomba"
fi
echo "KDE Roomba is verwijderd. (Ollama en het model zijn niet aangeraakt: 'ollama rm qwen2.5:1.5b')"
