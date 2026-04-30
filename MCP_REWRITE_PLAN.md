# Banking Assistant → Истински MCP Server
## Детален план за пълен rewrite

**Дата:** 2026-04-27  
**Автори:** Dimitar Boychev + Claude (Anthropic) + Codex (OpenAI)  
**Статус:** В прогрес — последна актуализация 2026-04-27

### Обобщен прогрес

| Фаза | Описание | Прогрес |
|---|---|---|
| 0 | Инфраструктура | **70%** |
| 1 | Adapter layer | **65%** |
| 2 | Oracle session/conversation store | **0%** *(отложено)* |
| 3 | Core tools | **0%** |
| 4 | Resources + Prompts | **0%** |
| 5 | Analytics tool | **0%** |
| 6 | Транспорт + Claude Desktop config | **15%** |
| 7 | Auth + Security | **15%** |
| 8 | Тестове + hardening | **0%** |

---

## 1. Контекст и цел

Текущият проект (`ai-banking-assistant`) е custom REST API върху FastAPI, 
което ползва "MCP" само като вътрешно наименование. Не следва Anthropic MCP протокола.

**Целта на rewrite-а:**
- Истински MCP server, съвместим с Claude Desktop, Cline, Cursor и всеки MCP host
- JSON-RPC 2.0 транспорт (stdio за Claude Desktop, SSE/streamable HTTP за web клиенти)
- Oracle DB за персистентност — сесии, conversation history, user preferences, audit log
- Запазване на бизнес логиката (banking adapter, canonical models, analytics, normalization)
- Отпадане на: FastAPI REST layer, custom chat endpoint, Vue frontend (или отделен проект)

---

## 2. Какво е истинският MCP (за двата агента)

### 2.1 Протокол

MCP (Model Context Protocol) е JSON-RPC 2.0 протокол за комуникация между:
- **MCP Host** (Claude Desktop, Cline, Cursor) — управлява разговора с LLM
- **MCP Server** (нашият код) — предоставя Tools, Resources, Prompts

```
Claude Desktop (Host)
    ↕ JSON-RPC 2.0 over stdio / SSE
MCP Server (наш)
    ↕ HTTP / Oracle DB
eBank Provider + Oracle DB
```

### 2.2 Основни MCP примитиви

| Примитив | Описание | Използваме ли? |
|---|---|---|
| **Tools** | Функции, които LLM може да извика | Да — всичките banking tools |
| **Resources** | Файлове/данни, достъпни за LLM | Да — account summaries, statements |
| **Prompts** | Reusable prompt шаблони | Опционално — help/concierge |
| **Sampling** | Server иска LLM completion | Не (засега) |

### 2.3 Tool call flow (JSON-RPC)

```json
// Host → Server: tool call
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_accounts",
    "arguments": {}
  }
}

// Server → Host: tool result
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      { "type": "text", "text": "Намерени 3 сметки: ..." }
    ],
    "isError": false
  }
}
```

### 2.4 Транспорти

| Транспорт | Кога | Конфигурация |
|---|---|---|
| **stdio** | Claude Desktop (локално) | `command: python mcp_main.py` в claude_desktop_config.json |
| **SSE** | Web клиенти, Cline в browser | HTTP GET `/sse` + POST `/messages` |
| **Streamable HTTP** | Новият универсален транспорт (MCP 2025-11-05) | POST `/mcp` с Content-Type: text/event-stream |

---

## 3. Архитектура на новия сървър

```
banking_mcp/
├── server.py                  # MCP server entry point (stdio + SSE)
├── transport/
│   ├── stdio.py               # Claude Desktop транспорт
│   └── sse.py                 # Web/browser транспорт (aiohttp или starlette)
├── tools/
│   ├── registry.py            # MCP tool registration
│   ├── accounts.py            # list_accounts, get_balance
│   ├── transactions.py        # list_transactions (с филтри)
│   ├── statement.py           # get_statement
│   ├── fx.py                  # get_fx_rates
│   ├── public_info.py         # get_bank_public_info
│   └── exports.py             # export_result (PDF/CSV/XML)
├── resources/
│   ├── registry.py            # MCP resource registration
│   ├── account_summary.py     # Resource: account://{id}/summary
│   └── statement_resource.py  # Resource: statement://{id}/{period}
├── prompts/
│   └── banking_help.py        # Prompt: banking_help
├── adapters/
│   ├── ebank_http.py          # ЗАПАЗВА СЕ (минимални промени)
│   └── bnb_fx.py              # ЗАПАЗВА СЕ
├── canonical/
│   ├── models.py              # ЗАПАЗВА СЕ
│   ├── mapping.py             # ЗАПАЗВА СЕ
│   └── normalize.py           # ЗАПАЗВА СЕ
├── analytics/
│   └── core.py                # ЗАПАЗВА СЕ
├── db/
│   ├── connection.py          # Oracle DB connection pool (python-oracledb)
│   ├── session_store.py       # Conversation sessions в Oracle
│   ├── conversation_store.py  # Message history в Oracle
│   ├── audit_log.py           # Tool call audit log
│   └── migrations/
│       ├── 001_sessions.sql
│       ├── 002_conversations.sql
│       ├── 003_tool_audit.sql
│       └── 004_user_preferences.sql
├── auth/
│   ├── jwt.py                 # ЗАПАЗВА СЕ (JWT decode)
│   └── provider_auth.py       # eBank session извличане от MCP context
├── normalization/             # ЗАПАЗВА СЕ изцяло
├── knowledge/                 # ЗАПАЗВА СЕ изцяло
├── policy/                    # ЗАПАЗВА СЕ изцяло
├── config.py                  # Pydantic settings (опростени — без FastAPI)
├── requirements.txt           # mcp, python-oracledb, httpx, pydantic-settings...
└── tests/
    ├── unit/
    └── mcp_protocol/          # JSON-RPC contract тестове
```

---

## 4. Oracle DB схема

### 4.1 Таблици

```sql
-- 001_sessions.sql
CREATE TABLE mcp_sessions (
    id           VARCHAR2(128)  PRIMARY KEY,   -- user_id:session_id
    user_id      VARCHAR2(256)  NOT NULL,
    created_at   TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at   TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    ttl_expires  TIMESTAMP      NOT NULL,
    state_json   CLOB,                          -- SessionState като JSON
    CONSTRAINT mcp_sessions_chk CHECK (state_json IS JSON)
);

CREATE INDEX idx_mcp_sessions_user ON mcp_sessions(user_id);
CREATE INDEX idx_mcp_sessions_ttl  ON mcp_sessions(ttl_expires);

-- 002_conversations.sql
CREATE TABLE mcp_conversations (
    id           NUMBER         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id   VARCHAR2(128)  NOT NULL REFERENCES mcp_sessions(id) ON DELETE CASCADE,
    role         VARCHAR2(16)   NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content      CLOB           NOT NULL,
    created_at   TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_mcp_conv_session ON mcp_conversations(session_id, created_at);

-- 003_tool_audit.sql
CREATE TABLE mcp_tool_audit (
    id            NUMBER         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id    VARCHAR2(128),
    user_id       VARCHAR2(256),
    tool_name     VARCHAR2(128)  NOT NULL,
    args_json     CLOB,
    result_status VARCHAR2(16)   NOT NULL CHECK (result_status IN ('ok', 'error', 'blocked')),
    duration_ms   NUMBER,
    error_detail  VARCHAR2(2000),
    called_at     TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT mcp_tool_audit_args_chk CHECK (args_json IS JSON)
);

CREATE INDEX idx_mcp_audit_user     ON mcp_tool_audit(user_id, called_at);
CREATE INDEX idx_mcp_audit_tool     ON mcp_tool_audit(tool_name, called_at);

-- 004_user_preferences.sql
CREATE TABLE mcp_user_preferences (
    user_id          VARCHAR2(256)  PRIMARY KEY,
    preferred_lang   VARCHAR2(8)    DEFAULT 'en',
    default_account  VARCHAR2(128),
    prefs_json       CLOB,
    updated_at       TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT mcp_prefs_chk CHECK (prefs_json IS JSON)
);
```

### 4.2 Connection pool (python-oracledb)

```python
# db/connection.py
import oracledb

pool: oracledb.AsyncConnectionPool | None = None

async def init_pool():
    global pool
    pool = oracledb.create_pool_async(
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
        dsn=settings.ORACLE_DSN,          # "host:port/service_name"
        min=2,
        max=10,
        increment=1,
    )
```

### 4.3 Нови env variables

```bash
# Oracle
ORACLE_USER=mcp_user
ORACLE_PASSWORD=
ORACLE_DSN=localhost:1521/XEPDB1       # или TNS alias
ORACLE_POOL_MIN=2
ORACLE_POOL_MAX=10
MCP_SESSION_TTL_S=1800
MCP_CONVERSATION_MAX_MESSAGES=20
```

---

## 5. MCP Tools дефиниция

### 5.1 Пълен списък

| Tool name | Описание | Args |
|---|---|---|
| `list_accounts` | Списък сметки с балансите | — |
| `get_balance` | Баланс на конкретна сметка | `account_id` |
| `list_transactions` | Транзакции с филтри | `account_id`, `from_date`, `to_date`, `category`, `min_amount`, `max_amount`, `merchant` |
| `get_statement` | Извлечение по период | `account_id`, `from_date`, `to_date` |
| `get_fx_rates` | Валутни курсове (BNB) | `currencies[]` (optional) |
| `get_bank_public_info` | Публична банкова информация | `query` |
| `analyze_spending` | Анализ на разходи по категории | `account_id`, `from_date`, `to_date` |
| `export_result` | Експортиране на последен резултат | `format` (pdf/csv/xml), `profile` (accountant/manager) |

### 5.2 Пример — list_transactions

```python
@mcp.tool()
async def list_transactions(
    account_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    merchant: str | None = None,
) -> list[dict]:
    """
    List account transactions with optional filters.
    
    Use from_date/to_date as YYYY-MM-DD strings.
    category is one of: food, fuel, utilities, shopping, transport, other.
    """
    ...
```

### 5.3 Resources

```python
@mcp.resource("account://{account_id}/summary")
async def account_summary(account_id: str) -> str:
    """Current balance and recent activity for an account."""
    ...

@mcp.resource("statement://{account_id}/{year}/{month}")
async def monthly_statement(account_id: str, year: str, month: str) -> str:
    """Full statement for a given month."""
    ...
```

---

## 6. Какво се ЗАПАЗВА (reuse)

| Компонент | Файл(ове) | Промени |
|---|---|---|
| eBank HTTP adapter | `adapters/ebank_http.py` | Минимални — маха се FastAPI зависимости |
| BNB FX adapter | `adapters/bnb_fx.py` | Без промяна |
| Canonical models | `canonical/models.py` | Без промяна |
| Canonical mapping | `canonical/mapping.py` | Без промяна |
| Canonical normalize | `canonical/normalize.py` | Без промяна |
| Analytics core | `ai/analytics/core.py` | Без промяна |
| Normalization | `ai/normalization/` | Без промяна |
| Knowledge base | `ai/knowledge/` | Без промяна |
| Policy / guardrails | `ai/policy/` | Без промяна |
| JWT decode | `core/security.py` | Адаптира се за MCP context |
| Circuit breaker | `core/circuit_breaker.py` | Без промяна |
| Intent extractors | `ai/intents/` | Опционално — ако ползваме Sampling |
| Config (Pydantic) | `core/config.py` | Разширява се с Oracle vars |

---

## 7. Какво ОТПАДА

| Компонент | Защо |
|---|---|
| `mcp_server/main.py` (FastAPI app) | Заменя се от MCP server entry point |
| `mcp_server/ai/agent/core.py` (BankingAgent) | LLM reasoning се поема от Host (Claude Desktop) |
| `mcp_server/ai/router/` | Маршрутизацията се поема от Host |
| `mcp_server/ai/llm/` | LLM calls се поемат от Host |
| `mcp_server/ai/agent/followups.py` | Follow-up context се управлява от Host |
| `mcp_server/ai/agent/response_profiles.py` | Форматирането се поема от Host |
| Vue frontend (`frontend/`) | Заменя се от Claude Desktop / Cline UI |
| Redis session backend | Заменя се от Oracle |
| In-memory session store | Заменя се от Oracle |

**Забележка за frontend-а:** Ако искаш да запазиш web UI — трябва отделен проект, 
който консумира MCP чрез SSE транспорт. Не е част от MCP server-а.

---

## 8. Фази на имплементация

### Фаза 0 — Инфраструктура — 70% ✅
**Отговорник: Claude**

- [x] Нова директория `banking_mcp/` + `__init__.py` за всички под-пакети
- [x] `requirements.txt` — mcp, httpx, pydantic-settings, PyJWT, python-oracledb
- [x] `config.py` с Oracle + eBank settings (от стария `core/config.py`, без FastAPI/STT/LLM/Redis)
- [ ] `db/connection.py` — Oracle async pool *(отложено — без база засега)*
- [ ] `db/migrations/*.sql` — 4-те таблици *(отложено — без база засега)*
- [x] `server.py` — FastMCP server, stdio/sse транспорт, `health://status` resource
- [ ] Unit тест: сървърът стартира и отговаря на `tools/list`

### Фаза 1 — Adapter layer — 65% 🔄
**Отговорник: Codex / Claude**

- [x] Копиране и адаптиране на `adapters/ebank_http.py`
- [x] Копиране на `adapters/bnb_fx.py`
- [x] Копиране на `adapters/provider_adapter.py`
- [x] Копиране на `adapters/provider_registry.py` (import paths обновени)
- [x] Копиране на `canonical/` изцяло (models, mapping, normalize)
- [x] Копиране на `normalization/` (entity_normalizer, merchant_normalization)
- [x] Копиране на `knowledge/` изцяло (включително semantic_synonyms)
- [x] Копиране на `policy/` (guardrails, policies)
- [x] `auth/jwt.py` — JWT decode без FastAPI (TokenError вместо HTTPException)
- [ ] `auth/provider_auth.py` — извличане на eBank session от MCP tool context
- [ ] Unit тестове за adapter-ите с mock HTTP

### Фаза 2 — Oracle session/conversation store — 0% ⏸️
**Отговорник: Claude** *(отложено — изчаква Oracle instance)*

- [ ] `db/connection.py` — Oracle async pool
- [ ] `db/session_store.py` — CRUD за `mcp_sessions` + JSON state
- [ ] `db/conversation_store.py` — append/get/clear за `mcp_conversations`
- [ ] `db/audit_log.py` — запис след всеки tool call
- [ ] TTL cleanup job (Oracle scheduled job или Python background task)
- [ ] Unit тестове с Oracle test instance

### Фаза 3 — Core tools — 0% ⏳
**Отговорник: Claude + Codex паралелно**

Claude:
- [ ] `tools/accounts.py` — `list_accounts`, `get_balance`
- [ ] `tools/statement.py` — `get_statement`
- [ ] `tools/exports.py` — `export_result`

Codex:
- [ ] `tools/transactions.py` — `list_transactions` с всички филтри
- [ ] `tools/fx.py` — `get_fx_rates`
- [ ] `tools/public_info.py` — `get_bank_public_info`

### Фаза 4 — Resources + Prompts — 0% ⏳
**Отговорник: Claude**

- [ ] `resources/account_summary.py`
- [ ] `resources/statement_resource.py`
- [ ] `prompts/banking_help.py`
- [ ] Регистрация в `server.py`

### Фаза 5 — Analytics tool — 0% ⏳
**Отговорник: Codex**

- [ ] Копиране на `ai/analytics/core.py` → `analytics/core.py`
- [ ] `tools/analysis.py` — `analyze_spending`
- [ ] Интеграция с Oracle (persist на последния анализ в session state)

### Фаза 6 — Транспорт + Claude Desktop config — 15% 🔄
**Отговорник: Claude**

- [x] Транспорт вграден в `server.py` (FastMCP.run stdio/sse)
- [ ] `transport/stdio.py` — изричен stdio wrapper ако е нужен
- [ ] `transport/sse.py` — SSE транспорт за web клиенти
- [ ] `claude_desktop_config.json` пример
- [ ] End-to-end тест: Claude Desktop → `list_accounts` → реален eBank отговор

### Фаза 7 — Auth + Security — 15% 🔄
**Отговорник: Claude**

- [x] `auth/jwt.py` — JWT decode (TokenError, без FastAPI)
- [ ] `auth/provider_auth.py` — eBank session от MCP tool context
- [ ] Tool-level authorization (кои tools изискват provider auth)
- [ ] Circuit breaker интеграция в tools
- [ ] Policy guardrails (mutation protection) в tools

### Фаза 8 — Тестове + hardening — 0% ⏳
**Отговорник: Claude + Codex паралелно**

- [ ] MCP protocol contract тестове (JSON-RPC format, tool schemas)
- [ ] Oracle integration тестове
- [ ] Adapter тестове с реален eBank (или mock)
- [ ] Error handling coverage

---

## 9. Claude Desktop конфигурация (крайна цел)

```json
{
  "mcpServers": {
    "banking-assistant": {
      "command": "python",
      "args": ["-m", "banking_mcp.server"],
      "env": {
        "EBANK_BASE_URL": "http://172.16.51.90:8080/EBank",
        "ORACLE_DSN": "localhost:1521/XEPDB1",
        "ORACLE_USER": "mcp_user",
        "ORACLE_PASSWORD": "...",
        "JWT_SECRET_KEY": "..."
      }
    }
  }
}
```

След тази конфигурация — Claude Desktop вижда инструментите и може директно да задава:
> "Покажи ми сметките ми" → `list_accounts` → реален eBank отговор

---

## 10. Разпределение на работата (Claude vs Codex)

### Claude прави:
- MCP server infrastructure (server.py, транспорти)
- Oracle DB layer (connection pool, migrations, session/conversation stores)
- Auth/security layer
- `list_accounts`, `get_balance`, `get_statement`, `export_result` tools
- Resources и Prompts
- MCP protocol тестове

### Codex прави:
- Adapter layer migration (ebank_http.py, bnb_fx.py)
- `list_transactions` tool (с всички филтри)
- `get_fx_rates`, `get_bank_public_info` tools
- `analyze_spending` tool (от analytics/core.py)
- Unit тестове за adapter-ите

### Синхронизация:
- Shared interface: `auth/provider_auth.py` (Claude дефинира → Codex ползва)
- Shared interface: `db/session_store.py` (Claude дефинира → двамата ползват)
- Shared interface: canonical models (запазват се без промяна)
- **Всеки PR минава и през двамата агента преди merge**

---

## 11. Зависимости (requirements.txt)

```txt
# MCP
mcp>=1.0.0

# Oracle
python-oracledb>=2.0.0

# HTTP / Async
httpx==0.27.0
aiohttp>=3.9.0            # за SSE транспорт

# Config / Validation
pydantic-settings>=2.0.0
pydantic>=2.0.0

# Auth
PyJWT==2.9.0
itsdangerous>=2.1.0

# STT (опционално)
faster-whisper

# Dev
pytest
pytest-asyncio
```

---

## 12. Отворени въпроси за решение

| # | Въпрос | Опции | Приоритет |
|---|---|---|---|
| 1 | Искаш ли да запазиш Vue frontend като отделен проект? | Да / Не / По-късно | Висок |
| 2 | Oracle instance — local Docker / remote? DSN? | Нужни credentials | Блокиращ за Фаза 2 |
| 3 | MCP транспорт по подразбиране — само stdio или и SSE? | Двата / Само stdio | Среден |
| 4 | `analyze_spending` — пренасяме analytics логиката или я маваме? | Пренасяме / Опростяваме | Среден |
| 5 | Export tool — генерира файл и го връща като binary content в MCP? | Да (base64) / URI | Среден |
| 6 | Audit log в Oracle — колко дълго да се пазят записите? | 30 дни / 90 дни | Нисък |

---

## 13. Рискове

| Риск | Вероятност | Смекчаване |
|---|---|---|
| Oracle async pool — python-oracledb v2 thin mode | Среден | Тест с реална Oracle instance в Фаза 0 |
| MCP auth — Host не подава provider credentials | Висок | Изрична документация в tool descriptions |
| Claude Desktop не поддържа SSE (само stdio) | Нисък | Stdio е приоритет; SSE е бонус |
| eBank adapter — httpx async в MCP context | Нисък | Adapter вече е async, само се копира |
| Analytics без LLM (Host поема LLM) | Среден | Analytics tool се изпълнява rule-based, без LLM |

---

## 14. Следваща стъпка

**Преди да започнем Фаза 0, отговори на:**
1. Oracle DSN / credentials (или Docker compose за local Oracle XE)
2. Искаш ли да запазиш Vue frontend?
3. Новият проект — в същото repo (subfolder) или ново repo?

След отговорите стартираме Фаза 0 незабавно.