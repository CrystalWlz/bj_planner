import pytest
from datetime import date
from pydantic import ValidationError

from app.calculator import (
    _quarterly_rent_withdrawal_before_purchase_at,
    calculate_affordability,
    calculate_car_loan,
    calculate_household_tax,
    calculate_loan,
    household_monthly_income_profile_at,
    monthly_household_expense_at,
    summarize_student_loans,
)
from app.schemas import CareerShockData, CarPlanData, ElderlyDependentData, HouseholdData, IncomeMember, IncomeStageData, RulePackData, ScenarioData, ScheduledExpenseData, StudentLoanData


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


def _sample_student_loans() -> list[StudentLoanData]:
    return [
        StudentLoanData(
            borrower="样例成员A",
            name="助学贷款A",
            principal=30_000,
            remaining_months=120,
            interest_start_month="2026-07",
            interest_only_until="2028-07",
        ),
        StudentLoanData(
            borrower="样例成员A",
            name="助学贷款B",
            principal=40_000,
            remaining_months=120,
            interest_start_month="2026-07",
            interest_only_until="2028-06",
        ),
        StudentLoanData(
            borrower="样例成员B",
            name="助学贷款C",
            principal=35_000,
            remaining_months=120,
            interest_start_month="2027-07",
            interest_only_until="2028-07",
        ),
        StudentLoanData(
            borrower="样例成员B",
            name="助学贷款D",
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
    household = HouseholdData(liquid_assets=300_000, monthly_income=50_000)
    scenario = ScenarioData(total_price=6_000_000, down_payment_amount=1_800_000)
    result = calculate_affordability(household, scenario, RulePackData())
    assert result.status == "不可行"
    assert result.funding_gap > 0


def test_affordability_builds_stress_tests() -> None:
    result = calculate_affordability(HouseholdData(), ScenarioData(), RulePackData())
    assert len(result.stress_tests) == 3
    assert {item.name for item in result.stress_tests} == {"利率上行", "收入下降", "房价上行"}


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


def test_annual_bonus_is_paid_in_april_not_spread_monthly() -> None:
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


def test_income_member_defaults_to_one_income_stage() -> None:
    member = IncomeMember(
        monthly_salary_gross=30_000,
        annual_bonus=60_000,
        employment_start_date="2026-07-01",
    )

    assert len(member.income_stages) == 1
    assert member.income_stages[0].monthly_salary_gross == 30_000
    assert member.income_stages[0].annual_bonus == 60_000
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
            layoff_member_name="我",
            layoff_age=31,
            self_birth_month="",
            spouse_birth_month="",
            self_current_age=30,
            spouse_current_age=28,
            unemployment_benefit_months=2,
            unemployment_benefit_monthly=2_000,
            self_social_insurance_monthly=1_800,
            self_retirement_age=50,
            spouse_retirement_age=58,
            self_pension_monthly=6_000,
            spouse_pension_monthly=5_000,
        ),
        members=[
            IncomeMember(name="我", monthly_salary_gross=20_000, annual_bonus=0, monthly_special_additional_deduction=0),
            IncomeMember(name="成员B", monthly_salary_gross=12_000, annual_bonus=0, monthly_special_additional_deduction=0),
        ],
    )

    before_layoff = household_monthly_income_profile_at(household, rule, as_of=date(2026, 7, 1))
    unemployment = household_monthly_income_profile_at(household, rule, months_from_now=12, as_of=date(2026, 7, 1))
    self_social = household_monthly_income_profile_at(household, rule, months_from_now=14, as_of=date(2026, 7, 1))
    pension = household_monthly_income_profile_at(household, rule, months_from_now=240, as_of=date(2026, 7, 1))

    assert unemployment.non_taxable_income == pytest.approx(2_000)
    assert unemployment.net_income < before_layoff.net_income
    assert self_social.extra_cash_expense == pytest.approx(1_800)
    assert pension.non_taxable_income >= 6_000


def test_career_shock_uses_birth_month_for_layoff_timing() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        scheduled_expenses=[],
        career_shock=CareerShockData(
            enabled=True,
            layoff_member_name="样例成员",
            layoff_age=35,
            self_birth_month="1980-01",
            self_current_age=30,
            unemployment_benefit_months=24,
            unemployment_benefit_monthly=2_000,
            self_social_insurance_monthly=1_800,
        ),
        members=[
            IncomeMember(name="样例成员", monthly_salary_gross=20_000, annual_bonus=0, monthly_special_additional_deduction=0),
        ],
    )

    before_35 = household_monthly_income_profile_at(household, rule, months_from_now=101, as_of=date(2006, 7, 1))
    at_35 = household_monthly_income_profile_at(household, rule, months_from_now=102, as_of=date(2006, 7, 1))

    assert before_35.non_taxable_income == 0
    assert at_35.non_taxable_income == pytest.approx(2_000)


def test_purchase_plan_avoids_negative_cash_pool_after_layoff() -> None:
    rule = _zero_contribution_rule()
    household = HouseholdData(
        liquid_assets=900_000,
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
            layoff_member_name="self",
            layoff_age=35,
            self_birth_month="1980-01",
            self_current_age=25,
            unemployment_benefit_months=0,
            unemployment_benefit_monthly=0,
            self_social_insurance_monthly=3_000,
            self_retirement_age=60,
        ),
        members=[
            IncomeMember(
                name="self",
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
        student_loans=[],
        car_plan=CarPlanData(enabled=False, no_car_monthly_commute_cost=0, second_car_enabled=False),
    )
    household_with_second = household_without_second.model_copy(
        update={
            "car_plan": CarPlanData(
                enabled=False,
                no_car_monthly_commute_cost=0,
                second_car_enabled=True,
                second_car_total_price=100_000,
                second_car_down_payment_ratio=0.5,
                second_car_purchase_delay_months=0,
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
        liquid_assets=180_000,
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


def test_student_loans_use_current_interest_only_policy() -> None:
    summaries = summarize_student_loans(_sample_student_loans(), as_of=date(2026, 7, 1))
    monthly_payment = sum(item.current_monthly_payment for item in summaries)

    assert monthly_payment == pytest.approx((30_000 + 40_000) * 0.028 / 12, abs=0.01)
    assert [item.phase for item in summaries] == ["只还利息", "只还利息", "未开始计息", "未开始计息"]


def test_student_loans_switch_to_equal_installment_after_interest_only_period() -> None:
    summaries = summarize_student_loans(
        [
            StudentLoanData(
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


def test_student_loans_can_use_equal_principal_after_interest_only_period() -> None:
    equal_installment = summarize_student_loans(
        [
            StudentLoanData(
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
    equal_principal = summarize_student_loans(
        [
            StudentLoanData(
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
    base = HouseholdData(student_loans=[], car_plan=CarPlanData(enabled=False, no_car_monthly_commute_cost=0))
    with_commute = base.model_copy(
        update={"car_plan": CarPlanData(enabled=False, no_car_monthly_commute_cost=1800)}
    )

    no_commute_result = calculate_affordability(base, ScenarioData(), RulePackData())
    commute_result = calculate_affordability(with_commute, ScenarioData(), RulePackData())

    assert commute_result.post_purchase_cash_flow == pytest.approx(no_commute_result.post_purchase_cash_flow - 1800)


def test_affordability_counts_student_loans_as_effective_debt() -> None:
    household_without_loans = HouseholdData(student_loans=[], monthly_debt_payment=1_000)
    household_with_loans = household_without_loans.model_copy(update={"student_loans": _sample_student_loans()[:1]})
    without_student_loans = calculate_affordability(
        household_without_loans,
        ScenarioData(),
        RulePackData(),
    )
    with_student_loans = calculate_affordability(household_with_loans, ScenarioData(), RulePackData())

    assert with_student_loans.student_loan_monthly_payment > 0
    assert with_student_loans.effective_monthly_debt_payment == pytest.approx(
        with_student_loans.student_loan_monthly_payment + household_with_loans.monthly_debt_payment
    )
    assert with_student_loans.post_purchase_cash_flow < without_student_loans.post_purchase_cash_flow


def test_affordability_generates_multiple_car_purchase_strategies() -> None:
    result = calculate_affordability(
        HouseholdData(
            liquid_assets=200_000,
            monthly_expense=18_000,
            car_plan=CarPlanData(enabled=True, total_price=300_000, down_payment_ratio=0.5),
        ),
        ScenarioData(),
        RulePackData(),
    )
    plans = {item.variant: item for item in result.car_plan_analyses}

    assert list(plans) == ["按目标设置", "全款", "高首付低贷", "低首付保现金", "延后买车"]
    assert plans["按目标设置"].total_price == 300_000
    assert plans["按目标设置"].down_payment_ratio == 0.5
    assert plans["全款"].loan_principal == 0
    assert plans["高首付低贷"].down_payment > plans["低首付保现金"].down_payment
    assert plans["低首付保现金"].loan_principal > plans["高首付低贷"].loan_principal
    assert plans["延后买车"].purchase_delay_months >= 12
    assert plans["高首付低贷"].total_months == 36
    assert plans["低首付保现金"].down_payment_ratio <= 0.20
    assert plans["低首付保现金"].total_months == 60
    assert all(0 <= item.happiness_score <= 10 for item in plans.values())
    assert len({item.happiness_score for item in plans.values()}) > 1


def test_manual_car_target_strategy_reflects_user_inputs() -> None:
    result = calculate_affordability(
        HouseholdData(
            liquid_assets=200_000,
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

    manual = {item.variant: item for item in result.car_plan_analyses}["按目标设置"]
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
    assert all(plans[name].provident_loan_amount > 0 for name in ["0商贷", "微量商贷", "较多商贷"])
    assert plans["0商贷"].commercial_loan_amount == 0


def test_provident_loan_cap_uses_150k_per_deposit_year() -> None:
    household = HouseholdData(
        social_security_months=48,
        liquid_assets=4_000_000,
        car_plan=CarPlanData(enabled=False),
    )
    result = calculate_affordability(household, ScenarioData(total_price=3_000_000), RulePackData())

    generated = [item for item in result.purchase_plan_analyses if item.variant != "手动指定"]
    assert {item.provident_loan_amount for item in generated} == {600_000}


def test_purchase_plan_provident_cap_depends_on_plan_purchase_time() -> None:
    household = HouseholdData(
        social_security_months=48,
        liquid_assets=1_300_000,
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
        liquid_assets=1_150_000,
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
        if item.commercial_loan_amount == 0 and item.variant != "鎵嬪姩鎸囧畾"
    )
    micro_plan = positive_commercial[0]

    assert scenario.total_price * 0.02 <= micro_plan.commercial_loan_amount <= scenario.total_price * 0.12
    assert micro_plan.months_to_buy is not None
    assert zero_commercial.months_to_buy is None or micro_plan.months_to_buy <= zero_commercial.months_to_buy


def test_purchase_plan_analysis_has_visualization_ready_cash_flow_fields() -> None:
    household = HouseholdData(
        liquid_assets=2_200_000,
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
        liquid_assets=1_500_000,
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
        liquid_assets=900_000,
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
    assert plan.post_purchase_cash_flow_with_pf_withdrawal == pytest.approx(
        plan.post_purchase_cash_flow + plan.monthly_post_purchase_pf_withdrawal
    )


def test_purchase_agreed_withdrawal_uses_future_monthly_deposit_not_total_payment_cap() -> None:
    household = HouseholdData(
        liquid_assets=2_500_000,
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

    assert plan.monthly_post_purchase_pf_withdrawal == pytest.approx(monthly_pf_deposit)
    assert plan.monthly_post_purchase_pf_withdrawal > plan.total_monthly_payment
    assert "purchase_agreed" in "；".join(plan.provident_extraction_notes)


def test_loan_offset_withdrawal_uses_provident_payment_cap() -> None:
    household = HouseholdData(
        liquid_assets=2_500_000,
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
            "provident_post_purchase_withdrawal_mode": "loan_offset",
        }
    )
    result = calculate_affordability(household, scenario, rules)
    plan = {item.variant: item for item in result.purchase_plan_analyses}["0商贷"]

    assert plan.monthly_post_purchase_pf_withdrawal == pytest.approx(plan.provident_monthly_payment)
    assert "loan_offset" in "；".join(plan.provident_extraction_notes)


def test_existing_home_family_does_not_continue_rent_withdrawal_before_purchase() -> None:
    scenario = ScenarioData(total_price=3_000_000, renovation_cost=0, moving_and_misc_cost=0)
    household_with_home = HouseholdData(
        existing_home_count=1,
        monthly_rent_from_housing_fund=20_000,
        liquid_assets=800_000,
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
        liquid_assets=900_000,
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
        ("liquid_assets", -1),
        ("investments", -1),
        ("required_liquidity_months", 37),
        ("borrower_age", 17),
    ],
)
def test_household_numeric_fields_reject_invalid_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        HouseholdData(**{field: value})
