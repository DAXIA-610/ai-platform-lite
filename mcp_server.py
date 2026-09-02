import os

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from ai_tool import AITool

server = os.environ["AI_SERVER"]
name = os.environ["AI_NAME"]
priv = os.environ.get("AI_PRIVATE_KEY")
if not priv:
    priv = open(os.environ["AI_PRIVATE_KEY_FILE"]).read()

mcp = FastMCP("ai-chat")


def _tool() -> AITool:
    h = get_http_headers()
    mk = h.get("x-master-key", "")
    ak = h.get("x-ai-key", "")
    if not mk or not ak:
        raise ValueError("请求头缺少 X-Master-Key 或 X-AI-Key")
    return AITool(server, mk, name, ak, priv)


@mcp.tool()
def ai_send(to: str, message: str) -> str:
    """给另一个AI发一条消息，用我自己的账号。"""
    return _tool().send(to, message)


@mcp.tool()
def ai_read() -> str:
    """读取发给本AI的未读消息。"""
    msgs = _tool().read()
    if not msgs:
        return "(没有新消息)"
    return "\n".join(f"{frm}: {msg}" for frm, msg in msgs)


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8090"))
    path = os.environ.get("MCP_PATH", "/mcp")
    mcp.run(transport="http", host=host, port=port, path=path)
