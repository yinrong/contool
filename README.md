# contool - 隐蔽 LLM API 中继（claude-code-proxy）

通过中间节点，将公司内网的大模型 API 安全中继到外部，所有流量伪装为正常 HTTPS 网站访问。

## 架构

```
A (Claude Code 客户端)      B (claude-code-proxy)           C (公司内网)
     │                          │                           │
     │ HTTPS 请求               │     WSS 出站连接          │
     │ /anthropic/v1/messages ► │ ◄── /ws/notifications     │
     │ (像调普通 API)           │ (像普通 WebSocket 应用)    │
     │                          │                           │
     │ ◄── JSON 响应 ────────── │ ──► 内网 LLM API ──────►  │
```

- **A**：Claude Code 客户端，可以和 B 在同一台机器，也可以在任意网络
- **B**：claude-code-proxy，需要有公网 IP（如家里的电脑），对外是普通 HTTPS 网站
- **C**：隧道客户端，在公司内网，主动出站连接 B

## 快速开始

### 前提条件

- **A**：安装 Claude Code（`npm install -g @anthropic-ai/claude-code`），无需 Python
- **B、C**：Python 3.10+

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

### 第三步：在 A 上配置 Claude Code（Windows 11 / Linux / Mac）

A 不需要安装 contool，只需要 Claude Code。

向服务提供人（B+C 的运营者）获取以下信息：
- **服务地址**：B 的域名或 IP + 端口
- **AUTH_TOKEN**：访问凭证
- **可用模型列表**：如 `ppio/pa/claude-opus-4-6`

将以下内容写入 A 机器的 `~/.claude/settings.json`：

```json
{
  "env": {
    "hasCompletedOnboarding": "true",
    "ANTHROPIC_BASE_URL": "https://B的域名或IP:端口/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "从服务提供人获取的AUTH_TOKEN",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "模型名称（从服务提供人获取）",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "模型名称（从服务提供人获取）",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "模型名称（从服务提供人获取）"
  },
  "skipDangerousModePermissionPrompt": true
}
```

然后直接运行 `claude` 即可。

> **示例**：如果 B 的地址是 `mysite.duckdns.org:8443`，AUTH_TOKEN 是 `sk-xxx`，模型是 `ppio/pa/claude-opus-4-6`：
> ```json
> {
>   "env": {
>     "hasCompletedOnboarding": "true",
>     "ANTHROPIC_BASE_URL": "https://mysite.duckdns.org:8443/anthropic",
>     "ANTHROPIC_AUTH_TOKEN": "sk-xxx",
>     "ANTHROPIC_DEFAULT_OPUS_MODEL": "ppio/pa/claude-opus-4-6",
>     "ANTHROPIC_DEFAULT_SONNET_MODEL": "ppio/pa/claude-opus-4-6",
>     "ANTHROPIC_DEFAULT_HAIKU_MODEL": "ppio/pa/claude-opus-4-6"
>   },
>   "skipDangerousModePermissionPrompt": true
> }
> ```

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

启动顺序：**B → C**，A 无需启动服务，直接用 Claude Code。

```bash
# B 上：
cd ~/contool && source venv/bin/activate
nohup python relay_server.py > relay.log 2>&1 &
# 用 nohup 后台运行，SSH 断开不会中断服务
# 查看日志：tail -f relay.log
# 停止：kill $(pgrep -f relay_server.py)

# C 上：
cd ~/contool && source venv/bin/activate
nohup python _server.py > server.log 2>&1 &

# A 上：直接运行 claude（已在第三步配置好 settings.json）
claude
```

> **提示**：如果有 `tmux` 或 `screen`，也可以用它们代替 `nohup` 管理 B/C 的长期进程。

> **自签名证书注意**：未运行 `setup_tls.sh` 时，Claude Code（Node.js）需额外设置：
> 在 `settings.json` 的 `env` 中加入 `"NODE_TLS_REJECT_UNAUTHORIZED": "0"`。
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
| INTERNAL_LLM_KEY | C 内网 LLM API Key | sk-xxx（无需认证则留空） |
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
| `setup.py` | B/C 全自动配置向导 |
| `relay_server.py` | B：claude-code-proxy 服务 |
| `_server.py` | C：隧道服务进程 |
| `config.py` | 配置加载（自动读 .env） |
| `gen_cert.py` | 自签名 TLS 证书生成器 |
| `setup_tls.sh` | B：DuckDNS + Let's Encrypt 一键配置 |
| `static/index.html` | 伪装网站首页 |

## 伪装策略

- B 对外仅一个 HTTPS 端口（如 8443），未认证访问返回正常博客网站
- C→B 的 WebSocket 连接与普通 Web 应用无异
- 所有流量标准 TLS 加密，无特殊协议指纹
- 心跳间隔随机化，定期重连避免长连接特征
- API 路径支持 Anthropic (`/anthropic/*`) 和 OpenAI (`/v1/*`) 标准格式
