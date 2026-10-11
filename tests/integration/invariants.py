"""Black-box request/result/export invariants; never import product calculators."""
import json
import math


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def finite_json(value):
    json.dumps(value, allow_nan=False)


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def check_evaluation(request, response):
    finite_json(response)
    fixed = request['fixed_enrollment']
    stress = request['stress_scenario']
    analytic = response['analytic']
    require(analytic['method'] == 'cohen_h_normal_v1', 'analytic method mismatch')
    expected = {arm: math.floor(fixed[arm] * (1 - stress['dropout'][arm]))
                for arm in ('control', 'treatment')}
    require(analytic['assumed_evaluable_n'] == expected, 'expected-retained floor/count mismatch')
    require(probability(analytic['conditional_power_approx']), 'invalid analytic power')
    mc = response['monte_carlo']
    options = request.get('simulation')
    if options is None:
        require(mc is None, 'disabled simulation must be explicit null')
        return
    require(mc is not None, 'requested simulation missing')
    require(mc['method'] == 'pooled_two_proportion_z_v1', 'simulation method mismatch')
    require(mc['replicates'] == options['replicates'] and mc['seed'] == options['seed'], 'seed/replicate drift')
    require(mc['invalid_test_policy'] == 'nonrejection_over_all_replicates', 'invalid-test denominator policy')
    invalid = mc['invalid_test_fraction']
    require(probability(invalid), 'invalid-test frequency')
    require('mcse' not in mc, 'ambiguous unsplit MCSE')
    for side in ('two_sided', 'favorable'):
        fraction = mc[f'significant_{side}_fraction']
        require(probability(fraction) and fraction <= 1 - invalid + 1e-12, 'invalid tests counted as rejections')
        expected_se = math.sqrt(fraction * (1 - fraction) / mc['replicates'])
        require(math.isclose(mc[f'mcse_{side}'], expected_se, rel_tol=1e-9, abs_tol=1e-12), 'MCSE must use all replicates')
    require(mc['significant_favorable_fraction'] <= mc['significant_two_sided_fraction'], 'favorable exceeds two-sided')
    for arm in ('control', 'treatment'):
        retained = mc[f'mean_retained_{arm}']
        events = mc[f'mean_{arm}_events']
        require(type(retained) in (int, float) and type(events) in (int, float)
                and 0 <= events <= retained <= fixed[arm], 'simulated count bounds')
    require(analytic.get('retention_semantics', 'floor_of_expected_retained_count')
            == 'floor_of_expected_retained_count', 'analytic retention semantics')


def check_grid(request, response, grid):
    finite_json(grid)
    require(grid['method'] == response['analytic']['method'], 'grid/point method mismatch')
    xs, ys = grid['x_baseline'], grid['y_dropout']
    for values in (xs, ys):
        require(len(values) >= 2 and all(probability(v) for v in values)
                and all(a < b for a, b in zip(values, values[1:])), 'unordered grid axes')
    powers, masks = grid['power'], grid['invalid_mask']
    require(len(powers) == len(ys) and len(masks) == len(ys), 'transposed grid rows')
    for row, mask in zip(powers, masks):
        require(len(row) == len(xs) and len(mask) == len(xs), 'transposed grid columns')
        for power, invalid in zip(row, mask):
            require(type(invalid) is bool, 'nonboolean invalid mask')
            require(power is None if invalid else probability(power), 'invalid cells must be null, never zero')
    stress = request['stress_scenario']
    baseline, dropout = stress['control_event_rate'], stress['dropout']['control']
    require(baseline in xs and dropout in ys, 'test scenario must be an exact grid node')
    r, c = ys.index(dropout), xs.index(baseline)
    require(not masks[r][c], 'selected scenario unexpectedly invalid')
    require(math.isclose(powers[r][c], response['analytic']['conditional_power_approx'], abs_tol=1e-10), 'grid/point disagreement at same fixed N/dropout')
    require(grid['target_power'] == request['planned_design']['target_power'], 'target drift')


def check_export(request, response, exported, expected_provenance):
    finite_json(exported)
    require(exported['export_schema_version'] == 1, 'export version')
    for key in ('planned_design', 'fixed_enrollment', 'stress_scenario'):
        require(exported[key] == request[key], f'export mutated {key}')
    require(exported['evaluation_result'] == response, 'export lost or changed API result/seed/metadata')
    require(bool(expected_provenance), 'provenance witness must not be empty')
    require(exported['provenance'] == expected_provenance, 'per-field provenance lost or relabeled')


def check_design(planned, design):
    finite_json(design)
    require(design['method'] == 'cohen_h_normal_v1', 'design method')
    for arm in ('control', 'treatment'):
        n = design['evaluable_n'][arm]
        require(type(n) is int and n > 0, 'strict evaluable count')
        require(type(design['enrolled_n'][arm]) is int, 'strict enrolled count')
        require(design['enrolled_n'][arm] == math.ceil(n / (1 - planned['dropout'][arm])), 'dropout enrollment inflation')
    require(design['evaluable_n']['control'] == design['evaluable_n']['treatment'], 'unequal enrollment')
