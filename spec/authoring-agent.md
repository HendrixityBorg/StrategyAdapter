# 可选上游 Agent 交接与审计边界

论文解析、正文抽取和策略代码生成不属于本项目交付范围。外部 Agent 可以在执行之前产出 `PaperStrategySpec`、代码和 `StrategyManifest`；PSRC 只定义这些产物的交接结构，并提供确定性审计。Agent 没有运行时权限，不能选择替代引擎，不能降低沙箱策略，也不能在缺少论文、操作者或实验来源记录时擅自解决阻塞性歧义。

晋级路径如下：

`论文 -> Agent 草稿 -> PaperStrategySpec -> 确定性审计 -> 人工复核 -> 已验证 StrategyManifest -> 能力编译 -> 隔离运行时`。

`AgentAuditReport.runtime_authority_granted` 在类型上固定为 `false`。Agent prompt、模型供应商、PDF/HTML 解析器和生成流程被有意排除在 Contract v1 之外：它们可以独立演进，但不能改变策略执行语义。因此 LLM 只是可选上游，不是本项目运行或复现的依赖。

审计检查策略类别、精确数据要求、允许的动作空间、训练/标签/奖励语义及未解决歧义。审计通过只是必要条件，不是充分条件；标准编译器、沙箱和测试仍必须执行。

确定性入口如下；未解决的阻塞歧义会写出拒绝报告并返回非零状态：

```bash
psrc author audit --spec paper-spec.json \
  --manifest strategy.yaml --output agent-audit-report.json
```

Agent 不负责维护“主流引擎知识库”的真相。可执行适配范围由版本化 `EngineCapabilities`、适配器代码及原生测试共同证明；Agent 最多提出候选画像，不能自行把支持等级提升为 `CONFORMANCE_VERIFIED`。
