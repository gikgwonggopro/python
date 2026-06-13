FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# 预装 Xray
RUN wget -q -O /tmp/xray.zip \
    "https://github.com/XTLS/Xray-core/releases/download/v1.8.11/Xray-linux-64.zip" \
    && unzip -o /tmp/xray.zip xray -d /tmp/ \
    && mv /tmp/xray /usr/local/bin/xray \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip

# 预装 cloudflared
RUN wget -q -O /usr/local/bin/cloudflared \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
    && chmod +x /usr/local/bin/cloudflared

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8001
CMD ["python", "app.py"]
