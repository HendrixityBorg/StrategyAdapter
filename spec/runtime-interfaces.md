# 运行接口

本文件定义 Contract v1 在参考 Python SDK 中的真实调用边界。其他语言和引擎可以使用不同函数名，但输入、输出、顺序及失败语义必须等价。

## 策略包统一入口

```bash
psrc run --strategy-dir <package> \
  --engine <reference|backtrader|nautilus-trader> \
  --output <report-directory>
```

该入口从目录读取策略 manifest、数据 manifest、精确输入事件及可选训练请求。它必须在 import 前依次完成声明解析、输入内容哈希校验、所选引擎能力编译和源码安全扫描，再根据生命周期使用同一 orchestrator 执行训练、内容寻址保存、完整性校验加载、推理和回测。`--engine` 默认为 `reference`；只有选定的引擎依赖和实现会被加载，能力不匹配时禁止替换引擎。目录格式见 [策略包规范](package.md)。

## 编译入口

```python
compile_run(
    *,
    run_id: str,
    strategy: StrategyManifest,
    dataset: DatasetManifest,
    engine: EngineCapabilities,
    policy: RunPolicy,
) -> ExecutionPlan
```

编译发生在策略 import 和运行之前。成功结果包含四份声明的哈希及逐项兼容性记录；不满足要求时抛出带 `ContractError` 的 `ContractViolation`，不得尝试替代引擎或隐藏转换。

## 策略推理入口

```python
class RuntimeStrategy(Protocol):
    manifest: StrategyManifest

    def on_start(self) -> None: ...
    def on_event(
        self,
        event: MarketEvent,
        account: AccountSnapshot,
    ) -> tuple[Action, ...]: ...
    def on_finish(self) -> None: ...
```

`on_event` 是统一推理回调。它只能读取当前已可用的规范行情事件和调用时账户快照，并返回声明动作空间内的规范动作。非法动作以 `ACTION_INVALID` 或 `ORDER_REJECTED` 失败；异常不得被改写成 no-op 成功。

## 训练与模型入口

```python
class TrainableStrategy(Protocol):
    def train(
        self,
        request: TrainingRequest,
        store: ArtifactStore,
    ) -> ArtifactManifest: ...

    def load(
        self,
        manifest: ArtifactManifest,
        store: ArtifactStore,
        *,
        run_id: str,
    ) -> None: ...
```

`TrainingRequest` 包含运行 ID、数据集 ID、确定性种子，以及监督学习的特征/标签或强化学习 transitions。`train` 必须把可重载内容写入 `ArtifactStore` 并返回 `ArtifactManifest`；`load` 必须验证声明文件的大小和 SHA-256。产物缺失或哈希不符分别返回 `ARTIFACT_NOT_FOUND`、`ARTIFACT_HASH_MISMATCH`。只有重载成功后才可进入推理/回测。

## 回测引擎入口

```python
class BacktestAdapter(Protocol):
    def run(
        self,
        *,
        plan: ExecutionPlan,
        strategy: RuntimeStrategy,
        events: tuple[MarketEvent, ...],
        sandbox_mode: SandboxMode,
    ) -> RunReport: ...
```

适配器驱动 `on_start -> on_event* -> on_finish`，把规范动作映射到原生引擎，并把订单、成交、账户、日志和指标还原为 `RunReport`。它必须遵守 `ExecutionPlan` 中的成交与时间语义，不得吞掉拒单。原生异常统一封装为结构化 `BACKTEST_FAILED`，同时保留原因链。

## 失败出口

所有阶段失败均以 `ContractError` 表示，并可写成 `FailureReport`。失败报告包含原始策略、数据集、引擎能力、运行策略及实际输入上下文；任何 fallback 成功都不能覆盖原始失败。运行生命周期进入 `FAILED` 后不可再次转换。
