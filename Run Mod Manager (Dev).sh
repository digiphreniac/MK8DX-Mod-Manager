#!/usr/bin/env bash
# Same as "Run Mod Manager.sh", with the web view's developer tools switched on.
export MK8DX_DEBUG=1
exec "$(dirname "$0")/Run Mod Manager.sh"
