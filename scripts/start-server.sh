# AI 知识库看板启动脚本
# 用法: bash scripts/start-server.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================"
echo "  AI 知识库看板 · 启动脚本"
echo "========================================"
echo ""

# 获取 WSL IP
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$WSL_IP" ]; then
    WSL_IP="<WSL_IP>"
fi

echo "正在启动 MCP HTTP API 服务器..."
echo ""

export PYTHONPATH="$PROJECT_ROOT"
export MCP_HOST="0.0.0.0"
export MCP_PORT="${MCP_PORT:-8080}"

echo "  MCP_HOST=$MCP_HOST"
echo "  MCP_PORT=$MCP_PORT"
echo "  WSL_IP=$WSL_IP"
echo ""

python3 "$PROJECT_ROOT/scripts/mcp_http_server.py" &
SERVER_PID=$!

sleep 2

if kill -0 $SERVER_PID 2>/dev/null; then
    echo "========================================"
    echo "  服务已启动！"
    echo ""
    echo "  公开看板:    http://localhost:$MCP_PORT/"
    echo "  审核看板:    http://localhost:$MCP_PORT/static/review.html"
    echo "  API 状态:    http://localhost:$MCP_PORT/health"
    echo "  搜索 API:    http://localhost:$MCP_PORT/mcp/search?keyword=langchain"
    echo ""
    echo "  (WSL 直接访问: http://$WSL_IP:$MCP_PORT/)"
    echo ""
    echo "  Windows 侧首次访问需运行: wsl-port-forward.ps1"
    echo "  关闭服务: kill $SERVER_PID"
    echo "========================================"
    wait $SERVER_PID
else
    echo "服务启动失败，请检查错误信息。"
    exit 1
fi
