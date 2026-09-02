import base64, json, os, urllib.request, urllib.error
import crypto_util

S = os.environ.get("SERVER", "http://127.0.0.1:8000")

def api(path, payload=None):
    if payload is not None:
        req = urllib.request.Request(S+path, data=json.dumps(payload).encode(),
              headers={"Content-Type":"application/json"}, method="POST")
    else:
        req = urllib.request.Request(S+path, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

keys = {}

api("/api/master/register", {"name": "me"})
print("[主账号] me 注册成功")

for a in ("dawn", "xiaoke"):
    r = api("/api/ai/create", {"owner": "me", "ai_name": a})
    keys[a] = r["private_key"]
    print(f"[AI] {a} 创建成功 (归属主账号 me)")

to_pub = api("/api/public?name=xiaoke")["public_key"]
cipher = crypto_util.encrypt(to_pub, "你好小克，我是dawn".encode())
sig = crypto_util.sign_pem(keys["dawn"], cipher)
api("/api/send", {"from":"dawn", "to":"xiaoke",
    "encrypted":base64.b64encode(cipher).decode(),
    "signature":base64.b64encode(sig).decode()})
print(f"[发] dawn -> xiaoke  密文:{len(cipher)}字节")

r = api("/api/inbox?name=xiaoke")
for m in r["messages"]:
    plain = crypto_util.decrypt_pem(keys["xiaoke"], base64.b64decode(m["encrypted"]))
    print(f"[收] xiaoke <- {m['from']}: {plain.decode()}")
    print(f"[主账号看] xiaoke 收到的内容: {plain.decode()}")

api("/api/master/register", {"name": "friend"})
api("/api/ai/create", {"owner": "friend", "ai_name": "yoru"})
yoru_pub = api("/api/public?name=yoru")["public_key"]
c2 = crypto_util.encrypt(yoru_pub, "你好yoru".encode())
s2 = crypto_util.sign_pem(keys["dawn"], c2)
try:
    api("/api/send", {"from":"dawn", "to":"yoru",
        "encrypted":base64.b64encode(c2).decode(),
        "signature":base64.b64encode(s2).decode()})
    print("[里程碑1] 跨主账号居然通了?! 不对")
except urllib.error.HTTPError as e:
    print(f"[里程碑1] 跨主账号被拒({e.code})，符合预期")
