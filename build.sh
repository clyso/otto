#!/bin/bash
# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later


run_build() {
  # When running inside container, ensure the mounted workspace is trusted by git
  git config --global --add safe.directory /app || echo "git config failed"

  # create a venv specifically for the installer builder, so we can remove
  # it after.
  uv venv --python 3.11 .venv-installer || exit 1

  # shellcheck source=/dev/null
  source .venv-installer/bin/activate

  # 'uv' will automatically use the sourced venv

  uv pip install pyinstaller || exit 1
  uv pip install -e ./otto/ || exit 1

  # Data directories are relative to specpath.
  # We set 'src/' as the specpath so the resulting 'otto.spec' does not
  # conflict with the rpm one.
  python3 -m PyInstaller --onefile \
    --name otto \
    --specpath otto/ \
    --clean \
    --add-data 'src/clyso/ceph/otto/tools:clyso/ceph/otto/tools' \
    --add-data 'src/clyso/ceph/ai/*.yaml:clyso/ceph/ai' \
    otto/src/clyso/ceph/otto/__main__.py || exit 1

  # ensure we deactivate the environment.
  deactivate

  ./dist/otto --version || exit 1
  ./dist/otto --help || exit 1

  rm -fr ./build/ ./clyso/otto.spec || exit 1
  rm -fr .venv-installer/ || exit 1
}

usage() {
  cat <<EOF >/dev/stderr
usage: $0 [options]

Helper to build otto's installer.

Builds either in the developer's local environment, or, if '--container' is
specified, within the context of a container.

If '--container' is specified, a container image will be created from scratch
and will be named 'otto-builder'. It is up to the user to remove the
image should they want to.

options:
  -h | --help       Shows this message
  -c | --container  Builds using a container

EOF
}

run_with_ctr() {
  ctr_tool="docker"
  extra_run_args=()
  if podman --version >/dev/null; then
    ctr_tool="podman"
    extra_run_args=(
      "--userns=keep-id"
      "--security-opt label=disable"
    )
  fi

  ${ctr_tool} build -f ./pyinstaller.Dockerfile \
    -t otto-builder:latest \
    . || exit 1

  # shellcheck disable=SC2068
  ${ctr_tool} run ${extra_run_args[@]} \
    -v .:/app \
    otto-builder:latest || exit 1
}

run_ctr=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --help | -h)
      usage
      exit 0
      ;;
    --container | -c) run_ctr=1 ;;
    *)
      echo "error: unknown argument '${1}'" >/dev/stderr
      usage
      exit 1
      ;;
  esac
  shift 1
done

if [[ ${run_ctr} -eq 1 ]]; then
  run_with_ctr
else
  run_build
fi
