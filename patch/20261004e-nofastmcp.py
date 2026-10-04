# -*- coding: utf-8 -*-
"""让后端在“没装 fastmcp”的机器上也能跑起来。

背景：fastmcp 拖着 pydantic，在 aarch64（Termux / 手机）上经常要现场编译、容易装不上。
现在装不上也能跑：REST + WebSocket 照常，只是 /mcp（AI 接入）这条关掉。
在仓库根目录跑：python3 patch/20261004e-nofastmcp.py
"""
import ast
import sys

SRC = "server.py"

P = []


def add(desc, old, new):
    P.append((desc, old, new))


add("1 fastmcp 变成可选",
    r'''from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers, get_http_request''',
    r'''try:
    from fastmcp import FastMCP
    from fastmcp.server.dependencies import get_http_headers, get_http_request
    HAS_MCP = True
except Exception as _e:
    # 没装 fastmcp 也能跑：REST + WebSocket 照常，只是 /mcp（AI 接入）这条会关掉
    print("[warn] fastmcp 没装上，/mcp（AI 接入）会关掉，其他功能正常：", _e)
    HAS_MCP = False''')

add("2 mcp 对象的占位实现",
    r'''mcp = FastMCP("ai-chat")
BASE = "http://127.0.0.1:" + SELF''',
    r'''if HAS_MCP:
    mcp = FastMCP("ai-chat")
else:
    class _NullMcp:
        # 没装 fastmcp 时的占位：@mcp.tool() 原样返回函数，什么都不做
        def tool(self, *a, **k):
            def deco(f):
                return f
            return deco

        def http_app(self, *a, **k):
            return None
    mcp = _NullMcp()

BASE = "http://127.0.0.1:" + SELF''')

add("3 没 fastmcp 就不挂 /mcp 路由",
    r'''def make_app():
    mcp_app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True, json_response=True)
    routes = [
        Route("/api/{path:path}", handle, methods=["GET", "POST"]),
        WebSocketRoute("/ws", ws_endpoint),
        Route("/mcp", mcp_app, methods=["GET", "POST"]),
        Mount("/public", StaticFiles(directory=os.path.join(BASE_DIR, "public"), html=True)),
    ]
    app = Starlette(routes=routes, lifespan=mcp_app.lifespan)''',
    r'''def make_app():
    routes = [
        Route("/api/{path:path}", handle, methods=["GET", "POST"]),
        WebSocketRoute("/ws", ws_endpoint),
    ]
    lifespan = None
    if HAS_MCP:
        mcp_app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True, json_response=True)
        routes.append(Route("/mcp", mcp_app, methods=["GET", "POST"]))
        lifespan = mcp_app.lifespan
    else:
        print("[warn] /mcp 没挂上（缺 fastmcp），AI 接不进来，人跟人照常玩")
    routes.append(Mount("/public", StaticFiles(directory=os.path.join(BASE_DIR, "public"), html=True)))
    app = Starlette(routes=routes, lifespan=lifespan)''')


def main():
    src = open(SRC, encoding="utf-8").read()
    out = src
    bad = []
    for desc, old, new in P:
        n = out.count(old)
        if n != 1:
            bad.append((desc, n))
            continue
        out = out.replace(old, new, 1)
    if bad:
        print("!! 匹配数不对，整体不动:")
        for d, n in bad:
            print("   -", d, "出现", n, "次")
        return 1
    try:
        ast.parse(out)
    except SyntaxError as e:
        print("!! 语法不过，整体不动:", e)
        return 1
    open(SRC, "w", encoding="utf-8").write(out)
    print("OK server.py 改了 %d 处（fastmcp 现在是可选的）" % len(P))
    return 0


sys.exit(main())
