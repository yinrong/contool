# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 三角色架构

contool 是一个伪装为普通 HTTPS 网站的 LLM API 中继。流量路径：

```
A (Claude Code 客户端) ──HTTPS──► B (公网 proxy) ◄──WSS 出站──── C (C 网络)
                                                                  │
                                                                  └──► LLM API
```

理解架构的关键：**C 主动出站连接 B，不是 B 连 C**。这样 C 处于不允许入站的网络（如严格防火墙）也能工作。所有运行时通信通过这一条 WebSocket 隧道复用。A、B、C 三方部署在不同机器上，从代码 review 到改动设计都要时刻意识到这一点。

- `relay_server.py` — B 的服务，aiohttp。处理 A 的 HTTP 请求 + 维护 C 的 WebSocket。**B 是透明代理**，不验证 API Key（A 的 API Key 是 LLM 服务方给的，B 没资格验证）。WS 路径 `/ws/notifications` 伪装为通知端点。
- `_server.py` — C 的隧道客户端，aiohttp。连到 B 后接收 `request` 消息，转发给 `INTERNAL_LLM_BASE`，结果按 `response` / `stream_chunk` / `stream_end` 三种消息类型回送。
- `static/index.html` — 伪装首页。`/` 和任何未知路径（catch-all）都返回这个，让访问者以为是普通网站。

## WebSocket 消息协议（B ↔ C）

所有消息为 JSON TEXT 帧。改动这里要谨慎，A→B→C→LLM 全链路任一处不一致就会断。

| 方向 | type | 关键字段 |
|------|------|---------|
| B→C | `request` | `id`, `method`, `path`（A 请求的原始路径，不重写）, `headers`, `body` |
| C→B | `response` | `id`, `status`, `headers`, `body`（dict/list → JSON, 否则 text） |
| C→B | `stream_chunk` | `id`, `data`（一行 SSE） |
| C→B | `stream_end` | `id` |
| C→B | `ping` | `padding`（16-128 随机字符，伪装流量指纹） |

**Header 白名单**：B 转发到 C 的 header 只有 `authorization`, `x-api-key`, `content-type`, `anthropic-version`, `anthropic-beta`（`relay_server.py:120-123`）。改动时要同步 `tests/test_e2e.py::test_header_allowlist`。

**WS 认证**：通过 `Cookie: _sid=<TUNNEL_SECRET>` 校验，错了返回 404 而非 401（伪装）。

## 配置加载

`config.py` 顶部自带 `.env` 解析器，无第三方依赖。所有配置走环境变量，B 和 C 各自有自己的 `.env`。

`setup.py` 是**配置向导**（不是 setuptools 脚本），生成 `.env` 和邀请码。B 生成的"C 邀请码"是 base64(`{addr, port, tunnel_secret}`)，C 粘贴后自动配好。A 完全不用 contool，只需按 README 配 Claude Code 的环境变量和 `~/.claude/settings.json`。

## 运行命令

| 任务 | 命令 |
|------|------|
| 启动 B | `python relay_server.py` |
| 启动 C | `python _server.py` |
| 配置 B/C | `python setup.py` |
| 端到端测试 | `python -m pytest tests/ -v` |
| 单个测试 | `python -m pytest tests/test_e2e.py::test_non_stream -v` |
| 旧 shell 测试 | `bash test_local.sh` |

测试默认串行，`asyncio_default_fixture_loop_scope=session`，`session`-scope 的 fixtures 共享 relay/mock_llm 实例，加速到 ~2s 跑完 10 个测试。

## 测试约束（重要）

**禁止 mock 测试。** `tests/conftest.py` 中 mock_llm 是真实的 aiohttp HTTP 服务（不是 mock 对象），B 和 C 也是进程内启动的真实组件，全链路走真实 TLS+WS+HTTP。新增测试不要引入 `unittest.mock` 或 `pytest-mock`。

`config.REQUEST_TIMEOUT` 是硬编码常量（不读环境变量），测试里不要尝试通过 env 覆盖，要直接 `config.REQUEST_TIMEOUT = N` 赋值。

## TLS 与证书

B 默认用自签名证书（`gen_cert.py` 生成）。Claude Code 默认拒绝自签名证书，需要 A 设置 `NODE_TLS_REJECT_UNAUTHORIZED=0`。生产环境跑 `setup_tls.sh` 申请 Let's Encrypt 正式证书。

`certs/` 在 `.gitignore` 中，不要提交证书和密钥。

## 部署细节

- 端口默认 8443（运营商常封 80/443）
- C 用 `RELAY_TLS=true` 强制 wss（`auto` 模式根据 C 自己的 cert 文件判断，C 通常没有 cert 所以会错）
- B 重启时 `nohup python relay_server.py > relay.log 2>&1 &`
- B 维护单一 tunnel：第二个 C 连进来会顶掉前一个（`relay_server.py:50-53`）
