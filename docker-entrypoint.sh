#!/bin/sh
# docker-entrypoint.sh – translates environment variables into CLI flags and
# launches either the terminal dashboard or the web dashboard.

set -e

# ── helpers ────────────────────────────────────────────────────────────────────
build_cli_args() {
    ARGS=""

    # --interval
    if [ -n "${SIGNALSCOPE_INTERVAL}" ]; then
        ARGS="${ARGS} --interval ${SIGNALSCOPE_INTERVAL}"
    fi

    # --top
    if [ -n "${SIGNALSCOPE_TOP}" ]; then
        ARGS="${ARGS} --top ${SIGNALSCOPE_TOP}"
    fi

    # --cpu-threshold
    if [ -n "${SIGNALSCOPE_CPU_THRESHOLD}" ]; then
        ARGS="${ARGS} --cpu-threshold ${SIGNALSCOPE_CPU_THRESHOLD}"
    fi

    # --mem-threshold
    if [ -n "${SIGNALSCOPE_MEM_THRESHOLD}" ]; then
        ARGS="${ARGS} --mem-threshold ${SIGNALSCOPE_MEM_THRESHOLD}"
    fi

    # --no-daemon
    if [ "${SIGNALSCOPE_NO_DAEMON}" = "true" ] || [ "${SIGNALSCOPE_NO_DAEMON}" = "1" ]; then
        ARGS="${ARGS} --no-daemon"
    fi

    # --user
    if [ -n "${SIGNALSCOPE_USER}" ]; then
        ARGS="${ARGS} --user ${SIGNALSCOPE_USER}"
    fi

    # --alert-log
    if [ -n "${SIGNALSCOPE_ALERT_LOG}" ]; then
        ARGS="${ARGS} --alert-log ${SIGNALSCOPE_ALERT_LOG}"
    fi

    # --log-level
    if [ -n "${SIGNALSCOPE_LOG_LEVEL}" ]; then
        ARGS="${ARGS} --log-level ${SIGNALSCOPE_LOG_LEVEL}"
    fi

    echo "${ARGS}"
}

# ── dispatch ───────────────────────────────────────────────────────────────────
if [ "${SIGNALSCOPE_MODE}" = "web" ]; then
    echo "Starting SignalScope web dashboard on ${SIGNALSCOPE_WEB_HOST}:${SIGNALSCOPE_WEB_PORT} …"
    exec python -m src.web.app \
        --host "${SIGNALSCOPE_WEB_HOST}" \
        --port "${SIGNALSCOPE_WEB_PORT}" \
        --interval "${SIGNALSCOPE_INTERVAL}" \
        --cpu-threshold "${SIGNALSCOPE_CPU_THRESHOLD}" \
        --mem-threshold "${SIGNALSCOPE_MEM_THRESHOLD}" \
        ${SIGNALSCOPE_TOP:+--top "${SIGNALSCOPE_TOP}"} \
        ${SIGNALSCOPE_NO_DAEMON:+--no-daemon} \
        ${SIGNALSCOPE_USER:+--user "${SIGNALSCOPE_USER}"} \
        --log-level "${SIGNALSCOPE_LOG_LEVEL}"
else
    # shellcheck disable=SC2046
    exec python -m src.main $(build_cli_args)
fi
