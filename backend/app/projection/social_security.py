from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ..domain.career import member_retirement_months_by_index
from ..domain.expenses import scheduled_expense_occurs_in_month
from ..domain.tax import ContributionDetails, beijing_contribution_details, income_stage_for_month
from ..domain.time import month_after, month_distance, parse_year_month
from ..policies import SocialSecurityAccountPolicy, get_policy
from ..schemas import (
    HouseholdData,
    IncomeMember,
    PurchasePlanAnalysis,
    RulePackData,
    SocialSecurityMemberAccountPoint,
    SocialSecurityVisualizationPoint,
)


class MemberIncomeProfileLike(Protocol):
    monthly_pf_deposit: float


MemberIncomeProvider = Callable[[int], dict[int, MemberIncomeProfileLike]]


@dataclass
class SocialSecurityMemberAccountState:
    member_index: int
    member_name: str
    pension_enabled: bool
    medical_enabled: bool
    pension_open_month: str
    medical_open_month: str
    pension_balance: float
    medical_balance: float
    pension_account_payout_monthly: float = 0.0


def initial_social_security_member_accounts(household: HouseholdData) -> list[SocialSecurityMemberAccountState]:
    return [
        SocialSecurityMemberAccountState(
            member_index=index,
            member_name=member.name,
            pension_enabled=bool(getattr(member, "pension_account_enabled", True)),
            medical_enabled=bool(getattr(member, "medical_account_enabled", True)),
            pension_open_month=getattr(member, "pension_account_open_month", "") or getattr(member, "family_join_month", ""),
            medical_open_month=getattr(member, "medical_account_open_month", "") or getattr(member, "family_join_month", ""),
            pension_balance=(
                max(0.0, member.pension_account_balance)
                if bool(getattr(member, "pension_account_enabled", True))
                else 0.0
            ),
            medical_balance=(
                max(0.0, member.medical_account_balance)
                if bool(getattr(member, "medical_account_enabled", True))
                else 0.0
            ),
        )
        for index, member in enumerate(household.members)
    ]


def account_open_in_month(open_month: object, target_month: date) -> bool:
    parsed = parse_year_month(str(open_month or ""))
    if parsed is None:
        return True
    return month_distance(parsed, (target_month.year, target_month.month)) >= 0


def age_at_month(member: IncomeMember, target_month: date) -> int | None:
    birth = parse_year_month(member.birth_month)
    if birth is None:
        return None
    age = target_month.year - birth[0]
    if target_month.month < birth[1]:
        age -= 1
    return max(0, age)


def pension_account_months_for_member(member: IncomeMember, policy: SocialSecurityAccountPolicy) -> int:
    category = str(getattr(member, "retirement_category", "") or "")
    return policy.pension_account_months_for_category(category)


def scheduled_medical_account_payable_expense_at(household: HouseholdData, target_month: tuple[int, int]) -> float:
    total = 0.0
    for item in household.scheduled_expenses:
        if bool(getattr(item, "medical_account_payable", False)) and scheduled_expense_occurs_in_month(item, target_month):
            total += max(0.0, float(item.monthly_amount))
    return total


def social_security_member_points(rows: list[dict[str, float | int | str | bool]]) -> list[SocialSecurityMemberAccountPoint]:
    points: list[SocialSecurityMemberAccountPoint] = []
    for row in rows:
        points.append(
            SocialSecurityMemberAccountPoint(
                member_index=int(row["member_index"]),
                member_name=str(row["member_name"]),
                pension_balance_start=round(float(row["pension_balance_start"]), 2),
                pension_contribution=round(float(row["pension_contribution"]), 2),
                pension_account_payout=round(float(row["pension_account_payout"]), 2),
                pension_interest=round(float(row["pension_interest"]), 2),
                pension_balance_end=round(float(row["pension_balance_end"]), 2),
                medical_balance_start=round(float(row["medical_balance_start"]), 2),
                medical_contribution=round(float(row["medical_contribution"]), 2),
                medical_retiree_transfer=round(float(row["medical_retiree_transfer"]), 2),
                medical_interest=round(float(row["medical_interest"]), 2),
                medical_healthcare_outflow=round(float(row["medical_healthcare_outflow"]), 2),
                medical_mutual_aid_outflow=round(float(row["medical_mutual_aid_outflow"]), 2),
                medical_outflow=round(float(row["medical_outflow"]), 2),
                medical_balance_end=round(float(row["medical_balance_end"]), 2),
                retired=bool(row["retired"]),
            )
        )
    return points


def build_social_security_projection(
    household: HouseholdData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    *,
    horizon_months: int,
    member_income_at_month: MemberIncomeProvider,
    as_of: date | None = None,
) -> list[SocialSecurityVisualizationPoint]:
    if not household.members or not purchase_plans:
        return []

    account_policy = get_policy(rules).social_security_account_policy()
    base = as_of or date.today()
    base_month = date(base.year, base.month, 1)
    retirement_months_by_member = member_retirement_months_by_index(household, as_of=base_month, rules=rules)

    rows: list[SocialSecurityVisualizationPoint] = []
    for plan in purchase_plans:
        account_states = initial_social_security_member_accounts(household)
        for month in range(horizon_months + 1):
            target_year, target_month_number = month_after(base_month, month)
            target_month = date(target_year, target_month_number, 1)
            medical_expense_remaining = scheduled_medical_account_payable_expense_at(
                household,
                (target_year, target_month_number),
            )
            profiles = member_income_at_month(month)
            account_rows: list[dict[str, float | int | str | bool]] = []
            for account in account_states:
                member_index = account.member_index
                member = household.members[member_index]
                profile = profiles.get(member_index)
                retirement_month = retirement_months_by_member.get(member_index, 999999)
                retired = month >= retirement_month
                pension_enabled = account.pension_enabled and account_open_in_month(account.pension_open_month, target_month)
                medical_enabled = account.medical_enabled and account_open_in_month(account.medical_open_month, target_month)
                pension_start = float(account.pension_balance)
                medical_start = float(account.medical_balance)
                pension_contribution = 0.0
                pension_account_payout = 0.0
                medical_contribution = 0.0
                medical_retiree_transfer = 0.0
                medical_healthcare_outflow = 0.0
                medical_mutual_aid_outflow = 0.0
                medical_outflow = 0.0
                if month > 0 and profile and not retired:
                    stage = income_stage_for_month(member, target_month.year, target_month.month)
                    details = beijing_contribution_details(stage, rules) if stage else ContributionDetails(0, 0, 0, 0, 0, 0, 0, 0, 0)
                    pension_contribution = details.employee_pension if pension_enabled else 0.0
                    medical_contribution = (
                        details.social_base * account_policy.medical_account_employee_transfer_rate
                        if medical_enabled
                        else 0.0
                    )
                elif month > 0 and retired:
                    if pension_enabled:
                        payout_monthly = account.pension_account_payout_monthly
                        if payout_monthly <= 0 and pension_start > 0:
                            payout_months = pension_account_months_for_member(member, account_policy)
                            payout_monthly = pension_start / payout_months
                            account.pension_account_payout_monthly = payout_monthly
                        pension_account_payout = min(pension_start, payout_monthly)
                    if medical_enabled:
                        age = age_at_month(member, target_month)
                        medical_retiree_transfer = (
                            account_policy.medical_account_retiree_monthly_transfer_70_plus
                            if age is not None and age >= 70
                            else account_policy.medical_account_retiree_monthly_transfer_under_70
                        )
                        medical_mutual_aid_outflow = min(
                            medical_start + medical_retiree_transfer,
                            account_policy.medical_account_retiree_large_mutual_aid_monthly,
                        )
                if month > 0 and medical_enabled and medical_expense_remaining > 0:
                    medical_available_for_healthcare = max(
                        0.0,
                        medical_start
                        + medical_contribution
                        + medical_retiree_transfer
                        - medical_mutual_aid_outflow,
                    )
                    medical_healthcare_outflow = min(
                        medical_available_for_healthcare,
                        medical_expense_remaining,
                    )
                    medical_expense_remaining = max(0.0, medical_expense_remaining - medical_healthcare_outflow)
                medical_outflow = medical_healthcare_outflow + medical_mutual_aid_outflow
                pension_rate = account_policy.pension_credit_rate_for_year(target_month.year)
                medical_rate = account_policy.medical_credit_rate_for_year(target_month.year)
                pension_interest = (
                    max(0.0, pension_start + pension_contribution - pension_account_payout) * pension_rate
                    if month > 0 and pension_enabled and target_month.month == account_policy.pension_account_interest_credit_month
                    else 0.0
                )
                medical_interest = (
                    max(
                        0.0,
                        medical_start
                        + medical_contribution
                        + medical_retiree_transfer
                        - medical_outflow,
                    )
                    * medical_rate
                    / 4
                    if month > 0 and medical_enabled and target_month.month in account_policy.medical_account_interest_credit_months
                    else 0.0
                )
                pension_end = max(0.0, pension_start + pension_contribution - pension_account_payout + pension_interest)
                medical_end = max(0.0, medical_start + medical_contribution + medical_retiree_transfer - medical_outflow + medical_interest)
                account_rows.append(
                    {
                        "member_index": member_index,
                        "member_name": account.member_name,
                        "pension_balance_start": pension_start,
                        "pension_contribution": pension_contribution,
                        "pension_account_payout": pension_account_payout,
                        "pension_interest": pension_interest,
                        "pension_balance_end": pension_end,
                        "medical_balance_start": medical_start,
                        "medical_contribution": medical_contribution,
                        "medical_retiree_transfer": medical_retiree_transfer,
                        "medical_interest": medical_interest,
                        "medical_healthcare_outflow": medical_healthcare_outflow,
                        "medical_mutual_aid_outflow": medical_mutual_aid_outflow,
                        "medical_outflow": medical_outflow,
                        "medical_balance_end": medical_end,
                        "retired": retired,
                    }
                )

            for index, account in enumerate(account_states):
                account.pension_balance = float(account_rows[index]["pension_balance_end"])
                account.medical_balance = float(account_rows[index]["medical_balance_end"])

            member_accounts = social_security_member_points(account_rows)
            pension_balance_start = sum(item.pension_balance_start for item in member_accounts)
            pension_contribution = sum(item.pension_contribution for item in member_accounts)
            pension_account_payout = sum(item.pension_account_payout for item in member_accounts)
            pension_interest = sum(item.pension_interest for item in member_accounts)
            pension_balance_end = sum(item.pension_balance_end for item in member_accounts)
            medical_balance_start = sum(item.medical_balance_start for item in member_accounts)
            medical_contribution = sum(item.medical_contribution for item in member_accounts)
            medical_retiree_transfer = sum(item.medical_retiree_transfer for item in member_accounts)
            medical_interest = sum(item.medical_interest for item in member_accounts)
            medical_healthcare_outflow = sum(item.medical_healthcare_outflow for item in member_accounts)
            medical_mutual_aid_outflow = sum(item.medical_mutual_aid_outflow for item in member_accounts)
            medical_outflow = sum(item.medical_outflow for item in member_accounts)
            medical_balance_end = sum(item.medical_balance_end for item in member_accounts)
            rows.append(
                SocialSecurityVisualizationPoint(
                    plan_variant=plan.variant,
                    month=month,
                    pension_balance_start=round(pension_balance_start, 2),
                    pension_contribution=round(pension_contribution, 2),
                    pension_account_payout=round(pension_account_payout, 2),
                    pension_interest=round(pension_interest, 2),
                    pension_balance_end=round(pension_balance_end, 2),
                    medical_balance_start=round(medical_balance_start, 2),
                    medical_contribution=round(medical_contribution, 2),
                    medical_retiree_transfer=round(medical_retiree_transfer, 2),
                    medical_interest=round(medical_interest, 2),
                    medical_healthcare_outflow=round(medical_healthcare_outflow, 2),
                    medical_mutual_aid_outflow=round(medical_mutual_aid_outflow, 2),
                    medical_outflow=round(medical_outflow, 2),
                    medical_balance_end=round(medical_balance_end, 2),
                    total_balance_end=round(pension_balance_end + medical_balance_end, 2),
                    member_accounts=member_accounts,
                )
            )
    return rows
