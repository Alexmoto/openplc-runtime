#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
src="$root/core/src/plc_app"
cc -std=c11 -D_GNU_SOURCE -Wall -Wextra -Werror -I"$src" -I"$src/utils" -c "$src/debug_handler.c" -o "$work/handler.o"
c++ -std=c++17 -Wall -Wextra -Werror -I"$src" -I"$src/utils" "$root/tools/targetvisu/tests/core_protocol.cpp" "$src/debug_write_journal.cpp" "$work/handler.o" -pthread -o "$work/core-test"
"$work/core-test"
