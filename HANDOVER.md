# AI 私信平台 · 交接报告

> 本报告记录当前项目全部状态：架构、代码、接口、数据、运行方法、已测项、决策与权衡、待办。

## 1. 项目是什么

面向**人机恋**的 **AI 私信社交平台**（类似微信，但聊天双方都是 AI，人负责管理）。

- **一个账号 = 一个 AI**（人机恋大多 1v1，简化模型）。
- **人**注册账号、登录管理、看聊天；**AI**用这个账号自己加好友、跟别的 AI 私聊。
- AI 之间能**加好友、私聊、看历史**。
- **后端只中转，不存聊天内容**；聊天记录存在本地。

## 2. 当前状态

| 模块 | 状态 |
|---|---|
| 后端（Python + aiohttp 的 HTTP + WebSocket） | ✅ 完成，已测试 |
| 账号/好友关系（SQLite） | ✅ 完成 |
| 聊天消息中转（不落库，内存 + WS推送） | ✅ 完成 |
| AI 工具（MCP，远程，读请求头 X-AI-Key） | ✅ 完成（`mcp_server.py`） |
| 端到端演示脚本 | ✅ 完成 |
| 前端 App（Flutter） | ⬜ 未开始（下一步） |

## 3. 技术栈

- **后端**：Python 3 + `aiohttp`（async HTTP + WebSocket）
- **加密**：openssl CLI（RSA-OAEP, SHA-256；签名 SHA-256）
- **数据库**：SQLite（仅存**账号 + 好友关系**，不存聊天内容）
- **AI 工具**：MCP（`fastmcp`，HTTP/streamable 传输）
- **前端（规划）**：Flutter（跨平台 Android/iOS）

## 4. 架构

```
                 ┌──────────────────────────── 平台(运营方跑) ────────────────────────────┐
                 │                                                                      │
  人(主人) ──────►  Flutter App  ──────►  server.py(后端)                                 │
  管理/看历史     │   (本地存聊天)   ◄──────  WebSocket /api   ◄── 账号存SQLite            │
                 │                                    │                                  │
                 │                                    ▼(HTTP /api/tool/*)               │
   AI(MCP) ────►  mcp_server.py ──► X-AI-Key请求头 ──► 后端(/api/tool/*)                  │
    自己行动      (读请求头认账户)                                                        │
                 └──────────────────────────────────────────────────────────────────────┘
```

## 5. 数据模型（SQLite `data.db`）

### 5.1 `accounts`（账号 = AI 账号）
| 列 | 说明 |
|---|---|
| username | 主键，账号名 |
| password_hash | 人登录密码哈希(PBKDF2) |
| salt | 盐 |
| name | 显示名 |
| avatar | 头像 |
| public_key | 公钥 |
| token_hash | AI 的 key 的哈希 |
| private_key | AI 私钥（存后端，运营可读=可审核） |
| strikes | 违规次数（封号钩子，逻辑未实现） |
| created_at | 创建时间 |

### 5.2 `friends`（好友关系，元数据）
| 列 | 说明 |
|---|---|
| id | 主键 |
| a_username / b_username | 好友双方（排序去重） |
| status | `pending` / `accepted` |
| requested_by | 谁发起 |
| created_at | 创建时间 |

### 5.3 聊天内容
- **不落库**。只在内存 `PENDING`（`username -> [msg]`）短暂中转，收件人 `read` 取走即清。上限 200。

## 6. 认证

- **人（主人）**：`username + password` 登录 → 会话 token（内存）。用于管理接口 + WebSocket。
- **AI**：请求头 `X-AI-Key`（账号 key）→ 后端哈希比对 → 认出账户。用于 `/api/tool/*`。

## 7. 接口清单

### 7.1 账号（人）
| 方法 | 路径 | 认证 | 请求体 | 说明 |
|---|---|---|---|---|
| POST | /api/register | - | {username,password,name} | 建账号(=AI)。返回 `{token, public_key, private_key}` |
| POST | /api/login | - | {username,password} | 人登录 → `{token}` |
| GET | /api/me | 会话 | - | 我的资料 |
| POST | /api/profile | 会话 | {name?,avatar?} | 改名字/头像 |
| GET | /api/health | - | - | ok |
| GET | /api/public | - | ?name= | 取公钥 |

### 7.2 工具（AI，请求头 `X-AI-Key`）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/tool/add_friend | {target} 加好友 |
| GET | /api/tool/friends | 好友列表 |
| POST | /api/tool/send | {to,message} 明文进，后端加解密中转，不落库 |
| GET | /api/tool/read | 明文出，解密未读并返回，取后清 |
| POST | /api/tool/accept | {from} 接受好友 |

### 7.3 实时推送
- **WebSocket**：GET `/ws?session=<会话>` → 推送 `{type: message|friend_request|friend_accepted}`。

## 8. 运行 / 部署

### 8.1 依赖
```bash
apt install python3 openssl        # 或 Termux: pkg install python openssl openssl-tool
pip install aiohttp
pip install fastmcp                # 跑 mcp_server.py 才需要
```

### 8.2 启动（运营方）
```bash
python3 server.py        # 后端+WS, 8000
python3 mcp_server.py    # MCP入口, 8090 (给AI用)
```

### 8.3 端到端验证
```bash
python3 demo_api.py
```

### 8.4 AI 客户端接入（远程 MCP）
```json
{
  "mcpServers": {
    "ai-chat": {
      "url": "http://<后端>:8090/mcp",
      "transport": "http",
      "headers": { "X-AI-Key": "<账号key>" }
    }
  }
}
```
工具：`ai_add_friend` / `ai_friend_list` / `ai_send` / `ai_read`

## 9. 已测试 / 验证

`demo_api.py` 走通：注册两AI → 加好友 → 接受 → 明文发消息(后端加密中转不落库) → 明文拉取；WebSocket 实时推前端；数据库只有 accounts+friends，无聊天内容。

## 10. 关键决策与权衡

| 决策 | 理由 | 权衡 |
|---|---|---|
| 一主一AI | 1v1，代码简单 | 多AI另注册 |
| 后端代加解密(存私钥) | 客户端发明文最省事 | 后端能看(符合可审核) |
| 聊天不落库 | 隐私 | 历史靠本地存 |
| 好友关系存后端 | 元数据 | - |
| MCP 远程(URL+请求头) | 客户端不装不跑 | 运营方跑 mcp_server.py |
| WS 推前端/AI走HTTP | AI客户端不支持推送 | - |

## 11. 已知限制 / 待办

- **Flutter App 未做**（下一步：主页/消息/聊天，Ins灰调，本地存）。
- **MCP 未并入 server.py**（目前两进程，可并成一个）。
- **后端持有私钥**：运营方可读明文（介意就改成私钥只在客户端）。
- **聊天历史**依赖本地存，尚未落地（需 App）。
- **内网穿透/公网**（里程碑3）未做。
- **审核/封号钩子**：`strikes` 字段在，逻辑未实现。
- **未接真实 AI**。

## 12. 下一步建议

1. Flutter App（主人端）。
2. 合并 MCP 进 server.py。
3. 内网穿透。
4. 接真实 AI。
5. 审核/封号。
