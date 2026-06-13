import os
import base64
import json
import subprocess
import threading
import time
import stat
from flask import Flask, Response, jsonify

app = Flask(__name__)

# ========== 配置 ==========
UUID = os.environ.get("UUID", "f929c4da-dc2e-4e0d-9a6f-1799036af214")
PORT = int(os.environ.get("PORT", "8001"))
NAME = os.environ.get("NAME", "dcdeploy-node")
DOMAIN = os.environ.get("DOMAIN", "")

WORK_DIR = "/tmp"

# ========== 下载 sing-box ==========
def download_singbox():
    singbox_path = "/usr/local/bin/sing-box"
    if os.path.exists(singbox_path):
        return singbox_path
    singbox_path = os.path.join(WORK_DIR, "sing-box")
    if os.path.exists(singbox_path):
        return singbox_path
    print("[*] Downloading sing-box...")
    url = "https://github.com/SagerNet/sing-box/releases/download/v1.8.0/sing-box-1.8.0-linux-amd64.tar.gz"
    subprocess.run(f"wget -q -O /tmp/sb.tar.gz '{url}'", shell=True)
    subprocess.run("tar -xzf /tmp/sb.tar.gz -C /tmp/", shell=True)
    subprocess.run("find /tmp -name 'sing-box' -type f | head -1 | xargs -I{{}} mv {{}} /tmp/sing-box", shell=True)
    os.chmod(singbox_path, stat.S_IRWXU)
    return singbox_path

# ========== sing-box 配置（VLESS + H2） ==========
def write_singbox_config():
    config = {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "vless",
                "listen": "0.0.0.0",
                "listen_port": PORT,
                "users": [{"uuid": UUID, "flow": ""}],
                "transport": {
                    "type": "http",
                    "host": [DOMAIN] if DOMAIN else [],
                    "path": "/vless"
                }
            }
        ],
        "outbounds": [
            {"type": "direct", "tag": "direct"}
        ]
    }
    config_path = os.path.join(WORK_DIR, "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    return config_path

# ========== 启动 sing-box ==========
def start_singbox():
    singbox_path = download_singbox()
    config_path = write_singbox_config()
    print("[*] Starting sing-box on port", PORT)
    subprocess.Popen(
        [singbox_path, "run", "-c", config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(2)
    print("[*] sing-box started.")

# ========== 生成 VLESS H2 节点链接 ==========
def generate_vless_link():
    if not DOMAIN:
        return None
    link = (
        f"vless://{UUID}@{DOMAIN}:443"
        f"?encryption=none&security=tls&sni={DOMAIN}"
        f"&type=h2&path=%2Fvless&host={DOMAIN}"
        f"#{NAME}"
    )
    return link

# ========== 路由 ==========
@app.route('/')
def index():
    return Response("OK", mimetype='text/plain')

@app.route('/sub')
def sub():
    link = generate_vless_link()
    if not link:
        return Response("Please set DOMAIN environment variable.", status=503)
    encoded = base64.b64encode(link.encode()).decode()
    return Response(encoded, mimetype='text/plain')

@app.route('/info')
def info():
    link = generate_vless_link()
    return jsonify({
        "name": NAME,
        "domain": DOMAIN or "not set",
        "port": 443,
        "uuid": UUID,
        "path": "/vless",
        "network": "h2",
        "tls": "tls",
        "vless_link": link or "Set DOMAIN env var first"
    })

# ========== 启动 ==========
if __name__ == '__main__':
    threading.Thread(target=start_singbox, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT)
