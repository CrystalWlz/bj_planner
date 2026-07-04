import pytest
from datetime import date
from pydantic import ValidationError

import app.calculator as calculator_module
from app.calculator import (
    _car_monthly_cash_cost_at,
    _is_beijing_pf_offset_month,
    _quarterly_rent_withdrawal_before_purchase_at,
    _semiannual_loan_offset_monthly_equivalent,
    calculate_affordability,
    calculate_car_loan,
    calculate_household_tax,
    calculate_loan,
    household_monthly_income_profile_at,
    monthly_household_expense_at,
    summarize_phased_loans,
)
from app.schemas import CareerShockData, CareerShockMemberSetting, CarPlanData, ElderlyDependentData, HouseholdData, IncomeMember, IncomeStageData, RulePackData, ScenarioData, ScheduledExpenseData, PhasedLoanData


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
    result = calculate_affordability(household, scenario, RulePackData())
    assert result.status == "不可行"
    assert result.funding_gap > 0


def test_affordability_builds_stress_tests() -> None:
    result = calculate_affordability(HouseholdData(), ScenarioData(), RulePackData())
    assert len(result.stress_tests) == 3
    assert {item.name for item in result.stress_tests} == {"利率上行", "收入下降", "房价上行"}


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

    serial = calculate_affordability(household, scenario, serial_rules)
    parallel = calculate_affordability(household, scenario, parallel_rules)

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
            enabled=True,
            total_price=250_000,
            down_payment_ratio=0.5,
            down_payment=125_000,
            purchase_delay_months=6,
            second_car_enabled=True,
            second_car_total_price=180_000,
            second_car_purchase_delay_months=48,
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
            IncomeMember(name="我", current_age=30, monthly_salary_gross=20_000, annual_bonus=0, monthly_special_additional_deduction=0),
            IncomeMember(name="成员B", current_age=28, monthly_salary_gross=12_000, annual_bonus=0, monthly_special_additional_deduction=0),
        ],
    )

    before_layoff = household_monthly_income_profile_at(household, rule, as_of=date(2026, 7, 1))
    unemployment = household_monthly_income_profile_at(household, rule, months_from_now=12, as_of=date(2026, 7, 1))
    self_social = household_monthly_income_profile_at(household, rule, months_from_now=14, as_of=date(2026, 7, 1))
    pension = household_monthly_income_profile_at(household, rule, months_from_now=240, as_of=date(2026, 7, 1))

    assert unemployment.non_taxable_income == pytest.approx(2_000)
    assert unemployment.net_income < before_layoff.net_income
    assert self_social.personal_social == pytest.approx(1_800)
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
    assert after_benefit.personal_social == pytest.approx(2180)


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
                    auto_pension_monthly=True,
                )
            ],
        ),
        members=[IncomeMember(name="样例成员", current_age=30, monthly_salary_gross=20_000, annual_bonus=0)],
    )

    unemployment = household_monthly_income_profile_at(household, rule, months_from_now=12, as_of=date(2026, 7, 1))
    flexible = household_monthly_income_profile_at(household, rule, months_from_now=30, as_of=date(2026, 7, 1))
    pension = household_monthly_income_profile_at(household, rule, months_from_now=240, as_of=date(2026, 7, 1))

    assert unemployment.non_taxable_income == pytest.approx(2200)
    assert unemployment.gross_income == pytest.approx(2200)
    assert flexible.personal_social == pytest.approx(2180)
    assert flexible.personal_housing_fund == pytest.approx(720)
    assert flexible.monthly_pf_deposit == pytest.approx(720)
    assert flexible.gross_income == pytest.approx(0)
    assert pension.non_taxable_income > 0


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


def test_second_car_down_payment_is_counted_in_current_cash_need() -> None:
    household_without_second = HouseholdData(
        phased_loans=[],
        car_plan=CarPlanData(enabled=False, no_car_monthly_commute_cost=0, vehicle_plans=[]),
    )
    household_with_second = household_without_second.model_copy(
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

    base = calculate_affordability(household_without_second, ScenarioData(), RulePackData())
    with_second = calculate_affordability(household_with_second, ScenarioData(), RulePackData())

    assert with_second.total_required_cash - base.total_required_cash == pytest.approx(50_000)


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


def test_car_plan_uses_interest_free_then_low_rate_schedule() -> None:
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
    assert loan.down_payment == 150_000
    assert loan.first_phase_monthly_payment == 2_500
    assert loan.later_phase_monthly_payment > loan.first_phase_monthly_payment
    assert loan.total_interest > 0
    assert loan.monthly_insurance_cost > 0
    assert loan.monthly_energy_cost > 0
    assert loan.monthly_total_ownership_cost > loan.monthly_cash_operating_cost


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
                    name="样例阶段性贷款",
                    principal=120_000,
                    annual_rate=0.028,
                    remaining_months=120,
                    interest_start_month="2026-07",
                    interest_only_until="2028-07",
                )
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
    assert rows[0].existing_loan_balance == pytest.approx(120_000)
    assert rows[0].existing_monthly_payment > 1_000
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
    assert cashflow_car_row.transaction_cash_out >= result.car_loan.down_payment
    assert cashflow_car_row.vehicle_down_payment == pytest.approx(result.car_loan.down_payment)
    assert cashflow_car_row.first_vehicle_down_payment == pytest.approx(result.car_loan.down_payment)
    assert cashflow_car_row.vehicle_asset_value == pytest.approx(result.car_loan.total_price)
    assert cashflow_car_row.first_vehicle_asset_value == pytest.approx(result.car_loan.total_price)
    assert any(
        entry.category == "vehicle_down_payment" and entry.amount == pytest.approx(-result.car_loan.down_payment)
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
        loan_years=20,
        deed_tax_rate=0,
        broker_fee_rate=0,
        renovation_cost=0,
        moving_and_misc_cost=0,
    )
    prepay_scenario = base_scenario.model_copy(
        update={
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
            cash_account_balance=200_000,
            monthly_expense=18_000,
            car_plan=CarPlanData(enabled=True, total_price=300_000, down_payment_ratio=0.5),
        ),
        ScenarioData(),
        RulePackData(),
    )
    plans = {item.strategy_key: item for item in result.car_plan_analyses}

    assert list(plans) == ["target", "cash", "high_down_low_loan", "low_down_keep_cash", "accelerated_principal", "delay_purchase"]
    assert plans["target"].total_price == 300_000
    assert plans["target"].down_payment_ratio == 0.5
    assert plans["cash"].loan_principal == 0
    assert plans["high_down_low_loan"].down_payment > plans["low_down_keep_cash"].down_payment
    assert plans["low_down_keep_cash"].loan_principal > plans["high_down_low_loan"].loan_principal
    assert plans["accelerated_principal"].prepayment_enabled
    assert plans["accelerated_principal"].interest_saved_by_prepayment >= 0
    assert plans["delay_purchase"].purchase_delay_months >= 12
    assert plans["high_down_low_loan"].total_months == 36
    assert plans["low_down_keep_cash"].down_payment_ratio <= 0.20
    assert plans["low_down_keep_cash"].total_months == 60
    assert all(0 <= item.happiness_score <= 10 for item in plans.values())
    assert len({item.happiness_score for item in plans.values()}) > 1


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
    compact_target = next(item for item in strategies if item.vehicle_candidate_name == "compact ev" and item.strategy_key == "target")
    large_target = next(item for item in strategies if item.vehicle_candidate_name == "large ev" and item.strategy_key == "target")
    assert compact_target.total_price == 180_000
    assert large_target.total_price == 320_000
    assert compact_target.variant == "compact ev | target"


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


def test_manual_car_target_strategy_reflects_user_inputs() -> None:
    result = calculate_affordability(
        HouseholdData(
            cash_account_balance=200_000,
            car_plan=CarPlanData(
                enabled=True,
                total_price=420_000,
                down_payment_ratio=0.35,
                total_months=72,
                interest_free_months=12,
                later_annual_rate=0.026,
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


def test_second_home_provident_plan_uses_30_percent_minimum_down_payment() -> None:
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
    assert all(item.minimum_down_payment >= scenario.total_price * 0.30 for item in provident_plans)


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
        scenario.provident_rate,
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
    result = calculate_affordability(household, scenario, RulePackData())
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


def test_provident_offset_only_relieves_provident_loan_cash_payment() -> None:
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
    assert loan_row.provident_monthly_payment_relief == pytest.approx(
        min(offset_row.loan_offset_payment, loan_row.provident_monthly_payment)
    )
    assert loan_row.cash_monthly_payment >= loan_row.commercial_monthly_payment
    assert cashflow_row.house_payment == pytest.approx(loan_row.commercial_monthly_payment)
    assert cashflow_row.provident_house_offset_payment == pytest.approx(offset_row.loan_offset_payment)
    assert cashflow_row.provident_house_payment_relief == pytest.approx(loan_row.provident_monthly_payment_relief)


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
            "provident_post_purchase_withdrawal_mode": "loan_offset",
        }
    )
    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]

    assert plan.monthly_post_purchase_pf_withdrawal == pytest.approx(round(plan.provident_monthly_payment / 6, 2))
    assert plan.monthly_post_purchase_pf_withdrawal < plan.provident_monthly_payment
    assert "公积金贷款冲还贷" in "；".join(plan.provident_extraction_notes)


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
    birth_month = f"{retirement_month.year - 50}-{retirement_month.month:02d}"
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
    assert any(event.month >= 122 and event.title == "退休后长期观察窗口" for event in events)


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
    cash_relief = min(offset_point.loan_offset_payment, loan_point.provident_monthly_payment)
    assert loan_point.provident_monthly_payment_relief == pytest.approx(cash_relief)
    assert loan_point.cash_monthly_payment == pytest.approx(loan_point.total_monthly_payment - cash_relief)
    assert cashflow_point.provident_house_offset_payment == pytest.approx(offset_point.loan_offset_payment)
    assert cashflow_point.provident_house_payment_relief == pytest.approx(cash_relief)
    assert cashflow_point.house_payment == pytest.approx(
        max(0, cashflow_point.house_contract_payment - cash_relief)
    )


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
        assert {item["name"] for item in plan.happiness_breakdown} >= {
            "交易当下现金安全",
            "买后现金流",
            "商贷与利息压力",
        }


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
