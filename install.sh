#!/usr/bin/env bash

set -euo pipefail

APP_NAME="${APP_NAME:-UY-NB-Meter}"
REPO_SLUG="${REPO_SLUG:-yobai-cc/UY-NB-Meter}"
TARGET_DIR="${TARGET_DIR:-$HOME/UY-NB-Meter}"
RELEASE_TAG="${RELEASE_TAG:-latest}"
RELEASE_FILE="${RELEASE_FILE:-UY-NB-Meter-release.tar.gz}"
RELEASE_URL="${RELEASE_URL:-}"
SOURCE_REF="${SOURCE_REF:-main}"
RUN_TESTS="${RUN_TESTS:-0}"
INSTALL_SERVICE="${INSTALL_SERVICE:-0}"
ENV_TEMPLATE="${ENV_TEMPLATE:-.env.example}"
SUDO_BIN="${SUDO_BIN:-sudo}"

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
  SOURCE_REF       Default: ${SOURCE_REF}
  RUN_TESTS        1 to run unittest
  INSTALL_SERVICE  1 to install/restart systemd service
  SUDO_BIN         Default: ${SUDO_BIN}
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

have_sudo() {
  command -v "${SUDO_BIN}" >/dev/null 2>&1
}

run_maybe_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    have_sudo || die "permission required for ${TARGET_DIR}; install ${SUDO_BIN} or choose a writable TARGET_DIR"
    "${SUDO_BIN}" "$@"
  fi
}

current_group_name() {
  id -gn
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

resolve_source_url() {
  if [[ "${RELEASE_TAG}" == "latest" ]]; then
    printf 'https://github.com/%s/archive/refs/heads/%s.tar.gz\n' "${REPO_SLUG}" "${SOURCE_REF}"
    return
  fi

  printf 'https://github.com/%s/archive/refs/tags/%s.tar.gz\n' "${REPO_SLUG}" "${RELEASE_TAG}"
}

download_release() {
  local url="$1"
  local archive_path="$2"

  log "downloading release package"
  curl -fL --connect-timeout 10 --max-time 120 "${url}" -o "${archive_path}"
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
  local parent_dir

  parent_dir="$(dirname "${TARGET_DIR}")"

  if [[ -d "${TARGET_DIR}" ]]; then
    if [[ ! -w "${TARGET_DIR}" ]]; then
      log "granting write access to ${TARGET_DIR} for $(id -un)"
      run_maybe_sudo chown -R "$(id -un):$(current_group_name)" "${TARGET_DIR}"
    fi
    return
  fi

  if [[ -w "${parent_dir}" ]]; then
    mkdir -p "${TARGET_DIR}"
    return
  fi

  log "creating ${TARGET_DIR} with elevated privileges"
  run_maybe_sudo mkdir -p "${TARGET_DIR}"
  if [[ "$(id -u)" -ne 0 ]]; then
    log "granting ownership of ${TARGET_DIR} to $(id -un)"
    run_maybe_sudo chown -R "$(id -un):$(current_group_name)" "${TARGET_DIR}"
  fi
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
  local work_dir archive_path extract_dir payload_dir release_url source_url

  case "${command}" in
    install|update)
      require_cmd bash
      require_cmd curl
      require_cmd tar
      require_cmd rsync
      if [[ "$(id -u)" -ne 0 ]] && [[ "${INSTALL_SERVICE}" == "1" ]]; then
        have_sudo || die "INSTALL_SERVICE=1 requires ${SUDO_BIN} when not running as root"
      fi

      work_dir="$(mktemp -d)"
      archive_path="${work_dir}/${RELEASE_FILE}"
      extract_dir="${work_dir}/extract"
      release_url="$(resolve_release_url)"
      source_url="$(resolve_source_url)"

      log "using release url: ${release_url}"
      if ! download_release "${release_url}" "${archive_path}"; then
        if [[ -n "${RELEASE_URL}" ]]; then
          die "failed to download RELEASE_URL=${RELEASE_URL}"
        fi
        log "release asset not available, falling back to source archive: ${source_url}"
        curl -fL --connect-timeout 10 --max-time 120 "${source_url}" -o "${archive_path}"
      fi
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
