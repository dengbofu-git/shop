"""Source DTO shared by retrieval and rendering; no local filesystem paths."""


def source_details(item):
    metadata = item.get('metadata', {})
    result = {'title': item.get('source_title', '资料'), 'url': item.get('source_reference', ''),
              'year': metadata.get('year')}
    if metadata.get('page_start') is not None:
        result.update(document_id=item.get('document_id'), chunk_id=item.get('chunk_id'),
            version=item.get('document_version'), page_start=metadata['page_start'], page_end=metadata['page_end'],
            mapping_basis='stored_chunk_unicode_codepoints',
            extraction_methods=sorted({m['method'] for m in metadata.get('mappings', [])}),
            mappings=metadata.get('mappings', []))
    return result


def source_label(source):
    text = source['title'] + ('（{}）'.format(source['year']) if source.get('year') else '')
    if source.get('page_start') is not None:
        text += '，第{}—{}页，版本{}'.format(source['page_start'], source['page_end'], source['version'])
    return text
