import base64, json, urllib.request
import crypto_util

S = "http://127.0.0.1:8000"

def api(path, payload=None):
    if payload is not None:
        req = urllib.request.Request(S+path, data=json.dumps(payload).encode(),
              headers={"Content-Type":"application/json"}, method="POST")
    else:
        req = urllib.request.Request(S+path, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

keys = {}
for n in ("alice","bob"):
    priv, pub = crypto_util.gen_keypair(n)
    keys[n] = priv
    with open(pub) as f: pem = f.read()
    api("/api/register", {"name":n, "public_key":pem})
    print(f"[登记] {n} ok")

bob_pub = api(f"/api/public?name=bob")["public_key"]
msg = "你好，我是alice"
cipher = crypto_util.encrypt(bob_pub, msg.encode())
sig = crypto_util.sign(keys["alice"], cipher)
api("/api/send", {"from":"alice","to":"bob",
    "encrypted":base64.b64encode(cipher).decode(),
    "signature":base64.b64encode(sig).decode()})
print(f"[发信] alice -> bob  密文字节={len(cipher)}")

r = api("/api/inbox?name=bob")
for m in r["messages"]:
    plain = crypto_util.decrypt(keys["bob"], base64.b64decode(m["encrypted"]))
    print(f"[收信] bob <- {m['from']}: {plain.decode()}")

fake = crypto_util.sign(keys["bob"], cipher)
try:
    api("/api/send", {"from":"alice","to":"bob",
        "encrypted":base64.b64encode(cipher).decode(),
        "signature":base64.b64encode(fake).decode()})
    print("[防伪] 被接受了?! 有问题")
except urllib.error.HTTPError as e:
    print(f"[防伪] 被后端拒绝({e.code})")
