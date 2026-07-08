from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ..schemas import (
    HouseholdData,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
    SocialSecurityVisualizationPoint,
)
from .context import MemberIncomeProjectionContext, MemberIncomeRowsProvider
from .provident import (
    build_provident_projection,
    initial_provident_member_accounts,
)
from .social_security import build_social_security_projection


def initial_provident_member_account_rows(
    household: HouseholdData,
    rules: RulePackData,
    *,
    income_rows_provider: MemberIncomeRowsProvider,
    as_of: date | None = None,
) -> list[dict[str, float | int | str | bool]]:
    base = as_of or date.today()
    income_context = MemberIncomeProjectionContext(
        household=household,
        rules=rules,
        base_month=date(base.year, base.month, 1),
        rows_provider=income_rows_provider,
    )
    return [
        {
            "member_index": account.member_index,
            "member_name": account.member_name,
            "balance": account.balance,
            "enabled": account.enabled,
            "open_month": account.open_month,
        }
        for account in initial_provident_member_accounts(household, income_context.rows_at_month)
    ]


def household_initial_provident_balance(
    household: HouseholdData,
    rules: RulePackData,
    *,
    income_rows_provider: MemberIncomeRowsProvider,
    as_of: date | None = None,
) -> float:
    return sum(
        float(account["balance"])
        for account in initial_provident_member_account_rows(
            household,
            rules,
            income_rows_provider=income_rows_provider,
            as_of=as_of,
        )
    )


def build_social_security_account_projection(
    household: HouseholdData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    *,
    horizon_months: int,
    income_rows_provider: MemberIncomeRowsProvider,
    as_of: date | None = None,
) -> list[SocialSecurityVisualizationPoint]:
    base = as_of or date.today()
    base_month = date(base.year, base.month, 1)
    income_context = MemberIncomeProjectionContext(
        household=household,
        rules=rules,
        base_month=base_month,
        rows_provider=income_rows_provider,
    )
    return build_social_security_projection(
        household,
        rules,
        purchase_plans,
        horizon_months=horizon_months,
        member_income_at_month=income_context.profiles_by_member_at,
        as_of=base_month,
    )


def build_provident_account_projection(
    household: HouseholdData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    *,
    horizon_months: int,
    income_rows_provider: MemberIncomeRowsProvider,
    retirement_months_by_member: dict[int, int],
    rent_withdrawal_at_month: Callable[[HouseholdData, int], float],
    is_offset_month: Callable[[int], bool],
    strategy_active_mode: Callable[[str, int, int], str],
    as_of: date | None = None,
) -> list[ProvidentVisualizationPoint]:
    base = as_of or date.today()
    base_month = date(base.year, base.month, 1)
    income_context = MemberIncomeProjectionContext(
        household=household,
        rules=rules,
        base_month=base_month,
        rows_provider=income_rows_provider,
    )
    return build_provident_projection(
        household,
        rules,
        purchase_plans,
        horizon_months=horizon_months,
        member_income_at_month=income_context.rows_at_month,
        retirement_months_by_member=retirement_months_by_member,
        rent_withdrawal_at_month=rent_withdrawal_at_month,
        is_offset_month=is_offset_month,
        strategy_active_mode=strategy_active_mode,
        as_of=base_month,
    )
