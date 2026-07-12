from datetime import date

import pytest

from app.domain.personal_pension import (
    personal_pension_annual_return_for_month,
    project_personal_pension_month,
)
from app.domain.personal_pension_returns import (
    build_personal_pension_return_snapshot,
    extract_observed_returns,
)
from app.schemas import HouseholdData, IncomeMember, PersonalPensionReturnEvidenceData, RulePackData, ScenarioData
from app.tax_engine import build_tax_strategy_items, member_monthly_income_profiles_at, optimize_personal_pension_strategies


BASE_MONTH = date(2026, 7, 1)


def test_personal_pension_suspends_contribution_when_cash_reserve_is_insufficient() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        personal_pension_cash_reserve_months=6,
        personal_pension_auto_suspend_for_cash_safety=True,
    )

    result = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=1,
        balance_start=10_000,
        planned_contribution=1_000,
        planned_tax_saving=180,
        cash_balance=20_000,
        household_monthly_expense=5_000,
    )

    assert result.cash_contribution == 0
    assert result.suspended_contribution == 1_000
    assert result.lost_tax_saving == 180


def test_personal_pension_contributes_when_cash_reserve_is_sufficient() -> None:
    member = IncomeMember(name="样例成员A", birth_month="1996-01")

    result = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=1,
        balance_start=10_000,
        planned_contribution=1_000,
        planned_tax_saving=180,
        cash_balance=50_000,
        household_monthly_expense=5_000,
    )

    assert result.cash_contribution == 1_000
    assert result.suspended_contribution == 0
    assert result.lost_tax_saving == 0
    assert result.balance_end > 11_000


def test_personal_pension_monthly_annuity_releases_locked_balance_after_retirement() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1960-01",
        personal_pension_account_balance=120_000,
        personal_pension_withdrawal_mode="monthly_annuity",
        personal_pension_withdrawal_years=10,
        personal_pension_return_mode="manual",
        personal_pension_annual_return=0,
    )

    result = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=0,
        balance_start=120_000,
        planned_contribution=1_000,
        planned_tax_saving=180,
        cash_balance=0,
        household_monthly_expense=5_000,
    )

    assert result.cash_contribution == 0
    assert result.gross_withdrawal == pytest.approx(1_000)
    assert result.withdrawal_tax == pytest.approx(30)
    assert result.net_withdrawal == pytest.approx(970)
    assert result.balance_end == pytest.approx(119_000)


def test_personal_pension_auto_safe_withdrawal_can_restore_cash_reserve_without_overdrawing() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1960-01",
        personal_pension_withdrawal_mode="auto_safe",
        personal_pension_withdrawal_years=20,
        personal_pension_cash_reserve_months=6,
        personal_pension_return_mode="manual",
        personal_pension_annual_return=0,
    )

    result = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=0,
        balance_start=20_000,
        planned_contribution=0,
        planned_tax_saving=0,
        cash_balance=0,
        household_monthly_expense=5_000,
    )

    assert result.gross_withdrawal == 20_000
    assert result.net_withdrawal == 19_400
    assert result.balance_end == 0


def test_personal_pension_lifecycle_return_glides_down_before_retirement() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1976-07",
        retirement_category="male_60",
        personal_pension_return_mode="auto_lifecycle",
        personal_pension_annual_return=0.06,
        personal_pension_post_retirement_annual_return=0.02,
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "personal_pension_auto_pre_retirement_return": 0.06,
            "personal_pension_auto_post_retirement_return": 0.02,
        }
    )

    far_from_retirement = personal_pension_annual_return_for_month(
        member, 0, rules, base_month=BASE_MONTH, months_from_now=0
    )
    near_retirement = personal_pension_annual_return_for_month(
        member, 0, rules, base_month=BASE_MONTH, months_from_now=100
    )

    assert far_from_retirement == pytest.approx(0.06)
    assert 0.02 <= near_retirement < far_from_retirement


def test_personal_pension_return_parser_requires_return_context() -> None:
    values = extract_observed_returns("个人养老金税率3%，某产品近一年年化收益率 4.25%，缴费上限12000元")

    assert values == [pytest.approx(0.0425)]


def test_personal_pension_return_snapshot_smooths_short_term_market_change() -> None:
    previous = build_personal_pension_return_snapshot([], today=date(2026, 6, 1))
    evidence = [
        {
            "source_name": "示例指数",
            "source_url": "https://example.com/index",
            "source_type": "index_provider",
            "product_type": "fund",
            "fetched_at": "2026-07-01",
            "observed_annual_return": 0.18,
            "sample_count": 10,
            "status": "parsed",
        }
    ]
    snapshot = build_personal_pension_return_snapshot(
        [PersonalPensionReturnEvidenceData.model_validate(item) for item in evidence],
        today=date(2026, 7, 1),
        previous=previous,
    )

    assert snapshot.pre_retirement_annual_return <= previous.pre_retirement_annual_return + 0.005
    assert snapshot.post_retirement_annual_return <= previous.post_retirement_annual_return + 0.003
    assert snapshot.optimistic_annual_return <= 0.08
    same_day = build_personal_pension_return_snapshot(
        [PersonalPensionReturnEvidenceData.model_validate(item) for item in evidence],
        today=date(2026, 7, 1),
        previous=snapshot,
    )
    assert same_day.pre_retirement_annual_return == snapshot.pre_retirement_annual_return


def test_auto_personal_pension_strategy_is_really_suspended_after_risk_counterfactual() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        pension_account_enabled=True,
        personal_pension_account_enabled=True,
        personal_pension_participation_eligible=True,
        personal_pension_open_mode="auto_tax_optimal",
        personal_pension_contribution_mode="auto_tax_optimal",
        personal_pension_return_mode="auto_lifecycle",
    )
    rules = RulePackData(
        params={
            **RulePackData().params,
            "personal_pension_auto_pre_retirement_return": 0.03,
            "personal_pension_auto_post_retirement_return": 0.018,
        }
    )

    items = build_tax_strategy_items(
        HouseholdData(members=[member]),
        ScenarioData(total_price=0),
        rules,
        base_date=BASE_MONTH,
        auto_suspended_personal_pension_member_indexes={0},
        personal_pension_original_insolvency_month=324,
    )

    item = next(item for item in items if item.deduction_type == "personal_pension")
    assert item.status == "conflict"
    assert item.cash_contribution == 0
    assert item.annual_amount == 0
    assert item.monthly_amount == 0
    assert item.estimated_tax_saving == 0
    assert item.start_month == ""
    assert item.account_return_rate == pytest.approx(0.03)
    assert item.post_retirement_return_rate == pytest.approx(0.018)
    assert "不建议为了税优专门开户并缴费" in item.recommended_action


def test_suspended_personal_pension_keeps_existing_account_balance_for_retirement_projection() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        pension_account_enabled=True,
        personal_pension_account_enabled=True,
        personal_pension_participation_eligible=True,
        personal_pension_account_balance=50_000,
        personal_pension_open_mode="auto_tax_optimal",
        personal_pension_contribution_mode="auto_tax_optimal",
    )

    items = build_tax_strategy_items(
        HouseholdData(members=[member]),
        ScenarioData(total_price=0),
        RulePackData(),
        base_date=BASE_MONTH,
        auto_suspended_personal_pension_member_indexes={0},
        personal_pension_original_insolvency_month=120,
    )

    item = next(item for item in items if item.deduction_type == "personal_pension")
    assert item.status == "conflict"
    assert item.estimated_retirement_balance > member.personal_pension_account_balance
    assert "保留已开户账户和既有余额" in item.recommended_action


def test_auto_optimizer_rejects_personal_pension_when_tax_saving_cannot_cover_investment_opportunity() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        pension_account_enabled=True,
        personal_pension_account_enabled=True,
        personal_pension_participation_eligible=True,
        personal_pension_open_mode="auto_tax_optimal",
        personal_pension_contribution_mode="auto_tax_optimal",
        monthly_salary_gross=0,
    )

    optimized, decisions = optimize_personal_pension_strategies(
        HouseholdData(members=[member]),
        ScenarioData(total_price=0, annual_investment_return=0.08),
        RulePackData(),
        base_date=BASE_MONTH,
    )

    assert decisions[0].should_open is False
    assert optimized.members[0].personal_pension_contribution_mode == "none"
    assert decisions[0].full_cap_annual_tax_saving == 0
    assert decisions[0].full_cap_net_advantage_at_withdrawal < 0


def test_auto_optimizer_controls_open_month_amount_and_ledger_contribution_schedule() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        pension_account_enabled=True,
        personal_pension_account_enabled=True,
        personal_pension_participation_eligible=True,
        personal_pension_open_mode="auto_tax_optimal",
        personal_pension_contribution_mode="auto_tax_optimal",
        monthly_salary_gross=50_000,
    )

    optimized, decisions = optimize_personal_pension_strategies(
        HouseholdData(members=[member]),
        ScenarioData(total_price=0, annual_investment_return=0),
        RulePackData(),
        base_date=BASE_MONTH,
    )

    decision = decisions[0]
    optimized_member = optimized.members[0]
    assert decision.should_open is True
    assert decision.open_month
    assert decision.annual_schedule
    assert decision.net_advantage_at_withdrawal > 0
    assert optimized_member.personal_pension_auto_annual_contribution_schedule == decision.annual_schedule
    first_year = int(next(iter(decision.annual_schedule)))
    first_month = date(first_year, 1, 1) if first_year > BASE_MONTH.year else BASE_MONTH
    month_offset = (first_month.year - BASE_MONTH.year) * 12 + first_month.month - BASE_MONTH.month
    profile = member_monthly_income_profiles_at(
        optimized,
        RulePackData(),
        month_offset,
        as_of=BASE_MONTH,
    )[0][2]
    assert profile.personal_pension_contribution > 0
    assert profile.personal_pension_contribution <= decision.annual_schedule[str(first_year)]


def test_legal_early_withdrawal_requires_an_explicit_statutory_reason() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        personal_pension_early_withdrawal_reason="long_unemployment",
        personal_pension_early_withdrawal_month="2026-08",
        personal_pension_withdrawal_mode="lump_sum",
        personal_pension_return_mode="manual",
        personal_pension_annual_return=0,
    )

    result = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=1,
        balance_start=12_000,
        planned_contribution=0,
        planned_tax_saving=0,
        cash_balance=0,
        household_monthly_expense=5_000,
    )

    assert result.gross_withdrawal == 12_000
    assert result.net_withdrawal == 11_640


def test_cash_shortage_alone_cannot_trigger_early_withdrawal() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1996-01",
        personal_pension_early_withdrawal_reason="none",
        personal_pension_early_withdrawal_month="2026-08",
        personal_pension_withdrawal_mode="auto_safe",
        personal_pension_return_mode="manual",
        personal_pension_annual_return=0,
    )

    result = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=1,
        balance_start=12_000,
        planned_contribution=0,
        planned_tax_saving=0,
        cash_balance=-50_000,
        household_monthly_expense=5_000,
    )

    assert result.gross_withdrawal == 0
    assert result.balance_end == 12_000


def test_product_liquidity_delay_ratio_and_fee_limit_withdrawal() -> None:
    member = IncomeMember(
        name="样例成员A",
        birth_month="1960-01",
        personal_pension_withdrawal_mode="lump_sum",
        personal_pension_return_mode="manual",
        personal_pension_annual_return=0,
        personal_pension_product_liquidity_mode="periodic",
        personal_pension_redemption_delay_months=2,
        personal_pension_monthly_redeemable_ratio=0.25,
        personal_pension_redemption_fee_rate=0.02,
    )

    before_payout = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=1,
        balance_start=40_000,
        planned_contribution=0,
        planned_tax_saving=0,
        cash_balance=0,
        household_monthly_expense=5_000,
    )
    payout = project_personal_pension_month(
        member,
        0,
        RulePackData(),
        base_month=BASE_MONTH,
        months_from_now=2,
        balance_start=40_000,
        planned_contribution=0,
        planned_tax_saving=0,
        cash_balance=0,
        household_monthly_expense=5_000,
    )

    assert before_payout.gross_withdrawal == 0
    assert payout.gross_withdrawal == 10_000
    assert payout.redemption_fee == 200
    assert payout.withdrawal_tax == 294
    assert payout.net_withdrawal == 9_506
    assert payout.balance_end == 30_000
