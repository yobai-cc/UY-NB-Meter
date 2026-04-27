#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_NAME="${APP_NAME:-UY-NB-Meter}"
SERVICE_NAME="${SERVICE_NAME:-uy-nb-meter}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${APP_DIR}/.venv}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
BRANCH="${BRANCH:-}"
RUN_TESTS="${RUN_TESTS:-0}"
SKIP_GIT_PULL="${SKIP_GIT_PULL:-0}"
SUDO_BIN="${SUDO_BIN:-sudo}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
JOURNALCTL_BIN="${JOURNALCTL_BIN:-journalctl}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") install
  $(basename "$0") update
  $(basename "$0") refresh
  $(basename "$0") restart
  $(basename "$0") status
  $(basename "$0") logs
  $(basename "$0") install-service

Environment overrides:
  APP_NAME                Default: ${APP_NAME}
  SERVICE_NAME            Default: ${SERVICE_NAME}
  PYTHON_BIN              Default: ${PYTHON_BIN}
  VENV_DIR                Default: ${VENV_DIR}
  ENV_FILE                Default: ${ENV_FILE}
  BRANCH                  Optional git branch to pull
  RUN_TESTS               1 to run unittest after install/update
  SKIP_GIT_PULL           1 to skip git pull during update
  SUDO_BIN                Default: ${SUDO_BIN}
  SYSTEMCTL_BIN           Default: ${SYSTEMCTL_BIN}
  JOURNALCTL_BIN          Default: ${JOURNALCTL_BIN}
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    log "loading env from ${ENV_FILE}"
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || die "missing required file: ${path}"
}

ensure_venv() {
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    log "creating virtualenv at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
}

install_requirements() {
  require_file "${APP_DIR}/requirements.txt"
  log "upgrading pip"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  log "installing dependencies"
  "${VENV_DIR}/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"
}

git_update() {
  if [[ ! -d "${APP_DIR}/.git" ]]; then
    log "git repo not found, skipping pull"
    return
  fi

  if [[ "${SKIP_GIT_PULL}" == "1" ]]; then
    log "SKIP_GIT_PULL=1, skipping git pull"
    return
  fi

  if ! git -C "${APP_DIR}" diff --quiet || ! git -C "${APP_DIR}" diff --cached --quiet; then
    die "working tree has uncommitted changes; commit/stash them or set SKIP_GIT_PULL=1"
  fi

  log "fetching latest git refs"
  git -C "${APP_DIR}" fetch --all --prune

  if [[ -n "${BRANCH}" ]]; then
    log "checking out branch ${BRANCH}"
    git -C "${APP_DIR}" checkout "${BRANCH}"
  fi

  log "pulling latest code"
  git -C "${APP_DIR}" pull --ff-only
}

run_tests() {
  if [[ "${RUN_TESTS}" != "1" ]]; then
    return
  fi
  log "running unit tests"
  (cd "${APP_DIR}" && "${VENV_DIR}/bin/python" -m unittest -v)
}

restart_service() {
  log "restarting service ${SERVICE_NAME}"
  "${SUDO_BIN}" "${SYSTEMCTL_BIN}" restart "${SERVICE_NAME}"
}

status_service() {
  "${SUDO_BIN}" "${SYSTEMCTL_BIN}" status "${SERVICE_NAME}" --no-pager
}

logs_service() {
  "${SUDO_BIN}" "${JOURNALCTL_BIN}" -u "${SERVICE_NAME}" -n 200 --no-pager
}

install_service() {
  local template="${APP_DIR}/deploy/uy-nb-meter.service.template"
  local rendered

  require_file "${template}"
  rendered="$(mktemp)"

  sed \
    -e "s|__APP_DIR__|${APP_DIR}|g" \
    -e "s|__SERVICE_NAME__|${SERVICE_NAME}|g" \
    -e "s|__RUN_USER__|${SUDO_USER:-$USER}|g" \
    -e "s|__ENV_FILE__|${ENV_FILE}|g" \
    "${template}" > "${rendered}"

  log "installing systemd unit to /etc/systemd/system/${SERVICE_NAME}.service"
  "${SUDO_BIN}" install -m 0644 "${rendered}" "/etc/systemd/system/${SERVICE_NAME}.service"
  rm -f "${rendered}"

  log "reloading systemd"
  "${SUDO_BIN}" "${SYSTEMCTL_BIN}" daemon-reload
  log "enabling service ${SERVICE_NAME}"
  "${SUDO_BIN}" "${SYSTEMCTL_BIN}" enable "${SERVICE_NAME}"
  restart_service
}

install_app() {
  load_env
  ensure_venv
  install_requirements
  run_tests
  log "install finished"
}

update_app() {
  load_env
  git_update
  ensure_venv
  install_requirements
  run_tests
  restart_service
  log "update finished"
}

refresh_app() {
  load_env
  ensure_venv
  install_requirements
  run_tests
  restart_service
  log "refresh finished"
}

main() {
  local command="${1:-}"

  case "${command}" in
    install)
      install_app
      ;;
    update)
      update_app
      ;;
    refresh)
      refresh_app
      ;;
    restart)
      restart_service
      ;;
    status)
      status_service
      ;;
    logs)
      logs_service
      ;;
    install-service)
      load_env
      install_service
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      die "unknown command: ${command}"
      ;;
  esac
}

main "$@"
