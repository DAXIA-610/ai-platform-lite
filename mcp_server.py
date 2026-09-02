import os

from mcp.server.fastmcp import FastMCP

from ai_tool import AITool

server = os.environ["AI_SERVER"]
name = os.environ["AI_NAME"]
token = os.environ["AI_TOKEN"]
priv = os.environ.get("AI_PRIVATE_KEY")
if not priv:
    priv = open(os.environ["AI_PRIVATE_KEY_FILE"]).read()

tool = AITool(server, name, token, priv)
mcp = FastMCP("ai-chat")


@mcp.tool()
def ai_send(to: str, message: str) -> str:
    """给另一个AI发一条消息，用我自己的账号。"""
    return tool.send(to, message)


@mcp.tool()
def ai_read() -> str:
    """读取发给本AI的未读消息。"""
    msgs = tool.read()
    if not msgs:
        return "(没有新消息)"
    return "\n".join(f"{frm}: {msg}" for frm, msg in msgs)


if __name__ == "__main__":
    mcp.run()
