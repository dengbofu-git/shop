"""Isolated fault injection for extraction recovery; no external model calls.

These checks supplement, and never replace, the real dialogue replay.
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        raise RuntimeError('Preserve prior results; choose a fresh file')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','tea_saas.settings')
    import django
    django.setup()
    from django.db import connections
    from langchain_core.runnables import RunnableLambda
    from support_ai.contracts import RecommendationOptions
    from support_ai.planning import TaskStep
    from support_ai.tool_services import create_tool_handlers
    from support_ai.mcp_client import AgentDataAccess
    from support_ai.configuration import effective_configuration

    class ScriptedExtraction:
        def __init__(self, payloads):
            self.payloads, self.calls = payloads, 0
        def with_structured_output(self, schema):
            def invoke(prompt):
                position = self.calls
                self.calls += 1
                if position >= len(self.payloads):
                    raise AssertionError('Exceeded the declared call bound')
                return schema.model_validate(self.payloads[position])
            return RunnableLambda(invoke)

    valid = {'action':'SEARCH','required':{'categories':['白茶'],'price_max':'20.00','currency':'USD','price_basis':'unit'},
        'evidence':[
            {'field':'required.categories','value':'白茶','source':'CURRENT','quote':'白茶'},
            {'field':'required.price_max','value':'20.00','source':'CURRENT','quote':'每包单价不超过20美元'},
            {'field':'required.currency','value':'USD','source':'CURRENT','quote':'每包单价不超过20美元'},
            {'field':'required.price_basis','value':'unit','source':'CURRENT','quote':'每包单价不超过20美元'}]}
    clone = lambda value:json.loads(json.dumps(value))
    invalid = clone(valid); invalid['evidence'][0]['field']='required.categories[0]'
    missing = clone(valid); missing['required']['currency']=None
    missing['evidence']=[e for e in missing['evidence'] if e['field']!='required.currency']
    for evidence in missing['evidence']:
        evidence['quote'] = evidence['quote'].replace('美元','')
    foreign = clone(valid); foreign['evidence'][0].update(source='CONTEXT',source_id='turn-nonexistent')
    cases = [
        ('一次非法字段后恢复',[invalid,valid],'success',2),
        ('连续非法字段为系统错误',[invalid,invalid],'error',2),
        ('真实缺少币种需业务澄清',[missing],'needs_clarification',1),
        ('连续伪造来源被拒绝',[foreign,foreign],'error',2),
        ('简单分类规则不调用抽取模型',[],'success',0)]
    rows=[]
    def readonly(execute,sql,params,many,context):
        if re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE)\b',sql,re.I):
            raise RuntimeError('No database mutation allowed')
        return execute(sql,params,many,context)
    with ExitStack() as stack:
        for connection in connections.all():
            stack.enter_context(connection.execute_wrapper(readonly))
        for name,payloads,status,calls in cases:
            message='推荐两款白茶' if calls==0 else '请推荐白茶，每包单价不超过20美元'
            if name=='真实缺少币种需业务澄清':
                message='请推荐白茶，每包单价不超过20'
            model=ScriptedExtraction(payloads)
            step=TaskStep(id='s1',intent='recommendation',tool='recommend_products',request=message,
                          limit=2,recommendation=RecommendationOptions())
            with AgentDataAccess(config=effective_configuration(), message=message, preview_history=[]) as access:
                result=create_tool_handlers(model,None,message,message,[],None,'[]',
                    data_access=access)['recommend_products'](step,{})
            checks={'status':result.status==status,'bounded_calls':model.calls==calls,
                    'attempts_recorded':result.data.get('extraction_attempts')==calls,
                    'no_products_on_failure':bool(result.data.get('recommendations')) if status=='success' else not result.data.get('recommendations')}
            if status=='error':
                checks['not_business_clarification']=result.data.get('recommendation_status')=='ERROR'
            if len(payloads)==2 and status=='success':
                checks['recovery_diagnostic_retained']=len(result.data.get('diagnostics',[]))==1
            rows.append({'name':name,'mode':'local_fault_injection_no_external_model','passed':all(checks.values()),
                         'checks':checks,'status':result.status,'calls':model.calls,
                         'extraction_attempts':result.data.get('extraction_attempts'),
                         'diagnostics':result.data.get('diagnostics',[])})
    output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':sum(r['passed'] for r in rows),'total':len(rows),'results':rows},ensure_ascii=False))


if __name__=='__main__':
    main()
