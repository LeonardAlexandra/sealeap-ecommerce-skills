# Ozon 第一阶段改造交付 · 2026-10-04

本轮只完成步骤1～8：统一证据规范，以及数据审计、niche-screening、competitor-map、price-segment、unit-economics、fulfillment-choice六项能力。MPstats 从这六项能力的必需来源改为可选增强。步骤9～17仅保留接口定义，未改动这些 Skill，也未创建飞书写入、商品发布或采购动作。

改造基于上游提交 `e1a39e197193a07a044ca80191bf541eae17f4a5`。保留所有原版权及许可。使用个人 Fork 的独立分支交付，不改上游默认分支。

## 改动清单与各 Skill 摘要

| 入口 | 改动 | 缺数据时的行为 |
| --- | --- | --- |
| [data-audit](ozon/sealeap-ozon-data-audit/SKILL.md)（新通用名称） | Seller/前台/自家/导出/MPstats来源清单、逐字段证据、Schema及离线验收；哈希可本地复验 | 分任务列缺口；通过仅为数据就绪，不是商业GO |
| [mpstats-data-audit](ozon/sealeap-ozon-mpstats-data-audit/SKILL.md)（旧名兼容） | 同样使用通用合同；保留原只读API探针、旧日序列格式与测试 | 旧调用不失效；旧格式与通用格式明确分开 |
| [niche-screening](ozon/sealeap-ozon-niche-screening/SKILL.md) | 同规格样本、成本与跨境约束驱动有限试销；不再先索要MPstats | 市场规模/动销未知仍可描述；关键成本/资格未知HOLD |
| [competitor-map](ozon/sealeap-ozon-competitor-map/SKILL.md) | 前台、用户列表等建池；卖家、规格、价类、评分、评论和送达承诺；分本土/跨境 | 无销量不算销售份额；模式未知不按时效猜FBO |
| [price-segment](ozon/sealeap-ozon-price-segment/SKILL.md) | 同规格及套装单位化；分离原价/折扣价/卡价，比较完整成本底线 | 无数量/币种HOLD单位价；无销量不算销量加权价格 |
| [unit-economics](ozon/sealeap-ozon-unit-economics/SKILL.md) | CNY采购/包装/国内运费转RUB，计入rFBS正向、退款净损失、佣金/支付/税费/广告；毛利、贡献、保本及压力场景 | 关键成本不填0；净结算重复扣费与非线性模型不套简化公式 |
| [fulfillment-choice](ozon/sealeap-ozon-fulfillment-choice/SKILL.md) | 中国→俄罗斯rFBS优先评审；账户资格、包装实测、体积重、时效和逆物流 | 明确不可用或超限NO-GO；缺证HOLD；FBO/FBS只作参照，除非本账户资格已核 |

其他变更：目录和调用提示同步更新；校验器允许上述7入口MPstats可选，仍强制未迁移20项原声明；增加副本同步检查、5个固定案例、回归测试和结果复跑脚本。全库195个入口（Ozon27个，含旧名称兼容入口），对应原194项能力，不把别名算成新业务能力。

## 统一 Schema

规范版本 `ozon-evidence/1.0`：[完整合同](ozon/sealeap-ozon-data-audit/references/data-contract.md)、[机器Schema](ozon/sealeap-ozon-data-audit/references/schema.json)、[来源适配](ozon/sealeap-ozon-data-audit/references/adapters.md)。

| 层 | 主要字段 |
| --- | --- |
| 数据集 | schema_version、dataset_id、synthetic、context、sources、records、conflicts |
| 上下文 | 卖家地区、市场、匿名账户、跨境/本土模式、目的地 |
| 来源 | provider、transport、module、原件定位与SHA-256、抓取时间、实际起止、时区、币种/单位、范围/分页/样本分母、字段映射 |
| 商品记录 | record_id、sku、candidate/competitor、seller_id、类目、规格组、履约方式 |
| 每个数值/判断输入 | value、FACT/ESTIMATE/ASSUMPTION/UNKNOWN、单位、币种、source_ids、raw_fields、confidence、reason |
| 冲突 | record_id、field、各来源、resolution；未解关键冲突HOLD |
| 结果 | ozon-result/1.0、范围、GO/HOLD/NO-GO、置信度、证据引用、派生公式、缺失字段、限制、下一步；synthetic贯穿 |

CSV/XLSX是文件格式，不是原始证据来源。资料真实与否不能由文件格式或Schema验证证明。FACT限于已核观察/明细；第三方市场销量为ESTIMATE；人为情景为ASSUMPTION；缺失为UNKNOWN/null。源可靠度按指标评估，不固定把某个提供方置顶。

保留独立安装方式：每个 Skill 自带共同合同副本。规范源是通用数据审计包；仓库根目录 `sync_ozon_phase1.py` 同步，`--check` 校验漂移。计算工具需Python 3.10+及包内 requirements.txt 声明的 jsonschema 依赖。

## 5个可复核 Case 与结果

这些是**人工编制、原件JSON和哈希齐全的固定测试案例**，不是实际Ozon商品或订单，不证明商机与实际收益。选择可复核合成案例是因为本次未提供真实店铺/供应/承运资料。所有价格、费率、运费、资格和限额仅为测试输入。冻结回测日期2026-10-04。

原材料位于[案例目录](ozon/sealeap-ozon-data-audit/references/cases/)，其中 `raw/`保存原值，`expected.json`为独立手算预期。[机器结果](assets/ozon-phase1-results.json)记录每例输入哈希、决策与数值。

| Case | 审计 | 基准/压力广告后贡献（RUB/单） | 关键判断 | 结果 |
| --- | --- | ---: | --- | --- |
| 01 轻小件有限试销 | VALID_SYNTHETIC | 440 / 235 | 无MPstats；假定已核资格/线路，计费重0.4kg，预算6000 RUB、5单、复查/停止条件齐全 | GO仅指该测试条件下有限试验 |
| 02 低售价负贡献 | VALID_SYNTHETIC | -120 / -269 | 完整成本下亏损，不能靠广告放量弥补 | NO-GO |
| 03 本土竞品有互动但跨境不适配 | VALID_SYNTHETIC | 1360 / 838 | 经济性为正；包装体积重32kg超过案例线路5kg上限；本土FBO不能授予本账号资格 | NO-GO（当前路线） |
| 04 报价/退款成本缺失 | 成本审计HOLD；描述性字段可用 | 不计算 | 缺outbound_shipping与return_loss；竞品描述仍可交付 | HOLD |
| 05 多源汇率冲突 | HOLD | 不计算 | 12与14 RUB/CNY未解；额外MPstats估算不能覆盖该冲突 | HOLD |

手算例01：采购口径成本=(20+3+2)×12=300；固定成本=300+250+40+20=610；总比例=.15+.02+.03+.10=.30；贡献=1500×.70−610=440。压力：1350×.70−(330+300+60+20)=235。保本价610/.70=871.43；压力保本价710/.70=1014.29。预算检查还计入已建模比例费用，不只检查采购。

按六项能力检查：审计验证原件哈希/结构及缺口；竞品池只报告seller-a两件、seller-b一件样本商品；同规格价格每件500/600/700，样本中位数600；销量CR5、市场规模、销量加权价全部UNKNOWN；单位经济匹配手算；履约拒绝案例03；细分筛选依据这些边界形成上表限定范围结论。

测试覆盖的是离线参考逻辑与Skill规则一致性审阅，未执行独立LLM盲测、真实Seller账户流程或商业效果测试。CSV/XLSX支持通过映射规范导入，未实现通用自动解析器、Seller API连接器或爬虫。

## 验证与复跑

在仓库根目录运行（依赖见通用审计包 requirements.txt）：

```bash
python3 sync_ozon_phase1.py --check
python3 validate_repo.py
python3 -m unittest discover -s tests -p test_ozon_phase1.py -v
python3 -m unittest discover -s sealeap-amazon-skills/ozon/sealeap-ozon-mpstats-data-audit/scripts -p test_mpstats.py
python3 run_ozon_phase1_cases.py
```

本轮新回归覆盖5例手算及缺失、冲突、时效、货币、单位、代理指标、硬资格、预算、独立复制等边界；原MPstats传输与旧数据校验回归继续运行。具体最终数量记录于[验证记录](VALIDATION.md)。

## 仍不能免费替代或不能推断的指标

| 指标 | 当前可用性与边界 |
| --- | --- |
| 竞品按日销量、订单额、历史库存、动销率、细分市场金额、卖家销售CR5/CR10 | 往往仍需有权限的市场报告、第三方数据或自建连续采集；MPstats也通常只能估算。无合格数据则UNKNOWN，不影响描述性分析 |
| 缺货潜力、潜在收入、上市时间 | 第三方模型/首次发现只是线索，不证明可抢销量或实际首上架时间 |
| 历史价与各地时效趋势 | 需要连续快照/报告；单次前台观察不能还原历史 |
| 关键词频次、词排名历史 | 本阶段未实施，保留给步骤9；无报告时不能假造搜索量 |
| 自家实际利润、退款净损失、回款、真实广告归因 | 必须自家平台账单/经营明细；第三方外部估算不能替代 |
| 现行费率、资格、承运限制和清关/产品文件 | 需当前账户、合同和适用地区官方证据；不是MPstats问题。Ozon官方入口本次返回重定向循环，未据此写入固定平台规则 |

## 步骤9～17的接口预留（未实现）

| 步骤 | 复用输入/预留扩展 | 下一阶段边界 |
| --- | --- | --- |
| 9 keyword-map | extensions.keyword_map；SKU/规格、俄语词、来源、frequency证据 | 无频次保留UNKNOWN |
| 10 listing-localization | extensions.listing；已核属性、关键词证据、禁用声明 | 不生成未经核验规格/品牌/认证 |
| 11 visual-brief | extensions.visual_brief；痛点来源、规格事实、素材任务及权利 | 不自动发布素材 |
| 12 crossborder-eligibility | extensions.crossborder_eligibility；尺寸/线路/费用/资格证据 | 本阶段只提供fulfillment输入，未新增专项 |
| 13 adult-product-compliance | extensions.adult_compliance；产品分类和文件缺口 | 需专项现行规则核验，未做合规结论 |
| 14 1688供应链 | extensions.sourcing_1688；报价、MOQ、包装、有效期和供货证据 | 本阶段只消费已有成本，不开发供应商筛选 |
| 15 飞书SKU池 | extensions.feishu_sku；dataset_id、SKU/市场、版本、证据、结论、缺失/动作；建议幂等键SKU+market+dataset_id | 没有创建表格或写入API |
| 16 端到端测试 | 共用版本化输入/结果和回归案例编号 | 要等9～15实现后再跑真实商品流程 |
| 17 其余Ozon Skills | extensions.operations；订单/退款/库存/结算真实明细 | 20项未迁移Skill维持原约束；以后逐项评审 |
