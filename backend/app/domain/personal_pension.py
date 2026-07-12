from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..policies import get_policy
from ..schemas import IncomeMember, RulePackData
from .career import policy_retirement_age_for_member_with_rules
from .time import month_start_for_birth_month_or_age, months_between_months, parse_year_month


@dataclass(frozen=True)
class PersonalPensionMonthResult:
    cash_contribution: float
    suspended_contribution: float
    lost_tax_saving: float
    investment_return: float
    gross_withdrawal: float
    redemption_fee: float
    withdrawal_tax: float
    net_withdrawal: float
    balance_end: float


def personal_pension_retirement_month(
    member: IncomeMember,
    member_index: int,
    rules: RulePackData,
    *,
    base_month: date,
) -> date:
    retirement_age = policy_retirement_age_for_member_with_rules(member, member_index, rules)
    return month_start_for_birth_month_or_age(
        base_month,
        member.birth_month,
        member.current_age,
        retirement_age,
    )


def personal_pension_withdrawal_start_month(
    member: IncomeMember,
    member_index: int,
    rules: RulePackData,
    *,
    base_month: date,
) -> date:
    retirement_month = personal_pension_retirement_month(member, member_index, rules, base_month=base_month)
    if member.personal_pension_early_withdrawal_reason != "none":
        early = parse_year_month(member.personal_pension_early_withdrawal_month)
        if early is not None:
            return date(early[0], early[1], 1)
    configured = parse_year_month(member.personal_pension_withdrawal_start_month)
    if configured is None:
        return retirement_month
    configured_month = date(configured[0], configured[1], 1)
    return max(retirement_month, configured_month)


def personal_pension_annual_return_for_month(
    member: IncomeMember,
    member_index: int,
    rules: RulePackData,
    *,
    base_month: date,
    months_from_now: int,
) -> float:
    pre_retirement_return = max(-0.95, member.personal_pension_annual_return)
    if member.personal_pension_return_mode == "manual":
        return pre_retirement_return
    return_policy = get_policy(rules).personal_pension_return_policy()
    pre_retirement_return = max(-0.95, return_policy.pre_retirement_annual_return)
    post_retirement_return = max(-0.95, return_policy.post_retirement_annual_return)
    retirement_month = personal_pension_retirement_month(member, member_index, rules, base_month=base_month)
    months_to_retirement = months_between_months(base_month, retirement_month) - months_from_now
    if months_to_retirement <= 0:
        return post_retirement_return
    if months_to_retirement >= 120:
        return pre_retirement_return
    pre_weight = months_to_retirement / 120
    return post_retirement_return + (pre_retirement_return - post_retirement_return) * pre_weight


def project_personal_pension_month(
    member: IncomeMember,
    member_index: int,
    rules: RulePackData,
    *,
    base_month: date,
    months_from_now: int,
    balance_start: float,
    planned_contribution: float,
    planned_tax_saving: float,
    cash_balance: float,
    household_monthly_expense: float,
) -> PersonalPensionMonthResult:
    balance = max(0.0, balance_start)
    withdrawal_start = personal_pension_withdrawal_start_month(
        member,
        member_index,
        rules,
        base_month=base_month,
    )
    withdrawal_start_offset = max(0, months_between_months(base_month, withdrawal_start))
    redemption_delay = (
        0
        if member.personal_pension_product_liquidity_mode == "daily_liquid"
        else member.personal_pension_redemption_delay_months
    )
    payout_start_offset = withdrawal_start_offset + redemption_delay
    before_withdrawal = months_from_now < withdrawal_start_offset
    contribution = max(0.0, planned_contribution) if before_withdrawal else 0.0
    suspended = 0.0
    lost_tax_saving = 0.0
    if (
        contribution > 0
        and member.personal_pension_auto_suspend_for_cash_safety
        and cash_balance < household_monthly_expense * member.personal_pension_cash_reserve_months
    ):
        suspended = contribution
        contribution = 0.0
        lost_tax_saving = max(0.0, planned_tax_saving)

    annual_return = personal_pension_annual_return_for_month(
        member,
        member_index,
        rules,
        base_month=base_month,
        months_from_now=months_from_now,
    )
    monthly_return = (1 + annual_return) ** (1 / 12) - 1
    investment_return = max(-balance - contribution, (balance + contribution) * monthly_return)
    balance = max(0.0, balance + contribution + investment_return)

    gross_withdrawal = 0.0
    if months_from_now >= payout_start_offset and balance > 0:
        elapsed = months_from_now - payout_start_offset
        mode = member.personal_pension_withdrawal_mode
        if mode == "lump_sum":
            gross_withdrawal = balance
        elif mode == "fixed_monthly":
            gross_withdrawal = min(balance, member.personal_pension_fixed_monthly_withdrawal)
        else:
            total_months = max(12, member.personal_pension_withdrawal_years * 12)
            remaining_months = max(1, total_months - elapsed)
            annuity = balance / remaining_months
            if mode == "auto_safe":
                reserve_target = household_monthly_expense * max(
                    member.personal_pension_cash_reserve_months,
                    6,
                )
                cash_gap = max(0.0, reserve_target - cash_balance)
                withdrawal_tax_rate = get_policy(rules).tax_benefit_policy().personal_pension_withdrawal_tax_rate
                gross_cash_gap = cash_gap / max(0.01, 1 - withdrawal_tax_rate)
                gross_withdrawal = min(balance, max(annuity, gross_cash_gap))
            else:
                gross_withdrawal = min(balance, annuity)

    redeemable_ratio = (
        1.0
        if member.personal_pension_product_liquidity_mode == "daily_liquid"
        else member.personal_pension_monthly_redeemable_ratio
    )
    max_redeemable = balance * redeemable_ratio
    gross_withdrawal = min(gross_withdrawal, max_redeemable)
    redemption_fee = gross_withdrawal * member.personal_pension_redemption_fee_rate
    taxable_withdrawal = max(0.0, gross_withdrawal - redemption_fee)
    withdrawal_tax_rate = get_policy(rules).tax_benefit_policy().personal_pension_withdrawal_tax_rate
    withdrawal_tax = taxable_withdrawal * withdrawal_tax_rate
    net_withdrawal = max(0.0, taxable_withdrawal - withdrawal_tax)
    balance = max(0.0, balance - gross_withdrawal)
    return PersonalPensionMonthResult(
        cash_contribution=round(contribution, 2),
        suspended_contribution=round(suspended, 2),
        lost_tax_saving=round(lost_tax_saving, 2),
        investment_return=round(investment_return, 2),
        gross_withdrawal=round(gross_withdrawal, 2),
        redemption_fee=round(redemption_fee, 2),
        withdrawal_tax=round(withdrawal_tax, 2),
        net_withdrawal=round(net_withdrawal, 2),
        balance_end=round(balance, 2),
    )


__all__ = [
    "PersonalPensionMonthResult",
    "personal_pension_annual_return_for_month",
    "personal_pension_retirement_month",
    "personal_pension_withdrawal_start_month",
    "project_personal_pension_month",
]
