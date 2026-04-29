# contool - 隐蔽 LLM API 中继

通过中间节点，将公司内网的大模型 API 安全中继到外部，所有流量伪装为正常 HTTPS 网站访问。

## 架构

```
A (校园网/Windows)          B (家里, 公网IP)              C (公司内网)
     │                          │                           │
     │ HTTPS 请求               │     WSS 出站连接          │
     │ /v1/chat/completions ──► │ ◄── /ws/notifications     │
     │ (像调普通 API)           │ (像普通 WebSocket 应用)    │
     │                          │                           │
     │ ◄── JSON 响应 ────────── │ ──► 内网 LLM API ──────►  │
```

- **A**：用户端（Windows 11 / Linux / Mac），发送 API 请求
- **B**：中继服务器，有公网 IP，对外是普通网站
- **C**：隧道客户端，在公司内网，主动出站连接 B

## 快速开始

### 前提条件

三台机器都需要：
- Python 3.10+
- 安装依赖：`pip install aiohttp cryptography`

### 第一步：在 B 上配置（有公网 IP 的机器）

```bash
git clone git@github.com:yinrong/contool.git
cd contool
pip install aiohttp cryptography
python setup.py
# 选择 B，输入公网 IP 和端口
# 会自动生成密钥、证书，并打印两个邀请码
```

输出示例：
```
【给 A（用户端）的邀请码】:
eyJyb2xlIjoiQSIsImFkZHIiOi...

【给 C（隧道客户端）的邀请码】:
eyJyb2xlIjoiQyIsImFkZHIiOi...
```

把邀请码分别发给 A 和 C。

### 第二步：在 C 上配置（公司内网机器）

```bash
git clone git@github.com:yinrong/contool.git
cd contool
pip install aiohttp cryptography
python setup.py
# 选择 C，粘贴邀请码，输入内网 LLM API 地址
```

### 第三步：在 A 上配置（Windows 11）

```powershell
git clone git@github.com:yinrong/contool.git
cd contool
pip install aiohttp cryptography
python setup.py
# 选择 A，粘贴邀请码
```

或者双击 `start_a.bat`，会自动引导配置。

## 启动服务

启动顺序：**B → C → A**

```bash
# B 上：
python relay_server.py
# 端口 443 需要 sudo: sudo python relay_server.py

# C 上：
python tunnel_client.py

# A 上（测试）：
python api_client.py "你好"
python api_client.py --stream "给我讲个故事"
```

## Claude Code 集成

在 A 机器上设置环境变量，让 Claude Code 通过中继访问 LLM：

**Windows PowerShell：**
```powershell
$env:ANTHROPIC_BASE_URL = "https://B的公网IP:443"
$env:ANTHROPIC_API_KEY = "你的AUTH_TOKEN（见.env文件）"
claude
```

**Linux/Mac：**
```bash
export ANTHROPIC_BASE_URL="https://B的公网IP:443"
export ANTHROPIC_API_KEY="你的AUTH_TOKEN"
claude
```

> 注意：由于使用自签名证书，可能需要设置 `NODE_TLS_REJECT_UNAUTHORIZED=0`（Node.js 客户端）。建议后续购买便宜域名 + Let's Encrypt 证书。

## 配置参考

`.env` 文件由 `setup.py` 自动生成，字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| RELAY_HOST | B 监听地址 | 0.0.0.0 |
| RELAY_PORT | B 监听端口 | 443 |
| RELAY_ADDR | B 的公网 IP | 1.2.3.4 |
| AUTH_TOKEN | A→B 认证令牌 | sk-xxx |
| TUNNEL_SECRET | C→B 隧道密钥 | tun-xxx |
| INTERNAL_LLM_BASE | C 内网 LLM 地址 | https://10.0.1.50:8080 |
| RELAY_TLS | 是否启用 TLS | auto/true/false |
| CERT_FILE | TLS 证书路径 | certs/server.crt |
| KEY_FILE | TLS 私钥路径 | certs/server.key |

## 本地测试

```bash
bash test_local.sh
```

会在本机同时启动 mock LLM、relay server、tunnel client，运行 4 个测试。

## 文件说明

| 文件 | 用途 |
|------|------|
| `setup.py` | 全自动配置向导 |
| `relay_server.py` | B：中继服务器 |
| `tunnel_client.py` | C：隧道客户端 |
| `api_client.py` | A：API 调用客户端 |
| `config.py` | 配置加载（自动读 .env） |
| `gen_cert.py` | TLS 证书生成器 |
| `mock_llm.py` | 测试用 mock LLM 服务 |
| `static/index.html` | 伪装网站首页 |
| `test_local.sh` | 本地端到端测试 |
| `start_a.bat` | Windows A 端启动脚本 |

## 伪装策略

- B 对外仅 443 端口，未认证访问返回正常博客网站
- C→B 的 WebSocket 连接与普通 Web 应用无异
- 所有流量标准 TLS 加密，无特殊协议指纹
- 心跳间隔随机化，定期重连避免长连接特征
- API 路径使用 OpenAI 标准格式 `/v1/chat/completions`
