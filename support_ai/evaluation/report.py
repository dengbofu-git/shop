"""Summarize paired outputs without changing source observations."""
import json
import statistics
from pathlib import Path


ROOT = Path('reports/agent-evaluation/2026-10-16-planner')


def summarize(rows):
    times = sorted(r['duration_ms'] for r in rows)
    tp = sum(r['metrics']['true_positive'] for r in rows)
    fp = sum(r['metrics']['false_positive'] for r in rows)
    fn = sum(r['metrics']['false_negative'] for r in rows)
    position = (len(times) - 1) * .95
    low = int(position)
    p95 = times[low] + (times[min(low + 1, len(times) - 1)] - times[low]) * (position - low)
    return {'cases': len(rows), 'intent_exact_correct': sum(r['metrics']['intent_exact'] for r in rows),
            'intent_exact_accuracy': sum(r['metrics']['intent_exact'] for r in rows) / len(rows),
            'micro_precision': tp / (tp + fp) if tp + fp else 0,
            'micro_recall': tp / (tp + fn) if tp + fn else 0,
            'micro_f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
            'recommendation_constraints_correct': sum(r['metrics']['recommendation_constraints_ok'] is True for r in rows),
            'recommendation_cases': sum(r['metrics']['recommendation_constraints_ok'] is not None for r in rows),
            'mean_ms': statistics.mean(times), 'median_ms': statistics.median(times), 'p95_ms': p95,
            'llm_calls': sum(r['llm_calls'] for r in rows), 'input_tokens': sum(r['input_tokens'] for r in rows),
            'output_tokens': sum(r['output_tokens'] for r in rows),
            'top_level_errors': sum(bool(r['error']) for r in rows),
            'tool_errors': sum(t['status'] == 'error' for r in rows for t in r['internal'].get('tool_results') or [])}


def main():
    data = json.loads((ROOT / 'paired-final.json').read_text(encoding='utf-8'))
    fixtures = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']
    old = [r for r in data['runs'] if r['version'] == 'baseline_0.5.0']
    new = [r for r in data['runs'] if r['version'] == 'candidate_0.6.0']
    stats = {'baseline_0.5.0': summarize(old), 'candidate_0.6.0': summarize(new)}
    (ROOT / 'summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    a, b = stats.values()
    lines = ['# Agent 有序多任务策略对照报告', '', '日期：2026-10-16（Asia/Shanghai）。', '',
        '## 结论', '',
        '冻结的昨晚 11 个输入中，当前 0.5.0 回放的有序任务完全匹配率为 4/11，修正版 0.6.0 为 11/11。6 个含推荐的输入，按返回非空、数量上限及已标注分类检查，分别为 2/6 和 6/6。', '',
        '**这是已知问题样例上的回归结果，不是独立测试集准确率，也不是商品用途、口感或知识事实正确率。**', '',
        '## 测试口径', '',
        '- 原始输入、原有历史窗口、重建后的偏好、DeepSeek 模型及配置、商品库相同。模型为 deepseek-flash，thinking=disabled，配置修订 3。',
        '- 两版每个样例交替先后运行，均真实调用本地向量检索/重排序及配置的模型；纯规则路径允许不调用模型。延迟从执行图 invoke 开始，含工具调用及旧版应用侧商品查询，不含 HTTP、前端、执行图构造。',
        '- 采用固定历史回放：每次注入历史记录中的前文，不注入另一版新生成的答案。没有向业务对话表写入测试回答。',
        '- 历史偏好缺少完整审计，由已保存 MEMORY 证据重建并沿用；该近似对两版相同。每版每样例一次，temperature=0 不保证服务端输出完全确定。',
        '- 有序任务完全匹配要求任务集合与顺序均正确；多意图微平均 P/R/F1 按任务集合计算。推荐指标只检查可售候选、数量和标注分类，不证明个性化排序最优。', '',
        '## 最终同输入对照', '',
        '| 指标 | 修改前 0.5.0 | 修正版 0.6.0 |', '|---|---:|---:|',
        f"| 有序任务完全匹配 | {a['intent_exact_correct']}/11（{a['intent_exact_accuracy']:.1%}） | {b['intent_exact_correct']}/11（{b['intent_exact_accuracy']:.1%}） |",
        f"| 多意图微平均 Precision | {a['micro_precision']:.1%} | {b['micro_precision']:.1%} |",
        f"| 多意图微平均 Recall | {a['micro_recall']:.1%} | {b['micro_recall']:.1%} |",
        f"| 多意图微平均 F1 | {a['micro_f1']:.1%} | {b['micro_f1']:.1%} |",
        f"| 推荐返回及数量/分类约束 | {a['recommendation_constraints_correct']}/6 | {b['recommendation_constraints_correct']}/6 |",
        f"| 平均耗时 | {a['mean_ms']/1000:.2f} 秒 | {b['mean_ms']/1000:.2f} 秒 |",
        f"| 中位耗时 | {a['median_ms']/1000:.2f} 秒 | {b['median_ms']/1000:.2f} 秒 |",
        f"| 样本 P95（线性插值） | {a['p95_ms']/1000:.2f} 秒 | {b['p95_ms']/1000:.2f} 秒 |",
        f"| 模型调用总数 | {a['llm_calls']} | {b['llm_calls']} |",
        f"| 输入 Token | {a['input_tokens']} | {b['input_tokens']} |",
        f"| 输出 Token | {a['output_tokens']} | {b['output_tokens']} |",
        f"| 顶层异常 / 工具异常 | {a['top_level_errors']} / {a['tool_errors']} | {b['top_level_errors']} / {b['tool_errors']} |", '',
        '## 逐条路由', '', '| 样例 | 输入 | 预期顺序 | 0.5.0 实际 | 0.6.0 实际 |', '|---|---|---|---|---|']
    for case in fixtures:
        x = next(r for r in old if r['case_id'] == case['id'])
        y = next(r for r in new if r['case_id'] == case['id'])
        lines.append('| {} | {} | {} | {} | {} |'.format(case['id'], case['message'],
            ' → '.join(case['expected_intents']), ' → '.join(x['response'].get('intents', [x['response']['intent']])),
            ' → '.join(y['response']['intents'])))
    lines += ['', '## 性能解释', '',
        '不能宣称本次修改整体更快。旧版将多个知识问题错误送入推荐或澄清路径，省略了本地向量化、CPU 重排序和知识回答；新版现在实际执行这些任务，因此总体平均耗时上升。',
        '模型调用总数下降，但知识证据和更完整的回答增加了 Token，用量并未随调用次数同比下降。简单品类推荐由确定性槽位及实时 SQL 完成，可以不调用模型。', '',
        '## 尚未解决的质量问题', '',
        '- “适合日常饮用”缺少商品属性证据。新版按红茶筛选并限制为一款，明确说明无法验证适用性；没有证明其排序或 320 美元礼盒适合日常饮用。',
        '- 知识回答仍偏长，并会出现额外选购提示；“介绍各种茶叶”未完整展开各茶类的风味与冲泡，受知识证据覆盖限制。任务路由正确不代表介绍已经充分。',
        '- 中文问题匹配英文知识的重排序偏差仍存在，相关评分不能作为事实正确率。',
        '- 规则覆盖已知表达，其他语言、反讽、嵌套否定、引用式表达等仍需独立样本验证；没有对整个模型的通用语义能力作保证。', '',
        '## 保存及迭代记录', '',
        '- 历史日志（0.4.0 观察）：5 个知识介绍请求仅 1 个进入 QA；排除混合请求，单意图路由 6/10；严格完整任务口径 6/11。它与上表的 0.5.0 回放是不同版本和不同观察，不能混用。',
        '- baseline-source、historical-records、baseline-manifest、cases 保留原样；paired-final.json 为最终完整 22 次回放。',
        '- paired-run-1.json 是评测快照加载/执行图编译阶段的未完成运行；paired-run-2.json、paired-run-3.json 保留开发阶段完整结果，包含已发现的推荐证据格式失败。diagnostic-pair.json 为单样例诊断，不混入最终指标。',
        '- 最终实现对简单品类及宽泛购买请求使用服务端槽位与已验证偏好；复杂预算、品牌、排除条件仍进入模型提取并经过证据校验。未放宽硬条件的证据检查。',
        '- 最终 64 项自动化测试通过；旧测试先保存，再按新任务契约更新断言。覆盖原有权限、幂等、库存、预算、脱敏、监控及新增顺序依赖、非法工具、失败跳过、订单续问和偏好校验。',
        f"- 评测前后业务对话数量：{data['initial_counts']} → {data['final_counts']}。", '',
        '## 复现入口', '',
        '配置已认证的本地运行环境后执行 `python -m support_ai.evaluation.compare --output <新的运行文件.json>`。保留基线文件，使用新文件名保存每轮完整结果；生成报告执行 `python -m support_ai.evaluation.report`。',
        '真实历史回放会向配置的模型服务发送脱敏历史，执行前需具备该数据用途授权。报告生成程序不调用模型。', '']
    (ROOT / 'comparison-report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
