"""Request-owned model admission and stage policy; no prompts or identities stored."""
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock

from django.conf import settings
from langchain_core.runnables import Runnable


class ModelBudgetExceeded(RuntimeError):
    pass


def option(name, default):
    return getattr(settings, name, os.environ.get(name, default))


def positive(name, default, maximum):
    value = option(name, default)
    if isinstance(value, bool):
        raise ValueError('Invalid model budget configuration: ' + name)
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError('Invalid model budget configuration: ' + name) from None
    if str(result) != str(value) or not 1 <= result <= maximum:
        raise ValueError('Invalid model budget configuration: ' + name)
    return result


@dataclass(frozen=True)
class CostPolicy:
    max_calls: int = 8
    max_input_tokens: int = 65536
    max_output_tokens: int = 8192

    @classmethod
    def current(cls):
        return cls(positive('SUPPORT_MODEL_MAX_CALLS', 8, 32),
                   positive('SUPPORT_MODEL_MAX_INPUT_TOKENS', 65536, 262144),
                   positive('SUPPORT_MODEL_MAX_OUTPUT_TOKENS', 8192, 32768))


STAGES = {
    'scope': 192,
    'planning': 1400, 'extraction': 1600, 'rewrite': 512,
    'knowledge': 2400, 'verification': 768, 'compliance': 512,
}
SCHEMA_STAGES = {
    'BudgetScopeDecision': 'scope',
    'PurchaseEvidenceRepair': 'extraction',
    'SemanticPlan': 'planning', 'FiniteIntents': 'planning', 'DialogueResolution': 'planning',
    'RecommendationIntent': 'extraction', 'QueryTranslations': 'rewrite',
    'KnowledgeDraft': 'knowledge', 'TeaExplanation': 'knowledge',
    'GroundingReview': 'verification', 'ComplianceVerdict': 'compliance',
}


def stage_options(stage):
    prefix = 'SUPPORT_' + stage.upper()
    thinking = option(prefix + '_THINKING', 'disabled')
    if thinking not in ('disabled', 'enabled'):
        raise ValueError('Invalid model thinking configuration: ' + prefix)
    return thinking, positive(prefix + '_MAX_TOKENS', STAGES[stage], 8192)


def input_upper_bound(prompt, schema=None):
    # Byte length is deliberately conservative for byte-based tokenizers. Include
    # schema/tool formatting and role overhead; provider usage wins after return.
    messages = prompt.to_messages() if hasattr(prompt, 'to_messages') else prompt
    if isinstance(messages, (list, tuple)):
        text = '\n'.join(str(getattr(m, 'content', m)) for m in messages)
        overhead = 64 * (len(messages) + 1)
    else:
        text, overhead = str(messages), 128
    if schema is not None:
        text += json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return len(text.encode('utf-8')) + overhead + 256


class RequestBudget:
    def __init__(self, policy=None):
        self.policy = policy or CostPolicy.current()
        self.lock = Lock()
        self.calls = self.input_tokens = self.output_tokens = 0
        self.reserved_input = self.reserved_output = self.unknown_usage_calls = 0
        self.rejected_calls = 0
        self.provider_overrun_calls = 0
        self.stages = {}
        self.stage_policy = {stage: stage_options(stage) for stage in STAGES}

    def reserve(self, stage, input_bound, output_limit):
        with self.lock:
            remaining = self.policy.max_output_tokens - self.output_tokens - self.reserved_output
            if (self.provider_overrun_calls or self.calls >= self.policy.max_calls or remaining <= 0 or
                    self.input_tokens + self.reserved_input + input_bound > self.policy.max_input_tokens):
                self.rejected_calls += 1
                raise ModelBudgetExceeded('Request model budget exhausted')
            allowance = min(output_limit, remaining)
            self.calls += 1
            self.stages[stage] = self.stages.get(stage, 0) + 1
            self.reserved_input += input_bound
            self.reserved_output += allowance
            return input_bound, allowance

    def settle(self, reservation, usage):
        with self.lock:
            before_input, before_output = reservation
            self.reserved_input -= before_input
            self.reserved_output -= before_output
            if (not usage or type(usage.get('input_tokens')) is not int or
                    type(usage.get('output_tokens')) is not int or
                    usage['input_tokens'] < 0 or usage['output_tokens'] < 0):
                # A timeout can still be billed. Keep its full reservation;
                # never turn missing usage into free capacity or replay a call.
                self.input_tokens += before_input
                self.output_tokens += before_output
                self.unknown_usage_calls += 1
            else:
                self.input_tokens += usage['input_tokens']
                self.output_tokens += usage['output_tokens']
                if usage['output_tokens'] > before_output:
                    self.provider_overrun_calls += 1

    def snapshot(self):
        with self.lock:
            return {'calls': self.calls, 'input_tokens': self.input_tokens, 'output_tokens': self.output_tokens,
                    'unknown_usage_calls': self.unknown_usage_calls, 'rejected_calls': self.rejected_calls,
                    'provider_overrun_calls': self.provider_overrun_calls,
                    'stages': dict(self.stages),
                    'stage_policy': {key: {'thinking': value[0], 'max_tokens': value[1]}
                                     for key, value in self.stage_policy.items()}, 'limits': {
                        'calls': self.policy.max_calls, 'input_tokens': self.policy.max_input_tokens,
                        'output_tokens': self.policy.max_output_tokens}}


_budget = ContextVar('support_model_budget', default=None)


def current_budget():
    return _budget.get()


@contextmanager
def model_request():
    existing = current_budget()
    if existing is not None:
        yield existing
        return
    budget = RequestBudget()
    token = _budget.set(budget)
    try:
        yield budget
    finally:
        _budget.reset(token)


class BudgetedGraph(Runnable):
    """A fresh context per invoke, including query-rewrite clients created inside tools."""
    def __init__(self, graph):
        self.graph = graph

    def invoke(self, input, config=None, **kwargs):
        with model_request() as budget:
            result = self.graph.invoke(input, config=config, **kwargs)
            result['model_usage'] = budget.snapshot()
            if isinstance(result.get('response'), dict):
                result['response']['model_usage'] = result['model_usage']
            return result

    def get_graph(self, config=None, **kwargs):
        return self.graph.get_graph(config=config, **kwargs)
