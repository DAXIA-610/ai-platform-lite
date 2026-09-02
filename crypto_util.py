import os
import subprocess
import tempfile


def _run(args, input_bytes=None):
    p = subprocess.run(args, input=input_bytes, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("openssl 失败: " + p.stderr.decode(errors="replace"))
    return p.stdout


def gen_keypair(name, keys_dir="keys"):
    os.makedirs(keys_dir, exist_ok=True)
    priv = os.path.join(keys_dir, f"{name}_private.pem")
    pub = os.path.join(keys_dir, f"{name}_public.pem")
    if not (os.path.exists(priv) and os.path.exists(pub)):
        _run(["openssl", "genpkey", "-algorithm", "RSA",
              "-pkeyopt", "rsa_keygen_bits:2048", "-out", priv])
        _run(["openssl", "rsa", "-in", priv, "-pubout", "-out", pub])
    return priv, pub


def _encrypt_impl(pub_path, plaintext):
    return _run([
        "openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", pub_path,
        "-pkeyopt", "rsa_padding_mode:oaep",
        "-pkeyopt", "rsa_oaep_md:sha256",
        "-pkeyopt", "rsa_mgf1_md:sha256",
    ], input_bytes=plaintext)


def encrypt(pub_pem_str, plaintext_bytes):
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(pub_pem_str)
        path = f.name
    try:
        return _encrypt_impl(path, plaintext_bytes)
    finally:
        os.unlink(path)


def decrypt(priv_path, cipher_bytes):
    return _run([
        "openssl", "pkeyutl", "-decrypt", "-inkey", priv_path,
        "-pkeyopt", "rsa_padding_mode:oaep",
        "-pkeyopt", "rsa_oaep_md:sha256",
        "-pkeyopt", "rsa_mgf1_md:sha256",
    ], input_bytes=cipher_bytes)


def sign(priv_path, data_bytes):
    return _run(["openssl", "dgst", "-sha256", "-sign", priv_path],
                input_bytes=data_bytes)


def verify(pub_pem_str, data_bytes, sig_bytes):
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(pub_pem_str)
        pub_path = f.name
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(sig_bytes)
        sig_path = f.name
    try:
        p = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", pub_path,
             "-signature", sig_path],
            input=data_bytes, capture_output=True)
        return p.returncode == 0
    finally:
        os.unlink(pub_path)
        os.unlink(sig_path)
