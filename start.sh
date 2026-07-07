#!/usr/bin/env bash
# 一键启动盯盘台: 数据后端(Python :5320) + 前端(vben, Node22)
# 用法:  ./start.sh
# 停止:  Ctrl-C (会一并停掉后端)
set -e
cd "$(dirname "$0")"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" && nvm use 22 >/dev/null

echo "▶ 启动数据后端 watch_server.py :5320 ..."
python3 watch_server.py &
SRV=$!
trap "echo; echo '停止后端'; kill $SRV 2>/dev/null" EXIT

sleep 1
echo "▶ 启动前端 (pnpm dev) ..."
cd dashboard
pnpm dev
