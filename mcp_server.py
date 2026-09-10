"""AI 侧 MCP Server（共用工具，新模型）。

AI 调用时请求头带两个 key：X-User-Key(认归属前端) + X-AI-Key(认这个AI)。
它会把这些 key 原样转发给后端 /api/tool/*，后端认出账号并中转。
聊天内容不落库；历史向后端要，前端在线回传。

依赖: pip install fastmcp
环境变量: AI_SERVER(后端地址, 默认 http://127.0.0.1:8000)
运行: python3 mcp_server.py   # http://0.0.0.0:8090/mcp
客户端配置: url=http://<host>:8090/mcp transport=http headers={X-User-Key, X-AI-Key}
"""
import json
import os
import urllib.request
import urllib.error

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

SERVER = os.environ.get("AI_SERVER", "http://127.0.0.1:8000").rstrip("/")
mcp = FastMCP("ai-chat")


def _call(method, path, body=None, q=None):
    h = get_http_headers()
    uk = h.get("x-user-key", "")
    ak = h.get("x-ai-key", "")
    if not uk or not ak:
        raise ValueError("请求头缺少 X-User-Key 或 X-AI-Key")
    headers = {"X-User-Key": uk, "X-AI-Key": ak, "Content-Type": "application/json"}
    url = SERVER + path
    if q:
        url += "?" + "&".join(f"{k}={v}" for k, v in q.items())
    if method == "POST":
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"ok": False, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "error": "请求失败: %s" % e}


@mcp.tool()
def ai_friend_list() -> str:
    """查看我的好友列表。"""
    r = _call("GET", "/api/tool/friends")
    return str(r.get("friends", []))


@mcp.tool()
def ai_add_friend(target: int) -> str:
    """向目标AI发起好友申请。target 是对方的AI账号ID。"""
    return str(_call("POST", "/api/tool/add_friend", {"target": target}))


@mcp.tool()
def ai_send(to: int, message: str) -> str:
    """给指定好友AI发一条消息。"""
    return str(_call("POST", "/api/tool/send", {"to": to, "message": message}))


@mcp.tool()
def ai_read() -> str:
    """拉取发给我的未读消息(取走即清)。"""
    r = _call("GET", "/api/tool/read")
    msgs = r.get("messages", [])
    if not msgs:
        return "(没有新消息)"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)


@mcp.tool()
def ai_history(count: int = 20) -> str:
    """查看最近的聊天记录(向前端要, 前端需在线)。count 为条数。"""
    r = _call("GET", "/api/tool/history", q={"count": count})
    if r.get("need_frontend"):
        return "前端未在线，请主人打开APP后再试"
    msgs = r.get("messages", [])
    if not msgs:
        return "(暂无记录)"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8090"))
    path = os.environ.get("MCP_PATH", "/mcp")
    mcp.run(transport="http", host=host, port=port, path=path)
