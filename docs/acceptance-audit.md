# 需求符合性审计

本文把公开任务要求映射到可执行证据，避免用“代码看起来完整”替代“结果可以复现”。`psrc verify` 只判断仓库内技术检查是否通过，不代表或替代主办方的档位认定。

## 要求—实现—证据

| 公开任务要求 | 当前实现 | 可执行证据 |
| --- | --- | --- |
| 完整工程与一键复现 | Python 3.12、`uv.lock`、Makefile、摘要固定 Docker 基础镜像、合成数据 | `make verify`、`make verify-container`、CI 可下载证据 artifact |
| 公开、稳定、可扩展 Contract | Contract `1.1.0`、22 份自包含 Draft 2020-12 Schema、稳定 `$id`、严格未知字段、反向域名扩展、`1.0.0` 向后解析回归 | `spec/`、`schemas/generated/`、标准 `jsonschema` 对 22 类真实文档的无网络验证 |
| 完整生命周期 | 编译、初始化、训练、保存、重载、推理/回测、结束或结构化失败 | `LifecycleMachine`、12 份可训练产物、18 份 `RunBundle` |
| 规则策略不少于 6 个 | 6 个，覆盖 bar、配对、L1、L2、执行 | 策略包发现、契约指纹、规则集成测试 |
| 监督学习不少于 6 个 | 6 个不同训练器与数据形态 | 训练、内容寻址保存、哈希校验重载、集成测试 |
| 强化学习不少于 6 个 | 6 个不同更新/规划/控制形态 | policy 产物、重载推理、集成测试 |
| 八类可解释异常 | 字段、周期、标的、模型、动作、订单、训练、回测错误 | `psrc demo failures`，实际错误码必须等于预期 |
| 不得静默兼容/降级 | 编译前协商，标的映射和 bar 重采样均需白名单且可关闭，并在适配器前组合执行；严格沙箱不可用或策略最低级别被降低时硬失败 | `psrc demo compatibility`、输入前后哈希、`fallback_used: false`、沙箱测试 |
| 真实回测引擎 | Reference、Backtrader、NautilusTrader 真实依赖运行并比较不变量，目录入口可显式选择引擎 | `psrc run --engine`、`psrc demo adapters`、3 套原生适配器测试 |
| 主流引擎扩展能力 | LEAN、Qlib、vn.py 仅发布保守画像，默认不可执行 | 支持等级门禁、profile-only 拒绝测试 |
| 沙箱与资源限制 | manifest/输入/能力/源码哈希先验证，源码扫描后 import；单策略生产 Docker 入口；非 root、真实容器标记、无网络、只读根目录、capabilities 全移除、资源上限 | 恶意包及源码变更拒绝测试、`psrc sandbox run`、严格容器作业、命令构造测试、严格模式门禁 |
| 统一结果与错误报告 | JSON 机器证据 + HTML，包含源/有效输入、计划、训练与推理日志、成交、账户、内容寻址产物 | 18 个成功 bundle、8 个失败 bundle、报告测试 |
