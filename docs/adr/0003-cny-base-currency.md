# 0003 人民币基础计价与外币参考显示

Status: accepted
Date: 2026-10-22
Decision makers: 用户（本次会话）
References: 用户明确要求“统一基础货币单位使用人民币，使用其他货币显示再更换”；[金额规格](../sdd/architecture/currency.md)
Supersedes: none
Superseded by: none

## 背景与决定

数据库金额没有独立币种字段；采购目录、经营统计已按CNY解释，Agent和采购车等入口曾将同一数值解释为USD。基础计价与程序计算统一为CNY，现有数值保持原值，不批量乘除汇率，不改写历史交易及客服回复。

USD、AED、SAR、EUR为参考显示币种；前后端共同读取tea_saas/currency.json，不接入实时外汇服务，不将显示金额写回商品售价、采购车存储或订单。Agent未标明币种默认CNY；明确外币保留原需求和证据，由程序换算，上限向下取人民币分，下限向上取分。

## 影响与验证

涉及core、support_ai、web与未来虚拟商品生成说明；无Migration、无业务库金额修改。支付可信通知、历史对账和实际渠道币种仍需独立验收，不能以显示改动证明。检查范围见金额规格。
