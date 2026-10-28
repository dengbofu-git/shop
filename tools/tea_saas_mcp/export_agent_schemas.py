"""Generate the SDK schema artifact with the Django Python, without DB access."""
import json
from pathlib import Path

from support_ai.mcp_contracts import ARGUMENTS

DESCRIPTIONS = {
    'get_conversation_context': 'Read the bound buyer conversation model projection, limited to the configured recent window.',
    'get_saved_preferences': 'Read only the authenticated buyer explicit saved preferences; unavailable is not empty.',
    'validate_categories': 'Check public category names against the catalog; accepts no query expressions.',
    'search_products': 'Match validated product intent using fixed public saleable filters, flat or bounded category groups.',
    'recommend_bundle': 'Compute bounded product bundles and exact CNY subtotals with fixed backend rules.',
    'resolve_product': 'Resolve an exact historical public SKU name pair only when unique.',
    'get_product_details': 'Read current allowlisted public fields of a specific saleable SKU.',
    'get_order_status': 'Read bound buyer orders with trusted current-turn constraints; no private IDs in result.',
    'explain_recommendations': 'Refresh public facts for a bound previous product list without searching for replacements.',
    'search_knowledge': 'Retrieve published, ACL-filtered evidence using bounded hybrid recall and reranking.',
}


def content():
    return json.dumps({name:{'description':DESCRIPTIONS[name], 'input':schema.model_json_schema()}
                       for name, schema in ARGUMENTS.items()}, ensure_ascii=False, indent=2) + '\n'


if __name__ == '__main__':
    target = Path(__file__).with_name('agent_schemas.json')
    target.write_text(content(), encoding='utf-8')
