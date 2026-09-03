# 论文策略运行时契约（PSRC）

PSRC 是一套公开、版本化、引擎中立的契约，用于把论文中的交易策略转化为可复现的训练、推理与回测运行。本仓库面向 SingularityX 挑战 `SX-CH-003` 的公开任务范围，提供可运行实现、需求映射和可独立复核的证据；最终评价由评审方作出。

本项目的输入是已经形成的策略包或结构化 `PaperStrategySpec`，不直接解析 PDF、HTML、arXiv 页面或论文正文，也不负责自动生成策略代码。论文理解和代码生成属于可选上游；PSRC 负责其输出进入真实训练、推理与回测环境之后的契约、隔离、执行和证据。

这里的“可适配”不是假设每个策略都能在每个引擎上运行。策略代码加载前，编译器会核对四份不可变声明：

1. `StrategyManifest`：策略的数据、生命周期、动作与资源要求；
2. `DatasetManifest`：实际提供的字段、标的、粒度及内容哈希；
3. `EngineCapabilities`：所选适配器能够如实提供的执行语义；
4. `RunPolicy`：要求的隔离级别及明确获准的数据转换。

编译结果只能是可审计的 `ExecutionPlan` 或机器可读的 `ContractError`。字段、引擎、模型和沙箱模式均不得静默替换。

代码标识符、枚举、JSON Schema 字段及错误码保留英文，保证公开机器契约稳定并便于跨语言、跨引擎集成；面向开发者和评审者的文档、Strategy Card 与 HTML 报告采用中文。

## 一键复现与验证

本地验证需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)：

```bash
make verify
```

该命令基于锁文件安装环境，执行 Ruff、严格 mypy、JSON Schema 导出、18 个策略包生成、完整测试、18 条训练/推理/回测链路、8 类强制失败场景、兼容转换闭环和 3 个原生引擎差分运行，最后执行开发环境预检。成功时末行如下：

```text
Development preflight passed; report: reports/generated/acceptance-report.json
```

`make verify` 报告中的 `verification_scope` 为 `development_preflight`，不构成严格隔离证据。需要验证操作系统级隔离时使用 Docker：

```bash
make verify-container
```

此命令在同一个受限容器中执行全部质量门禁、生成物漂移检查、测试、示例和带 `--require-strict` 的证据判定。容器以非 root 用户运行，禁用网络，根文件系统只读，移除全部 capabilities，启用 `no-new-privileges`，限制 CPU、内存和 PID，并使用 `noexec` 临时文件系统。进程证明还要求真实容器标记；严格隔离不可用时返回 `SANDBOX_UNAVAILABLE`，不会退回宿主机执行。

GitHub Actions 同时运行开发环境和严格容器验证，并将两类完整证据分别保留为 30 天可下载 artifact。

## 已实现范围

- Contract `1.1.0`：策略、数据、行情事件、账户、动作、训练、产物、决策、日志、运行输入证据、策略源码证据、执行计划、聚合 bundle、成功/失败报告和 Agent 审计共 22 份公开 JSON Schema；
- 规则、监督学习和强化学习三类确定性生命周期；
- 18 个有实质差异的策略示例，每类 6 个，覆盖分钟/日线、配对、截面、L1、L2 与执行任务；
- 12 个可训练策略均执行训练、内容寻址保存、完整性校验重载，再进入推理/回测；
- 18 个目录均可通过 `psrc run --strategy-dir` 独立执行；manifest、输入和源码哈希先验证、能力先协商、源码先扫描，之后才允许 import；
- 端到端测试会动态组装规则、监督学习和强化学习三类外部策略包，其源码不引用内置 strategy catalog，仍通过同一目录入口完成运行；
- 每份策略运行计划均绑定包源码和受信运行时源码树哈希，Bundle 独立保存逐文件策略源码证据；
- 显式、可禁用且实际执行的兼容转换，包括无损标的映射与具有源/有效事件哈希和数量证据的 bar 重采样；
- 字段、时间周期、标的映射、模型、非法动作、非法订单、训练和回测 8 类结构化失败证据；
- 确定性参考引擎，以及真实 Backtrader、NautilusTrader 适配器；
- LEAN、Qlib、vn.py 的保守能力画像，仅用于兼容性分析，不冒充已运行适配器；
- 可选上游 Agent 交接边界：`psrc author audit` 对已有结构化草稿提供确定性审计，模型结构上固定为无运行时权限；
- JSON `RunBundle` 与中文 HTML 报告，记录声明、源/有效实际输入、生命周期、训练/推理日志、订单、成交、账户、内容寻址产物、假设和错误。

## 架构

```text
项目外上游（可选）：论文 -> 解析/生成 Agent -> 策略包或 PaperStrategySpec
                                                   |
----------------------------- PSRC 边界 -----------------------------
                                                   |
                                      人工复核 / 确定性审计
                                                   |
StrategyManifest + DatasetManifest + EngineCapabilities + RunPolicy
                           |
                       契约编译器
                       /       \
              ContractError   ExecutionPlan
                                    |
                            隔离的统一运行时
                       训练 -> 保存 -> 重载 -> 推理
                                    |
                   Reference / Backtrader / Nautilus
                                    |
                          JSON + 中文 HTML RunBundle
```

Agent 输出不能绕过 Schema 校验、能力协商或沙箱。引擎专属字段只能放在反向域名扩展命名空间中，稳定核心不绑定供应商。是否适配由契约协商决定，而不是靠 Agent 猜测或运行时补丁。

## 常用命令

```bash
uv sync --frozen --extra dev --extra adapters
uv run psrc schema export --output schemas/generated
uv run psrc package export --output strategies
uv run psrc run --strategy-dir strategies/rule.sma_cross --output runs/package-sma
uv run psrc run --strategy-dir strategies/rule.sma_cross \
  --engine backtrader --output runs/package-sma-backtrader
uv run psrc sandbox run --strategy-dir strategies/rule.sma_cross \
  --engine nautilus-trader --output runs/strict-sma-nautilus
uv run psrc author audit --spec paper-spec.json \
  --manifest strategies/rule.sma_cross/strategy.yaml --output agent-audit.json
uv run psrc demo all --output runs/all
uv run psrc demo failures --output runs/failures
uv run psrc demo adapters --output runs/adapters
uv run psrc demo compatibility --output runs/compatibility
uv run psrc verify --matrix ACCEPTANCE_MATRIX.yaml \
  --evidence-root reports/generated \
  --output reports/generated/acceptance-report.json
```

`psrc run --engine` 明确选择 `reference`、`backtrader` 或 `nautilus-trader`，默认为 `reference`。选定引擎的数据、动作或能力不足时编译阶段直接返回结构化错误，不会改用参考引擎。`psrc sandbox run` 是宿主机发起的单策略严格 Docker 入口，会把同一引擎选择送入容器。直接运行或批量运行需要拒绝开发模式时增加 `--require-strict`；如果真实容器控制无法证明，命令返回 `SANDBOX_UNAVAILABLE`，不会降级执行。策略 manifest 的 `resources.sandbox` 是最低要求，`RunPolicy` 低于它时返回 `SANDBOX_POLICY_DOWNGRADE`。

全部 22 份 JSON Schema 声明 Draft 2020-12，内部引用使用自包含的 `#/$defs/...`。默认验证门禁会用标准 `jsonschema` 实现对 22 类真实文档逐份验证，不需要网络或外部 Schema registry。

证据验证器不根据矩阵中的说明性文字判定结果，而是从实际生成物中核验 Schema、策略数量与差异度、训练产物、失败码、原生引擎、测试、覆盖率、沙箱控制以及证据运行模式。

## 仓库导航

- `spec/`：Contract v1、真实运行接口、生命周期、错误、兼容性、安全、Agent 与版本规范；
- `schemas/generated/`：具有稳定 `$id` 的机器契约；
- `src/psrc/`：SDK、编译器、运行时、策略、适配器、沙箱和证据工具；
- `strategies/`：18 个可移动执行包，包含 manifest、源码入口、精确输入、训练请求和中文 Strategy Card；
- `engine_profiles/`：可执行和仅画像两类引擎能力声明；
- `tests/`：单元、属性、负向、集成、适配器、沙箱和端到端测试；
- `docs/`：架构、适配器、复现、策略覆盖及需求符合性审计。

评审建议依次阅读 [需求符合性审计](docs/acceptance-audit.md)、[架构与语义边界](docs/architecture.md)、[引擎适配器指南](docs/adapter-guide.md) 和 [复现与证据审阅](docs/reproduction.md)。

## 范围与许可

本项目是研究基础设施及合成策略演示，不构成投资建议，也不代表对生产交易系统或第三方引擎的生产认证。项目采用 Apache-2.0；详见 `LICENSE`。可选第三方引擎保留各自许可证。
