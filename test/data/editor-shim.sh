#!/usr/bin/env bash
set -e
scratch="$1"
shift
printf '%s\n' "$@" > "$scratch"
