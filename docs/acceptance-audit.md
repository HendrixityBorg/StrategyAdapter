# 需求符合性审计

本文把公开任务要求映射到可执行证据，避免用“代码看起来完整”替代“结果可以复现”。`psrc verify` 只判断仓库内技术检查是否通过，不代表或替代主办方的档位认定。

## 要求—实现—证据

| 公开任务要求 | 当前实现 | 可执行证据 |
| --- | --- | --- |
| 完整工程与一键复现 | Python 3.12、`uv.lock`、Makefile、摘要固定 Docker 基础镜像、合成数据 | `make verify`、`make verify-container`、CI 可下载证据 artifact |
| 公开、稳定、可扩展 Contract | Contract `1.1.0`、22 份稳定 `$id` JSON Schema、严格未知字段、反向域名扩展、`1.0.0` 向后解析回归 | `spec/`、`schemas/generated/`、Schema 校验和版本演进测试 |
| 完整生命周期 | 编译、初始化、训练、保存、重载、推理/回测、结束或结构化失败 | `LifecycleMachine`、12 份可训练产物、18 份 `RunBundle` |
| 规则策略不少于 6 个 | 6 个，覆盖 bar、配对、L1、L2、执行 | 策略包发现、契约指纹、规则集成测试 |
| 监督学习不少于 6 个 | 6 个不同训练器与数据形态 | 训练、内容寻址保存、哈希校验重载、集成测试 |
| 强化学习不少于 6 个 | 6 个不同更新/规划/控制形态 | policy 产物、重载推理、集成测试 |
| 八类可解释异常 | 字段、周期、标的、模型、动作、订单、训练、回测错误 | `psrc demo failures`，实际错误码必须等于预期 |
| 不得静默兼容/降级 | 编译前协商，标的映射和 bar 重采样均需白名单且可关闭，并在适配器前组合执行；严格沙箱不可用或策略最低级别被降低时硬失败 | `psrc demo compatibility`、输入前后哈希、`fallback_used: false`、沙箱测试 |
| 真实回测引擎 | Reference、Backtrader、NautilusTrader 真实依赖运行并比较不变量 | `psrc demo adapters`、3 套原生适配器测试 |
| 主流引擎扩展能力 | LEAN、Qlib、vn.py 仅发布保守画像，默认不可执行 | 支持等级门禁、profile-only 拒绝测试 |
| 沙箱与资源限制 | manifest/输入/能力/源码哈希先验证，源码扫描后 import；单策略生产 Docker 入口；非 root、真实容器标记、无网络、只读根目录、capabilities 全移除、资源上限 | 恶意包及源码变更拒绝测试、`psrc sandbox run`、严格容器作业、命令构造测试、严格模式门禁 |
| 统一结果与错误报告 | JSON 机器证据 + 中文 HTML，包含源/有效输入、计划、训练与推理日志、成交、账户、内容寻址产物 | 18 个成功 bundle、8 个失败 bundle、报告测试 |

## 设计与验证要点

1. 面向评审的 README、规范、设计文档、Strategy Card 和 HTML 报告改为中文，机器字段保持英文稳定。
2. 修正生命周期旧文档中过度概括的统一 `request_id` 声明，使规范与实际 Schema 一致。
3. 严格容器从“只跑测试和示例”升级为完整门禁：增加 Ruff、mypy、Schema 漂移、策略包漂移检查。
4. 增加 `.dockerignore`，排除虚拟环境、缓存和生成证据，缩小并稳定构建上下文。
5. 增加最小权限 CI，同时执行本地 Contract 门禁和严格容器门禁。
6. 证据验证包含中文评审材料、容器完整验证设计和运行模式一致性检查。
7. 增加可移动策略包规范和 `psrc run --strategy-dir`，18 个示例均由目录发现并执行；另有不引用内置 catalog、`psrc.examples` 或 `psrc.strategies` 的临时论文包端到端测试。
8. 兼容计划在进入引擎前实际应用，并保存转换前后事件、数量和哈希。
9. 包源码 import 前强制执行允许列表扫描；严格证明同时核验容器标记、网络接口、进程 capability、NoNewPrivs 和挂载选项，环境变量不能单独伪造。
10. 非法动作与非法订单拆分；成功报告补齐实际输入和训练、推理、回测分阶段日志。
11. Contract 升级到 `1.1.0`，运行计划绑定策略包与运行时源码证据，并保留 `1.0.0` 文档解析回归。
12. 增加可组合的显式标的映射、策略最低沙箱门禁、单策略 Docker CLI 与 Agent 审计 CLI。

## 不应扩大解释的边界

- `PROFILED` 的 LEAN、Qlib、vn.py 是扩展设计，不是运行成功证据；只有实现桥接和原生测试后才能升级。
- 论文解析和代码生成属于项目外上游；仓库中的 Agent Contract 只负责结构化交接审计，不进入运行时，也不是回测复现依赖。
- 本地 `make verify` 验证功能和证据链，但不提供操作系统隔离；严格隔离必须以 `make verify-container` 的实际成功结果为准。
- 本项目不声称生产认证、策略盈利、不同引擎 PnL 完全相同，也不覆盖内核级容器逃逸。

## 提交前复核建议

提交前应保留以下两项结果：

1. `make verify` 返回 0，报告的 `verification_scope` 为 `development_preflight`；
2. 有 Docker 的干净环境中 `make verify-container` 返回 0，报告的 `verification_scope` 为 `strict_container_verification`，且 18 个正常运行均为 `strict_container`。

第二项是把“具备严格隔离设计”提升为“严格隔离已动态复现”的关键证据。若评审机器无 Docker，应明确标注未执行，而不是把静态配置当作动态通过。
