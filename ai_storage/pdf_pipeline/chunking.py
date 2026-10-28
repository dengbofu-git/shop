"""Sentence/heading aware chunks with exact offsets back to immutable page blocks."""
from collections import Counter
import re

CHUNKER_VERSION = 'structure-token-v2'


def make_chunks(pages, tokenizer, target=500, maximum=800, overlap=64):
    def tokens(text):
        return len(tokenizer.encode(text, add_special_tokens=False).ids)
    repeated = Counter()
    for page in pages:
        edges = set()
        for block in page.blocks:
            if block['bbox'][1] < page.height * .08 or block['bbox'][3] > page.height * .92:
                edges.add(' '.join(block['text'].split()))
        repeated.update(edges)
    parts, heading, output = [], '', []

    def emit(separator='\n\n'):
        if not parts:
            return
        text, mappings = '', []
        for part in parts:
            if text:
                text += separator
            start = len(text)
            text += part['text']
            mappings.append({**{k: v for k, v in part.items() if k != 'text'},
                             'chunk_start': start, 'chunk_end': len(text)})
        output.append({'text': text, 'metadata': {'page_start': min(p['page'] for p in parts),
            'page_end': max(p['page'] for p in parts), 'section_path': [heading] if heading else [],
            'mappings': mappings, 'token_count': tokens(text), 'chunker_version': CHUNKER_VERSION}})

    def bounded(text, start=0):
        # Slice original characters using tokenizer offsets; never decode/rewrite OCR.
        encoded = tokenizer.encode(text, add_special_tokens=False)
        if len(encoded.ids) <= maximum:
            return [(start, text)]
        result, position = [], 0
        while position < len(text):
            tail = text[position:]
            encoded = tokenizer.encode(tail, add_special_tokens=False)
            end = encoded.offsets[min(target, len(encoded.ids)) - 1][1]
            if end <= 0:
                raise ValueError('Tokenizer did not advance')
            result.append((start + position, tail[:end]))
            position += end
        return result

    for page in pages:
        for block in page.blocks:
            raw = block['text']
            if not block.get('indexable', True):
                continue
            if block.get('kind') in ('table', 'figure'):
                emit()
                parts = []
                if block['kind'] == 'table':
                    header, rows = block['table']['header'], block['table']['rows']
                    if raw != header + '\n' + '\n'.join(rows):
                        raise ValueError('VISION_TABLE_TEXT_MISMATCH')
                    groups, current, offset = [], [], len(header) + 1
                    for row in rows:
                        if tokens(header + '\n' + row) > maximum:
                            raise ValueError('VISION_TABLE_ROW_TOO_LARGE')
                        if current and tokens(header + '\n' + '\n'.join(x[0] for x in current) + '\n' + row) > target:
                            groups.append(current)
                            current = []
                        current.append((row, offset))
                        offset += len(row) + 1
                    if current:
                        groups.append(current)
                    fragments = []
                    for group in groups:
                        fragments.append([(header, 0)] + group)
                else:
                    fragments = [[(text, start)] for start, text in bounded(raw)]
                for fragment in fragments:
                    for text, start in fragment:
                        parts.append({'text': text, 'page': page.number, 'block_id': block['id'],
                            'block_start': start, 'block_end': start + len(text), 'bbox': block['bbox'],
                            'method': block['method'], 'confidence': block.get('confidence'),
                            'extraction': block.get('extraction', {})})
                    emit(separator='\n')
                    parts = []
                    output[-1]['metadata']['content_kind'] = block['kind']
                continue
            if not raw.strip() or (raw.strip().isdigit() and len(raw.strip()) < 5):
                continue
            edge = block['bbox'][1] < page.height * .08 or block['bbox'][3] > page.height * .92
            if edge and repeated[' '.join(raw.split())] >= max(3, len(pages) // 2):
                continue
            if block.get('heading'):
                emit()
                parts = []
                heading = raw.strip()[:180]
            sentences = list(re.finditer(r'.+?(?:[。！？!?；;](?:\s|$)?|[.!?](?:\s+|$)|\n\s*\n|$)', raw, re.S))
            for sentence in sentences:
                for start, text in bounded(sentence.group(), sentence.start()):
                    candidate = {'text': text, 'page': page.number, 'block_id': block['id'],
                        'block_start': start, 'block_end': start + len(text), 'bbox': block['bbox'],
                        'method': block['method'], 'confidence': block.get('confidence')}
                    if block.get('extraction'):
                        candidate['extraction'] = block['extraction']
                    if parts and tokens('\n\n'.join(p['text'] for p in parts) + '\n\n' + text) > target:
                        emit()
                        tail = []
                        for old in reversed(parts):
                            if tokens('\n\n'.join(p['text'] for p in [old] + tail)) > overlap:
                                break
                            tail.insert(0, old)
                        parts = tail
                        if parts and tokens('\n\n'.join(p['text'] for p in parts) + '\n\n' + text) > maximum:
                            parts = []
                    parts.append(candidate)
    emit()
    return output
