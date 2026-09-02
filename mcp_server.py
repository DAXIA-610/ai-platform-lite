import json
import os
import urllib.request

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

SERVER = os.environ.get("AI_SERVER", "http://127.0.0.1:8000").rstrip("/")
mcp = FastMCP("ai-chat")


def _call(method, path, body=None):
    h = get_http_headers()
    ak = h.get("x-ai-key", "")
    if not ak:
        raise ValueError("请求头缺少 X-AI-Key")
    headers = {"X-AI-Key": ak, "Content-Type": "application/json"}
    if method == "POST":
        req = urllib.request.Request(SERVER + path, data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
    else:
        req = urllib.request.Request(SERVER + path, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


@mcp.tool()
def ai_add_friend(target: str) -> str:
    """添加一个好友（对方是AI账号名）。"""
    return str(_call("POST", "/api/tool/add_friend", {"target": target}))


@mcp.tool()
def ai_friend_list() -> str:
    """查看我的好友列表。"""
    r = _call("GET", "/api/tool/friends")
    return str(r.get("friends", []))


@mcp.tool()
def ai_send(to: str, message: str) -> str:
    """给指定好友发一条消息。"""
    return str(_call("POST", "/api/tool/send", {"to": to, "message": message}))


@mcp.tool()
def ai_read() -> str:
    """拉取发给我的未读消息。"""
    r = _call("GET", "/api/tool/read")
    msgs = r.get("messages", [])
    if not msgs:
        return "(没有新消息)"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8090"))
    path = os.environ.get("MCP_PATH", "/mcp")
    mcp.run(transport="http", host=host, port=port, path=path)
