# 0002 站内咨询与交易后评价独立保存

Status: accepted
Date: 2026-10-21
Decision makers: 项目用户
References: 本轮用户在咨询与评价方案后明确要求“执行”；CAP-MER-006、CAP-CAT-005
Supersedes: none
Superseded by: none

## 背景与问题

现有AI会话属于买家与模型的受控任务链，不能用作买卖双方消息；商品已有计数字段但没有真实评价记录。多商家归属、类型化订单完成状态与订单物理删除会影响评价可信性。

## 决定

新增engagement Django App，MySQL保存会话、消息、评价、回复、举报与处理审计。复用身份鉴权与前端样式；首期增量轮询，不引入WebSocket、模型调用、外部消息平台。新订单商品保存购买快照；旧订单不从当前归属伪造历史。买家删除改隐藏，商家禁止物理删除已完成订单，有购买记录商品使用PROTECT防止级联丢失。

## 影响与验证

增加orders与engagement迁移，core装配、web双端入口以及goods／supplier删除兼容。评价按原购买商家和SPU聚合，提交／汇总使用事务和唯一约束。见[咨询](../sdd/modules/merchant-operations/buyer-merchant-conversations.md)、[评价](../sdd/modules/catalog-content/purchase-reviews.md)、[验证](../sdd/evidence/2026-10-21-engagement/verification.md)。部署和业务数据库迁移仍单独授权；本次决定不构成已发布证明。
