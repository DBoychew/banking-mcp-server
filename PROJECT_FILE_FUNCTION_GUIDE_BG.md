# Справочник на файловете и функциите

Този файл описва ролята на всеки смислен файл в проекта и на всяка функция/метод в Python кода и тестовете.

Обхват:
- Включени са root/config файловете, Python пакетът `banking_mcp`, тестовете и versioned IDE метаданните.
- Добавено е и описание на локалните root runtime файлове `.env` и `db_config.json`, без да се изписват секрети.
- Не са описвани `.git`, cache директории, `logs/`, `data/` и други runtime/temporary артефакти.

## Root и meta файлове

### `.dockerignore`
Предназначение: казва на Docker кои файлове и директории да не влизат в build context-а, за да не се качват тестове, IDE файлове, `.env`, документация и локални артефакти.

Функции: няма.

### `.env`
Предназначение: локален runtime файл с реалните стойности за environment променливите. Използва се от `pydantic-settings` и `python-dotenv`, за да зареди транспорт, порт, audit и Oracle настройки.

Функции: няма.

### `.env.example`
Предназначение: шаблон на `.env` с всички очаквани ключове и примерни DSN стойности за multi-DB режим.

Функции: няма.

### `.gitignore`
Предназначение: описва кои локални файлове да не се commit-ват: `.env`, логове, data, cache, IDE артефакти и generated runtime state.

Функции: няма.

### `.mcp.json`
Предназначение: примерна MCP client конфигурация. Дефинира един `stdio` server и един HTTP server към локалния endpoint.

Функции: няма.

### `AUDIT.md`
Предназначение: оперативна бележка, че `domain_queries.scards` по подразбиране е празен и кои аналитични query типове могат да се добавят по-късно.

Функции: няма.

### `db_config.json`
Предназначение: активната runtime конфигурация за базите. В момента регистрира само `scards` Oracle connection, маркира я като default и оставя `domain_queries` празни.

Функции: няма.

### `docker-compose.yml`
Предназначение: описва контейнера `banking-mcp`, env настройките, volume mount-овете за `logs/` и `data/`, healthcheck-а и публикуването на порт 80.

Функции: няма.

### `Dockerfile`
Предназначение: multi-stage build. Първият stage инсталира Python зависимостите, вторият stage изгражда runtime image с `nginx`, `supervisor`, приложението и production env defaults.

Функции: няма.

### `main.py`
Предназначение: CLI entry point за стартиране на сървъра в `stdio`, `http` или `sse` режим.

Класове и функции:
- `main()`: избира transport от CLI аргумент или `settings.MCP_TRANSPORT`, валидира го и стартира `run_stdio()` или `run_http()`.

### `nginx.conf`
Предназначение: reverse proxy пред FastAPI/MCP приложението. Пренасочва `/health`, `/mcp`, `/docs` и `/openapi.json` към вътрешния порт 8080.

Функции: няма.

### `pyproject.toml`
Предназначение: централна project metadata конфигурация за packaging, зависимости, optional extras (`multi-db`, `dev`) и pytest настройки.

Функции: няма.

### `README.md`
Предназначение: кратък operational guide за локално HTTP стартиране, Docker demo run и клиентска MCP конфигурация.

Функции: няма.

### `requirements.txt`
Предназначение: flat списък със зависимости за `pip install -r`, включително core stack-а и закоментираните optional multi-DB драйвери.

Функции: няма.

### `supervisord.conf`
Предназначение: управлява двата процеса в контейнера: `python main.py http` и `nginx -g "daemon off;"`.

Функции: няма.


## `banking_mcp/`

### `banking_mcp/__init__.py`
Предназначение: package marker. В момента е празен.

Функции: няма.

### `banking_mcp/config.py`
Предназначение: central settings слой. Зарежда env стойности и валидира MCP transport/path параметрите.

Класове и функции:
- `Settings`: `BaseSettings` моделът за server, audit, MCP transport и Oracle env настройките.
- `Settings.normalize_mcp_transport()`: нормализира и валидира `MCP_TRANSPORT`, така че да е само `stdio`, `http` или `sse`.
- `Settings.normalize_mcp_http_path()`: прави `MCP_HTTP_PATH` валиден URL path без trailing slash, query string или fragment.

### `banking_mcp/server.py`
Предназначение: сглобява FastAPI приложението, FastMCP инстанцията, audit lifecycle-а и публичните HTTP маршрути.

Класове и функции:
- `get_public_mcp_endpoint_path()`: връща външния MCP path като `/mcp/...`, независимо как е зададен вътрешният `MCP_HTTP_PATH`.
- `health_status()`: MCP resource за бърз health сигнал с резултат `"ok"`.
- `create_combined_app()`: създава FastAPI приложението, монтира MCP ASGI app-а и регистрира помощните HTTP route-ове.
- `create_combined_app.lifespan()`: стартира audit логера и MCP session manager-а при boot, а при shutdown flush-ва schema cache-а и спира audit-а.
- `create_combined_app.unhandled_exception_handler()`: глобален exception handler, който audit-ва грешката и връща стандартен 500 JSON отговор.
- `create_combined_app.health()`: HTTP `/health` endpoint с транспорт, endpoint path, stateless mode и UTC timestamp.
- `create_combined_app.root()`: пренасочва `/` към Swagger документацията `/docs`.
- `create_combined_app.favicon()`: връща `204 No Content` за `/favicon.ico`, за да няма шумни 404 заявки.
- `create_combined_app.mcp_redirect()`: пренасочва `/mcp` към реалния конфигуриран MCP path.
- `create_combined_app.mcp_root_redirect()`: ако `MCP_HTTP_PATH` не е `/`, пренасочва и `/mcp/` към точния именуван endpoint.
- `run_stdio()`: стартира FastMCP в `stdio` режим за desktop MCP клиенти.
- `run_http()`: стартира `uvicorn`, отпечатва локалните URL-и и вдига FastAPI/MCP сървъра.

### `banking_mcp/tools_api.py`
Предназначение: high-level wrapper над `DatabaseManager`, който sandbox кодът вижда като обект `tools`.

Класове и функции:
- `BankingToolsAPI`: фасада за SQL заявки, domain queries и schema context без директен достъп до драйвери.
- `BankingToolsAPI.__init__()`: запазва `DatabaseManager`, избира default connection и инициализира `last_error`.
- `BankingToolsAPI._resolve_connection()`: връща изрично подадената или default connection; при липса хвърля грешка.
- `BankingToolsAPI.execute_sql_query()`: изпълнява read-only SQL през manager-а и връща `DataFrame`; при грешка връща празен `DataFrame`.
- `BankingToolsAPI.execute_domain_query()`: изпълнява pre-configured domain query и използва същия error handling модел като SQL path-а.
- `BankingToolsAPI.classify_transactions()`: hybrid enrichment — приема DataFrame, използва Phase 3 keyword index, добавя 5 нови колони (`category_code`, `category_path`, `category_score`, `category_matched_keywords`, `category_unclassified`). Не мутира input-а. Empty/None input → празен DataFrame без error. Missing column → empty + `last_error`. Per-row direction filter поддържан през `direction_column`.
- `BankingToolsAPI.get_context_for_llm()`: връща schema, dialect hint и domain queries за prompt generation.
- `BankingToolsAPI.last_error`: property за последната грешка, която е върната към sandbox кода.

### `banking_mcp/executor.py`
Предназначение: RestrictedPython sandbox за `execute_code`, с позволени само безопасни builtin-и и preloaded библиотеки.

Класове и функции:
- `_inplacevar()`: реализира позволените inplace оператори като `+=`, `-=`, `*=`, `**=` за RestrictedPython.
- `_write_()`: write guard hook; в текущия вид не блокира мутации и просто връща обекта.
- `_blocked_import()`: твърдо забранява `import` и връща ясна грешка към потребителя.
- `SafeJSON`: лек wrapper над `json`, който умее да сериализира numpy/pandas/datetime подобни обекти.
- `SafeJSON._default_serializer()`: fallback serializer за масиви, scalar-и и обекти с `isoformat()`.
- `SafeJSON.dumps()`: `json.dumps()` с безопасен default serializer.
- `SafeJSON.loads()`: стандартен `json.loads()` passthrough.
- `CodeExecutor`: основният sandbox executor, който подава `tools`, `pd`, `np`, `json` и `math` в ограниченото изпълнение.
- `CodeExecutor.__init__()`: създава вътрешен `BankingToolsAPI` за избраната default connection.
- `CodeExecutor._normalize_code()`: чисти типографски кавички и други често срещани не-ASCII артефакти от copy/paste код.
- `CodeExecutor._fix_multiline_fstrings()`: поправя проблемни f-string случаи, в които има escape-нат нов ред в един ред код.
- `CodeExecutor._validate_imports()`: парсва AST и предварително спира `import`/`from ... import ...` конструкции.
- `CodeExecutor.execute()`: компилира кода с RestrictedPython, изпълнява го, връща `result` или `printed` и нормализира syntax/runtime грешките.

### `banking_mcp/tools/__init__.py`
Предназначение: централен registry слой за всички MCP tools.

Класове и функции:
- `register_all_tools()`: регистрира database tools и classification tools.

### `banking_mcp/tools/db_tools.py`
Предназначение: дефинира MCP tools, които expose-ват database context и sandbox анализ.

Класове и функции:
- `register_db_tools()`: закача трите tool handler-а към FastMCP инстанцията.
- `register_db_tools.list_databases()`: връща JSON списък с наличните връзки, type, description и default flag.
- `register_db_tools.get_database_context()`: връща JSON с schema, domain queries и dialect hint за избрана или default връзка.
- `register_db_tools.execute_code()`: изпълнява Python код през `CodeExecutor` и връща сериализиран резултат или текстова грешка.

### `banking_mcp/tools/classification_tools.py`
Предназначение: дефинира MCP tools за keyword-базирана класификация на транзакции срещу IRIS таксономията.

Класове и функции:
- `register_classification_tools()`: закача `classify_description` tool-а към FastMCP инстанцията.
- `register_classification_tools.classify_description()`: приема `text`, `direction` (auto/incoming/outgoing), `top_k` (1–10) и връща JSON със top-K кандидата, hierarchical path, score, matched keywords, payroll hit flag и `unclassified` boolean. Грешен `direction` се връща като JSON `{error}`.

### `banking_mcp/classification/__init__.py`
Предназначение: централен export на classification API (`classify`, `get_index`, `ClassificationMatch`, `ClassificationResult`).

### `banking_mcp/classification/keyword_index.py`
Предназначение: keyword индекс и matcher срещу IRIS таксономията (само BG). Build-ва се веднъж като singleton (`@lru_cache`).

Класове и функции:
- `ClassificationMatch`: dataclass с `code`, `leaf_name`, `path`, `direction`, `score`, `matched_keywords`. `to_dict()` сериализатор.
- `ClassificationResult`: dataclass с `input`, `matches[]`, `payroll_pattern_hit`, derived `unclassified`. `to_dict()` сериализатор.
- `_fold()`: lowercase + NFC normalize за case-insensitive matching.
- `_category_path()`: builds 'Main > Primary > Sub1 > Sub2' string.
- `_payroll_pattern_to_regex()`: превръща `PAYROLL_MM_YYYY`-style шаблон в regex с `\d{2}` / `\d{4}` за placeholder-ите.
- `KeywordIndex`: build-ва reverse index + payroll regexes; `classify()` scoring (substring за keywords ≥4 символа, word-boundary regex за по-къси).
- `get_index()`: singleton accessor.
- `classify()`: convenience wrapper.

### `banking_mcp/resources/__init__.py`
Предназначение: централен registry слой за MCP resources.

Класове и функции:
- `register_all_resources()`: регистрира banking resource-ите.

### `banking_mcp/resources/banking_resources.py`
Предназначение: read-only MCP resources, които дават контекст през `banking://...` URI-та.

Класове и функции:
- `register_banking_resources()`: регистрира всички banking resources.
- `register_banking_resources.databases_resource()`: връща JSON списък с всички връзки и default connection-а.
- `register_banking_resources.schema_resource()`: връща compact schema текст за дадена връзка или текстова грешка.
- `register_banking_resources.domain_queries_resource()`: връща JSON с pre-configured domain queries за връзката.
- `register_banking_resources.dialects_resource()`: връща JSON справочник с SQL dialect hints за всички поддържани `db_type`.
- `register_banking_resources.transaction_categories_resource()`: връща пълната IRIS PSD2Hub таксономия (BG-only).
- `register_banking_resources.transaction_categories_incoming_resource()`: филтриран изглед — само входящи категории.
- `register_banking_resources.transaction_categories_outgoing_resource()`: филтриран изглед — само изходящи категории.
- `register_banking_resources.transaction_categories_payroll_patterns_resource()`: BG payroll description patterns.

### `banking_mcp/resources/categories_loader.py`
Предназначение: кеширан loader за IRIS таксономията. Чете `data/transaction_categories.json` веднъж, нормализира whitespace (NBSP → space, trim) и предоставя филтрирани изгледи.

Класове и функции:
- `load_categories()`: `@lru_cache(maxsize=1)` — пълният payload (всички категории + patterns + counts + locale).
- `get_incoming()`: списък само с категории за постъпления (`direction == "incoming"`).
- `get_outgoing()`: списък само с категории за разходи (`direction == "outgoing"`).
- `get_payroll_patterns()`: BG payroll description patterns за special-case payroll detection.
- `get_counts()`: copy на `counts` блока от payload-а.

### `banking_mcp/resources/data/transaction_categories.json`
Предназначение: bundled package data — IRIS PSD2Hub таксономия във flat JSON. Генерира се от `scripts/convert_transaction_categories.py`. **Само BG локал** (Greek колони/patterns се филтрират при конверсия).

Структура:
- `version`, `source_file`, `standard`, `locale: "bg_BG"`.
- `counts`: `{incoming: 55, outgoing: 122, payroll_patterns: 5}`.
- `categories[]`: всеки запис има `full_code`, `direction`, `level`, hierarchy (`main_category`, `primary_category`, `sub_level_1`, `sub_level_2`), `leaf_name`, `description`, `keywords_bg`.
- `payroll_patterns[]`: `{pattern_group, example}` за payroll regex matching.

### `scripts/convert_transaction_categories.py`
Предназначение: еднократен / repeatable конвертор от `Transaction Categories Iris Solutions v.1.1.xlsx` към `banking_mcp/resources/data/transaction_categories.json`. Forward-fill-ва merged-cell йерархията, разделя ключови думи и филтрира Greek съдържание.

Класове и функции:
- `_contains_greek()`: True ако в текста има Greek/Coptic codepoint.
- `_clean()`, `_split_keywords()`, `_parse_full_code()`, `_level_from_code()`: помощни нормализатори.
- `_parse_sheet()`: обхожда един sheet с forward-fill на hierarchy state.
- `_parse_payroll_patterns()`: BG-only payroll patterns от Sheet1.
- `main()`: CLI entry point (`--src`, `--out`).

### `banking_mcp/prompts/__init__.py`
Предназначение: централен registry слой за MCP prompts.

Класове и функции:
- `register_all_prompts()`: регистрира banking prompt template-ите.

### `banking_mcp/prompts/banking_prompts.py`
Предназначение: домейн-специфични prompt шаблони за банкови анализи, които инжектират schema и dialect context.

Класове и функции:
- `_resolve_connection()`: връща подадената връзка или default connection-а от manager-а.
- `_connection_context()`: сглобява кратък текстов блок с име на връзката, `db_type`, dialect hint и compact schema.
- `register_banking_prompts()`: регистрира prompt handler-ите към MCP.
- `register_banking_prompts.database_overview()`: генерира prompt за high-level преглед на база и идеи за аналитични въпроси.
- `register_banking_prompts.analyze_table()`: генерира prompt за фокусиран анализ на една таблица, sample rows, KPIs и breakdown-и.
- `register_banking_prompts.compare_periods()`: генерира prompt за сравнение на метрика между два периода.
- `register_banking_prompts.data_quality_check()`: генерира prompt за NULL ratio, duplicate check и базови anomaly hints.
- `register_banking_prompts.sql_helper()`: генерира prompt, който превежда естествен език към диалектно коректен SELECT и го изпълнява.
- `register_banking_prompts.categorize_transaction()`: prompt за класификация на единично описание срещу IRIS таксономията — инструктира LLM-а да вика `classify_description` tool-а, отказва се от гадаене при `unclassified`, споменава `payroll_pattern_hit` и salary code `001001001000`.
- `register_banking_prompts.spending_breakdown_by_category()`: prompt за разходи per category за един customer в date range — fetch → `tools.classify_transactions` enrichment → group by `category_path` → флаг при unclassified rate > 30%.
- `register_banking_prompts.income_pattern_analysis()`: prompt за recurring-income detection — филтър по code `001001001000` или `payroll_pattern_hit`, consecutive-months heuristic върху payer колоната.

### `banking_mcp/audit/__init__.py`
Предназначение: re-export модул за audit public API-то (`log_query`, `log_error`, `start`, `stop`, `redact`).

Функции: няма локални дефиниции.

### `banking_mcp/audit/redaction.py`
Предназначение: минимална PII redaction логика за SQL и error текстове.

Класове и функции:
- `redact()`: заменя email-и, телефони и дълги string literal-и вътре в единични кавички с маркери като `<EMAIL>`, `<PHONE>` и `<REDACTED>`.

### `banking_mcp/audit/logger.py`
Предназначение: asynchronous audit logger с background writer thread, daily rotated JSONL логове и retention policy.

Класове и функции:
- `_current_log_path()`: връща текущия дневен audit log path според днешната дата и `AUDIT_LOG_PATH`.
- `_writer_loop()`: фоновият loop, който чете записи от queue, върти файловете по дата и flush-ва JSON редовете на диска.
- `_purge_old_logs()`: изтрива стари audit файлове според `AUDIT_LOG_RETENTION_DAYS`.
- `start()`: стартира writer thread-а идемпотентно.
- `stop()`: изчаква queue-то да се източи и спира writer thread-а.
- `_enqueue()`: подава запис към queue-то; ако audit е изключен, не прави нищо.
- `_utc_iso()`: връща UTC timestamp в ISO формат със `Z` suffix.
- `log_query()`: записва audit събитие за SQL заявка, като редактирa query/error текста и пази duration, row count и source.
- `log_error()`: async вариант за запис на неочаквани request-level грешки.

### `banking_mcp/db/__init__.py`
Предназначение: convenience export модул за `DatabaseManager`, schema fetcher-ите, SQL dialect hints и singleton factory-то.

Функции: няма локални дефиниции.

### `banking_mcp/db/config.py`
Предназначение: CRUD и serialization слой за connection config-а и domain queries в `db_config.json`.

Класове и функции:
- `SchemaFilter`: TypedDict за `include`/`exclude` wildcard правила при schema filtering.
- `ParameterInfo`: TypedDict описание на един domain query параметър.
- `DomainQueryDef`: TypedDict за SQL, параметри, описание и expected output на domain query.
- `ConnectionInfo`: TypedDict за една database connection конфигурация.
- `ConfigData`: TypedDict за целия JSON config файл.
- `_get_default_config()`: връща bootstrap конфигурация с единствената default връзка `scards`.
- `load_config()`: чете `db_config.json`, нормализира legacy ключа `type -> db_type`, а ако файлът липсва, създава default config.
- `save_config()`: записва конфигурацията обратно на диска като pretty JSON.
- `resolve_env_vars()`: заменя `${VAR}` placeholders в низ с реалните env стойности.
- `resolve_env_vars._replace()`: regex callback, който вади името на env променливата и връща нейната стойност.
- `resolve_dsn()`: backward-compatible alias към `resolve_env_vars()` за DSN низове.
- `get_connection()`: връща connection config по име и добавя изчислен `is_default` флаг.
- `list_connections()`: връща всички връзки от конфигурацията с попълнен `is_default`.
- `get_default_connection()`: връща името на default connection-а или `None`.
- `add_connection()`: добавя нова връзка в конфигурацията и я прави default само ако досега няма default.
- `remove_connection()`: премахва връзка и нейните domain queries; ако е била default, избира нова default връзка.
- `set_default_connection()`: задава коя връзка да е default.
- `update_schema_filter()`: обновява include/exclude правилата за schema filtering на конкретна връзка.
- `get_domain_queries()`: връща domain query map-а за дадена връзка.
- `add_domain_query()`: добавя или обновява named domain query към връзка.
- `remove_domain_query()`: премахва domain query по име и връща дали е имало такава.
- `filter_tables()`: филтрира списък от таблици чрез wildcard include/exclude правила.
- `parse_compact_params()`: парсва параметрите на domain query от compact string или legacy list формат до унифициран списък от `ParameterInfo`.

### `banking_mcp/db/manager.py`
Предназначение: основният data layer на проекта. Отговаря за connection dispatch, SQL validation, execution, schema cache, domain queries и LLM context.

Класове и функции:
- `DomainQueryInfo`: TypedDict shape за domain query metadata, която се показва към LLM/clients.
- `LLMContext`: TypedDict shape за schema, dialect hint, domain queries и налични връзки.
- `_resolve_config_value()`: опитва да resolve-не `${VAR}` placeholder; ако не може, връща оригиналния низ.
- `_parse_url_dsn()`: разбива URL-style DSN на `user`, `password`, `host`, `port` и `database`.
- `_open_sqlite()`: отваря SQLite база, създава parent directory при нужда и задава `sqlite3.Row` row factory.
- `_quote_oracle_identifier()`: валидира и quote-ва Oracle schema identifier за `ALTER SESSION`.
- `_get_oracle_schema()`: взема schema от connection config-а или global settings и я нормализира за Oracle употреба.
- `_get_oracle_connect_args()`: resolve-ва Oracle DSN, user и password от env/settings или от embedding в DSN низа.
- `_open_oracle()`: отваря Oracle връзка и по желание сменя `CURRENT_SCHEMA`.
- `_open_postgres()`: отваря PostgreSQL чрез `psycopg`, а при липса прави fallback към `psycopg2`.
- `_open_mysql()`: отваря MySQL/MariaDB връзка чрез `pymysql`.
- `_open_duckdb()`: отваря DuckDB база в memory mode или read-only file mode.
- `_open_clickhouse()`: създава ClickHouse client чрез `clickhouse-connect`.
- `_open_connection()`: dispatcher, който избира правилния opener според `db_type`.
- `_close_quietly()`: затваря cursor/connection/client без да вдига вторична грешка.
- `_run_select()`: изпълнява SELECT заявка по driver-specific начин и връща `(columns, rows)`.
- `_ping_sql()`: връща най-простата health query за дадения driver, например `SELECT 1 FROM DUAL` за Oracle.
- `_strip_sql_literals_and_comments()`: чисти string literal-и и SQL коментари, за да може validator-ът да търси забранени ключови думи без false positive.
- `DatabaseManager`: главният orchestrator за query execution, schema fetch и runtime config management.
- `DatabaseManager.__init__()`: bootstrap-ва config-а и зарежда schema cache-а от диска.
- `DatabaseManager._load_schema_cache()`: чете кеширания schema JSON файл, ако е наличен и валиден.
- `DatabaseManager._save_schema_cache()`: записва текущия schema cache на диска.
- `DatabaseManager._validate_sql()`: спира празни заявки, multiple statements, mutating SQL и всичко, което не започва с `SELECT`/`WITH`.
- `DatabaseManager.query()`: изпълнява SELECT, audit-ва резултата и връща `pandas.DataFrame`.
- `DatabaseManager.execute_sql()`: изпълнява parameterized SELECT и връща резултата като `list[dict]`.
- `DatabaseManager.test_connection()`: проверява дали дадена връзка може да изпълни базов ping SELECT.
- `DatabaseManager.execute_domain_query()`: намира named domain query, слива default параметрите с подадените и връща резултата като `DataFrame`.
- `DatabaseManager.get_schema()`: връща compact schema от кеш или, ако е нужно, го refresh-ва от базата.
- `DatabaseManager._fetch_schema()`: избира специализирания schema fetch path според `db_type`.
- `DatabaseManager._fetch_sqlite_schema()`: чете SQLite schema през `sqlite_master` и `PRAGMA table_info`.
- `DatabaseManager._fetch_oracle_schema()`: чете Oracle schema през `all_tab_columns` или `user_tab_columns` и форматира типовете.
- `DatabaseManager._fetch_generic_schema()`: използва `SchemaFetcher` abstraction за Postgres/MySQL/DuckDB/ClickHouse.
- `DatabaseManager.refresh_schema()`: force refresh wrapper около `get_schema()`.
- `DatabaseManager.list_connections()`: връща имената на конфигурираните връзки.
- `DatabaseManager.get_connection_info()`: връща пълната конфигурация за една връзка.
- `DatabaseManager.get_default_connection()`: връща default connection-а.
- `DatabaseManager.add_connection()`: facade към config слоя за добавяне на връзка.
- `DatabaseManager.remove_connection()`: facade към config слоя, плюс чистене на schema cache-а за премахнатата връзка.
- `DatabaseManager.set_default_connection()`: facade за смяна на default connection-а.
- `DatabaseManager.update_schema_filter()`: обновява schema filter-а и инвалидира кеша за тази връзка.
- `DatabaseManager.list_domain_queries()`: връща само имената на domain queries за връзката.
- `DatabaseManager.get_domain_queries_info()`: връща user-facing метаданни за domain queries, включително примерен `tools.execute_domain_query(...)` call.
- `DatabaseManager.add_domain_query()`: facade за добавяне на named domain query.
- `DatabaseManager.remove_domain_query()`: facade за премахване на named domain query.
- `DatabaseManager.get_context_for_llm()`: връща пълния context, нужен за prompt-ове и tool/resource отговори.
- `DatabaseManager.shutdown()`: записва schema cache-а при shutdown.
- `DatabaseManager.__del__()`: best-effort destructor, който вика `shutdown()`.
- `get_manager()`: singleton factory за една споделена `DatabaseManager` инстанция в процеса.

### `banking_mcp/db/schema_fetcher.py`
Предназначение: abstraction слой за schema introspection по отделните database dialect-и.

Класове и функции:
- `ColumnInfo`: TypedDict shape за една колона в schema описанието.
- `TableInfo`: TypedDict shape за една таблица и нейните колони.
- `SchemaFetcher`: abstract base class за schema fetcher implementations.
- `SchemaFetcher.get_schema_query()`: абстрактен метод, който връща SQL за schema introspection.
- `SchemaFetcher.parse_schema_result()`: групира суровите row-ове по таблица и нормализира `nullable`.
- `SchemaFetcher.format_compact_schema()`: превръща таблиците в compact текстов формат `table: col(type), ...`.
- `OracleSchemaFetcher`: Oracle implementation на schema abstraction-а.
- `OracleSchemaFetcher.get_schema_query()`: връща Oracle query към `user_tab_columns`.
- `OracleSchemaFetcher.format_data_type()`: добавя размер/precision/scale към Oracle типовете там, където има смисъл.
- `SQLiteSchemaFetcher`: SQLite implementation; manager-ът има и специализиран path, защото SQLite няма `INFORMATION_SCHEMA`.
- `SQLiteSchemaFetcher.get_schema_query()`: връща SQLite query през `sqlite_master` и `pragma_table_info`.
- `PostgreSQLSchemaFetcher`: PostgreSQL implementation.
- `PostgreSQLSchemaFetcher.get_schema_query()`: връща query към `information_schema.columns`, изключвайки системните schema-и.
- `MySQLSchemaFetcher`: MySQL/MariaDB implementation.
- `MySQLSchemaFetcher.get_schema_query()`: връща query към `INFORMATION_SCHEMA.COLUMNS` за текущата база.
- `DuckDBSchemaFetcher`: DuckDB implementation.
- `DuckDBSchemaFetcher.get_schema_query()`: връща query към `information_schema.columns` за `main` schema.
- `ClickHouseSchemaFetcher`: ClickHouse implementation.
- `ClickHouseSchemaFetcher.get_schema_query()`: връща query към `system.columns` за текущата база.
- `get_schema_fetcher()`: registry lookup, който връща правилния fetcher по `db_type`.
- `get_supported_db_types()`: връща списък на всички поддържани database type aliases.

## `tests/`

### `tests/__init__.py`
Предназначение: package marker за test suite-а.

Функции: няма.

### `tests/unit/__init__.py`
Предназначение: package marker за unit test пакета.

Функции: няма.

### `tests/unit/test_tools_api.py`
Предназначение: тества `BankingToolsAPI` wrapper-а и error handling-а му.

Класове и функции:
- `_api()`: helper, който връща mock-нат `BankingToolsAPI` и съответния mock database manager.
- `test_execute_sql_query_returns_dataframe()`: проверява happy path-а на `execute_sql_query()`.
- `test_execute_sql_query_with_explicit_connection()`: проверява, че explicit connection override-ва default-a.
- `test_execute_sql_query_returns_empty_df_on_error()`: проверява, че при грешка се връща празен `DataFrame` и се попълва `last_error`.
- `test_execute_domain_query_passes_kwargs()`: проверява, че параметрите към domain query се подават коректно.
- `test_execute_domain_query_returns_empty_df_on_error()`: проверява error handling-а при липсваща/грешна domain query.
- `test_get_context_for_llm_delegates()`: проверява, че wrapper-ът делегира към manager-а.
- `test_last_error_resets_on_success()`: проверява, че успешен call чисти предишната грешка.
- `sample_txn_df()`: fixture с 6 примерни транзакции (вкл. NaN и whitespace описания) за enrichment тестовете.
- `test_classify_transactions_adds_expected_columns()`: проверява че 5-те нови колони се добавят.
- `test_classify_transactions_assigns_known_categories()`: пин-ва category codes за restaurant / salary / rent.
- `test_classify_transactions_marks_unclassified()`: NaN, whitespace и merchant-only → `unclassified: true`.
- `test_classify_transactions_does_not_mutate_input()`: input DataFrame не се променя.
- `test_classify_transactions_returns_empty_for_empty_input()`: empty input → empty output, без error.
- `test_classify_transactions_returns_empty_for_none_input()`: `None` input → empty output, без error.
- `test_classify_transactions_error_on_missing_description_column()`: missing column → empty + `last_error`.
- `test_classify_transactions_error_on_missing_direction_column()`: missing direction column → empty + `last_error`.
- `test_classify_transactions_respects_direction_column()`: per-row direction filtering работи (incoming филтрира outgoing-only keyword).
- `test_classify_transactions_unclassified_rate_is_measurable()`: `mean()` на `category_unclassified` дава очаквания QA сигнал.
- `test_classify_transactions_codes_are_only_from_taxonomy()`: hallucination-safe invariant — всеки върнат code ∈ known_codes.

### `tests/unit/test_server.py`
Предназначение: тества HTTP слоя и MCP path wiring-а на FastAPI приложението.

Класове и функции:
- `test_app_has_health_endpoint()`: проверява `/health` структурата и ключовите полета.
- `test_root_redirects_to_docs()`: проверява, че `/` отива към `/docs`.
- `test_favicon_returns_204()`: потвърждава тихия отговор за favicon заявки.
- `test_mcp_path_redirects_to_endpoint_path()`: проверява redirect-а от `/mcp`.
- `test_mcp_root_redirects_to_named_endpoint_path()`: проверява redirect-а от `/mcp/`.
- `test_public_mcp_endpoint_path_for_root()`: проверява path helper-а за root MCP path.
- `test_public_mcp_endpoint_path_for_named_path()`: проверява path helper-а за именуван MCP path.
- `test_settings_normalize_mcp_http_path()`: покрива нормализацията на `MCP_HTTP_PATH`.
- `test_no_api_routes_registered()`: гарантира, че старите REST `/api/*` route-ове са махнати.
- `test_app_has_no_mcp_api_key_setting()`: гарантира, че и старите REST auth settings вече не съществуват.

### `tests/unit/test_schema_fetcher.py`
Предназначение: тества schema fetcher abstraction-а и registry lookup-а за поддържаните бази.

Класове и функции:
- `test_supported_db_types_includes_all_drivers()`: проверява, че всички очаквани `db_type` alias-и са регистрирани.
- `test_get_schema_fetcher_returns_correct_class()`: проверява registry dispatch-а към правилния fetcher клас.
- `test_get_schema_fetcher_is_case_insensitive()`: проверява case-insensitive lookup-а.
- `test_get_schema_fetcher_raises_for_unknown()`: гарантира смислена грешка при непознат `db_type`.
- `test_oracle_format_data_type_varchar()`: проверява форматирането на Oracle string типове с размер.
- `test_oracle_format_data_type_number()`: проверява форматирането на Oracle `NUMBER`.
- `test_oracle_format_data_type_passthrough()`: проверява, че типове като `DATE` минават без промяна.
- `test_parse_schema_result_groups_by_table()`: проверява групирането на row-ове в `TableInfo`.
- `test_format_compact_schema_alphabetises_tables()`: проверява, че compact schema output-ът е стабилно сортиран.
- `test_get_schema_query_returns_select_for_each()`: проверява, че всеки fetcher връща SELECT query.

### `tests/unit/test_resources.py`
Предназначение: тества resource регистрацията и формата на resource отговорите.

Класове и функции:
- `FakeMCP`: минимален stub на MCP registry за resources.
- `FakeMCP.__init__()`: подготвя вътрешния речник `resources`.
- `FakeMCP.resource()`: имитира `@mcp.resource(...)` decorator factory.
- `FakeMCP.resource.decorator()`: записва регистрираната функция под нейния URI.
- `registered()`: pytest fixture, която регистрира resources върху fake MCP с mock database manager.
- `test_all_resources_registered()`: проверява, че всички resource URI-та (включително transaction-categories) са налични.
- `test_databases_resource_returns_json()`: проверява JSON формата и default connection-а.
- `test_schema_resource_uses_connection_arg()`: проверява, че schema resource ползва подадената връзка.
- `test_schema_resource_returns_error_string_on_failure()`: проверява fallback error текста.
- `test_domain_queries_resource()`: проверява JSON формата за domain queries resource-а.
- `test_domain_queries_resource_returns_error_json()`: проверява JSON error path-а.
- `test_dialects_resource_lists_all_supported()`: проверява, че dialect resource-ът покрива всички drivers.
- `test_transaction_categories_full_resource()`: проверява пълния taxonomy resource (locale, counts).
- `test_transaction_categories_incoming_resource()`: проверява филтрирания incoming view.
- `test_transaction_categories_outgoing_resource()`: проверява филтрирания outgoing view.
- `test_transaction_categories_payroll_patterns_resource()`: проверява payroll-patterns resource-а.

### `tests/unit/test_categories_loader.py`
Предназначение: тества `categories_loader` — cache, формат на payload-а, и Greek-free invariant.

Класове и функции:
- `_reset_cache()`: autouse fixture, която чисти `lru_cache` между тестовете.
- `test_counts_match_phase_1()`: проверява че counts са `{incoming: 55, outgoing: 122, payroll_patterns: 5}`.
- `test_locale_is_bulgarian()`: проверява `locale == "bg_BG"`.
- `test_no_greek_anywhere()`: regex обхожда payload-а и fail-ва ако намери Greek codepoint.
- `test_incoming_outgoing_split_is_clean()`: incoming/outgoing views са disjoint и сумата им е тоталът.
- `test_payroll_patterns_have_pattern_group_and_example()`: всеки pattern има двете полета и без NBSP.
- `test_load_is_cached()`: повторни извиквания връщат същия object.
- `test_every_category_has_full_code_and_main()`: invariant за схемата.
- `test_missing_data_file_raises()`: ясен `FileNotFoundError` при липсващ JSON.

### `tests/unit/test_classification.py`
Предназначение: тества keyword index, matcher и `classify_description` tool с golden fixture.

Класове и функции:
- `GOLDEN_CASES`: 17 примера (description → expected_code → direction) покриващи incoming income/financing + outgoing food/leisure/home.
- `_reset_caches()`: autouse fixture, чисти и `categories_loader` и `get_index` кеша между тестовете.
- `_FakeMCP`: stub за MCP tool registry.
- `test_index_is_cached_singleton()`: `get_index()` връща същия object.
- `test_index_contains_all_taxonomy_codes()`: `KeywordIndex.known_codes` покрива пълната таксономия.
- `test_payroll_pattern_compiles_to_digit_regex()`: `PAYROLL_MM_YYYY` → regex с `\d{2}_\d{4}`.
- `test_payroll_pattern_handles_empty_input()`: празен pattern → `None`.
- `test_top3_contains_expected[...]`: parametrized — за всеки golden case top-3 трябва да съдържа expected code.
- `test_top1_precision_meets_threshold()`: top-1 ≥ 80% precision invariant.
- `test_classifier_never_invents_a_code()`: никой returned code не е извън loaded таксономията.
- `test_unclassified_for_empty_input()`: empty/whitespace input → `unclassified: true`.
- `test_unclassified_for_merchant_only_description()`: pin-ва документираното ограничение (merchant-only описания са unclassified — Phase 6 follow-up).
- `test_direction_filter_excludes_other_side()`: `direction="incoming"` не връща outgoing категории.
- `test_invalid_direction_raises()`: грешен direction → `ValueError`.
- `test_payroll_pattern_boosts_salary_even_without_keyword()`: bare `PAYROLL_03_2026` → top-1 е code `001001001000`.
- `test_longer_keyword_outranks_shorter_overlap()`: 'ипотечен кредит' побеждава 'ипотечен' при overlap.
- `test_classify_description_tool_returns_valid_json()`: end-to-end през MCP tool surface.
- `test_classify_description_tool_clamps_top_k()`: `top_k=999` се clamp-ва до 10.
- `test_classify_description_tool_returns_error_for_bad_direction()`: грешен direction → JSON с `error` ключ.

### `tests/unit/test_prompts.py`
Предназначение: тества prompt регистрацията и съдържанието на генерираните banking prompt-и.

Класове и функции:
- `FakeMCP`: минимален stub на MCP prompt registry.
- `FakeMCP.__init__()`: подготвя речника `prompts`.
- `FakeMCP.prompt()`: имитира `@mcp.prompt(...)` decorator factory.
- `FakeMCP.prompt.decorator()`: записва prompt функцията под нейното име.
- `registered()`: fixture, която регистрира prompt-овете върху fake MCP с mock context.
- `test_all_prompts_registered()`: проверява, че са регистрирани всички осем banking prompt-а (5 базови + 3 от Phase 5).
- `test_database_overview_includes_schema_and_dialect()`: проверява, че overview prompt-ът инжектира schema и dialect.
- `test_database_overview_uses_default_when_no_arg()`: проверява default connection поведението.
- `test_database_overview_uses_explicit_connection()`: проверява explicit connection path-а.
- `test_analyze_table_includes_table_name()`: проверява, че prompt-ът за таблица инжектира правилното име.
- `test_compare_periods_renders_metric_and_dates()`: проверява, че prompt-ът съдържа метриката и датните граници.
- `test_data_quality_check_targets_table()`: проверява, че DQ prompt-ът се фокусира върху подадената таблица.
- `test_sql_helper_quotes_question()`: проверява, че natural-language въпросът се вгражда коректно.
- `test_prompt_handles_missing_connection_gracefully()`: проверява graceful fallback при липсваща default връзка.
- `test_prompt_handles_context_failure()`: проверява fallback текста при грешка в `get_context_for_llm()`.
- `test_categorize_transaction_quotes_description_and_lists_tool()`: проверява quoted description, tool reference, споменаване на `unclassified`, `payroll_pattern_hit` и salary code.
- `test_categorize_transaction_defaults_to_auto_direction()`: default direction filter = `auto`.
- `test_categorize_transaction_respects_explicit_direction()`: explicit direction override работи.
- `test_spending_breakdown_includes_schema_and_tool_call()`: customer + dates plumbed, schema rendered, `tools.classify_transactions` instruction, category columns named, `last_error` контракт.
- `test_spending_breakdown_uses_default_connection()`: ползва default connection при празен аргумент.
- `test_income_pattern_analysis_references_salary_code_and_heuristic()`: код `001001001000`, consecutive-months heuristic, и двата tool references.
- `test_income_pattern_analysis_default_months_is_six()`: default lookback = 6 месеца.
- `test_phase5_prompts_render_when_no_connection()`: graceful "no connection configured" fallback за новите prompt-и.

### `tests/unit/test_redaction.py`
Предназначение: тества PII redaction правилата.

Класове и функции:
- `test_redact_returns_empty_for_empty_input()`: проверява празен/`None` input.
- `test_redact_email_in_quotes()`: проверява redaction на email в SQL literal.
- `test_redact_phone_in_quotes()`: проверява redaction на телефонен номер.
- `test_redact_long_string_literal()`: проверява redaction на дълъг текстов literal.
- `test_redact_does_not_touch_short_literals()`: пази късите и невинни string literal-и непроменени.
- `test_redact_does_not_touch_numeric_ids()`: гарантира, че числовите ID-та не се маскират.
- `test_redact_handles_multiple_patterns()`: проверява едновременна поява на няколко чувствителни патерна.
- `test_redact_is_case_insensitive_for_email()`: проверява case-insensitive поведението при email-и.

### `tests/unit/test_mcp_tools.py`
Предназначение: тества MCP tool регистрацията и поведението на `list_databases`, `get_database_context` и `execute_code`.

Класове и функции:
- `FakeMCP`: минимален stub на MCP tool registry.
- `FakeMCP.__init__()`: подготвя речника `tools`.
- `FakeMCP.tool()`: имитира `@mcp.tool(...)` decorator factory.
- `FakeMCP.tool.decorator()`: записва tool функцията под нейното име.
- `registered_tools()`: fixture, която регистрира tool-овете върху fake MCP с mock database manager.
- `test_three_tools_registered()`: проверява, че са налични точно трите очаквани tool-а.
- `test_list_databases_returns_json()`: проверява JSON формата на `list_databases()`.
- `test_get_database_context_uses_default_when_empty()`: проверява default connection path-а за context tool-а.
- `test_get_database_context_explicit_connection()`: проверява explicit connection path-а.
- `test_get_database_context_handles_no_default()`: проверява грешката при липса на default connection.
- `test_get_database_context_returns_error_on_exception()`: проверява JSON error path-а.
- `test_execute_code_success()`: проверява успешен sandbox call, който връща сериализиран резултат.
- `test_execute_code_error_returns_error_message()`: проверява, че забранен import води до user-facing error text.

### `tests/unit/test_executor.py`
Предназначение: тества RestrictedPython sandbox-а и guard логиката му.

Класове и функции:
- `executor()`: fixture, която връща `CodeExecutor` с mock database manager.
- `test_execute_simple_assignment()`: проверява базово изпълнение и връщане на `result`.
- `test_execute_uses_pandas()`: проверява, че `pd` е достъпен вътре в sandbox-а.
- `test_execute_uses_tools_object()`: проверява използването на `tools.execute_sql_query()` от sandbox кода.
- `test_execute_blocks_forbidden_imports()`: проверява, че директните import-и са блокирани.
- `test_execute_blocks_forbidden_from_imports()`: проверява блокирането на `from x import y`.
- `test_execute_blocks_importlib_bypass()`: проверява, че няма обход през `importlib`.
- `test_execute_returns_error_when_result_missing()`: проверява, че код без `result` връща смислена грешка.
- `test_execute_captures_print_as_result()`: проверява fallback-а към `printed` изход.
- `test_execute_normalizes_smart_quotes()`: проверява нормализацията на smart quotes.
- `test_execute_returns_runtime_error_message()`: проверява error wrapping-а при runtime exception.
- `test_execute_supports_loops_and_unpacking()`: проверява, че цикли и unpacking работят в sandbox-а.
- `test_execute_blocks_syntax_errors()`: проверява syntax error path-а.

### `tests/unit/test_db_config.py`
Предназначение: тества CRUD поведението на config слоя и парсинга на параметри.

Класове и функции:
- `isolated_config()`: fixture, която насочва `CONFIG_FILE` към временен JSON файл.
- `test_default_config_is_banking_schemaracle()`: проверява bootstrap Oracle config-а за `scards`.
- `test_default_config_has_only_scards()`: проверява, че default config-ът регистрира само `scards`.
- `test_load_config_creates_default_when_missing()`: проверява auto-bootstrap при липсващ config файл.
- `test_load_config_invalid_json_raises_and_preserves_file()`: проверява правилната грешка и че файлът не се презаписва при невалиден JSON.
- `test_resolve_env_vars_substitutes()`: проверява env substitution в DSN низ.
- `test_resolve_env_vars_raises_on_missing()`: проверява грешката при липсваща env променлива.
- `test_add_remove_connection()`: покрива add/remove lifecycle-а на връзка.
- `test_add_connection_rejects_duplicate()`: гарантира, че duplicate имена се отказват.
- `test_set_default_connection()`: проверява смяната на default connection-а.
- `test_set_default_connection_unknown_raises()`: проверява грешката при неизвестно име.
- `test_filter_tables_include()`: проверява include wildcard филтъра.
- `test_filter_tables_exclude()`: проверява exclude wildcard филтъра.
- `test_domain_query_crud()`: покрива add/get/remove на domain query.
- `test_legacy_type_key_normalized()`: проверява автоматичната миграция `type -> db_type`.
- `test_parse_compact_params_list_format()`: проверява legacy list формата за параметри.
- `test_parse_compact_params_string_format()`: проверява compact string формата.
- `test_parse_compact_params_empty()`: проверява празни входове.

### `tests/unit/test_db_manager.py`
Предназначение: тества `DatabaseManager` върху временна SQLite база, включително validation, schema и LLM context.

Класове и функции:
- `isolated_db()`: fixture, която създава временна SQLite база, временен config и reset-ва singleton-а.
- `test_query_returns_dataframe()`: проверява, че `query()` връща редовете като `DataFrame`.
- `test_query_validates_select_only()`: проверява блокирането на mutating SQL.
- `test_query_allows_keywords_inside_string_literals()`: пази валидни string literal-и, съдържащи забранени думи.
- `test_query_rejects_multiple_statements()`: проверява защитата срещу multiple statements.
- `test_query_rejects_non_select_calls()`: проверява блокирането на `CALL` и `REPLACE`.
- `test_test_connection_works()`: проверява happy path-а на connection ping-а.
- `test_test_connection_returns_false_for_unknown()`: проверява поведението за непозната връзка.
- `test_get_schema_returns_compact_format()`: проверява формата на compact schema output-а.
- `test_schema_cache_persists()`: проверява, че schema cache-ът се попълва.
- `test_execute_domain_query_no_params()`: проверява изпълнение на domain query без параметри.
- `test_execute_domain_query_with_params()`: проверява parameterized domain query.
- `test_execute_domain_query_unknown_raises()`: проверява смислената грешка при липсваща domain query.
- `test_get_context_for_llm()`: проверява пълния контекст за LLM.
- `test_get_context_for_llm_normalizes_db_type()`: проверява, че `db_type` се нормализира до lowercase и взема правилния dialect hint.
- `test_list_connections()`: проверява списъка с връзки.
- `test_singleton_returns_same_instance()`: гарантира singleton поведението на `get_manager()`.

### `tests/unit/test_multi_db_drivers.py`
Предназначение: тества driver opener-ите и dispatch логиката без реални външни бази чрез fake modules и fake connections.

Класове и функции:
- `test_parse_url_dsn_basic()`: проверява базовото разпадане на URL-style DSN.
- `test_parse_url_dsn_url_decodes_password()`: проверява URL decode на парола.
- `test_parse_url_dsn_handles_missing_pieces()`: проверява липсващи user/password/port части.
- `test_open_postgres_uses_psycopg()`: проверява happy path-а през `psycopg`.
- `test_open_postgres_uses_psycopg.fake_connect()`: локален stub, който пази подадения DSN и връща fake connection.
- `test_open_postgres_falls_back_to_psycopg2()`: проверява fallback-а към `psycopg2`.
- `test_open_postgres_falls_back_to_psycopg2.fake_connect()`: локален stub за fallback path-а.
- `test_open_postgres_raises_when_no_driver()`: проверява грешката при липсващ PostgreSQL драйвер.
- `test_open_mysql_parses_url_and_calls_pymysql()`: проверява MySQL parsing-а и аргументите към `pymysql.connect`.
- `test_open_mysql_parses_url_and_calls_pymysql.fake_connect()`: локален stub за събиране на подадените kwargs.
- `test_open_mysql_uses_default_port_when_omitted()`: проверява default port 3306.
- `test_open_mysql_raises_when_driver_missing()`: проверява грешката при липсващ `pymysql`.
- `test_open_duckdb_in_memory()`: проверява in-memory DuckDB path-а.
- `test_open_duckdb_in_memory.fake_connect()`: локален stub за capture на in-memory connect аргументите.
- `test_open_duckdb_file_uses_read_only()`: проверява, че file mode е `read_only=True`.
- `test_open_duckdb_raises_when_driver_missing()`: проверява грешката при липсващ `duckdb`.
- `test_open_clickhouse_parses_url_and_calls_get_client()`: проверява ClickHouse parsing-а и аргументите към `get_client`.
- `test_open_clickhouse_parses_url_and_calls_get_client.fake_get_client()`: локален stub за capture на client kwargs.
- `test_open_clickhouse_defaults()`: проверява default host/port/user/database стойностите.
- `test_open_clickhouse_raises_when_driver_missing()`: проверява грешката при липсващ ClickHouse драйвер.
- `test_open_connection_dispatches_to_correct_opener()`: проверява top-level dispatch-а по `db_type`.
- `test_open_connection_rejects_unknown_db_type()`: проверява грешката при неподдържан `db_type`.
- `_FakeCursor`: helper cursor за симулация на DB-API и DuckDB cursor поведение.
- `_FakeCursor.__init__()`: инициализира fake `description`, rows и списък с изпълнени заявки.
- `_FakeCursor.execute()`: записва изпълнената SQL заявка и параметрите.
- `_FakeCursor.fetchall()`: връща предварително подготвените rows.
- `_FakeCursor.fetchdf()`: helper за DuckDB-подобен API.
- `_FakeCursor.close()`: no-op close, за да прилича на истински cursor.
- `_FakeDBAPIConn`: helper connection за DB-API style драйвери.
- `_FakeDBAPIConn.__init__()`: пази cursor инстанцията.
- `_FakeDBAPIConn.cursor()`: връща fake cursor-а.
- `_FakeDuckDBConn`: helper connection, в който `execute()` връща cursor директно.
- `_FakeDuckDBConn.__init__()`: пази columns/rows и последната SQL заявка.
- `_FakeDuckDBConn.execute()`: връща fake cursor и пази SQL-а.
- `_FakeClickHouseClient`: helper client за ClickHouse result обект.
- `_FakeClickHouseClient.__init__()`: пази fake column names, rows и последната SQL заявка.
- `_FakeClickHouseClient.query()`: връща ClickHouse-подобен result object.
- `test_run_select_postgres_path()`: проверява `_run_select()` при DB-API style PostgreSQL курсор.
- `test_run_select_mysql_path_with_params()`: проверява `_run_select()` с параметри за MySQL path-а.
- `test_run_select_duckdb_path()`: проверява DuckDB branch-а в `_run_select()`.
- `test_run_select_clickhouse_path()`: проверява ClickHouse branch-а в `_run_select()`.
- `test_ping_sql_dialect_selection()`: проверява ping query-то за различните диалекти.

### `tests/unit/test_oracle_support.py`
Предназначение: тества Oracle-specific поведението без реална Oracle инстанция.

Класове и функции:
- `FakeOracleCursor`: helper cursor за Oracle-style execute/fetch lifecycle.
- `FakeOracleCursor.__init__()`: пази редовете, description-а и историята на изпълнените заявки.
- `FakeOracleCursor.execute()`: записва SQL-а и параметрите.
- `FakeOracleCursor.fetchall()`: връща предварително зададените rows.
- `FakeOracleCursor.close()`: no-op close.
- `FakeOracleConnection`: helper connection, която връща `FakeOracleCursor`.
- `FakeOracleConnection.__init__()`: инициализира курсора и close флага.
- `FakeOracleConnection.cursor()`: връща fake Oracle cursor-а.
- `FakeOracleConnection.close()`: маркира връзката като затворена.
- `test_open_connection_uses_oracle_settings_and_schema()`: проверява Oracle connect аргументите и `ALTER SESSION SET CURRENT_SCHEMA`.
- `test_open_connection_uses_oracle_settings_and_schema.fake_connect()`: локален stub, който capture-ва kwargs към `oracledb.connect`.
- `test_test_connection_uses_dual_for_oracle()`: проверява Oracle ping-а чрез `SELECT 1 FROM DUAL`.
- `test_execute_sql_returns_rows_for_oracle()`: проверява Oracle branch-а на `execute_sql()`.
- `test_fetch_oracle_schema_uppercases_plain_owner()`: проверява, че Oracle owner/schema името се upper-case-ва коректно.
- `test_fetch_oracle_schema_uppercases_plain_owner.fake_run_select()`: локален stub за capture на bind параметрите при schema fetch.

### `tests/unit/test_audit_log_query.py`
Предназначение: тества audit logger-а, queue drain-а, redaction-а и поведението при disabled audit.

Класове и функции:
- `_drain_queue()`: helper, който изчаква writer thread-ът да източи queue-то.
- `_read_log_records()`: helper, който чете JSONL audit файла и го връща като списък от dict-ове.
- `test_log_query_writes_success_record()`: проверява записването на успешен query audit record.
- `test_log_query_redacts_email_in_query()`: проверява redaction-а на email вътре в записаната query.
- `test_log_query_records_error()`: проверява error audit record-а.
- `test_log_query_skipped_when_audit_disabled()`: проверява, че при изключен audit не се пише файл и не се пуска thread.
- `test_stop_drains_pending_records()`: проверява, че `stop()` flush-ва и чака всички натрупани записи.
