# 单位经济的计算口径

Python 3.10+；依赖 jsonschema>=4.18,<5。先安装 requirements.txt 所列依赖，再从 Skill 根目录运行 scripts/economics.py。

所有输入使用 [共同合同](data-contract.md)。可复跑输入：[独立样例](standalone-example.json)，synthetic=true，仅校验逻辑，不是实际费率或商品推荐。运行时先验证原件和当前规则。

## 简化模型（每发出一单）

P = seller_price（RUB，gross_seller）；不能传已扣佣金的净回款。
G = (procurement + domestic_shipping + packaging) × fx_rub_per_cny。
F = G + outbound_shipping + return_loss + other_fixed。
r = commission_rate + payment_rate + tax_rate；a = ad_rate。

- 采购口径毛利 = P - G，仅扣采购/国内运费/包装，明确未扣平台与跨境费用。
- 广告前贡献 = P × (1-r) - F。
- 广告后贡献 = P × (1-r-a) - F；贡献率 = 贡献/P。
- 保本价 = F/(1-r-a)，仅当分母>0、费率/基数/阶梯在该售价仍成立。
- 保本广告率 = 广告前贡献/P；负值表示没有广告空间，不能变成可投放预算。

return_loss 是每发出一单的预期增量净损失：退款造成的收入损失 + 逆运费/处置等 - 可回收库存及退回费用，不能再次计入已经包含在 G 或 outbound_shipping 中的同一笔成本。若随售价变化，必须在每个售价/保本候选点重新计算；简化工具只支持可视为固定准备金的情景，不处理复杂退款状态。other_fixed 明确含哪些额外逐单费用；零值也需依据。

标准压力场景是本地测试假设：售价×0.90、RUB/CNY×1.10（人民币采购折RUB增加）、运费×1.20、退款准备金×1.50；可另行人工增加符合业务的情景，不将该比例解释为预测。公式用 Decimal 计算，仅最终显示四舍五入到两位；每笔实际结算遵循账户规则。

分母非正时无有限保本价，输出 NO-GO，不能除零。佣金跨价档、最低收费、不同税基、净结算输入、补偿尚未对账或退款模型不适用时，使用逐笔模型，保持 HOLD 而非套用上述公式。

## 决策边界

scenario_signal 是局部经济性结论；总体有限 GO 另需 FACT 的账户/合规/物流门槛、FACT 的包装/线路限制、可承受压力成本的预算、试销数量、未来复查日期和停止条件。UNKNOWN 硬证据不能被 ASSUMPTION=true 绕过。体积重仅按合同除数计算，其他限制由 logistics_verified 的原件支撑。

工具的预算检查为压力情景下全部已建模逐单支出（固定成本及按收入计费的费用）×数量≤loss_cap，只是保守支出检查，不是完整现金流或最大损失证明。实际还要列付款节点、账期、广告花费、税费及突发退货准备；总体 GO 要由 Skill 的人工评审完成。

输出保留 synthetic、输入引用、formula、情景参数及缺口。原件真实性、商品资格、费表是否完整与会计税务结论均未由代码核实。
