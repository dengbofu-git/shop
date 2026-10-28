"""Trusted Django data service, used only behind the MCP protocol adapter."""
import time

from django.db import close_old_connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from goods.models import Catalog
from users.models import UserProfile
from .configuration import AgentConfig
from .context import ConversationConflict, recent_context, saved_preferences, select_bundle_context
from .contracts import validate_recommendation_intent, validate_recommendation_branch
from .cost_control import RequestBudget, CostPolicy, bind_budget
from .mcp_contracts import ARGUMENTS
from .mcp_security import AccessDenied, read_private, write_private, verify_grant
from .models import SupportConversation
from .order_queries import OrderQueryContext, query_orders
from .planning import explicit_requests
from .product_details import get_product_details
from .recommendations import CATEGORY_ALIASES, match_products, match_product_groups, available_products
from .bundle_recommendations import recommend_bundle
from .recommendation_explanations import explain_existing_products
from .retrieval import KnowledgeRetriever
from .query_rewrite import QueryPolicy


def order_request(message, quote):
    anchors = explicit_requests(message)
    anchor = next((r for r in anchors if r.kind == 'after_sales'), None)
    request = message
    for other in anchors:
        if (other.kind != 'after_sales' and quote not in other.quote
                and (anchor is None or anchor.quote not in other.quote)):
            request = request.replace(other.quote, ' ', 1)
    return request


def envelope(status='success', data=None, **extra):
    return dict(schema_version='1.0', status=status, data=data,
                observed_at=timezone.now().isoformat(), limitations=[], **extra)


def failure(code):
    return envelope('error', None, error_code=code,
                    retryable=code in ('SERVICE_UNAVAILABLE', 'BACKEND_TIMEOUT'))


class DataSession:
    """A single grant, identity, deadline, retriever and strictly increasing sequence."""
    def __init__(self, token):
        self.grant = verify_grant(token)
        self.sequence = 0
        self.history = None
        self.memory = None
        self.memory_loaded = False
        self.retriever = None
        self.config = AgentConfig(**self.grant['config'])
        self.order_context = OrderQueryContext(
            owner_id=self.grant['owner_id'], conversation_id=self.grant['conversation_id'],
            references=self.grant['references'], **self.grant.get('order_binding', {}))
        if isinstance(self.order_context.active_order_at, str):
            self.order_context.active_order_at = parse_datetime(self.order_context.active_order_at)

    def authorize(self):
        if time.time() >= self.grant['expires_at'] or self.sequence > 40:
            raise AccessDenied('MCP request expired')
        owner = self.grant['owner_id']
        user = UserProfile.objects.filter(pk=owner, is_active=True).first() if owner is not None else None
        if owner is not None and (user is None or not user.is_customer()):
            raise AccessDenied('MCP buyer no longer authorized')
        conversation = None
        if self.grant['conversation_id']:
            conversation = SupportConversation.objects.filter(pk=self.grant['conversation_id'], user=user).first()
            if conversation is None:
                self.order_context.conversation_missing = True
                raise AccessDenied('MCP conversation scope changed')
            if conversation.revision != self.grant['revision']:
                raise ConversationConflict('MCP conversation revision changed')
        return user, conversation

    def context(self, user, conversation):
        if self.history is None:
            # Preview history is in-memory host state, never a client-supplied
            # replacement for a persisted buyer conversation.
            if self.grant['mode'] == 'preview':
                self.history = self.grant['preview_history']
            else:
                self.history = recent_context(conversation)
            selection = self.grant.get('selection')
            if selection and not select_bundle_context(user, conversation, self.history, selection):
                raise AccessDenied('Invalid saved bundle selection')
        return self.history

    def preferences(self, user):
        if user is None:
            raise AccessDenied('Private MCP tool requires a buyer')
        if not self.memory_loaded:
            self.memory = saved_preferences(user)
            self.memory_loaded = True
        return self.memory

    def invoke(self, tool, arguments):
        private = None
        budget = None
        try:
            private = read_private(self.grant['private_dir'], 'input', self.grant['nonce'], self.sequence + 1)
            self.sequence += 1
            if tool not in ARGUMENTS or tool not in self.grant['allowed_tools']:
                raise AccessDenied('Tool outside grant')
            args = ARGUMENTS[tool].model_validate(arguments)
            user, conversation = self.authorize()
            if tool == 'search_knowledge':
                allocated = private.get('model_budget')
                if not isinstance(allocated, dict):
                    raise AccessDenied('Missing model budget allocation')
                budget = RequestBudget(CostPolicy(**allocated['policy']))
                budget.stage_policy = {k: tuple(v) for k, v in allocated['stage_policy'].items()}
            with bind_budget(budget):
                result = self.dispatch(tool, args, user, conversation)
        except ConversationConflict:
            result = failure('CONVERSATION_CONFLICT')
        except AccessDenied:
            result = failure('ACCESS_DENIED')
        except ValueError:
            result = failure('INVALID_ARGUMENT')
        except Exception:
            # Exception text can contain SQL, credentials or a private object.
            result = failure('SERVICE_UNAVAILABLE')
        finally:
            close_old_connections()
        if private is not None:
            effects = {name: getattr(self.order_context, name) for name in
                       ('binding_changed', 'selected_order_id', 'not_queryable', 'conversation_missing', 'navigation_tokens')}
            write_private(self.grant['private_dir'], 'output', {
                'nonce': self.grant['nonce'], 'sequence': private['sequence'], 'order_effects': effects,
                'model_usage': budget.snapshot() if budget else None,
            })
        return result

    def dispatch(self, tool, args, user, conversation):
        if tool == 'get_conversation_context':
            return envelope(data={'history': self.context(user, conversation)})
        if tool == 'get_saved_preferences':
            return envelope(data={'memory': self.preferences(user)})
        if tool == 'validate_categories':
            names = set(Catalog.objects.values_list('name', flat=True))
            return envelope(data={'valid': all(CATEGORY_ALIASES.get(v.casefold(), v) in names for v in args.categories)})
        if tool in ('search_products', 'recommend_bundle'):
            history = self.context(user, conversation)
            memory = self.memory if self.memory_loaded else None
            intent = validate_recommendation_intent(args.intent, self.grant['message'], history, memory, branch_rules=False)
            intent = validate_recommendation_branch(intent, tool='recommend_bundle' if tool == 'recommend_bundle' else 'recommend_products', limit=args.limit)
            if tool == 'recommend_bundle':
                data = recommend_bundle(intent, category_scope=args.category_scope)
            elif args.options and args.options.mode == 'by_category':
                data = match_product_groups(intent, args.options, category_scope=args.category_scope)
            else:
                data = match_products(intent, limit=args.limit)
            status = {'MATCHED':'success', 'PARTIAL':'success', 'NO_MATCH':'no_match', 'CLARIFY':'needs_clarification', 'ERROR':'error'}[data['recommendation_status']]
            return envelope(status, data)
        if tool == 'resolve_product':
            ids = list(available_products().filter(name=args.name, spu__name=args.product_name).values_list('pk', flat=True)[:2])
            return envelope(data={'sku_id': ids[0] if len(ids) == 1 else None})
        if tool == 'get_product_details':
            return get_product_details(args.sku_id)
        if tool == 'get_order_status':
            if user is None:
                raise AccessDenied('Private MCP tool requires a buyer')
            # The complete signed current message remains the source of
            # constraints. A shortened model quote cannot remove a date filter.
            requests = explicit_requests(self.grant['message'])
            quotes = [r.quote for r in requests if r.kind == 'after_sales'] or [self.grant['message']]
            if args.request not in [order_request(self.grant['message'], q) for q in quotes]:
                raise AccessDenied('Order request lost constraints')
            result = query_orders(args.query, self.order_context, args.request)
            return envelope(result['status'], result['data'])
        if tool == 'explain_recommendations':
            if args.step.tool != 'explain_recommendations':
                raise ValueError('Invalid explanation tool')
            status, data = explain_existing_products(args.step, args.completed, self.context(user, conversation))
            return envelope(status, data)
        if tool == 'search_knowledge':
            if args.category is not None and not args.scope:
                raise ValueError('Missing knowledge scope')
            if self.retriever is None:
                self.retriever = KnowledgeRetriever(self.grant['owner_id'], self.config)
                self.retriever.policy = QueryPolicy(**self.grant['query_policy'])
            evidence = (self.retriever.scoped_search(args.query, args.category, args.scope)
                        if args.scope else self.retriever.search(args.query))
            return envelope(data={'evidence': evidence, 'notes': self.retriever.notes(), 'audit': self.retriever.audit})
        raise AccessDenied('Unknown data tool')
