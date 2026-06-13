FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q -O /tmp/sb.tar.gz \
    "https://github.com/SagerNet/sing-box/releases/download/v1.8.0/sing-box-1.8.0-linux-amd64.tar.gz" \
    && tar -xzf /tmp/sb.tar.gz -C /tmp/ \
    && find /tmp -name "sing-box" -type f | head -1 | xargs -I{} mv {} /usr/local/bin/sing-box \
    && chmod +x /usr/local/bin/sing-box \
    && rm -rf /tmp/sb.tar.gz /tmp/sing-box-*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8001
CMD ["python", "app.py"]
