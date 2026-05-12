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

## Phase 3 — `classify_description` standalone tool

**Цел:** Чист keyword-matching инструмент, който приема свободен текст и връща top-K кандидата с code + score. Без DB. Това е инструментът, който решава 80% от случаите детерминистично.

### Deliverables
- [ ] Extract keywords from `description` за outgoing категориите (regex от шаблона *"ключови думи като - X, Y, Z"*). Update-ва се `transaction_categories.json` (Phase 1 скрипта се преизпълнява).
- [ ] `banking_mcp/classification/keyword_index.py`:
  - Build reverse index `keyword → [category_code, ...]` веднъж при load.
  - Case-insensitive, accent-aware matching.
  - Tokenize transaction description; score = брой matched keywords × specificity weight.
- [ ] Нов MCP tool в `banking_mcp/tools/`:
  ```python
  classify_description(text: str, direction: str = "auto", top_k: int = 3)
  ```
  Връща structured response:
  ```json
  {
    "input": "...",
    "matches": [
      {"code": "002001001001", "name": "Хранителни магазини",
       "path": "Изходяща > Плащания > Храна > Хранителни магазини",
       "score": 0.95, "matched_keywords": ["лидл", "супермаркет"]}
    ],
    "unclassified": false
  }
  ```
- [ ] Special-case payroll patterns — ако описанието match-ва `PAYROLL_MM_YYYY` или подобен BG pattern → boost score за code `001001001000`.

### Acceptance criteria
- [ ] Pytest **fixture с реални описания** (минимум 20 от продакшън Oracle-а, ако са достъпни — иначе синтетични):
  - "ЛИДЛ БЪЛГАРИЯ ЕООД ПЛОВДИВ" → `002001001001` (Хранителни магазини).
  - "PAYROLL_03_2026 СИРМА СОЛЮШЪНС" → `001001001000` (Възнаграждение).
  - "OMV BG SOFIA" → `002001002001` (Гориво).
  - "ПЕНСИЯ НОИ 03/2026" → `001001004000` (Доход от пенсия).
- [ ] Precision на златния тест ≥ 80% top-1; ≥ 95% top-3.
- [ ] Tool **никога не халюцинира code** — връща само codes от заредената таксономия (enum constraint).
- [ ] Audit log запис при всяко извикване ([[project_petru_alignment]] стил).

### Out of scope
- DB integration — идва в Phase 4.
- LLM fallback за unclassified — идва в Phase 6.

---

## Phase 4 — Domain query: `classify_transactions`

**Цел:** Пуска класификацията върху реални транзакции от Oracle. Връща обогатен DataFrame с category code/name.

### Deliverables
- [ ] Решение **SQL-only vs hybrid**:
  - Опция A (SQL-only): `REGEXP_LIKE` CASE chain в Oracle. Бързо, но огромен SQL. Hard to maintain.
  - Опция B (hybrid, **препоръчителна**): SQL fetch на raw транзакции → Python pass с Phase 3 индекса → return.
- [ ] Domain query registration в `db_config.json` (или където стоят domain queries в момента):
  ```yaml
  classify_transactions:
    sql: "SELECT txn_id, txn_date, amount, description, customer_id
          FROM SCARDS_O.TRANSACTIONS
          WHERE customer_id = :customer_id
            AND txn_date BETWEEN :from_date AND :to_date"
    post_process: classify_with_keyword_index   # извиква Phase 3
  ```
- [ ] Output schema: оригинални колони + `category_code`, `category_path`, `category_score`, `category_unclassified` (bool).
- [ ] Покритие на `last_error` контракта от `_ERROR_HANDLING_NOTE` в prompts.

### Acceptance criteria
- [ ] Pytest с **mock Oracle** (използваме съществуващия test fixture от `tests/`).
- [ ] Integration test срещу реална SCARDS_O — pending [[project_oracle_network_block]] да се разреши; **МОЖЕ ДА БЛОКИРА ФАЗАТА**.
- [ ] `tools.execute_domain_query("classify_transactions", customer_id=...)` връща непразен DataFrame с очакваните колони.
- [ ] Unclassified rate < 20% върху 1000-редов production sample.
- [ ] Audit logger логва: customer_id, row count, unclassified count.

### Pre-conditions
- Phase 3 е merge-нат и tagged като stable.
- Потвърдена достъпност на target table в SCARDS_O (column names, типове).

---

## Phase 5 — Banking prompts

**Цел:** LLM-ът има готови analytical primer-и, които използват Phase 2–4.

### Deliverables
- [ ] `categorize_transaction(description)` prompt в `banking_prompts.py` — викa `classify_description` tool-а, форматира резултата.
- [ ] `spending_breakdown_by_category(customer_id, from_date, to_date)` — викa `classify_transactions` domain query, групира по main + primary category, връща таблица + кратка интерпретация.
- [ ] `income_pattern_analysis(customer_id)` — детектира regular income (вижда payroll patterns + код 001001001000 в последователни месеци).
- [ ] Всеки prompt включва `_ERROR_HANDLING_NOTE`.

### Acceptance criteria
- [ ] Pytest за всеки prompt: render-ва се без exception при празна и при валидна connection.
- [ ] Manual smoke: тестова сесия с Claude Code срещу prompt → разумен output.
- [ ] Тестът покрива случая *"клиент 12345 — разходи за храна Q1 2026"*.

---

## Phase 6 — Audit, observability, LLM fallback

**Цел:** Production-ready полировка. Не започва преди Phase 5.

### Deliverables
- [ ] Audit запис на всяка класификация: input description (redacted PII), top match, score, unclassified flag.
- [ ] Metric: % unclassified per direction (експозирано като MCP resource `banking://classification-stats`).
- [ ] LLM fallback за unclassified > 0.5 score gap — извиква LLM **САМО със constrained enum** от valid codes (продължение на structured-output дискусията).
- [ ] Reload mechanism — `POST /admin/reload-categories` или подобно, без рестарт на сървъра.

### Acceptance criteria
- [ ] Stats resource връща смислени числа след 1 ден production trafik.
- [ ] LLM fallback **не може** да върне code извън taxonomy-та (verified чрез fuzz test).

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
| 1 — Foundation | ✅ DONE | Claude + DBoychew | Commit `66eb7ce`, BG-only |
| 2 — MCP Resource | ✅ DONE | Claude + DBoychew | 160/160 tests PASS |
| 3 — Classify tool | ⏳ NEXT | — | Стартираме след approve |
| 4 — Domain query | 🔒 LOCKED | — | Чака Phase 3 + Oracle мрежа |
| 5 — Prompts | 🔒 LOCKED | — | Чака Phase 4 |
| 6 — Audit/observability | 🔒 LOCKED | — | Чака Phase 5 |
