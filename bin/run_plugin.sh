#!/usr/bin/env bash

set -euo pipefail

readonly current_script_path=${BASH_SOURCE[0]}
readonly plugin_dir="$(dirname "$(dirname "$current_script_path")")/lib"

export PYTHONPATH="${plugin_dir}"
readonly args=(
  python
  -m
  asdf_clang_format
  "$@"
)

exec "${args[@]}"
