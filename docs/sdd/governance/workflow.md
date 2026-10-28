# SDD 规则、状态与变更约定

版本0.2.2，2026-10-28，执行R10／R11并接入本地收尾设计与Skill流程。适用于当前个人维护项目；Git授权、版本、Hook及Migration规则仍以根AGENTS.md和Git协作规范为准。

## 规则归属

`MOD`为业务域，`CAP`为能力，`FEAT`为来源功能；一项FEAT只有一个primaryCapability。需求、规则、验收使用REQ／RULE／AC，形成FEAT→CAP→REQ/RULE→AC→契约／测试→证据。App与业务域可以多对多，不据此拆服务。

## 四个独立状态

| 字段 | 取值及含义 | 更新依据 |
| --- | --- | --- |
| specStatus | unreviewed、in-review、rules-accepted | 业务规则审查记录；rules-accepted仅表示标明范围的规则已确认，技术设计可仍待评审 |
| implementationStatus | not-implemented、entry-only、source-observed、partial | 代码观察和具体差异；source-observed不等于完成实现验收 |
| verificationStatus | not-run、historical-evidence、partial-evidence、verified | 必须绑定规格版本、源码快照、环境和覆盖AC；新规则不继承旧测试成绩 |
| deploymentStatus | unverified、local-recorded、not-enabled、released | 对应目标环境的实际启用／发布记录；有本地记录不代表远端上线 |

四字段统一位于catalog能力项及活动capability.yaml的assessment中。模块REGISTERED/MAPPED仅描述映射完整性；既有status保留为legacyStage兼容信息，不用它表达四种不同完成情况。未覆盖能力默认unreviewed/source-observed/not-run/unverified，不能自动标成已验收。

旧阶段值只保留为legacyStage兼容字段；历史批准仅在原授权范围有效，不复制旧阶段规范。后续小改按影响选材料，不要求重新补齐全套原型阶段；旧阶段不构成跳过支付、库存、权限等验证的理由。

## 按风险交付

| 变化 | 最小材料 | 验证 |
| --- | --- | --- |
| 文案、样式、既定规则缺陷 | 依据、变化和可观察预期 | 直接受影响文件／页面 |
| 新增或替换业务规则 | 当前需求、规则、AC、契约与规格版本；保留决定来源 | 当前切片及依赖 |
| 支付、库存、认证、跨用户或跨库数据 | 以上材料及幂等、并发、失败、兼容、迁移／回滚 | 真实组件的隔离验证及目标环境验收 |

用户明确授权可以确认本次业务范围；不得代填技术评审、测试通过、发布批准。实施、提交、推送、PR、合入和部署分别按实际授权。纯文档修订不隐式运行全量业务测试，不机械提升实现模块版本。

## 本地交付收尾

[本地收尾设计](local-delivery-closeout.md)分别定义远端结果、原工作核销、临时资源和整体收尾状态。交付完成到哪一步按用户请求报告：建PR成功可以结束当前请求，但不能据此宣称原现场已核销或工作区已回收。

该设计属于工程治理，不新增业务MOD／CAP，不改变能力的四项assessment。来源记录、只读核对、收尾模式和恢复入口已接入交付Skill；自动核销／回收工具尚未实现，实际验收和清理须分别记录，不能把文档或技能修改当作执行完成。

## 单一现行正文

现行requirements/acceptance及对应领域规格定义规则；api-contract是目标接口，api-observed只记录特定源码快照的事实。发现冲突先登记差异，不能把旧代码行为直接认可为产品规则。

替换规则时完整更新唯一现行正文，删除已被完整替换的旧规格并同步所有活动引用；不建立history、日期副本或多版本规格。历史evidence不改写；其中“当前／未部署／未实现”仅属于其快照。当前入口不得继续引用旧对账作为现行结论。跨域规则由唯一拥有者维护，消费者链接引用。

## 证据与依赖

证据至少包含CAP、规格版本、源码提交及脏工作区补丁／哈希、环境、时间、命令、退出码、覆盖AC、限制和原始记录。静态检查只说明结构一致，不能证明运行、模型质量、业务库启用或发布。

依赖区分data-owner、platform-runtime、optional-runtime与delivery-blocking。任务只因真实必要依赖失败而停止；可选依赖失败不得伪装成没有记录。订单查询、商品推荐、知识问答和偏好任务各自声明依赖，认证和对象归属始终为必要条件。

实施后按本规格对照差异，取得新证据再更新verificationStatus；部署独立更新deploymentStatus。不引入自动阶段工具，不放宽根仓库Git门禁。
