#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_HOST="${SPB_HOST:-127.0.0.1}"
APP_PORT="${SPB_PORT:-8080}"
APP_URL="http://localhost:8080/"
STARTUP_TIMEOUT="${SPB_STARTUP_TIMEOUT:-300}"
LOG_FILE="${SCRIPT_DIR}/data/kiosk-backend.log"
BACKEND_PID=""

if [[ "${EUID}" -eq 0 ]]; then
    echo "Do not run the kiosk as root; launch it from the Raspberry Pi desktop user." >&2
    exit 1
fi

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "No desktop display session found. Start this launcher from the Raspberry Pi desktop." >&2
    exit 1
fi

if command -v chromium-browser >/dev/null 2>&1; then
    BROWSER="$(command -v chromium-browser)"
elif command -v chromium >/dev/null 2>&1; then
    BROWSER="$(command -v chromium)"
else
    echo "Chromium is not installed. Install it with: sudo apt install chromium" >&2
    exit 1
fi

PYTHON="${SPB_PYTHON:-${SCRIPT_DIR}/../.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
    PYTHON="$(command -v python3 || true)"
fi
if [[ -z "${PYTHON}" || ! -x "${PYTHON}" ]]; then
    echo "Python not found. Set SPB_PYTHON to the SPB virtual environment interpreter." >&2
    exit 1
fi

health_check() {
    SPB_HEALTH_URL="${APP_URL}/api/health" "${PYTHON}" -c \
        'import os, urllib.request; urllib.request.urlopen(os.environ["SPB_HEALTH_URL"], timeout=1)' \
        >/dev/null 2>&1
}

if health_check; then
    echo "Another Smart Parcel Box instance is already responding at ${APP_URL}." >&2
    exit 1
fi

stop_backend() {
    if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill "${BACKEND_PID}" 2>/dev/null || true
        wait "${BACKEND_PID}" 2>/dev/null || true
    fi
}
trap stop_backend EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "${SCRIPT_DIR}/data"
echo "Starting Smart Parcel Box on the edge device at ${APP_URL}..."
SPB_HOST="${APP_HOST}" SPB_PORT="${APP_PORT}" \
    "${PYTHON}" "${SCRIPT_DIR}/main.py" >>"${LOG_FILE}" 2>&1 &
BACKEND_PID=$!

ready=0
for ((second = 0; second < STARTUP_TIMEOUT; second++)); do
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
        echo "Smart Parcel Box backend exited during startup. Recent log output:" >&2
        tail -n 80 "${LOG_FILE}" >&2 || true
        exit 1
    fi
    if health_check; then
        ready=1
        break
    fi
    sleep 1
done

if [[ "${ready}" -ne 1 ]]; then
    echo "Smart Parcel Box did not become healthy within ${STARTUP_TIMEOUT}s. Recent log output:" >&2
    tail -n 80 "${LOG_FILE}" >&2 || true
    exit 1
fi

echo "Opening the fullscreen kiosk. Press Alt+F4 to exit."
"${BROWSER}" \
    --kiosk \
    --app="${APP_URL}" \
    --no-first-run \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --noerrdialogs \
    --autoplay-policy=no-user-gesture-required
