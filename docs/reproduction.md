# 复现与证据审阅

## 本地独立 Python 环境

```bash
git clone https://github.com/HendrixityBorg/StrategyAdapter.git
cd StrategyAdapter
make verify
```

`uv sync --frozen` 只接受提交的锁文件。Ruff、类型、测试、覆盖率、示例、失败场景、适配器或证据门禁任一项失败，命令都会以非零状态退出。生成证据位于 `reports/generated/`，且故意不提交到源码库，评审者应亲自复现。

建议按以下顺序查看：

- `acceptance-report.json`：独立验证器及全部检查细节；
- `junit.xml`、`coverage.json`：测试数、零 skip 约束及覆盖率；
- `runs/all/summary.json`：18 个成功策略运行；
- `runs/failures/summary.json`：8 个稳定错误码，分别覆盖非法动作与非法订单；
- `runs/compatibility/bundle.json`：兼容转换前后输入及实际运行数量；
- `runs/adapters/comparison.json`：原生跨引擎不变量；
- 任意 `runs/**/report.html`：中文统一运行报告。
- 任意 `runs/all/*/bundle.json`：声明、实际输入、训练请求与运行结果的单一机器可读聚合对象。
- 任意 `runs/all/*/strategy-code-evidence.json`：策略包逐文件哈希及运行时源码树哈希。

## Docker 严格隔离

```bash
make verify-container
```

该命令构建基础镜像摘要固定、Python 依赖锁定的镜像，并在一个受限容器内依次执行：

1. Ruff 与严格 mypy；
2. 重新导出 Schema 和策略包，与提交内容做目录比较；
3. 全量 pytest、JUnit、覆盖率；
4. 18 个正常示例、8 个失败场景、兼容转换闭环、3 个原生适配器差分；
5. 带 `--require-strict` 的证据符合性检查。

容器无网络、根文件系统只读、使用非 root UID、移除全部 capabilities、启用 `no-new-privileges`，并限制资源和可写位置。Docker 缺失会硬失败。只有在明确接受开发模式时才使用 `make verify`；本地通过不能替代严格容器实际通过的声明。

Ruff、mypy 和 uv 的缓存全部位于容器的 `noexec/nosuid/nodev` 临时文件系统，pytest 项目缓存被禁用；验证过程不需要向只读的 `/app` 写入。

## 单项诊断

```bash
make lint
make test
make schema
make packages
make examples
make failures
make adapters
make compatibility
make acceptance
```

单个第三方策略需要宿主机主动送入严格容器时，先执行 `make container-build`，再运行：

```bash
uv run psrc sandbox run \
  --strategy-dir strategies/rule.sma_cross \
  --output reports/single-strict-run
```

项目不使用私有数据、账户、API Key 或外部服务。全部 fixture 都是确定性生成的合成事件，并具有 manifest 内容哈希。

## 预期证据下限

- 至少 22 份 JSON Schema；
- 18 个策略包及运行，严格为规则 6 + 监督学习 6 + 强化学习 6；
- 12 份保存后重载的模型/策略产物；
- 8 个结构化强制失败场景；
- 3 个 `CONFORMANCE_VERIFIED` 原生引擎和 3 个 `PROFILED` 引擎设计；
- 至少 50 项测试，失败、错误、跳过均为 0，代码覆盖率不低于 90%；
- 所有 18 个策略包均从目录源码入口执行，具有精确源输入、有效输入及源码证据；
- 所有 18 个运行均产生决策、订单和至少一笔成交；
- 严格验证要求全部运行均为 `strict_container`，开发预验收不能冒充严格证据。

## 评审声明边界

若机器没有 Docker，只能报告本地开发模式门禁结果，并注明严格容器“未在本机执行”。不得根据 Dockerfile 静态存在就声称已经获得操作系统隔离证据。CI 中的容器作业及评审者本机运行可补齐该动态证据。

GitHub Actions 的两个验证作业会分别保留 `psrc-development-evidence` 和 `psrc-strict-container-evidence` artifact 30 天；即使某项检查失败，也会尝试上传已生成证据，便于定位与独立复核。
