"""Reject unprojected or malformed backend records before Agent consumption."""
import math

from .contracts import Preferences
from .order_contracts import OrderQueryData

FORBIDDEN = frozenset({'password','secret','api_key','cost_price','market_price','owner_id','user_id',
    'receiver','address','receiver_mobile','order_id','active_order_id','selected_order_id',
    'connection','sql','navigation_tokens'})
PUBLIC_DETAILS = frozenset({'sku_id','product_name','specification','category','price','currency','price_basis',
    'currency_source','available_stock','stock_source','attributes'})
HISTORY = frozenset({'turn_id','user_text','assistant_text','intent','budget_scope_evidence','dialogue_state',
    'product_references','recommendation_basis','recommendation_groups','explained_categories',
    'recommendation_bundles','primary_bundle_id','selected_bundle_id'})


def public_tree(value, depth=0):
    if depth > 24:
        raise ValueError('Backend result nesting limit')
    if isinstance(value, dict):
        if any(not isinstance(key,str) or key.casefold() in FORBIDDEN for key in value):
            raise ValueError('Backend returned a private field')
        for item in value.values():
            public_tree(item,depth+1)
    elif isinstance(value, list):
        for item in value:
            public_tree(item,depth+1)
    elif isinstance(value,float) and not math.isfinite(value):
        raise ValueError('Backend returned a nonfinite value')


def validate_data(tool, data):
    public_tree(data)
    if tool == 'get_product_details':
        if set(data) != PUBLIC_DETAILS or type(data['sku_id']) is not int or type(data['available_stock']) is not int:
            raise ValueError('Invalid public product DTO')
        if not isinstance(data['attributes'],list) or len(data['attributes']) > 50:
            raise ValueError('Invalid public attributes')
        allowed = {'attribute__name','value_text','value_number','value_boolean','value_date'}
        if any(not isinstance(row,dict) or set(row)-allowed for row in data['attributes']):
            raise ValueError('Invalid public attributes')
    elif tool == 'get_order_status':
        OrderQueryData.model_validate(data)
    elif tool == 'get_conversation_context':
        if set(data) != {'history'} or len(data['history']) > 6:
            raise ValueError('Invalid context projection')
        if any(not isinstance(row,dict) or set(row)-HISTORY for row in data['history']):
            raise ValueError('Unexpected history field')
    elif tool == 'get_saved_preferences':
        if set(data) != {'memory'}:
            raise ValueError('Invalid preference projection')
        memory = data['memory']
        if memory is not None:
            if set(memory) != {'id','preferences'} or not isinstance(memory['id'],str):
                raise ValueError('Invalid preference projection')
            Preferences.model_validate(memory['preferences'])
    elif tool == 'resolve_product':
        if set(data) != {'sku_id'} or (data['sku_id'] is not None and type(data['sku_id']) is not int):
            raise ValueError('Invalid public identity')
    elif tool == 'validate_categories':
        if set(data) != {'valid'} or type(data['valid']) is not bool:
            raise ValueError('Invalid category result')
    elif tool == 'search_knowledge':
        if set(data) != {'evidence','notes','audit'} or not isinstance(data['notes'],list) or not isinstance(data['audit'],list):
            raise ValueError('Invalid knowledge DTO')
        if any(not isinstance(row,dict) or not isinstance(row.get('text'),str) for row in data['evidence']):
            raise ValueError('Invalid evidence DTO')
