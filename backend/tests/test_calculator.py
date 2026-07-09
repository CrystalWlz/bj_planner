import pytest
from datetime import date
from pathlib import Path
from pydantic import ValidationError

import app.calculator as calculator_module
from app.calculator import (
    _car_monthly_cash_cost_at,
    _is_beijing_pf_offset_month,
    _quarterly_rent_withdrawal_before_purchase_at,
    _semiannual_loan_offset_monthly_equivalent,
    calculate_affordability,
    build_car_plan_analyses,
    build_child_plan_strategies,
    build_monthly_cashflow_visualization,
    build_tax_events,
    build_tax_monthly_points,
    build_social_security_visualization,
    calculate_car_loan,
    calculate_household_tax,
    calculate_household_tax_for_year,
    calculate_loan,
    household_monthly_income_profile_at,
    monthly_household_expense_at,
    summarize_phased_loans,
)
from app.domain.scoring import purchase_happiness_weights
from app.engine_config import parallel_worker_count
from app.domain.time import month_after
from app.projection.horizon import visualization_horizon_months
from app.schemas import CareerShockData, CareerShockMemberSetting, CalculationContextGoalSnapshot, CalculationContextSnapshot, CarPlanData, ChildPlanData, DailyExpenseStageData, ElderlyDependentData, HouseholdData, IncomeMember, IncomeStageData, InvestmentTaxProfileData, MarketSnapshotData, RentExpenseStageData, RulePackData, ScenarioData, ScheduledExpenseData, SpecialDeductionItemData, PhasedLoanData, VehicleFinancingOptionData
from app.strategies.vehicle import vehicle_candidate_plans


def _zero_contribution_rule() -> RulePackData:
    rule = RulePackData()
    return rule.model_copy(
        update={
            "params": {
                **rule.params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999999,
                "beijing_housing_fund_base_floor": 0,
                "beijing_housing_fund_base_ceiling": 999999,
                "housing_fund_min_rate": 0,
                "employee_pension_rate": 0,
                "employee_medical_rate": 0,
                "employee_medical_fixed": 0,
                "employee_unemployment_rate": 0,
            }
        }
    )


def test_domain_projection_and_strategy_layers_do_not_construct_default_rule_pack() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    allowed_default_rule_pack_files = {
        Path("calculator.py"),
        Path("database.py"),
        Path("policies.py"),
        Path("projection_facade.py"),
        Path("storage/normalization.py"),
        Path("vehicle_facade.py"),
    }
    allowed_rule_param_access_files = {
        Path("engine_config.py"),
        Path("policies.py"),
        Path("storage/normalization.py"),
    }
    allowed_execution_config_key_files = {
        Path("engine_config.py"),
        Path("schemas.py"),
    }
    forbidden_fragments = [
        "RulePackData()",
        "rules or RulePackData",
        "active_rules = rules or",
        "effective_rules = rules or",
        "rules: RulePackData | None",
    ]
    forbidden_rule_param_fragments = [
        ".params.get(",
        ".params[",
    ]

    violations: list[str] = []
    for path in app_dir.rglob("*.py"):
        relative_path = path.relative_to(app_dir)
        text = path.read_text(encoding="utf-8")
        if relative_path not in allowed_default_rule_pack_files:
            for fragment in forbidden_fragments:
                if fragment in text:
                    violations.append(f"{relative_path} contains {fragment}")
        if relative_path not in allowed_rule_param_access_files:
            for fragment in forbidden_rule_param_fragments:
                if fragment in text:
                    violations.append(f"{relative_path} reads RulePackData.params via {fragment}")
        if relative_path not in allowed_execution_config_key_files and "backend_parallel_workers" in text:
            violations.append(f"{relative_path} references execution config key backend_parallel_workers")

    assert violations == []


def test_domain_layers_do_not_import_policy_default_constants() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    scanned_dirs = [app_dir / "domain", app_dir / "strategies", app_dir / "projection"]

    violations = [
        str(path.relative_to(app_dir))
        for directory in scanned_dirs
        for path in directory.rglob("*.py")
        if "DEFAULT_PURCHASE_HAPPINESS_WEIGHTS" in path.read_text(encoding="utf-8")
    ]

    assert violations == []


def _sample_phased_loans() -> list[PhasedLoanData]:
    return [
        PhasedLoanData(
            borrower="样例成员A",
            name="阶段性贷款A",
            principal=30_000,
            remaining_months=120,
            interest_start_month="2026-07",
            interest_only_until="2028-07",
        ),
        PhasedLoanData(
            borrower="样例成员A",
            name="阶段性贷款B",
            principal=40_000,
            remaining_months=120,
            interest_start_month="2026-07",
            interest_only_until="2028-06",
        ),
        PhasedLoanData(
            borrower="样例成员B",
            name="阶段性贷款C",
            principal=35_000,
            remaining_months=120,
            interest_start_month="2027-07",
            interest_only_until="2028-07",
        ),
        PhasedLoanData(
            borrower="样例成员B",
            name="阶段性贷款D",
            principal=45_000,
            remaining_months=120,
            interest_start_month="2027-07",
            interest_only_until="2028-06",
        ),
    ]


def test_equal_installment_loan_has_stable_monthly_payment() -> None:
    loan = calculate_loan(1_000_000, 0.036, 30, "equal_installment")
    assert round(loan.first_month_payment, 2) == round(loan.average_month_payment, 2)
    assert loan.total_interest > 600_000


def test_affordability_marks_cash_gap_as_not_viable() -> None:
    household = HouseholdData(cash_account_balance=300_000, monthly_income=50_000)
    scenario = ScenarioData(total_price=6_000_000, down_payment_amount=1_800_000)
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_municipal_monthly_repayment_withdrawal_supported": False,
        }
    )
    result = calculate_affordability(household, scenario, rules)
    assert result.status == "不可行"
    assert result.funding_gap > 0


def test_affordability_risk_thresholds_are_read_from_policy_interface() -> None:
    base_rules = RulePackData()
    strict_rules = base_rules.model_copy(
        update={
            "params": {
                **base_rules.params,
                "caution_dti": 0.01,
                "danger_dti": 0.95,
                "recommended_emergency_months": 0,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=2_000_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=60_000, annual_bonus=0)],
    )
    scenario = ScenarioData(total_price=2_000_000, down_payment_amount=1_000_000, commercial_loan_amount=1_000_000)

    baseline = calculate_affordability(household, scenario, base_rules)
    strict = calculate_affordability(household, scenario, strict_rules)

    assert baseline.status in {"可行", "谨慎可行"}
    assert strict.status == "谨慎可行"
    assert strict.debt_to_income_ratio > 0.01
    assert strict.status_reason == "资金可覆盖购房，但现金流或应急金低于推荐安全垫。"


def test_affordability_skips_stress_tests_by_default() -> None:
    result = calculate_affordability(HouseholdData(), ScenarioData(), RulePackData())
    assert result.stress_tests == []


def test_affordability_builds_stress_tests_when_requested() -> None:
    result = calculate_affordability(HouseholdData(), ScenarioData(), RulePackData(), include_stress_tests=True)
    assert len(result.stress_tests) == 3
    assert all(item.name for item in result.stress_tests)


def test_stress_test_assumptions_are_read_from_policy_interface() -> None:
    base_rules = RulePackData()
    rules = base_rules.model_copy(
        update={
            "params": {
                **base_rules.params,
                "rate_stress_add": 0.02,
                "income_stress_factor": 1.0,
                "price_stress_factor": 1.0,
            }
        }
    )
    household = HouseholdData(cash_account_balance=1_000_000, monthly_income=50_000, monthly_expense=10_000)
    scenario = ScenarioData(total_price=3_000_000, commercial_loan_amount=2_000_000, provident_loan_amount=0)

    result = calculate_affordability(household, scenario, rules, include_stress_tests=True)
    base_monthly_payment = result.monthly_payment
    rate_stress = next(item for item in result.stress_tests if item.name == "利率上行")

    assert rate_stress.monthly_payment > base_monthly_payment


def test_visualization_horizon_retirement_tail_uses_current_policy_rules() -> None:
    base_rules = RulePackData()
    delayed_rules = base_rules.model_copy(
        update={
            "params": {
                **base_rules.params,
                "retirement_age_male": 70,
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="样例成员A",
                birth_month="1980-07",
                retirement_category="male_60",
            )
        ]
    )
    disabled_car_loan = calculate_car_loan(CarPlanData(enabled=False))

    baseline = visualization_horizon_months(
        household,
        [],
        disabled_car_loan,
        as_of=date(2026, 7, 1),
        rules=base_rules,
    )
    delayed = visualization_horizon_months(
        household,
        [],
        disabled_car_loan,
        as_of=date(2026, 7, 1),
        rules=delayed_rules,
    )

    assert baseline == 324
    assert delayed == 408
    assert delayed - baseline == 84


def test_parallel_worker_count_is_runtime_config_not_calculator_rule_read() -> None:
    base_params = RulePackData().params
    assert parallel_worker_count(RulePackData(params={**base_params, "backend_parallel_workers": 1}), 4) == 1
    assert parallel_worker_count(RulePackData(params={**base_params, "backend_parallel_workers": 4}), 2) == 2
    assert parallel_worker_count(RulePackData(params={**base_params, "backend_parallel_workers": 99}), 20) == 8
    assert parallel_worker_count(RulePackData(params={**base_params, "backend_parallel_workers": "bad"}), 5) == 4
    assert parallel_worker_count(RulePackData(params={**base_params, "backend_parallel_workers": 0}), 5) == 1
    assert parallel_worker_count(RulePackData(params={**base_params, "backend_parallel_workers": 4}), 1) == 1


def test_parallel_affordability_matches_serial_result() -> None:
    serial_rules = RulePackData(
        params={**RulePackData().params, "backend_parallel_workers": 1}
    )
    parallel_rules = RulePackData(
        params={**RulePackData().params, "backend_parallel_workers": 4}
    )
    household = HouseholdData(
        cash_account_balance=1_000_000,
        monthly_expense=12_000,
        social_security_months=96,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=35_000, annual_bonus=80_000),
            IncomeMember(name="样例成员B", monthly_salary_gross=18_000, annual_bonus=20_000),
        ],
    )
    scenario = ScenarioData(total_price=3_000_000, renovation_cost=80_000)

    serial = calculate_affordability(household, scenario, serial_rules, include_stress_tests=True)
    parallel = calculate_affordability(household, scenario, parallel_rules, include_stress_tests=True)

    assert parallel.status == serial.status
    assert parallel.yield_sensitivity == serial.yield_sensitivity
    assert parallel.stress_tests == serial.stress_tests
    assert [item.variant for item in parallel.purchase_plan_analyses] == [
        item.variant for item in serial.purchase_plan_analyses
    ]


def test_vehicle_loan_projection_is_cached_during_full_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    original = calculator_module.calculate_car_loan
    call_count = 0

    def counting_calculate_car_loan(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(calculator_module, "calculate_car_loan", counting_calculate_car_loan)

    household = HouseholdData(
        cash_account_balance=1_500_000,
        monthly_expense=12_000,
        social_security_months=120,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=35_000, annual_bonus=80_000),
            IncomeMember(name="样例成员B", monthly_salary_gross=18_000, annual_bonus=20_000),
        ],
        car_plan=CarPlanData(
            enabled=False,
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="样例车辆A",
                    total_price=250_000,
                    down_payment_ratio=0.5,
                    down_payment=125_000,
                    purchase_delay_months=6,
                    purchase_timing_mode="parallel",
                    planning_sequence=1,
                ),
                CarPlanData(
                    enabled=True,
                    name="样例车辆B",
                    total_price=180_000,
                    down_payment_ratio=0.5,
                    purchase_delay_months=48,
                    purchase_timing_mode="auto_sequence",
                    planning_sequence=2,
                ),
            ],
        ),
    )
    scenario = ScenarioData(total_price=3_000_000, renovation_cost=80_000)

    result = calculate_affordability(household, scenario, RulePackData())

    assert result.purchase_plan_analyses
    assert call_count < 120


def test_scheduled_family_support_expense_starts_in_2027_july_without_tax_deduction() -> None:
    household = HouseholdData(
        monthly_expense=8_000,
        scheduled_expenses=[
            ScheduledExpenseData(
                name="家庭支持支出",
                monthly_amount=3_500,
                start_month="2027-07",
                tax_deductible_elderly_care=False,
            )
        ],
    )

    assert monthly_household_expense_at(household, as_of=date(2027, 6, 1)) == 8_000
    assert monthly_household_expense_at(household, as_of=date(2027, 7, 1)) == 11_500
    assert household.scheduled_expenses[0].tax_deductible_elderly_care is False


def test_domain_monthly_expense_requires_explicit_rule_pack() -> None:
    from app.domain.expenses import monthly_household_expense_at as domain_monthly_household_expense_at

    household = HouseholdData(monthly_expense=8_000)

    with pytest.raises(ValueError, match="explicit rule pack"):
        domain_monthly_household_expense_at(household, as_of=date(2027, 6, 1), rules=None)  # type: ignore[arg-type]

    assert monthly_household_expense_at(household, as_of=date(2027, 6, 1)) == 8_000


def test_annual_once_scheduled_expense_only_hits_occurrence_month() -> None:
    household = HouseholdData(
        monthly_expense=8_000,
        scheduled_expenses=[
            ScheduledExpenseData(
                name="数码产品支出",
                monthly_amount=10_000,
                frequency="annual_once",
                annual_occurrence_month=6,
                start_month="2027-01",
                tax_deductible_elderly_care=False,
            )
        ],
    )

    assert monthly_household_expense_at(household, as_of=date(2027, 5, 1)) == 8_000
    assert monthly_household_expense_at(household, as_of=date(2027, 6, 1)) == 18_000
    assert monthly_household_expense_at(household, as_of=date(2028, 6, 1)) == 18_000


def test_one_time_scheduled_expense_supports_fixed_and_flexible_months() -> None:
    household = HouseholdData(
        monthly_expense=8_000,
        scheduled_expenses=[
            ScheduledExpenseData(
                name="固定月份大额支出",
                monthly_amount=12_000,
                frequency="one_time",
                one_time_timing_mode="fixed_month",
                start_month="2027-04",
            ),
            ScheduledExpenseData(
                name="弹性窗口大额支出",
                monthly_amount=20_000,
                frequency="one_time",
                one_time_timing_mode="flexible_range",
                start_month="2027-05",
                end_month="2027-08",
            ),
        ],
    )

    assert monthly_household_expense_at(household, as_of=date(2027, 3, 1)) == 8_000
    assert monthly_household_expense_at(household, as_of=date(2027, 4, 1)) == 20_000
    assert monthly_household_expense_at(household, as_of=date(2027, 5, 1)) == 8_000
    assert monthly_household_expense_at(household, as_of=date(2027, 8, 1)) == 28_000
    assert monthly_household_expense_at(household, as_of=date(2027, 9, 1)) == 8_000


def test_member_profile_fields_derive_household_policy_and_accounts() -> None:
    household = HouseholdData(
        cash_account_balance=10_000,
        investments=20_000,
        social_security_months=12,
        existing_home_count=0,
        existing_mortgage_count=0,
        members=[
            IncomeMember(
                name="样例成员A",
                social_security_months=36,
                income_tax_months=60,
                existing_home_count=1,
                existing_mortgage_count=1,
                initial_cash_balance=100_000,
                initial_investments=50_000,
            ),
            IncomeMember(
                name="样例成员B",
                social_security_months=24,
                income_tax_months=12,
                existing_home_count=0,
                existing_mortgage_count=1,
                initial_cash_balance=20_000,
                initial_investments=10_000,
            ),
        ],
    )

    derived = calculator_module._household_with_member_derived_profile(household)

    assert derived.social_security_months == 60
    assert derived.existing_home_count == 1
    assert derived.existing_mortgage_count == 2
    assert derived.cash_account_balance == 120_000
    assert derived.investments == 60_000


def test_member_income_tax_is_calculated_from_configured_salary_and_bonus() -> None:
    household = HouseholdData(
        members=[
            IncomeMember(
                name="测试成员",
                monthly_salary_gross=30_000,
                annual_bonus=120_000,
                monthly_social_insurance=2_000,
                monthly_housing_fund=3_000,
                monthly_special_additional_deduction=2_000,
                bonus_tax_method="best",
            )
        ]
    )
    summaries, gross_monthly, net_monthly, annual_tax = calculate_household_tax(household, RulePackData())
    assert len(summaries) == 1
    assert gross_monthly == 40_000
    assert annual_tax > 0
    assert net_monthly < gross_monthly
    assert summaries[0].selected_bonus_method in {"separate", "merged"}


def test_annual_bonus_defaults_to_april_not_spread_monthly() -> None:
    household = HouseholdData(
        members=[
            IncomeMember(
                name="测试成员",
                monthly_salary_gross=30_000,
                annual_bonus=120_000,
                employment_start_date="2026-07-01",
                bonus_tax_method="separate",
            )
        ]
    )
    rule = _zero_contribution_rule()

    march = household_monthly_income_profile_at(household, rule, as_of=date(2027, 3, 1))
    april = household_monthly_income_profile_at(household, rule, as_of=date(2027, 4, 1))
    may = household_monthly_income_profile_at(household, rule, as_of=date(2027, 5, 1))

    assert march.gross_income == 30_000
    assert april.gross_income == 150_000
    assert april.income_tax > march.income_tax
    assert may.gross_income == 30_000


def test_annual_bonus_payout_month_can_differ_by_income_stage() -> None:
    household = HouseholdData(
        members=[
            IncomeMember(
                name="测试成员",
                monthly_salary_gross=30_000,
                annual_bonus=120_000,
                employment_start_date="2026-07-01",
                income_stages=[
                    IncomeStageData(
                        name="当前收入",
                        start_date="2026-07-01",
                        monthly_salary_gross=30_000,
                        annual_bonus=120_000,
                        annual_bonus_payout_month=5,
                        bonus_tax_method="separate",
                    )
                ],
            )
        ]
    )
    rule = _zero_contribution_rule()

    april = household_monthly_income_profile_at(household, rule, as_of=date(2027, 4, 1))
    may = household_monthly_income_profile_at(household, rule, as_of=date(2027, 5, 1))

    assert april.gross_income == 30_000
    assert may.gross_income == 150_000


def test_annual_bonus_monthly_spread_enters_salary_tax_not_bonus_tax() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=30_000,
                annual_bonus=120_000,
                bonus_tax_method="separate",
                income_stages=[
                    IncomeStageData(
                        name="按月发奖收入",
                        start_date="2027-01-01",
                        monthly_salary_gross=30_000,
                        annual_bonus=120_000,
                        annual_bonus_payout_mode="monthly_spread",
                        annual_bonus_payout_month=4,
                        bonus_tax_method="separate",
                    )
                ],
            )
        ],
    )

    january = household_monthly_income_profile_at(household, rule, as_of=date(2027, 1, 1))
    april = household_monthly_income_profile_at(household, rule, as_of=date(2027, 4, 1))
    monthly_points = build_tax_monthly_points(household, rule, base_date=date(2027, 1, 1), horizon_months=3)
    summary = calculate_household_tax(household, rule)[0][0]

    assert january.gross_income == 40_000
    assert april.gross_income == 40_000
    assert monthly_points[0].member_points[0].bonus_income == 10_000
    assert monthly_points[3].member_points[0].bonus_income == 10_000
    assert monthly_points[3].member_points[0].bonus_tax == 0
    assert summary.selected_bonus_method == "merged"
    assert summary.gross_annual_income == 480_000
    assert summary.bonus_tax == 0
    assert summary.salary_tax > 0


def test_annual_tax_summary_only_counts_bonus_when_payout_month_is_active() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="下半年入职成员",
                monthly_salary_gross=12_000,
                annual_bonus=12_000,
                employment_start_date="2027-07-01",
                bonus_tax_method="separate",
                income_stages=[
                    IncomeStageData(
                        name="下半年收入",
                        start_date="2027-07-01",
                        monthly_salary_gross=12_000,
                        annual_bonus=12_000,
                        annual_bonus_payout_month=4,
                        bonus_tax_method="separate",
                    )
                ],
            )
        ],
    )

    summary = calculate_household_tax(household, rule)[0][0]

    assert summary.active_months == 6
    assert summary.gross_annual_income == 72_000
    assert summary.bonus_tax == 0


def test_tax_monthly_points_exclude_inactive_member_and_pay_bonus_in_payout_month() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="member_b",
                monthly_salary_gross=12_000,
                annual_bonus=12_000,
                employment_start_date="2027-07-01",
                bonus_tax_method="separate",
                income_stages=[
                    IncomeStageData(
                        name="job_after_july",
                        start_date="2027-07-01",
                        monthly_salary_gross=12_000,
                        annual_bonus=12_000,
                        annual_bonus_payout_month=4,
                        bonus_tax_method="separate",
                    )
                ],
            )
        ],
    )

    points = build_tax_monthly_points(household, rule, base_date=date(2027, 1, 1), horizon_months=16)
    april_2027 = points[3]
    july_2027 = points[6]
    april_2028 = points[15]

    assert april_2027.member_points == []
    assert april_2027.gross_income == 0
    assert july_2027.member_points[0].gross_salary == 12_000
    assert july_2027.member_points[0].bonus_income == 0
    assert april_2028.member_points[0].bonus_income == 12_000


def test_tax_year_summary_is_backend_source_for_future_year_bonus() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="member_b",
                monthly_salary_gross=12_000,
                annual_bonus=12_000,
                employment_start_date="2027-07-01",
                bonus_tax_method="separate",
                income_stages=[
                    IncomeStageData(
                        name="job_after_july",
                        start_date="2027-07-01",
                        monthly_salary_gross=12_000,
                        annual_bonus=12_000,
                        annual_bonus_payout_month=4,
                        bonus_tax_method="separate",
                    )
                ],
            )
        ],
    )

    summary_2027 = calculate_household_tax_for_year(household, rule, 2027)
    summary_2028 = calculate_household_tax_for_year(household, rule, 2028)

    assert summary_2027.gross_annual_income == 72_000
    assert summary_2027.bonus_tax == 0
    assert summary_2028.gross_annual_income == 156_000
    assert summary_2028.summaries[0].gross_annual_income == 156_000


def test_affordability_result_contains_backend_tax_timeline() -> None:
    result = calculate_affordability(
        HouseholdData(
            members=[
                IncomeMember(
                    name="member_a",
                    monthly_salary_gross=30_000,
                    annual_bonus=60_000,
                    employment_start_date="2026-07-01",
                )
            ]
        ),
        ScenarioData(total_price=0),
        _zero_contribution_rule(),
    )

    assert result.tax_year_summaries
    assert result.tax_monthly_points
    assert result.tax_events
    assert result.tax_monthly_points[0].member_points[0].member_name == "member_a"


def test_affordability_result_contains_backend_annual_financial_summary() -> None:
    result = calculate_affordability(
        HouseholdData(
            cash_account_balance=1_200_000,
            investments=120_000,
            monthly_expense=12_000,
            members=[
                IncomeMember(name="member_a", monthly_salary_gross=30_000, annual_bonus=60_000),
                IncomeMember(name="member_b", monthly_salary_gross=18_000, annual_bonus=20_000),
            ],
            car_plan=CarPlanData(
                enabled=True,
                total_price=180_000,
                down_payment_ratio=0.4,
                purchase_delay_months=8,
            ),
        ),
        ScenarioData(total_price=3_000_000, renovation_cost=80_000),
        RulePackData(params={**RulePackData().params, "backend_parallel_workers": 1}),
    )

    assert result.annual_financial_summaries
    plan = result.purchase_plan_analyses[0]
    summary = next(item for item in result.annual_financial_summaries if item.plan_variant == plan.variant)
    base_month = date.today().replace(day=1)
    rows = [
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == summary.plan_variant
        and month_after(base_month, item.month)[0] == summary.year
    ]
    ledger_entries = [
        item
        for item in result.monthly_ledger
        if item.plan_variant == summary.plan_variant
        and month_after(base_month, item.month)[0] == summary.year
    ]
    assert rows
    last_month = max(item.month for item in rows)
    snapshot = next(
        item
        for item in result.account_snapshots
        if item.plan_variant == summary.plan_variant and item.month == last_month
    )
    loan_row = next(
        item
        for item in result.loan_visualization
        if item.plan_variant == summary.plan_variant and item.month == last_month
    )
    provident_row = next(
        item
        for item in result.provident_visualization
        if item.plan_variant == summary.plan_variant and item.month == last_month
    )

    assert summary.months == len(rows)
    monthly_details = [
        item
        for item in result.monthly_visualization_details
        if item.plan_variant == summary.plan_variant
        and month_after(base_month, item.month)[0] == summary.year
    ]
    assert len(monthly_details) == len(rows)
    assert any(item.cash_flow_items for item in monthly_details)
    assert any(item.expense_pie for item in monthly_details)
    assert all(item.loan_payment_pie is not None for item in monthly_details)
    assert all(item.provident_inflow_pie is not None for item in monthly_details)
    assert all(item.social_security_inflow_pie is not None for item in monthly_details)
    annual_visual_detail = next(
        item
        for item in result.annual_visualization_details
        if item.plan_variant == summary.plan_variant and item.year == summary.year
    )
    assert annual_visual_detail.cash_inflow_pie
    assert annual_visual_detail.cash_outflow_pie
    assert annual_visual_detail.liquid_asset_pie
    assert annual_visual_detail.loan_payment_pie is not None
    assert annual_visual_detail.social_security_inflow_pie is not None
    assert result.tax_visualization_details
    assert any(item.month is not None and item.monthly_tax_member_pie for item in result.tax_visualization_details)
    assert any(item.month is None and item.annual_tax_type_pie for item in result.tax_visualization_details)
    assert summary.cash_income == pytest.approx(sum(item.cash_income for item in rows))
    assert summary.cash_income == pytest.approx(
        sum(item.amount for item in ledger_entries if item.category == "income")
    )
    assert summary.transaction_cash_out == pytest.approx(
        sum(
            abs(item.amount)
            for item in ledger_entries
            if item.category in {"home_purchase", "vehicle_down_payment", "vehicle_plate_rental"}
        )
    )
    assert summary.investment_contribution == pytest.approx(sum(item.investment_contribution for item in rows))
    assert summary.cash_balance_end == pytest.approx(snapshot.cash_balance)
    assert summary.investment_balance_end == pytest.approx(snapshot.investment_balance)
    assert summary.fixed_asset_value_end == pytest.approx(snapshot.fixed_asset_value)
    last_cashflow_row = next(item for item in rows if item.month == last_month)
    assert summary.property_asset_value_end == pytest.approx(last_cashflow_row.property_asset_value)
    assert summary.vehicle_asset_value_end == pytest.approx(last_cashflow_row.vehicle_asset_value)
    assert summary.first_vehicle_asset_value_end == pytest.approx(last_cashflow_row.first_vehicle_asset_value)
    assert summary.second_vehicle_asset_value_end == pytest.approx(last_cashflow_row.second_vehicle_asset_value)
    assert summary.total_loan_balance_end == pytest.approx(loan_row.total_loan_balance)
    assert summary.provident_balance_end == pytest.approx(provident_row.balance_end)
    assert summary.commercial_loan_balance_end == pytest.approx(loan_row.commercial_loan_balance)
    assert summary.provident_loan_balance_end == pytest.approx(loan_row.provident_loan_balance)
    export_sheet_titles = {
        item.title
        for item in result.export_sheets
        if item.plan_variant in {"", plan.variant}
    }
    assert "账户月度快照" in export_sheet_titles
    assert "后端月度流水" in export_sheet_titles
    assert "核心对象与账户概念" in export_sheet_titles
    assert "核心对象分组摘要" in export_sheet_titles
    snapshot_sheet = next(
        item
        for item in result.export_sheets
        if item.plan_variant == plan.variant and item.title == "账户月度快照"
    )
    ledger_sheet = next(
        item
        for item in result.export_sheets
        if item.plan_variant == plan.variant and item.title == "后端月度流水"
    )
    core_object_sheet = next(
        item
        for item in result.export_sheets
        if item.plan_variant == plan.variant and item.title == "核心对象与账户概念"
    )
    core_object_group_sheet = next(
        item
        for item in result.export_sheets
        if item.plan_variant == plan.variant and item.title == "核心对象分组摘要"
    )
    assert snapshot_sheet.headers[:4] == ["月份序号", "真实年月", "阶段", "现金账户"]
    assert core_object_sheet.headers[:6] == ["概念编码", "名称", "类别", "核心对象数量", "当前余额/目标金额", "月流量"]
    assert any(row[0] == "cash_account" for row in core_object_sheet.rows)
    assert core_object_group_sheet.headers[:4] == ["分组编码", "名称", "类别", "包含概念"]
    assert any(row[0] == "liquid_assets" for row in core_object_group_sheet.rows)
    assert len(snapshot_sheet.rows) == len(selected_plan_snapshot_rows := [
        item for item in result.account_snapshots if item.plan_variant == plan.variant
    ])
    assert len(ledger_sheet.rows) == len([
        item for item in result.monthly_ledger if item.plan_variant == plan.variant
    ])
    assert selected_plan_snapshot_rows
    export_text = next(
        item
        for item in result.export_texts
        if item.plan_variant == plan.variant
    )
    assert export_text.filename == f"house-plan-{plan.variant}.txt"
    assert any("账户与贷款快照" in line for line in export_text.lines)
    assert any("后端 export_sheets" in line for line in export_text.lines)


def test_income_member_defaults_to_one_income_stage() -> None:
    member = IncomeMember(
        monthly_salary_gross=30_000,
        annual_bonus=60_000,
        employment_start_date="2026-07-01",
    )

    assert len(member.income_stages) == 1
    assert member.income_stages[0].monthly_salary_gross == 30_000
    assert member.income_stages[0].annual_bonus == 60_000
    assert member.income_stages[0].annual_bonus_payout_month == 4
    assert member.income_stages[0].start_date == "2026-07-01"


def test_income_stages_are_weighted_by_projection_year_months() -> None:
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="阶段成员",
                monthly_salary_gross=20_000,
                annual_bonus=0,
                income_stages=[
                    IncomeStageData(
                        name="上半年",
                        start_date="2027-01-01",
                        end_date="2027-06-30",
                        monthly_salary_gross=20_000,
                        annual_bonus=0,
                        monthly_special_additional_deduction=0,
                    ),
                    IncomeStageData(
                        name="下半年",
                        start_date="2027-07-01",
                        monthly_salary_gross=30_000,
                        annual_bonus=0,
                        monthly_special_additional_deduction=0,
                    ),
                ],
            )
        ],
    )

    summaries, gross_monthly, _, _ = calculate_household_tax(household, RulePackData())

    assert summaries[0].gross_annual_income == 300_000
    assert gross_monthly == 25_000


def test_monthly_income_profile_uses_cumulative_salary_withholding() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        scheduled_expenses=[],
        members=[
            IncomeMember(
                name="tax member",
                monthly_salary_gross=50_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
                employment_start_date="2027-01-01",
                personal_pension_account_enabled=False,
                personal_pension_contribution_mode="none",
            )
        ],
    )

    january = household_monthly_income_profile_at(household, rule, as_of=date(2027, 1, 1))
    february = household_monthly_income_profile_at(household, rule, months_from_now=1, as_of=date(2027, 1, 1))

    assert january.income_tax == pytest.approx(1980)
    assert february.income_tax == pytest.approx(4500)
    assert february.net_income < january.net_income


def test_career_shock_adds_layoff_self_social_and_pension_income_stages() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        scheduled_expenses=[],
        career_shock=CareerShockData(
            enabled=True,
            auto_unemployment_benefit=False,
            auto_self_social_insurance=False,
            unemployment_benefit_months=2,
            unemployment_benefit_monthly=2_000,
            self_social_insurance_monthly=1_800,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="我",
                    enabled=True,
                    layoff_age=31,
                    retirement_age=50,
                    pension_monthly=6_000,
                    auto_pension_monthly=False,
                ),
                CareerShockMemberSetting(
                    member_name="成员B",
                    enabled=False,
                    retirement_age=58,
                    pension_monthly=5_000,
                    auto_pension_monthly=False,
                ),
            ],
        ),
        members=[
            IncomeMember(
                name="我",
                current_age=30,
                retirement_category="female_50",
                monthly_salary_gross=20_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
            ),
            IncomeMember(name="成员B", current_age=28, monthly_salary_gross=12_000, annual_bonus=0, monthly_special_additional_deduction=0),
        ],
    )

    before_layoff = household_monthly_income_profile_at(household, rule, as_of=date(2026, 7, 1))
    unemployment = household_monthly_income_profile_at(household, rule, months_from_now=12, as_of=date(2026, 7, 1))
    self_social = household_monthly_income_profile_at(household, rule, months_from_now=14, as_of=date(2026, 7, 1))
    pension = household_monthly_income_profile_at(household, rule, months_from_now=300, as_of=date(2026, 7, 1))

    assert unemployment.non_taxable_income == pytest.approx(2_000)
    assert unemployment.net_income < before_layoff.net_income
    assert self_social.personal_social == 0
    assert monthly_household_expense_at(household, 14, as_of=date(2026, 7, 1), rules=rule) == pytest.approx(2_659.44)
    assert pension.non_taxable_income >= 6_000


def test_career_shock_auto_estimates_unemployment_and_self_social_from_rules() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_unemployment_benefit_10_to_15y": 2600,
                "beijing_unemployment_benefit_after_12_months": 2100,
                "beijing_social_base_floor": 7000,
                "beijing_social_base_ceiling": 30000,
                "flexible_employment_social_base": 8000,
                "flexible_employment_pension_rate": 0.2,
                "flexible_employment_unemployment_rate": 0.01,
                "flexible_employment_medical_monthly": 500,
            }
        }
    )
    household = HouseholdData(
        social_security_months=132,
        scheduled_expenses=[],
        career_shock=CareerShockData(
            enabled=True,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="样例成员",
                    enabled=True,
                    layoff_age=31,
                    retirement_age=60,
                )
            ],
        ),
        members=[IncomeMember(name="样例成员", current_age=30, monthly_salary_gross=20_000, annual_bonus=0)],
    )

    first_month = household_monthly_income_profile_at(household, rule, months_from_now=12, as_of=date(2026, 7, 1))
    thirteenth_month = household_monthly_income_profile_at(household, rule, months_from_now=24, as_of=date(2026, 7, 1))
    after_benefit = household_monthly_income_profile_at(household, rule, months_from_now=36, as_of=date(2026, 7, 1))

    assert first_month.non_taxable_income == pytest.approx(2600)
    assert thirteenth_month.non_taxable_income == pytest.approx(2100)
    assert after_benefit.personal_social == 0
    assert monthly_household_expense_at(household, 36, as_of=date(2026, 7, 1), rules=rule) == pytest.approx(3039.44)


def test_career_shock_supports_freelance_income_flexible_housing_fund_and_auto_pension() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_unemployment_benefit_under_5y": 2200,
                "beijing_social_base_floor": 7000,
                "beijing_social_base_ceiling": 30000,
                "beijing_housing_fund_base_floor": 3000,
                "beijing_housing_fund_base_ceiling": 30000,
                "flexible_employment_social_base": 8000,
                "flexible_employment_pension_rate": 0.2,
                "flexible_employment_unemployment_rate": 0.01,
                "flexible_employment_medical_monthly": 500,
                "flexible_employment_housing_fund_base": 6000,
                "flexible_employment_housing_fund_rate": 0.12,
                "pension_default_paid_years": 15,
                "pension_average_salary_growth_rate": 0.0,
                "pension_personal_account_annual_return": 0.0,
                "pension_replacement_rate_floor": 0.2,
                "pension_replacement_rate_ceiling": 0.65,
            }
        }
    )
    household = HouseholdData(
        social_security_months=36,
        scheduled_expenses=[],
        career_shock=CareerShockData(
            enabled=True,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="样例成员",
                    enabled=True,
                    layoff_age=31,
                    retirement_age=50,
                    freelance_income_monthly=3_500,
                    auto_pension_monthly=True,
                )
            ],
        ),
        members=[
            IncomeMember(
                name="样例成员",
                current_age=30,
                retirement_category="female_50",
                monthly_salary_gross=20_000,
                annual_bonus=0,
            )
        ],
    )

    unemployment = household_monthly_income_profile_at(household, rule, months_from_now=12, as_of=date(2026, 7, 1))
    flexible = household_monthly_income_profile_at(household, rule, months_from_now=30, as_of=date(2026, 7, 1))
    pension = household_monthly_income_profile_at(household, rule, months_from_now=300, as_of=date(2026, 7, 1))

    assert unemployment.non_taxable_income == pytest.approx(2200)
    assert unemployment.gross_income == pytest.approx(5700)
    assert unemployment.gross_income - unemployment.non_taxable_income == pytest.approx(3500)
    assert flexible.personal_social == 0
    assert flexible.personal_housing_fund == 0
    assert flexible.monthly_pf_deposit == 0
    assert monthly_household_expense_at(household, 30, as_of=date(2026, 7, 1), rules=rule) == pytest.approx(2900)
    assert flexible.gross_income == pytest.approx(3500)
    assert pension.non_taxable_income > 0


def test_affordability_exposes_backend_career_shock_projection() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        social_security_months=120,
        members=[
            IncomeMember(
                name="样例成员A",
                birth_month="2001-08",
                monthly_salary_gross=30_000,
                annual_bonus=60_000,
            )
        ],
        career_shock=CareerShockData(
            enabled=True,
            auto_unemployment_benefit=True,
            auto_self_social_insurance=True,
            auto_flexible_housing_fund=True,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="样例成员A",
                    enabled=True,
                    layoff_age=35,
                    retirement_age=50,
                    auto_pension_monthly=True,
                )
            ],
        ),
    )

    result = calculate_affordability(household, ScenarioData(total_price=0), rule)

    assert result.career_shock_projection is not None
    projection = result.career_shock_projection.member_projections[0]
    assert projection.member_name == "样例成员A"
    assert projection.enabled is True
    assert projection.retirement_age == 63
    assert projection.unemployment_benefit_months == 24
    assert projection.unemployment_benefit_monthly > 0
    assert projection.self_social_insurance_monthly > 0
    assert projection.pension_monthly > 0
    assert any(stage.name.startswith("自动情景：") for stage in projection.generated_stages)
    assert any(
        stage.name.startswith("自动情景：")
        for stage in result.career_shock_projection.effective_members[0].income_stages
    )


def test_affordability_exposes_backend_investment_recommendations() -> None:
    household = HouseholdData(
        cash_account_balance=200_000,
        investments=50_000,
        monthly_expense=10_000,
        monthly_investment_amount=5_000,
        investment_cash_reserve_months=6,
        investment_auto_rebalance=True,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=30_000),
        ],
    )

    result = calculate_affordability(household, ScenarioData(total_price=0), RulePackData())

    assert result.investment_plan_recommendations
    assert result.investment_plan_recommendations[0].plan_name in {
        "cash_reserve_first",
        "balanced_monthly_investment",
        "growth_monthly_investment",
    }
    assert result.current_investment_allocation is not None
    assert result.current_investment_allocation.reserve_target == pytest.approx(60_000)
    assert result.current_investment_allocation.total_investment >= 0


def test_career_shock_uses_birth_month_for_layoff_timing() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        scheduled_expenses=[],
        career_shock=CareerShockData(
            enabled=True,
            auto_unemployment_benefit=False,
            auto_self_social_insurance=False,
            unemployment_benefit_months=24,
            unemployment_benefit_monthly=2_000,
            self_social_insurance_monthly=1_800,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="样例成员",
                    enabled=True,
                    layoff_age=35,
                )
            ],
        ),
        members=[
            IncomeMember(name="样例成员", birth_month="1980-01", current_age=30, monthly_salary_gross=20_000, annual_bonus=0, monthly_special_additional_deduction=0),
        ],
    )

    before_35 = household_monthly_income_profile_at(household, rule, months_from_now=101, as_of=date(2006, 7, 1))
    at_35 = household_monthly_income_profile_at(household, rule, months_from_now=102, as_of=date(2006, 7, 1))

    assert before_35.non_taxable_income == 0
    assert at_35.non_taxable_income == pytest.approx(2_000)


def test_purchase_plan_avoids_negative_cash_pool_after_layoff() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        cash_account_balance=900_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=12_000,
        monthly_debt_payment=0,
        required_liquidity_months=3,
        social_security_months=120,
        scheduled_expenses=[],
        car_plan=CarPlanData(enabled=False, no_car_monthly_commute_cost=0),
        career_shock=CareerShockData(
            enabled=True,
            auto_unemployment_benefit=False,
            auto_self_social_insurance=False,
            unemployment_benefit_months=0,
            unemployment_benefit_monthly=0,
            self_social_insurance_monthly=3_000,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="self",
                    enabled=True,
                    layoff_age=35,
                    retirement_age=60,
                )
            ],
        ),
        members=[
            IncomeMember(
                name="self",
                birth_month="1980-01",
                current_age=25,
                monthly_salary_gross=45_000,
                annual_bonus=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
            ),
            IncomeMember(
                name="spouse",
                monthly_salary_gross=8_000,
                annual_bonus=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
            ),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=400_000,
        commercial_loan_amount=1_600_000,
        provident_loan_amount=0,
        loan_years=25,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, rule)
    manual_plan = result.purchase_plan_analyses[0]

    assert manual_plan.cash_stress_ok is True
    assert manual_plan.minimum_cash_balance >= 0
    assert manual_plan.minimum_cash_balance_month is None or manual_plan.minimum_cash_balance_month >= (manual_plan.months_to_buy or 0)


def test_vehicle_plan_down_payment_is_counted_in_current_cash_need() -> None:
    household_without_vehicle = HouseholdData(
        phased_loans=[],
        car_plan=CarPlanData(enabled=False, no_car_monthly_commute_cost=0, vehicle_plans=[]),
    )
    household_with_vehicle = household_without_vehicle.model_copy(
        update={
            "car_plan": CarPlanData(
                enabled=False,
                no_car_monthly_commute_cost=0,
                vehicle_plans=[
                    CarPlanData(
                        enabled=True,
                        name="新增车辆需求",
                        total_price=100_000,
                        down_payment_ratio=0.5,
                        purchase_timing_mode="parallel",
                        purchase_delay_months=0,
                    )
                ],
            )
        }
    )

    base = calculate_affordability(household_without_vehicle, ScenarioData(), RulePackData())
    with_vehicle = calculate_affordability(household_with_vehicle, ScenarioData(), RulePackData())

    assert with_vehicle.total_required_cash - base.total_required_cash == pytest.approx(50_000)


def test_elderly_care_deduction_starts_when_parent_turns_sixty() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        scheduled_expenses=[],
        elderly_dependents=[
            ElderlyDependentData(
                member_name="tax member",
                birth_month="1980-01",
                is_only_child=False,
                shared_monthly_deduction=1500,
            )
        ],
        members=[
            IncomeMember(
                name="tax member",
                monthly_salary_gross=50_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
                employment_start_date="2035-01-01",
            )
        ],
    )

    november = household_monthly_income_profile_at(household, rule, as_of=date(2039, 12, 1))
    december = household_monthly_income_profile_at(household, rule, as_of=date(2040, 1, 1))
    december_without_deduction = household_monthly_income_profile_at(
        household.model_copy(update={"elderly_dependents": []}),
        rule,
        as_of=date(2040, 1, 1),
    )

    assert november.income_tax == pytest.approx(
        household_monthly_income_profile_at(
            household.model_copy(update={"elderly_dependents": []}),
            rule,
            as_of=date(2039, 12, 1),
        ).income_tax
    )
    assert december.income_tax < december_without_deduction.income_tax
    assert december.net_income > december_without_deduction.net_income


def test_only_child_elderly_care_deduction_is_more_favorable_than_shared_deduction() -> None:
    rule = _zero_contribution_rule()
    member = IncomeMember(
        name="tax member",
        monthly_salary_gross=80_000,
        annual_bonus=0,
        monthly_special_additional_deduction=0,
        housing_fund_personal_rate=0,
        housing_fund_employer_rate=0,
        employment_start_date="2035-01-01",
    )
    shared = HouseholdData(
        scheduled_expenses=[],
        members=[member],
        elderly_dependents=[
            ElderlyDependentData(
                member_name="tax member",
                birth_month="1980-01",
                is_only_child=False,
                shared_monthly_deduction=1500,
            )
        ],
    )
    only_child = shared.model_copy(
        update={
            "elderly_dependents": [
                ElderlyDependentData(
                    member_name="tax member",
                    birth_month="1980-01",
                    is_only_child=True,
                    shared_monthly_deduction=1500,
                )
            ]
        }
    )

    shared_december = household_monthly_income_profile_at(shared, rule, as_of=date(2040, 1, 1))
    only_child_december = household_monthly_income_profile_at(only_child, rule, as_of=date(2040, 1, 1))

    assert only_child_december.income_tax < shared_december.income_tax
    assert only_child_december.net_income > shared_december.net_income


def test_elderly_care_deduction_annual_summary_uses_only_eligible_months() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2040,
        scheduled_expenses=[],
        elderly_dependents=[
            ElderlyDependentData(
                member_name="tax member",
                birth_month="1980-01",
                is_only_child=False,
                shared_monthly_deduction=1500,
            )
        ],
        members=[
            IncomeMember(
                name="tax member",
                monthly_salary_gross=50_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
                employment_start_date="2035-01-01",
            )
        ],
    )

    summary_2040 = calculate_household_tax(household, rule)[0][0]
    summary_2041 = calculate_household_tax(household.model_copy(update={"income_projection_year": 2041}), rule)[0][0]
    no_deduction_2040 = calculate_household_tax(household.model_copy(update={"elderly_dependents": []}), rule)[0][0]
    no_deduction_2041 = calculate_household_tax(
        household.model_copy(update={"income_projection_year": 2041, "elderly_dependents": []}),
        rule,
    )[0][0]

    assert no_deduction_2040.taxable_income - summary_2040.taxable_income == pytest.approx(18_000)
    assert no_deduction_2041.taxable_income - summary_2041.taxable_income == pytest.approx(18_000)
    assert summary_2041.total_tax < no_deduction_2041.total_tax


def test_purchase_cash_flow_uses_income_stage_at_purchase_month() -> None:
    household = HouseholdData(
        cash_account_balance=180_000,
        investments=0,
        monthly_expense=8_000,
        monthly_debt_payment=0,
        required_liquidity_months=3,
        social_security_months=48,
        provident_fund_balance=0,
        provident_fund_monthly_deposit=0,
        scheduled_expenses=[],
        car_plan=CarPlanData(enabled=False),
        members=[
            IncomeMember(
                name="stage member",
                monthly_salary_gross=10_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
                income_stages=[
                    IncomeStageData(
                        name="before raise",
                        start_date="2026-07-01",
                        end_date="2026-12-31",
                        monthly_salary_gross=10_000,
                        annual_bonus=0,
                        monthly_special_additional_deduction=0,
                    ),
                    IncomeStageData(
                        name="after raise",
                        start_date="2027-01-01",
                        monthly_salary_gross=50_000,
                        annual_bonus=0,
                        monthly_special_additional_deduction=0,
                    ),
                ],
            )
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        moving_and_misc_cost=0,
        renovation_cost=0,
        commercial_rate=0.035,
        provident_rate=0.0285,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = max(result.purchase_plan_analyses, key=lambda item: item.commercial_loan_amount)

    assert plan.months_to_buy is not None
    assert plan.months_to_buy >= 6
    assert plan.post_purchase_cash_flow > household_monthly_income_profile_at(
        household, RulePackData(), as_of=date(2026, 7, 1)
    ).net_income - household.monthly_expense - plan.total_monthly_payment


def test_affordability_uses_net_income_after_tax() -> None:
    household = HouseholdData(
        monthly_income=200_000,
        members=[
            IncomeMember(
                name="高收入成员",
                monthly_salary_gross=80_000,
                annual_bonus=500_000,
                monthly_social_insurance=4_000,
                monthly_housing_fund=4_000,
            )
        ],
    )
    result = calculate_affordability(household, ScenarioData(), RulePackData())
    assert result.household_gross_monthly_income > result.household_net_monthly_income
    assert result.annual_income_tax > 0


def test_beijing_social_and_housing_fund_contributions_use_policy_caps() -> None:
    household = HouseholdData(
        members=[
            IncomeMember(
                name="封顶成员",
                monthly_salary_gross=60_000,
                annual_bonus=0,
                housing_fund_personal_rate=0.12,
                housing_fund_employer_rate=0.12,
                employment_start_date="2027-01-01",
            )
        ]
    )
    summaries, _, _, _ = calculate_household_tax(household, RulePackData())
    summary = summaries[0]
    assert summary.monthly_personal_housing_fund == round(35_811 * 0.12, 2)
    assert summary.monthly_personal_social_insurance == pytest.approx(35_811 * 0.105 + 3, abs=0.02)


def test_car_plan_uses_contract_installment_with_manufacturer_interest_subsidy() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=300_000,
            down_payment_ratio=0.5,
            annual_mileage_km=12_000,
            total_months=60,
            interest_free_months=24,
            later_annual_rate=0.0199,
            current_month_index=1,
        )
    )
    principal = 150_000
    monthly_rate = 0.0199 / 12
    factor = (1 + monthly_rate) ** 60
    contract_monthly = principal * monthly_rate * factor / (factor - 1)
    assert loan.down_payment == 150_000
    assert loan.contract_monthly_payment == pytest.approx(contract_monthly, abs=0.01)
    assert loan.first_phase_interest_subsidy == pytest.approx(principal * monthly_rate, abs=0.01)
    assert loan.first_phase_monthly_payment == pytest.approx(contract_monthly - principal * monthly_rate, abs=0.01)
    assert loan.later_phase_monthly_payment == pytest.approx(contract_monthly, abs=0.01)
    assert loan.total_interest_subsidy > 0
    assert loan.total_interest == loan.borrower_total_interest
    assert loan.total_interest < contract_monthly * 60 - principal
    assert loan.monthly_insurance_cost > 0
    assert loan.monthly_energy_cost > 0
    assert loan.monthly_total_ownership_cost > loan.monthly_cash_operating_cost


def test_new_energy_vehicle_purchase_tax_policy_enters_car_cash_need() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "new_energy_vehicle_purchase_tax_exempt_until": "2025-12",
                "new_energy_vehicle_purchase_tax_half_until": "2027-12",
            }
        }
    )
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=226_000,
            down_payment_ratio=0.5,
            purchase_delay_months=6,
            energy_type="pure_electric",
            new_energy_catalog_eligible=True,
        ),
        rules=rule,
    )

    gross_tax = 226_000 / 1.13 * 0.10
    assert loan.purchase_tax == pytest.approx(gross_tax / 2, abs=0.01)
    assert loan.purchase_tax_relief == pytest.approx(gross_tax / 2, abs=0.01)
    assert loan.annual_vehicle_vessel_tax == 0
    assert any("新能源车政策" in note for note in loan.policy_notes)


def test_plug_in_vehicle_vessel_tax_can_change_after_policy_period() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "plug_in_hybrid_vehicle_vessel_tax_exempt_until": "2026-12",
                "plug_in_hybrid_vehicle_vessel_tax_annual": 420,
            }
        }
    )
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.4,
            purchase_delay_months=12,
            energy_type="plug_in_hybrid",
            new_energy_catalog_eligible=True,
        ),
        rules=rule,
    )

    assert loan.purchase_tax >= 0
    assert loan.annual_vehicle_vessel_tax == pytest.approx(420)
    assert any("2027" in note for note in loan.policy_notes)


def test_vehicle_taxes_follow_policy_pack_parameters() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "vehicle_purchase_tax_rate": 0.05,
                "vehicle_purchase_tax_taxable_price_ratio": 1.0,
                "fuel_vehicle_vessel_tax_annual_default": 960,
            }
        }
    )
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.4,
            energy_type="fuel",
            new_energy_catalog_eligible=False,
        ),
        rules=rule,
    )

    assert loan.purchase_tax == pytest.approx(10_000, abs=0.01)
    assert loan.purchase_tax_relief == 0
    assert loan.annual_vehicle_vessel_tax == pytest.approx(960)
    assert any("5%" in note for note in loan.policy_notes)


def test_beijing_vehicle_indicator_delay_affects_generated_car_strategy() -> None:
    household = HouseholdData(
        cash_account_balance=300_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=35_000, annual_bonus=0)],
        car_plan=CarPlanData(
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="示例电车",
                    total_price=180_000,
                    down_payment_ratio=0.3,
                    beijing_license_indicator_status="family_new_energy_pending",
                    beijing_indicator_expected_delay_months=18,
                )
            ]
        ),
    )
    strategies = build_car_plan_analyses(
        household,
        net_monthly_income=30_000,
        rules=RulePackData(),
    )
    target = next(item for item in strategies if item.strategy_key == "target")

    assert target.purchase_delay_months >= 18
    assert target.required_cash_at_purchase >= target.down_payment + target.purchase_tax
    assert any("北京小客车" in note or "家庭新能源指标" in note for note in target.notes)


def test_beijing_family_indicator_score_wait_affects_pure_ev_strategy() -> None:
    household = HouseholdData(
        cash_account_balance=500_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=35_000, annual_bonus=0)],
        car_plan=CarPlanData(
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="示例纯电车",
                    total_price=180_000,
                    down_payment_ratio=0.3,
                    energy_type="pure_electric",
                    beijing_license_indicator_status="family_new_energy_pending",
                    beijing_family_indicator_score_enabled=True,
                    beijing_family_indicator_generations=1,
                    beijing_family_indicator_has_spouse=False,
                    beijing_family_indicator_main_points=1,
                    beijing_family_indicator_current_cutoff_score=36,
                    beijing_family_indicator_cutoff_score_annual_change=0,
                )
            ]
        ),
    )

    strategies = build_car_plan_analyses(household, net_monthly_income=30_000, rules=RulePackData())
    target = next(item for item in strategies if item.strategy_key == "target")

    assert target.beijing_family_indicator_score == pytest.approx(1)
    assert target.beijing_family_indicator_estimated_wait_months is not None
    assert target.purchase_delay_months >= target.beijing_family_indicator_estimated_wait_months


def test_beijing_family_indicator_score_uses_spouse_weight_and_generation_multiplier() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=180_000,
            energy_type="pure_electric",
            beijing_license_indicator_status="family_new_energy_pending",
            beijing_family_indicator_score_enabled=True,
            beijing_family_indicator_generations=2,
            beijing_family_indicator_has_spouse=True,
            beijing_family_indicator_main_points=3,
            beijing_family_indicator_spouse_points=2,
            beijing_family_indicator_other_applicant_count=1,
            beijing_family_indicator_other_points_total=4,
            beijing_family_indicator_current_cutoff_score=36,
        ),
        rules=RulePackData(),
    )

    assert loan.beijing_family_indicator_score == pytest.approx(((3 + 2) * 2 + 4) * 2)


def test_beijing_family_indicator_applicants_can_include_elder_for_generation_scoring() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=180_000,
            energy_type="pure_electric",
            beijing_license_indicator_status="family_new_energy_pending",
            beijing_family_indicator_score_enabled=True,
            beijing_family_indicator_application_start_month="2026-07",
            beijing_family_indicator_current_cutoff_score=36,
            beijing_family_indicator_applicants=[
                {
                    "name": "样例主申请人",
                    "relationship": "main",
                    "generation": "self_generation",
                    "eligibility_type": "beijing_household",
                    "personal_history_points_override": 3,
                },
                {
                    "name": "样例老人",
                    "relationship": "parent",
                    "generation": "parent_generation",
                    "eligibility_type": "beijing_residence_permit_social_tax",
                    "only_for_indicator_scoring": True,
                },
            ],
        ),
        rules=RulePackData(),
    )

    assert loan.beijing_family_indicator_score == pytest.approx(((2 + 3) * 2 + 1) * 2)
    assert any("样例老人" in note and "不会进入家庭现金流" in "；".join(loan.policy_notes) for note in loan.policy_notes)


def test_beijing_family_indicator_applicants_accept_runtime_dict_items() -> None:
    plan = CarPlanData(
        enabled=True,
        total_price=180_000,
        energy_type="pure_electric",
        beijing_license_indicator_status="family_new_energy_pending",
        beijing_family_indicator_score_enabled=True,
        beijing_family_indicator_application_start_month="2026-07",
        beijing_family_indicator_current_cutoff_score=36,
    )
    plan.beijing_family_indicator_applicants = [
        {
            "name": "样例主申请人",
            "relationship": "main",
            "generation": "self_generation",
            "eligibility_type": "beijing_household",
            "personal_history_points_override": 3,
        },
        {
            "name": "样例老人",
            "relationship": "parent",
            "generation": "parent_generation",
            "eligibility_type": "beijing_residence_permit_social_tax",
        },
    ]

    loan = calculate_car_loan(plan, rules=RulePackData())

    assert loan.beijing_family_indicator_score == pytest.approx(((2 + 3) * 2 + 1) * 2)


def test_range_extended_vehicle_does_not_wait_for_family_new_energy_score() -> None:
    household = HouseholdData(
        cash_account_balance=500_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=35_000, annual_bonus=0)],
        car_plan=CarPlanData(
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="示例增程车",
                    total_price=180_000,
                    down_payment_ratio=0.3,
                    energy_type="range_extended",
                    new_energy_catalog_eligible=True,
                    beijing_license_indicator_status="family_new_energy_pending",
                    beijing_indicator_expected_delay_months=6,
                    beijing_family_indicator_score_enabled=True,
                    beijing_family_indicator_generations=1,
                    beijing_family_indicator_has_spouse=False,
                    beijing_family_indicator_main_points=1,
                    beijing_family_indicator_current_cutoff_score=36,
                )
            ]
        ),
    )

    strategies = build_car_plan_analyses(household, net_monthly_income=30_000, rules=RulePackData())
    target = next(item for item in strategies if item.strategy_key == "target")

    assert target.purchase_delay_months == 6
    assert any("不能按北京家庭新能源指标上牌" in note for note in target.notes)


def test_license_plate_rental_is_cash_cost_not_vehicle_loan_or_down_payment() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.3,
            license_plate_rental_enabled=True,
            license_plate_rental_upfront_fee=20_000,
        ),
        rules=RulePackData(),
    )

    assert loan.down_payment == pytest.approx(60_000)
    assert loan.loan_principal == pytest.approx(140_000)
    assert loan.license_plate_rental_initial_fee == pytest.approx(20_000)
    assert any("不计入车辆首付、贷款本金或车辆资产" in note for note in loan.policy_notes)


def test_license_plate_rental_enters_monthly_cashflow_and_renewal() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0)],
        car_plan=CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.25,
            purchase_delay_months=2,
            total_months=36,
            license_plate_rental_enabled=True,
            license_plate_rental_upfront_fee=20_000,
            license_plate_rental_term_months=3,
            license_plate_rental_renewal_fee=18_000,
            license_plate_rental_renewal_term_months=3,
            license_plate_rental_after_term_mode="renew_until_own_indicator",
        ),
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        down_payment_amount=1_000_000,
        commercial_loan_amount=1_000_000,
        provident_loan_amount=800_000,
        manual_purchase_delay_months=12,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["手动指定"]
    purchase_month = result.car_loan.months_to_down_payment or result.car_loan.purchase_delay_months
    purchase_row = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == purchase_month
    )
    renewal_row = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == purchase_month + 3
    )

    assert purchase_row.vehicle_down_payment == pytest.approx(result.car_loan.down_payment + result.car_loan.purchase_tax)
    assert purchase_row.vehicle_plate_rental_payment == pytest.approx(20_000)
    assert any(entry.category == "vehicle_plate_rental" and entry.amount == pytest.approx(-20_000) for entry in purchase_row.ledger_entries)
    assert renewal_row.vehicle_plate_rental_payment == pytest.approx(18_000)


def test_plug_in_vehicle_does_not_use_beijing_new_energy_indicator_by_default() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.3,
            energy_type="range_extended",
            new_energy_catalog_eligible=True,
            beijing_license_indicator_status="family_new_energy_pending",
        ),
        rules=RulePackData(),
    )

    assert any("国家新能源购置税口径不等于北京新能源小客车指标口径" in note for note in loan.policy_notes)
    assert any("不能按北京家庭新能源指标上牌" in note for note in loan.policy_notes)


def test_vehicle_indicator_rules_follow_policy_pack() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_new_energy_indicator_vehicle_types": ["pure_electric", "range_extended"],
                "beijing_tail_restriction_exempt_vehicle_types": ["pure_electric", "range_extended"],
            }
        }
    )
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.3,
            energy_type="range_extended",
            new_energy_catalog_eligible=True,
            beijing_license_indicator_status="family_new_energy_pending",
        ),
        rules=rule,
    )

    joined_notes = "；".join(loan.policy_notes)
    assert "不能按北京家庭新能源指标上牌" not in joined_notes
    assert "国家新能源购置税口径不等于北京新能源小客车指标口径" not in joined_notes
    assert "按北京家庭新能源指标等待处理" in joined_notes


def test_vehicle_indicator_can_be_disabled_by_policy_pack() -> None:
    rule = RulePackData().model_copy(
        update={"params": {**RulePackData().params, "beijing_small_passenger_indicator_required": False}}
    )
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.3,
            energy_type="fuel",
            beijing_license_indicator_status="unknown",
        ),
        rules=rule,
    )

    joined_notes = "；".join(loan.policy_notes)
    assert "北京小客车上牌需要指标" not in joined_notes
    assert "普通小客车指标等待" not in joined_notes


def test_ordinary_indicator_status_is_available_for_non_pure_vehicle() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.3,
            energy_type="fuel",
            beijing_license_indicator_status="ordinary_indicator_pending",
        ),
        rules=RulePackData(),
    )

    assert any("普通小客车指标等待" in note for note in loan.policy_notes)


def test_car_operating_cost_estimate_responds_to_price_and_mileage() -> None:
    modest = calculate_car_loan(CarPlanData(enabled=True, total_price=200_000, annual_mileage_km=8_000))
    expensive_high_mileage = calculate_car_loan(CarPlanData(enabled=True, total_price=400_000, annual_mileage_km=24_000))

    assert expensive_high_mileage.monthly_energy_cost > modest.monthly_energy_cost
    assert expensive_high_mileage.monthly_depreciation_cost > modest.monthly_depreciation_cost
    assert expensive_high_mileage.monthly_total_ownership_cost > modest.monthly_total_ownership_cost


def test_phased_loans_use_current_interest_only_policy() -> None:
    summaries = summarize_phased_loans(_sample_phased_loans(), as_of=date(2026, 7, 1))
    monthly_payment = sum(item.current_monthly_payment for item in summaries)

    assert monthly_payment == pytest.approx((30_000 + 40_000) * 0.028 / 12, abs=0.01)
    assert [item.phase for item in summaries] == ["只还利息", "只还利息", "未开始计息", "未开始计息"]


def test_phased_loans_switch_to_equal_installment_after_interest_only_period() -> None:
    summaries = summarize_phased_loans(
        [
            PhasedLoanData(
                principal=20_000,
                annual_rate=0.028,
                remaining_months=120,
                interest_start_month="2026-07",
                interest_only_until="2028-07",
            )
        ],
        as_of=date(2028, 8, 1),
    )

    assert summaries[0].phase == "等额本息"
    assert summaries[0].current_monthly_payment > 20_000 * 0.028 / 12


def test_phased_loans_can_use_equal_principal_after_interest_only_period() -> None:
    equal_installment = summarize_phased_loans(
        [
            PhasedLoanData(
                principal=20_000,
                annual_rate=0.028,
                repayment_method="equal_installment",
                remaining_months=120,
                interest_start_month="2026-07",
                interest_only_until="2028-07",
            )
        ],
        as_of=date(2028, 8, 1),
    )[0]
    equal_principal = summarize_phased_loans(
        [
            PhasedLoanData(
                principal=20_000,
                annual_rate=0.028,
                repayment_method="equal_principal",
                remaining_months=120,
                interest_start_month="2026-07",
                interest_only_until="2028-07",
            )
        ],
        as_of=date(2028, 8, 1),
    )[0]

    assert equal_principal.phase == "等额本金"
    assert equal_principal.current_monthly_payment > equal_installment.current_monthly_payment


def test_phased_loans_support_manual_and_auto_prepayment() -> None:
    base = PhasedLoanData(
        name="提前还本样例",
        principal=120_000,
        annual_rate=0.05,
        remaining_months=60,
        interest_start_month="2026-07",
        interest_only_until="2026-06",
    )
    manual = base.model_copy(
        update={
            "prepayment_mode": "manual",
            "prepayment_start_month": 1,
            "prepayment_allowed_after_month": 1,
            "prepayment_monthly_amount": 2_000,
        }
    )
    auto = base.model_copy(update={"prepayment_mode": "auto", "prepayment_start_month": 1, "prepayment_allowed_after_month": 1})

    base_month0 = calculator_module._phased_loan_state_detail_at(base, 0, as_of=date(2026, 7, 1))
    manual_month0 = calculator_module._phased_loan_state_detail_at(manual, 0, as_of=date(2026, 7, 1))
    base_month12 = calculator_module._phased_loan_state_detail_at(base, 12, as_of=date(2026, 7, 1))
    manual_month12 = calculator_module._phased_loan_state_detail_at(manual, 12, as_of=date(2026, 7, 1))
    auto_summary = summarize_phased_loans([auto], as_of=date(2026, 7, 1))[0]

    assert manual_month0[1] > base_month0[1]
    assert manual_month0[2] == pytest.approx(2_000)
    assert manual_month12[0] < base_month12[0]
    assert auto_summary.current_extra_principal_payment > 0
    assert auto_summary.prepayment_mode == "auto"


def test_phased_loan_auto_prepayment_respects_investment_opportunity_cost() -> None:
    loan = PhasedLoanData(
        name="低息已有贷款样例",
        principal=120_000,
        annual_rate=0.028,
        remaining_months=60,
        interest_start_month="2026-07",
        interest_only_until="2026-06",
        prepayment_mode="auto",
        prepayment_start_month=1,
        prepayment_allowed_after_month=1,
    )

    low_return = summarize_phased_loans([loan], as_of=date(2026, 7, 1), annual_investment_return=0.0)[0]
    high_return = summarize_phased_loans([loan], as_of=date(2026, 7, 1), annual_investment_return=0.08)[0]

    assert low_return.current_extra_principal_payment > 0
    assert high_return.current_extra_principal_payment == 0


def test_car_plan_is_included_in_affordability_cash_flow() -> None:
    household = HouseholdData(car_plan=CarPlanData(enabled=True, total_price=300_000))
    with_car = calculate_affordability(household, ScenarioData(), RulePackData())
    without_car = calculate_affordability(
        household.model_copy(update={"car_plan": CarPlanData(enabled=False)}),
        ScenarioData(),
        RulePackData(),
    )
    assert with_car.post_purchase_cash_flow < without_car.post_purchase_cash_flow
    assert with_car.debt_to_income_ratio > without_car.debt_to_income_ratio


def test_no_car_commute_cost_is_included_when_car_plan_disabled() -> None:
    base = HouseholdData(phased_loans=[], car_plan=CarPlanData(enabled=False, no_car_monthly_commute_cost=0))
    with_commute = base.model_copy(
        update={"car_plan": CarPlanData(enabled=False, no_car_monthly_commute_cost=1800)}
    )

    no_commute_result = calculate_affordability(base, ScenarioData(), RulePackData())
    commute_result = calculate_affordability(with_commute, ScenarioData(), RulePackData())

    assert commute_result.post_purchase_cash_flow == pytest.approx(no_commute_result.post_purchase_cash_flow - 1800)


def test_affordability_counts_phased_loans_as_effective_debt() -> None:
    household_without_loans = HouseholdData(phased_loans=[], monthly_debt_payment=1_000)
    household_with_loans = household_without_loans.model_copy(update={"phased_loans": _sample_phased_loans()[:1]})
    without_phased_loans = calculate_affordability(
        household_without_loans,
        ScenarioData(),
        RulePackData(),
    )
    with_phased_loans = calculate_affordability(household_with_loans, ScenarioData(), RulePackData())

    assert with_phased_loans.phased_loan_monthly_payment > 0
    assert with_phased_loans.effective_monthly_debt_payment == pytest.approx(
        with_phased_loans.phased_loan_monthly_payment + household_with_loans.monthly_debt_payment
    )
    assert with_phased_loans.post_purchase_cash_flow < without_phased_loans.post_purchase_cash_flow


def test_affordability_returns_backend_loan_visualization_series() -> None:
    result = calculate_affordability(
        HouseholdData(
            cash_account_balance=1_200_000,
            monthly_income=80_000,
            monthly_expense=12_000,
            monthly_debt_payment=1_000,
            phased_loans=[
                PhasedLoanData(
                    name="教育贷款A",
                    principal=120_000,
                    annual_rate=0.028,
                    remaining_months=120,
                    interest_start_month="2026-07",
                    interest_only_until="2028-07",
                ),
                PhasedLoanData(
                    borrower="样例成员B",
                    name="消费贷B",
                    loan_type="consumer",
                    principal=60_000,
                    annual_rate=0.036,
                    remaining_months=72,
                    interest_start_month="2026-07",
                    interest_only_until="2026-07",
                ),
            ],
        ),
        ScenarioData(total_price=2_000_000, down_payment_amount=700_000),
        RulePackData(),
    )
    plan = max(
        result.purchase_plan_analyses,
        key=lambda item: item.commercial_loan_amount + item.provident_loan_amount,
    )
    rows = [item for item in result.loan_visualization if item.plan_variant == plan.variant]

    assert rows
    assert rows[0].existing_loan_balance == pytest.approx(180_000)
    assert rows[0].existing_monthly_payment > 1_000
    assert [item.name for item in rows[0].existing_loan_details] == ["教育贷款A", "消费贷B"]
    assert sum(item.balance for item in rows[0].existing_loan_details) == pytest.approx(rows[0].existing_loan_balance)
    assert rows[0].existing_monthly_payment == pytest.approx(
        1_000 + sum(item.monthly_payment for item in rows[0].existing_loan_details)
    )
    if plan.months_to_buy is not None:
        purchase_row = rows[plan.months_to_buy]
        later_row = rows[min(plan.months_to_buy + 12, len(rows) - 1)]
        assert purchase_row.home_loan_balance > 0
        assert later_row.home_loan_balance < purchase_row.home_loan_balance
        assert purchase_row.total_loan_balance >= purchase_row.home_loan_balance


def test_backend_loan_visualization_projects_selected_strategy_loans_by_month() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        monthly_expense=12_000,
        required_liquidity_months=3,
        social_security_months=180,
        car_plan=CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.25,
            target_purchase_mode="delayed",
            purchase_delay_months=6,
            total_months=60,
        ),
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=60_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=4_000_000,
        down_payment_amount=1_300_000,
        commercial_loan_amount=1_500_000,
        provident_loan_amount=1_000_000,
        manual_purchase_delay_months=3,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["手动指定"]
    rows = [item for item in result.loan_visualization if item.plan_variant == plan.variant]

    assert plan.months_to_buy is not None
    assert plan.commercial_loan_amount > 0
    assert plan.provident_loan_amount > 0
    assert result.car_loan.loan_principal > 0
    assert rows
    assert rows[0].commercial_loan_balance == 0
    assert rows[0].provident_loan_balance == 0
    assert rows[0].vehicle_loan_balance == 0

    purchase_row = next(item for item in rows if item.month == plan.months_to_buy)
    assert purchase_row.commercial_loan_balance == pytest.approx(plan.commercial_loan_amount)
    assert purchase_row.provident_loan_balance == pytest.approx(plan.provident_loan_amount)
    assert purchase_row.home_loan_balance == pytest.approx(
        purchase_row.commercial_loan_balance + purchase_row.provident_loan_balance
    )

    car_purchase_month = result.car_loan.months_to_down_payment or result.car_loan.purchase_delay_months
    car_row = next(item for item in rows if item.month == car_purchase_month)
    assert car_row.vehicle_loan_balance == pytest.approx(result.car_loan.loan_principal)
    cashflow_car_row = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == car_purchase_month
    )
    car_transaction_cash = result.car_loan.down_payment + result.car_loan.purchase_tax
    assert cashflow_car_row.transaction_cash_out >= car_transaction_cash
    assert cashflow_car_row.vehicle_down_payment == pytest.approx(car_transaction_cash)
    assert cashflow_car_row.first_vehicle_down_payment == pytest.approx(car_transaction_cash)
    assert cashflow_car_row.vehicle_asset_value == pytest.approx(result.car_loan.total_price)
    assert cashflow_car_row.first_vehicle_asset_value == pytest.approx(result.car_loan.total_price)
    assert 0 <= cashflow_car_row.happiness_score <= 10
    assert any(
        entry.category == "vehicle_down_payment" and entry.amount == pytest.approx(-car_transaction_cash)
        for entry in cashflow_car_row.ledger_entries
    )

    later_row = next(item for item in rows if item.month == max(plan.months_to_buy, car_purchase_month) + 12)
    assert later_row.commercial_loan_balance < purchase_row.commercial_loan_balance
    assert later_row.provident_loan_balance < purchase_row.provident_loan_balance
    assert later_row.vehicle_loan_balance < car_row.vehicle_loan_balance


def test_commercial_and_vehicle_prepayment_reduce_interest_and_balances() -> None:
    household = HouseholdData(
        cash_account_balance=1_200_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="sample", monthly_salary_gross=80_000, annual_bonus=0)],
        car_plan=CarPlanData(enabled=False, vehicle_plans=[]),
    )
    base_scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=800_000,
        commercial_loan_amount=1_000_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=1,
        commercial_rate=0.04,
        commercial_prepayment_mode="none",
        loan_years=20,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    prepay_scenario = base_scenario.model_copy(
        update={
            "commercial_prepayment_mode": "manual",
            "commercial_prepayment_enabled": True,
            "commercial_prepayment_start_month": 1,
            "commercial_prepayment_monthly_amount": 5_000,
        }
    )

    base_result = calculate_affordability(household, base_scenario, RulePackData())
    prepay_result = calculate_affordability(household, prepay_scenario, RulePackData())
    base_plan = {item.variant: item for item in base_result.purchase_plan_analyses}["手动指定"]
    prepay_plan = {item.variant: item for item in prepay_result.purchase_plan_analyses}["手动指定"]

    assert prepay_plan.commercial_prepayment_enabled
    assert prepay_plan.commercial_prepayment_allowed_after_month == 12
    assert prepay_plan.commercial_prepayment_start_month == 12
    assert prepay_plan.commercial_actual_payoff_months < base_plan.commercial_loan_years * 12
    assert prepay_plan.commercial_interest_saved_by_prepayment > 0
    assert prepay_plan.total_interest < base_plan.total_interest

    base_rows = [item for item in base_result.loan_visualization if item.plan_variant == base_plan.variant]
    prepay_rows = [item for item in prepay_result.loan_visualization if item.plan_variant == prepay_plan.variant]
    first_payment_row = next(item for item in prepay_rows if item.month == prepay_plan.months_to_buy + 1)
    assert first_payment_row.commercial_extra_principal_payment == 0
    compare_month = prepay_plan.months_to_buy + 24
    base_row = next(item for item in base_rows if item.month == compare_month)
    prepay_row = next(item for item in prepay_rows if item.month == compare_month)
    assert prepay_row.commercial_extra_principal_payment == pytest.approx(5_000)
    assert prepay_row.commercial_loan_balance < base_row.commercial_loan_balance

    base_car = calculate_car_loan(
        CarPlanData(enabled=True, total_price=120_000, down_payment_ratio=0.2, total_months=60, interest_free_months=0, later_annual_rate=0.05)
    )
    prepay_car = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=120_000,
            down_payment_ratio=0.2,
            total_months=60,
            interest_free_months=0,
            later_annual_rate=0.05,
            loan_prepayment_enabled=True,
            loan_prepayment_start_month=1,
            loan_prepayment_monthly_amount=1_000,
        )
    )
    assert prepay_car.prepayment_enabled
    assert prepay_car.prepayment_allowed_after_month == 12
    assert prepay_car.prepayment_start_month == 12
    assert prepay_car.actual_payoff_months < base_car.total_months
    assert prepay_car.total_interest < base_car.total_interest
    assert prepay_car.interest_saved_by_prepayment > 0


def test_auto_commercial_prepayment_is_chosen_from_cashflow_pressure() -> None:
    roomy_household = HouseholdData(
        cash_account_balance=1_600_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="sample", monthly_salary_gross=90_000, annual_bonus=0)],
        car_plan=CarPlanData(enabled=False, vehicle_plans=[]),
    )
    tight_household = HouseholdData(
        cash_account_balance=900_000,
        monthly_expense=24_000,
        members=[IncomeMember(name="sample", monthly_salary_gross=28_000, annual_bonus=0)],
        car_plan=CarPlanData(enabled=False, vehicle_plans=[]),
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=800_000,
        commercial_loan_amount=1_000_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=1,
        commercial_rate=0.045,
        commercial_prepayment_mode="auto",
        commercial_prepayment_allowed_after_month=12,
        commercial_prepayment_monthly_amount=0,
        loan_years=20,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    no_prepay_scenario = scenario.model_copy(update={"commercial_prepayment_mode": "none"})

    roomy_result = calculate_affordability(roomy_household, scenario, RulePackData())
    no_prepay_result = calculate_affordability(roomy_household, no_prepay_scenario, RulePackData())
    tight_result = calculate_affordability(tight_household, scenario, RulePackData())

    roomy_plan = {item.variant: item for item in roomy_result.purchase_plan_analyses}["手动指定"]
    no_prepay_plan = {item.variant: item for item in no_prepay_result.purchase_plan_analyses}["手动指定"]
    tight_plan = {item.variant: item for item in tight_result.purchase_plan_analyses}["手动指定"]

    assert roomy_plan.commercial_prepayment_mode == "auto"
    assert roomy_plan.commercial_prepayment_enabled
    assert roomy_plan.commercial_prepayment_start_month >= roomy_plan.commercial_prepayment_allowed_after_month
    assert roomy_plan.commercial_prepayment_monthly_amount > 0
    assert roomy_plan.commercial_interest_saved_by_prepayment > 0
    assert roomy_plan.total_interest < no_prepay_plan.total_interest

    assert tight_plan.commercial_prepayment_mode == "auto"
    assert not tight_plan.commercial_prepayment_enabled
    assert tight_plan.commercial_prepayment_monthly_amount == 0


def test_auto_commercial_prepayment_respects_investment_opportunity_cost() -> None:
    household = HouseholdData(
        cash_account_balance=1_600_000,
        monthly_expense=8_000,
        members=[IncomeMember(name="sample", monthly_salary_gross=90_000, annual_bonus=0)],
        car_plan=CarPlanData(enabled=False, vehicle_plans=[]),
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=800_000,
        commercial_loan_amount=1_000_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=1,
        commercial_rate=0.04,
        commercial_prepayment_mode="auto",
        commercial_prepayment_allowed_after_month=12,
        loan_years=20,
        annual_investment_return=0.08,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["手动指定"]

    assert plan.commercial_prepayment_mode == "auto"
    assert not plan.commercial_prepayment_enabled
    assert plan.commercial_prepayment_monthly_amount == 0


def test_affordability_returns_backend_account_cashflow_series() -> None:
    household = HouseholdData(
        cash_account_balance=900_000,
        investments=120_000,
        monthly_expense=14_000,
        monthly_investment_amount=5_000,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=45_000, annual_bonus=60_000),
            IncomeMember(name="样例成员B", monthly_salary_gross=20_000, annual_bonus=20_000),
        ],
        phased_loans=[
            PhasedLoanData(
                name="样例阶段性贷款",
                principal=80_000,
                annual_rate=0.028,
                remaining_months=96,
                interest_start_month="2026-07",
                interest_only_until="2028-07",
            )
        ],
    )
    scenario = ScenarioData(total_price=2_200_000, down_payment_amount=800_000)
    result = calculate_affordability(household, scenario, RulePackData())
    plan = result.purchase_plan_analyses[0]

    rows = [item for item in result.monthly_cashflow_visualization if item.plan_variant == plan.variant]
    snapshots = [item for item in result.account_snapshots if item.plan_variant == plan.variant]
    loan_rows = [item for item in result.loan_visualization if item.plan_variant == plan.variant]

    assert rows
    assert snapshots
    assert rows[0].cash_balance == pytest.approx(household.cash_account_balance)
    assert rows[0].investment_balance == pytest.approx(household.investments)
    assert rows[0].liquid_asset_value == pytest.approx(household.cash_account_balance + household.investments)
    assert all(item.cash_balance >= 0 for item in rows)
    assert all(item.investment_balance >= 0 for item in rows)
    assert all(item.provident_balance >= 0 for item in rows)
    assert all(item.fixed_asset_value >= 0 for item in rows)
    assert all(item.total_asset_value >= 0 for item in rows)
    assert rows[1].cash_income > 0
    assert rows[1].living_expense == pytest.approx(household.monthly_expense)
    assert rows[1].investment_contribution >= 0
    assert rows[1].regular_debt_payment + rows[1].phased_loan_payment == pytest.approx(rows[1].debt_payment)
    assert snapshots[12].liquid_asset_value == pytest.approx(
        snapshots[12].cash_balance + snapshots[12].investment_balance
    )
    assert snapshots[12].total_loan_balance == pytest.approx(loan_rows[12].total_loan_balance)
    assert snapshots[12].net_worth == pytest.approx(snapshots[12].total_asset_value - snapshots[12].total_loan_balance)
    assert any(item.category == "income" for item in result.monthly_ledger if item.plan_variant == plan.variant)


def test_investment_return_tax_reduces_compounded_investment_balance() -> None:
    household = HouseholdData(
        cash_account_balance=50_000,
        investments=100_000,
        monthly_expense=0,
        investment_taxable_return_ratio=1.0,
        investment_return_tax_rate=0.20,
        members=[IncomeMember(name="样例成员", monthly_salary_gross=0, annual_bonus=0)],
    )
    scenario = ScenarioData(total_price=10_000_000, annual_investment_return=0.12)

    result = calculate_affordability(household, scenario, RulePackData())
    plan = result.purchase_plan_analyses[0]
    first_return_month = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == 1
    )

    assert first_return_month.investment_return == pytest.approx(1000)
    assert first_return_month.investment_tax == pytest.approx(200)
    assert first_return_month.investment_balance == pytest.approx(100_800)


def test_account_balances_are_non_negative_but_net_worth_can_be_negative() -> None:
    household = HouseholdData(
        cash_account_balance=20_000,
        investments=0,
        monthly_expense=8_000,
        members=[IncomeMember(name="样例成员", monthly_salary_gross=12_000, annual_bonus=0)],
        phased_loans=[
            PhasedLoanData(
                name="样例大额贷款",
                principal=500_000,
                annual_rate=0.04,
                remaining_months=120,
                interest_start_month="2026-07",
                interest_only_until="2026-07",
            )
        ],
    )
    result = calculate_affordability(household, ScenarioData(total_price=10_000_000), RulePackData())
    plan = result.purchase_plan_analyses[0]
    first_row = next(item for item in result.monthly_cashflow_visualization if item.plan_variant == plan.variant)

    assert first_row.cash_balance >= 0
    assert first_row.investment_balance >= 0
    assert first_row.provident_balance >= 0
    assert first_row.fixed_asset_value >= 0
    assert first_row.total_asset_value >= 0
    assert first_row.net_worth < 0


def test_investment_strategy_sweeps_excess_cash_toward_cash_reserve() -> None:
    household = HouseholdData(
        cash_account_balance=500_000,
        investments=0,
        monthly_expense=12_000,
        required_liquidity_months=10,
        investment_cash_reserve_months=2,
        monthly_investment_amount=5_000,
        investment_auto_rebalance=True,
        members=[IncomeMember(name="样例成员", monthly_salary_gross=20_000, annual_bonus=0)],
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(total_price=10_000_000, annual_investment_return=0)
    result = calculate_affordability(household, scenario, RulePackData())
    plan = result.purchase_plan_analyses[0]
    rows = [item for item in result.monthly_cashflow_visualization if item.plan_variant == plan.variant]
    first_year = rows[:13]
    investment_reserve = household.monthly_expense * household.investment_cash_reserve_months
    purchase_reserve = household.monthly_expense * household.required_liquidity_months

    assert plan.months_to_buy is None or plan.months_to_buy > 24
    assert first_year[12].cash_balance < first_year[0].cash_balance
    assert first_year[12].investment_balance > first_year[0].investment_balance
    assert sum(item.investment_contribution for item in first_year[1:13]) > household.monthly_investment_amount * 12
    assert sum(item.investment_contribution_cash_sweep for item in first_year[1:13]) > 0
    assert all(
        item.investment_contribution
        == pytest.approx(item.investment_contribution_base + item.investment_contribution_cash_sweep)
        for item in first_year[1:13]
    )
    assert min(item.cash_balance for item in rows[:25]) >= investment_reserve - 1
    assert min(item.cash_balance for item in rows[:25]) < purchase_reserve


def test_investment_strategy_redeems_to_protect_cash_reserve() -> None:
    household = HouseholdData(
        cash_account_balance=20_000,
        investments=300_000,
        monthly_expense=10_000,
        required_liquidity_months=3,
        investment_cash_reserve_months=3,
        monthly_investment_amount=0,
        investment_auto_rebalance=True,
        members=[IncomeMember(name="样例成员", monthly_salary_gross=0, annual_bonus=0)],
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(total_price=10_000_000, annual_investment_return=0)
    result = calculate_affordability(household, scenario, RulePackData())
    plan = result.purchase_plan_analyses[0]
    rows = [item for item in result.monthly_cashflow_visualization if item.plan_variant == plan.variant]
    reserve_target = household.monthly_expense * household.investment_cash_reserve_months

    assert rows[1].investment_sell_proceeds > 0
    assert rows[1].cash_balance == pytest.approx(reserve_target)
    assert min(item.cash_balance for item in rows[1:13]) >= reserve_target - 1
    assert rows[12].investment_balance < rows[0].investment_balance


def test_affordability_returns_backend_strategy_events_and_concepts() -> None:
    household = HouseholdData(
        cash_account_balance=2_000_000,
        investments=200_000,
        provident_fund_balance=80_000,
        monthly_expense=12_000,
        required_liquidity_months=3,
        social_security_months=180,
        monthly_investment_amount=3_000,
        car_plan=CarPlanData(
            enabled=True,
            total_price=180_000,
            down_payment_ratio=0.3,
            purchase_delay_months=2,
            total_months=36,
            interest_free_months=12,
        ),
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=60_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=40_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_800_000,
        down_payment_amount=1_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=120_000,
        renovation_funding_mode="after_purchase_saving",
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["手动指定"]
    events = [item for item in result.plan_events if item.plan_variant == plan.variant]
    explanations = [item for item in result.strategy_explanations if item.plan_variant == plan.variant]
    concept_codes = {item.code for item in result.account_concepts}

    assert {"cash_account", "investment_account", "liquid_asset_account", "provident_account", "loan_account", "net_worth"}.issubset(concept_codes)
    assert explanations
    assert any(item.section == "loan" and "公积金贷" in item.body for item in explanations)
    assert events
    assert any(item.category == "account" and item.month == 0 for item in events)
    assert any(item.category == "home_purchase" and item.month == plan.months_to_buy for item in events)
    assert any(item.category == "loan" and "贷款结构" in item.title for item in events)
    assert any(item.category == "vehicle" and "车辆购入" in item.title for item in events)
    assert any(item.category == "renovation" for item in events)


def test_affordability_generates_multiple_car_purchase_strategies() -> None:
    result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="member", monthly_salary_gross=45_000)],
            cash_account_balance=200_000,
            monthly_expense=18_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=300_000,
                down_payment_ratio=0.5,
                financing_options=[
                    VehicleFinancingOptionData(
                        id="dealer_subsidy",
                        name="经销商贴息方案",
                        financing_type="dealer_subsidy",
                        total_months=60,
                        interest_free_months=24,
                        later_annual_rate=0.0199,
                        min_down_payment_ratio=0.10,
                        prepayment_allowed=True,
                        prepayment_allowed_after_month=12,
                    )
                ],
            ),
        ),
        ScenarioData(),
        RulePackData(),
    )
    plans = {item.strategy_key: item for item in result.car_plan_analyses}

    assert list(plans) == ["target", "cash", "high_down_low_loan", "low_down_keep_cash", "delay_purchase"]
    assert plans["target"].total_price == 300_000
    assert plans["target"].down_payment_ratio == 0.5
    assert plans["cash"].loan_principal == 0
    assert plans["high_down_low_loan"].down_payment_ratio != plans["target"].down_payment_ratio
    assert plans["high_down_low_loan"].down_payment > plans["low_down_keep_cash"].down_payment
    assert plans["low_down_keep_cash"].loan_principal > plans["high_down_low_loan"].loan_principal
    assert plans["delay_purchase"].purchase_delay_months >= 12
    assert plans["high_down_low_loan"].total_months == plans["target"].total_months
    assert plans["high_down_low_loan"].financing_option_name == plans["target"].financing_option_name
    assert plans["low_down_keep_cash"].down_payment_ratio <= 0.20
    assert plans["low_down_keep_cash"].total_months == 60
    assert all(0 <= item.happiness_score <= 10 for item in plans.values())
    assert len({item.happiness_score for item in plans.values()}) > 1


def test_car_strategy_generation_deduplicates_equivalent_cash_plans() -> None:
    result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="sample member", monthly_salary_gross=42_000)],
            cash_account_balance=260_000,
            monthly_expense=16_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=180_000,
                down_payment_ratio=0.35,
            ),
        ),
        ScenarioData(),
        RulePackData(),
    )

    immediate_cash_plans = [
        item
        for item in result.car_plan_analyses
        if item.loan_principal <= 1 and item.purchase_delay_months == 0
    ]

    assert len(immediate_cash_plans) == 1
    assert immediate_cash_plans[0].strategy_key == "cash"
    assert immediate_cash_plans[0].financing_type == "cash_only"
    assert all(
        not (
            item.loan_principal <= 1
            and item.strategy_key in {"target", "high_down_low_loan", "low_down_keep_cash", "accelerated_principal"}
        )
        for item in result.car_plan_analyses
    )


def test_selected_car_strategy_changes_home_purchase_strategy() -> None:
    def result_for(selection: str):
        car_plan = CarPlanData(
            enabled=False,
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="示例车辆",
                    selected_strategy_variant=selection,
                    total_price=300_000,
                    down_payment_ratio=0.5,
                    purchase_timing_mode="parallel",
                    planning_sequence=1,
                    financing_options=[
                        VehicleFinancingOptionData(
                            id="dealer_plan",
                            name="经销商方案",
                            financing_type="dealer_subsidy",
                            total_months=60,
                            interest_free_months=24,
                            later_annual_rate=0.0199,
                            min_down_payment_ratio=0.10,
                            max_down_payment_ratio=1.0,
                            prepayment_allowed=True,
                            prepayment_allowed_after_month=12,
                        )
                    ],
                )
            ],
        )
        return calculate_affordability(
            HouseholdData(
                members=[IncomeMember(name="样例成员A", monthly_salary_gross=55_000)],
                cash_account_balance=850_000,
                monthly_expense=16_000,
                social_security_months=120,
                car_plan=car_plan,
            ),
            ScenarioData(
                total_price=3_000_000,
                down_payment_amount=900_000,
                renovation_cost=0,
                moving_and_misc_cost=0,
                broker_fee_rate=0,
            ),
            RulePackData(),
        )

    cash_result = result_for("经销商方案 | cash")
    low_down_result = result_for("经销商方案 | low_down_keep_cash")

    cash_plan = cash_result.purchase_plan_analyses[-1]
    low_down_plan = low_down_result.purchase_plan_analyses[-1]

    assert cash_result.car_plan_analyses
    assert low_down_result.car_plan_analyses
    assert low_down_plan.months_to_buy is not None
    assert cash_plan.months_to_buy is not None
    assert low_down_plan.months_to_buy < cash_plan.months_to_buy
    assert low_down_plan.cash_after_transaction > cash_plan.cash_after_transaction


def test_car_prepayment_strategy_is_chosen_from_cashflow_pressure() -> None:
    roomy_result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="member", monthly_salary_gross=50_000)],
            cash_account_balance=300_000,
            monthly_expense=12_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=220_000,
                down_payment_ratio=0.3,
                financing_options=[
                    VehicleFinancingOptionData(
                        id="standard_high_rate",
                        name="普通高息贷款",
                        financing_type="standard",
                        total_months=60,
                        interest_free_months=0,
                        later_annual_rate=0.05,
                        prepayment_allowed_after_month=1,
                    )
                ],
                loan_prepayment_enabled=True,
                loan_prepayment_monthly_amount=0,
            ),
        ),
        ScenarioData(),
        RulePackData(),
    )
    tight_result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="member", monthly_salary_gross=18_000)],
            cash_account_balance=80_000,
            monthly_expense=17_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=220_000,
                down_payment_ratio=0.3,
                financing_options=[
                    VehicleFinancingOptionData(
                        id="standard_high_rate",
                        name="普通高息贷款",
                        financing_type="standard",
                        total_months=60,
                        interest_free_months=0,
                        later_annual_rate=0.05,
                        prepayment_allowed_after_month=1,
                    )
                ],
                loan_prepayment_enabled=True,
                loan_prepayment_monthly_amount=0,
            ),
        ),
        ScenarioData(),
        RulePackData(),
    )

    roomy_plan = {item.strategy_key: item for item in roomy_result.car_plan_analyses}["accelerated_principal"]
    tight_plans = {item.strategy_key: item for item in tight_result.car_plan_analyses}

    assert roomy_plan.prepayment_enabled
    assert roomy_plan.prepayment_monthly_amount > 0
    assert roomy_plan.interest_saved_by_prepayment > 0
    assert any("auto_extra_principal" in note for note in roomy_plan.notes)
    assert "accelerated_principal" not in tight_plans


def test_car_prepayment_strategy_respects_investment_opportunity_cost() -> None:
    result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="member", monthly_salary_gross=60_000)],
            cash_account_balance=400_000,
            monthly_expense=10_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=220_000,
                down_payment_ratio=0.3,
                later_annual_rate=0.035,
                loan_prepayment_enabled=True,
                loan_prepayment_monthly_amount=0,
            ),
        ),
        ScenarioData(annual_investment_return=0.08),
        RulePackData(),
    )
    assert "accelerated_principal" not in {item.strategy_key for item in result.car_plan_analyses}


def test_car_prepayment_strategy_respects_financing_contract_permission() -> None:
    result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="sample member", monthly_salary_gross=80_000)],
            cash_account_balance=900_000,
            monthly_expense=12_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=300_000,
                down_payment_ratio=0.2,
                financing_options=[
                    VehicleFinancingOptionData(
                        id="no_prepay_offer",
                        name="不可提前还本金融方案",
                        financing_type="standard",
                        total_months=60,
                        later_annual_rate=0.08,
                        prepayment_allowed=False,
                        prepayment_allowed_after_month=12,
                        prepayment_policy_note="合同约定不可提前还本。",
                    )
                ],
                loan_prepayment_enabled=True,
                loan_prepayment_monthly_amount=20_000,
                loan_prepayment_lump_sum_month=12,
                loan_prepayment_lump_sum_amount=100_000,
            ),
        ),
        ScenarioData(annual_investment_return=0.01),
        RulePackData(),
    )

    assert "accelerated_principal" not in {item.strategy_key for item in result.car_plan_analyses}


def test_car_prepayment_strategy_can_choose_lump_sum_and_monthly_combo() -> None:
    result = calculate_affordability(
        HouseholdData(
            members=[IncomeMember(name="sample member", monthly_salary_gross=80_000)],
            cash_account_balance=900_000,
            monthly_expense=12_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=300_000,
                down_payment_ratio=0.3,
                later_annual_rate=0.08,
                loan_prepayment_enabled=True,
                loan_prepayment_monthly_amount=0,
            ),
        ),
        ScenarioData(annual_investment_return=0.02),
        RulePackData(),
    )

    plan = {item.strategy_key: item for item in result.car_plan_analyses}["accelerated_principal"]

    assert plan.prepayment_enabled
    assert plan.prepayment_strategy_type in {"lump_sum", "monthly", "hybrid"}
    assert plan.prepayment_total_extra_principal > 0
    assert plan.prepayment_net_benefit > 0
    assert "自动策略" in plan.prepayment_explanation
    assert plan.prepayment_lump_sum_amount > 0 or plan.prepayment_monthly_amount > 0


def test_car_plan_generates_strategies_for_each_vehicle_source_candidate() -> None:
    car_plan = CarPlanData(
        enabled=True,
        vehicle_plans=[
            CarPlanData(
                enabled=True,
                name="family car",
                total_price=220_000,
                candidate_vehicles=[
                    CarPlanData(enabled=True, name="compact ev", total_price=180_000, down_payment_ratio=0.3),
                    CarPlanData(enabled=True, name="large ev", total_price=320_000, down_payment_ratio=0.4),
                ],
            )
        ],
    )
    result = calculate_affordability(
        HouseholdData(cash_account_balance=300_000, monthly_expense=12_000, car_plan=car_plan),
        ScenarioData(),
        RulePackData(),
    )

    strategies = result.car_plan_analyses
    assert len(strategies) == 12
    assert {item.vehicle_candidate_name for item in strategies} == {"compact ev", "large ev"}
    assert {item.vehicle_candidate_index for item in strategies} == {0, 1}
    assert all(
        len([item for item in strategies if item.vehicle_candidate_name == candidate]) <= 6
        for candidate in {"compact ev", "large ev"}
    )
    assert all(
        len([item for item in strategies if item.vehicle_candidate_name == candidate and item.strategy_key == "target"]) == 1
        for candidate in {"compact ev", "large ev"}
    )
    compact_target = next(
        item
        for item in strategies
        if item.vehicle_candidate_name == "compact ev"
        and item.strategy_key == "target"
    )
    large_target = next(
        item
        for item in strategies
        if item.vehicle_candidate_name == "large ev"
        and item.strategy_key == "target"
    )
    assert compact_target.total_price == 180_000
    assert large_target.total_price == 320_000
    assert compact_target.strategy_key == "target"
    assert compact_target.variant.endswith("target")


def test_vehicle_candidate_plans_use_demand_level_registration_policy() -> None:
    vehicle = CarPlanData(
        enabled=True,
        name="示例用车需求",
        total_price=220_000,
        beijing_license_indicator_status="family_new_energy_pending",
        beijing_indicator_expected_delay_months=18,
        license_plate_rental_enabled=True,
        license_plate_rental_upfront_fee=18_000,
        beijing_family_indicator_score_enabled=True,
        beijing_family_indicator_generations=3,
        candidate_vehicles=[
            CarPlanData(
                enabled=True,
                name="候选车源A",
                total_price=180_000,
                beijing_license_indicator_status="already_have",
                beijing_indicator_expected_delay_months=0,
                license_plate_rental_enabled=False,
                beijing_family_indicator_score_enabled=False,
                beijing_family_indicator_generations=1,
            )
        ],
    )

    _, candidate = vehicle_candidate_plans(vehicle)[0]

    assert candidate.beijing_license_indicator_status == "family_new_energy_pending"
    assert candidate.beijing_indicator_expected_delay_months == 18
    assert candidate.license_plate_rental_enabled is True
    assert candidate.license_plate_rental_upfront_fee == 18_000
    assert candidate.beijing_family_indicator_score_enabled is True
    assert candidate.beijing_family_indicator_generations == 3
    assert candidate.energy_type == "pure_electric"
    assert candidate.total_price == 180_000


def test_car_plan_generates_strategies_for_each_vehicle_financing_option() -> None:
    car_plan = CarPlanData(
        enabled=True,
        vehicle_plans=[
            CarPlanData(
                enabled=True,
                name="commuter car",
                total_price=180_000,
                candidate_vehicles=[
                    CarPlanData(
                        enabled=True,
                        name="compact ev",
                        total_price=180_000,
                        down_payment_ratio=0.3,
                        financing_options=[
                            VehicleFinancingOptionData(
                                id="dealer_subsidy",
                                name="经销商贴息方案",
                                financing_type="dealer_subsidy",
                                total_months=60,
                                interest_free_months=24,
                                later_annual_rate=0.0199,
                            ),
                            VehicleFinancingOptionData(
                                id="standard_loan",
                                name="普通贷款方案",
                                financing_type="standard",
                                total_months=48,
                                interest_free_months=0,
                                later_annual_rate=0.039,
                            ),
                        ],
                    )
                ],
            )
        ],
    )

    result = calculate_affordability(
        HouseholdData(cash_account_balance=300_000, monthly_expense=12_000, car_plan=car_plan),
        ScenarioData(),
        RulePackData(),
    )

    strategies = result.car_plan_analyses
    assert len(strategies) == 6
    assert {item.financing_option_name for item in strategies} == {"经销商贴息方案", "普通贷款方案"}
    assert sum(1 for item in strategies if item.strategy_key == "cash") == 1
    assert sum(1 for item in strategies if item.strategy_key == "target") == 1
    subsidized_target = next(item for item in strategies if item.financing_option_name == "经销商贴息方案" and item.strategy_key == "target")
    assert subsidized_target.total_months == 60
    assert subsidized_target.interest_free_months == 24
    assert subsidized_target.later_annual_rate == 0.0199
    assert any(item.financing_option_name == "普通贷款方案" for item in strategies)


def test_vehicle_purchase_events_can_be_ordered_around_home_purchase() -> None:
    car_plan = CarPlanData(
        enabled=True,
        vehicle_plans=[
            CarPlanData(
                enabled=True,
                name="先买车",
                total_price=160_000,
                down_payment_ratio=0.5,
                planning_sequence=1,
                purchase_delay_months=2,
            ),
            CarPlanData(
                enabled=True,
                name="房后车",
                total_price=220_000,
                down_payment_ratio=0.4,
                planning_sequence=3,
                purchase_delay_months=4,
                after_previous_event_delay_months=6,
            ),
        ],
    )
    scenario = ScenarioData(total_price=3_000_000, purchase_sequence=2)

    pre_home_states = calculator_module._vehicle_loan_states(
        car_plan,
        scenario=scenario,
        include_after_home=False,
    )
    plan_states = calculator_module._vehicle_loan_states(
        car_plan,
        scenario=scenario,
        home_purchase_month=18,
    )

    assert [item[1].name for item in pre_home_states] == ["先买车"]
    assert {item[1].name for item in plan_states} == {"先买车", "房后车"}
    after_home_vehicle = next(item for item in plan_states if item[1].name == "房后车")
    assert after_home_vehicle[3] == 24


def test_vehicle_order_uses_planning_goal_sequence_before_legacy_purchase_sequence() -> None:
    car_plan = CarPlanData(
        enabled=True,
        vehicle_plans=[
            CarPlanData(
                enabled=True,
                name="目标车辆",
                planning_goal_id="vehicle-goal",
                total_price=180_000,
                down_payment_ratio=0.4,
                planning_sequence=1,
                purchase_delay_months=2,
                after_previous_event_delay_months=5,
            ),
        ],
    )
    scenario = ScenarioData(total_price=3_000_000, purchase_sequence=2)
    context = CalculationContextSnapshot(
        household_id="household-a",
        scenario_id="home-goal",
        current_goal_id="home-goal",
        planning_goals=[
            CalculationContextGoalSnapshot(
                id="home-goal",
                goal_type="home",
                name="目标房源",
                priority=1,
                sequence_index=1,
                normalized_timing_mode="auto_sequence",
            ),
            CalculationContextGoalSnapshot(
                id="vehicle-goal",
                goal_type="vehicle",
                name="目标车辆",
                priority=2,
                sequence_index=2,
                normalized_timing_mode="auto_sequence",
            ),
        ],
    )

    pre_home_states = calculator_module._vehicle_loan_states(
        car_plan,
        scenario=scenario,
        include_after_home=False,
        calculation_context=context,
    )
    plan_states = calculator_module._vehicle_loan_states(
        car_plan,
        scenario=scenario,
        home_purchase_month=18,
        calculation_context=context,
    )

    assert pre_home_states == []
    assert [item[1].name for item in plan_states] == ["目标车辆"]
    assert plan_states[0][3] == 23


def test_projection_vehicle_state_uses_selected_home_purchase_month_for_goal_dependency() -> None:
    household = HouseholdData(
        cash_account_balance=900_000,
        investments=0,
        monthly_expense=6_000,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=50_000, annual_bonus=0)],
        car_plan=CarPlanData(
            enabled=True,
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="房后车辆",
                    planning_goal_id="vehicle-goal",
                    total_price=120_000,
                    down_payment_ratio=0.5,
                    planning_sequence=1,
                    purchase_delay_months=0,
                    after_previous_event_delay_months=6,
                    selected_strategy_variant="target",
                )
            ],
        ),
    )
    scenario = ScenarioData(
        planning_goal_id="home-goal",
        selected_purchase_plan_variant="手动指定",
        total_price=1_000_000,
        down_payment_amount=300_000,
        commercial_loan_amount=500_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=2,
        purchase_sequence=2,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    context = CalculationContextSnapshot(
        household_id="household-a",
        scenario_id="home-goal",
        current_goal_id="home-goal",
        planning_goals=[
            CalculationContextGoalSnapshot(
                id="home-goal",
                goal_type="home",
                name="目标房源",
                priority=1,
                sequence_index=1,
                normalized_timing_mode="manual_month",
                resolved_not_before_month=2,
            ),
            CalculationContextGoalSnapshot(
                id="vehicle-goal",
                goal_type="vehicle",
                name="房后车辆",
                priority=2,
                sequence_index=2,
                normalized_timing_mode="auto_sequence",
            ),
        ],
    )

    result = calculate_affordability(household, scenario, _zero_contribution_rule(), calculation_context=context)
    plan = next(item for item in result.purchase_plan_analyses if item.variant == "手动指定")
    vehicle_down_payment_months = [
        item.month
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.vehicle_down_payment > 0
    ]

    assert plan.months_to_buy is not None
    assert plan.months_to_buy >= 2
    assert vehicle_down_payment_months
    assert min(vehicle_down_payment_months) >= plan.months_to_buy + 6


def test_loan_projection_vehicle_dependency_uses_each_purchase_plan_month() -> None:
    household = HouseholdData(
        cash_account_balance=900_000,
        investments=0,
        monthly_expense=6_000,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=50_000, annual_bonus=0)],
        car_plan=CarPlanData(
            enabled=True,
            vehicle_plans=[
                CarPlanData(
                    enabled=True,
                    name="房后车辆",
                    planning_goal_id="vehicle-goal",
                    total_price=120_000,
                    down_payment_ratio=0.5,
                    planning_sequence=1,
                    purchase_delay_months=0,
                    after_previous_event_delay_months=6,
                    selected_strategy_variant="target",
                )
            ],
        ),
    )
    scenario = ScenarioData(
        planning_goal_id="home-goal",
        selected_purchase_plan_variant="手动指定",
        total_price=1_000_000,
        down_payment_amount=300_000,
        commercial_loan_amount=500_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=2,
        purchase_sequence=2,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    context = CalculationContextSnapshot(
        household_id="household-a",
        scenario_id="home-goal",
        current_goal_id="home-goal",
        planning_goals=[
            CalculationContextGoalSnapshot(
                id="home-goal",
                goal_type="home",
                name="目标房源",
                priority=1,
                sequence_index=1,
                normalized_timing_mode="manual_month",
                resolved_not_before_month=2,
            ),
            CalculationContextGoalSnapshot(
                id="vehicle-goal",
                goal_type="vehicle",
                name="房后车辆",
                priority=2,
                sequence_index=2,
                normalized_timing_mode="auto_sequence",
            ),
        ],
    )

    result = calculate_affordability(household, scenario, _zero_contribution_rule(), calculation_context=context)
    plan_by_variant = {item.variant: item for item in result.purchase_plan_analyses}
    manual_plan = plan_by_variant["手动指定"]
    delayed_plan = next(
        item
        for item in result.purchase_plan_analyses
        if item.variant != manual_plan.variant and item.months_to_buy is not None and item.months_to_buy > manual_plan.months_to_buy
    )

    first_vehicle_balance_month_by_variant: dict[str, int] = {}
    for row in result.loan_visualization:
        if row.vehicle_loan_balance > 0 and row.plan_variant not in first_vehicle_balance_month_by_variant:
            first_vehicle_balance_month_by_variant[row.plan_variant] = row.month

    assert manual_plan.months_to_buy is not None
    assert delayed_plan.months_to_buy is not None
    assert first_vehicle_balance_month_by_variant[manual_plan.variant] >= manual_plan.months_to_buy + 6
    assert first_vehicle_balance_month_by_variant[delayed_plan.variant] >= delayed_plan.months_to_buy + 6
    assert first_vehicle_balance_month_by_variant[delayed_plan.variant] > first_vehicle_balance_month_by_variant[manual_plan.variant]


def test_vehicle_list_order_uses_resolved_planning_goal_sequence() -> None:
    car_plan = CarPlanData(
        enabled=True,
        vehicle_plans=[
            CarPlanData(
                enabled=True,
                name="旧顺序靠前车辆",
                planning_goal_id="vehicle-goal-b",
                total_price=200_000,
                down_payment_ratio=0.5,
                planning_sequence=1,
                purchase_delay_months=1,
            ),
            CarPlanData(
                enabled=True,
                name="目标顺序靠前车辆",
                planning_goal_id="vehicle-goal-a",
                total_price=160_000,
                down_payment_ratio=0.5,
                planning_sequence=2,
                purchase_delay_months=1,
            ),
        ],
    )
    context = CalculationContextSnapshot(
        household_id="household-a",
        planning_goals=[
            CalculationContextGoalSnapshot(
                id="vehicle-goal-a",
                goal_type="vehicle",
                name="目标顺序靠前车辆",
                priority=9,
                sequence_index=1,
                normalized_timing_mode="auto_sequence",
            ),
            CalculationContextGoalSnapshot(
                id="vehicle-goal-b",
                goal_type="vehicle",
                name="旧顺序靠前车辆",
                priority=1,
                sequence_index=2,
                normalized_timing_mode="auto_sequence",
            ),
        ],
    )

    plan_states = calculator_module._vehicle_loan_states(
        car_plan,
        calculation_context=context,
    )

    assert [item[1].name for item in plan_states] == ["目标顺序靠前车辆", "旧顺序靠前车辆"]
    assert [item[1].planning_sequence for item in plan_states] == [1, 2]


def test_manual_car_target_strategy_reflects_user_inputs() -> None:
    result = calculate_affordability(
        HouseholdData(
            cash_account_balance=200_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=420_000,
                down_payment_ratio=0.35,
                financing_options=[
                    VehicleFinancingOptionData(
                        id="manual_dealer_offer",
                        name="手动经销商方案",
                        financing_type="dealer_subsidy",
                        total_months=72,
                        interest_free_months=12,
                        later_annual_rate=0.026,
                        min_down_payment_ratio=0.10,
                        max_down_payment_ratio=1.0,
                    )
                ],
            ),
        ),
        ScenarioData(),
        RulePackData(),
    )

    manual = {item.strategy_key: item for item in result.car_plan_analyses}["target"]
    assert manual.total_price == 420_000
    assert manual.down_payment_ratio == 0.35
    assert manual.down_payment == 147_000
    assert manual.total_months == 72
    assert manual.interest_free_months == 12
    assert manual.later_annual_rate == 0.026


def test_delayed_car_plan_has_no_current_monthly_payment() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=300_000,
            down_payment_ratio=0.5,
            purchase_delay_months=12,
        ),
        initial_cash=1_000_000,
        monthly_cash_savings_before_car=30_000,
    )

    assert loan.months_to_down_payment == 12
    assert loan.current_monthly_payment == 0
    assert loan.first_phase_monthly_payment > 0


def test_affordability_returns_multiple_purchase_plan_analyses() -> None:
    result = calculate_affordability(HouseholdData(), ScenarioData(total_price=3_000_000), RulePackData())
    plans = {item.variant: item for item in result.purchase_plan_analyses}
    assert set(plans) == {"手动指定", "0商贷", "微量商贷", "较多商贷"}
    assert all(plan.provident_loan_amount >= 0 for plan in plans.values())
    assert all(plan.minimum_cash_balance >= 0 for plan in plans.values())
    assert all(0 <= plan.recommendation_score <= 100 for plan in plans.values())
    assert all(plan.recommendation_reasons for plan in plans.values())
    assert sum(1 for plan in plans.values() if plan.is_recommended) == 1
    assert plans["0商贷"].commercial_loan_amount == 0


def test_disabled_purchase_target_returns_no_purchase_baseline() -> None:
    result = calculate_affordability(
        HouseholdData(cash_account_balance=100_000),
        ScenarioData(enabled=False, total_price=3_000_000),
        RulePackData(),
    )

    assert result.status == "不买房基线"
    assert result.purchase_plan_analyses == []
    assert result.total_required_cash == 0
    assert result.minimum_down_payment == 0
    assert result.monthly_payment == 0


def test_provident_loan_cap_uses_150k_per_deposit_year() -> None:
    household = HouseholdData(
        social_security_months=48,
        cash_account_balance=4_000_000,
        car_plan=CarPlanData(enabled=False),
    )
    result = calculate_affordability(household, ScenarioData(total_price=3_000_000), RulePackData())

    generated = [item for item in result.purchase_plan_analyses if item.variant != "手动指定"]
    assert {item.provident_loan_amount for item in generated} == {600_000}


def test_provident_loan_cap_comes_from_policy_interface() -> None:
    from app.domain.housing import provident_loan_cap

    household = HouseholdData(existing_home_count=0, social_security_months=120)
    scenario = ScenarioData(total_price=3_000_000, property_type="新房")
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_loan_amount_per_deposit_year": 80_000,
            "provident_first_home_loan_cap": 700_000,
            "provident_green_three_star_bonus": 200_000,
            "provident_policy_bonus_cap": 200_000,
        }
    )
    efficient_home = scenario.model_copy(update={"green_building_level": "three_star"})

    regular_cap, regular_bonus = provident_loan_cap(household, scenario, rules)
    efficient_cap, efficient_bonus = provident_loan_cap(household, efficient_home, rules)

    assert regular_bonus == 0
    assert regular_cap == pytest.approx(700_000)
    assert efficient_bonus == pytest.approx(200_000)
    assert efficient_cap == pytest.approx(900_000)


def test_home_purchase_eligibility_comes_from_policy_interface() -> None:
    from app.domain.household import evaluate_home_purchase_eligibility

    household = HouseholdData(
        has_beijing_hukou=False,
        social_security_months=48,
        existing_home_count=1,
    )
    base_rules = RulePackData(
        params={
            **RulePackData().params,
            "required_social_security_months": 60,
            "max_home_count": 2,
        }
    )
    relaxed_rules = RulePackData(
        params={
            **RulePackData().params,
            "required_social_security_months": 36,
            "max_home_count": 1,
        }
    )

    eligible_by_months, month_notes = evaluate_home_purchase_eligibility(household, relaxed_rules)
    eligible_by_home_count, home_count_notes = evaluate_home_purchase_eligibility(household, base_rules)

    assert eligible_by_months is False
    assert any("上限 1 套" in note for note in month_notes)
    assert eligible_by_home_count is False
    assert any("60 个月" in note for note in home_count_notes)


def test_provident_repayment_capacity_cap_comes_from_policy_interface() -> None:
    from app.domain.housing import provident_loan_cap

    household = HouseholdData(existing_home_count=0, social_security_months=240)
    scenario = ScenarioData(total_price=3_000_000, property_type="新房", loan_years=30)
    base_rules = RulePackData()
    constrained_rules = RulePackData(
        params={
            **base_rules.params,
            "provident_repayment_capacity_enabled": True,
            "provident_repayment_income_ratio": 0.10,
            "provident_basic_living_cost_per_person": 0,
        }
    )

    base_cap, _ = provident_loan_cap(
        household,
        scenario,
        base_rules,
        monthly_income_for_capacity=30_000,
        borrower_count=1,
    )
    constrained_cap, _ = provident_loan_cap(
        household,
        scenario,
        constrained_rules,
        monthly_income_for_capacity=30_000,
        borrower_count=1,
    )

    assert base_cap == pytest.approx(1_200_000)
    assert constrained_cap < base_cap
    assert constrained_cap == pytest.approx(749_364, rel=0.01)


def test_first_home_provident_minimum_down_payment_uses_current_20_percent_policy() -> None:
    household = HouseholdData(
        existing_home_count=0,
        existing_mortgage_count=0,
        social_security_months=180,
        cash_account_balance=2_000_000,
        monthly_expense=8_000,
        required_liquidity_months=1,
        car_plan=CarPlanData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    provident_plans = [item for item in result.purchase_plan_analyses if item.provident_loan_amount > 0]

    assert provident_plans
    assert min(item.minimum_down_payment for item in provident_plans) == pytest.approx(scenario.total_price * 0.20)


def test_affordability_summary_minimum_down_payment_uses_policy_interface() -> None:
    household = HouseholdData(
        existing_home_count=0,
        existing_mortgage_count=0,
        social_security_months=180,
        cash_account_balance=2_000_000,
        monthly_expense=8_000,
        required_liquidity_months=1,
        car_plan=CarPlanData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rule = RulePackData()
    rule = rule.model_copy(
        update={
            "params": {
                **rule.params,
                "minimum_down_payment_ratio": 0.80,
                "first_home_provident_min_down_payment_ratio": 0.20,
                "first_home_commercial_min_down_payment_ratio": 0.15,
            }
        }
    )

    result = calculate_affordability(household, scenario, rule)

    assert result.minimum_down_payment == pytest.approx(scenario.total_price * 0.20)


def test_second_home_provident_plan_uses_25_percent_minimum_down_payment() -> None:
    household = HouseholdData(
        existing_home_count=1,
        social_security_months=180,
        cash_account_balance=2_000_000,
        monthly_expense=8_000,
        required_liquidity_months=1,
        car_plan=CarPlanData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    provident_plans = [item for item in result.purchase_plan_analyses if item.provident_loan_amount > 0]

    assert provident_plans
    assert all(item.minimum_down_payment >= scenario.total_price * 0.25 for item in provident_plans)


def test_purchase_plan_provident_cap_depends_on_plan_purchase_time() -> None:
    household = HouseholdData(
        social_security_months=48,
        cash_account_balance=1_300_000,
        investments=0,
        monthly_expense=8_000,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=40_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
            )
        ],
        career_shock=CareerShockData(enabled=False),
        car_plan=CarPlanData(enabled=False),
    )
    scenario = ScenarioData(total_price=3_000_000)

    result = calculate_affordability(household, scenario, RulePackData())
    plans = {item.variant: item for item in result.purchase_plan_analyses}

    assert plans["较多商贷"].months_to_buy == 0
    assert plans["较多商贷"].provident_policy_cap == 600_000
    assert plans["较多商贷"].provident_loan_amount == 600_000
    assert plans["0商贷"].months_to_buy is not None
    assert plans["0商贷"].months_to_buy > 0
    assert plans["0商贷"].provident_policy_cap > plans["较多商贷"].provident_policy_cap


def test_provident_loan_cap_respects_repayment_capacity() -> None:
    household = HouseholdData(
        social_security_months=180,
        cash_account_balance=2_000_000,
        monthly_expense=6_000,
        required_liquidity_months=1,
        members=[
            IncomeMember(name="样例成员", monthly_salary_gross=5_000, annual_bonus=0),
        ],
        car_plan=CarPlanData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        down_payment_amount=2_000_000,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["较多商贷"]

    assert plan.provident_policy_cap < 1_200_000
    assert plan.provident_loan_amount <= plan.provident_policy_cap


def test_eligible_green_or_ultra_low_energy_home_increases_provident_cap() -> None:
    household = HouseholdData(social_security_months=96)
    regular = calculate_affordability(
        household,
        ScenarioData(total_price=3_000_000, property_type="二手房"),
        RulePackData(),
    )
    efficient_new_home = calculate_affordability(
        household,
        ScenarioData(
            total_price=3_000_000,
            property_type="新房",
            green_building_level="three_star",
            is_ultra_low_energy_building=True,
        ),
        RulePackData(),
    )

    regular_plan = {item.variant: item for item in regular.purchase_plan_analyses}["0商贷"]
    efficient_plan = {item.variant: item for item in efficient_new_home.purchase_plan_analyses}["0商贷"]
    assert regular_plan.provident_policy_bonus == 0
    assert efficient_plan.provident_policy_bonus == 400_000
    assert efficient_plan.provident_policy_cap == 1_600_000
    assert efficient_plan.provident_loan_amount > regular_plan.provident_loan_amount


def test_new_home_provident_policy_bonus_can_stack_until_cap() -> None:
    result = calculate_affordability(
        HouseholdData(social_security_months=120),
        ScenarioData(
            total_price=3_000_000,
            property_type="新房",
            green_building_level="two_star",
            prefab_building_level="A",
        ),
        RulePackData(),
    )
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]

    assert plan.provident_policy_bonus == 300_000
    assert plan.provident_policy_cap == 1_500_000


def test_new_home_clears_second_hand_policy_fields() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="新房",
        loan_years=30,
        building_age_years=45,
        building_structure="brick_mixed",
        is_old_community_renovated=True,
        remaining_land_use_years=20,
    )

    assert scenario.building_age_years == 0
    assert scenario.building_structure == "unknown"
    assert scenario.is_old_community_renovated is False
    assert scenario.remaining_land_use_years is None

    result = calculate_affordability(HouseholdData(borrower_age=30, social_security_months=96), scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    assert plan.provident_loan_years == 30
    assert "房龄" not in "；".join(plan.provident_loan_year_limit_reasons)
    assert "土地" not in "；".join(plan.provident_loan_year_limit_reasons)


def test_second_hand_clears_new_home_bonus_fields() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="二手房",
        green_building_level="three_star",
        prefab_building_level="AAA",
        is_ultra_low_energy_building=True,
    )

    assert scenario.green_building_level == "none"
    assert scenario.prefab_building_level == "none"
    assert scenario.is_ultra_low_energy_building is False

    result = calculate_affordability(HouseholdData(social_security_months=96), scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    assert plan.provident_policy_bonus == 0


def test_new_home_provident_loan_years_can_use_requested_term() -> None:
    scenario = ScenarioData(total_price=3_000_000, property_type="新房", loan_years=30, provident_loan_amount=1_000_000)
    result = calculate_affordability(HouseholdData(borrower_age=30, social_security_months=96), scenario, RulePackData())

    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    assert plan.provident_loan_years == 30
    assert result.provident_loan is not None
    assert result.provident_loan.years == 30


def test_second_hand_brick_mixed_age_limits_provident_loan_years() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="二手房",
        loan_years=25,
        building_age_years=30,
        building_structure="brick_mixed",
    )
    result = calculate_affordability(HouseholdData(borrower_age=30, social_security_months=96), scenario, RulePackData())

    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    expected_25_year_payment = calculate_loan(
        plan.provident_loan_amount,
        plan.provident_rate,
        25,
        scenario.provident_repayment_method,
    ).first_month_payment
    assert plan.provident_loan_years == 17
    assert "砖混结构" in "；".join(plan.provident_loan_year_limit_reasons)
    assert plan.provident_monthly_payment > expected_25_year_payment


def test_second_hand_steel_concrete_age_allows_longer_provident_loan_years() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="二手房",
        loan_years=30,
        building_age_years=30,
        building_structure="steel_concrete",
    )
    result = calculate_affordability(HouseholdData(borrower_age=30, social_security_months=96), scenario, RulePackData())

    plan = result.purchase_plan_analyses[0]
    assert plan.provident_loan_years == 27
    assert "钢混结构" in "；".join(plan.provident_loan_year_limit_reasons)


def test_provident_rate_comes_from_policy_pack_not_scenario() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_first_home_rate_6_to_30_years": 0.0123,
        }
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="新房",
        loan_years=30,
        provident_rate=0.19,
    )
    result = calculate_affordability(
        HouseholdData(cash_account_balance=900_000, borrower_age=30, social_security_months=120),
        scenario,
        rules,
    )

    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    assert plan.provident_rate == pytest.approx(0.0123)
    assert plan.provident_monthly_payment == pytest.approx(
        calculate_loan(
            plan.provident_loan_amount,
            0.0123,
            plan.provident_loan_years,
            plan.provident_repayment_method,
        ).first_month_payment,
        abs=0.01,
    )


def test_deed_tax_rate_comes_from_policy_pack_by_home_count_and_area() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "deed_tax_standard_area_sqm": 140,
            "deed_tax_first_home_large_rate": 0.013,
            "deed_tax_second_home_large_rate": 0.024,
        }
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        area_sqm=160,
        deed_tax_rate=0,
    )
    first_home = calculate_affordability(
        HouseholdData(cash_account_balance=1_200_000, social_security_months=120),
        scenario,
        rules,
    ).purchase_plan_analyses[0]
    second_home = calculate_affordability(
        HouseholdData(cash_account_balance=1_200_000, social_security_months=120, existing_home_count=1),
        scenario,
        rules,
    ).purchase_plan_analyses[0]

    assert first_home.deed_tax_rate == pytest.approx(0.013)
    assert first_home.deed_tax_amount == pytest.approx(39_000)
    assert second_home.deed_tax_rate == pytest.approx(0.024)
    assert second_home.deed_tax_amount == pytest.approx(72_000)


def test_renovated_old_community_uses_remaining_land_years_for_provident_term() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="二手房",
        loan_years=30,
        building_age_years=45,
        building_structure="brick_mixed",
        is_old_community_renovated=True,
        remaining_land_use_years=25,
    )
    result = calculate_affordability(HouseholdData(borrower_age=30, social_security_months=96), scenario, RulePackData())

    plan = result.purchase_plan_analyses[0]
    assert plan.provident_loan_years == 22
    assert "剩余土地使用年限" in "；".join(plan.provident_loan_year_limit_reasons)


def test_borrower_age_limits_provident_loan_years() -> None:
    scenario = ScenarioData(total_price=3_000_000, property_type="新房", loan_years=30)
    result = calculate_affordability(HouseholdData(borrower_age=50, social_security_months=96), scenario, RulePackData())

    plan = result.purchase_plan_analyses[0]
    assert plan.provident_loan_years == 18
    assert "50 岁" in "；".join(plan.provident_loan_year_limit_reasons)


def test_purchase_plan_uses_separate_commercial_and_provident_repayment_methods() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        commercial_repayment_method="equal_principal",
        provident_repayment_method="equal_installment",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )
    result = calculate_affordability(HouseholdData(), scenario, RulePackData())
    more_commercial = {item.variant: item for item in result.purchase_plan_analyses}["较多商贷"]

    assert more_commercial.commercial_loan_amount > 0
    assert more_commercial.commercial_repayment_method == "equal_principal"
    assert more_commercial.provident_repayment_method == "equal_installment"
    assert more_commercial.commercial_monthly_payment > calculate_loan(
        more_commercial.commercial_loan_amount,
        scenario.commercial_rate,
        scenario.loan_years,
        "equal_installment",
    ).first_month_payment


def test_generated_purchase_plans_calculate_loan_mix_from_target_and_rules() -> None:
    scenario = ScenarioData(
        total_price=3_000_000,
        down_payment_amount=999_999,
        commercial_loan_amount=999_999,
        provident_loan_amount=999_999,
        micro_commercial_loan_ratio=0.08,
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )
    rules = RulePackData()

    result = calculate_affordability(HouseholdData(), scenario, rules)
    plans = {item.variant: item for item in result.purchase_plan_analyses}

    assert plans["手动指定"].commercial_loan_amount == pytest.approx(scenario.commercial_loan_amount)
    assert plans["手动指定"].planned_down_payment + plans["手动指定"].provident_loan_amount + plans["手动指定"].commercial_loan_amount == pytest.approx(
        scenario.total_price
    )
    assert plans["0商贷"].commercial_loan_amount == 0
    assert plans["0商贷"].planned_down_payment + plans["0商贷"].provident_loan_amount == pytest.approx(
        scenario.total_price
    )
    assert plans["微量商贷"].commercial_loan_amount == pytest.approx(
        scenario.total_price * scenario.micro_commercial_loan_ratio
    )
    assert plans["较多商贷"].commercial_loan_amount > plans["微量商贷"].commercial_loan_amount

    for plan in plans.values():
        assert plan.planned_down_payment + plan.provident_loan_amount + plan.commercial_loan_amount == pytest.approx(
            scenario.total_price
        )


def test_micro_commercial_strategy_auto_selects_ratio_within_bounds() -> None:
    from app.policies import get_policy

    rules = RulePackData()
    rules = rules.model_copy(
        update={
            "params": {
                **rules.params,
                "micro_commercial_loan_ratio": 0.05,
                "micro_commercial_loan_ratio_min": 0.02,
                "micro_commercial_loan_ratio_max": 0.12,
            }
        }
    )
    home_policy = get_policy(rules).home_strategy_policy()
    household = HouseholdData(
        cash_account_balance=1_150_000,
        investments=0,
        social_security_months=48,
        monthly_expense=8_000,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=45_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        micro_commercial_loan_ratio=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    result = calculate_affordability(household, scenario, rules)
    positive_commercial = sorted(
        [item for item in result.purchase_plan_analyses if item.commercial_loan_amount > 0],
        key=lambda item: item.commercial_loan_amount,
    )
    zero_commercial = next(
        item
        for item in result.purchase_plan_analyses
        if item.commercial_loan_amount == 0 and item.variant != "手动指定"
    )
    micro_plan = positive_commercial[0]

    assert home_policy.micro_commercial_loan_ratio == pytest.approx(0.05)
    assert home_policy.micro_commercial_loan_ratio_min == pytest.approx(0.02)
    assert home_policy.micro_commercial_loan_ratio_max == pytest.approx(0.12)
    assert scenario.total_price * 0.02 <= micro_plan.commercial_loan_amount <= scenario.total_price * 0.12
    assert micro_plan.months_to_buy is not None
    assert zero_commercial.months_to_buy is None or micro_plan.months_to_buy <= zero_commercial.months_to_buy


def test_micro_commercial_strategy_avoids_negative_cash_for_400w_new_home() -> None:
    rules = RulePackData()
    rules = rules.model_copy(
        update={
            "params": {
                **rules.params,
                "micro_commercial_loan_ratio": 0.05,
                "micro_commercial_loan_ratio_min": 0.02,
                "micro_commercial_loan_ratio_max": 0.12,
                "provident_base_loan_cap": 600_000,
                "provident_loan_cap_increase_per_year": 150_000,
                "provident_upfront_purchase_extract_ratio_new_home": 1.0,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=300_000,
        investments=0,
        provident_fund_balance=200_000,
        social_security_months=60,
        monthly_expense=12_000,
        required_liquidity_months=6,
        members=[
            IncomeMember(
                name="样例成员",
                birth_month="1995-01",
                monthly_salary_gross=20_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=4_000_000,
        property_type="新房",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    result = calculate_affordability(household, scenario, rules)
    micro_plan = next(item for item in result.purchase_plan_analyses if item.variant == "微量商贷")

    assert micro_plan.months_to_buy is not None
    assert micro_plan.cash_stress_ok is True
    assert micro_plan.cash_stress_shortfall == 0
    assert micro_plan.minimum_cash_balance >= 0
    assert scenario.total_price * 0.02 <= micro_plan.commercial_loan_amount <= scenario.total_price * 0.12


def test_family_provident_support_reduces_new_home_upfront_cash_need() -> None:
    household = HouseholdData(
        cash_account_balance=800_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=60,
        family_provident_support_enabled=True,
        family_provident_initial_balance=100_000,
        family_provident_monthly_salary=10_000,
        family_provident_total_rate=0.24,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=50_000,
                annual_bonus=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        property_type="新房",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    with_support = calculate_affordability(household, scenario, RulePackData())
    without_support = calculate_affordability(
        household.model_copy(update={"family_provident_support_enabled": False}),
        scenario,
        RulePackData(),
    )
    support_plan = next(item for item in with_support.purchase_plan_analyses if item.variant == "较多商贷")
    base_plan = next(item for item in without_support.purchase_plan_analyses if item.variant == "较多商贷")

    assert support_plan.family_provident_upfront_extractable > 0
    assert support_plan.required_cash_after_pf_extract < base_plan.required_cash_after_pf_extract
    assert support_plan.family_provident_upfront_extractable == pytest.approx(
        base_plan.required_cash_after_pf_extract - support_plan.required_cash_after_pf_extract,
        abs=1,
    )
    assert support_plan.family_down_payment_support_mode == "provident"
    assert support_plan.family_down_payment_support_amount == pytest.approx(support_plan.family_provident_upfront_extractable)


def test_family_savings_support_reduces_second_hand_upfront_cash_need() -> None:
    household = HouseholdData(
        cash_account_balance=700_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=60,
        family_provident_support_enabled=True,
        family_down_payment_support_mode="savings",
        family_savings_support_amount=120_000,
        family_provident_support_label="亲属积蓄首付支持",
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=50_000,
                annual_bonus=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        property_type="二手房",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    with_support = calculate_affordability(household, scenario, RulePackData())
    without_support = calculate_affordability(
        household.model_copy(update={"family_provident_support_enabled": False}),
        scenario,
        RulePackData(),
    )
    support_plan = next(item for item in with_support.purchase_plan_analyses if item.variant == "较多商贷")
    base_plan = next(item for item in without_support.purchase_plan_analyses if item.variant == "较多商贷")

    assert support_plan.family_down_payment_support_mode == "savings"
    assert support_plan.family_down_payment_support_label == "亲属积蓄首付支持"
    assert support_plan.family_down_payment_support_amount == pytest.approx(120_000)
    assert support_plan.required_cash_after_pf_extract == pytest.approx(
        base_plan.required_cash_after_pf_extract - 120_000
    )


def test_family_provident_support_does_not_reduce_second_hand_upfront_cash_need_by_default() -> None:
    household = HouseholdData(
        cash_account_balance=700_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=60,
        family_provident_support_enabled=True,
        family_down_payment_support_mode="provident",
        family_provident_initial_balance=120_000,
        members=[IncomeMember(name="样例成员", monthly_salary_gross=50_000, annual_bonus=0)],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        property_type="二手房",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = next(item for item in result.purchase_plan_analyses if item.variant == "较多商贷")

    assert plan.family_down_payment_support_mode == "none"
    assert plan.family_down_payment_support_amount == 0


def test_car_annual_insurance_and_maintenance_grow_by_owning_year() -> None:
    plan = CarPlanData(
        enabled=True,
        total_price=100_000,
        down_payment_ratio=1,
        annual_mileage_km=0,
        monthly_parking_cost=0,
        annual_insurance_min=5_000,
        annual_maintenance_cost=2_000,
        annual_insurance_growth_rate=0.10,
        annual_maintenance_growth_rate=0.20,
    )
    loan = calculate_car_loan(plan)

    first_year_cost = _car_monthly_cash_cost_at(plan, loan, 0)
    second_year_cost = _car_monthly_cash_cost_at(plan, loan, 12)

    assert first_year_cost == pytest.approx(7_000, abs=0.2)
    assert second_year_cost == pytest.approx(5_500 + 2_400, abs=0.2)


def test_vehicle_service_years_default_to_actual_performance_life() -> None:
    plan = CarPlanData(enabled=True, total_price=120_000, purchase_delay_months=0, annual_mileage_km=12_000)

    assert plan.vehicle_service_years == 10
    assert calculator_module._vehicle_update_month(plan, 0) == 120


def test_vehicle_retirement_stops_operating_cost_but_keeps_unpaid_loan() -> None:
    household = HouseholdData(
        cash_account_balance=2_000_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=60_000, annual_bonus=0)],
        car_plan=CarPlanData(
            enabled=True,
            total_price=120_000,
            down_payment_ratio=0.2,
            total_months=36,
            interest_free_months=0,
            later_annual_rate=0.04,
            purchase_delay_months=0,
            annual_mileage_km=100_000,
            electricity_kwh_per_100km=15,
            electricity_price_per_kwh=1,
            monthly_parking_cost=600,
            annual_insurance_min=6_000,
            annual_maintenance_cost=2_400,
            vehicle_service_years=15,
            vehicle_retirement_mileage_km=100_000,
            no_car_monthly_commute_cost=900,
        ),
    )
    scenario = ScenarioData(total_price=5_000_000, annual_investment_return=0)

    result = calculate_affordability(household, scenario, RulePackData())
    plan_variant = result.purchase_plan_analyses[0].variant
    before_retirement = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan_variant and item.month == 11
    )
    retirement_month = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan_variant and item.month == 12
    )
    retirement_loan = next(
        item
        for item in result.loan_visualization
        if item.plan_variant == plan_variant and item.month == 12
    )

    assert before_retirement.vehicle_asset_value > 0
    assert before_retirement.first_vehicle_energy_cost > 0
    assert before_retirement.first_vehicle_parking_cost > 0
    assert retirement_month.vehicle_asset_value == 0
    assert retirement_month.first_vehicle_energy_cost == 0
    assert retirement_month.first_vehicle_parking_cost == 0
    assert retirement_month.no_car_commute_cost == pytest.approx(900)
    assert retirement_month.vehicle_operating_cost == pytest.approx(900)
    assert retirement_loan.vehicle_loan_balance > 0
    assert any("更新/报废" in event.title for event in result.plan_events)


def test_family_provident_support_can_make_400w_new_home_micro_plan_cash_safe() -> None:
    rules = RulePackData()
    rules = rules.model_copy(
        update={
            "params": {
                **rules.params,
                "micro_commercial_loan_ratio": 0.05,
                "micro_commercial_loan_ratio_min": 0.02,
                "micro_commercial_loan_ratio_max": 0.12,
                "provident_base_loan_cap": 600_000,
                "provident_loan_cap_increase_per_year": 150_000,
                "provident_upfront_purchase_extract_ratio_new_home": 1.0,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=300_000,
        investments=0,
        provident_fund_balance=200_000,
        social_security_months=60,
        monthly_expense=12_000,
        required_liquidity_months=6,
        family_provident_support_enabled=True,
        family_provident_initial_balance=100_000,
        family_provident_monthly_salary=10_000,
        family_provident_total_rate=0.24,
        members=[
            IncomeMember(
                name="样例成员",
                birth_month="1995-01",
                monthly_salary_gross=20_000,
                annual_bonus=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=4_000_000,
        property_type="新房",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    result = calculate_affordability(household, scenario, rules)
    micro_plan = next(item for item in result.purchase_plan_analyses if item.variant == "微量商贷")

    assert micro_plan.months_to_buy is not None
    assert micro_plan.cash_stress_ok is True
    assert micro_plan.cash_stress_shortfall == 0
    assert micro_plan.family_provident_upfront_extractable > 0


def test_purchase_plan_reports_shortfall_instead_of_negative_cash_balance() -> None:
    rules = RulePackData()
    rules = rules.model_copy(
        update={
            "params": {
                **rules.params,
                "micro_commercial_loan_ratio": 0.05,
                "micro_commercial_loan_ratio_min": 0.02,
                "micro_commercial_loan_ratio_max": 0.12,
                "provident_upfront_purchase_extract_ratio_new_home": 1.0,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=100_000,
        investments=0,
        provident_fund_balance=0,
        social_security_months=12,
        monthly_expense=20_000,
        required_liquidity_months=6,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=8_000,
                annual_bonus=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=4_000_000,
        property_type="新房",
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    result = calculate_affordability(household, scenario, rules)
    micro_plan = next(item for item in result.purchase_plan_analyses if item.variant == "微量商贷")

    assert micro_plan.months_to_buy is None
    assert micro_plan.cash_stress_ok is False
    assert micro_plan.minimum_cash_balance == 0
    assert micro_plan.cash_stress_shortfall > 0


def test_manual_purchase_delay_month_is_respected() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        social_security_months=96,
        monthly_expense=8_000,
        required_liquidity_months=3,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=60_000,
                annual_bonus=0,
            )
        ],
        car_plan=CarPlanData(enabled=False),
        career_shock=CareerShockData(enabled=False),
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=800_000,
        commercial_loan_amount=1_200_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=18,
        renovation_cost=0,
        moving_and_misc_cost=0,
        deed_tax_rate=0,
        broker_fee_rate=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    manual_plan = next(item for item in result.purchase_plan_analyses if item.variant == "手动指定")

    assert manual_plan.months_to_buy is not None
    assert manual_plan.months_to_buy >= 18


def test_purchase_plan_analysis_has_visualization_ready_cash_flow_fields() -> None:
    household = HouseholdData(
        cash_account_balance=2_200_000,
        investments=200_000,
        monthly_expense=20_000,
        required_liquidity_months=6,
        social_security_months=96,
        scheduled_expenses=[],
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=60_000,
                annual_bonus=120_000,
                monthly_special_additional_deduction=0,
            )
        ],
        career_shock=CareerShockData(enabled=False),
    )

    result = calculate_affordability(household, ScenarioData(total_price=3_000_000), RulePackData())

    for plan in result.purchase_plan_analyses:
        assert plan.months_to_buy is None or plan.months_to_buy >= 0
        assert plan.years_to_buy is None or plan.years_to_buy >= 0
        assert plan.cash_after_purchase >= -1_000_000
        assert plan.post_purchase_cash_flow != 0
        assert plan.required_liquidity_reserve == household.monthly_expense * household.required_liquidity_months
        assert plan.upfront_cash_required >= plan.planned_down_payment
        assert 0 <= plan.happiness_score <= 10


def test_renovation_budget_defaults_to_after_purchase_saving() -> None:
    scenario_after = ScenarioData(
        total_price=3_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        moving_and_misc_cost=0,
        renovation_cost=300_000,
    )
    scenario_upfront = scenario_after.model_copy(update={"renovation_funding_mode": "upfront_cash"})
    household = HouseholdData(
        cash_account_balance=1_500_000,
        investments=0,
        monthly_expense=10_000,
        required_liquidity_months=3,
    )

    after_result = calculate_affordability(household, scenario_after, RulePackData())
    upfront_result = calculate_affordability(household, scenario_upfront, RulePackData())
    after_plan = {item.variant: item for item in after_result.purchase_plan_analyses}["较多商贷"]
    upfront_plan = {item.variant: item for item in upfront_result.purchase_plan_analyses}["较多商贷"]

    assert scenario_after.renovation_funding_mode == "after_purchase_saving"
    assert after_plan.renovation_included_in_upfront_cash is False
    assert after_plan.upfront_cash_required + scenario_after.renovation_cost == pytest.approx(
        upfront_plan.upfront_cash_required
    )
    assert after_plan.months_to_renovation is None or after_plan.months_to_renovation >= 0
    assert upfront_plan.renovation_included_in_upfront_cash is True
    assert upfront_plan.months_to_renovation == 0


def test_purchase_plan_treats_provident_extract_as_post_transaction_cash_by_default() -> None:
    household = HouseholdData(
        cash_account_balance=900_000,
        investments=0,
        provident_fund_balance=300_000,
        monthly_expense=12_000,
        required_liquidity_months=6,
        social_security_months=120,
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["较多商贷"]

    assert plan.provident_upfront_extractable == 0
    assert plan.required_cash_after_pf_extract == plan.upfront_cash_required
    assert plan.provident_post_transaction_extractable > 0
    assert plan.cash_after_purchase == pytest.approx(
        plan.cash_after_transaction + plan.provident_post_transaction_extractable
    )
    assert plan.monthly_post_purchase_pf_withdrawal == 0
    assert plan.post_purchase_cash_flow_with_pf_withdrawal == pytest.approx(
        plan.post_purchase_cash_flow
    )


def test_purchase_month_cash_balance_matches_monthly_cash_delta() -> None:
    household = HouseholdData(
        cash_account_balance=600_000,
        investments=100_000,
        monthly_expense=8_000,
        monthly_debt_payment=2_000,
        required_liquidity_months=3,
        social_security_months=120,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=30_000,
                annual_bonus=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
            )
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=400_000,
        commercial_loan_amount=1_600_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=2,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        annual_investment_return=0,
    )

    result = calculate_affordability(household, scenario, _zero_contribution_rule())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["手动指定"]
    rows = [item for item in result.monthly_cashflow_visualization if item.plan_variant == plan.variant]
    purchase_row = next(item for item in rows if item.month == plan.months_to_buy)
    previous_row = next(item for item in rows if item.month == (plan.months_to_buy or 0) - 1)

    assert plan.months_to_buy == 2
    assert purchase_row.transaction_cash_in == pytest.approx(purchase_row.investment_sell_proceeds)
    assert purchase_row.cash_balance == pytest.approx(
        previous_row.cash_balance + purchase_row.monthly_cash_delta
    )


def test_auto_purchase_investment_withdrawal_preserves_unneeded_investments() -> None:
    household = HouseholdData(
        cash_account_balance=250_000,
        investments=500_000,
        monthly_expense=10_000,
        required_liquidity_months=3,
        social_security_months=120,
        members=[
            IncomeMember(
                name="sample member",
                monthly_salary_gross=25_000,
                annual_bonus=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
            )
        ],
    )
    scenario = ScenarioData(
        total_price=1_000_000,
        down_payment_amount=300_000,
        commercial_loan_amount=700_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=1,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        annual_investment_return=0,
        investment_withdrawal_mode="auto",
    )

    result = calculate_affordability(household, scenario, _zero_contribution_rule())
    plan = result.purchase_plan_analyses[0]
    purchase_row = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == plan.months_to_buy
    )

    assert plan.investment_sell_gross_at_purchase > 0
    assert plan.investment_sell_gross_at_purchase < plan.investment_balance_before_purchase
    assert plan.investment_balance_after_purchase > 0
    assert purchase_row.investment_sell_proceeds == pytest.approx(plan.investment_sell_proceeds_at_purchase)
    assert purchase_row.investment_balance == pytest.approx(plan.investment_balance_after_purchase)


def test_purchase_planning_window_start_delays_all_purchase_strategies() -> None:
    today = date.today()
    next_year_month = f"{today.year + 1:04d}-{today.month:02d}"
    household = HouseholdData(
        cash_account_balance=1_000_000,
        investments=0,
        monthly_expense=8_000,
        social_security_months=120,
        members=[
            IncomeMember(
                name="sample member",
                monthly_salary_gross=30_000,
                annual_bonus=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
            )
        ],
    )
    scenario = ScenarioData(
        total_price=1_000_000,
        down_payment_amount=300_000,
        commercial_loan_amount=700_000,
        provident_loan_amount=0,
        planning_window_start_month=next_year_month,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        annual_investment_return=0,
    )

    result = calculate_affordability(household, scenario, _zero_contribution_rule())
    reachable = [item for item in result.purchase_plan_analyses if item.months_to_buy is not None]

    assert reachable
    assert min(item.months_to_buy or 0 for item in reachable) >= 12


def test_manual_purchase_investment_withdrawal_respects_target_reserve() -> None:
    household = HouseholdData(
        cash_account_balance=250_000,
        investments=500_000,
        monthly_expense=10_000,
        required_liquidity_months=3,
        social_security_months=120,
        members=[
            IncomeMember(
                name="sample member",
                monthly_salary_gross=35_000,
                annual_bonus=0,
                housing_fund_personal_rate=0,
                housing_fund_employer_rate=0,
            )
        ],
    )
    scenario = ScenarioData(
        total_price=1_000_000,
        down_payment_amount=300_000,
        commercial_loan_amount=700_000,
        provident_loan_amount=0,
        manual_purchase_delay_months=1,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        annual_investment_return=0,
        investment_withdrawal_mode="manual_reserve",
        investment_min_balance_after_purchase=480_000,
    )

    result = calculate_affordability(household, scenario, _zero_contribution_rule())
    plan = result.purchase_plan_analyses[0]

    assert plan.cash_stress_ok
    assert plan.investment_balance_after_purchase >= 480_000
    assert plan.investment_sell_gross_at_purchase <= 20_000


def test_auto_strategy_can_select_semiannual_loan_offset_for_material_principal_effect() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_municipal_monthly_repayment_withdrawal_supported": False,
        }
    )
    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    monthly_pf_deposit = sum(
        item.monthly_personal_housing_fund + item.monthly_employer_housing_fund
        for item in result.tax_summaries
    )

    assert monthly_pf_deposit > 0
    assert plan.monthly_post_purchase_pf_withdrawal > 0
    assert plan.monthly_post_purchase_pf_withdrawal < plan.provident_monthly_payment
    assert plan.post_purchase_cash_flow_with_pf_withdrawal == pytest.approx(
        plan.post_purchase_cash_flow + plan.monthly_post_purchase_pf_withdrawal
    )
    assert "loan_offset" in plan.post_purchase_pf_strategy


def test_semiannual_loan_offset_fails_when_available_balance_below_agreed_payment() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_balance_annual_interest_rate": 0,
            "provident_loan_offset_retained_balance": 0,
        }
    )
    monthly_equivalent = _semiannual_loan_offset_monthly_equivalent(
        purchase_month=0,
        starting_pf_balance=0,
        monthly_pf_deposit=100,
        provident_monthly_payment=2_000,
        rules=rules,
        horizon_months=6,
        as_of=date(2026, 7, 1),
    )

    assert monthly_equivalent == 0


def test_semiannual_loan_offset_uses_available_balance_after_policy_threshold() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_balance_annual_interest_rate": 0,
            "provident_loan_offset_retained_balance": 0,
        }
    )
    monthly_equivalent = _semiannual_loan_offset_monthly_equivalent(
        purchase_month=0,
        starting_pf_balance=0,
        monthly_pf_deposit=1_000,
        provident_monthly_payment=2_000,
        rules=rules,
        horizon_months=6,
        as_of=date(2026, 7, 1),
    )

    assert monthly_equivalent == pytest.approx(2_000 / 6)


def test_semiannual_provident_offset_does_not_replace_monthly_card_payment() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_post_purchase_strategy_mode": "loan_offset",
            "provident_loan_offset_retained_balance": 0,
        }
    )
    household = HouseholdData(
        cash_account_balance=2_800_000,
        investments=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=120,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        property_type="二手房",
        commercial_loan_amount=150_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["微量商贷"]
    offset_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month > (plan.months_to_buy or 0) and row.loan_offset_payment > 0
    )
    loan_row = next(
        row
        for row in result.loan_visualization
        if row.plan_variant == plan.variant and row.month == offset_row.month
    )
    cashflow_row = next(
        row
        for row in result.monthly_cashflow_visualization
        if row.plan_variant == plan.variant and row.month == offset_row.month
    )

    assert plan.commercial_loan_amount > 0
    assert plan.provident_loan_amount > 0
    assert offset_row.loan_offset_payment >= plan.provident_monthly_payment
    assert loan_row.provident_offset_payment == pytest.approx(offset_row.loan_offset_payment)
    assert loan_row.provident_principal_offset_payment == pytest.approx(offset_row.loan_offset_payment)
    assert loan_row.provident_monthly_withdrawal_payment == 0
    assert loan_row.provident_monthly_payment_relief == 0
    assert loan_row.cash_monthly_payment == pytest.approx(loan_row.total_monthly_payment)
    assert cashflow_row.house_payment == pytest.approx(loan_row.home_monthly_payment)
    assert cashflow_row.provident_house_offset_payment == pytest.approx(offset_row.loan_offset_payment)
    assert cashflow_row.provident_house_payment_relief == 0


def test_purchase_agreed_cashflow_requires_explicit_policy_switch() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_post_purchase_cashflow_enabled": True,
            "provident_monthly_withdrawal_after_purchase_enabled": True,
            "provident_post_purchase_strategy_mode": "manual",
            "provident_post_purchase_withdrawal_mode": "purchase_agreed",
        }
    )
    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    monthly_pf_deposit = sum(
        item.monthly_personal_housing_fund + item.monthly_employer_housing_fund
        for item in result.tax_summaries
    )

    assert monthly_pf_deposit > 0
    assert plan.monthly_post_purchase_pf_withdrawal == pytest.approx(monthly_pf_deposit)
    assert plan.monthly_post_purchase_pf_withdrawal > plan.total_monthly_payment
    assert plan.post_purchase_cash_flow_with_pf_withdrawal == pytest.approx(
        plan.post_purchase_cash_flow + plan.monthly_post_purchase_pf_withdrawal
    )
    assert "购房约定提取" in "；".join(plan.provident_extraction_notes)


def test_loan_offset_cash_relief_uses_semiannual_payment_cap() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_post_purchase_cashflow_enabled": True,
            "provident_monthly_withdrawal_after_purchase_enabled": True,
            "provident_post_purchase_strategy_mode": "manual",
            "provident_post_purchase_withdrawal_mode": "semiannual_principal_offset",
        }
    )
    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]

    assert plan.monthly_post_purchase_pf_withdrawal == pytest.approx(round(plan.provident_monthly_payment / 6, 2))
    assert plan.monthly_post_purchase_pf_withdrawal < plan.provident_monthly_payment
    assert "半年度冲本金" in "；".join(plan.provident_extraction_notes)


def test_monthly_repayment_withdrawal_offsets_provident_payment_every_month() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        provident_account_repayment_strategy="monthly_repayment_withdrawal",
    )
    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    first_after_purchase = (plan.months_to_buy or 0) + 1
    provident_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month == first_after_purchase
    )
    loan_row = next(
        row
        for row in result.loan_visualization
        if row.plan_variant == plan.variant and row.month == first_after_purchase
    )

    assert plan.post_purchase_pf_strategy == "monthly_repayment_withdrawal"
    assert provident_row.monthly_repayment_withdrawal == pytest.approx(
        min(plan.provident_monthly_payment, provident_row.total_deposit)
    )
    assert provident_row.loan_offset_payment == 0
    assert loan_row.provident_monthly_withdrawal_payment == pytest.approx(provident_row.monthly_repayment_withdrawal)
    assert loan_row.provident_principal_offset_payment == 0
    assert loan_row.provident_monthly_payment_relief == pytest.approx(provident_row.monthly_repayment_withdrawal)
    assert loan_row.provident_loan_balance > 0


def test_manual_provident_strategy_switches_from_monthly_withdrawal_to_semiannual_offset() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=80_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        provident_account_repayment_strategy="monthly_repayment_withdrawal",
        provident_account_repayment_switch_enabled=True,
        provident_account_repayment_switch_after_month=2,
        provident_account_repayment_switch_to_strategy="semiannual_principal_offset",
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    purchase_month = plan.months_to_buy or 0
    monthly_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month == purchase_month + 1
    )
    offset_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month > purchase_month + 2 and row.loan_offset_payment > 0
    )
    switch_event = next(
        event
        for event in result.plan_events
        if event.plan_variant == plan.variant and event.category == "provident" and "切换" in event.title
    )

    assert plan.post_purchase_pf_strategy == "monthly_then_semiannual_offset:2"
    assert monthly_row.monthly_repayment_withdrawal > 0
    assert monthly_row.loan_offset_payment == 0
    assert offset_row.loan_offset_payment > 0
    assert offset_row.monthly_repayment_withdrawal == 0
    assert switch_event.month == purchase_month + 3
    assert "两种模式互斥" in switch_event.detail


def test_manual_provident_strategy_switches_from_semiannual_offset_to_monthly_withdrawal() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=80_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        provident_account_repayment_strategy="semiannual_principal_offset",
        provident_account_repayment_switch_enabled=True,
        provident_account_repayment_switch_after_month=2,
        provident_account_repayment_switch_to_strategy="monthly_repayment_withdrawal",
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    purchase_month = plan.months_to_buy or 0
    switched_month_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month == purchase_month + 3
    )
    switch_event = next(
        event
        for event in result.plan_events
        if event.plan_variant == plan.variant and event.category == "provident" and "切换" in event.title
    )

    assert plan.post_purchase_pf_strategy == "semiannual_offset_then_monthly:2"
    assert switched_month_row.monthly_repayment_withdrawal > 0
    assert switched_month_row.loan_offset_payment == 0
    assert switch_event.month == purchase_month + 3
    assert "两种模式互斥" in switch_event.detail


def test_national_provident_member_uses_monthly_repayment_default_strategy() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_municipal_monthly_repayment_withdrawal_supported": False,
            "provident_municipal_semiannual_principal_offset_supported": True,
            "provident_national_monthly_direct_offset_supported": True,
        }
    )
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        monthly_expense=8_000,
        social_security_months=180,
        borrower_member_index=0,
        members=[
            IncomeMember(
                name="国管成员",
                monthly_salary_gross=80_000,
                annual_bonus=0,
                income_stages=[
                    IncomeStageData(
                        name="国管工作阶段",
                        start_date="2026-07-01",
                        provident_account_management_center="national",
                        monthly_salary_gross=80_000,
                        annual_bonus=0,
                    )
                ],
            )
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        provident_account_repayment_strategy="auto",
    )

    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    first_after_purchase = (plan.months_to_buy or 0) + 1
    provident_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month == first_after_purchase
    )

    assert plan.post_purchase_pf_strategy == "monthly_repayment_withdrawal_auto"
    assert provident_row.monthly_repayment_withdrawal > 0
    assert provident_row.loan_offset_payment == 0


def test_provident_repayment_support_is_exposed_by_policy_interface() -> None:
    from app.policies import get_policy

    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_balance_annual_interest_rate": 0.012,
            "provident_loan_offset_retained_balance": 88,
            "provident_upfront_purchase_extract_ratio_new_home": 0.75,
            "provident_upfront_purchase_extract_ratio_second_hand": 0.25,
            "provident_post_transaction_extract_ratio": 0.6,
            "provident_municipal_monthly_repayment_withdrawal_supported": False,
            "provident_municipal_semiannual_principal_offset_supported": True,
            "provident_national_monthly_direct_offset_supported": False,
            "provident_national_semiannual_principal_offset_supported": True,
        }
    )
    policy = get_policy(rules)

    assert policy.provident_account_balance_annual_interest_rate() == pytest.approx(0.012)
    assert policy.provident_loan_offset_retained_balance() == pytest.approx(88)
    assert policy.provident_upfront_purchase_extract_ratio(ScenarioData(property_type="新房")) == pytest.approx(0.75)
    assert policy.provident_upfront_purchase_extract_ratio(ScenarioData(property_type="二手房")) == pytest.approx(0.25)
    assert policy.provident_post_transaction_extract_ratio(ScenarioData()) == pytest.approx(0.6)
    assert policy.provident_post_purchase_policy().cashflow_enabled is False
    assert policy.provident_post_purchase_policy().strategy_mode == "auto"
    assert policy.provident_monthly_repayment_withdrawal_supported("beijing_municipal") is False
    assert policy.provident_semiannual_principal_offset_supported("beijing_municipal") is True
    assert policy.provident_monthly_repayment_withdrawal_supported("national") is False
    assert policy.provident_semiannual_principal_offset_supported("national") is True
    assert calculator_module._policy_default_pf_account_strategy(rules) == "semiannual_principal_offset"


def test_provident_center_uses_income_stage_at_purchase_month() -> None:
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_municipal_monthly_repayment_withdrawal_supported": False,
            "provident_municipal_semiannual_principal_offset_supported": True,
            "provident_national_monthly_direct_offset_supported": True,
        }
    )
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        monthly_expense=8_000,
        social_security_months=180,
        borrower_member_index=0,
        members=[
            IncomeMember(
                name="阶段切换成员",
                monthly_salary_gross=80_000,
                annual_bonus=0,
                income_stages=[
                    IncomeStageData(
                        name="市管阶段",
                        start_date="2026-07-01",
                        end_date="2026-12-31",
                        provident_account_management_center="beijing_municipal",
                        monthly_salary_gross=80_000,
                        annual_bonus=0,
                    ),
                    IncomeStageData(
                        name="国管阶段",
                        start_date="2027-01-01",
                        provident_account_management_center="national",
                        monthly_salary_gross=80_000,
                        annual_bonus=0,
                    ),
                ],
            )
        ],
    )
    assert (
        calculator_module._policy_default_pf_account_strategy(rules, household, months_from_now=0)
        == "semiannual_principal_offset"
    )
    assert (
        calculator_module._policy_default_pf_account_strategy(rules, household, months_from_now=8)
        == "monthly_repayment_withdrawal"
    )


def test_auto_provident_strategy_can_switch_from_monthly_withdrawal_to_semiannual_offset() -> None:
    household = HouseholdData(
        cash_account_balance=900_000,
        monthly_expense=18_000,
        members=[
                IncomeMember(
                    name="样例成员A",
                    provident_fund_balance=120_000,
                    personal_pension_account_enabled=False,
                    personal_pension_contribution_mode="none",
                    income_stages=[
                    IncomeStageData(
                        name="当前收入",
                        monthly_salary_gross=28_000,
                        monthly_housing_fund=3_360,
                        housing_fund_personal_rate=0.12,
                        housing_fund_employer_rate=0.12,
                    )
                ],
            )
        ],
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        provident_loan_amount=1_000_000,
        commercial_loan_amount=500_000,
        loan_years=25,
        provident_account_repayment_strategy="auto",
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_municipal_monthly_repayment_withdrawal_supported": True,
            "provident_municipal_semiannual_principal_offset_supported": True,
            "provident_post_purchase_strategy_mode": "auto",
            "provident_loan_offset_retained_balance": 10,
        }
    )

    result = calculate_affordability(household, scenario, rules)
    plan = next(
        item
        for item in result.purchase_plan_analyses
        if item.months_to_buy is not None and item.post_purchase_pf_strategy.startswith("monthly_then_semiannual_offset_auto")
    )
    purchase_month = plan.months_to_buy or 0
    first_month = purchase_month + 1
    monthly_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month == first_month
    )
    later_offset_row = next(
        row
        for row in result.provident_visualization
        if row.plan_variant == plan.variant and row.month > purchase_month + 12 and row.loan_offset_payment > plan.provident_monthly_payment
    )
    switch_event = next(
        event
        for event in result.plan_events
        if event.plan_variant == plan.variant and event.category == "provident" and "切换" in event.title
    )

    assert plan.post_purchase_pf_strategy_label.startswith("自动先按月约定提取")
    assert monthly_row.monthly_repayment_withdrawal == pytest.approx(
        min(plan.provident_monthly_payment, monthly_row.total_deposit)
    )
    assert monthly_row.loan_offset_payment == 0
    assert later_offset_row.loan_offset_payment > plan.provident_monthly_payment
    assert later_offset_row.monthly_repayment_withdrawal == 0
    assert switch_event.month == purchase_month + 13
    assert "两种模式互斥" in switch_event.detail
    assert any("阶段切换" in note and "两种模式互斥" in note for note in plan.provident_extraction_notes)


def test_beijing_loan_offset_is_semiannual_not_monthly() -> None:
    assert _is_beijing_pf_offset_month(0, as_of=date(2026, 7, 1))
    assert not _is_beijing_pf_offset_month(1, as_of=date(2026, 7, 1))
    assert _is_beijing_pf_offset_month(6, as_of=date(2026, 7, 1))

    monthly_equivalent = _semiannual_loan_offset_monthly_equivalent(
        purchase_month=0,
        starting_pf_balance=0,
        monthly_pf_deposit=10_000,
        provident_monthly_payment=6_000,
        rules=RulePackData(),
        horizon_months=12,
        as_of=date(2026, 7, 1),
    )

    assert monthly_equivalent == pytest.approx(1_000)


def test_provident_visualization_records_account_loan_offset_outflow() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=120_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_post_purchase_strategy_mode": "loan_offset",
        }
    )

    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    rows = [item for item in result.provident_visualization if item.plan_variant == plan.variant]
    offset_rows = [item for item in rows if item.loan_offset_payment > 0]

    assert rows
    assert offset_rows
    assert any(item.loan_offset_payment > plan.provident_monthly_payment for item in offset_rows)
    assert offset_rows[0].total_outflow >= offset_rows[0].loan_offset_payment
    assert offset_rows[0].balance_end < offset_rows[0].balance_start + offset_rows[0].total_inflow


def test_provident_visualization_splits_member_accounts() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=999_999,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", provident_fund_balance=100_000, monthly_salary_gross=10_000, annual_bonus=0),
            IncomeMember(name="样例成员B", provident_fund_balance=20_000, monthly_salary_gross=20_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_balance_annual_interest_rate": 0.012,
            "provident_upfront_purchase_extract_ratio": 0,
            "provident_upfront_purchase_extract_ratio_new_home": 0,
            "provident_upfront_purchase_extract_ratio_second_hand": 0,
            "provident_post_transaction_extract_ratio": 0,
            "provident_post_purchase_strategy_mode": "keep_in_account",
        }
    )

    result = calculate_affordability(household, scenario, rules)
    plan = result.purchase_plan_analyses[0]
    first_row = next(item for item in result.provident_visualization if item.plan_variant == plan.variant and item.month == 0)
    second_row = next(item for item in result.provident_visualization if item.plan_variant == plan.variant and item.month == 1)

    assert [item.member_name for item in first_row.member_accounts] == ["样例成员A", "样例成员B"]
    assert [item.balance_end for item in first_row.member_accounts] == pytest.approx([100_000, 20_000])
    assert first_row.balance_end == pytest.approx(120_000)
    assert first_row.balance_end != pytest.approx(household.provident_fund_balance)
    assert sum(item.balance_end for item in second_row.member_accounts) == pytest.approx(second_row.balance_end)
    assert second_row.interest == pytest.approx(120.0)


def test_provident_account_closes_and_transfers_to_cash_at_retirement() -> None:
    current_month = date(date.today().year, date.today().month, 1)
    retirement_month = calculator_module._add_months(current_month, 2)
    birth_month = f"{retirement_month.year - 63}-{retirement_month.month:02d}"
    household = HouseholdData(
        cash_account_balance=500_000,
        investments=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(
                name="即将退休成员",
                birth_month=birth_month,
                provident_fund_balance=100_000,
                monthly_salary_gross=20_000,
                annual_bonus=0,
            ),
        ],
    )
    scenario = ScenarioData(
        total_price=5_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_balance_annual_interest_rate": 0.012,
            "provident_upfront_purchase_extract_ratio": 0,
            "provident_upfront_purchase_extract_ratio_new_home": 0,
            "provident_upfront_purchase_extract_ratio_second_hand": 0,
            "provident_post_transaction_extract_ratio": 0,
            "provident_post_purchase_strategy_mode": "keep_in_account",
        }
    )

    result = calculate_affordability(household, scenario, rules)
    plan = result.purchase_plan_analyses[0]
    rows = [item for item in result.provident_visualization if item.plan_variant == plan.variant]
    before_retirement = next(item for item in rows if item.month == 1)
    retirement_row = next(item for item in rows if item.month == 2)
    after_retirement = next(item for item in rows if item.month == 3)
    member_retirement_row = retirement_row.member_accounts[0]
    cashflow_row = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == 2
    )

    assert before_retirement.total_deposit > 0
    assert retirement_row.total_deposit == 0
    assert retirement_row.retirement_withdrawal == pytest.approx(member_retirement_row.balance_start)
    assert member_retirement_row.account_closed_by_retirement is True
    assert retirement_row.balance_end == 0
    assert after_retirement.total_deposit == 0
    assert after_retirement.balance_end == 0
    assert cashflow_row.provident_withdrawal == pytest.approx(retirement_row.retirement_withdrawal)
    assert any(
        event.plan_variant == plan.variant
        and event.month == 2
        and event.category == "provident"
        and "公积金退休销户" in event.title
        and event.amount == pytest.approx(retirement_row.retirement_withdrawal)
        for event in result.plan_events
    )


def test_timeline_and_account_curves_extend_past_retirement() -> None:
    current_month = date(date.today().year, date.today().month, 1)
    retirement_month = calculator_module._add_months(current_month, 2)
    birth_month = f"{retirement_month.year - 55}-{retirement_month.month:02d}"
    household = HouseholdData(
        cash_account_balance=800_000,
        investments=50_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        career_shock=CareerShockData(
            member_settings=[
                CareerShockMemberSetting(
                    member_name="样例成员",
                    enabled=False,
                    retirement_age=50,
                    pension_monthly=4_000,
                    auto_pension_monthly=False,
                )
            ],
        ),
        members=[
                IncomeMember(
                    name="样例成员",
                    birth_month=birth_month,
                    retirement_category="female_50",
                    provident_fund_balance=80_000,
                    monthly_salary_gross=20_000,
                annual_bonus=0,
            ),
        ],
    )
    scenario = ScenarioData(
        total_price=3_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = result.purchase_plan_analyses[0]
    cashflow_months = [
        item.month
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant
    ]
    events = [item for item in result.plan_events if item.plan_variant == plan.variant]

    assert max(cashflow_months) >= 122
    assert any(event.month == 2 and "退休-养老金" in event.title and "养老金" in event.detail for event in events)
    assert any(event.month >= 120 and event.title == "退休后长期观察窗口" for event in events)
    retirement_cashflow = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == 2
    )
    assert retirement_cashflow.pension_income == pytest.approx(4_000)
    assert retirement_cashflow.cash_income >= 4_000


def test_pension_income_starts_at_retirement_without_career_shock_enabled() -> None:
    current_month = date(date.today().year, date.today().month, 1)
    retirement_month = calculator_module._add_months(current_month, 2)
    birth_month = f"{retirement_month.year - 63}-{retirement_month.month:02d}"
    rules = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999_999,
                "pension_reference_average_salary": 10_000,
                "pension_average_salary_growth_rate": 0,
                "pension_default_paid_years": 15,
                "pension_personal_account_annual_return": 0,
                "pension_replacement_rate_floor": 0.2,
                "pension_replacement_rate_ceiling": 0.65,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=300_000,
        monthly_expense=3_000,
        members=[
            IncomeMember(
                name="样例成员A",
                birth_month=birth_month,
                retirement_category="male_60",
                social_security_months=180,
                income_stages=[
                    IncomeStageData(
                        name="工资阶段",
                        start_date="2026-07-01",
                        monthly_salary_gross=12_000,
                    )
                ],
            )
        ],
    )
    scenario = ScenarioData(total_price=100_000, deed_tax_rate=0, broker_fee_rate=0, renovation_cost=0, moving_and_misc_cost=0)

    result = calculate_affordability(household, scenario, rules)
    plan = result.purchase_plan_analyses[0]
    retirement_row = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == 2
    )
    tax_row = next(item for item in result.tax_monthly_points if item.month == 2)

    assert retirement_row.pension_income > 0
    assert retirement_row.cash_income >= retirement_row.pension_income
    assert tax_row.pension_income == pytest.approx(retirement_row.pension_income)
    assert tax_row.member_points[0].stage_kind == "pension"


def test_member_retirement_category_follows_sex_defaults() -> None:
    male = IncomeMember(name="样例成员A", sex="male", retirement_category="female_50")
    female = IncomeMember(name="样例成员B", sex="female", retirement_category="male_60")
    unspecified = IncomeMember(name="样例成员C", sex="unspecified", retirement_category="female_50")

    assert male.retirement_category == "male_60"
    assert female.retirement_category == "female_55"
    assert unspecified.retirement_category == "female_50"


def test_provident_loan_offset_uses_borrower_account_before_other_members() -> None:
    household = HouseholdData(
        cash_account_balance=2_000_000,
        investments=0,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        borrower_member_index=1,
        members=[
            IncomeMember(name="非主借款人", provident_fund_balance=500_000, monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="主借款人", provident_fund_balance=1_000_000, monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=1_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_post_purchase_strategy_mode": "loan_offset",
            "provident_loan_offset_retained_balance": 0,
            "provident_upfront_purchase_extract_ratio": 0,
            "provident_upfront_purchase_extract_ratio_new_home": 0,
            "provident_upfront_purchase_extract_ratio_second_hand": 0,
            "provident_post_transaction_extract_ratio": 0,
        }
    )

    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    offset_row = next(
        item
        for item in result.provident_visualization
        if item.plan_variant == plan.variant and item.loan_offset_payment > 0
    )
    member_offsets = {item.member_name: item.loan_offset_payment for item in offset_row.member_accounts}

    assert offset_row.loan_offset_payment > 0
    assert member_offsets["主借款人"] == pytest.approx(offset_row.loan_offset_payment)
    assert member_offsets["非主借款人"] == 0


def test_provident_loan_offset_uses_other_member_only_after_borrower_available_balance() -> None:
    account_rows = [
        {
            "member_index": 0,
            "member_name": "主借款人",
            "balance_end": 15_010.0,
            "loan_offset_payment": 0.0,
        },
        {
            "member_index": 1,
            "member_name": "共同借款人",
            "balance_end": 20_010.0,
            "loan_offset_payment": 0.0,
        },
    ]
    target = calculator_module._beijing_pf_loan_offset_target(
        available_balance=35_000,
        agreed_payment=20_000,
        remaining_loan_balance=100_000,
    )

    actual = calculator_module._apply_provident_member_outflow(
        account_rows,
        target,
        "loan_offset_payment",
        retained_balance=10,
        priority_member_index=0,
    )

    assert actual == pytest.approx(35_000)
    assert account_rows[0]["loan_offset_payment"] == pytest.approx(15_000)
    assert account_rows[0]["balance_end"] == pytest.approx(10)
    assert account_rows[1]["loan_offset_payment"] == pytest.approx(20_000)
    assert account_rows[1]["balance_end"] == pytest.approx(10)


def test_cashflow_and_loan_visualization_apply_provident_offset_before_cash_payment() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=120_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=80_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=80_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "provident_post_purchase_strategy_mode": "loan_offset",
        }
    )

    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]
    offset_point = next(
        item
        for item in result.provident_visualization
        if item.plan_variant == plan.variant and item.loan_offset_payment > 0
    )
    loan_point = next(
        item
        for item in result.loan_visualization
        if item.plan_variant == plan.variant and item.month == offset_point.month
    )
    cashflow_point = next(
        item
        for item in result.monthly_cashflow_visualization
        if item.plan_variant == plan.variant and item.month == offset_point.month
    )

    assert loan_point.provident_offset_payment == pytest.approx(offset_point.loan_offset_payment)
    assert loan_point.provident_principal_offset_payment == pytest.approx(offset_point.loan_offset_payment)
    assert loan_point.provident_monthly_withdrawal_payment == 0
    assert loan_point.provident_monthly_payment_relief == 0
    assert loan_point.cash_monthly_payment == pytest.approx(loan_point.total_monthly_payment)
    assert cashflow_point.provident_house_offset_payment == pytest.approx(offset_point.loan_offset_payment)
    assert cashflow_point.provident_house_payment_relief == 0
    assert cashflow_point.house_payment == pytest.approx(cashflow_point.house_contract_payment)


def test_purchase_plan_explains_repayment_method_interest_tradeoff() -> None:
    household = HouseholdData(
        cash_account_balance=2_500_000,
        investments=0,
        provident_fund_balance=100_000,
        monthly_expense=8_000,
        required_liquidity_months=3,
        social_security_months=180,
        members=[
            IncomeMember(name="样例成员A", monthly_salary_gross=50_000, annual_bonus=0),
            IncomeMember(name="样例成员B", monthly_salary_gross=50_000, annual_bonus=0),
        ],
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
        provident_repayment_method="equal_installment",
    )

    result = calculate_affordability(household, scenario, RulePackData())
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]

    assert plan.provident_interest_saving_if_equal_principal > 0
    assert plan.provident_equal_principal_first_payment > plan.provident_equal_installment_payment
    assert plan.provident_repayment_method == "equal_principal"
    assert "等额本金" in plan.provident_repayment_advice


def test_existing_home_family_does_not_continue_rent_withdrawal_before_purchase() -> None:
    scenario = ScenarioData(total_price=3_000_000, renovation_cost=0, moving_and_misc_cost=0)
    household_with_home = HouseholdData(
        existing_home_count=1,
        monthly_rent_from_housing_fund=20_000,
        cash_account_balance=800_000,
        investments=0,
        provident_fund_balance=300_000,
        provident_fund_monthly_deposit=8_000,
        monthly_expense=8_000,
        social_security_months=96,
        members=[
            IncomeMember(
                name="样例成员",
                monthly_salary_gross=50_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
            )
        ],
    )
    household_without_home = household_with_home.model_copy(update={"existing_home_count": 0})

    with_home = calculate_affordability(household_with_home, scenario, RulePackData())
    without_home = calculate_affordability(household_without_home, scenario, RulePackData())
    with_home_plan = {item.variant: item for item in with_home.purchase_plan_analyses}["较多商贷"]
    without_home_plan = {item.variant: item for item in without_home.purchase_plan_analyses}["较多商贷"]

    assert with_home_plan.provident_post_transaction_extractable > without_home_plan.provident_post_transaction_extractable


def test_rent_provident_withdrawal_is_quarterly_before_purchase() -> None:
    household = HouseholdData(monthly_rent_from_housing_fund=6_000, existing_home_count=0)
    household_with_home = household.model_copy(update={"existing_home_count": 1})

    assert _quarterly_rent_withdrawal_before_purchase_at(household, 1) == 0
    assert _quarterly_rent_withdrawal_before_purchase_at(household, 2) == 0
    assert _quarterly_rent_withdrawal_before_purchase_at(household, 3) == 18_000
    assert _quarterly_rent_withdrawal_before_purchase_at(household, 6) == 18_000
    assert _quarterly_rent_withdrawal_before_purchase_at(household_with_home, 3) == 0


def test_daily_and_rent_expense_stages_support_cash_and_provident_rent() -> None:
    household = HouseholdData(
        monthly_expense=8_000,
        monthly_debt_payment=1_000,
        daily_expense_stages=[
            DailyExpenseStageData(
                name="当前日常支出",
                start_month="2026-07",
                end_month="2026-12",
                base_living_expense=8_000,
            ),
            DailyExpenseStageData(
                name="新日常支出",
                start_month="2027-01",
                base_living_expense=9_000,
            ),
        ],
        rent_expense_stages=[
            RentExpenseStageData(
                name="现金租房阶段",
                start_month="2026-07",
                end_month="2026-12",
                rent_amount=4_000,
                broker_fee_months=1,
                service_fee_first_year_rate=0.09,
                service_fee_later_year_rate=0.06,
                rent_payment_mode="cash",
            ),
            RentExpenseStageData(
                name="公积金租房阶段",
                start_month="2027-01",
                rent_amount=5_000,
                rent_payment_mode="provident",
                rent_payment_frequency="quarterly",
            ),
        ],
        scheduled_expenses=[
            ScheduledExpenseData(
                name="其他固定还款",
                monthly_amount=2_000,
                start_month="2027-01",
            )
        ],
    )

    assert monthly_household_expense_at(household, as_of=date(2026, 7, 1)) == 16_360
    assert monthly_household_expense_at(household, as_of=date(2026, 8, 1)) == 12_360
    assert monthly_household_expense_at(household, as_of=date(2027, 1, 1)) == 17_350
    assert calculator_module._regular_debt_payment_at(household, as_of=date(2027, 1, 1)) == 1_000
    assert _quarterly_rent_withdrawal_before_purchase_at(household, 6) == 15_000


def test_rent_service_fee_can_change_after_first_year_and_broker_fee_can_be_manual() -> None:
    household = HouseholdData(
        monthly_expense=8_000,
        rent_expense_stages=[
            RentExpenseStageData(
                name="服务费测试",
                start_month="2026-07",
                rent_amount=5_000,
                broker_fee_amount=3_000,
                service_fee_first_year_rate=0.10,
                service_fee_later_year_rate=0.05,
                rent_payment_mode="cash",
            )
        ],
    )

    assert monthly_household_expense_at(household, as_of=date(2026, 7, 1)) == 16_500
    assert monthly_household_expense_at(household, as_of=date(2026, 8, 1)) == 13_500
    assert monthly_household_expense_at(household, as_of=date(2027, 7, 1)) == 13_250


def test_broker_fee_default_comes_from_policy_interface_and_scenario_can_override() -> None:
    from app.domain.housing import broker_fee_rate

    base_rules = RulePackData()
    rules = base_rules.model_copy(
        update={"params": {**base_rules.params, "default_broker_fee_rate": 0.018}}
    )
    scenario_without_manual_rate = ScenarioData().model_construct(broker_fee_rate=None)
    market_snapshot = MarketSnapshotData(default_broker_fee_rate=0.016)

    assert broker_fee_rate(scenario_without_manual_rate, rules) == pytest.approx(0.018)
    assert broker_fee_rate(ScenarioData(), rules) == pytest.approx(0.018)
    assert broker_fee_rate(scenario_without_manual_rate, rules, market_snapshot) == pytest.approx(0.016)
    assert broker_fee_rate(ScenarioData(), rules, market_snapshot) == pytest.approx(0.016)
    assert broker_fee_rate(ScenarioData(broker_fee_rate=0.01), rules) == pytest.approx(0.01)
    assert broker_fee_rate(ScenarioData(broker_fee_rate=0.01), rules, market_snapshot) == pytest.approx(0.01)


def test_commercial_loan_rate_uses_market_quote_entrypoint() -> None:
    from app.domain.housing import commercial_loan_rate

    market_snapshot = MarketSnapshotData(commercial_loan_rate=0.032)

    assert commercial_loan_rate(ScenarioData(commercial_rate=0.041)) == pytest.approx(0.041)
    assert commercial_loan_rate(ScenarioData(), market_snapshot) == pytest.approx(0.032)
    assert commercial_loan_rate(ScenarioData(commercial_rate=0.041), market_snapshot) == pytest.approx(0.041)
    assert commercial_loan_rate(ScenarioData().model_construct(commercial_rate=None)) == pytest.approx(0.035)
    assert commercial_loan_rate(ScenarioData().model_construct(commercial_rate=None), market_snapshot) == pytest.approx(0.032)
    assert commercial_loan_rate(ScenarioData().model_construct(commercial_rate=0.35)) == pytest.approx(0.2)


def test_market_snapshot_feeds_purchase_strategy_market_assumptions() -> None:
    household = HouseholdData(
        monthly_income=60_000,
        monthly_expense=10_000,
        cash_account_balance=1_200_000,
        investments=100_000,
        social_security_months=96,
        borrower_age=30,
    )
    scenario = ScenarioData(
        total_price=2_000_000,
        down_payment_amount=700_000,
        commercial_loan_amount=800_000,
        provident_loan_amount=500_000,
    )
    market_snapshot = MarketSnapshotData(commercial_loan_rate=0.032, default_broker_fee_rate=0.016)

    result = calculate_affordability(household, scenario, RulePackData(), market_snapshot=market_snapshot)

    assert result.purchase_plan_analyses
    plan = result.purchase_plan_analyses[0]
    assert plan.commercial_rate == pytest.approx(0.032)
    assert plan.broker_fee_rate == pytest.approx(0.016)

    manual_quote = scenario.model_copy(update={"commercial_rate": 0.041, "broker_fee_rate": 0.012})
    manual_result = calculate_affordability(household, manual_quote, RulePackData(), market_snapshot=market_snapshot)
    manual_plan = manual_result.purchase_plan_analyses[0]
    assert manual_plan.commercial_rate == pytest.approx(0.041)
    assert manual_plan.broker_fee_rate == pytest.approx(0.012)


def test_seller_tax_pass_through_default_comes_from_policy_interface_and_scenario_can_override() -> None:
    from app.calculation_context import build_purchase_cash_context
    from app.domain.housing import seller_tax_pass_through_amount

    base_rules = RulePackData()
    rules = base_rules.model_copy(
        update={"params": {**base_rules.params, "seller_tax_pass_through_default_rate": 0.012}}
    )
    scenario_without_manual_rate = ScenarioData(
        total_price=2_000_000,
        seller_tax_pass_through_enabled=True,
        seller_tax_pass_through_rate=0,
        seller_tax_pass_through_amount=0,
    )
    scenario_with_manual_rate = scenario_without_manual_rate.model_copy(
        update={"seller_tax_pass_through_rate": 0.02}
    )
    scenario_with_manual_amount = scenario_without_manual_rate.model_copy(
        update={"seller_tax_pass_through_amount": 18_000}
    )
    market_snapshot = MarketSnapshotData(seller_tax_pass_through_rate=0.015)

    assert seller_tax_pass_through_amount(scenario_without_manual_rate, rules) == pytest.approx(24_000)
    assert seller_tax_pass_through_amount(scenario_without_manual_rate, rules, market_snapshot) == pytest.approx(30_000)
    assert seller_tax_pass_through_amount(scenario_with_manual_rate, rules) == pytest.approx(40_000)
    assert seller_tax_pass_through_amount(scenario_with_manual_rate, rules, market_snapshot) == pytest.approx(40_000)
    assert seller_tax_pass_through_amount(scenario_with_manual_amount, rules) == pytest.approx(18_000)
    assert seller_tax_pass_through_amount(scenario_with_manual_amount, rules, market_snapshot) == pytest.approx(18_000)
    assert seller_tax_pass_through_amount(
        scenario_without_manual_rate.model_copy(update={"seller_tax_pass_through_enabled": False}),
        rules,
        market_snapshot,
    ) == 0
    assert seller_tax_pass_through_amount(
        scenario_without_manual_rate.model_copy(update={"seller_tax_pass_through_enabled": False}),
        rules,
    ) == 0
    purchase_cash_context = build_purchase_cash_context(
        HouseholdData(),
        scenario_without_manual_rate,
        rules,
        min_down_payment_ratio=0.3,
    )
    assert purchase_cash_context.seller_tax_pass_through == pytest.approx(24_000)
    assert purchase_cash_context.taxes_and_fees >= 24_000
    market_purchase_cash_context = build_purchase_cash_context(
        HouseholdData(),
        scenario_without_manual_rate,
        rules,
        min_down_payment_ratio=0.3,
        market_snapshot=market_snapshot,
    )
    assert market_purchase_cash_context.seller_tax_pass_through == pytest.approx(30_000)


def test_purchase_plan_happiness_scores_have_explainable_breakdown() -> None:
    household = HouseholdData(
        cash_account_balance=900_000,
        investments=100_000,
        monthly_expense=15_000,
        social_security_months=96,
    )
    result = calculate_affordability(household, ScenarioData(total_price=3_200_000), RulePackData())
    scores = {item.happiness_score for item in result.purchase_plan_analyses}

    assert len(scores) > 1
    for plan in result.purchase_plan_analyses:
        assert plan.happiness_breakdown
        assert {item.name for item in plan.happiness_breakdown} >= {
            "买房当天现金安全",
            "长期理财连续性",
            "买后月度自由现金流",
            "买车对买房影响",
            "贷款利息与商贷暴露",
            "现金缺口风险",
            "压力测试韧性",
        }
        assert sum(item.weight for item in plan.happiness_breakdown) == pytest.approx(1.0, abs=0.01)
        assert sum(item.weighted_score for item in plan.happiness_breakdown) == pytest.approx(plan.happiness_score, abs=0.05)
        assert all(0 <= item.score <= 10 for item in plan.happiness_breakdown)


def test_purchase_happiness_weights_are_read_from_policy_interface() -> None:
    base_rules = RulePackData()
    rules = base_rules.model_copy(
        update={
            "params": {
                **base_rules.params,
                "purchase_happiness_weights": {
                    "cash_shortfall": 99,
                    "living_quality": 1,
                },
            }
        }
    )

    weights = purchase_happiness_weights(rules, liquidity_priority_score=5)

    assert weights["cash_shortfall"] > 0.9
    assert weights["cash_shortfall"] > weights["living_quality"]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_purchase_happiness_weight_defaults_stay_inside_policy_interface() -> None:
    base_rules = RulePackData()
    zero_rules = base_rules.model_copy(
        update={
            "params": {
                **base_rules.params,
                "purchase_happiness_weights": {
                    key: 0
                    for key in base_rules.params["purchase_happiness_weights"]
                },
            }
        }
    )

    weights = purchase_happiness_weights(zero_rules, liquidity_priority_score=5)

    assert weights
    assert sum(weights.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("child_count", -1),
        ("cash_account_balance", -1),
        ("investments", -1),
        ("required_liquidity_months", 37),
        ("borrower_age", 17),
    ],
)
def test_household_numeric_fields_reject_invalid_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        HouseholdData(**{field: value})


@pytest.mark.parametrize(
    ("model_cls", "kwargs"),
    [
        (IncomeStageData, {"annual_bonus_payout_month": 13}),
        (IncomeStageData, {"monthly_salary_gross": -1}),
        (IncomeMember, {"housing_fund_personal_rate": 0.13}),
        (IncomeMember, {"current_age": 121}),
        (CareerShockMemberSetting, {"layoff_age": 17}),
        (CarPlanData, {"total_months": 0}),
        (CarPlanData, {"later_annual_rate": 0.51}),
        (VehicleFinancingOptionData, {"min_down_payment_ratio": 0.8, "max_down_payment_ratio": 0.2}),
        (PhasedLoanData, {"remaining_months": 0}),
        (PhasedLoanData, {"annual_rate": 0.21}),
        (ScheduledExpenseData, {"monthly_amount": -1}),
        (ScenarioData, {"loan_years": 31}),
        (ScenarioData, {"annual_investment_return": -0.51}),
        (ScenarioData, {"commercial_prepayment_allowed_after_month": 0}),
    ],
)
def test_nested_numeric_fields_reject_unreasonable_values(model_cls, kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


def test_invalid_phased_loan_month_strings_are_marked_for_review_without_payment() -> None:
    loan = PhasedLoanData(
        borrower="样例成员",
        name="月份配置错误贷款",
        principal=10_000,
        interest_start_month="not-a-month",
        interest_only_until="2028-13",
    )

    summary = summarize_phased_loans([loan], as_of=date(2027, 1, 1))[0]

    assert summary.phase == "配置待校验"
    assert summary.current_monthly_payment == 0


def test_extreme_car_prepayment_is_capped_without_negative_interest_or_balance() -> None:
    loan = calculate_car_loan(
        CarPlanData(
            enabled=True,
            total_price=200_000,
            down_payment_ratio=0.10,
            total_months=60,
            interest_free_months=0,
            later_annual_rate=0.08,
            loan_prepayment_enabled=True,
            loan_prepayment_start_month=1,
            loan_prepayment_allowed_after_month=1,
            loan_prepayment_monthly_amount=1_000_000,
        )
    )

    assert loan.loan_principal == pytest.approx(180_000)
    assert loan.actual_payoff_months == 1
    assert loan.total_interest >= 0
    assert loan.interest_saved_by_prepayment >= 0


def test_extreme_negative_monthly_cashflow_keeps_account_balances_non_negative() -> None:
    household = HouseholdData(
        cash_account_balance=0,
        investments=0,
        monthly_expense=20_000,
        monthly_debt_payment=5_000,
        members=[
            IncomeMember(
                name="无收入成员",
                monthly_salary_gross=0,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
            )
        ],
    )
    scenario = ScenarioData(
        total_price=100_000,
        renovation_cost=0,
        moving_and_misc_cost=0,
        annual_investment_return=-0.50,
    )

    result = calculate_affordability(household, scenario, RulePackData())

    assert result.purchase_plan_analyses
    assert result.monthly_cashflow_visualization
    assert any(item.monthly_cash_delta < 0 for item in result.monthly_cashflow_visualization)
    assert all(item.cash_balance >= 0 for item in result.monthly_cashflow_visualization)
    assert all(item.investment_balance >= 0 for item in result.monthly_cashflow_visualization)
    assert all(item.provident_balance >= 0 for item in result.monthly_cashflow_visualization)
    assert all(item.total_loan_balance >= 0 for item in result.monthly_cashflow_visualization)


def test_structured_child_and_housing_deductions_reduce_tax_with_rent_mortgage_exclusive() -> None:
    rule = _zero_contribution_rule()
    base_member = IncomeMember(
        name="样例成员A",
        monthly_salary_gross=30_000,
        annual_bonus=0,
        monthly_special_additional_deduction=0,
    )
    base = HouseholdData(members=[base_member], income_projection_year=2027)
    optimized = base.model_copy(
        update={
            "child_plans": [
                ChildPlanData(
                    name="样例子女",
                    enabled=True,
                    birth_month="2026-01",
                    education_start_month="2032-09",
                    tax_deduction_owner="样例成员A",
                )
            ],
            "special_deductions": [
                SpecialDeductionItemData(
                    deduction_type="housing_rent",
                    name="住房租金",
                    enabled=True,
                    member_name="样例成员A",
                    start_month="2027-01",
                    monthly_amount=1500,
                ),
                SpecialDeductionItemData(
                    deduction_type="mortgage_interest",
                    name="首套房贷利息",
                    enabled=True,
                    member_name="样例成员A",
                    start_month="2027-01",
                    monthly_amount=1000,
                    is_first_home_loan=True,
                ),
            ],
        }
    )

    base_summary = calculate_household_tax_for_year(base, rule, 2027).summaries[0]
    optimized_summary = calculate_household_tax_for_year(optimized, rule, 2027).summaries[0]

    assert optimized_summary.taxable_income == pytest.approx(base_summary.taxable_income - (2000 + 1500) * 12)
    assert optimized_summary.total_tax < base_summary.total_tax


def test_child_tax_strategy_waits_for_tax_page_owner_assignment() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=30_000)],
        child_plans=[
            ChildPlanData(
                name="样例子女",
                enabled=True,
                birth_month="2027-01",
                education_start_month="2033-09",
            )
        ],
    )

    result = calculate_affordability(household, ScenarioData(total_price=2_000_000), rule)
    infant = next(item for item in result.tax_strategy_items if item.deduction_type == "infant_care")

    assert infant.status == "available"
    assert infant.member_name == ""
    assert "税务页指定申报成员" in infant.reason

    assigned = household.model_copy(
        update={
            "child_plans": [
                household.child_plans[0].model_copy(update={"tax_deduction_owner": "样例成员A"})
            ]
        }
    )
    assigned_result = calculate_affordability(assigned, ScenarioData(enabled=False), rule)
    assigned_infant = next(item for item in assigned_result.tax_strategy_items if item.deduction_type == "infant_care")

    assert assigned_infant.status == "auto_enabled"
    assert assigned_infant.member_name == "样例成员A"
    assigned_timeline = [
        item
        for item in assigned_result.tax_strategy_timeline
        if item.deduction_type == "infant_care"
    ]
    assert assigned_timeline
    assert assigned_timeline[0].member_name == "样例成员A"
    assert assigned_timeline[0].category == "deduction_assignment"


def test_rent_stage_generates_auto_tax_strategy_and_deduction() -> None:
    rule = _zero_contribution_rule()
    base_member = IncomeMember(
        name="样例成员A",
        monthly_salary_gross=30_000,
        annual_bonus=0,
        monthly_special_additional_deduction=0,
    )
    base = HouseholdData(members=[base_member], income_projection_year=2027)
    with_rent = base.model_copy(
        update={
            "rent_expense_stages": [
                RentExpenseStageData(
                    name="样例租房阶段",
                    start_month="2027-01",
                    rent_amount=5000,
                    rent_payment_mode="cash",
                )
            ],
        }
    )

    base_summary = calculate_household_tax_for_year(base, rule, 2027).summaries[0]
    rent_summary = calculate_household_tax_for_year(with_rent, rule, 2027).summaries[0]
    result = calculate_affordability(with_rent, ScenarioData(enabled=False), rule)

    assert rent_summary.taxable_income == pytest.approx(base_summary.taxable_income - 1500 * 12)
    assert rent_summary.total_tax < base_summary.total_tax
    rent_strategy = next(item for item in result.tax_strategy_items if item.deduction_type == "housing_rent")
    assert rent_strategy.status == "auto_enabled"
    assert rent_strategy.source == "event"


def test_child_plan_expense_enters_household_monthly_cashflow() -> None:
    household = HouseholdData(
        daily_expense_stages=[DailyExpenseStageData(start_month="2027-01", base_living_expense=10_000)],
        child_plans=[
            ChildPlanData(
                name="样例子女",
                enabled=True,
                birth_month="2027-01",
                education_start_month="2033-09",
                monthly_childcare_cost_before_kindergarten=3000,
                monthly_kindergarten_cost=2500,
                monthly_primary_secondary_cost=4000,
            )
        ],
    )

    assert monthly_household_expense_at(household, as_of=date(2027, 2, 1)) == 13_000
    assert monthly_household_expense_at(household, as_of=date(2031, 1, 1)) == 12_500
    assert monthly_household_expense_at(household, as_of=date(2034, 1, 1)) == 14_000


def test_child_plan_default_expense_profile_is_filled_by_normalization() -> None:
    from app.database import normalize_household_data

    normalized = normalize_household_data(
        {
            "child_plans": [
                {
                    "name": "样例子女",
                    "enabled": True,
                    "birth_month": "2027-01",
                    "monthly_childcare_cost_before_kindergarten": 0,
                    "monthly_kindergarten_cost": 0,
                    "monthly_primary_secondary_cost": 0,
                    "monthly_higher_education_cost": 0,
                }
            ]
        }
    )
    child = normalized["child_plans"][0]

    assert child["monthly_childcare_cost_before_kindergarten"] == 4500
    assert child["monthly_kindergarten_cost"] == 5000
    assert child["monthly_primary_secondary_cost"] == 6000
    assert child["monthly_higher_education_cost"] == 8000
    assert child["birth_medical_cost"] == 30000


def test_child_plan_birth_range_generates_strategy_and_maternal_age_warning() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        members=[
            IncomeMember(name="样例成员A", sex="male", birth_month="1990-01"),
            IncomeMember(name="样例成员B", sex="female", birth_month="1990-01"),
        ],
        child_plans=[
            ChildPlanData(
                name="样例子女",
                enabled=True,
                timing_mode="manual_month",
                planned_birth_start_month="2027-06",
                planned_birth_end_month="2027-12",
                monthly_preparation_cost=1000,
                monthly_pregnancy_cost=2000,
                birth_medical_cost=20000,
                postpartum_recovery_cost=10000,
                initial_baby_supplies_cost=5000,
                monthly_childcare_cost_before_kindergarten=3000,
            )
        ],
    )

    strategies = build_child_plan_strategies(household, rule, as_of=date(2026, 7, 1))

    assert strategies[0].birth_month_label == "2027-06"
    assert strategies[0].mother_member_name == "样例成员B"
    assert strategies[0].mother_age_at_birth == pytest.approx(37.42, abs=0.02)
    assert any("高龄妊娠" in warning for warning in strategies[0].warnings)
    assert strategies[0].first_year_cash_need >= 35_000
    assert 0 <= strategies[0].happiness_score <= 10


def test_child_plan_strategy_consumes_planning_goal_snapshot_directly() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        members=[IncomeMember(name="样例成员B", sex="female", birth_month="1995-01")],
        child_plans=[
            ChildPlanData(
                name="样例子女",
                enabled=True,
                planning_goal_id="child-goal-a",
                timing_mode="manual_month",
                planned_birth_month="2027-01",
                monthly_pregnancy_cost=2000,
                monthly_childcare_cost_before_kindergarten=3000,
            )
        ],
    )
    context = CalculationContextSnapshot(
        planning_goals=[
            CalculationContextGoalSnapshot(
                id="child-goal-a",
                goal_type="child",
                name="样例子女",
                priority=30,
                sequence_index=1,
                normalized_timing_mode="manual_month",
                resolved_not_before_month=48,
                resolved_window_start_month=48,
                resolved_window_end_month=48,
                explanation="按统一目标窗口安排出生月。",
            )
        ]
    )

    strategies = build_child_plan_strategies(
        household,
        rule,
        as_of=date(2026, 7, 1),
        calculation_context=context,
    )

    assert strategies[0].planning_goal_id == "child-goal-a"
    assert strategies[0].source == "planning_goals"
    assert strategies[0].timing_mode == "manual_month"
    assert strategies[0].birth_month_label == "2030-07"
    assert any("统一规划目标" in warning for warning in strategies[0].warnings)


def test_child_plan_strategy_order_uses_resolved_planning_goal_sequence() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        members=[IncomeMember(name="样例成员B", sex="female", birth_month="1995-01")],
        child_plans=[
            ChildPlanData(
                name="旧顺序靠前子女",
                enabled=True,
                planning_goal_id="child-goal-b",
                timing_mode="manual_month",
                planned_birth_month="2028-01",
            ),
            ChildPlanData(
                name="目标顺序靠前子女",
                enabled=True,
                planning_goal_id="child-goal-a",
                timing_mode="manual_month",
                planned_birth_month="2028-01",
            ),
        ],
    )
    context = CalculationContextSnapshot(
        planning_goals=[
            CalculationContextGoalSnapshot(
                id="child-goal-a",
                goal_type="child",
                name="目标顺序靠前子女",
                priority=40,
                sequence_index=1,
                normalized_timing_mode="manual_month",
                resolved_not_before_month=24,
                resolved_window_start_month=24,
            ),
            CalculationContextGoalSnapshot(
                id="child-goal-b",
                goal_type="child",
                name="旧顺序靠前子女",
                priority=30,
                sequence_index=2,
                normalized_timing_mode="manual_month",
                resolved_not_before_month=36,
                resolved_window_start_month=36,
            ),
        ]
    )

    strategies = build_child_plan_strategies(
        household,
        rule,
        as_of=date(2026, 7, 1),
        calculation_context=context,
    )

    assert [item.child_name for item in strategies] == ["目标顺序靠前子女", "旧顺序靠前子女"]
    assert [item.planning_goal_id for item in strategies] == ["child-goal-a", "child-goal-b"]


def test_child_plan_after_home_uses_purchase_month_when_no_birth_range() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        members=[IncomeMember(name="样例成员B", sex="female", birth_month="1990-01")],
        child_plans=[
            ChildPlanData(
                name="样例子女",
                enabled=True,
                timing_mode="after_first_home",
                monthly_pregnancy_cost=2000,
                monthly_childcare_cost_before_kindergarten=3000,
            )
        ],
    )

    before_home = monthly_household_expense_at(household, 5, as_of=date(2026, 7, 1), rules=rule, home_purchase_month=12)
    pregnancy_month = monthly_household_expense_at(household, 15, as_of=date(2026, 7, 1), rules=rule, home_purchase_month=12)
    birth_month = monthly_household_expense_at(household, 24, as_of=date(2026, 7, 1), rules=rule, home_purchase_month=12)

    assert before_home == 0
    assert pregnancy_month == 2000
    assert birth_month == 93_000


def test_child_planning_policy_controls_birth_delay_and_maternal_age_threshold() -> None:
    base_rule = _zero_contribution_rule()
    rule = base_rule.model_copy(
        update={
            "params": {
                **base_rule.params,
                "child_plan_birth_after_home_delay_months": 3,
                "child_plan_advanced_maternal_age": 40,
            }
        }
    )
    household = HouseholdData(
        members=[IncomeMember(name="样例成员B", sex="female", birth_month="1990-01")],
        child_plans=[
            ChildPlanData(
                name="样例子女",
                enabled=True,
                timing_mode="after_first_home",
                monthly_pregnancy_cost=2000,
                monthly_childcare_cost_before_kindergarten=3000,
            )
        ],
    )

    pregnancy_month = monthly_household_expense_at(household, 5, as_of=date(2026, 7, 1), rules=rule, home_purchase_month=3)
    birth_month = monthly_household_expense_at(household, 6, as_of=date(2026, 7, 1), rules=rule, home_purchase_month=3)
    strategies = build_child_plan_strategies(
        household,
        rule,
        as_of=date(2026, 7, 1),
        home_purchase_month=3,
    )

    assert pregnancy_month == 2000
    assert birth_month == 93_000
    assert strategies[0].birth_month_label == "2027-01"
    assert not any("高龄妊娠" in warning for warning in strategies[0].warnings)


def test_personal_pension_deduction_is_capped_annually() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="样例成员A",
                monthly_salary_gross=40_000,
                annual_bonus=0,
                monthly_special_additional_deduction=0,
                personal_pension_account_enabled=True,
                personal_pension_contribution_mode="fixed_annual",
                personal_pension_annual_contribution_target=30_000,
                personal_pension_contribution_start_month="2027-01",
            )
        ],
    )
    without = household.model_copy(
        update={
            "members": [
                household.members[0].model_copy(
                    update={
                        "personal_pension_account_enabled": False,
                        "personal_pension_contribution_mode": "none",
                    }
                )
            ]
        }
    )

    summary = calculate_household_tax_for_year(household, rule, 2027).summaries[0]
    summary_without = calculate_household_tax_for_year(without, rule, 2027).summaries[0]

    assert summary.taxable_income == pytest.approx(summary_without.taxable_income - 12_000)
    assert summary.total_tax < summary_without.total_tax


def test_personal_pension_auto_strategy_applies_only_with_taxable_work_income() -> None:
    rule = _zero_contribution_rule()
    salary_member = IncomeMember(
        name="样例成员A",
        monthly_salary_gross=30_000,
        annual_bonus=0,
        personal_pension_account_enabled=True,
        personal_pension_contribution_mode="auto_tax_optimal",
        income_stages=[
            IncomeStageData(
                name="工资阶段",
                stage_kind="salary",
                start_date="2027-01-01",
                monthly_salary_gross=30_000,
            )
        ],
    )
    pension_member = salary_member.model_copy(
        update={
            "income_stages": [
                IncomeStageData(
                    name="退休养老金",
                    stage_kind="pension",
                    start_date="2027-01-01",
                    monthly_non_taxable_income=5_000,
                )
            ]
        }
    )

    salary_profile = household_monthly_income_profile_at(HouseholdData(members=[salary_member]), rule, as_of=date(2027, 1, 1))
    pension_profile = household_monthly_income_profile_at(HouseholdData(members=[pension_member]), rule, as_of=date(2027, 1, 1))

    assert salary_profile.personal_pension_contribution == pytest.approx(1_000)
    assert salary_profile.other_cash_outflow == 0
    assert salary_profile.income_tax < household_monthly_income_profile_at(
        HouseholdData(members=[salary_member.model_copy(update={"personal_pension_account_enabled": False})]),
        rule,
        as_of=date(2027, 1, 1),
    ).income_tax
    assert pension_profile.personal_pension_contribution == 0
    assert pension_profile.other_cash_outflow == 0


def test_personal_pension_auto_strategy_recommends_open_month_from_taxable_income() -> None:
    rule = _zero_contribution_rule()
    member = IncomeMember(
        name="样例成员A",
        monthly_salary_gross=0,
        annual_bonus=0,
        personal_pension_account_enabled=True,
        personal_pension_open_mode="auto_tax_optimal",
        personal_pension_contribution_mode="auto_tax_optimal",
        income_stages=[
            IncomeStageData(
                name="未就业阶段",
                stage_kind="unemployment",
                start_date="2027-01-01",
            ),
            IncomeStageData(
                name="工资阶段",
                stage_kind="salary",
                start_date="2027-07-01",
                monthly_salary_gross=30_000,
            ),
        ],
    )
    household = HouseholdData(members=[member])

    june = household_monthly_income_profile_at(household, rule, as_of=date(2027, 6, 1))
    july = household_monthly_income_profile_at(household, rule, as_of=date(2027, 7, 1))
    result = calculate_affordability(household, ScenarioData(total_price=2_000_000), rule)
    strategy = next(item for item in result.tax_strategy_items if item.deduction_type == "personal_pension")

    assert june.personal_pension_contribution == 0
    assert july.personal_pension_contribution == pytest.approx(1000)
    assert strategy.status == "auto_enabled"
    assert strategy.start_month == "2027-07"
    assert strategy.cash_contribution == pytest.approx(12_000)
    assert strategy.estimated_tax_saving > 0
    timeline = next(item for item in result.tax_strategy_timeline if item.category == "personal_pension")
    assert timeline.member_name == "样例成员A"
    assert timeline.amount == pytest.approx(12_000)
    assert timeline.estimated_tax_saving > 0


def test_personal_pension_contribution_enters_cashflow_and_account_projection() -> None:
    rule = _zero_contribution_rule().model_copy(
        update={
            "params": {
                **_zero_contribution_rule().params,
                "personal_pension_deduction_annual_cap": 12000,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=100_000,
        investments=0,
        members=[
            IncomeMember(
                name="样例成员A",
                personal_pension_account_enabled=True,
                personal_pension_account_balance=12_000,
                personal_pension_contribution_mode="auto_tax_optimal",
                personal_pension_annual_return=0.12,
                income_stages=[
                    IncomeStageData(
                        name="工资阶段",
                        stage_kind="salary",
                        start_date="2027-01-01",
                        monthly_salary_gross=30_000,
                    )
                ],
            )
        ],
    )

    result = calculate_affordability(household, ScenarioData(total_price=2_000_000), rule)
    plan = result.purchase_plan_analyses[0]
    first_month = next(item for item in result.monthly_cashflow_visualization if item.plan_variant == plan.variant and item.month == 6)

    assert first_month.personal_pension_contribution == pytest.approx(1_000)
    assert first_month.personal_pension_return > 0
    assert first_month.personal_pension_balance > 13_000
    assert any(
        entry.category == "personal_pension_contribution" and entry.amount == pytest.approx(-1_000)
        for entry in first_month.ledger_entries
    )


def test_removed_top_level_personal_pension_accounts_are_discarded() -> None:
    from app.database import normalize_household_data

    normalized = normalize_household_data(
        {
            "members": [
                {
                    "name": "样例成员A",
                    "income_stages": [],
                }
            ],
            "personal_pension_accounts": [
                {
                    "member_name": "样例成员A",
                    "enabled": True,
                    "current_balance": 5_000,
                    "annual_contribution": 12_000,
                    "contribution_month": 4,
                    "start_year": 2027,
                    "end_year": 2030,
                    "annual_return": 0.03,
                }
            ],
        }
    )

    member = normalized["members"][0]
    assert "personal_pension_accounts" not in normalized
    assert member["personal_pension_account_enabled"] is True
    assert member["personal_pension_account_balance"] == 0
    assert member["personal_pension_open_mode"] == "auto_tax_optimal"
    assert member["personal_pension_contribution_mode"] == "auto_tax_optimal"
    assert member["personal_pension_annual_contribution_target"] == 0
    assert member["personal_pension_contribution_start_month"] == ""
    assert member["personal_pension_contribution_end_month"] is None


def test_annual_bonus_separate_tax_defaults_to_continue_after_2028() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2029,
        members=[
            IncomeMember(
                name="样例成员A",
                monthly_salary_gross=20_000,
                annual_bonus=120_000,
                bonus_tax_method="separate",
                income_stages=[
                    IncomeStageData(
                        name="未来阶段",
                        start_date="2029-01-01",
                        monthly_salary_gross=20_000,
                        annual_bonus=120_000,
                        annual_bonus_payout_month=4,
                        bonus_tax_method="separate",
                    )
                ],
            )
        ],
    )

    summary = calculate_household_tax_for_year(household, rule, 2029).summaries[0]

    assert summary.selected_bonus_method == "separate"
    assert summary.bonus_tax > 0


def test_annual_bonus_earning_period_prorates_cross_year_bonus() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        income_projection_year=2027,
        members=[
            IncomeMember(
                name="样例成员A",
                monthly_salary_gross=20_000,
                annual_bonus=120_000,
                income_stages=[
                    IncomeStageData(
                        name="入职后阶段",
                        start_date="2026-07-01",
                        monthly_salary_gross=20_000,
                        annual_bonus=120_000,
                        annual_bonus_payout_month=4,
                        annual_bonus_earning_start_month="2026-07",
                        annual_bonus_earning_end_month="2027-01",
                        bonus_tax_method="merged",
                    )
                ],
            )
        ],
    )

    summary = calculate_household_tax_for_year(household, rule, 2027).summaries[0]

    assert summary.gross_annual_income == pytest.approx(20_000 * 12 + 120_000 * 7 / 12)


def test_investment_tax_profile_reduces_backend_investment_return() -> None:
    household = HouseholdData(
        cash_account_balance=500_000,
        investments=200_000,
        monthly_expense=5_000,
        investment_plan_name="manual_investment",
        monthly_investment_amount=0,
        investment_tax_profile=InvestmentTaxProfileData(
            stock_dividend_short_ratio=1.0,
            stock_dividend_short_holding_tax_rate=0.2,
        ),
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=20_000, annual_bonus=0)],
    )
    scenario = ScenarioData(
        total_price=100_000,
        annual_investment_return=0.12,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    first_month = next(item for item in result.monthly_cashflow_visualization if item.investment_return > 0)

    assert first_month.investment_return > 0
    assert first_month.investment_tax == pytest.approx(first_month.investment_return * 0.2)
    investment_tax_timeline = next(item for item in result.tax_strategy_timeline if item.category == "investment_tax")
    assert investment_tax_timeline.status == "auto_enabled"
    assert investment_tax_timeline.amount == pytest.approx(0.2)
    assert "投资账户" in investment_tax_timeline.detail


def test_investment_tax_defaults_follow_investment_strategy_allocation() -> None:
    household = HouseholdData(
        cash_account_balance=500_000,
        investments=200_000,
        monthly_expense=5_000,
        investment_plan_name="balanced",
        monthly_investment_amount=0,
        investment_equity_ratio=0.25,
        investment_bond_ratio=0.45,
        investment_cash_ratio=0.30,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=20_000, annual_bonus=0)],
    )
    scenario = ScenarioData(
        total_price=100_000,
        annual_investment_return=0.12,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    first_month = next(item for item in result.monthly_cashflow_visualization if item.investment_return > 0)
    investment_tax_timeline = next(item for item in result.tax_strategy_timeline if item.category == "investment_tax")

    expected_rate = 0.45 * 0.30 * 0.20 + 0.25 * 0.05 * 0.20
    assert first_month.investment_tax == pytest.approx(first_month.investment_return * expected_rate)
    assert investment_tax_timeline.status == "auto_enabled"
    assert investment_tax_timeline.amount == pytest.approx(round(expected_rate, 2))
    assert investment_tax_timeline.source == "strategy_auto"
    assert "按理财策略资产配置自动估算" in investment_tax_timeline.detail


def test_cash_only_investment_tax_default_explains_zero_rate() -> None:
    household = HouseholdData(
        cash_account_balance=500_000,
        investments=200_000,
        monthly_expense=5_000,
        investment_plan_name="cash_only",
        monthly_investment_amount=0,
        investment_equity_ratio=0,
        investment_bond_ratio=0,
        investment_cash_ratio=1,
        members=[IncomeMember(name="样例成员A", monthly_salary_gross=20_000, annual_bonus=0)],
    )
    scenario = ScenarioData(
        total_price=100_000,
        annual_investment_return=0.12,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )

    result = calculate_affordability(household, scenario, RulePackData())
    investment_tax_timeline = next(item for item in result.tax_strategy_timeline if item.category == "investment_tax")

    assert investment_tax_timeline.status == "available"
    assert investment_tax_timeline.amount == 0
    assert investment_tax_timeline.source == "strategy_auto"
    assert "有效税率为 0" in investment_tax_timeline.detail


def _sample_purchase_plan(variant: str = "sample_plan") -> calculator_module.PurchasePlanAnalysis:
    return calculator_module.PurchasePlanAnalysis(
        variant=variant,
        description="sample",
        months_to_buy=12,
        years_to_buy=1,
        minimum_down_payment=0,
        planned_down_payment=0,
        provident_fund_extractable=0,
        provident_upfront_extractable=0,
        family_provident_upfront_extractable=0,
        family_down_payment_support_amount=0,
        family_down_payment_support_mode="none",
        family_down_payment_support_label="",
        provident_post_transaction_extractable=0,
        required_cash_after_pf_extract=0,
        upfront_cash_required=0,
        commercial_loan_amount=0,
        provident_loan_amount=0,
        provident_policy_bonus=0,
        provident_policy_cap=0,
        commercial_loan_years=30,
        provident_loan_years=30,
        provident_loan_year_limit_reasons=[],
        commercial_repayment_method="equal_installment",
        provident_repayment_method="equal_installment",
        commercial_monthly_payment=0,
        provident_monthly_payment=0,
        total_monthly_payment=0,
        total_interest=0,
        renovation_cost=0,
        renovation_funding_mode="after_purchase_saving",
        renovation_included_in_upfront_cash=False,
        months_to_renovation=0,
        years_to_renovation=0,
        post_purchase_renovation_monthly_saving=0,
        cash_after_transaction=0,
        cash_after_purchase=0,
        provident_balance_after_extract=0,
        required_liquidity_reserve=0,
        liquidity_ok=True,
        post_purchase_cash_flow=0,
        monthly_post_purchase_pf_withdrawal=0,
        post_purchase_cash_flow_with_pf_withdrawal=0,
        debt_to_income_ratio=0,
        happiness_score=0,
        provident_extraction_notes=[],
        happiness_breakdown=[],
    )


def test_social_security_accounts_accrue_from_salary_stage() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999999,
                "employee_pension_rate": 0.08,
                "employee_medical_rate": 0.02,
                "medical_account_employee_transfer_rate": 0.02,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="sample_member",
                pension_account_balance=1_000,
                medical_account_balance=200,
                income_stages=[
                    IncomeStageData(
                        name="salary_stage",
                        start_date="2026-07-01",
                        monthly_salary_gross=20_000,
                    )
                ],
            )
        ]
    )
    plan = _sample_purchase_plan()

    rows = build_social_security_visualization(household, rule, [plan], None, horizon_months=2, as_of=date(2026, 7, 1))
    first_month = next(item for item in rows if item.month == 1)

    assert first_month.pension_contribution == pytest.approx(1_600)
    assert first_month.medical_contribution == pytest.approx(400)
    assert first_month.pension_balance_end == pytest.approx(2_600)
    assert first_month.medical_balance_end == pytest.approx(600)


def test_disabled_social_security_accounts_do_not_accrue() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999999,
                "employee_pension_rate": 0.08,
                "medical_account_employee_transfer_rate": 0.02,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="sample_member",
                pension_account_enabled=False,
                medical_account_enabled=False,
                pension_account_balance=1_000,
                medical_account_balance=200,
                income_stages=[
                    IncomeStageData(
                        name="salary_stage",
                        start_date="2026-07-01",
                        monthly_salary_gross=20_000,
                    )
                ],
            )
        ]
    )

    rows = build_social_security_visualization(household, rule, [_sample_purchase_plan()], None, horizon_months=1, as_of=date(2026, 7, 1))
    first_month = next(item for item in rows if item.month == 1)

    assert first_month.pension_contribution == 0
    assert first_month.medical_contribution == 0
    assert first_month.pension_balance_end == 0
    assert first_month.medical_balance_end == 0


def test_social_security_account_interest_uses_policy_credit_months() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999999,
                "employee_pension_rate": 0,
                "medical_account_employee_transfer_rate": 0,
                "pension_personal_account_annual_return": 0.12,
                "pension_personal_account_interest_credit_month": 12,
                "medical_account_annual_interest_rate": 0.04,
                "medical_account_interest_credit_months": [3, 6, 9, 12],
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="sample_member",
                family_join_month="2026-01",
                pension_account_open_month="2026-01",
                medical_account_open_month="2026-01",
                pension_account_balance=10_000,
                medical_account_balance=1_000,
                income_stages=[
                    IncomeStageData(
                        name="salary_stage",
                        start_date="2026-01-01",
                        monthly_salary_gross=20_000,
                    )
                ],
            )
        ]
    )

    rows = build_social_security_visualization(household, rule, [_sample_purchase_plan()], None, horizon_months=12, as_of=date(2026, 1, 1))
    february = next(item for item in rows if item.month == 1)
    march = next(item for item in rows if item.month == 2)
    december = next(item for item in rows if item.month == 11)

    assert february.pension_interest == 0
    assert february.medical_interest == 0
    assert march.medical_interest > 0
    assert march.pension_interest == 0
    assert december.pension_interest > 0


def test_social_security_accounts_stop_salary_contribution_after_retirement_and_keep_non_negative() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999999,
                "employee_pension_rate": 0.08,
                "medical_account_employee_transfer_rate": 0.02,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
                "medical_account_retiree_monthly_transfer_under_70": 100,
                "medical_account_retiree_large_mutual_aid_monthly": 3,
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="retiring_member",
                birth_month="1963-07",
                retirement_category="male_60",
                pension_account_balance=10,
                medical_account_balance=0,
                income_stages=[
                    IncomeStageData(
                        name="salary_stage",
                        start_date="2026-07-01",
                        monthly_salary_gross=10_000,
                    )
                ],
            )
        ]
    )
    plan = _sample_purchase_plan("retirement_plan")

    rows = build_social_security_visualization(household, rule, [plan], None, horizon_months=3, as_of=date(2026, 7, 1))
    retired_month = next(item for item in rows if item.month == 1)

    assert retired_month.pension_contribution == 0
    assert retired_month.medical_retiree_transfer == pytest.approx(100)
    assert retired_month.medical_outflow == pytest.approx(3)
    assert retired_month.medical_balance_end >= 0


def test_retired_pension_account_pays_out_by_policy_months() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
                "medical_account_retiree_monthly_transfer_under_70": 0,
                "medical_account_retiree_large_mutual_aid_monthly": 0,
                "pension_personal_account_months_by_retirement_category": {"male_60": 10},
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="retired_member",
                birth_month="1963-07",
                retirement_category="male_60",
                pension_account_balance=1_000,
                medical_account_balance=0,
                income_stages=[],
            )
        ]
    )

    rows = build_social_security_visualization(household, rule, [_sample_purchase_plan()], None, horizon_months=3, as_of=date(2026, 7, 1))
    first_retired_month = next(item for item in rows if item.month == 1)
    second_retired_month = next(item for item in rows if item.month == 2)

    assert first_retired_month.pension_account_payout == pytest.approx(100)
    assert first_retired_month.pension_balance_end == pytest.approx(900)
    assert second_retired_month.pension_account_payout == pytest.approx(100)
    assert second_retired_month.pension_balance_end == pytest.approx(800)


def test_social_security_account_projection_uses_policy_interface() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
                "medical_account_retiree_monthly_transfer_under_70": 120,
                "medical_account_retiree_large_mutual_aid_monthly": 5,
                "pension_personal_account_months_by_retirement_category": {"male_60": 4},
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="retired_member",
                birth_month="1963-07",
                retirement_category="male_60",
                pension_account_balance=400,
                medical_account_balance=0,
                income_stages=[],
            )
        ]
    )

    rows = build_social_security_visualization(household, rule, [_sample_purchase_plan()], None, horizon_months=1, as_of=date(2026, 7, 1))
    retired_month = next(item for item in rows if item.month == 1)

    assert retired_month.pension_account_payout == pytest.approx(100)
    assert retired_month.medical_retiree_transfer == pytest.approx(120)
    assert retired_month.medical_mutual_aid_outflow == pytest.approx(5)


def test_retired_pension_account_stops_payout_after_balance_depleted() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
                "medical_account_retiree_monthly_transfer_under_70": 0,
                "medical_account_retiree_large_mutual_aid_monthly": 0,
                "pension_personal_account_months_by_retirement_category": {"male_60": 2},
            }
        }
    )
    household = HouseholdData(
        members=[
            IncomeMember(
                name="retired_member",
                birth_month="1963-07",
                retirement_category="male_60",
                pension_account_balance=100,
                medical_account_balance=0,
                income_stages=[],
            )
        ]
    )

    rows = build_social_security_visualization(household, rule, [_sample_purchase_plan()], None, horizon_months=4, as_of=date(2026, 7, 1))
    first_retired_month = next(item for item in rows if item.month == 1)
    second_retired_month = next(item for item in rows if item.month == 2)
    after_depleted_month = next(item for item in rows if item.month == 3)

    assert first_retired_month.pension_account_payout == pytest.approx(50)
    assert second_retired_month.pension_account_payout == pytest.approx(50)
    assert second_retired_month.pension_balance_end == pytest.approx(0)
    assert after_depleted_month.pension_account_payout == pytest.approx(0)
    assert after_depleted_month.pension_balance_end == pytest.approx(0)


def test_medical_account_splits_retiree_mutual_aid_and_healthcare_outflow() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
                "medical_account_retiree_monthly_transfer_under_70": 100,
                "medical_account_retiree_large_mutual_aid_monthly": 3,
            }
        }
    )
    household = HouseholdData(
        scheduled_expenses=[
            ScheduledExpenseData(
                name="医疗支出",
                monthly_amount=80,
                start_month="2026-08",
                medical_account_payable=True,
            )
        ],
        members=[
            IncomeMember(
                name="retired_member",
                birth_month="1963-07",
                retirement_category="male_60",
                pension_account_balance=0,
                medical_account_balance=20,
                income_stages=[],
            )
        ],
    )

    rows = build_social_security_visualization(household, rule, [_sample_purchase_plan()], None, horizon_months=1, as_of=date(2026, 7, 1))
    retired_month = next(item for item in rows if item.month == 1)

    assert retired_month.medical_retiree_transfer == pytest.approx(100)
    assert retired_month.medical_mutual_aid_outflow == pytest.approx(3)
    assert retired_month.medical_healthcare_outflow == pytest.approx(80)
    assert retired_month.medical_outflow == pytest.approx(83)
    assert retired_month.medical_balance_end == pytest.approx(37)


def test_medical_account_payable_expense_reduces_cash_scheduled_expense() -> None:
    rule = RulePackData().model_copy(
        update={
            "params": {
                **RulePackData().params,
                "pension_personal_account_annual_return": 0,
                "medical_account_annual_interest_rate": 0,
                "medical_account_retiree_monthly_transfer_under_70": 0,
                "medical_account_retiree_large_mutual_aid_monthly": 0,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=10_000,
        investments=0,
        investment_plan_name="cash_only",
        scheduled_expenses=[
            ScheduledExpenseData(
                name="医保可支付医疗支出",
                monthly_amount=800,
                start_month="2026-08",
                medical_account_payable=True,
            )
        ],
        members=[
            IncomeMember(
                name="sample_member",
                pension_account_balance=0,
                medical_account_balance=500,
                income_stages=[],
            )
        ],
    )
    plan = _sample_purchase_plan()
    social_security_rows = build_social_security_visualization(household, rule, [plan], None, horizon_months=1, as_of=date(2026, 7, 1))

    cashflow_rows, _, ledger_rows = build_monthly_cashflow_visualization(
        household,
        ScenarioData(),
        rule,
        [plan],
        calculate_car_loan(CarPlanData()),
        [],
        [],
        social_security_rows,
    )
    month_one = next(item for item in cashflow_rows if item.month == 1)

    assert social_security_rows[1].medical_healthcare_outflow == pytest.approx(500)
    assert month_one.scheduled_expense == pytest.approx(300)
    assert month_one.monthly_cash_delta == pytest.approx(-300)
    assert any(item.category == "medical_healthcare_outflow" and item.amount == pytest.approx(-500) for item in ledger_rows)


def test_scheduled_expense_category_scopes_medical_account_payment() -> None:
    general_expense = ScheduledExpenseData(
        name="示例普通支出",
        monthly_amount=500,
        expense_category="general",
        medical_account_payable=True,
    )
    legacy_medical_expense = ScheduledExpenseData(
        name="示例医疗支出",
        monthly_amount=500,
        medical_account_payable=True,
    )

    assert general_expense.expense_category == "general"
    assert general_expense.medical_account_payable is False
    assert legacy_medical_expense.expense_category == "medical"
    assert legacy_medical_expense.medical_account_payable is True


def test_member_can_have_no_income_stage_without_top_level_income_fallback() -> None:
    household = HouseholdData(
        monthly_income=50_000,
        members=[
            IncomeMember(
                name="样例成员A",
                monthly_salary_gross=30_000,
                annual_bonus=120_000,
                income_stages=[],
            )
        ],
    )
    profile = household_monthly_income_profile_at(household, RulePackData(), as_of=date(2026, 7, 1))
    tax_summary = calculate_household_tax_for_year(household, RulePackData(), 2027)

    assert profile.gross_income == 0
    assert profile.net_income == 0
    assert tax_summary.gross_annual_income == 0
    assert tax_summary.total_tax == 0


def test_career_shock_self_payment_is_backend_monthly_expense() -> None:
    base_rules = RulePackData()
    rules = base_rules.model_copy(
        update={
            "params": {
                **base_rules.params,
                "beijing_social_base_floor": 0,
                "beijing_social_base_ceiling": 999_999,
                "beijing_housing_fund_base_floor": 0,
                "beijing_housing_fund_base_ceiling": 999_999,
                "flexible_employment_social_base": 10_000,
                "flexible_employment_pension_rate": 0.20,
                "flexible_employment_unemployment_rate": 0.01,
                "flexible_employment_medical_monthly": 500,
                "flexible_employment_housing_fund_base": 10_000,
                "flexible_employment_housing_fund_rate": 0.12,
            }
        }
    )
    household = HouseholdData(
        cash_account_balance=1_000_000,
        required_liquidity_months=1,
        investment_cash_reserve_months=1,
        members=[
            IncomeMember(
                name="样例成员A",
                birth_month="1991-07",
                retirement_category="male_60",
                income_stages=[
                    IncomeStageData(
                        name="工资阶段",
                        start_date="2026-07-01",
                        end_date="2026-07-31",
                        monthly_salary_gross=10_000,
                    )
                ],
            )
        ],
        career_shock=CareerShockData(
            enabled=True,
            auto_unemployment_benefit=False,
            unemployment_benefit_months=0,
            auto_self_social_insurance=True,
            auto_flexible_housing_fund=True,
            member_settings=[
                CareerShockMemberSetting(
                    member_name="样例成员A",
                    enabled=True,
                    layoff_age=35,
                )
            ],
        ),
    )
    scenario = ScenarioData(total_price=100_000, down_payment_amount=30_000, target_name="示例房源")

    result = calculate_affordability(household, scenario, rules)
    month_after_layoff = next(item for item in result.monthly_cashflow_visualization if item.month == 1)

    assert result.career_shock_projection is not None
    assert result.career_shock_projection.member_projections[0].self_payment_monthly == pytest.approx(3_800)
    assert month_after_layoff.career_shock_self_payment == pytest.approx(3_800)
    assert month_after_layoff.scheduled_expense == 0
    assert month_after_layoff.monthly_cash_delta == pytest.approx(-3_800)


def test_account_calibration_updates_backend_projection_and_events() -> None:
    today = date.today()
    base_month = date(today.year, today.month, 1)
    next_month_year = base_month.year + (base_month.month // 12)
    next_month_value = base_month.month % 12 + 1
    next_month = f"{next_month_year:04d}-{next_month_value:02d}"
    household = HouseholdData(
        cash_account_balance=100_000,
        investments=20_000,
        monthly_income=0,
        monthly_expense=0,
        monthly_investment_amount=0,
        account_calibrations=[
            {
                "month": next_month,
                "calibration_scope": "major_event",
                "target": "cash",
                "amount": 50_000,
                "source_title": "示例重大事件",
                "source_category": "home_purchase",
                "note": "月度对账",
            },
            {
                "month": next_month,
                "target": "investment",
                "amount": 30_000,
            },
            {
                "month": next_month,
                "target": "total_loan",
                "amount": 12_345,
                "reference_name": "示例贷款",
            },
        ],
    )
    scenario = ScenarioData(total_price=10_000_000, annual_investment_return=0)

    result = calculate_affordability(household, scenario, RulePackData())
    plan_variant = result.purchase_plan_analyses[0].variant
    month_one = next(
        row
        for row in result.monthly_cashflow_visualization
        if row.plan_variant == plan_variant and row.month == 1
    )
    month_two = next(
        row
        for row in result.monthly_cashflow_visualization
        if row.plan_variant == plan_variant and row.month == 2
    )

    assert month_one.cash_balance == pytest.approx(50_000)
    assert month_one.investment_balance == pytest.approx(30_000)
    assert month_one.total_loan_balance == pytest.approx(12_345)
    assert month_two.cash_balance == pytest.approx(50_000)
    assert month_two.investment_balance == pytest.approx(30_000)
    assert month_two.total_loan_balance == pytest.approx(12_345)
    assert any(
        entry.category == "account_calibration" and entry.plan_variant == plan_variant
        for entry in result.monthly_ledger
    )
    assert any(
        event.title.startswith("手动校准") and event.plan_variant == plan_variant
        for event in result.plan_events
    )
    assert any(
        "示例重大事件" in event.title and "来源：示例重大事件" in event.detail
        for event in result.plan_events
    )


def test_income_stage_manual_cash_adjustment_is_cleared_by_normalization() -> None:
    from app.database import normalize_household_data

    normalized = normalize_household_data(
        {
            "manual_adjustments": [
                {
                    "name": "旧手动现金流",
                    "amount": -1000,
                }
            ],
            "members": [
                {
                    "name": "样例成员A",
                    "monthly_extra_cash_expense": 800,
                    "income_stages": [
                        {
                            "name": "工资阶段",
                            "stage_kind": "salary",
                            "start_date": "2026-07-01",
                            "monthly_salary_gross": 20000,
                            "monthly_extra_cash_expense": 1000,
                        }
                    ],
                }
            ],
        }
    )

    assert "manual_adjustments" not in normalized
    assert normalized["members"][0]["monthly_extra_cash_expense"] == 0
    assert normalized["members"][0]["income_stages"][0]["monthly_extra_cash_expense"] == 0
