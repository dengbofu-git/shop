"""Render paired records and separately stored human answer reviews."""
import argparse
import json
from pathlib import Path


def pct(value):
    return '—' if value is None else '{:.1%}'.format(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    args = parser.parse_args()
    root = Path(args.run_dir).resolve()
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    summary = json.loads((root/'run-summary.json').read_text(encoding='utf-8'))
    manual = json.loads((root/'manual-review.json').read_text(encoding='utf-8'))
    records = [json.loads(line) for line in (root/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    pairs = {(r['case_id'],r['arm']):r for r in records}
    assert len(records)==30 and len(pairs)==30
    for case in manifest['cases']:
        for arm in ('single_query','rewrite'):
            assert str(case['id']) in manual['cases'] and arm in manual['cases'][str(case['id'])]
    a,b = summary['arms']['single_query'],summary['arms']['rewrite']
    dialogue = ['# 真实模型对照：30次完整问答','',
        'A=同一Agent关闭查询改写，使用旧单查询检索；B=同一Agent启用0.9.0查询链路。',
        '以下回答直接来自原始JSONL，不用修改后的答案替换。每题独立公开会话，未传入真实客户历史。','']
    report = ['# Agent 0.9.0 RAG真实模型对照','',
        '## 设计','',
        '- 15题，每题A/B各运行一次，共30次；AB/BA交替，不选择性重跑或替换失败结果。',
        '- 固定DeepSeek deepseek-flash、thinking disabled、配置修订3；本地BGE-M3、bge-reranker-v2-m3，候选30/证据5。',
        '- A关闭新查询链路；旧检索函数正文与保存的0.8.1源码AST一致。B启用当前默认查询链路。其他Agent逻辑相同，属于查询链路对照，并非整个系统版本回滚。',
        '- B默认中文/英文目标、首轮最多4路、补检最多2路一次、改写模型最多2次、每次5秒。未为本测试调长超时。',
        '- 运行前固定15个输入、支持片段组和相关片段标签。当前公开库50个英文片段；只读真实向量库。',
        '- 知识复核依据本库原文，没有独立访问来源网站核验。未覆盖多语言正文混合知识库和真实买家权限。','',
        '## 自动指标','',
        '| 指标 | A 单查询 | B 查询改写 |','|---|---:|---:|',
        f"| 正常返回 | {a['returned_turns']}/15 | {b['returned_turns']}/15 |",
        f"| 最终证据支持点覆盖 | {a['support_groups_hit']}/{a['support_groups_total']}（{pct(a['support_group_coverage'])}） | {b['support_groups_hit']}/{b['support_groups_total']}（{pct(b['support_group_coverage'])}） |",
        f"| 可用支持点全部找到的题数 | {a['all_available_support_cases']}/{a['support_eligible_cases']} | {b['all_available_support_cases']}/{b['support_eligible_cases']} |",
        f"| 预标注相关片段占比（逐题宏平均） | {pct(a['macro_labelled_relevant_precision'])} | {pct(b['macro_labelled_relevant_precision'])} |",
        f"| 平均整轮耗时 | {a['mean_seconds']:.3f}s | {b['mean_seconds']:.3f}s |",
        f"| 中位整轮耗时 | {a['median_seconds']:.3f}s | {b['median_seconds']:.3f}s |",
        f"| 模型调用 | {a['model_calls']} | {b['model_calls']} |",
        f"| 输入Token | {a['input_tokens']:,} | {b['input_tokens']:,} |",
        f"| 输出Token | {a['output_tokens']:,} | {b['output_tokens']:,} |",
        f"| 实际向量查询次数 | {a['vector_searches']} | {b['vector_searches']} |",
        f"| 实际补检/采用补检题数 | {a['retry_cases']}/{a['retry_adopted_cases']} | {b['retry_cases']}/{b['retry_adopted_cases']} |",'',
        '支持点覆盖按预先列出的可用片段组计算，不是答案准确率：一组中至少命中一段即可。第5–7题只对库中存在的沙特习俗计算支持点，不会把不存在的阿联酋资料算成可召回目标；第13题无配方证据，不参加召回指标。',
        '相关片段占比只统计预标注的直接相关片段，其他背景资料可能仍有辅助价值。所有标签及原文均可在manifest.json和corpus.json复核。','',
        '## 人工回答复核','',*manual['summary'], '',
        '## 逐题结果','',
        '| # | 问题 | 支持点 A→B | 人工判断 A→B | 耗时秒 A→B | 分析 |','|---|---|---|---|---|---|']
    for case in manifest['cases']:
        ra, rb = (pairs[(case['id'],arm)] for arm in ('single_query','rewrite'))
        ma, mb = (manual['cases'][str(case['id'])][arm] for arm in ('single_query','rewrite'))
        cov = lambda r:'{}/{}'.format(r['evidence_metrics']['support_groups_hit'],r['evidence_metrics']['support_groups_total']) if r['evidence_metrics']['support_groups_total'] else '无证据题'
        report.append('| {} | {} | {}→{} | {}→{} | {:.2f}→{:.2f} | {} |'.format(
            case['id'],case['message'],cov(ra),cov(rb),ma['verdict'],mb['verdict'],
            ra.get('elapsed_seconds',0),rb.get('elapsed_seconds',0),manual['cases'][str(case['id'])]['analysis']))
        dialogue += ['## {:02d} · {}'.format(case['id'],case['scene']),'', '**用户：** '+case['message'],'',
            '预先固定目标：'+case['answer_goal'],'']
        for arm, row, review in (('single_query',ra,ma),('rewrite',rb,mb)):
            dialogue += ['### '+('A · 单查询' if arm=='single_query' else 'B · 查询改写'),'',
                row.get('response',{}).get('answer','[无正常回答]'),'',
                '**人工复核：** '+review['verdict']+'；'+review['reason'],'',
                '耗时 {}s；模型调用 {}；Token 输入 {} / 输出 {}。'.format(row.get('elapsed_seconds'),row.get('model_calls'),row.get('input_tokens'),row.get('output_tokens')),'',
                '最终支持点指标：`'+json.dumps(row['evidence_metrics'],ensure_ascii=False)+'`。','',
                '查询与补检实际记录：','', '```json',json.dumps(row.get('retrieval',[]),ensure_ascii=False,indent=2),'```','',
                '实际来源：','']
            dialogue += ['- [{}]({})'.format(s['title'],s['url']) for s in row.get('response',{}).get('knowledge_sources',[])]
            dialogue += ['']
    report += ['', '## 改写与补检表现','', *manual['mechanism_analysis'],'',
               '## 已知问题与后续顺序','',*manual['recommendations'],'',
               '## 完整性与限制','',
               '- 生产源码哈希前后一致：{}；公开知识快照前后一致：{}。'.format(summary['source_unchanged'],summary['corpus_unchanged']),
               '- 业务表起始计数：`'+json.dumps(summary['business_counts_before'])+'`；结束计数：`'+json.dumps(summary['business_counts_after'])+'`。本执行器使用不提交业务会话的PreviewSession，遥测关闭；若其他页面同时使用系统，计数变化不能归因于本测试。',
               '- 单次配对、小样本且部分题目互为翻译，不能推断总体准确率或统计显著性；网络和答案长度影响整轮耗时。',
               '- Token仅汇总服务返回的usage；超时调用没有返回的用量不在统计中，不估算费用。',
               '- 阿拉伯文输入测试不要求输出阿拉伯文；目标检索翻译仍为默认中英。',
               '- 未修改线上参数或生产代码，保留全部成功、失败和降级记录。','',
               '## 文件','',
               '- [完整30次实际问答](dialogues.md)',
               '- [原始记录及中间证据](results.jsonl)',
               '- [输入、支持片段标签及配置](manifest.json)',
               '- [公开知识快照](corpus.json)',
               '- [机器汇总](run-summary.json)',
               '- [第14题本地重排序复算](case14-rank-diagnostic.json)',
               '- [人工复核](manual-review.json)','']
    (root/'dialogues.md').write_text('\n'.join(dialogue),encoding='utf-8')
    (root/'report.md').write_text('\n'.join(report),encoding='utf-8')
    print('Wrote dialogues.md and report.md')


if __name__=='__main__':
    main()
