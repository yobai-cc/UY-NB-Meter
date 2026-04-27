#!/usr/bin/env bash

set -euo pipefail

APP_NAME="${APP_NAME:-UY-NB-Meter}"
REPO_SLUG="${REPO_SLUG:-yobai-cc/UY-NB-Meter}"
TARGET_DIR="${TARGET_DIR:-$HOME/UY-NB-Meter}"
RELEASE_TAG="${RELEASE_TAG:-latest}"
RELEASE_FILE="${RELEASE_FILE:-UY-NB-Meter-release.tar.gz}"
RELEASE_URL="${RELEASE_URL:-}"
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
  curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | RELEASE_TAG=v1.0.0 bash -s -- update

Environment overrides:
  APP_NAME         Default: ${APP_NAME}
  REPO_SLUG        Default: ${REPO_SLUG}
  TARGET_DIR       Default: ${TARGET_DIR}
  RELEASE_TAG      Default: ${RELEASE_TAG}
  RELEASE_FILE     Default: ${RELEASE_FILE}
  RELEASE_URL      Optional direct download url
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

resolve_release_url() {
  if [[ -n "${RELEASE_URL}" ]]; then
    printf '%s\n' "${RELEASE_URL}"
    return
  fi

  if [[ "${RELEASE_TAG}" == "latest" ]]; then
    printf 'https://github.com/%s/releases/latest/download/%s\n' "${REPO_SLUG}" "${RELEASE_FILE}"
    return
  fi

  printf 'https://github.com/%s/releases/download/%s/%s\n' "${REPO_SLUG}" "${RELEASE_TAG}" "${RELEASE_FILE}"
}

download_release() {
  local url="$1"
  local archive_path="$2"

  log "downloading release package"
  curl -fL "${url}" -o "${archive_path}"
}

extract_release() {
  local archive_path="$1"
  local extract_dir="$2"

  mkdir -p "${extract_dir}"
  tar -xzf "${archive_path}" -C "${extract_dir}"
}

resolve_payload_dir() {
  local extract_dir="$1"
  local candidate

  if [[ -f "${extract_dir}/deploy/deploy_update.sh" ]]; then
    printf '%s\n' "${extract_dir}"
    return
  fi

  candidate="$(find "${extract_dir}" -mindepth 1 -maxdepth 2 -type f -path '*/deploy/deploy_update.sh' | head -n 1 || true)"
  [[ -n "${candidate}" ]] || die "release package does not contain deploy/deploy_update.sh"
  dirname "$(dirname "${candidate}")"
}

prepare_target_dir() {
  mkdir -p "${TARGET_DIR}"
}

preserve_env() {
  local payload_dir="$1"

  if [[ -f "${TARGET_DIR}/.env" ]]; then
    return
  fi

  if [[ -f "${payload_dir}/${ENV_TEMPLATE}" ]]; then
    log "creating .env from ${ENV_TEMPLATE}"
    cp "${payload_dir}/${ENV_TEMPLATE}" "${TARGET_DIR}/.env"
  fi
}

sync_payload() {
  local payload_dir="$1"

  prepare_target_dir
  preserve_env "${payload_dir}"

  log "installing files to ${TARGET_DIR}"
  rsync -a \
    --delete \
    --exclude '.env' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    "${payload_dir}/" "${TARGET_DIR}/"
}

run_repo_script() {
  local command="$1"
  local repo_command="install"

  if [[ "${command}" == "update" ]]; then
    repo_command="refresh"
  fi

  log "running deploy/deploy_update.sh ${repo_command}"
  RUN_TESTS="${RUN_TESTS}" bash "${TARGET_DIR}/deploy/deploy_update.sh" "${repo_command}"

  if [[ "${INSTALL_SERVICE}" == "1" ]]; then
    log "installing systemd service"
    bash "${TARGET_DIR}/deploy/deploy_update.sh" install-service
  fi
}

main() {
  local command="${1:-install}"
  local work_dir archive_path extract_dir payload_dir release_url

  case "${command}" in
    install|update)
      require_cmd bash
      require_cmd curl
      require_cmd tar
      require_cmd rsync

      work_dir="$(mktemp -d)"
      archive_path="${work_dir}/${RELEASE_FILE}"
      extract_dir="${work_dir}/extract"
      release_url="$(resolve_release_url)"

      log "using release url: ${release_url}"
      download_release "${release_url}" "${archive_path}"
      extract_release "${archive_path}" "${extract_dir}"
      payload_dir="$(resolve_payload_dir "${extract_dir}")"
      sync_payload "${payload_dir}"
      run_repo_script "${command}"
      rm -rf "${work_dir}"
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
