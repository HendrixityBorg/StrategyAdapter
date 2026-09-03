# rule.l2_imbalance_maker

- 策略类别：`rule`
- 策略版本：`1.0.0`
- 执行入口：`strategy.py:Strategy`
- 训练模式：`not_required`
- 允许动作：no_op, replace_order, submit_order
- 确定性种子：`7`

## 数据契约

- `book_snapshot_l2` / `event`: asks.price, asks.size, bids.price, bids.size

本策略仅用于合成研究演示，不构成投资建议。
