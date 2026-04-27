#!/usr/bin/env bash

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/yobai-cc/UY-NB-Meter.git}"
BRANCH="${BRANCH:-main}"
TARGET_DIR="${TARGET_DIR:-$HOME/UY-NB-Meter}"
RUN_TESTS="${RUN_TESTS:-0}"
INSTALL_SERVICE="${INSTALL_SERVICE:-0}"
ENV_TEMPLATE="${ENV_TEMPLATE:-.env.example}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") install
  $(basename "$0") update

Examples:
  curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | bash -s -- install
  curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | TARGET_DIR=/opt/UY-NB-Meter bash -s -- install
  curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | INSTALL_SERVICE=1 bash -s -- install

Environment overrides:
  REPO_URL         Default: ${REPO_URL}
  BRANCH           Default: ${BRANCH}
  TARGET_DIR       Default: ${TARGET_DIR}
  RUN_TESTS        1 to run unittest
  INSTALL_SERVICE  1 to install/restart systemd service
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

clone_or_update_repo() {
  if [[ -d "${TARGET_DIR}/.git" ]]; then
    log "updating existing repo in ${TARGET_DIR}"
    git -C "${TARGET_DIR}" fetch --all --prune
    git -C "${TARGET_DIR}" checkout "${BRANCH}"
    git -C "${TARGET_DIR}" pull --ff-only origin "${BRANCH}"
    return
  fi

  if [[ -e "${TARGET_DIR}" && -n "$(ls -A "${TARGET_DIR}" 2>/dev/null || true)" ]]; then
    die "target dir exists and is not an empty git repo: ${TARGET_DIR}"
  fi

  log "cloning ${REPO_URL} to ${TARGET_DIR}"
  git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${TARGET_DIR}"
}

prepare_env_file() {
  if [[ -f "${TARGET_DIR}/.env" ]]; then
    return
  fi

  if [[ -f "${TARGET_DIR}/${ENV_TEMPLATE}" ]]; then
    log "creating .env from ${ENV_TEMPLATE}"
    cp "${TARGET_DIR}/${ENV_TEMPLATE}" "${TARGET_DIR}/.env"
  fi
}

run_repo_script() {
  local command="$1"

  prepare_env_file
  log "running deploy/deploy_update.sh ${command}"
  RUN_TESTS="${RUN_TESTS}" bash "${TARGET_DIR}/deploy/deploy_update.sh" "${command}"

  if [[ "${INSTALL_SERVICE}" == "1" ]]; then
    log "installing systemd service"
    bash "${TARGET_DIR}/deploy/deploy_update.sh" install-service
  fi
}

main() {
  local command="${1:-install}"

  case "${command}" in
    install|update)
      require_cmd git
      require_cmd bash
      clone_or_update_repo
      run_repo_script "${command}"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      die "unknown command: ${command}"
      ;;
  esac
}

main "$@"
