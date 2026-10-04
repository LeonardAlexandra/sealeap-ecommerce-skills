# Ozon 多源证据合同 · ozon-evidence/1.0

本文件为第一阶段共同规则。每包附相同副本以保持单包可复制；规范源位于 sealeap-ozon-data-audit，仓库 sync_ozon_phase1.py 同步并检查副本。
先读本合同，再读本任务 playbook。[机器 Schema](schema.json)约束交换格式；Schema 合格不等于来源真实或 GO。

## 来源优先级按指标，而不是按文件格式

| 数据 | 首选 | 可选增强或补充 | 不可替代 |
| --- | --- | --- | --- |
| 自家订单、费用、到账、退款 | 已授权 Ozon Seller 明细与自家账单对账 | 自家 ERP；有原始账单定位的 MPstats 内部报表 | 外部估算销量或买家卡价 |
| 自家采购、包装、称重、物流报价 | 自家实测/供应报价/承运合同 | 手工录入并附原件、适用日期 | 行业平均或竞品物流 |
| 竞品价格、评分、评论数、规格、卖家、承诺时效 | Ozon 前台带目的地的快照 | MPstats 商品报表 | 不能当成交价、实际时效或真实销量 |
| 市场规模、竞品订单、动销率、集中度 | 有权访问且有明确市场分母的报告 | MPstats 外部估算及其他经核验报告 | 评论量、排名、抓取数量不能变销量 |
| 账户资格、费率、线路 | 当前账户/合同及适用地区官方规则 | 历史截图只作线索 | 竞品用 FBO 不证明本账号可用 |

CSV/XLSX 是 transport，不是信誉等级。来源不明用 provider=manual，必须追溯原提供方；有原始平台证据则按原提供方标 provider，transport 仍保留 csv/xlsx。不得因导入表格自动提升为 FACT。Seller 报告也需看字段定义和账户权限，不能默认可见全市场数据。

## 证据状态

- FACT：可核验的观察/实测/自家已核明细，仅在声明范围内成立。前台评论数是观察事实，不是销量事实。文档说明某字段存在，不是该商品数值证据。
- ESTIMATE：第三方估算、带明确计算依据的推算/预期成本。公开页面不能直接提供竞品真实利润。MPstats external 的 sales/revenue 必须为 ESTIMATE。
- ASSUMPTION：用户设定的试售价、预算、情景参数；说明依据与敏感性。假设认证通过、账户可用、重量已核验不能通过硬门槛。
- UNKNOWN：value=null、confidence=UNKNOWN，reason 写缺失/过期/冲突/不适用原因；不适用不是零。已证实费用为零可写 FACT 0 并留依据。

confidence 为 HIGH/MEDIUM/LOW/UNKNOWN（证据质量等级，不是概率）。HIGH 不会将 ESTIMATE 变成 FACT；派生结论不得高于最弱关键输入。合成测试中 FACT 仅模拟该证据形态，synthetic=true 必须传播至所有输出。

## 统一结构与字段字典

- 顶层：schema_version、dataset_id、synthetic、context、sources、records、conflicts。
- context：seller_region / market / account_scope（匿名）/ destination / mode。
- 每个 source：id、provider、transport、module、locator、raw_sha256、captured_at（带时区）、period_start/end、timezone（IANA）、currency、money_unit、scope、coverage、field_map。原始文件私下留存；哈希证明内容一致，不证明内容真实。
- coverage：selected、total（未知为 null）、pagination_complete、filters（查询词、目的地、FBS开关、抽样规则）。sample 永远只代表样本；全市场结论要求 declared_market、完整分页及明确分母，仍需人工核验覆盖定义。
- record：record_id 唯一；sku 保留字符串；role=candidate/competitor；seller_id、category_path、spec_group、fulfillment。UNKNOWN 模式不能依据时效猜成 FBO。不同变体/包装/目的地/快照保留独立 record_id。
- 每个字段：value、kind、unit、currency、source_ids、raw_fields（原列/行/单元格定位）、confidence、reason。原始单位先记录再转换；金钱规范值使用 major 主币种单位。当前可执行测算限 CNY/RUB，其他币种需显式扩展，不能偷换币种。

| 字段组 | 规范字段和单位 |
| --- | --- |
| 前台/竞品 | price_regular、price_discount、price_card（money，RUB）；pack_quantity（count）；rating（score）；review_count（count）；delivery_days（days）；brand（text） |
| 市场可选 | sales_estimate（count）、revenue_estimate（money，RUB）、stock_days（days）；来源、时间和分母不齐不算份额/动销 |
| 实际经营可选 | sales_actual（count）、revenue_actual（money，RUB）；必须已核自家范围 |
| 采购 | procurement、domestic_shipping、packaging（money，CNY）；fx_rub_per_cny（RUB/CNY）=1 CNY可换RUB |
| 收入/成本 | seller_price（money，RUB，扣平台费用前卖家应计收入基数）、revenue_basis（text，gross_seller）；outbound_shipping、return_loss、other_fixed（money，RUB） |
| 比率 | commission_rate、payment_rate、tax_rate、ad_rate（ratio，0至小于1，统一基于 seller_price）；不同计费基数用明细模型，不能套此简化计算器 |
| 履约 | weight_kg、length_cm、width_cm、height_cm、volumetric_divisor（cm3/kg）、max_billable_kg、delivery_days、max_delivery_days；体积重除数来自合同，非平台常量 |
| 硬门槛 | account_eligible、compliance_verified、logistics_verified（boolean）；true必须为 FACT、有来源，不能用假设补齐 |
| 试销 | loss_cap（money，RUB）、test_units（count）、review_on（text，日期）、stop_condition（text）；明确上限、退出条件和复查日 |

零售价格与 seller_price 分开。review_count 不参与 sales_estimate 推算。源字段冲突保留两份原始证据，conflicts 记录选用理由；关键冲突未解则 HOLD，不能静默取均值。

## 缺失、时效与决策

缺失列表由所请求任务的必填字段产生，不强制所有来源同时存在。无 MPstats 本身不构成 HOLD。仅有前台时可完成描述性竞品/价带；市场规模、订单份额保持 UNKNOWN。缺可比规格、价口径、关键成本、当前资格则相关判断 HOLD。
默认快照新鲜度 7 天是可配置本地策略，不是 Ozon 规定。核对数据实际期末而非下载日；过期、未来日期、坏单位、重复键、未解冲突不可用。历史回测显式指定 as_of，不得用旧日期冒充当前判断。

GO = 证据充分的、有损失上限的小额试验；不是推荐直接采购或无限扩量。全部硬门槛通过、基准与压力贡献为正、试销约束齐全才可 GO。已经证实的硬限制失败/完整计算亏损为 NO-GO；只是缺证为 HOLD。已证实单项硬否决足以 NO-GO 时可说明局部证据，不把缺失的其他项称已通过。
数据审计用 READY_FOR_REVIEW / HOLD，测试数据用 VALID_SYNTHETIC / HOLD；审计就绪不能转成业务 GO。

## 统一输出与第二阶段接口

每个 Skill 输出 result_version=ozon-result/1.0、dataset_id、synthetic、skill、as_of、scope、decision（GO/HOLD/NO-GO）、decision_scope、confidence、evidence_refs、metrics、missing_fields、conflicts、limitations、next_actions。审计另用 audit_status，decision 保留 HOLD 直至业务评审。
metrics 继续携带同一证据对象；派生值增加 formula、input_refs。next_actions 包含字段、所需文件/行/日期、负责人角色、恢复条件和复查日。人工输出也遵守此合同；当前工具只实现校验与局部数值核验，不自动生成完整商业评审。
预留 extensions 下 keyword_map、listing、visual_brief、crossborder_eligibility、adult_compliance、sourcing_1688、feishu_sku、operations，默认不填，不据此宣称已实现步骤9～17。写入飞书或发布商品需要相应任务授权。
