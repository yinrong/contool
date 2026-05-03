import os

# 自动加载 .env 文件
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

RELAY_HOST = os.environ.get("RELAY_HOST", "0.0.0.0")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "443"))

# B 的公网地址（C 和 A 连这里）
RELAY_ADDR = os.environ.get("RELAY_ADDR", "127.0.0.1")

# 认证 token
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "sk-contool-default-token-change-me")
TUNNEL_SECRET = os.environ.get("TUNNEL_SECRET", "tun-contool-default-secret-change-me")

# WebSocket 路径（伪装为通知推送端点）
WS_PATH = "/ws/notifications"

# 内网 LLM API 地址和认证（C 的内网）
INTERNAL_LLM_BASE = os.environ.get("INTERNAL_LLM_BASE", "http://127.0.0.1:9000")
INTERNAL_LLM_KEY = os.environ.get("INTERNAL_LLM_KEY", "")

# TLS 证书路径
CERT_FILE = os.environ.get("CERT_FILE", "certs/server.crt")
KEY_FILE = os.environ.get("KEY_FILE", "certs/server.key")

# 是否使用 TLS（auto 时根据证书文件是否存在判断）
RELAY_TLS = os.environ.get("RELAY_TLS", "auto")

# 心跳间隔范围（秒）- 随机化避免检测
HEARTBEAT_MIN = 20
HEARTBEAT_MAX = 40

# 重连退避
RECONNECT_BASE = 5
RECONNECT_MAX = 60

# 请求超时（秒）
REQUEST_TIMEOUT = 120
