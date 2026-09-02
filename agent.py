import argparse
import base64
import json
import time
import urllib.request

import crypto_util

SERVER = "http://127.0.0.1:8000"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="账号名")
    ap.add_argument("--send", nargs=2, metavar=("TO", "MESSAGE"))
    ap.add_argument("--listen", action="store_true")
    args = ap.parse_args()

    priv, _pub = crypto_util.gen_keypair(args.name)
    with open(_pub) as f:
        pub_pem = f.read()

    api("/api/register", {"name": args.name, "public_key": pub_pem})
    print(f"[{args.name}] 已登记，身份公钥: {pub_pem.splitlines()[0]}")

    if args.send:
        to, msg = args.send
        their_pub = api(f"/api/public?name={to}")["public_key"]
        cipher = crypto_util.encrypt(their_pub, msg.encode())
        sig = crypto_util.sign(priv, cipher)
        api("/api/send", {
            "from": args.name, "to": to,
            "encrypted": base64.b64encode(cipher).decode(),
            "signature": base64.b64encode(sig).decode(),
        })
        print(f"[{args.name}] -> {to}  已发出(明文:{msg!r}, 密文字节:{len(cipher)})")

    if args.listen or not args.send:
        print(f"[{args.name}] 开始监听信箱，Ctrl+C 退出")
        while True:
            r = api(f"/api/inbox?name={args.name}")
            for m in r.get("messages", []):
                try:
                    plain = crypto_util.decrypt(priv, base64.b64decode(m["encrypted"]))
                    print(f"[{args.name}] <- {m['from']}: {plain.decode()}")
                except Exception as e:
                    print(f"[{args.name}] 消息解密失败: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
