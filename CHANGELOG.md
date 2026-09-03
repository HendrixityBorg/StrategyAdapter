# 变更记录

本项目遵循语义化版本。Contract 字段和机器标识符保持英文，评审说明采用中文。

## Unreleased

- JSON Schema 改为自包含 Draft 2020-12 文档，并用标准验证器对 22 类真实文档执行无网络验证。
- 统一策略目录入口增加显式 `--engine`，可直接选择 Reference、Backtrader 或 NautilusTrader，禁止隐式替换。
- 增加规则、监督学习和强化学习三类外部策略包的统一入口端到端验证。

## 1.1.0 — 2026-09-03

- 为 `ExecutionPlan` 和 `RunBundle` 增加可选策略源码证据，绑定策略包源码与受信运行时源码树；当前完整验证要求新生成的运行证据包含该文件。
- 增加显式、无损、可逆的 `symbol.map.v1`，并证明它可与需授权的 `bar.resample.v1` 组合执行。
- 明确 `StrategyManifest.resources.sandbox` 是最低隔离要求；运行策略试图降低该要求时返回 `SANDBOX_POLICY_DOWNGRADE`。
- 增加 `psrc sandbox run`，把单个外部策略包实际送入无网络、只读根文件系统、非 root 的 Docker 边界。
- 增加 `psrc author audit`，提供论文规格到策略 manifest 的确定性、机器可读审计入口。
- 增加 Contract `1.0.0` 文档向后解析回归测试；本次仅新增可选字段、错误码和转换标识符，因此保持 major 版本不变。

## 1.0.0 — 2026-09-02

- 首次公开稳定 Contract、18 个策略包、三套可执行引擎、结构化失败证据及严格容器验证。
