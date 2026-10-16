"""Replay the public mixed explanation/recommendation incident without business writes."""
import argparse
import json
import os
from pathlib import Path

QUESTION = '说明不同茶种的区别，给出具体说明的茶种的推荐商品'
FOLLOWUP = '我希望你能根据不同的茶叶种类给我进行一些商品推荐，并给出理由'


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dadashop.settings')
    import django
    django.setup()
    from support_ai.preview import PreviewSession
    from support_ai.models import SupportTurn, SupportConversation, AgentSpan
    root = Path(__file__).resolve().parents[2] / 'reports' / 'agent-evaluation' / '2026-10-16-mixed-tea'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(root / 'live-replay.json'))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        raise RuntimeError('Output exists; choose another file to preserve previous runs')
    counts = lambda: {'turns': SupportTurn.objects.count(), 'conversations': SupportConversation.objects.count(),
                      'spans': AgentSpan.objects.count()}
    before, rows = counts(), []
    session = PreviewSession(log_dir=root / 'after')
    for key, question in [('mixed_user_question', QUESTION), ('plain_group_followup', FOLLOWUP),
                          ('explicit_two_types', '说明绿茶和红茶的区别，并推荐对应商品')]:
        if key == 'explicit_two_types':
            session.new()
        try:
            row = dict(session.ask(question), case=key)
            response = row['response']
            print(json.dumps({'case': key, 'intents': response['intents'], 'tasks': response['tasks'],
                'explained_categories': response['explained_categories'], 'product_categories': [p['category'] for p in response['recommendations']],
                'elapsed_seconds': row['elapsed_seconds'], 'model_calls': row['model_calls'],
                'compliance_blocked': response['compliance_blocked'], 'answer': response['answer'][:180]}, ensure_ascii=False), flush=True)
        except Exception:
            row = dict(session.last_error, case=key)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    after = counts()
    output.write_text(json.dumps({'runtime': session.status(), 'business_counts_before': before,
                                 'business_counts_after': after, 'unchanged': before == after, 'records': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved: ' + str(output))
    print('Business counts unchanged: ' + str(before == after))


if __name__ == '__main__':
    main()
