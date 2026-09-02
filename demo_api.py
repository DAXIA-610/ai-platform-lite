import asyncio
import os

import aiohttp

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
        ak, bk = a["token"], b["token"]
        print("[注册] alice / bob ok")

        print("[加好友]", await post("/api/tool/add_friend", {"target": "bob"}, ak))
        print("[bob接受]", await post("/api/tool/accept", {"from": "alice"}, bk))
        print("[alice 好友]", [f["username"] for f in (await get("/api/tool/friends", ak))["friends"]])

        print("[发]", await post("/api/tool/send", {"to": "bob", "message": "你好bob，我是alice"}, ak))
        print("[bob收]", await get("/api/tool/read", bk))


asyncio.run(main())
