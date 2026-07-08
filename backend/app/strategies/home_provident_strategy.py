from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Protocol

from ..domain.tax import income_stage_for_month
from ..domain.time import add_months
from ..policies import get_policy
from ..schemas import HouseholdData, RulePackData, ScenarioData
from ..projection.provident import beijing_pf_loan_offset_target


class MonthlyIncomeProfileLike(Protocol):
    gross_income: float
    net_income: float
    monthly_pf_deposit: float
    personal_pension_contribution: float


def _money_text(amount: float) -> str:
    value = round(float(amount), 2)
    if abs(value) >= 10000:
        text = f"{value / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text} 万"
    return f"{value:.0f} 元"


def _pf_strategy_switch_month(mode: str) -> int:
    if ":" not in mode:
        return 12
    try:
        return max(1, int(mode.rsplit(":", 1)[1]))
    except ValueError:
        return 12


def post_purchase_monthly_pf_withdrawal(
    *,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
) -> tuple[float, str]:
    if not bool(rules.params.get("provident_post_purchase_cashflow_enabled", False)):
        return 0.0, "kept_in_account"
    if not bool(rules.params.get("provident_monthly_withdrawal_after_purchase_enabled", False)):
        return 0.0, "kept_in_account"
    mode = str(rules.params.get("provident_post_purchase_withdrawal_mode", "purchase_agreed"))
    if mode in {"loan_offset", "monthly_repayment_withdrawal"}:
        return min(monthly_pf_deposit, provident_monthly_payment), "monthly_repayment_withdrawal"
    return monthly_pf_deposit, "purchase_agreed"


def normalized_provident_account_management_center(value: str | None) -> str | None:
    center = str(value or "").strip().lower()
    if center in {"national", "central_state", "guoguan", "state"}:
        return "national"
    if center in {"beijing_municipal", "municipal", "shiguan", "city"}:
        return "beijing_municipal"
    return None


def borrower_provident_account_management_center(
    household: HouseholdData,
    rules: RulePackData,
    *,
    months_from_now: int = 0,
    as_of: date | None = None,
) -> str:
    if household.members:
        index = max(0, min(household.borrower_member_index, len(household.members) - 1))
        member = household.members[index]
        current = as_of or date.today()
        target = add_months(date(current.year, current.month, 1), max(0, months_from_now))
        stage = income_stage_for_month(member, target.year, target.month)
        center = normalized_provident_account_management_center(
            getattr(stage, "provident_account_management_center", None) if stage else None
        )
        if center:
            return center
    return get_policy(rules).provident_account_management_center()


def policy_default_pf_account_strategy(
    rules: RulePackData,
    household: HouseholdData | None = None,
    *,
    months_from_now: int = 0,
    as_of: date | None = None,
) -> str:
    center = (
        borrower_provident_account_management_center(
            household,
            rules,
            months_from_now=months_from_now,
            as_of=as_of,
        )
        if household
        else get_policy(rules).provident_account_management_center()
    )
    if center == "national" and bool(rules.params.get("provident_national_monthly_direct_offset_supported", True)):
        return "monthly_repayment_withdrawal"
    if bool(rules.params.get("provident_municipal_monthly_repayment_withdrawal_supported", True)):
        return "monthly_repayment_withdrawal"
    if bool(rules.params.get("provident_municipal_semiannual_principal_offset_supported", True)):
        return "semiannual_principal_offset"
    return "keep_in_account"


def effective_pf_account_strategy(scenario: ScenarioData, rules: RulePackData, household: HouseholdData) -> str:
    strategy = str(getattr(scenario, "provident_account_repayment_strategy", "auto") or "auto")
    if strategy == "auto":
        return "auto"
    if strategy == "loan_offset":
        return "semiannual_principal_offset"
    if strategy in {"monthly_repayment_withdrawal", "semiannual_principal_offset", "keep_in_account"}:
        return strategy
    return policy_default_pf_account_strategy(rules, household)


def is_beijing_pf_offset_month(months_from_now: int, *, as_of: date | None = None) -> bool:
    current = as_of or date.today()
    target = add_months(date(current.year, current.month, 1), max(0, months_from_now))
    return target.month in {1, 7}


def semiannual_loan_offset_projection(
    *,
    purchase_month: int,
    starting_pf_balance: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
    horizon_months: int = 12,
    as_of: date | None = None,
) -> tuple[float, float]:
    if monthly_pf_deposit <= 0 or provident_monthly_payment <= 0:
        return 0.0, 0.0
    pf_balance = max(0.0, starting_pf_balance)
    retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_rate = max(0.0, pf_interest_rate) / 12
    total_cash_relief = 0.0
    total_offset_payment = 0.0
    for offset in range(1, horizon_months + 1):
        absolute_month = purchase_month + offset
        pf_balance += pf_balance * pf_monthly_rate + monthly_pf_deposit
        if not is_beijing_pf_offset_month(absolute_month, as_of=as_of):
            continue
        available = max(0.0, pf_balance - retained_balance)
        if available <= 0:
            continue
        offset_payment = beijing_pf_loan_offset_target(
            available_balance=available,
            agreed_payment=provident_monthly_payment,
            remaining_loan_balance=max(available, provident_monthly_payment),
        )
        if offset_payment <= 0:
            continue
        pf_balance -= offset_payment
        total_cash_relief += min(offset_payment, provident_monthly_payment)
        total_offset_payment += offset_payment
    months = max(1, horizon_months)
    return total_cash_relief / months, total_offset_payment / months


def semiannual_loan_offset_monthly_equivalent(
    *,
    purchase_month: int,
    starting_pf_balance: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    rules: RulePackData,
    horizon_months: int = 12,
    as_of: date | None = None,
) -> float:
    cash_relief, _ = semiannual_loan_offset_projection(
        purchase_month=purchase_month,
        starting_pf_balance=starting_pf_balance,
        monthly_pf_deposit=monthly_pf_deposit,
        provident_monthly_payment=provident_monthly_payment,
        rules=rules,
        horizon_months=horizon_months,
        as_of=as_of,
    )
    return cash_relief


def pf_strategy_monthly_then_offset(switch_month: int = 12, *, auto: bool = True) -> str:
    prefix = "monthly_then_semiannual_offset_auto" if auto else "monthly_then_semiannual_offset"
    return f"{prefix}:{max(1, switch_month)}"


def pf_strategy_active_mode(mode: str, *, purchase_month: int, current_month: int | None = None) -> str:
    if not mode.startswith("monthly_then_semiannual_offset"):
        return mode
    if current_month is None:
        return "monthly_repayment_withdrawal_auto" if "_auto" in mode else "monthly_repayment_withdrawal"
    repayment_month = max(1, current_month - purchase_month)
    if repayment_month <= _pf_strategy_switch_month(mode):
        return "monthly_repayment_withdrawal_auto" if "_auto" in mode else "monthly_repayment_withdrawal"
    return "loan_offset_semiannual_auto" if "_auto" in mode else "loan_offset_semiannual"


def post_purchase_pf_strategy(
    *,
    household: HouseholdData,
    purchase_month: int,
    starting_pf_balance: float,
    free_cash_flow: float,
    monthly_pf_deposit: float,
    provident_monthly_payment: float,
    total_monthly_payment: float,
    post_purchase_monthly_expense: float,
    rules: RulePackData,
    strategy_preference: str = "auto",
    current_month: int | None = None,
) -> tuple[float, str]:
    strategy_mode = str(rules.params.get("provident_post_purchase_strategy_mode", "auto"))
    if strategy_preference != "auto":
        strategy_mode = strategy_preference
    manual_enabled = bool(rules.params.get("provident_post_purchase_cashflow_enabled", False)) and bool(
        rules.params.get("provident_monthly_withdrawal_after_purchase_enabled", False)
    )
    if strategy_mode == "manual":
        if not manual_enabled:
            return 0.0, "kept_in_account"
        manual_mode = str(rules.params.get("provident_post_purchase_withdrawal_mode", "monthly_repayment_withdrawal"))
        if manual_mode in {"monthly_repayment_withdrawal", "semiannual_principal_offset", "keep_in_account"}:
            strategy_mode = manual_mode
        else:
            strategy_mode = "purchase_agreed"
    if strategy_mode == "keep_in_account":
        return 0.0, "kept_in_account"
    if strategy_mode.startswith("monthly_then_semiannual_offset"):
        active_mode = pf_strategy_active_mode(
            strategy_mode,
            purchase_month=purchase_month,
            current_month=current_month,
        )
        if active_mode in {"monthly_repayment_withdrawal", "monthly_repayment_withdrawal_auto"}:
            if monthly_pf_deposit <= 0 or provident_monthly_payment <= 0:
                return 0.0, "kept_in_account"
            return min(monthly_pf_deposit, provident_monthly_payment), strategy_mode
        monthly_equivalent = semiannual_loan_offset_monthly_equivalent(
            purchase_month=purchase_month,
            starting_pf_balance=starting_pf_balance,
            monthly_pf_deposit=monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            rules=rules,
        )
        if monthly_equivalent <= 0:
            return 0.0, "kept_in_account"
        return monthly_equivalent, strategy_mode
    if strategy_mode in {"loan_offset", "semiannual_principal_offset"}:
        monthly_equivalent = semiannual_loan_offset_monthly_equivalent(
            purchase_month=purchase_month,
            starting_pf_balance=starting_pf_balance,
            monthly_pf_deposit=monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            rules=rules,
        )
        if monthly_equivalent <= 0:
            return 0.0, "kept_in_account"
        return monthly_equivalent, "loan_offset_semiannual"
    if strategy_mode == "monthly_repayment_withdrawal":
        if monthly_pf_deposit <= 0 or provident_monthly_payment <= 0:
            return 0.0, "kept_in_account"
        return min(monthly_pf_deposit, provident_monthly_payment), "monthly_repayment_withdrawal"
    if strategy_mode == "purchase_agreed":
        if monthly_pf_deposit <= 0:
            return 0.0, "kept_in_account"
        return monthly_pf_deposit, "purchase_agreed"

    default_policy_strategy = policy_default_pf_account_strategy(
        rules,
        household,
        months_from_now=purchase_month,
    )
    monthly_relief = (
        min(monthly_pf_deposit, provident_monthly_payment)
        if default_policy_strategy == "monthly_repayment_withdrawal" and monthly_pf_deposit > 0 and provident_monthly_payment > 0
        else 0.0
    )

    loan_offset_improvement, loan_offset_principal_effect = semiannual_loan_offset_projection(
        purchase_month=purchase_month,
        starting_pf_balance=starting_pf_balance,
        monthly_pf_deposit=monthly_pf_deposit,
        provident_monthly_payment=provident_monthly_payment,
        rules=rules,
    )
    can_switch_between_modes = (
        monthly_relief > 0
        and loan_offset_improvement > 0
        and bool(rules.params.get("provident_municipal_monthly_repayment_withdrawal_supported", True))
        and bool(rules.params.get("provident_municipal_semiannual_principal_offset_supported", True))
    )
    if can_switch_between_modes:
        monthly_fixes_cash_deficit = free_cash_flow < 0 <= free_cash_flow + monthly_relief
        loan_offset_material = loan_offset_principal_effect >= max(1000.0, provident_monthly_payment * 0.75)
        monthly_needed_for_pressure = free_cash_flow < post_purchase_monthly_expense * 0.20
        if loan_offset_material and (monthly_fixes_cash_deficit or monthly_needed_for_pressure):
            return monthly_relief, pf_strategy_monthly_then_offset(12, auto=True)

    if monthly_relief > 0 and (free_cash_flow < 0 or monthly_relief >= max(500.0, total_monthly_payment * 0.08)):
        return monthly_relief, "monthly_repayment_withdrawal_auto"

    if provident_monthly_payment > 0 and loan_offset_improvement > 0:
        pressure_ratio = total_monthly_payment / max(1.0, total_monthly_payment + post_purchase_monthly_expense)
        near_cash_tension = free_cash_flow < post_purchase_monthly_expense * 0.25
        material_payment_share = loan_offset_improvement >= max(500.0, total_monthly_payment * 0.08)
        material_principal_effect = loan_offset_principal_effect >= max(500.0, provident_monthly_payment * 0.5)
        if free_cash_flow < 0 or (near_cash_tension and material_payment_share) or pressure_ratio > 0.55 or material_principal_effect:
            return loan_offset_improvement, "loan_offset_semiannual_auto"

    if manual_enabled:
        return post_purchase_monthly_pf_withdrawal(
            monthly_pf_deposit=monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            rules=rules,
        )
    return 0.0, "kept_in_account"


def post_purchase_pf_withdrawal_label(mode: str) -> str:
    if mode.startswith("monthly_then_semiannual_offset"):
        return f"自动先按月提取还公积金贷，第 {_pf_strategy_switch_month(mode)} 个还款月后切换为北京半年度冲还贷"
    labels = {
        "kept_in_account": "默认留存在公积金账户",
        "purchase_agreed": "显式开启后按购房约定提取估算",
        "monthly_repayment_withdrawal": "按月约定提取偿还公积金贷款月供",
        "monthly_repayment_withdrawal_auto": "自动选择按月约定提取抵扣公积金贷月供",
        "loan_offset": "显式开启后按公积金贷款冲还贷估算",
        "loan_offset_semiannual": "显式开启后按北京半年度冲还贷估算",
        "loan_offset_semiannual_auto": "自动选择北京半年度公积金贷款冲还贷",
    }
    return labels.get(mode, "默认留存在公积金账户")


def post_purchase_pf_strategy_note(mode: str, *, monthly_relief: float = 0.0) -> str:
    if mode.startswith("monthly_then_semiannual_offset"):
        switch_month = _pf_strategy_switch_month(mode)
        return (
            f"自动策略采用阶段切换：买房后前 {switch_month} 个还款月走按月约定提取偿还公积金贷款，"
            f"优先缓解现金流压力，月均减少现金压力约 {_money_text(monthly_relief)}；"
            f"第 {switch_month + 1} 个还款月起切换为北京半年度冲还贷，在每年 1 月/7 月合同约定日集中冲抵公积金贷款本金。"
            "两种模式互斥，切换到冲还贷后原按月约定提取会终止，后端账户曲线按切换后的规则逐月记账。"
        )
    if "monthly_repayment_withdrawal" in mode:
        return "按月约定提取偿还公积金贷款时，系统按每月先用公积金账户余额覆盖当期公积金贷月供、不足部分由银行卡补扣估算。"
    if "loan_offset" in mode:
        return "半年度冲还贷属于用公积金账户资金在约定月份集中冲抵贷款本金；该路径与购房、租房、按月约定提取事项互斥。"
    return "未启用贷后公积金提取或冲还贷时，买房后的公积金继续留存在个人账户中，除退休销户等政策情形外不计入自由现金。"


def provident_extraction_notes(mode: str, *, monthly_relief: float = 0.0) -> list[str]:
    return [
        "交易前仅按规则包中的可提前提取比例计入首付现金；默认 0%，避免把审核后到账资金误当作交易前现金。",
        "交易后购房提取按购房价款额度内、账户可用余额估算，审核通过后回流到银行卡。",
        "买房后家庭在京住房性质发生变化，租房提取不再作为后续公积金现金流来源。",
        "买房后月度公积金缴存默认不作为工资类收入；自动策略会在现金压力偏高且存在公积金贷款时优先考虑按月抵月供或半年度冲本金。",
        post_purchase_pf_strategy_note(mode, monthly_relief=monthly_relief),
        f"当前购后公积金处理：{post_purchase_pf_withdrawal_label(mode)}。",
    ]


def post_purchase_cash_stress(
    *,
    household: HouseholdData,
    rules: RulePackData,
    purchase_month: int,
    starting_cash: float,
    starting_pf_balance: float,
    total_monthly_payment: float,
    provident_monthly_payment: float,
    expense_at_month: Callable[[int], float],
    income_at_month: Callable[[int], MonthlyIncomeProfileLike],
    car_monthly_cash_cost_at: Callable[[int], float],
    car_down_payment_at: Callable[[int], float],
    extra_monthly_payment: float = 0.0,
    extra_payment_start_month: int = 1,
    strategy_preference: str = "auto",
    horizon_months: int = 120,
) -> tuple[float, int | None, bool]:
    cash_balance = starting_cash
    pf_balance = max(0.0, starting_pf_balance)
    minimum_cash = cash_balance
    minimum_month: int | None = purchase_month
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_rate = max(0.0, pf_interest_rate) / 12
    extra_monthly_payment = max(0.0, extra_monthly_payment)
    extra_payment_start_month = max(1, extra_payment_start_month)

    for absolute_month in range(purchase_month + 1, purchase_month + horizon_months + 1):
        repayment_month = max(1, absolute_month - purchase_month)
        income = income_at_month(absolute_month)
        pf_balance += pf_balance * pf_monthly_rate + income.monthly_pf_deposit
        monthly_expense = expense_at_month(absolute_month)
        free_cash_flow = (
            income.net_income
            - monthly_expense
            - household.monthly_debt_payment
            - car_monthly_cash_cost_at(absolute_month)
            - total_monthly_payment
        )
        monthly_pf_withdrawal, pf_strategy_mode = post_purchase_pf_strategy(
            household=household,
            purchase_month=purchase_month,
            starting_pf_balance=starting_pf_balance,
            free_cash_flow=free_cash_flow,
            monthly_pf_deposit=income.monthly_pf_deposit,
            provident_monthly_payment=provident_monthly_payment,
            total_monthly_payment=total_monthly_payment,
            post_purchase_monthly_expense=monthly_expense,
            rules=rules,
            strategy_preference=strategy_preference,
            current_month=absolute_month,
        )
        active_pf_mode = pf_strategy_active_mode(
            pf_strategy_mode,
            purchase_month=purchase_month,
            current_month=absolute_month,
        )
        if "loan_offset" in active_pf_mode:
            retained_balance = max(0.0, float(rules.params.get("provident_loan_offset_retained_balance", 10.0)))
            available = max(0.0, pf_balance - retained_balance)
            pf_withdrawal = available if is_beijing_pf_offset_month(absolute_month) and available > 0 else 0.0
        else:
            pf_withdrawal = min(pf_balance, monthly_pf_withdrawal)
        pf_balance -= pf_withdrawal
        monthly_cash_delta = free_cash_flow + min(pf_withdrawal, provident_monthly_payment)
        if extra_monthly_payment > 0 and repayment_month >= extra_payment_start_month:
            monthly_cash_delta -= extra_monthly_payment
        monthly_cash_delta -= car_down_payment_at(absolute_month)
        cash_balance += monthly_cash_delta
        if cash_balance < minimum_cash:
            minimum_cash = cash_balance
            minimum_month = absolute_month
        if cash_balance < 0:
            return round(minimum_cash, 2), minimum_month, False

    return round(minimum_cash, 2), minimum_month, minimum_cash >= 0


