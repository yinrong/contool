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

> **B 在路由器/NAT 后面？** 需要在路由器管理页面设置端口转发，将外部端口（如 8443）转发到 B 的内网 IP 和端口。
>
> **家用宽带注意**：国内运营商普遍封锁 80/443 端口，推荐使用 **8443**（标准 HTTPS 备用端口，不会引起注意）。

### 第一步：在 B 上配置（有公网 IP 的机器）

```bash
git clone git@github.com:yinrong/contool.git
cd contool
python -m venv venv
source venv/bin/activate
pip install aiohttp cryptography
python setup.py
# 选择 B，输入公网 IP（或域名）和端口
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
python -m venv venv
source venv/bin/activate
pip install aiohttp cryptography
python setup.py
# 选择 C，粘贴邀请码，输入内网 LLM API 地址
```

### 第三步：在 A 上配置（Windows 11）

```powershell
git clone git@github.com:yinrong/contool.git
cd contool
python -m venv venv
venv\Scripts\activate
pip install aiohttp cryptography
python setup.py
# 选择 A，粘贴邀请码
```

或者双击 `start_a.bat`，会自动引导配置。

## 升级到正式 TLS 证书（强烈推荐）

默认配置使用自签名证书，TLS 握手中证书 CN 可见，会暴露工具用途。
使用真实域名 + Let's Encrypt 证书后，流量与任何普通 HTTPS 网站完全一致。

### 第一步：注册 DuckDNS 免费域名（浏览器手动操作，仅一次）

1. 打开 [duckdns.org](https://www.duckdns.org)，用 Google / GitHub 登录
2. 在 "domains" 栏输入一个子域名（如 `my-relay`），点击 **add domain**
3. 记下页面顶部的 **token**（格式类似 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）

### 第二步：在 B 上运行一键配置脚本

```bash
bash setup_tls.sh
```

脚本会自动完成：
- 将 DuckDNS A 记录指向 B 当前公网 IP
- 安装 `certbot-dns-duckdns`（如已安装则升级）
- 通过 DNS 验证申请 Let's Encrypt 正式证书（全程无需手动操作）
- 更新 `.env` 中的证书路径和域名
- 输出新的邀请码（需重新发给 A 和 C）

运行后把新邀请码重新分别发给 A 和 C，在 A/C 上重跑 `python setup.py`。

**证书有效期 90 天，续期只需重新运行 `bash setup_tls.sh`。**

---

## 启动服务

启动顺序：**B → C → A**

```bash
# B 上（进入 venv 后）：
cd ~/contool && source venv/bin/activate
nohup python relay_server.py > relay.log 2>&1 &
# 用 nohup 后台运行，SSH 断开不会中断服务
# 查看日志：tail -f relay.log
# 停止：kill $(pgrep -f relay_server.py)

# C 上（进入 venv 后）：
cd ~/contool && source venv/bin/activate
nohup python _server.py > server.log 2>&1 &

# A 上（Windows，测试）：
cd contool
venv\Scripts\activate
python api_client.py "你好"
python api_client.py --stream "给我讲个故事"
# AUTH_TOKEN 已由 setup.py 从邀请码写入 .env，无需手动配置

# A 上（Linux/Mac，测试）：
cd ~/contool && source venv/bin/activate
python api_client.py "你好"
python api_client.py --stream "给我讲个故事"
```

> **提示**：如果有 `tmux` 或 `screen`，也可以用它们代替 `nohup` 管理长期进程。

## Claude Code 集成

在 A 机器上设置环境变量，让 Claude Code 通过中继访问 LLM：

**Windows PowerShell：**
```powershell
$env:ANTHROPIC_BASE_URL = "https://域名或IP:端口"
$env:ANTHROPIC_API_KEY = "AUTH_TOKEN（见.env文件）"
claude
```

**Linux/Mac：**
```bash
export ANTHROPIC_BASE_URL="https://域名或IP:端口"
export ANTHROPIC_API_KEY="AUTH_TOKEN"
claude
```

> 使用自签名证书时（未运行 `setup_tls.sh`），Node.js 客户端需额外设置：
> `NODE_TLS_REJECT_UNAUTHORIZED=0`
> 运行 `setup_tls.sh` 换成正式证书后无需此设置。

## 配置参考

`.env` 文件由 `setup.py` 自动生成，字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| RELAY_HOST | B 监听地址 | 0.0.0.0 |
| RELAY_PORT | B 监听端口 | 8443 |
| RELAY_ADDR | B 的公网 IP 或域名 | mysite.duckdns.org |
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
| `_server.py` | C：服务进程 |
| `api_client.py` | A：API 调用客户端 |
| `config.py` | 配置加载（自动读 .env） |
| `gen_cert.py` | 自签名 TLS 证书生成器 |
| `setup_tls.sh` | B：DuckDNS + Let's Encrypt 一键配置 |
| `mock_llm.py` | 测试用 mock LLM 服务 |
| `static/index.html` | 伪装网站首页 |
| `test_local.sh` | 本地端到端测试 |
| `start_a.bat` | Windows A 端启动脚本 |

## 伪装策略

- B 对外仅一个 HTTPS 端口（如 8443），未认证访问返回正常博客网站
- C→B 的 WebSocket 连接与普通 Web 应用无异
- 所有流量标准 TLS 加密，无特殊协议指纹
- 心跳间隔随机化，定期重连避免长连接特征
- API 路径使用 OpenAI 标准格式 `/v1/chat/completions`
