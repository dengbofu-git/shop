"""Offline, read-only scoring diagnostic against a captured public candidate set.

Run in the reranker image with its model cache mounted read-only. No application
configuration, business records, traces or model files are modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import requests
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REVISION = '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--service-url', required=True)
    parser.add_argument('--supplement', action='store_true', help='Append language controls to an existing result')
    args = parser.parse_args()
    captured = json.loads(Path(args.input).read_text(encoding='utf-8'))
    docs = captured['candidates']
    by_id = {row['chunk_id']: row for row in docs}
    snapshot = '/models/hub/models--BAAI--bge-reranker-v2-m3/snapshots/' + REVISION
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    torch.set_num_threads(4)
    model = AutoModelForSequenceClassification.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False, use_safetensors=True,
    ).eval()
    query = captured['query']
    query_ids = tokenizer.encode(query, add_special_tokens=False)
    roundtrip = tokenizer.decode(query_ids[:96], skip_special_tokens=True)
    print(json.dumps({'query': query, 'roundtrip': roundtrip, 'changed': roundtrip != query}, ensure_ascii=False), flush=True)

    def reference(q, items, size=4):
        scores, lengths, started = [], [], time.perf_counter()
        with torch.inference_mode():
            for index in range(0, len(items), size):
                batch_items = items[index:index + size]
                inputs = tokenizer([[q, row['text']] for row in batch_items], padding=True,
                                   truncation=True, max_length=512, return_tensors='pt')
                lengths.extend(inputs['attention_mask'].sum(dim=1).tolist())
                scores.extend(torch.sigmoid(model(**inputs).logits.view(-1).float()).tolist())
        return {'scores': [{'chunk_id': row['chunk_id'], 'score': value, 'tokens': length}
                           for row, value, length in zip(items, scores, lengths)],
                'duration_ms': round((time.perf_counter() - started) * 1000, 2)}

    def production(q, items):
        result = requests.post(args.service_url.rstrip('/') + '/rerank',
                               json={'model': 'BAAI/bge-reranker-v2-m3', 'query': q,
                                     'documents': [{'index': i, 'text': d['text']} for i, d in enumerate(items)],
                                     'deadline_ms': 30000}, timeout=(3, 35))
        result.raise_for_status()
        data = result.json()
        return {'scores': [{'chunk_id': items[row['index']]['chunk_id'], 'score': row['score'],
                            'excerpt_matches_full_text': row['excerpt'] == items[row['index']]['text'],
                            'excerpt': row['excerpt']} for row in data['results']],
                'duration_ms': data['duration_ms'], 'windows': data['windows']}

    sample = [by_id[key] for key in [65, 66, 68, 81, 78, 79]]
    if args.supplement:
        result = json.loads(Path(args.output).read_text(encoding='utf-8'))
        result['language_cases']['zh_bilingual_anchor'] = dict(reference(query + ' (green tea)', sample), query=query + ' (green tea)')
        result['language_cases']['en_explicit'] = dict(reference('What is green tea and how is it processed?', sample), query='What is green tea and how is it processed?')
        translations = [
            {'chunk_id': 65, 'text': '绿茶以鲜叶为原料，通过快速加热钝化酶，然后揉捻、整形或粉碎并干燥。其加工不包含红茶那样有意的通气氧化。加热方式和形状因地区和产品而异。'},
            {'chunk_id': 66, 'text': '白茶以采摘的茶树嫩梢为原料，经过萎凋和干燥阶段制成。白茶是茶树茶类和加工工艺，并非用白色花朵或草本植物冲泡的饮品。'},
            {'chunk_id': 68, 'text': '黄茶加工包括杀青钝化酶、揉捻或整形、闷黄及干燥。闷黄是区别性步骤。黄茶是茶树六大基本茶类之一。'},
        ]
        result['synthetic_translation_control'] = dict(reference(query, translations),
            note='Diagnostic translations only; not knowledge-base edits', documents=translations)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: result['language_cases'][key] for key in ['zh_bilingual_anchor', 'en_explicit']}, ensure_ascii=False), flush=True)
        print(json.dumps(result['synthetic_translation_control'], ensure_ascii=False), flush=True)
        return
    result = {'trace_id': captured['previous_trace'], 'torch': torch.__version__,
              'query': query, 'roundtrip_query': roundtrip, 'roundtrip_changed': roundtrip != query,
              'query_ids': query_ids, 'query_tokens': tokenizer.convert_ids_to_tokens(query_ids),
              'model_class': type(model).__name__, 'dtype': str(next(model.parameters()).dtype),
              'tokenizer_class': type(tokenizer).__name__,
              'candidate_hashes': [{'chunk_id': d['chunk_id'], 'sha256': hashlib.sha256(d['text'].encode()).hexdigest()} for d in docs]}
    def checkpoint():
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    result['reference_original_all'] = reference(query, docs)
    checkpoint()
    result['production_original_all'] = production(query, docs)
    checkpoint()
    result['reference_roundtrip_sample'] = reference(roundtrip, sample)
    result['reference_original_sample'] = reference(query, sample)
    result['reference_original_individual'] = reference(query, sample, size=1)
    result['reference_original_reversed'] = reference(query, list(reversed(sample)), size=3)
    checkpoint()
    result['language_cases'] = {}
    for name, text in [('zh_keyword', '绿茶'), ('zh_explicit', '绿茶是什么？请介绍绿茶的制作工艺。'),
                       ('en', 'Introduce green tea.'), ('ar', 'ما هو الشاي الأخضر وكيف تتم صناعته؟')]:
        result['language_cases'][name] = dict(reference(text, sample), query=text)
        checkpoint()
    encoded = tokenizer([[query, by_id[65]['text']]], padding=False)
    result['pair_input'] = {key: value[0] for key, value in encoded.items()}
    # Explicit two-argument form to compare with the pair-list form used in production.
    result['explicit_pair_input'] = dict(tokenizer(query, by_id[65]['text'], padding=False))
    result['pair_tokens'] = tokenizer.convert_ids_to_tokens(result['explicit_pair_input']['input_ids'])
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': args.output, 'roundtrip_changed': result['roundtrip_changed'],
                      'query': query, 'roundtrip_query': roundtrip,
                      'reference_sample': result['reference_original_sample']['scores'],
                      'production_windows': result['production_original_all']['windows']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
