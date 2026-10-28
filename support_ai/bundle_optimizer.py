"""套餐整数优化：预算／库存硬约束，多样性与收益递减为显式软目标。"""
from time import monotonic
from ortools.sat.python import cp_model
from .budget_combinations import MAX_CANDIDATES, MAX_SECONDS

POLICY_VERSION = 'balanced-cpsat-v1'


def optimize_bundles(candidates, *, budget_cents, minimum_cents=0, categories=(), quantity=None,
                     distinct_count=None, preference_max=0, prefer_near=False, minimum_distinct=1):
    """最多三套不同SPU集合，共享总时限；最优仅指当前候选和本策略目标。"""
    if (type(budget_cents) is not int or not 0 < budget_cents <= 10**10
            or type(minimum_cents) is not int or not 0 <= minimum_cents <= budget_cents
            or type(minimum_distinct) is not int or not 1 <= minimum_distinct <= 4
            or (quantity is not None and (type(quantity) is not int or not 1 <= quantity <= 100))
            or (distinct_count is not None and (type(distinct_count) is not int or not 1 <= distinct_count <= 4))
            or len(candidates) > MAX_CANDIDATES or type(preference_max) is not int or preference_max < 0):
        raise ValueError('Invalid bundle bounds')
    if distinct_count is not None and distinct_count < minimum_distinct:
        raise ValueError('Conflicting distinct count')
    if len({c.sku_id for c in candidates}) != len(candidates):
        raise ValueError('Duplicate bundle candidate')
    for c in candidates:
        if (any(type(v) is not int for v in (c.sku_id,c.product_id,c.price_cents,c.available_quantity,c.preference_score))
                or c.preference_score < 0 or c.available_quantity < 0):
            raise ValueError('Invalid candidate')
    items = sorted((c for c in candidates if c.price_cents > 0 and c.available_quantity >= (quantity or 1)
                    and c.price_cents * (quantity or 1) <= budget_cents), key=lambda c:c.sku_id)
    model = cp_model.CpModel()
    xs, ys, lines = [], [], []
    utility = []
    for i,c in enumerate(items):
        upper = min(c.available_quantity,budget_cents//c.price_cents)
        y = model.new_bool_var('chosen_'+str(i))
        x = model.new_int_var(0, upper, 'units_'+str(i))
        model.add(x >= y); model.add(x <= upper*y)
        if quantity is not None: model.add(x == quantity*y)
        xs.append(x); ys.append(y); lines.append(c.price_cents*x)
        match = min(1000, c.preference_score*1000//preference_max) if preference_max else 1000
        utility.append((1000+match)*y)
        # 后续重复件只获得递减且有界的效用，不按每件无限累加偏好分。
        for threshold,reward in [(2,100),(4,50),(8,25),(16,12),(32,6)]:
            if threshold <= upper:
                reached=model.new_bool_var('tier_%s_%s'%(i,threshold))
                model.add(x>=threshold).only_enforce_if(reached)
                model.add(x<threshold).only_enforce_if(reached.Not())
                utility.append(reward*reached)
    low = distinct_count if distinct_count is not None else minimum_distinct
    high = distinct_count if distinct_count is not None else 4
    model.add(sum(ys)>=low); model.add(sum(ys)<=high)
    for product in {c.product_id for c in items}:
        model.add(sum(y for c,y in zip(items,ys) if c.product_id==product)<=1)
    for category in set(categories):
        model.add(sum(y for c,y in zip(items,ys) if c.category==category)>=1)
    for category in sorted({c.category for c in items}):
        covered=model.new_bool_var('category_'+category)
        model.add_max_equality(covered,[y for c,y in zip(items,ys) if c.category==category])
        utility.append(1000*covered)
    total=model.new_int_var(minimum_cents,budget_cents,'subtotal')
    model.add(total==sum(lines))
    utilization=model.new_int_var(0,10000,'utilization')
    model.add_division_equality(utilization,total*10000,budget_cents)
    max_line=model.new_int_var(0,budget_cents,'largest_line')
    model.add_max_equality(max_line,lines or [0])
    concentration=model.new_int_var(0,3000,'concentration')
    model.add_division_equality(concentration,max_line*3000,budget_cents)
    # 用候选中位单价归一化采购体量，软惩罚大量廉价重复件，不设任意硬件数上限。
    median_price = sorted(c.price_cents for c in items)[len(items)//2] if items else 1
    volume=model.new_int_var(0, budget_cents//min((c.price_cents for c in items),default=1), 'total_units')
    model.add(volume==sum(xs))
    reference_quantity=max(1,budget_cents//median_price)
    volume_penalty=model.new_int_var(0, (budget_cents//min((c.price_cents for c in items),default=1))*2000//reference_quantity, 'volume_penalty')
    model.add_division_equality(volume_penalty,volume*2000,reference_quantity)
    balanced=sum(utility)+utilization-concentration-volume_penalty
    deadline=monotonic()+MAX_SECONDS
    records=[]; nodes=0; near_floor=max(minimum_cents,(budget_cents*95+99)//100)

    def solve(objective, stages=1):
        nonlocal nodes
        remaining=deadline-monotonic()
        if remaining<=0: return None,None
        model.maximize(objective)
        solver=cp_model.CpSolver()
        solver.parameters.max_time_in_seconds=max(0.001,remaining/((3-len(records))*stages))
        solver.parameters.num_search_workers=1
        solver.parameters.random_seed=0
        status=solver.solve(model); nodes+=solver.num_branches
        if status == cp_model.MODEL_INVALID: raise ValueError('Invalid CP-SAT model')
        return solver,status

    status=cp_model.UNKNOWN
    for _ in range(3):
        # 显式接近模式先最大化可行金额，再在保留该金额的候选中选平衡方案。
        stage_status=None
        if prefer_near:
            solver,stage_status=solve(total, stages=2)
            if stage_status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
                status=stage_status
                break
            floor=model.new_bool_var('near_floor_'+str(len(records)))
            model.add(total>=solver.value(total)).only_enforce_if(floor)
            model.add_assumption(floor)
        best,status=solve(balanced)
        if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            if prefer_near: best,status=solver,stage_status
            else: break
        selected=[(c,best.value(x)) for c,x in zip(items,xs) if best.value(x)>0]
        subtotal=sum(c.price_cents*q for c,q in selected)
        count=len(selected)
        match=(sum(c.preference_score for c,q in selected)*100//(preference_max*count)) if preference_max else 100
        quality=(80*min(100,match)+20*len({c.category for c,q in selected})*100//count)//100
        records.append({'sku_ids':[c.sku_id for c,q in selected], 'quantities':[q for c,q in selected],
            'subtotal_cents':subtotal,'quality_score':quality,'near_budget':subtotal>=near_floor,
            'solver_status':best.status_name(status),'objective_value':best.objective_value,
            'best_objective_bound':best.best_objective_bound,
            'budget_stage_optimal':stage_status==cp_model.OPTIMAL if prefer_near else None})
        if prefer_near:
            model.clear_assumptions(); model.add(floor==0)
        # 方案差异按SPU集合约束，不能仅换同款规格或微调一件冒充新方案。
        chosen_products={c.product_id for c,q in selected}
        # 对每个SPU使用是否选中表达式，兼容同SPU多个SKU。
        selected_sum=sum(y for c,y in zip(items,ys) if c.product_id in chosen_products)
        other_sum=sum(y for c,y in zip(items,ys) if c.product_id not in chosen_products)
        model.add(selected_sum-other_sum <= count-1)
    return {'plans':records,'nodes':nodes,'valid_combinations':len(records),
        'candidate_count':len(items),'near_floor_cents':near_floor,'solver':'ortools-cp-sat',
        'policy_version':POLICY_VERSION,'termination_status':cp_model.CpSolver().status_name(status) if status is not None else 'UNKNOWN','search_complete':False,'globally_optimal':False,
        'quantity_mode':'fixed' if quantity is not None else 'automatic',
        'automatic_quantity_cap':None,'quantity_bound':'budget_and_available_stock',
        'duration_ms':round((monotonic()-(deadline-MAX_SECONDS))*1000,3),
        'objective_policy':{'utilization':10000,'max_line_penalty':3000,'distinct_product':1000,
                            'category':1000,'preference_per_product':1000,
                            'volume_reference_price_cents':median_price,'volume_penalty':2000,
                            'repeat_tiers':[[2,100],[4,50],[8,25],[16,12],[32,6]]}}
