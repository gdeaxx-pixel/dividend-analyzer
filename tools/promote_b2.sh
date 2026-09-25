#!/bin/zsh
# Corre promote_case.py contra el bucket B2 con la clave LOCAL (lectura y borrado), leída
# del Llavero de macOS. La clave nunca se escribe en disco ni se imprime.
#   tools/promote_b2.sh --list
#   tools/promote_b2.sh --show <broker> <case_id>
#   tools/promote_b2.sh --promote <broker> <case_id>
#   tools/promote_b2.sh --delete <broker> <case_id>
set -e
llavero() { security find-generic-password -s b2-captura-local -a "$1" -w 2>/dev/null \
  || { echo "Falta '$1' en el Llavero (servicio b2-captura-local)." >&2; exit 1; } }
export CAPTURE_B2_BUCKET="${CAPTURE_B2_BUCKET:-iyg-dividend-casos-k7p2qx}"
export CAPTURE_B2_ENDPOINT="${CAPTURE_B2_ENDPOINT:-https://s3.us-east-005.backblazeb2.com}"
export CAPTURE_B2_KEY_ID="$(llavero key_id)"
export CAPTURE_B2_APP_KEY="$(llavero application_key)"
unset CAPTURE_LOCAL_DIR
cd "$(dirname "$0")/.."
exec env -u PYTHONPATH ./.venv/bin/python promote_case.py "$@"
