# Rust-Only Ultimate Plan (10/10)

Дата: 2026-06-02
Область: `\\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy`

## 1) Цели и жесткие ограничения

1. Привести систему к архитектуре `Rust-first / Rust-only`, где вся бизнес-логика, оркестрация и recovery реализованы на Rust.
2. Исключить `.sh`/`.ps1` из runtime-логики.  
   Допустимое исключение: минимальный bootstrap для Magisk (`service.sh`) только для старта одного Rust-бинаря.
3. Обеспечить устойчивость после:
   - перезагрузки телефона;
   - ручного airplane on/off;
   - программного airplane-bounce из API.
4. Гарантировать воспроизводимость: новый девайс поднимается по детерминированной процедуре без ручных «костылей».

## 2) Целевая архитектура (модельная, послойная)

### L0. Bootstrap Layer (минимально неизбежный)
- `service.sh` только запускает `runtime-supervisor` и пишет PID.
- Никаких проверок маршрутов, WireGuard, retry, rotate, парсинга или бизнес-правил в shell.

### L1. Runtime Supervisor (Rust)
- Один долгоживущий процесс (`runtime-supervisor`) как оркестратор:
  - контроль жизненного цикла `host-daemon` и `sing-box`;
  - проверка route/vpn/proxy readiness;
  - автоматическое восстановление после сетевых флапов;
  - state machine с таймерами и backoff.

### L2. Domain State Machine (Rust, чистая модель)
- Отдельный модуль domain-логики без side-effects:
  - входы: события probes, rotate, network-change, boot, process-exit;
  - выходы: команды действий (repair route, restart proxy, rotate strategy, quarantine).
- Строгое разделение:
  - `domain` (pure);
  - `application` (orchestration);
  - `infrastructure` (adb/android/system calls).

### L3. Device Control Adapters (Rust)
- Typed adapters вместо shell-скриптов:
  - netlink/ip route;
  - Android settings/am/cmd;
  - process supervisor;
  - health/readiness probes.

### L4. Control Plane / API Integration
- Контракты в `proxy-core` как единый source-of-truth:
  - readiness model;
  - degradation reason taxonomy;
  - recovery intent.

### L5. Ops CLI (Rust)
- Замена `scripts/device/*.ps1` на `operator-cli`/новый `device-cli`:
  - install;
  - verify;
  - rotate;
  - rollback;
  - fleet check.

## 3) План миграции по этапам

## Этап A. Freeze и инвентаризация (1 день)
- Зафиксировать текущие контракты API/health/job.
- Полный список shell/PowerShell обязанностей и зависимостей.
- Определить границы «допустимого shell».

Критерий выхода:
- Документирован map: `feature -> current implementation -> target Rust module`.

## Этап B. Supervisor Core (2-3 дня)
- Создать crate `services/runtime-supervisor`.
- Реализовать:
  - process manager;
  - event loop;
  - structured logging/metrics;
  - persistence snapshot state (последнее стабильное состояние).

Критерий выхода:
- Supervisor поднимает/перезапускает `host-daemon` и `sing-box` без shell-логики.

## Этап C. State Machine 10/10 (2-3 дня)
- Перенести policy в чистый доменный автомат:
  - состояния: `booting`, `waiting_wireguard`, `waiting_cellular`, `starting_proxy`, `healthy`, `quarantined`, `recovering`;
  - события и guard conditions;
  - deterministic transitions + idempotent actions.
- Ввести contract-tests на переходы.

Критерий выхода:
- 100% deterministic replay на recorded event-trace.

## Этап D. Recovery Engine (2 дня)
- Реализовать в Rust:
  - route repair (main table + policy tables);
  - safe restart sequencing;
  - adaptive backoff;
  - quarantine with controlled exit criteria.
- Убрать восстановление из `service.sh`/`rotate-ip.ps1`.

Критерий выхода:
- После network flap система возвращается в `healthy/serving` без ручного вмешательства.

## Этап E. Rotate Pipeline (1-2 дня)
- Встроить rotate orchestration в Rust CLI/API:
  - start job;
  - monitor job;
  - post-rotate convergence check;
  - SLA timeout + rollback action.

Критерий выхода:
- `rotate` стабильно проходит N прогонов подряд с требуемой сменой IP (если оператор допускает).

## Этап F. Rust Ops CLI и деплой (2 дня)
- Заменить `install-device.ps1`, `verify-device.ps1`, `rotate-ip.ps1`, `rollback-device.ps1` на Rust-команды.
- Оставить PowerShell только как thin wrapper (опционально) или убрать полностью.

Критерий выхода:
- One-command onboarding нового устройства через Rust CLI.

## Этап G. Hardening + QA Matrix (2-3 дня)
- Тест-матрица:
  - 20x reboot;
  - 30x manual airplane;
  - 30x API airplane bounce;
  - длительный soak-test (6-12 часов);
  - burst proxy probes (1000+ запросов).
- SLO/SLI:
  - recovery time;
  - proxy availability;
  - false quarantine rate.

Критерий выхода:
- Прохождение матрицы по порогам качества (см. раздел 6).

## 4) Библиотеки Rust (production-grade профиль)

Базовый стек:
- async/runtime: `tokio`
- API: `axum`
- HTTP client: `reqwest`
- serialization: `serde`, `serde_json`
- IDs/time: `uuid`, `time`/`chrono`
- errors: `thiserror`, `anyhow`
- observability: `tracing`, `tracing-subscriber`
- retry/backoff: `backoff` (или собственный policy layer)
- tests: `proptest` (для state-machine свойств), `rstest`

Опционально:
- process supervision helpers;
- netlink crates для route операций (если стабильны для Android target), иначе изолированный command adapter с жесткими контрактами и тестами.

## 5) Что удаляем/упрощаем

1. Толстая логика из `deploy/device-runtime/module/service.sh`.
2. Runtime/recovery из `.ps1`.
3. Разрозненные «ручные» последовательности действий без модельной фиксации.

## 6) Критерии 10/10

Архитектура:
- Четкое разделение `domain/application/infrastructure`.
- Все переходы состояния формализованы и тестируются.
- Idempotency по recovery/rotate операциям.

Надежность:
- `>= 99.5%` успешных автоматических восстановлений после airplane/reboot в тест-матрице.
- median recovery `< 20s`, p95 `< 60s`.
- proxy flap rate минимизирован, без длительных зависаний в `waiting_cellular`.

Операционка:
- Полный onboarding устройства одной Rust-командой.
- Наблюдаемость: структурные логи, reason-codes, timeline событий.
- Воспроизводимость релиза: фиксированные артефакты, checksums, versioned deployment.

## 7) Риски и контрмеры

Риск 1: Android OEM ограничения на фоновые действия VPN.  
Контрмера: явная стратегия fallback и строгие readiness критерии; всегда-on VPN policy where supported.

Риск 2: нестабильность route table после airplane.  
Контрмера: supervisor-level route reconciliation (main + policy tables), periodic verification loop.

Риск 3: hidden drift между бинарем на устройстве и исходниками.  
Контрмера: reproducible build, binary fingerprint enforcement, deployment guard.

## 8) План выполнения (порядок коммитов)

1. `feat(supervisor): scaffold runtime-supervisor`
2. `feat(domain): formal state machine + transition tests`
3. `feat(recovery): route/vpn/proxy convergence engine`
4. `feat(cli): rust install/verify/rotate/rollback`
5. `refactor(runtime): shrink service.sh to bootstrap-only`
6. `test(e2e): reboot/airplane/proxy soak matrix`
7. `docs(ops): runbooks + SLO + onboarding`

## 9) Definition of Done

- Runtime logic: Rust-only.
- Shell: только минимальный bootstrap, без бизнес-логики.
- Прохождение полной стресс-матрицы.
- Документированные runbooks для масштабирования на новые устройства.

