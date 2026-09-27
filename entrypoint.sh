#!/bin/sh
set -eu

# Ozon/Variti may reject Chromium's native headless mode. By default run a normal
# Chromium inside a virtual X display. Set OZON_HEADLESS=1 only for experiments.
if [ "${OZON_HEADLESS:-0}" = "1" ]; then
  exec ozon-buyer-mcp
fi

exec xvfb-run -a -s "-screen 0 1920x1080x24" ozon-buyer-mcp
