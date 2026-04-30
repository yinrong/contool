#!/bin/bash
# 在 B 上运行：一键申请 DuckDNS + Let's Encrypt 正式证书
# 支持重复运行（会清理旧证书重新申请）
set -e

cd "$(dirname "$0")"

echo "========================================"
echo "  DuckDNS + Let's Encrypt 一键配置"
echo "========================================"
echo ""
echo "前提：已在 https://www.duckdns.org 注册并创建子域名"
echo ""

read -p "DuckDNS 子域名（不含 .duckdns.org）: " SUBDOMAIN
read -p "DuckDNS Token: " DUCKDNS_TOKEN
read -p "邮箱（Let's Encrypt 续期通知用）: " EMAIL

DOMAIN="${SUBDOMAIN}.duckdns.org"
CERT_DIR="$(pwd)/certs/letsencrypt"

# 获取当前公网 IP
echo ""
PUBLIC_IP=$(curl -s https://api.ipify.org 2>/dev/null || curl -s https://ifconfig.me)
if [ -z "$PUBLIC_IP" ]; then
    read -p "无法自动获取公网 IP，请手动输入: " PUBLIC_IP
fi
echo "当前公网 IP：$PUBLIC_IP"

# 更新 DuckDNS A 记录
echo "正在更新 DuckDNS A 记录..."
RESP=$(curl -s "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=${PUBLIC_IP}")
if [ "$RESP" != "OK" ]; then
    echo "错误：DuckDNS 更新失败（返回：$RESP）"
    echo "请检查 Token 和子域名是否正确"
    exit 1
fi
echo "✓ A 记录已指向 $PUBLIC_IP"

# 安装 certbot-dns-duckdns（支持重新安装）
echo ""
echo "正在安装 certbot-dns-duckdns..."
pip install -q --upgrade certbot certbot-dns-duckdns
echo "✓ certbot-dns-duckdns 已就绪"

# 写凭据文件
mkdir -p "$CERT_DIR"
CREDS_FILE="${CERT_DIR}/duckdns.ini"
cat > "$CREDS_FILE" <<EOF
dns_duckdns_token = ${DUCKDNS_TOKEN}
EOF
chmod 600 "$CREDS_FILE"

# 清理旧证书（支持重新申请）
if [ -d "${CERT_DIR}/live/${DOMAIN}" ]; then
    echo "检测到已有证书，清理后重新申请..."
    rm -rf "${CERT_DIR}/live/${DOMAIN}" \
           "${CERT_DIR}/archive/${DOMAIN}" \
           "${CERT_DIR}/renewal/${DOMAIN}.conf" 2>/dev/null || true
fi

# 申请证书
echo ""
echo "正在通过 DNS 验证申请 Let's Encrypt 证书（约等待 40 秒）..."
certbot certonly \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --dns-duckdns \
    --dns-duckdns-credentials "$CREDS_FILE" \
    --dns-duckdns-propagation-seconds 40 \
    --config-dir "$CERT_DIR" \
    --work-dir "${CERT_DIR}/work" \
    --logs-dir "${CERT_DIR}/logs" \
    -d "$DOMAIN"

CERT_FILE="${CERT_DIR}/live/${DOMAIN}/fullchain.pem"
KEY_FILE="${CERT_DIR}/live/${DOMAIN}/privkey.pem"

if [ ! -f "$CERT_FILE" ]; then
    echo "错误：证书文件未生成，请查看日志 ${CERT_DIR}/logs/"
    exit 1
fi
echo "✓ 证书申请成功：$CERT_FILE"

# 更新 .env
echo ""
echo "正在更新 .env..."
python3 - <<PYEOF
import os

env_path = ".env"
updates = {
    "RELAY_ADDR": "${DOMAIN}",
    "CERT_FILE": "${CERT_FILE}",
    "KEY_FILE": "${KEY_FILE}",
    "RELAY_TLS": "true",
}

lines = []
if os.path.exists(env_path):
    with open(env_path) as f:
        lines = f.readlines()

found = set()
new_lines = []
for line in lines:
    key = line.split("=")[0].strip()
    if key in updates:
        new_lines.append(f"{key}={updates[key]}\n")
        found.add(key)
    else:
        new_lines.append(line)
for k, v in updates.items():
    if k not in found:
        new_lines.append(f"{k}={v}\n")

with open(env_path, "w") as f:
    f.writelines(new_lines)
print("✓ .env 已更新")
PYEOF

# 重新生成邀请码
echo ""
python3 - <<PYEOF
import os, json, base64

# 读取 .env
env = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

addr = env.get("RELAY_ADDR", "")
port = int(env.get("RELAY_PORT", "443"))
auth_token = env.get("AUTH_TOKEN", "")
tunnel_secret = env.get("TUNNEL_SECRET", "")

invite_a = base64.urlsafe_b64encode(json.dumps({
    "role": "A", "addr": addr, "port": port, "auth_token": auth_token
}).encode()).decode()

invite_c = base64.urlsafe_b64encode(json.dumps({
    "role": "C", "addr": addr, "port": port, "tunnel_secret": tunnel_secret
}).encode()).decode()

print("=" * 60)
print("配置完成！域名已切换，请将新邀请码发给 A 和 C：")
print("=" * 60)
print(f"\n【给 A（用户端）的新邀请码】:")
print(invite_a)
print(f"\n【给 C（隧道客户端）的新邀请码】:")
print(invite_c)
print()
print(f"Claude Code 配置：")
print(f"  ANTHROPIC_BASE_URL=https://{addr}:{port}")
print(f"  ANTHROPIC_API_KEY={auth_token}")
print("=" * 60)
PYEOF

echo ""
echo "证书有效期 90 天，续期命令："
echo "  bash setup_tls.sh  （重新运行即可，无需额外操作）"
