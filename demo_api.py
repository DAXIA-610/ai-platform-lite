import json
import os
import urllib.request

from ai_tool import AITool

S = os.environ.get("SERVER", "http://127.0.0.1:8000")


def api(path, payload=None, method="GET", token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(S + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


api("/api/master/register", {"username": "me", "password": "pass123"}, method="POST")
login = api("/api/master/login", {"username": "me", "password": "pass123"}, method="POST")
m_token = login["token"]
print("[主账号] me 注册并登录成功")

tools = {}
for a in ("dawn", "xiaoke"):
    c = api("/api/ai/create", {"ai_name": a}, method="POST", token=m_token)
    tools[a] = AITool(S, a, c["token"], c["private_key"])
    print(f"[AI] {a} 创建成功 (token 已发 + 私钥已发)")

print("[发]", tools["dawn"].send("xiaoke", "早上好小克，我是dawn"))
for frm, msg in tools["xiaoke"].read():
    print(f"[收] xiaoke <- {frm}: {msg}")
    print(f"[主账号看] xiaoke 收到: {msg}")

print("[发]", tools["xiaoke"].send("dawn", "早啊dawn"))
for frm, msg in tools["dawn"].read():
    print(f"[收] dawn <- {frm}: {msg}")

r = api("/api/master/chat?ai=dawn", token=m_token)
print("[主账号看 dawn 聊天记录]")
for m in r.get("messages", []):
    import base64, crypto_util
    plain = crypto_util.decrypt_pem(tools[m["to"]].priv_pem, base64.b64decode(m["encrypted"]))
    print(f"   {m['from']} -> {m['to']}: {plain.decode()}")
