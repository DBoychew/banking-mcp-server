# Интеграция на IRIS Transaction Categories — план по фази

Source: `Transaction Categories Iris Solutions v.1.1.xlsx` (IRIS PSD2Hub стандарт)
Last updated: 2026-05-12

## Какво ще постигнем

Йерархичната класификация (55 входящи + 122 изходящи категории, **само BG локал** — приложението обслужва български клиенти) се превръща в:
1. Runtime ресурс, който LLM-ът може да зарежда.
2. Детерминистичен инструмент за класификация по keyword.
3. Domain query, който закача category code към реални транзакции от Oracle.
4. Готови prompt-и за анализ на разходи по категории.

Всяка фаза има **изрични acceptance criteria**. Следваща фаза започва **САМО** след като предишната е 100% завършена, тествана и committed.

---

## Phase 1 — Foundation ✅ ЗАВЪРШЕНА (2026-05-12)

**Цел:** еднократна конверсия XLSX → структуриран JSON, който останалите фази да консумират.

### Deliverables
- [x] `scripts/convert_transaction_categories.py` — конвертиращ скрипт (idempotent, repeatable).
- [x] `banking_mcp/resources/data/transaction_categories.json` — финален артефакт.
- [x] Плоска структура: `categories[]` с `full_code`, `direction`, hierarchy, `keywords_bg`, `description`.
- [x] `payroll_patterns[]` за специален payroll matching (само BG).
- [x] `locale: "bg_BG"` marker в payload-а — Greek колони/patterns се филтрират при конверсия.

### Acceptance criteria
- [x] Counts отговарят: 55 incoming, 122 outgoing, 5 patterns (BG-only).
- [x] **0 гръцки знака** в финалния JSON (verified чрез regex `[Ͱ-Ͽἀ-῿]`).
- [x] Известно ограничение, документирано: **outgoing категориите нямат keyword колона** — keyword-ите са вградени в `description`. Решава се в Phase 3.
- [x] Скриптът е детерминистичен — повторно изпълнение дава байт-равен резултат.

### Open issues за следващи фази
- `outgoing` keyword извличане от description (Phase 3).
- NBSP normalization в payroll pattern groups — частично адресирано в скрипта, double-check в Phase 2 loader.

---

## Phase 2 — MCP Resource exposure ✅ ЗАВЪРШЕНА (2026-05-12)

**Цел:** Таксономията да се чете през стандартен MCP resource URI, без да я hardcode-ваме в prompt-ите.

### Deliverables
- [x] `banking_mcp/resources/categories_loader.py` — кеширан loader на JSON-а (`functools.lru_cache`).
- [x] Нормализация при load: trim, NBSP → space.
- [x] Нови ресурси в `banking_resources.py`:
  - `banking://transaction-categories` → пълна таксономия (JSON).
  - `banking://transaction-categories/incoming` → само входящи.
  - `banking://transaction-categories/outgoing` → само изходящи.
  - `banking://transaction-categories/payroll-patterns` → payroll patterns.
- [x] Update `PROJECT_FILE_FUNCTION_GUIDE_BG.md` с новите файлове.

### Acceptance criteria
- [x] Pytest: resource връща валиден JSON със същите counts като Phase 1 (`test_transaction_categories_*`).
- [x] Pytest: loader е singleton (`test_load_is_cached`).
- [x] Pytest: 0 Greek codepoints в payload-а (`test_no_greek_anywhere`).
- [x] Пълен test suite зелен: **160/160 PASS**.
- [x] Няма промени в `tools_api.py`, `manager.py` или `db_tools.py` (изолация на промените).

### Out of scope (нарочно)
- Никаква класификационна логика.
- Никакъв DB достъп.

---

## Phase 3 — `classify_description` standalone tool ✅ ЗАВЪРШЕНА (2026-05-12)

**Цел:** Чист keyword-matching инструмент, който приема свободен текст и връща top-K кандидата с code + score. Без DB. Това е инструментът, който решава 80% от случаите детерминистично.

### Deliverables
- [x] Extract keywords from `description` за outgoing категориите (regex `_KEYWORDS_IN_DESC_RE` в конвертора, шаблон *"ключови думи като - X, Y, Z"*). JSON-ът регенериран: 79/122 outgoing категории сега имат keywords; останалите 43 са "999 catch-all".
- [x] `banking_mcp/classification/keyword_index.py`:
  - Reverse index `keyword → [category_record]`, build веднъж в singleton (`@lru_cache`).
  - Case-insensitive + NFC unicode normalization.
  - Substring matching за keywords ≥4 символа, word-boundary regex за по-къси (избягва false hit като "нои" в "нощен").
  - Score = sum(`max(1.0, len(keyword)/5.0)`) — по-дълги/специфични keywords тежат повече.
- [x] `banking_mcp/tools/classification_tools.py` — нов MCP tool `classify_description(text, direction='auto', top_k=3)`. Връща JSON със `matches[]`, `payroll_pattern_hit`, `unclassified`.
- [x] Special-case payroll patterns: компилират се от Phase 1 patterns към regex-ове (`PAYROLL_MM_YYYY` → `\bPAYROLL_\d{2}_\d{4}\b`). При match → boost `+5.0` за code `001001001000` (Възнаграждение).

### Acceptance criteria
- [x] Pytest golden fixture с 17 описания, покриващи incoming income/financing + outgoing food/leisure/home.
- [x] Top-3 contains expected: **17/17 (100%)**.
- [x] Top-1 precision threshold: **≥80%** (assertion enforced в `test_top1_precision_meets_threshold`).
- [x] Tool **никога не халюцинира code** — `test_classifier_never_invents_a_code` обхожда golden + edge cases и проверява срещу `known_codes`.
- [x] Direction filter работи коректно (`test_direction_filter_excludes_other_side`).
- [x] Invalid direction → `ValueError` (а tool surface връща JSON с `error`).
- [x] Payroll boost работи дори без BG keyword (`test_payroll_pattern_boosts_salary_even_without_keyword`).
- [x] Пълен test suite зелен: **192/192 PASS**.

### Известни ограничения (документирани, gating-safe)
- **Merchant-only описания → UNCLASSIFIED.** Таксономията не съдържа имена на търговци (ЛИДЛ, OMV, БИЛЛА, КАУФЛАНД и пр.). Текущо поведение: `unclassified: true` вместо хипотеза. Pin-нато с `test_unclassified_for_truly_random_description` (Phase 3 limitation) и `test_merchant_alias_closes_phase3_gap` (Phase 6 closure). Phase 6 / merchant alias list запълни тази празнина.
- **Typo в source данните** за code 001001006000 (`"обезщетеТие безработица"`). Не блокира Phase 3. Phase 6 data-quality follow-up.
- **Audit log integration** не е реализирано в Phase 3 — отложено за Phase 6 заедно с LLM fallback и stats resource.

### Out of scope (нарочно)
- DB integration — Phase 4.
- LLM fallback за unclassified — Phase 6.
- Merchant alias list — Phase 6.

---

## Phase 4 — `classify_transactions` API ✅ ЗАВЪРШЕНА (2026-05-12)

**Цел:** Обогатява DataFrame от транзакции с category codes от IRIS таксономията. Hybrid дизайн: SQL fetch + Python pass.

### Решение на дизайна
`DatabaseManager.execute_domain_query` е pure-SQL и няма post-process hook. Вместо да го инвазивно разширяваме, добавихме `classify_transactions(df, ...)` като метод на `BankingToolsAPI`. Това:
- Държи domain queries чисти (separation of concerns).
- Прави фазата testable без жив Oracle ([[project_oracle_network_block]]).
- Позволява enrichment на произволен DataFrame (не само от конкретен SQL).

### Deliverables
- [x] `BankingToolsAPI.classify_transactions(df, description_column='description', direction_column=None)`:
  - Приема DataFrame, не SQL — caller прави fetch чрез `execute_sql_query` / `execute_domain_query`.
  - Добавя 5 нови колони: `category_code`, `category_path`, `category_score`, `category_matched_keywords`, `category_unclassified`.
  - Не мутира input-а (copy).
  - Respect-ва `last_error` контракта — error → empty DataFrame + populated `last_error`.
  - Лениво импортва `banking_mcp.classification` за да не зарежда taxonomy при API import.
- [x] Update на `execute_code` tool description в `db_tools.py` — нов пример и signature listing, така че LLM-ът да знае за метода.

### Output columns
- `category_code` — 12-цифрен code от таксономията или `None`.
- `category_path` — "Main > Primary > Sub1 > Sub2" string или `None`.
- `category_score` — float (по-висок = по-специфичен match).
- `category_matched_keywords` — list[str].
- `category_unclassified` — bool. `mean()` дава unclassified rate.

### Acceptance criteria
- [x] Pytest **11 нови** теста в `test_tools_api.py`:
  - Adds expected columns.
  - Assigns correct codes за restaurant / salary / rent.
  - Marks unclassified правилно (merchant-only, NaN, whitespace).
  - **Does not mutate input** — invariant за безопасност.
  - Empty / `None` input → empty DataFrame, no error.
  - Missing description / direction column → empty + `last_error`.
  - Direction filter работи per-row.
  - **`category_code` ∈ known_codes** invariant (hallucination-safe).
- [x] Пълен test suite зелен: **203/203 PASS**.
- [x] Real-Oracle integration test пропуснат заради network blocker — записан като Phase 6 follow-up.

### Recommended workflow inside `execute_code`
```python
df = tools.execute_sql_query(
    "SELECT txn_id, amount, description FROM transactions "
    "WHERE customer_id = 12345 AND txn_date >= TO_DATE('2026-01-01','YYYY-MM-DD')"
)
enriched = tools.classify_transactions(df)
unclassified_rate = enriched['category_unclassified'].mean()
by_category = enriched.groupby('category_path')['amount'].sum().sort_values()
result = by_category.to_dict()
```

### Известни ограничения (документирани)
- **Real Oracle integration** не е тестван — [[project_oracle_network_block]] блокира. Mock тестовете покриват shape/invariants. Phase 6 за live test.
- **Audit logging на enrichment** — `BankingToolsAPI.execute_sql_query` вече логва SQL-а. Самият enrichment pass не е audit-ван (Phase 6).
- **Per-row Python loop** — за 1000 транзакции тества се <1s; за >100k реда ще има нужда от vectorization (Phase 6).

### Out of scope (нарочно)
- Prompts за категории — Phase 5.
- LLM fallback / merchant aliases / audit / observability — Phase 6.

---

## Phase 5 — Banking prompts ✅ ЗАВЪРШЕНА (2026-05-12)

**Цел:** LLM-ът има готови analytical primer-и, които използват Phase 2–4.

### Deliverables
- [x] `categorize_transaction(description, direction='auto', top_k=3)` — primer-ва LLM-а да извика `classify_description` MCP tool, отказва се от гадаене когато `unclassified: true`, споменава `payroll_pattern_hit` и salary code `001001001000`.
- [x] `spending_breakdown_by_category(customer_id, from_date, to_date, connection)` — fetches transactions, enrich-ва ги с `tools.classify_transactions`, групира по `category_path`, флагва unclassified rate > 30% като data-quality concern.
- [x] `income_pattern_analysis(customer_id, months=6, connection)` — детектира recurring income: filter по code `001001001000` или `payroll_pattern_hit`, проверка за един и същ payer в >= 2 последователни месеца (heuristic от source workbook-а).
- [x] Всичките 3 нови prompt-а включват `_ERROR_HANDLING_NOTE`.

### Acceptance criteria
- [x] **8 нови** pytest теста в `test_prompts.py`:
  - All 8 prompts registered (5 стари + 3 нови).
  - `categorize_transaction`: quoted description, lists tool name, споменава `unclassified`, `payroll_pattern_hit`, salary code.
  - Default direction = "auto", explicit direction override.
  - `spending_breakdown_by_category`: customer + dates plumbed, schema rendered, `tools.classify_transactions` instruction, category columns named, `last_error` контракт.
  - Uses default connection.
  - `income_pattern_analysis`: customer id, lookback months, code `001001001000`, consecutive-months heuristic, both tool refs.
  - Default months = 6.
  - No-connection graceful path работи.
- [x] Пълен test suite зелен: **211/211 PASS**.

### Out of scope (нарочно)
- LLM fallback / merchant aliases / audit / observability / live-Oracle integration — Phase 6.

---

## Phase 6 — Audit, observability, aliases, reload ✅ ЗАВЪРШЕНА (2026-05-12)

**Цел:** Production-ready полировка. Затваря Phase 3 known gap-овете и добавя observability.

### Deliverables
- [x] **Merchant alias overlay** `banking_mcp/resources/data/merchant_aliases.json`:
  - ~55 BG търговци (ЛИДЛ/Kaufland/Билла, OMV/Shell/Lukoil, Bolt/Wizz Air, IKEA/Practiker, Glovo и т.н.).
  - Typo corrections за code `001001006000` (добавя коректно изписани "обезщетение [за] безработица").
  - Merge-ва се в `KeywordIndex._build()` срещу същия `code → category` map.
- [x] **Audit hook** `banking_mcp.audit.log_classification`:
  - Description PII-redacted, top_code verbatim (safe), source identifier.
  - Per-call за `classify_description` (source="mcp_tool"); един batch summary за `classify_transactions` (source="tools_api.classify_transactions").
- [x] **In-memory stats** `banking_mcp/classification/stats.py`:
  - Thread-safe counter: total, unclassified, payroll_pattern_hits, per-direction breakdown с unclassified rate.
  - `snapshot()` за read; `reset()` за reload-а; resets на process restart by design.
- [x] **MCP resources**:
  - `banking://transaction-categories/codes` — flat enum от 177 codes за client-side LLM structured-output fallback.
  - `banking://classification-stats` — live snapshot на counter-а.
- [x] **Reload mechanism**:
  - `banking_mcp.classification.reload_index()` — drop classifier singleton + categories_loader caches + stats reset.
  - MCP tool `reload_classification_taxonomy` за admin без рестарт.

### Acceptance criteria
- [x] Phase 3 unclassified gap затворен — LIDL/OMV/IKEA/Glovo и др. вече класифицират (`test_merchant_alias_classifies` × 13 параметризации).
- [x] Source typo за code `001001006000` обработен — формалното "обезщетение за безработица" вече match-ва (`test_typo_correction_for_unemployment_benefit`).
- [x] Audit hook се вика при `classify()`, не се вика при `audit=False`; пише `top_code=None` за unclassified (`test_audit_hook_*` × 3).
- [x] Stats counter правилно инкрементира, payroll hits се броят, per-direction breakdown работи, `reset()` нулира (`test_stats_*` × 4).
- [x] `reload_index()` сменя singleton-а и нулира stats; MCP tool връща `status: ok` (`test_reload_*` × 3).
- [x] `codes` resource връща всичките 177 категории със 12-цифрени codes; `classification-stats` resource отразява live state (× 2).
- [x] **Hallucination-safe инвариант продължава** — codes от alias overlay-а са pre-validated срещу `by_code` map; ако code не съществува в таксономията, alias-ът се игнорира.
- [x] Пълен test suite зелен: **238/238 PASS** (+ 27 нови за Phase 6, − 0 регресии след update на 4 Phase 3 теста).

### Известни ограничения (документирани, не блокират)
- **Live Oracle integration test** — все още блокиран от [[project_oracle_network_block]]. Когато мрежата се отвори: смок-тест с реална SCARDS_O.TRANSACTIONS заявка през `tools.execute_sql_query` + `tools.classify_transactions`, измерване на unclassified rate върху production sample.
- **LLM fallback inside server** — нарочно НЕ е реализиран. MCP сървърът няма LLM client wired — fallback стои на client side: clientът чете `banking://transaction-categories/codes` и прави structured output срещу enum-а. Документирано в `classify_description` tool description.
- **Per-row Python loop** в `classify_transactions` — все още не е vectorized; за >100k реда ще има нужда от optimization (open issue, не блокира).

### Out of scope (нарочно)
- Vectorized batch classification (за >100k реда).
- Server-side LLM client (архитектурно не е тук — MCP е data-providing слой).
- Real-Oracle integration test (мрежов blocker).

---

## Phase gating rules

1. **One phase at a time.** Не започваме Phase N+1 преди Phase N да има всички ☑ acceptance criteria.
2. **Tests must pass.** `pytest` на цялото repo трябва да е зелен преди merge.
3. **Doc must update.** Този файл и `PROJECT_FILE_FUNCTION_GUIDE_BG.md` се update-ват в същия PR.
4. **No silent scope creep.** Ако фаза изисква повече от описаното — спираме, обсъждаме, update-ваме плана преди да продължим.
5. **Rollback plan.** Всяка фаза е изолирана: ако някоя счупи нещо, revert на нейния commit връща предишно работещо състояние.

---

## Текущ статус

| Phase | Status | Owner | Notes |
|---|---|---|---|
| 1 — Foundation | ✅ DONE | DBoychew | Commit `66eb7ce`, BG-only |
| 2 — MCP Resource | ✅ DONE | DBoychew | Commit `a06b74c`, 160/160 PASS |
| 3 — Classify tool | ✅ DONE | DBoychew | Commit `f13f2bf`, 192/192 PASS |
| 4 — `classify_transactions` | ✅ DONE | DBoychew | Commit `77e5123`, 203/203 PASS |
| 5 — Prompts | ✅ DONE | DBoychew | Commit `b0d7a08`, 211/211 PASS |
| 6 — Audit/observability | ✅ DONE | DBoychew | 238/238 PASS; aliases затварят Phase 3 gap |
