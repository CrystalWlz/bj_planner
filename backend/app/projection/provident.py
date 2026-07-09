from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ..domain.time import month_after, month_distance, parse_year_month
from ..policies import get_policy
from ..schemas import (
    HouseholdData,
    ProvidentMemberAccountPoint,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    RulePackData,
)


class MemberIncomeProfileLike(Protocol):
    personal_housing_fund: float
    employer_housing_fund: float
    monthly_pf_deposit: float


MemberIncomeRowsProvider = Callable[[int], Sequence[tuple[int, str, MemberIncomeProfileLike]]]
RentWithdrawalProvider = Callable[[HouseholdData, int], float]
OffsetMonthChecker = Callable[[int], bool]
StrategyModeResolver = Callable[[str, int, int], str]


@dataclass
class ProvidentMemberAccountState:
    member_index: int
    member_name: str
    balance: float
    enabled: bool = True
    open_month: str = ""


def initial_provident_member_accounts(
    household: HouseholdData,
    member_income_at_month: MemberIncomeRowsProvider,
) -> list[ProvidentMemberAccountState]:
    members = household.members
    if not members:
        return [
            ProvidentMemberAccountState(
                member_index=0,
                member_name="家庭公积金账户",
                balance=max(0.0, household.provident_fund_balance),
            )
        ]

    explicit_balances = [
        max(0.0, getattr(member, "provident_fund_balance", 0.0))
        if bool(getattr(member, "provident_account_enabled", True))
        else 0.0
        for member in members
    ]
    explicit_total = sum(explicit_balances)
    if explicit_total > 0:
        balances = explicit_balances
    else:
        profiles = member_income_at_month(1)
        deposit_by_index = {index: max(0.0, profile.monthly_pf_deposit) for index, _, profile in profiles}
        deposit_weights = [deposit_by_index.get(index, 0.0) for index in range(len(members))]
        total_weight = sum(deposit_weights)
        if total_weight <= 0:
            deposit_weights = [1.0 for _ in members]
            total_weight = float(len(members))
        balances = [
            max(0.0, household.provident_fund_balance) * weight / total_weight
            for weight in deposit_weights
        ]

    return [
        ProvidentMemberAccountState(
            member_index=index,
            member_name=member.name,
            balance=balances[index] if index < len(balances) else 0.0,
            enabled=bool(getattr(member, "provident_account_enabled", True)),
            open_month=getattr(member, "provident_account_open_month", "") or getattr(member, "family_join_month", ""),
        )
        for index, member in enumerate(members)
    ]


def household_initial_provident_balance(
    household: HouseholdData,
    member_income_at_month: MemberIncomeRowsProvider,
) -> float:
    return sum(account.balance for account in initial_provident_member_accounts(household, member_income_at_month))


def future_provident_value(initial_balance: float, monthly_net_growth: float, annual_interest_rate: float, months: int) -> float:
    monthly_rate = max(0, annual_interest_rate) / 12
    value = max(0, initial_balance)
    for _ in range(months):
        value = value * (1 + monthly_rate) + monthly_net_growth
    return max(0, value)


def future_provident_value_with_schedule(
    initial_balance: float,
    annual_interest_rate: float,
    months: int,
    monthly_net_growth_at: Callable[[int], float],
) -> float:
    monthly_rate = max(0, annual_interest_rate) / 12
    value = max(0, initial_balance)
    for month in range(1, months + 1):
        value = max(0, value * (1 + monthly_rate) + monthly_net_growth_at(month))
    return max(0, value)


def account_open_in_month(open_month: object, target_month: date) -> bool:
    parsed = parse_year_month(str(open_month or ""))
    if parsed is None:
        return True
    return month_distance(parsed, (target_month.year, target_month.month)) >= 0


def apply_provident_member_outflow(
    account_rows: list[dict[str, float | int | str | bool]],
    amount: float,
    field: str,
    *,
    retained_balance: float = 0.0,
    priority_member_index: int | None = None,
) -> float:
    target = max(0.0, amount)
    if target <= 0:
        return 0.0
    available_by_index = [max(0.0, float(row["balance_end"]) - retained_balance) for row in account_rows]
    total_available = sum(available_by_index)
    actual = min(target, total_available)
    if actual <= 0:
        return 0.0

    if priority_member_index is not None:
        remaining = actual
        ordered_indexes = sorted(
            range(len(account_rows)),
            key=lambda index: 0 if int(account_rows[index]["member_index"]) == priority_member_index else 1,
        )
        for index in ordered_indexes:
            account_available = max(0.0, float(account_rows[index]["balance_end"]) - retained_balance)
            if account_available <= 0:
                continue
            outflow = min(account_available, remaining)
            account_rows[index][field] = float(account_rows[index].get(field, 0.0)) + outflow
            account_rows[index]["balance_end"] = max(0.0, float(account_rows[index]["balance_end"]) - outflow)
            remaining -= outflow
            if remaining <= 0:
                break
        return actual - max(0.0, remaining)

    remaining = actual
    remaining_available = total_available
    for index, row in enumerate(account_rows):
        account_available = available_by_index[index]
        if account_available <= 0:
            continue
        share = remaining if index == len(account_rows) - 1 else actual * account_available / total_available
        outflow = min(account_available, share, remaining)
        row[field] = float(row.get(field, 0.0)) + outflow
        row["balance_end"] = max(0.0, float(row["balance_end"]) - outflow)
        remaining -= outflow
        remaining_available -= account_available
        if remaining <= 0:
            break

    if remaining > 0 and remaining_available > 0:
        for row in account_rows:
            account_available = max(0.0, float(row["balance_end"]) - retained_balance)
            outflow = min(account_available, remaining)
            row[field] = float(row.get(field, 0.0)) + outflow
            row["balance_end"] = max(0.0, float(row["balance_end"]) - outflow)
            remaining -= outflow
            if remaining <= 0:
                break
    return actual - max(0.0, remaining)


def provident_member_points(account_rows: list[dict[str, float | int | str | bool]]) -> list[ProvidentMemberAccountPoint]:
    points: list[ProvidentMemberAccountPoint] = []
    for row in account_rows:
        total_deposit = float(row["personal_deposit"]) + float(row["employer_deposit"])
        total_inflow = total_deposit + float(row["interest"])
        total_outflow = (
            float(row["rent_withdrawal"])
            + float(row["upfront_withdrawal"])
            + float(row["post_transaction_withdrawal"])
            + float(row["agreed_withdrawal"])
            + float(row.get("monthly_repayment_withdrawal", 0.0))
            + float(row["loan_offset_payment"])
            + float(row["retirement_withdrawal"])
        )
        points.append(
            ProvidentMemberAccountPoint(
                member_index=int(row["member_index"]),
                member_name=str(row["member_name"]),
                balance_start=round(float(row["balance_start"]), 2),
                personal_deposit=round(float(row["personal_deposit"]), 2),
                employer_deposit=round(float(row["employer_deposit"]), 2),
                total_deposit=round(total_deposit, 2),
                interest=round(float(row["interest"]), 2),
                rent_withdrawal=round(float(row["rent_withdrawal"]), 2),
                upfront_withdrawal=round(float(row["upfront_withdrawal"]), 2),
                post_transaction_withdrawal=round(float(row["post_transaction_withdrawal"]), 2),
                agreed_withdrawal=round(float(row["agreed_withdrawal"]), 2),
                monthly_repayment_withdrawal=round(float(row.get("monthly_repayment_withdrawal", 0.0)), 2),
                loan_offset_payment=round(float(row["loan_offset_payment"]), 2),
                retirement_withdrawal=round(float(row["retirement_withdrawal"]), 2),
                account_closed_by_retirement=bool(row["account_closed_by_retirement"]),
                total_inflow=round(total_inflow, 2),
                total_outflow=round(total_outflow, 2),
                balance_end=round(float(row["balance_end"]), 2),
            )
        )
    return points


def beijing_pf_loan_offset_target(
    *,
    available_balance: float,
    agreed_payment: float,
    remaining_loan_balance: float,
) -> float:
    available = max(0.0, available_balance)
    remaining = max(0.0, remaining_loan_balance)
    if available <= 0 or remaining <= 0:
        return 0.0

    minimum_offset = min(max(0.0, agreed_payment), remaining)
    if minimum_offset > 0 and available < minimum_offset:
        return 0.0
    return min(available, remaining)


def build_provident_projection(
    household: HouseholdData,
    rules: RulePackData,
    purchase_plans: list[PurchasePlanAnalysis],
    *,
    horizon_months: int,
    member_income_at_month: MemberIncomeRowsProvider,
    retirement_months_by_member: dict[int, int],
    rent_withdrawal_at_month: RentWithdrawalProvider,
    is_offset_month: OffsetMonthChecker,
    strategy_active_mode: StrategyModeResolver,
    as_of: date | None = None,
) -> list[ProvidentVisualizationPoint]:
    policy = get_policy(rules)
    pf_interest_rate = policy.provident_account_balance_annual_interest_rate() / 12
    retained_balance = policy.provident_loan_offset_retained_balance()
    base = as_of or date.today()
    base_month = date(base.year, base.month, 1)
    rows: list[ProvidentVisualizationPoint] = []

    for plan in purchase_plans:
        purchase_month = plan.months_to_buy if plan.months_to_buy is not None else 360
        account_states = initial_provident_member_accounts(household, member_income_at_month)
        remaining_offsetable_loan = max(0.0, plan.provident_loan_amount)
        for month in range(horizon_months + 1):
            member_profiles = {index: profile for index, _, profile in member_income_at_month(month)}
            account_rows: list[dict[str, float | int | str | bool]] = []
            for account in account_states:
                member_index = account.member_index
                profile = member_profiles.get(member_index)
                retirement_month = retirement_months_by_member.get(member_index, 999999)
                is_retired_account_month = month >= retirement_month
                closes_this_month = month == retirement_month
                target_year, target_month_number = month_after(base_month, month)
                account_open = account.enabled and account_open_in_month(
                    account.open_month,
                    date(target_year, target_month_number, 1),
                )
                balance_start = float(account.balance)
                personal_deposit = profile.personal_housing_fund if account_open and profile and month > 0 and not is_retired_account_month else 0.0
                employer_deposit = profile.employer_housing_fund if account_open and profile and month > 0 and not is_retired_account_month else 0.0
                interest = balance_start * pf_interest_rate if account_open and month > 0 and not is_retired_account_month else 0.0
                balance_end = balance_start + personal_deposit + employer_deposit + interest
                retirement_withdrawal = balance_end if closes_this_month and balance_end > 0 else 0.0
                if retirement_withdrawal:
                    balance_end = 0.0
                account_rows.append(
                    {
                        "member_index": member_index,
                        "member_name": account.member_name,
                        "balance_start": balance_start,
                        "personal_deposit": personal_deposit,
                        "employer_deposit": employer_deposit,
                        "interest": interest,
                        "rent_withdrawal": 0.0,
                        "upfront_withdrawal": 0.0,
                        "post_transaction_withdrawal": 0.0,
                        "agreed_withdrawal": 0.0,
                        "monthly_repayment_withdrawal": 0.0,
                        "loan_offset_payment": 0.0,
                        "retirement_withdrawal": retirement_withdrawal,
                        "account_closed_by_retirement": is_retired_account_month,
                        "balance_end": balance_end,
                    }
                )

            rent_withdrawal = 0.0
            upfront_withdrawal = 0.0
            post_transaction_withdrawal = 0.0
            agreed_withdrawal = 0.0
            monthly_repayment_withdrawal = 0.0
            loan_offset_payment = 0.0
            retirement_withdrawal = sum(float(row["retirement_withdrawal"]) for row in account_rows)

            is_purchase_month = plan.months_to_buy is not None and month == purchase_month
            is_after_purchase = plan.months_to_buy is not None and month > purchase_month
            if month > 0 and not is_purchase_month and not is_after_purchase:
                rent_withdrawal = apply_provident_member_outflow(
                    account_rows,
                    rent_withdrawal_at_month(household, month),
                    "rent_withdrawal",
                )

            if is_purchase_month:
                upfront_withdrawal = apply_provident_member_outflow(
                    account_rows,
                    plan.provident_upfront_extractable,
                    "upfront_withdrawal",
                )
                post_transaction_withdrawal = apply_provident_member_outflow(
                    account_rows,
                    plan.provident_post_transaction_extractable,
                    "post_transaction_withdrawal",
                )
            elif is_after_purchase:
                strategy = plan.post_purchase_pf_strategy or ""
                active_strategy = strategy_active_mode(strategy, purchase_month, month)
                if "monthly_repayment_withdrawal" in active_strategy:
                    monthly_repayment_withdrawal = apply_provident_member_outflow(
                        account_rows,
                        plan.provident_monthly_payment,
                        "monthly_repayment_withdrawal",
                        priority_member_index=household.borrower_member_index,
                    )
                elif "loan_offset" in active_strategy:
                    available = sum(max(0.0, float(row["balance_end"]) - retained_balance) for row in account_rows)
                    loan_offset_payment = (
                        beijing_pf_loan_offset_target(
                            available_balance=available,
                            agreed_payment=plan.provident_monthly_payment,
                            remaining_loan_balance=remaining_offsetable_loan,
                        )
                        if is_offset_month(month) and available > 0
                        else 0.0
                    )
                    loan_offset_payment = apply_provident_member_outflow(
                        account_rows,
                        loan_offset_payment,
                        "loan_offset_payment",
                        retained_balance=retained_balance,
                        priority_member_index=household.borrower_member_index,
                    )
                    remaining_offsetable_loan = max(0.0, remaining_offsetable_loan - loan_offset_payment)
                elif "purchase_agreed" in strategy:
                    agreed_withdrawal = apply_provident_member_outflow(
                        account_rows,
                        plan.monthly_post_purchase_pf_withdrawal,
                        "agreed_withdrawal",
                    )

            for index, account in enumerate(account_states):
                account.balance = float(account_rows[index]["balance_end"])

            member_accounts = provident_member_points(account_rows)
            balance_start = sum(item.balance_start for item in member_accounts)
            personal_deposit = sum(item.personal_deposit for item in member_accounts)
            employer_deposit = sum(item.employer_deposit for item in member_accounts)
            total_deposit = sum(item.total_deposit for item in member_accounts)
            interest = sum(item.interest for item in member_accounts)
            total_inflow = total_deposit + interest
            total_outflow = (
                rent_withdrawal
                + upfront_withdrawal
                + post_transaction_withdrawal
                + agreed_withdrawal
                + monthly_repayment_withdrawal
                + loan_offset_payment
                + retirement_withdrawal
            )
            balance_end = sum(item.balance_end for item in member_accounts)
            rows.append(
                ProvidentVisualizationPoint(
                    plan_variant=plan.variant,
                    month=month,
                    balance_start=round(balance_start, 2),
                    personal_deposit=round(personal_deposit, 2),
                    employer_deposit=round(employer_deposit, 2),
                    total_deposit=round(total_deposit, 2),
                    interest=round(interest, 2),
                    rent_withdrawal=round(rent_withdrawal, 2),
                    upfront_withdrawal=round(upfront_withdrawal, 2),
                    post_transaction_withdrawal=round(post_transaction_withdrawal, 2),
                    agreed_withdrawal=round(agreed_withdrawal, 2),
                    monthly_repayment_withdrawal=round(monthly_repayment_withdrawal, 2),
                    loan_offset_payment=round(loan_offset_payment, 2),
                    retirement_withdrawal=round(retirement_withdrawal, 2),
                    total_inflow=round(total_inflow, 2),
                    total_outflow=round(total_outflow, 2),
                    balance_end=round(max(0.0, balance_end), 2),
                    strategy_label=plan.post_purchase_pf_strategy_label,
                    member_accounts=member_accounts,
                )
            )
    return rows
