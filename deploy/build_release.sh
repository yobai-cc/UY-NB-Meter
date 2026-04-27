#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-${APP_DIR}}"
ARCHIVE_NAME="${ARCHIVE_NAME:-UY-NB-Meter-release.tar.gz}"
TMP_ARCHIVE="$(mktemp "/tmp/${ARCHIVE_NAME}.XXXXXX")"

mkdir -p "${OUTPUT_DIR}"

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.env' \
  --exclude='*.pyc' \
  --exclude="${ARCHIVE_NAME}" \
  -czf "${TMP_ARCHIVE}" \
  -C "${APP_DIR}" \
  .

mv "${TMP_ARCHIVE}" "${OUTPUT_DIR}/${ARCHIVE_NAME}"

printf 'created %s\n' "${OUTPUT_DIR}/${ARCHIVE_NAME}"
