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
PIP_INDEX_URL="${PIP_INDEX_URL:-}"
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
PIP_REGION="${PIP_REGION:-overseas}"
PIP_MAINLAND_INDEX_URL="${PIP_MAINLAND_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PIP_MAINLAND_TRUSTED_HOST="${PIP_MAINLAND_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"
PIP_OVERSEAS_INDEX_URL="${PIP_OVERSEAS_INDEX_URL:-https://pypi.org/simple}"
PIP_OVERSEAS_TRUSTED_HOST="${PIP_OVERSEAS_TRUSTED_HOST:-pypi.org files.pythonhosted.org}"
PIP_TIMEOUT="${PIP_TIMEOUT:-120}"
PIP_RETRIES="${PIP_RETRIES:-20}"
PIP_RESUME_RETRIES="${PIP_RESUME_RETRIES:-20}"
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
  PIP_INDEX_URL           Optional pip mirror, e.g. https://pypi.tuna.tsinghua.edu.cn/simple
  PIP_EXTRA_INDEX_URL     Optional extra pip index
  PIP_TRUSTED_HOST        Optional trusted host for pip
  PIP_REGION              mainland or overseas. Default: ${PIP_REGION}
  PIP_MAINLAND_INDEX_URL  Default: ${PIP_MAINLAND_INDEX_URL}
  PIP_MAINLAND_TRUSTED_HOST Default: ${PIP_MAINLAND_TRUSTED_HOST}
  PIP_OVERSEAS_INDEX_URL  Default: ${PIP_OVERSEAS_INDEX_URL}
  PIP_OVERSEAS_TRUSTED_HOST Default: ${PIP_OVERSEAS_TRUSTED_HOST}
  PIP_TIMEOUT             Default: ${PIP_TIMEOUT}
  PIP_RETRIES             Default: ${PIP_RETRIES}
  PIP_RESUME_RETRIES      Default: ${PIP_RESUME_RETRIES}
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

pip_supports_option() {
  local option="$1"
  "${VENV_DIR}/bin/python" -m pip install --help 2>/dev/null | grep -q -- "${option}"
}

run_pip_install() {
  local index_url="$1"
  local trusted_hosts="$2"
  shift 2

  local pip_args=(
    --timeout "${PIP_TIMEOUT}"
    --retries "${PIP_RETRIES}"
  )
  local host

  if [[ -n "${PIP_RESUME_RETRIES}" ]] && pip_supports_option "--resume-retries"; then
    pip_args+=(--resume-retries "${PIP_RESUME_RETRIES}")
  fi

  if [[ -n "${index_url}" ]]; then
    pip_args+=(--index-url "${index_url}")
  fi
  if [[ -n "${PIP_EXTRA_INDEX_URL}" ]]; then
    pip_args+=(--extra-index-url "${PIP_EXTRA_INDEX_URL}")
  fi
  if [[ -n "${PIP_TRUSTED_HOST}" ]]; then
    pip_args+=(--trusted-host "${PIP_TRUSTED_HOST}")
  elif [[ -n "${trusted_hosts}" ]]; then
    for host in ${trusted_hosts}; do
      pip_args+=(--trusted-host "${host}")
    done
  fi

  "${VENV_DIR}/bin/python" -m pip install "${pip_args[@]}" "$@"
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
  local primary_index primary_hosts secondary_index secondary_hosts

  require_file "${APP_DIR}/requirements.txt"

  if [[ -n "${PIP_INDEX_URL}" ]]; then
    primary_index="${PIP_INDEX_URL}"
    primary_hosts="${PIP_TRUSTED_HOST}"
    secondary_index=""
    secondary_hosts=""
  elif [[ "${PIP_REGION}" == "mainland" ]]; then
    primary_index="${PIP_MAINLAND_INDEX_URL}"
    primary_hosts="${PIP_MAINLAND_TRUSTED_HOST}"
    secondary_index="${PIP_OVERSEAS_INDEX_URL}"
    secondary_hosts="${PIP_OVERSEAS_TRUSTED_HOST}"
  else
    primary_index="${PIP_OVERSEAS_INDEX_URL}"
    primary_hosts="${PIP_OVERSEAS_TRUSTED_HOST}"
    secondary_index="${PIP_MAINLAND_INDEX_URL}"
    secondary_hosts="${PIP_MAINLAND_TRUSTED_HOST}"
  fi

  log "upgrading pip with primary index: ${primary_index:-default}"
  if ! run_pip_install "${primary_index}" "${primary_hosts}" --upgrade pip; then
    if [[ -n "${secondary_index}" ]]; then
      log "primary pip index failed, retrying with fallback index: ${secondary_index}"
      run_pip_install "${secondary_index}" "${secondary_hosts}" --upgrade pip
    else
      return 1
    fi
  fi

  if pip_supports_option "--resume-retries"; then
    log "pip supports --resume-retries; resumable downloads enabled"
  else
    log "pip does not support --resume-retries; continuing with compatible retry options"
  fi

  log "installing dependencies with primary index: ${primary_index:-default}"
  if ! run_pip_install "${primary_index}" "${primary_hosts}" -r "${APP_DIR}/requirements.txt"; then
    if [[ -n "${secondary_index}" ]]; then
      log "primary pip index failed, retrying dependencies with fallback index: ${secondary_index}"
      run_pip_install "${secondary_index}" "${secondary_hosts}" -r "${APP_DIR}/requirements.txt"
    else
      return 1
    fi
  fi
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
