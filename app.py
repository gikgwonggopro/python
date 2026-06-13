import os
import uuid
import base64
import subprocess
import threading
import time
import json
import stat
from flask import Flask, Response, jsonify

app = Flask(__name__)

# ========== 配置 ==========
UUID = os.environ.get("UUID", "f929c4da-dc2e-4e0d-9a6f-1799036af214")
PORT = int(os.environ.get("PORT", "8001"))
ARGO_PORT = int(os.environ.get("ARGO_PORT", "8001"))
NAME = os.environ.get("NAME", "dcdeploy-node")
PROJECT_URL = os.environ.get("PROJECT_URL", "")

WORK_DIR = "/tmp"
ARGO_DOMAIN_FILE = os.path.join(WORK_DIR, "argo_domain.txt")

# ========== 下载 sing-box ==========
def download_singbox():
    singbox_path = os.path.join(WORK_DIR, "sing-box")
    if os.path.exists(singbox_path):
        return singbox_path
    print("[*] Downloading sing-box...")
    url = "https://github.com/SagerNet/sing-box/releases/download/v1.8.0/sing-box-1.8.0-linux-amd64.tar.gz"
    subprocess.run(f"wget -q -O /tmp/sb.tar.gz '{url}'", shell=True)
    subprocess.run("tar -xzf /tmp/sb.tar.gz -C /tmp/", shell=True)
    subprocess.run("mv /tmp/sing-box-1.8.0-linux-amd64/sing-box /tmp/sing-box", shell=True)
    os.chmod(singbox_path, stat.S_IRWXU)
    print("[*] sing-box downloaded.")
    return singbox_path

# ========== 下载 cloudflared ==========
def download_cloudflared():
    cf_path = os.path.join(WORK_DIR, "cloudflared")
    if os.path.exists(cf_path):
        return cf_path
    print("[*] Downloading cloudflared...")
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    subprocess.run(f"wget -q -O {cf_path} '{url}'", shell=True)
    os.chmod(cf_path, stat.S_IRWXU)
    print("[*] cloudflared downloaded.")
    return cf_path

# ========== 生成 sing-box 配置 ==========
def write_singbox_config():
    config = {
        "inbounds": [
            {
                "type": "vmess",
                "listen": "0.0.0.0",
                "listen_port": ARGO_PORT,
                "users": [{"uuid": UUID, "alterId": 0}],
                "transport": {
                    "type": "ws",
                    "path": "/vmess"
                }
            }
        ],
        "outbounds": [
            {"type": "direct"},
            {"type": "dns", "tag": "dns-out"}
        ],
        "dns": {
            "servers": [{"address": "8.8.8.8"}]
        }
    }
    config_path = os.path.join(WORK_DIR, "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    return config_path

# ========== 启动 sing-box ==========
def start_singbox():
    singbox_path = download_singbox()
    config_path = write_singbox_config()
    print("[*] Starting sing-box...")
    subprocess.Popen(
        [singbox_path, "run", "-c", config_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    print("[*] sing-box started.")

# ========== 启动 Argo 隧道 ==========
def start_argo():
    cf_path = download_cloudflared()
    print("[*] Starting Argo tunnel...")
    log_file = open(os.path.join(WORK_DIR, "argo.log"), "w")
    proc = subprocess.Popen(
        [cf_path, "tunnel", "--url", f"http://localhost:{ARGO_PORT}", "--no-autoupdate"],
        stdout=log_file,
        stderr=log_file
    )
    # 等待获取域名
    for _ in range(30):
        time.sleep(2)
        try:
            with open(os.path.join(WORK_DIR, "argo.log"), "r") as f:
                content = f.read()
            for line in content.splitlines():
                if "trycloudflare.com" in line:
                    import re
                    match = re.search(r'https://([a-zA-Z0-9\-]+\.trycloudflare\.com)', line)
                    if match:
                        domain = match.group(1)
                        with open(ARGO_DOMAIN_FILE, "w") as df:
                            df.write(domain)
                        print(f"[*] Argo domain: {domain}")
                        return domain
        except:
            pass
    print("[!] Could not get Argo domain")
    return None

# ========== 生成节点链接 ==========
def get_argo_domain():
    if os.path.exists(ARGO_DOMAIN_FILE):
        with open(ARGO_DOMAIN_FILE, "r") as f:
            return f.read().strip()
    return None

def generate_vmess_link(domain):
    config = {
        "v": "2",
        "ps": NAME,
        "add": domain,
        "port": "443",
        "id": UUID,
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": domain,
        "path": "/vmess",
        "tls": "tls",
        "sni": domain,
        "alpn": ""
    }
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    return f"vmess://{encoded}"

# ========== Flask 路由 ==========
@app.route('/')
def index():
    return Response("Service is running.", mimetype='text/plain')

@app.route('/sub')
def sub():
    domain = get_argo_domain()
    if not domain:
        return Response("Argo tunnel not ready yet. Please wait and retry.", status=503)
    vmess = generate_vmess_link(domain)
    encoded = base64.b64encode(vmess.encode()).decode()
    return Response(encoded, mimetype='text/plain')

@app.route('/info')
def info():
    domain = get_argo_domain()
    if not domain:
        return jsonify({"status": "Argo not ready"}), 503
    vmess = generate_vmess_link(domain)
    return jsonify({
        "name": NAME,
        "argo_domain": domain,
        "uuid": UUID,
        "port": 443,
        "path": "/vmess",
        "tls": "tls",
        "vmess_link": vmess
    })

# ========== 启动 ==========
def initialize():
    t1 = threading.Thread(target=start_singbox)
    t1.start()
    t1.join()
    t2 = threading.Thread(target=start_argo)
    t2.start()

if __name__ == '__main__':
    threading.Thread(target=initialize).start()
    app.run(host='0.0.0.0', port=PORT)
