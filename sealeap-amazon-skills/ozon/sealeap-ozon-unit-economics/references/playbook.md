# OZON 跨境单位经济与保本价：判断与验收

需要 [统一合同](data-contract.md)中全部成本字段，不能默认遗漏费用为0。已核为零需提供依据。不适用的未知税费仍是 HOLD，除非当前责任口径明确并给零值证据。

[计算器](../scripts/economics.py)与[计算说明](economics.md)配套，接受规范 JSON，不联网。复制整个 Skill 可独立使用。可运行的完整五例在数据审计包；本包提供一个 standalone-example.json。

```bash
python3 scripts/economics.py references/standalone-example.json --as-of 2026-10-04
```

返回 scenario_signal 是局部数值结论；不是自动采购建议。佣金阶梯、不同税基、不可线性化退款或净结算输入为 HOLD，要求逐项现金流重算。

通用规则及输出结构见 [多源证据合同](data-contract.md)；缺失字段不得填0或用行业均值暗中补齐。
