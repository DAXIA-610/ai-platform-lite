import asyncio
import os

import aiohttp

from ai_tool import AITool

S = os.environ.get("SERVER", "http://127.0.0.1:8000").rstrip("/")


async def main():
    async with aiohttp.ClientSession() as s:
        async def post(path, body=None, key=None):
            h = {}
            if key:
                h["X-AI-Key"] = key
            r = await s.post(S + path, json=body or {}, headers=h)
            return await r.json()

        async def get(path, key=None):
            h = {}
            if key:
                h["X-AI-Key"] = key
            r = await s.get(S + path, headers=h)
            return await r.json()

        a = await post("/api/register", {"username": "alice", "password": "123", "name": "Alice"})
        b = await post("/api/register", {"username": "bob", "password": "123", "name": "Bob"})
        alice = AITool(S, a["token"], a["private_key"])
        bob = AITool(S, b["token"], b["private_key"])
        print("[注册] alice / bob ok")

        alice.add_friend("bob")
        print("[好友] alice -> bob 请求已发")
        print("[好友]", bob.list_friends().get("friends"), "<- bob(还没好友)")
        bob.accept("alice")
        print("[好友] bob 接受了 alice")
        print("[好友]", [f["username"] for f in alice.list_friends().get("friends", [])], "<- alice 好友")

        print("[发]", alice.send("bob", "你好bob，我是alice"))
        for frm, msg in bob.read():
            print(f"[收] bob <- {frm}: {msg}")

        lb = await post("/api/login", {"username": "bob", "password": "123"})
        ws = await s.ws_connect(S.replace("http", "ws") + "/ws?session=" + lb["token"])
        print("[WS] bob 前端已连")
        alice.send("bob", "第二条，测试推送")
        try:
            evt = await asyncio.wait_for(ws.receive(), timeout=5)
            print("[WS] bob 前端收到推送:", evt.data[:80])
        except asyncio.TimeoutError:
            print("[WS] 超时没收到推送")
        await ws.close()


asyncio.run(main())
