# contool - 隐蔽 LLM API 中继（claude-code-proxy）

通过中间节点，将公司内网的大模型 API 安全中继到外部，所有流量伪装为正常 HTTPS 网站访问。

## 架构

```
A (Claude Code 客户端)      B (claude-code-proxy)           C (公司内网)
     │                          │                           │
     │ HTTPS 请求               │     WSS 出站连接          │
     │ /anthropic/v1/messages ► │ ◄── /ws/notifications     │
     │                          │                           │
     │ ◄── JSON 响应 ────────── │ ──► 内网 LLM API ──────►  │
```

- **A**：Claude Code 客户端，可以和 B 在同一台机器，也可以在任意网络
- **B**：claude-code-proxy，需要有公网 IP（如家里的电脑），对外是普通 HTTPS 网站
- **C**：隧道客户端，在公司内网，主动出站连接 B

## 配置步骤

### 前提条件

- **A**：安装 Claude Code（`npm install -g @anthropic-ai/claude-code`），无需 Python
- **B、C**：Python 3.10+
- **B**：需要一个指向 B 公网 IP 的域名（用于 TLS 证书申请）
- **B 在路由器/NAT 后面**：在路由器设置端口转发，外部 8443 → B 内网 IP:8443

> 国内运营商封锁 80/443，使用 **8443**。

### 第一步：配置 B

```bash
git clone git@github.com:yinrong/contool.git
cd contool
python -m venv venv
source venv/bin/activate
pip install aiohttp cryptography
python setup.py          # 选择 B，输入域名和端口
bash setup_tls.sh        # 输入 DuckDNS 子域名、token、邮箱，自动申请正式证书
```

完成后会打印两个邀请码和 AUTH_TOKEN，分别发给 A 和 C。

> 证书有效期 90 天，续期重新运行 `bash setup_tls.sh`。

### 第二步：配置 C

```bash
git clone git@github.com:yinrong/contool.git
cd contool
python -m venv venv
source venv/bin/activate
pip install aiohttp cryptography
python setup.py          # 选择 C，粘贴邀请码，输入内网 LLM 地址和 API Key
```

### 第三步：配置 A（Claude Code）

A 不需要安装 contool。向服务提供人（B+C 运营者）获取服务地址、AUTH_TOKEN 和可用模型名称。

将以下内容写入 `~/.claude/settings.json`：

```json
{
  "env": {
    "hasCompletedOnboarding": "true",
    "ANTHROPIC_BASE_URL": "https://mysite.duckdns.org:8443/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "从服务提供人获取的AUTH_TOKEN",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "ppio/pa/claude-opus-4-6",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "ppio/pa/claude-opus-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "ppio/pa/claude-opus-4-6"
  },
  "skipDangerousModePermissionPrompt": true
}
```

运行 `claude` 即可。

## 启动服务

启动顺序：**B → C**，A 直接运行 `claude`。

```bash
# B：
cd ~/contool && source venv/bin/activate
nohup python relay_server.py > relay.log 2>&1 &

# C：
cd ~/contool && source venv/bin/activate
nohup python _server.py > server.log 2>&1 &
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `setup.py` | B/C 配置向导 |
| `relay_server.py` | B：claude-code-proxy |
| `_server.py` | C：隧道服务 |
| `config.py` | 配置加载 |
| `setup_tls.sh` | B：DuckDNS + Let's Encrypt 一键配置 |
| `gen_cert.py` | 自签名证书生成（setup.py 内部调用） |
| `static/index.html` | 伪装网站首页 |
