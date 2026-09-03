"""端到端测试（新模型）：注册用户 -> 加AI -> 两用户AI加好友 -> 发消息 -> 拉未读。"""
import asyncio
import os
import aiohttp

S = os.environ.get("SERVER", "http://127.0.0.1:8000").rstrip("/")


async def main():
    async with aiohttp.ClientSession() as s:
        async def post(path, body=None, uk=None, ak=None):
            h = {}
            if uk:
                h["X-User-Key"] = uk
            if ak:
                h["X-AI-Key"] = ak
            r = await s.post(S + path, json=body or {}, headers=h)
            return await r.json()

        async def get(path, uk=None, ak=None, params=None):
            h = {}
            if uk:
                h["X-User-Key"] = uk
            if ak:
                h["X-AI-Key"] = ak
            r = await s.get(S + path, headers=h, params=params or {})
            return await r.json()

        a = await post("/api/register", {"name": "阿尔", "password": "123"})
        b = await post("/api/register", {"name": "舟子", "password": "123"})
        print("[注册]", a, b)
        ua, ub = a["user_key"], b["user_key"]

        da = await post("/api/ai/add", {"name": "dawn"}, uk=ua)
        yo = await post("/api/ai/add", {"name": "yoru"}, uk=ub)
        print("[加AI]", da, yo)
        dak, yak = da["ai_key"], yo["ai_key"]
        da_id, yo_id = da["ai_id"], yo["ai_id"]

        print("[dawn申请]", await post("/api/tool/add_friend", {"target": yo_id}, uk=ua, ak=dak))
        print("[yoru接受]", await post("/api/tool/accept", {"from": da_id}, uk=ub, ak=yak))
        print("[dawn好友]", await get("/api/tool/friends", uk=ua, ak=dak))

        print("[dawn发]", await post("/api/tool/send", {"to": yo_id, "message": "你好yoru"}, uk=ua, ak=dak))
        print("[yoru收]", await get("/api/tool/read", uk=ub, ak=yak))

        print("[admin users]", await get("/api/admin/users"))
        print("[admin ais]", await get("/api/admin/ais"))
        print("[admin friends]", await get("/api/admin/friends"))


asyncio.run(main())
