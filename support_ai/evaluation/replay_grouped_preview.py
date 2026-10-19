"""Replay the public preview incident without committing customer conversations.

Run with the project Python: python -m support_ai.evaluation.replay_grouped_preview
"""
import json
import os
import argparse
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tea_saas.settings')
    import django
    django.setup()
    from support_ai.preview import PreviewSession
    from support_ai.models import SupportTurn, SupportConversation, AgentSpan
    root = Path(__file__).resolve().parents[2] / 'reports' / 'agent-evaluation' / '2026-10-16-grouping'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(root / 'live-replay-final.json'))
    args = parser.parse_args()
    output_path = Path(args.output).resolve()
    if output_path.exists():
        raise RuntimeError('Final replay already exists; preserve it and choose a new run file')
    source = root / 'before' / '20261016-114613-cf6a9b60bb8047dead1a4663ec911451.jsonl'
    rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()]
    if rows[0]['configuration']['scope'] != 'public':
        raise RuntimeError('This incident replay only supports the captured public preview')
    question = next(r['message'] for r in reversed(rows) if r['event'] == 'error')
    counts = lambda: {'turns': SupportTurn.objects.count(), 'conversations': SupportConversation.objects.count(),
                      'spans': AgentSpan.objects.count()}
    before, records = counts(), []
    session = PreviewSession(log_dir=root / 'after-final')
    session.turns = [SimpleNamespace(pk='baseline-' + str(r['sequence']), user_text=r['message'],
                       answer=r['response']['answer'], intent=r['response']['intent'], response=r['response'],
                       created_at=datetime.fromisoformat(r['created_at'])) for r in rows if r['event'] == 'turn']
    cases = [('original_question', question), ('repeat_original', question),
             ('group_followup', '第二类的商品多少钱'), ('sixth_product_followup', '第六款商品多少钱'),
             ('single_category', '推荐两款绿茶'),
             ('budget_and_exclusion', '请按不同茶类推荐商品，每盒单价不超过15美元，不要红茶，并给出理由')]
    for key, message in cases:
        try:
            record = dict(session.ask(message), case=key)
            response = record['response']
            print(json.dumps({'case': key, 'intents': response['intents'], 'tasks': response['tasks'],
                  'cards': len(response['recommendations']), 'groups': [g['category'] for g in response.get('recommendation_groups', [])],
                  'elapsed_seconds': record['elapsed_seconds'], 'model_calls': record['model_calls'],
                  'compliance_blocked': response['compliance_blocked'], 'answer': response['answer'][:100]}, ensure_ascii=False), flush=True)
        except Exception:
            record = dict(session.last_error, case=key)
            print(json.dumps(record, ensure_ascii=False), flush=True)
        records.append(record)
    after = counts()
    output_path.write_text(json.dumps({'baseline_log': str(source), 'runtime': session.status(),
        'business_counts_before': before, 'business_counts_after': after, 'unchanged': before == after,
        'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved: ' + str(output_path))
    print('Business history unchanged: ' + str(before == after))


if __name__ == '__main__':
    main()
