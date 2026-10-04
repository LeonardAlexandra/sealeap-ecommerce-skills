# OZON 多数据源验收：判断与验收

数据审计不强制销量或 MPstats；按 requested_fields 传任务必需字段。空列表只查合同，不能意味着后续任务通过。默认检查所有输入的结构与来源；不相关坏数据可隔离后作为另一个 dataset 重验，保留排除理由。用七天新鲜度时，实际期末和抓取日都需通过。

从本 Skill 根目录运行：

```bash
python3 scripts/audit.py path-to-normalized-input.json --as-of 2026-10-04 --required seller_price procurement
```

需要 Python 3.10+ 和 jsonschema>=4.18,<5；安装依赖见 requirements.txt。输出只核验结构/局部语义，不验证原件真实性。案例都是固定测试材料，使用冻结 as_of 才能复跑；不能用历史通过结果做今天经营决策。

验收：无 MPstats 的有效合同可通过；UNKNOWN 被列出；UNKNOWN 核心成本为 HOLD；重复记录、无源 FACT、币种不明和未解冲突拒绝。

通用规则及输出结构见 [多源证据合同](data-contract.md)；缺失字段不得填0或用行业均值暗中补齐。
