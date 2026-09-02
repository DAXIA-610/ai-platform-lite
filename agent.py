import argparse
import base64
import json
import sys
import time
import urllib.request
import os

import crypto_util

SERVER = os.environ.get("SERVER", "http://127.0.0.1:8000")
KEYS_DIR = "keys"


def api(path, payload=None):
    url = SERVER + path
    if payload is not None:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _key_path(name):
    return os.path.join(KEYS_DIR, f"{name}_private.pem")


def cmd_master(name):
    r = api("/api/master/register", {"name": name})
    print(f"[主账号] {r['name']} 注册成功")


def cmd_create(owner, ai_name):
    r = api("/api/ai/create", {"owner": owner, "ai_name": ai_name})
    os.makedirs(KEYS_DIR, exist_ok=True)
    priv = os.path.join(KEYS_DIR, f"{ai_name}_private.pem")
    pub = os.path.join(KEYS_DIR, f"{ai_name}_public.pem")
    with open(priv, "w") as f:
        f.write(r["private_key"])
    with open(pub, "w") as f:
        f.write(r["public_key"])
    print(f"[AI] {ai_name} 已在主账号 {owner} 名下创建，私钥存入 keys/{ai_name}_private.pem")


def cmd_send(ai_name, to, msg):
    priv = _key_path(ai_name)
    if not os.path.exists(priv):
        print(f"[错误] 找不到 {ai_name} 的私钥，先 create"); sys.exit(1)
    their_pub = api(f"/api/public?name={to}")["public_key"]
    cipher = crypto_util.encrypt(their_pub, msg.encode())
    sig = crypto_util.sign(priv, cipher)
    api("/api/send", {"from": ai_name, "to": to,
                       "encrypted": base64.b64encode(cipher).decode(),
                       "signature": base64.b64encode(sig).decode()})
    print(f"[AI {ai_name}] -> {to}  已发出(明文:{msg!r}, 密文:{len(cipher)}字节)")


def cmd_listen(ai_name):
    priv = _key_path(ai_name)
    if not os.path.exists(priv):
        print(f"[错误] 找不到 {ai_name} 的私钥，先 create"); sys.exit(1)
    print(f"[AI {ai_name}] 开始监听信箱，Ctrl+C 退出")
    while True:
        try:
            r = api(f"/api/inbox?name={ai_name}")
        except Exception:
            time.sleep(2)
            continue
        for m in r.get("messages", []):
            try:
                plain = crypto_util.decrypt(priv, base64.b64decode(m["encrypted"]))
                print(f"[AI {ai_name}] <- {m['from']}: {plain.decode()}")
            except Exception as e:
                print(f"[AI {ai_name}] 解密失败: {e}")
        time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("master"); p1.add_argument("name")
    p2 = sub.add_parser("create"); p2.add_argument("owner"); p2.add_argument("ai_name")
    p3 = sub.add_parser("send"); p3.add_argument("ai_name"); p3.add_argument("to"); p3.add_argument("message")
    p4 = sub.add_parser("listen"); p4.add_argument("ai_name")

    args = ap.parse_args()
    if args.cmd == "master":
        cmd_master(args.name)
    elif args.cmd == "create":
        cmd_create(args.owner, args.ai_name)
    elif args.cmd == "send":
        cmd_send(args.ai_name, args.to, args.message)
    elif args.cmd == "listen":
        cmd_listen(args.ai_name)


if __name__ == "__main__":
    main()
