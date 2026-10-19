"""Paired real-model replay against an immutable source and input baseline."""
import argparse
import copy
import hashlib
import importlib.util
import json
import statistics
import sys
import time
import traceback
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler


class Usage(BaseCallbackHandler):
    def __init__(self):
        self.calls = self.input_tokens = self.output_tokens = self.errors = 0
        self.structured_outputs = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.calls += 1

    def on_llm_error(self, error, **kwargs):
        self.errors += 1

    def on_llm_end(self, response, **kwargs):
        usage = None
        for group in response.generations:
            for item in group:
                usage = getattr(getattr(item, 'message', None), 'usage_metadata', None) or usage
                for call in getattr(getattr(item, 'message', None), 'tool_calls', []):
                    self.structured_outputs.append({'name': call['name'], 'args': call['args']})
        if usage:
            self.input_tokens += usage.get('input_tokens', 0)
            self.output_tokens += usage.get('output_tokens', 0)
        else:
            usage = (response.llm_output or {}).get('token_usage', {})
            self.input_tokens += usage.get('prompt_tokens', 0)
            self.output_tokens += usage.get('completion_tokens', 0)


def load_snapshot(name, path):
    spec = importlib.util.spec_from_file_location('support_ai._baseline_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def evaluate_case(case, response):
    expected = case['expected_intents']
    actual = response.get('intents', [response.get('intent', 'error')])
    cards = response.get('recommendations', [])
    recommendation_ok = None
    if 'recommendation' in expected:
        recommendation_ok = ('recommendation' in actual and 1 <= len(cards) <= case['expected_max_products']
                             and (not case.get('expected_category') or all(c['category'] == case['expected_category'] for c in cards)))
    wanted, received = set(expected), set(actual)
    return {'intent_exact': actual == expected, 'intent_set_exact': received == wanted,
            'true_positive': len(wanted & received), 'false_positive': len(received - wanted),
            'false_negative': len(wanted - received), 'recommendation_constraints_ok': recommendation_ok}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='reports/archive/2026-10-16/agent-evaluation/2026-10-16-planner')
    parser.add_argument('--output', default='paired-run-1.json')
    parser.add_argument('--case-id', action='append')
    parser.add_argument('--expected-database-name', required=True)
    args = parser.parse_args()
    root = Path(args.root)
    manifest = json.loads((root / 'baseline-manifest.json').read_text(encoding='utf-8'))
    for path, digest in manifest.items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Baseline modified: ' + path)
    fixture = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
    snapshot = json.loads((root / 'historical-records.json').read_text(encoding='utf-8'))
    from django.db import connection
    from support_ai.configuration import AgentConfig
    from support_ai.model_client import configured_model
    from support_ai.workflow import build_graph
    from support_ai.tool_services import create_tool_handlers
    from support_ai.retrieval import retrieve_knowledge
    from support_ai.contracts import validate_recommendation_intent
    from support_ai.models import SupportTurn, SupportConversation
    with connection.cursor() as cursor:
        cursor.execute('SELECT DATABASE(), @@server_uuid')
        if cursor.fetchone() != (args.expected_database_name, '6b35ae3b-0afa-11f1-808b-2632d3201c4a'):
            raise RuntimeError('Wrong MySQL target')
    legacy = load_snapshot('workflow_050', root / 'baseline-source/workflow.py')
    legacy_products = load_snapshot('recommendations_050', root / 'baseline-source/recommendations.py')
    config = AgentConfig(**snapshot['configuration'])
    output_path = root / args.output
    fingerprints = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in [
        'support_ai/workflow.py', 'support_ai/planning.py', 'support_ai/execution.py',
        'support_ai/tool_services.py', 'support_ai/recommendations.py']}
    result = json.loads(output_path.read_text(encoding='utf-8')) if output_path.exists() else {
        'protocol': fixture['protocol'], 'configuration': snapshot['configuration'],
        'candidate_source_sha256': fingerprints, 'cases_sha256': hashlib.sha256((root / 'cases.json').read_bytes()).hexdigest(),
        'initial_counts': {'turns': SupportTurn.objects.count(), 'conversations': SupportConversation.objects.count()}, 'runs': []}
    if result['candidate_source_sha256'] != fingerprints:
        raise RuntimeError('Candidate source changed; use a different output filename')
    if result['cases_sha256'] != hashlib.sha256((root / 'cases.json').read_bytes()).hexdigest():
        raise RuntimeError('Evaluation inputs changed; use a different output filename')
    for index, case in enumerate(fixture['cases']):
        if args.case_id and case['id'] not in args.case_id:
            continue
        versions = ['baseline_0.5.0', 'candidate_0.6.0'] if index % 2 == 0 else ['candidate_0.6.0', 'baseline_0.5.0']
        for version in versions:
            if any(r['case_id'] == case['id'] and r['version'] == version for r in result['runs']):
                continue
            usage = Usage()
            model = configured_model(config)
            state = {key: copy.deepcopy(case[key]) for key in ('message', 'recent_turns', 'memory', 'order_context')}
            state['owner_id'] = case['owner_id']
            retrieval_times = []
            tool_errors = []
            def search(query):
                started = time.perf_counter()
                values = retrieve_knowledge(query, case['owner_id'], config)
                retrieval_times.append({'query': query, 'ms': (time.perf_counter() - started) * 1000,
                                        'ids': [e['chunk_id'] for e in values]})
                return values
            if version == 'baseline_0.5.0':
                graph = legacy.build_graph(model, knowledge_search=lambda query, owner: search(query))
            else:
                def factory(s):
                    handlers = create_tool_handlers(model, search, s['safe_message'], s['resolved_question'],
                                                    s.get('recent_turns', []), case['memory'], case['order_context'])
                    def wrap(fn):
                        def call(step, completed):
                            try:
                                return fn(step, completed)
                            except Exception as exc:
                                tool_errors.append({'step': step.id, 'type': type(exc).__name__,
                                    'frames': [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                                               for f in traceback.extract_tb(exc.__traceback__)]})
                                raise
                        return call
                    return {k: wrap(v) for k, v in handlers.items()}
                graph = build_graph(model, tool_factory=factory)
            started = time.perf_counter()
            error = None
            try:
                generated = graph.invoke(state, config={'callbacks': [usage]})
                if version == 'candidate_0.6.0':
                    response = generated['response']
                else:
                    response = {'intent': generated['intent'], 'confidence': round(max(generated['scores'].values()), 2),
                                'recommendations': []}
                    if generated.get('clarification_required'):
                        response['answer'] = generated['answer']
                    elif generated['intent'] == 'recommendation':
                        intent = validate_recommendation_intent(generated['product_intent'], case['message'],
                                                                case['recent_turns'], case['memory'])
                        response.update(legacy_products.match_products(intent))
                        response['product_intent'] = intent.model_dump()
                    else:
                        response.update(answer=generated['answer'], knowledge_sources=generated.get('knowledge_sources', []))
                internal = {'plan': generated.get('plan'), 'tool_results': generated.get('tool_results'),
                            'scores': generated.get('scores'), 'resolved_question': generated.get('resolved_question')}
            except Exception as exc:
                error = type(exc).__name__
                response = {'intent': 'error', 'intents': ['error'], 'recommendations': [], 'answer': ''}
                internal = {}
            run = {'case_id': case['id'], 'group': case['group'], 'version': version,
                   'message': case['message'], 'expected_intents': case['expected_intents'],
                   'duration_ms': round((time.perf_counter() - started) * 1000, 2),
                   'llm_calls': usage.calls, 'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens,
                   'model_errors': usage.errors, 'error': error, 'response': response,
                   'tool_errors': tool_errors, 'structured_outputs': usage.structured_outputs,
                   'internal': internal, 'retrieval': retrieval_times, 'metrics': evaluate_case(case, response)}
            result['runs'].append(run)
            result['final_counts'] = {'turns': SupportTurn.objects.count(), 'conversations': SupportConversation.objects.count()}
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
            print(json.dumps({k: run[k] for k in ('case_id', 'version', 'duration_ms', 'llm_calls', 'error', 'metrics')}, ensure_ascii=False), flush=True)
    print('COMPLETED ' + str(output_path), flush=True)


if __name__ == '__main__':
    main()
