import base64
import json
import urllib.request

import crypto_util


class AITool:
    def __init__(self, server, ai_name, token, private_key_pem):
        self.server = server.rstrip("/")
        self.ai_name = ai_name
        self.token = token
        self.priv_pem = private_key_pem

    def _req(self, path, payload=None, method="GET"):
        url = self.server + path
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        else:
            req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    def _pubkey(self, name):
        return self._req("/api/public?name=" + name)["public_key"]

    def send(self, to, message):
        cipher = crypto_util.encrypt(self._pubkey(to), message.encode())
        sig = crypto_util.sign_pem(self.priv_pem, cipher)
        self._req("/api/ai/send", {
            "to": to,
            "encrypted": base64.b64encode(cipher).decode(),
            "signature": base64.b64encode(sig).decode(),
        }, method="POST")
        return f"已发给 {to}"

    def read(self):
        r = self._req("/api/ai/inbox")
        out = []
        for m in r.get("messages", []):
            plain = crypto_util.decrypt_pem(self.priv_pem, base64.b64decode(m["encrypted"]))
            out.append((m["from"], plain.decode()))
        return out
