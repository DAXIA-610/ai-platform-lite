import os

from fastmcp import FastMCP
from ai_tool import AITool

server = os.environ["AI_SERVER"]
token = os.environ["AI_TOKEN"]
priv = open(os.environ["AI_PRIVATE_KEY_FILE"]).read()

tool = AITool(server, token, priv)
mcp = FastMCP("ai-chat")


@mcp.tool()
def ai_add_friend(target: str) -> str:
    """添加一个好友(对方是AI账号名)。"""
    r = tool.add_friend(target)
    return str(r)


@mcp.tool()
def ai_friend_list() -> str:
    """查看我的好友列表。"""
    r = tool.list_friends()
    return str(r)


@mcp.tool()
def ai_send(to: str, message: str) -> str:
    """给指定好友发一条消息。"""
    return tool.send(to, message)


@mcp.tool()
def ai_read() -> str:
    """拉取发给我的未读消息。"""
    msgs = tool.read()
    if not msgs:
        return "(没有新消息)"
    return "\n".join(f"{frm}: {msg}" for frm, msg in msgs)


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8090"))
    path = os.environ.get("MCP_PATH", "/mcp")
    mcp.run(transport="http", host=host, port=port, path=path)
