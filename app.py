import os
import base64
import json
import subprocess
import threading
import time
import stat
import re
from flask import Flask, Response, jsonify

app = Flask(__name__)

UUID = os.environ.get("UUID", "f929c4da-dc2e-4e0d-9a6f-1799036af214")
PORT = int(os.environ.get("PORT", "8001"))
NAME = os.environ.get("NAME", "dcdeploy-node")
WORK_DIR = "/tmp"
ARGO_DOMAIN_FILE = os.path.join(WORK_DIR, "argo_domain.txt")
argo_domain_cache = ""

def get_argo_domain():
    global argo_domain_cache
    if argo_domain_cache:
        return argo_domain_cache
    if os.path.exists(ARGO_DOMAIN_FILE):
        with open(ARGO_DOMAIN_FILE) as f:
            argo_domain_cache = f.read().strip()
    return argo_domain_cache

def generate_vmess_link(domain):
    config = {
        "v": "2", "ps": NAME, "add": domain, "port": "443",
        "id": UUID, "aid": "0", "scy": "auto", "net": "ws",
        "type": "none", "host": domain, "path": "/",
        "tls": "tls", "sni": domain, "alpn": ""
    }
    return "vmess://" + base64.b64encode(json.dumps(config).encode()).decode()

def start_xray():
    xray_path = os.path.join(WORK_DIR, "xray")
    if not os.path.exists(xray_path):
        print("[*] Downloading Xray...")
        subprocess.run(
            "wget -q -O /tmp/xray.zip "
            "'https://github.com/XTLS/Xray-core/releases/download/v1.8.11/Xray-linux-64.zip'",
            shell=True
        )
        subprocess.run("unzip -o /tmp/xray.zip xray -d /tmp/", shell=True)
        os.chmod(xray_path, stat.S_IRWXU)

    config = {
        "inbounds": [{
            "port": 8444,
            "listen": "127.0.0.1",
            "protocol": "vmess",
            "settings": {"clients": [{"id": UUID, "alterId": 0}]},
            "streamSettings": {
                "network": "ws",
                "wsSettings": {"path": "/"}
            }
        }],
        "outbounds": [{"protocol": "freedom"}]
    }
    with open(os.path.join(WORK_DIR, "xray_config.json"), "w") as f:
        json.dump(config, f)

    print("[*] Starting Xray...")
    subprocess.Popen(
        [xray_path, "run", "-c", os.path.join(WORK_DIR, "xray_config.json")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1)
    print("[*] Xray started.")

def start_argo():
    global argo_domain_cache
    cf_path = os.path.join(WORK_DIR, "cloudflared")
    if not os.path.exists(cf_path):
        print("[*] Downloading cloudflared...")
        subprocess.run(
            f"wget -q -O {cf_path} "
            "'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64'",
            shell=True
        )
        os.chmod(cf_path, stat.S_IRWXU)

    print("[*] Starting Argo...")
    log_path = os.path.join(WORK_DIR, "argo.log")
    with open(log_path, "w") as log_file:
        subprocess.Popen(
            [cf_path, "tunnel", "--url", "http://127.0.0.1:8444", "--no-autoupdate"],
            stdout=log_file, stderr=log_file
        )

    for _ in range(30):
        time.sleep(2)
        try:
            with open(log_path) as f:
                content = f.read()
            match = re.search(r'https://([a-zA-Z0-9\-]+\.trycloudflare\.com)', content)
            if match:
                domain = match.group(1)
                argo_domain_cache = domain
                with open(ARGO_DOMAIN_FILE, "w") as f:
                    f.write(domain)
                print(f"[*] Argo domain: {domain}")
                return
        except:
            pass
    print("[!] Argo domain not found")

@app.route('/')
def index():
    return Response("OK", mimetype='text/plain')

@app.route('/sub')
def sub():
    domain = get_argo_domain()
    if not domain:
        return Response("Not ready, retry in 1 min.", status=503)
    encoded = base64.b64encode(generate_vmess_link(domain).encode()).decode()
    return Response(encoded, mimetype='text/plain')

@app.route('/info')
def info():
    domain = get_argo_domain()
    if not domain:
        return jsonify({"status": "Argo not ready, retry in 1 min."})
    return jsonify({
        "name": NAME, "argo_domain": domain,
        "port": 443, "uuid": UUID,
        "path": "/", "network": "ws", "tls": "tls",
        "vmess_link": generate_vmess_link(domain)
    })

if __name__ == '__main__':
    threading.Thread(target=start_xray, daemon=True).start()
    time.sleep(2)
    threading.Thread(target=start_argo, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT)
