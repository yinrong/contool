import os

RELAY_HOST = os.environ.get("RELAY_HOST", "0.0.0.0")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "443"))

# B's public address (C and A connect here)
RELAY_ADDR = os.environ.get("RELAY_ADDR", "127.0.0.1")

# Auth tokens
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "sk-contool-default-token-change-me")
TUNNEL_SECRET = os.environ.get("TUNNEL_SECRET", "tun-contool-default-secret-change-me")

# WebSocket path (disguised as a notification endpoint)
WS_PATH = "/ws/notifications"

# Internal LLM API base URL (C's internal network)
INTERNAL_LLM_BASE = os.environ.get("INTERNAL_LLM_BASE", "http://127.0.0.1:9000")

# TLS cert paths
CERT_FILE = os.environ.get("CERT_FILE", "certs/server.crt")
KEY_FILE = os.environ.get("KEY_FILE", "certs/server.key")

# Whether relay uses TLS (auto-detected from cert files, or override with env)
RELAY_TLS = os.environ.get("RELAY_TLS", "auto")  # "auto", "true", "false"

# Heartbeat interval range (seconds) - randomized to avoid pattern detection
HEARTBEAT_MIN = 20
HEARTBEAT_MAX = 40

# Reconnect backoff
RECONNECT_BASE = 5
RECONNECT_MAX = 60

# Request timeout (seconds)
REQUEST_TIMEOUT = 120
