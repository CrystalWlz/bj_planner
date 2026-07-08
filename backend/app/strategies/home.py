from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import ceil
from typing import Protocol

from ..domain.housing import (
    housing_transaction_rate_amounts,
    minimum_down_payment_ratio,
    provident_loan_rate as policy_provident_loan_rate,
    provident_loan_cap,
    provident_loan_years as policy_provident_loan_years,
    provident_repayment_method as scenario_provident_repayment_method,
    is_new_home_property,
    is_second_hand_property,
)
from ..domain.investments import (
    future_cash_value,
    future_cash_value_with_schedule,
    investment_allocation_for_month,
    investment_withdrawal_at_purchase,
    investment_withdrawal_mode,
    investment_withdrawal_mode_label,
)
from ..domain.loans import (
    LoanComputation,
    calculate_loan,
    commercial_prepayment_mode as scenario_commercial_prepayment_mode,
    commercial_repayment_method as scenario_commercial_repayment_method,
)
from ..domain.scoring import (
    cash_flow_score,
    clamp_score,
    dti_score,
    purchase_happiness_weights,
    prepayment_rate_spread_score,
    ratio_score,
    renovation_readiness_score,
    stress_resilience_score,
    wait_score,
    weighted_happiness_breakdown,
)
from ..projection.provident import (
    future_provident_value,
    future_provident_value_with_schedule,
)
from ..schemas import (
    CarLoanSummary,
    CarPlanData,
    HouseholdData,
    LoanSummary,
    PurchasePlanAnalysis,
    RulePackData,
    ScenarioData,
)
from .home_commercial_prepayment import (
    build_commercial_prepayment_plan,
    choose_auto_commercial_prepayment,
)
from .home_recommendations import with_purchase_plan_recommendations

from .home_provident_strategy import (
    effective_pf_account_strategy,
    post_purchase_cash_stress,
    post_purchase_pf_strategy,
    post_purchase_pf_withdrawal_label,
    provident_extraction_notes,
)

VehicleLoanState = tuple[int, CarPlanData, CarLoanSummary, int | None]


class MonthlyIncomeProfileLike(Protocol):
    gross_income: float
    net_income: float
    monthly_pf_deposit: float
    personal_pension_contribution: float


class TaxSummaryLike(Protocol):
    monthly_personal_housing_fund: float
    monthly_employer_housing_fund: float


@dataclass(frozen=True)
class ProvidentRepaymentChoice:
    equal_installment_payment: LoanComputation
    equal_principal_payment: LoanComputation
    selected_method: str
    selected_payment: LoanComputation
    interest_saving_if_equal_principal: float
    equal_principal_extra_first_payment: float


@dataclass(frozen=True)
class RenovationFundingPlan:
    included_upfront: bool
    saving_months: int | None
    monthly_saving: float


@dataclass(frozen=True)
class PurchaseVariantSpec:
    name: str
    description: str
    target_commercial_loan: float
    use_min_down_payment: bool
    use_manual_mix: bool
    use_micro_strategy: bool


@dataclass(frozen=True)
class PurchaseCandidate:
    purchase_month: int
    mix: tuple[float, float, float, float, float, float, float]
    pf_upfront_extractable: float
    family_pf_upfront_extractable: float
    pf_post_transaction_extractable: float
    cash_account_before_purchase: float
    investment_balance_before_purchase: float
    investment_sell_gross_at_purchase: float
    investment_sell_proceeds_at_purchase: float
    investment_balance_after_purchase: float
    cash_after_transaction: float
    cash_after_purchase: float
    pf_after_extract: float
    minimum_cash_balance: float
    minimum_cash_balance_month: int | None
    cash_stress_ok: bool
    cash_stress_shortfall: float


@dataclass(frozen=True)
class PurchaseCandidateSearchResult:
    months: int | None
    candidate: PurchaseCandidate
    required_liquidity_reserve: float


@dataclass
class PurchasePlanningContext:
    household: HouseholdData
    scenario: ScenarioData
    rules: RulePackData
    tax_summaries: Sequence[TaxSummaryLike]
    income_profile_provider: Callable[[int], MonthlyIncomeProfileLike]
    expense_provider: Callable[[int, int | None], float]
    rent_withdrawal_before_purchase: Callable[[HouseholdData], float]
    quarterly_rent_withdrawal_before_purchase_at: Callable[[HouseholdData, int], float]
    vehicle_states_provider: Callable[[], list[VehicleLoanState]]
    car_monthly_cash_cost_provider: Callable[[list[VehicleLoanState], int], float]
    car_down_payment_provider: Callable[[list[VehicleLoanState], int], float]
    family_down_payment_upfront_support: Callable[[int, float], float]
    initial_provident_balance: float
    current_monthly_expense: float = 0.0
    required_liquidity_reserve: float = 0.0
    monthly_pf_deposit: float = 0.0
    monthly_pf_net_growth: float = 0.0
    vehicle_states: list[VehicleLoanState] = field(default_factory=list)
    initial_car_down_payment: float = 0.0
    initial_cash: float = 0.0
    initial_investment: float = 0.0
    monthly_cash_savings: float = 0.0
    cash_value_by_month: list[float] = field(default_factory=list)
    investment_value_by_month: list[float] = field(default_factory=list)
    pf_value_by_month: list[float] = field(default_factory=list)
    _expense_cache: dict[int, float] = field(default_factory=dict)
    _income_cache: dict[int, MonthlyIncomeProfileLike] = field(default_factory=dict)
    _car_cost_cache: dict[int, float] = field(default_factory=dict)
    _car_down_payment_cache: dict[int, float] = field(default_factory=dict)

    def expense_at_month(self, month: int, home_purchase_month: int | None = None) -> float:
        cache_key = (home_purchase_month if home_purchase_month is not None else -1) * 10000 + month
        if cache_key not in self._expense_cache:
            self._expense_cache[cache_key] = self.expense_provider(month, home_purchase_month)
        return self._expense_cache[cache_key]

    def income_at_month(self, month: int) -> MonthlyIncomeProfileLike:
        if month not in self._income_cache:
            self._income_cache[month] = self.income_profile_provider(month)
        return self._income_cache[month]

    def car_monthly_cash_cost_at(self, month: int) -> float:
        if month not in self._car_cost_cache:
            self._car_cost_cache[month] = self.car_monthly_cash_cost_provider(self.vehicle_states, month)
        return self._car_cost_cache[month]

    def car_down_payment_at(self, month: int) -> float:
        if month not in self._car_down_payment_cache:
            self._car_down_payment_cache[month] = self.car_down_payment_provider(self.vehicle_states, month)
        return self._car_down_payment_cache[month]

    def monthly_pf_net_growth_at(self, month: int) -> float:
        return (
            self.income_at_month(month).monthly_pf_deposit
            - self.quarterly_rent_withdrawal_before_purchase_at(self.household, month)
        )

    def monthly_cash_savings_at(self, month: int) -> float:
        income_profile = self.income_at_month(month)
        savings = (
            income_profile.net_income
            + self.quarterly_rent_withdrawal_before_purchase_at(self.household, month)
            - self.expense_at_month(month)
            - income_profile.personal_pension_contribution
            - self.household.monthly_debt_payment
            - self.car_monthly_cash_cost_at(month)
        )
        if month > 0:
            savings -= self.car_down_payment_at(month)
        return savings

    def financing_mix_at(
        self,
        *,
        variant_spec: PurchaseVariantSpec,
        purchase_months: int,
        taxes_and_fees: float,
        target_commercial_loan: float | None = None,
    ) -> tuple[float, float, float, float, float, float, float]:
        return purchase_financing_mix(
            household=self.household,
            scenario=self.scenario,
            rules=self.rules,
            variant_spec=variant_spec,
            purchase_months=purchase_months,
            taxes_and_fees=taxes_and_fees,
            monthly_income_for_capacity=self.income_at_month(purchase_months).gross_income,
            target_commercial_loan=target_commercial_loan,
        )

    def purchase_state_for_mix(
        self,
        candidate_month: int,
        mix: tuple[float, float, float, float, float, float, float],
    ) -> tuple[float, float, float, float, float, float, float, float, float, float, float]:
        return purchase_cash_state_at_month(
            month=candidate_month,
            upfront_cash_required=mix[6],
            planned_down_payment=mix[3],
            household=self.household,
            rules=self.rules,
            initial_cash=self.initial_cash,
            monthly_cash_savings=self.monthly_cash_savings,
            monthly_cash_savings_at=self.monthly_cash_savings_at,
            monthly_pf_net_growth=self.monthly_pf_net_growth,
            monthly_pf_net_growth_at=self.monthly_pf_net_growth_at,
            annual_return=self.scenario.annual_investment_return,
            property_price=self.scenario.total_price,
            scenario=self.scenario,
            initial_provident_balance=self.initial_provident_balance,
            monthly_household_expense_at=self.expense_at_month,
            family_down_payment_upfront_support=self.family_down_payment_upfront_support,
            cash_value_by_month=self.cash_value_by_month,
            investment_value_by_month=self.investment_value_by_month,
            pf_value_by_month=self.pf_value_by_month,
        )

    def cash_stress_for_mix(
        self,
        *,
        candidate_month: int,
        mix: tuple[float, float, float, float, float, float, float],
        candidate_cash_after_purchase: float,
        candidate_pf_after_extract: float,
        effective_provident_rate: float,
        provident_loan_years: int,
        commercial_repayment_method: str,
        provident_repayment_method: str,
        commercial_prepayment_mode: str,
        strategy_preference: str,
    ) -> tuple[float, int | None, bool]:
        return cash_stress_for_financing_mix(
            household=self.household,
            scenario=self.scenario,
            rules=self.rules,
            purchase_month=candidate_month,
            financing_mix=mix,
            starting_cash=candidate_cash_after_purchase,
            starting_pf_balance=candidate_pf_after_extract,
            effective_provident_rate=effective_provident_rate,
            provident_loan_years=provident_loan_years,
            commercial_repayment_method=commercial_repayment_method,
            provident_repayment_method=provident_repayment_method,
            commercial_prepayment_mode=commercial_prepayment_mode,
            expense_at_month=self.expense_at_month,
            income_at_month=self.income_at_month,
            car_monthly_cash_cost_at=self.car_monthly_cash_cost_at,
            car_down_payment_at=self.car_down_payment_at,
            strategy_preference=strategy_preference,
        )

    def find_candidate(
        self,
        *,
        variant_spec: PurchaseVariantSpec,
        micro_ratio_candidates: list[float],
        search_start_month: int,
        target_commercial_loan: float,
        taxes_and_fees: float,
        effective_provident_rate: float,
        provident_loan_years: int,
        commercial_repayment_method: str,
        provident_repayment_method: str,
        commercial_prepayment_mode: str,
        strategy_preference: str,
    ) -> PurchaseCandidateSearchResult:
        def compute_mix_at(
            purchase_months: int,
            commercial_target: float,
        ) -> tuple[float, float, float, float, float, float, float]:
            return self.financing_mix_at(
                variant_spec=variant_spec,
                purchase_months=purchase_months,
                taxes_and_fees=taxes_and_fees,
                target_commercial_loan=commercial_target,
            )

        def cash_stress_for_candidate(
            candidate_month: int,
            mix: tuple[float, float, float, float, float, float, float],
            candidate_cash_after_purchase: float,
            candidate_pf_after_extract: float,
        ) -> tuple[float, int | None, bool]:
            return self.cash_stress_for_mix(
                candidate_month=candidate_month,
                mix=mix,
                candidate_cash_after_purchase=candidate_cash_after_purchase,
                candidate_pf_after_extract=candidate_pf_after_extract,
                effective_provident_rate=effective_provident_rate,
                provident_loan_years=provident_loan_years,
                commercial_repayment_method=commercial_repayment_method,
                provident_repayment_method=provident_repayment_method,
                commercial_prepayment_mode=commercial_prepayment_mode,
                strategy_preference=strategy_preference,
            )

        return find_purchase_candidate(
            household=self.household,
            variant_spec=variant_spec,
            micro_ratio_candidates=micro_ratio_candidates,
            search_start_month=search_start_month,
            price=self.scenario.total_price,
            target_commercial_loan=target_commercial_loan,
            compute_mix_at=compute_mix_at,
            purchase_state_for_mix=self.purchase_state_for_mix,
            cash_stress_for_mix=cash_stress_for_candidate,
            expense_at_month=self.expense_at_month,
        )


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(value, ceiling))


def micro_commercial_ratio_candidates(scenario: ScenarioData, rules: RulePackData) -> list[float]:
    micro_default_ratio = _clamp(float(rules.params.get("micro_commercial_loan_ratio", 0.05)), 0, 1)
    micro_min_ratio = _clamp(
        float(rules.params.get("micro_commercial_loan_ratio_min", min(0.02, micro_default_ratio))),
        0,
        1,
    )
    micro_max_ratio = _clamp(
        float(rules.params.get("micro_commercial_loan_ratio_max", max(0.12, micro_default_ratio))),
        micro_min_ratio,
        1,
    )
    manual_micro_ratio = _clamp(scenario.micro_commercial_loan_ratio, 0, 1)
    if manual_micro_ratio > 0:
        return [manual_micro_ratio]
    ratio_steps = max(1, int(round((micro_max_ratio - micro_min_ratio) / 0.01)))
    return sorted(
        {
            round(micro_min_ratio + (micro_max_ratio - micro_min_ratio) * index / ratio_steps, 4)
            for index in range(ratio_steps + 1)
        }
        | {micro_min_ratio, micro_default_ratio, micro_max_ratio}
    )


def purchase_variant_specs(scenario: ScenarioData, rules: RulePackData) -> list[PurchaseVariantSpec]:
    micro_default_ratio = _clamp(float(rules.params.get("micro_commercial_loan_ratio", 0.05)), 0, 1)
    price = scenario.total_price
    return [
        PurchaseVariantSpec(
            name="手动指定",
            description="按当前目标里手动填写的首付、商贷和公积金贷生成，超出政策或价格约束时自动校正。",
            target_commercial_loan=0.0,
            use_min_down_payment=False,
            use_manual_mix=True,
            use_micro_strategy=False,
        ),
        PurchaseVariantSpec(
            name="0商贷",
            description="公积金贷优先，目标是把商贷压到 0。",
            target_commercial_loan=0.0,
            use_min_down_payment=False,
            use_manual_mix=False,
            use_micro_strategy=False,
        ),
        PurchaseVariantSpec(
            name="微量商贷",
            description="以加快买房速度为目标，在微量商贷比例范围内自动选择较少商贷；若房源目标填写了手动比例，则按手动比例测算。",
            target_commercial_loan=price * micro_default_ratio,
            use_min_down_payment=False,
            use_manual_mix=False,
            use_micro_strategy=True,
        ),
        PurchaseVariantSpec(
            name="较多商贷",
            description="按北京最低首付测算，剩余贷款优先公积金后商贷。",
            target_commercial_loan=0.0,
            use_min_down_payment=True,
            use_manual_mix=False,
            use_micro_strategy=False,
        ),
    ]


def build_purchase_funding_projection(
    *,
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    initial_cash: float,
    initial_investment: float,
    initial_provident_balance: float,
    monthly_cash_savings_at: Callable[[int], float],
    monthly_household_expense_at: Callable[[int], float],
    monthly_pf_net_growth_at: Callable[[int], float],
    horizon_months: int = 360,
) -> tuple[list[float], list[float], list[float]]:
    buy_fee_rate = _clamp(household.investment_buy_fee_rate, 0.0, 0.05)
    sell_fee_rate = _clamp(household.investment_sell_fee_rate, 0.0, 0.05)
    monthly_return = scenario.annual_investment_return / 12
    pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
    pf_monthly_return = max(0.0, pf_interest_rate) / 12
    cash_value_by_month = [max(0.0, initial_cash)]
    investment_value_by_month = [max(0.0, initial_investment)]
    pf_value_by_month = [max(0.0, initial_provident_balance)]
    investment_enabled = household.investment_plan_name != "cash_only"

    for month_index in range(1, horizon_months + 1):
        monthly_savings = monthly_cash_savings_at(month_index)
        cash_value = cash_value_by_month[-1]
        investment_value = investment_value_by_month[-1]
        if investment_enabled:
            investment_value = max(0.0, investment_value * (1 + monthly_return))
        reserve_target = max(0.0, monthly_household_expense_at(month_index) * household.investment_cash_reserve_months)
        projected_cash_before_investment = cash_value + monthly_savings
        if (
            investment_enabled
            and household.investment_auto_rebalance
            and projected_cash_before_investment < reserve_target
            and investment_value > 0
        ):
            liquidity_need = max(0.0, reserve_target - projected_cash_before_investment)
            gross_sell = min(investment_value, liquidity_need / max(0.01, 1 - sell_fee_rate))
            cash_value += max(0.0, gross_sell * (1 - sell_fee_rate))
            investment_value = max(0.0, investment_value - gross_sell)

        investment_contribution = 0.0
        if investment_enabled:
            base_contribution, sweep_contribution = investment_allocation_for_month(
                monthly_surplus=monthly_savings,
                cash_balance=cash_value,
                reserve_target=reserve_target,
                household=household,
            )
            investment_contribution = base_contribution + sweep_contribution
        buy_fee = investment_contribution * buy_fee_rate
        cash_value = max(0.0, cash_value + monthly_savings - investment_contribution)
        investment_value = max(0.0, investment_value + max(0.0, investment_contribution - buy_fee))
        cash_value_by_month.append(cash_value)
        investment_value_by_month.append(investment_value)
        pf_value_by_month.append(
            max(0.0, pf_value_by_month[-1] * (1 + pf_monthly_return) + monthly_pf_net_growth_at(month_index))
        )

    return cash_value_by_month, investment_value_by_month, pf_value_by_month


def build_purchase_planning_context(
    *,
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    tax_summaries: Sequence[TaxSummaryLike],
    income_profile_provider: Callable[[int], MonthlyIncomeProfileLike],
    expense_provider: Callable[[int, int | None], float],
    rent_withdrawal_before_purchase: Callable[[HouseholdData], float],
    quarterly_rent_withdrawal_before_purchase_at: Callable[[HouseholdData, int], float],
    vehicle_states_provider: Callable[[], list[VehicleLoanState]],
    car_monthly_cash_cost_provider: Callable[[list[VehicleLoanState], int], float],
    car_down_payment_provider: Callable[[list[VehicleLoanState], int], float],
    family_down_payment_upfront_support: Callable[[int, float], float],
    initial_provident_balance: float,
) -> PurchasePlanningContext:
    context = PurchasePlanningContext(
        household=household,
        scenario=scenario,
        rules=rules,
        tax_summaries=tax_summaries,
        income_profile_provider=income_profile_provider,
        expense_provider=expense_provider,
        rent_withdrawal_before_purchase=rent_withdrawal_before_purchase,
        quarterly_rent_withdrawal_before_purchase_at=quarterly_rent_withdrawal_before_purchase_at,
        vehicle_states_provider=vehicle_states_provider,
        car_monthly_cash_cost_provider=car_monthly_cash_cost_provider,
        car_down_payment_provider=car_down_payment_provider,
        family_down_payment_upfront_support=family_down_payment_upfront_support,
        initial_provident_balance=initial_provident_balance,
    )
    context.current_monthly_expense = context.expense_at_month(0)
    context.required_liquidity_reserve = max(
        0.0,
        context.current_monthly_expense * household.required_liquidity_months,
    )
    context.monthly_pf_deposit = context.income_at_month(0).monthly_pf_deposit or sum(
        item.monthly_personal_housing_fund + item.monthly_employer_housing_fund
        for item in tax_summaries
    )
    context.monthly_pf_net_growth = context.monthly_pf_deposit - rent_withdrawal_before_purchase(household)
    context.vehicle_states = vehicle_states_provider()
    context.initial_car_down_payment = context.car_down_payment_at(0)
    context.initial_cash = max(0.0, household.cash_account_balance - context.initial_car_down_payment)
    context.initial_investment = max(0.0, household.investments)
    context.monthly_cash_savings = context.monthly_cash_savings_at(0)
    (
        context.cash_value_by_month,
        context.investment_value_by_month,
        context.pf_value_by_month,
    ) = build_purchase_funding_projection(
        household=household,
        scenario=scenario,
        rules=rules,
        initial_cash=context.initial_cash,
        initial_investment=context.initial_investment,
        initial_provident_balance=initial_provident_balance,
        monthly_cash_savings_at=context.monthly_cash_savings_at,
        monthly_household_expense_at=context.expense_at_month,
        monthly_pf_net_growth_at=context.monthly_pf_net_growth_at,
    )
    return context


def purchase_financing_mix(
    *,
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    variant_spec: PurchaseVariantSpec,
    purchase_months: int,
    taxes_and_fees: float,
    monthly_income_for_capacity: float,
    target_commercial_loan: float | None = None,
) -> tuple[float, float, float, float, float, float, float]:
    price = scenario.total_price
    cap, bonus = provident_loan_cap(
        household,
        scenario,
        rules,
        purchase_months=purchase_months,
        monthly_income_for_capacity=monthly_income_for_capacity,
        borrower_count=max(1, len(household.members)),
    )
    max_pf_loan = min(cap, price)
    min_down_ratio = minimum_down_payment_ratio(household, max_pf_loan > 0, rules)
    minimum_down = price * min_down_ratio
    if variant_spec.use_manual_mix:
        commercial = _clamp(scenario.commercial_loan_amount, 0, max(0, price - minimum_down))
        pf_loan = min(
            max(0, scenario.provident_loan_amount),
            max_pf_loan,
            max(0, price - minimum_down - commercial),
        )
        down = max(minimum_down, scenario.down_payment_amount, price - commercial - pf_loan)
        excess = max(0, down + commercial + pf_loan - price)
        if excess > 0:
            pf_reduction = min(pf_loan, excess)
            pf_loan -= pf_reduction
            excess -= pf_reduction
        if excess > 0:
            commercial = max(0, commercial - excess)
    else:
        pf_loan = min(max_pf_loan, max(0, price - minimum_down))
        if variant_spec.use_min_down_payment:
            down = minimum_down
            commercial = max(0, price - down - pf_loan)
        else:
            commercial_target = variant_spec.target_commercial_loan if target_commercial_loan is None else target_commercial_loan
            commercial = min(commercial_target, max(0, price - pf_loan - minimum_down))
            down = max(minimum_down, price - pf_loan - commercial)
    return cap, bonus, minimum_down, down, commercial, pf_loan, down + taxes_and_fees


def cash_stress_for_financing_mix(
    *,
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    purchase_month: int,
    financing_mix: tuple[float, float, float, float, float, float, float],
    starting_cash: float,
    starting_pf_balance: float,
    effective_provident_rate: float,
    provident_loan_years: int,
    commercial_repayment_method: str,
    provident_repayment_method: str,
    commercial_prepayment_mode: str,
    expense_at_month: Callable[[int], float],
    income_at_month: Callable[[int], MonthlyIncomeProfileLike],
    car_monthly_cash_cost_at: Callable[[int], float],
    car_down_payment_at: Callable[[int], float],
    strategy_preference: str,
) -> tuple[float, int | None, bool]:
    commercial_payment = calculate_loan(
        financing_mix[4],
        scenario.commercial_rate,
        scenario.loan_years,
        commercial_repayment_method,
    )
    provident_payment = calculate_loan(
        financing_mix[5],
        effective_provident_rate,
        provident_loan_years,
        provident_repayment_method,
    )
    commercial_prepayment_allowed_after_month = max(
        1,
        min(scenario.loan_years * 12, scenario.commercial_prepayment_allowed_after_month),
    )
    commercial_prepayment_start_month = max(
        commercial_prepayment_allowed_after_month,
        max(1, min(scenario.loan_years * 12, scenario.commercial_prepayment_start_month)),
    )
    commercial_prepayment = (
        max(0.0, scenario.commercial_prepayment_monthly_amount)
        if commercial_prepayment_mode == "manual" and financing_mix[4] > 0
        else 0.0
    )
    return post_purchase_cash_stress(
        household=household,
        rules=rules,
        purchase_month=purchase_month,
        starting_cash=starting_cash,
        starting_pf_balance=starting_pf_balance,
        total_monthly_payment=commercial_payment.first_month_payment + provident_payment.first_month_payment,
        provident_monthly_payment=provident_payment.first_month_payment,
        expense_at_month=expense_at_month,
        income_at_month=income_at_month,
        car_monthly_cash_cost_at=car_monthly_cash_cost_at,
        car_down_payment_at=car_down_payment_at,
        extra_monthly_payment=commercial_prepayment,
        extra_payment_start_month=commercial_prepayment_start_month,
        strategy_preference=strategy_preference,
    )


def choose_provident_repayment_choice(
    *,
    household: HouseholdData,
    rules: RulePackData,
    provident_loan: float,
    effective_provident_rate: float,
    provident_loan_years: int,
    default_repayment_method: str,
    use_manual_mix: bool,
    commercial_first_month_payment: float,
    post_purchase_income_net: float,
    post_purchase_pf_deposit: float,
    post_purchase_monthly_expense: float,
    post_purchase_car_cost: float,
    immediate_commercial_prepayment: float,
    purchase_month: int,
    starting_pf_balance: float,
    strategy_preference: str,
) -> ProvidentRepaymentChoice:
    equal_installment_payment = calculate_loan(
        provident_loan,
        effective_provident_rate,
        provident_loan_years,
        "equal_installment",
    )
    equal_principal_payment = calculate_loan(
        provident_loan,
        effective_provident_rate,
        provident_loan_years,
        "equal_principal",
    )
    selected_method = default_repayment_method
    if (
        provident_loan > 0
        and not use_manual_mix
        and selected_method != "equal_principal"
        and equal_principal_payment.first_month_payment > 0
    ):
        equal_principal_total_payment = commercial_first_month_payment + equal_principal_payment.first_month_payment
        equal_principal_free_cash_flow = (
            post_purchase_income_net
            - post_purchase_monthly_expense
            - household.monthly_debt_payment
            - post_purchase_car_cost
            - equal_principal_total_payment
            - immediate_commercial_prepayment
        )
        equal_principal_pf_relief, _ = post_purchase_pf_strategy(
            household=household,
            purchase_month=purchase_month,
            starting_pf_balance=starting_pf_balance,
            free_cash_flow=equal_principal_free_cash_flow,
            monthly_pf_deposit=post_purchase_pf_deposit,
            provident_monthly_payment=equal_principal_payment.first_month_payment,
            total_monthly_payment=equal_principal_total_payment,
            post_purchase_monthly_expense=post_purchase_monthly_expense,
            rules=rules,
            strategy_preference=strategy_preference,
        )
        pf_income_covers_material_share = post_purchase_pf_deposit >= equal_principal_payment.first_month_payment * 0.55
        if equal_principal_free_cash_flow + equal_principal_pf_relief >= 0 and pf_income_covers_material_share:
            selected_method = "equal_principal"

    selected_payment = (
        equal_principal_payment
        if selected_method == "equal_principal"
        else equal_installment_payment
    )
    return ProvidentRepaymentChoice(
        equal_installment_payment=equal_installment_payment,
        equal_principal_payment=equal_principal_payment,
        selected_method=selected_method,
        selected_payment=selected_payment,
        interest_saving_if_equal_principal=max(
            0.0,
            equal_installment_payment.total_interest - equal_principal_payment.total_interest,
        ),
        equal_principal_extra_first_payment=max(
            0.0,
            equal_principal_payment.first_month_payment - equal_installment_payment.first_month_payment,
        ),
    )


def build_renovation_funding_plan(
    scenario: ScenarioData,
    *,
    cash_after_purchase: float,
    required_liquidity_reserve: float,
    post_purchase_cash_flow: float,
) -> RenovationFundingPlan:
    included_upfront = scenario.renovation_funding_mode == "upfront_cash"
    saving_months: int | None = 0
    monthly_saving = 0.0
    if not included_upfront and scenario.renovation_cost > 0:
        monthly_saving = max(0.0, post_purchase_cash_flow)
        immediate_renovation_cash = max(0.0, cash_after_purchase - required_liquidity_reserve)
        renovation_remaining = max(0.0, scenario.renovation_cost - immediate_renovation_cash)
        if renovation_remaining <= 0:
            saving_months = 0
        elif monthly_saving > 0:
            saving_months = ceil(renovation_remaining / monthly_saving)
        else:
            saving_months = None
    return RenovationFundingPlan(
        included_upfront=included_upfront,
        saving_months=saving_months,
        monthly_saving=monthly_saving,
    )


def provident_repayment_advice(
    *,
    provident_loan: float,
    selected_provident_repayment_method: str,
    equal_principal_extra_first_payment: float,
    provident_interest_saving_if_equal_principal: float,
    equal_principal_cash_flow: float,
) -> str:
    if provident_loan <= 0:
        return "本方案不使用公积金贷款，无需比较公积金还款方式。"
    if selected_provident_repayment_method == "equal_principal":
        return (
            f"当前已采用等额本金；相比等额本息首月多付约 {round(equal_principal_extra_first_payment)}，"
            f"但公积金贷款总利息少约 {round(provident_interest_saving_if_equal_principal)}，本金下降更快。"
        )
    if equal_principal_cash_flow >= 0:
        return (
            f"若切换公积金贷为等额本金，首月现金压力约增加 {round(equal_principal_extra_first_payment)}，"
            f"但总利息可少约 {round(provident_interest_saving_if_equal_principal)}，本金下降更快；当前策略后现金流可覆盖，可作为优先比较项。"
        )
    return (
        f"等额本金可少付公积金利息约 {round(provident_interest_saving_if_equal_principal)}，"
        f"但首月现金压力增加约 {round(equal_principal_extra_first_payment)}，当前现金流不宜自动切换。"
    )


def build_purchase_happiness_breakdown(
    *,
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    months: int | None,
    price: float,
    required_liquidity_reserve: float,
    upfront_cash: float,
    cash_after_transaction: float,
    cash_after_purchase: float,
    minimum_cash_balance: float,
    investment_balance_after_purchase: float,
    post_purchase_cash_flow: float,
    post_purchase_cash_flow_with_pf: float,
    post_purchase_monthly_expense: float,
    post_purchase_income_net: float,
    post_purchase_car_cost: float,
    pre_home_vehicle_down_payment: float,
    pre_home_vehicle_monthly_cost: float,
    dti: float,
    total_monthly_payment: float,
    commercial_prepayment_monthly: float,
    commercial_loan: float,
    commercial_interest: float,
    provident_interest: float,
    cash_stress_ok: bool,
    cash_stress_shortfall: float,
    renovation_included_upfront: bool,
    renovation_saving_months: int | None,
    monthly_pf_withdrawal_mode: str,
) -> tuple[float, list[dict[str, float | str]]]:
    wait_component = wait_score(months, 120)
    stress_liquidity_floor = min(required_liquidity_reserve, max(1.0, post_purchase_monthly_expense * 3))
    liquidity_component = ratio_score(min(cash_after_transaction, minimum_cash_balance), stress_liquidity_floor)
    post_extract_liquidity_component = ratio_score(cash_after_purchase, required_liquidity_reserve)
    cash_shortfall_component = clamp_score(
        10 - max(0.0, cash_stress_shortfall, -minimum_cash_balance) / max(required_liquidity_reserve, 1.0) * 10
    )
    investment_continuity_component = ratio_score(
        investment_balance_after_purchase,
        max(required_liquidity_reserve * 0.5, household.investments * 0.25, 1.0),
    )
    flow_component = cash_flow_score(post_purchase_cash_flow_with_pf, post_purchase_monthly_expense)
    dti_component = dti_score(dti)
    payment_pressure_component = clamp_score(
        10 - (total_monthly_payment + commercial_prepayment_monthly) / max(post_purchase_income_net, 1) / 0.45 * 10
    )
    commercial_pressure_component = clamp_score(10 - commercial_loan / max(price, 1) / 0.65 * 10)
    interest_component = clamp_score(10 - (commercial_interest + provident_interest) / max(price, 1) / 0.55 * 10)
    vehicle_convenience_component = (
        clamp_score(household.car_plan.happiness_score)
        if post_purchase_car_cost > 0
        else clamp_score(7 - (household.car_plan.no_car_monthly_commute_cost or 0) / max(post_purchase_income_net, 1) / 0.08 * 3)
    )
    vehicle_home_tradeoff_component = clamp_score(
        10
        - pre_home_vehicle_down_payment / max(required_liquidity_reserve + upfront_cash, 1.0) * 8
        - pre_home_vehicle_monthly_cost / max(post_purchase_income_net, 1.0) / 0.18 * 4
    )
    loan_interest_pressure_component = clamp_score(commercial_pressure_component * 0.55 + interest_component * 0.45)
    renovation_component = renovation_readiness_score(
        scenario.renovation_cost,
        renovation_included_upfront,
        renovation_saving_months,
    )
    stress_component = stress_resilience_score(cash_stress_ok, cash_stress_shortfall, required_liquidity_reserve)
    weights = purchase_happiness_weights(rules, scenario.liquidity_priority_score)

    return weighted_happiness_breakdown(
        [
            {
                "key": "living_quality",
                "name": "居住体验",
                "category": "life",
                "score": scenario.happiness_score,
                "note": "目标房源的户型、面积、社区、楼龄和主观居住满意度。",
            },
            {
                "key": "commute",
                "name": "通勤便利",
                "category": "life",
                "score": scenario.commute_score,
                "note": "通勤时间、稳定性和日常时间成本。",
            },
            {
                "key": "education",
                "name": "教育匹配",
                "category": "life",
                "score": scenario.school_score,
                "note": "教育资源与家庭长期确定性。",
            },
            {
                "key": "vehicle_convenience",
                "name": "用车便利",
                "category": "life",
                "score": vehicle_convenience_component,
                "note": (
                    f"已纳入买车后的便利度约 {round(household.car_plan.happiness_score, 1)} 分。"
                    if post_purchase_car_cost > 0
                    else f"未购车时按无车通勤成本 {round(household.car_plan.no_car_monthly_commute_cost or 0)} 估算便利度。"
                ),
            },
            {
                "key": "vehicle_home_tradeoff",
                "name": "买车对买房影响",
                "category": "timing",
                "score": vehicle_home_tradeoff_component,
                "note": (
                    "买房前没有车辆首付或车贷现金压力。"
                    if pre_home_vehicle_down_payment <= 0 and pre_home_vehicle_monthly_cost <= 0
                    else f"买房前车辆首付约 {round(pre_home_vehicle_down_payment)}，购房节点月车辆现金成本约 {round(pre_home_vehicle_monthly_cost)}，会占用首付和月结余。"
                ),
            },
            {
                "key": "transaction_liquidity",
                "name": "买房当天现金安全",
                "category": "finance",
                "score": liquidity_component,
                "note": f"买房当天现金 {round(cash_after_transaction)}，压力期最低现金 {round(minimum_cash_balance)}，基础安全垫 {round(required_liquidity_reserve)}。",
            },
            {
                "key": "post_purchase_liquidity",
                "name": "买后现金安全",
                "category": "finance",
                "score": post_extract_liquidity_component,
                "note": f"买后现金 {round(cash_after_purchase)}，目标安全垫 {round(required_liquidity_reserve)}。",
            },
            {
                "key": "investment_continuity",
                "name": "长期理财连续性",
                "category": "finance",
                "score": investment_continuity_component,
                "note": f"买房后投资账户约 {round(investment_balance_after_purchase)}；保留部分长期投资可降低把未来收益完全牺牲给首付的压力。",
            },
            {
                "key": "monthly_cashflow",
                "name": "买后月度自由现金流",
                "category": "finance",
                "score": flow_component,
                "note": f"买后自由现金月结余 {round(post_purchase_cash_flow)}；公积金策略为{post_purchase_pf_withdrawal_label(monthly_pf_withdrawal_mode)}，策略后现金压力约 {round(post_purchase_cash_flow_with_pf)}。",
            },
            {
                "key": "debt_to_income",
                "name": "负债收入比",
                "category": "finance",
                "score": dti_component,
                "note": f"负债收入比 {round(dti * 100, 1)}%。",
            },
            {
                "key": "monthly_payment_pressure",
                "name": "月供压力",
                "category": "finance",
                "score": payment_pressure_component,
                "note": f"房贷合同月供 {round(total_monthly_payment)}，商贷额外还本 {round(commercial_prepayment_monthly)}。",
            },
            {
                "key": "loan_interest_pressure",
                "name": "贷款利息与商贷暴露",
                "category": "finance",
                "score": loan_interest_pressure_component,
                "note": f"商贷 {round(commercial_loan)}，全周期利息约 {round(commercial_interest + provident_interest)}。",
            },
            {
                "key": "cash_shortfall",
                "name": "现金缺口风险",
                "category": "resilience",
                "score": cash_shortfall_component,
                "note": (
                    "当前策略没有形成现金账户穿底或安全垫缺口。"
                    if max(0.0, cash_stress_shortfall, -minimum_cash_balance) <= 0
                    else f"综合交易、购后推演和压力情景，最大现金缺口约 {round(max(0.0, cash_stress_shortfall, -minimum_cash_balance))}。"
                ),
            },
            {
                "key": "waiting_time",
                "name": "等待时间",
                "category": "timing",
                "score": wait_component,
                "note": "越早可执行，对家庭确定性和机会成本越友好。",
            },
            {
                "key": "renovation_readiness",
                "name": "装修可达性",
                "category": "timing",
                "score": renovation_component,
                "note": (
                    "未设置装修预算。"
                    if scenario.renovation_cost <= 0
                    else "装修资金已计入交易现金。"
                    if renovation_included_upfront
                    else (
                        "买后现金流暂不足以估算装修启动时间。"
                        if renovation_saving_months is None
                        else f"预计买后 {renovation_saving_months} 个月可启动装修。"
                    )
                ),
            },
            {
                "key": "stress_resilience",
                "name": "压力测试韧性",
                "category": "resilience",
                "score": stress_component,
                "note": (
                    "压力情景下现金账户没有跌破 0。"
                    if cash_stress_ok
                    else f"压力情景现金缺口约 {round(cash_stress_shortfall)}。"
                ),
            },
        ],
        weights,
    )


def find_purchase_candidate(
    *,
    household: HouseholdData,
    variant_spec: PurchaseVariantSpec,
    micro_ratio_candidates: list[float],
    search_start_month: int,
    price: float,
    target_commercial_loan: float,
    compute_mix_at: Callable[[int, float], tuple[float, float, float, float, float, float, float]],
    purchase_state_for_mix: Callable[
        [int, tuple[float, float, float, float, float, float, float]],
        tuple[float, float, float, float, float, float, float, float, float, float, float],
    ],
    cash_stress_for_mix: Callable[
        [int, tuple[float, float, float, float, float, float, float], float, float],
        tuple[float, int | None, bool],
    ],
    expense_at_month: Callable[[int], float],
    horizon_months: int = 360,
) -> PurchaseCandidateSearchResult:
    best_failed_result: PurchaseCandidate | None = None
    best_failed_rank: tuple[float, int, float] | None = None
    selected_candidate: PurchaseCandidate | None = None

    for candidate_month in range(search_start_month, horizon_months + 1):
        required_liquidity_reserve = max(
            0.0,
            expense_at_month(candidate_month) * household.required_liquidity_months,
        )
        candidate_targets = (
            [price * ratio for ratio in micro_ratio_candidates]
            if variant_spec.use_micro_strategy
            else [target_commercial_loan]
        )
        for commercial_target in candidate_targets:
            candidate_mix = compute_mix_at(candidate_month, commercial_target)
            (
                candidate_pf_upfront,
                candidate_family_pf_upfront,
                candidate_pf_post,
                candidate_cash_before_purchase,
                candidate_investment_before_purchase,
                candidate_investment_sell_gross,
                candidate_investment_sell_proceeds,
                candidate_investment_after_purchase,
                candidate_cash_after_transaction,
                candidate_cash_after_purchase,
                candidate_pf_after_extract,
            ) = purchase_state_for_mix(candidate_month, candidate_mix)
            transaction_shortfall = max(0.0, required_liquidity_reserve - candidate_cash_after_transaction)
            if transaction_shortfall > 0:
                candidate_minimum_cash_balance = min(candidate_cash_after_transaction, candidate_cash_after_purchase)
                candidate_minimum_cash_balance_month = candidate_month
                candidate_cash_stress_ok = False
            else:
                (
                    candidate_minimum_cash_balance,
                    candidate_minimum_cash_balance_month,
                    candidate_cash_stress_ok,
                ) = cash_stress_for_mix(
                    candidate_month,
                    candidate_mix,
                    candidate_cash_after_purchase,
                    candidate_pf_after_extract,
                )
            candidate = PurchaseCandidate(
                purchase_month=candidate_month,
                mix=candidate_mix,
                pf_upfront_extractable=candidate_pf_upfront,
                family_pf_upfront_extractable=candidate_family_pf_upfront,
                pf_post_transaction_extractable=candidate_pf_post,
                cash_account_before_purchase=candidate_cash_before_purchase,
                investment_balance_before_purchase=candidate_investment_before_purchase,
                investment_sell_gross_at_purchase=candidate_investment_sell_gross,
                investment_sell_proceeds_at_purchase=candidate_investment_sell_proceeds,
                investment_balance_after_purchase=candidate_investment_after_purchase,
                cash_after_transaction=candidate_cash_after_transaction,
                cash_after_purchase=candidate_cash_after_purchase,
                pf_after_extract=candidate_pf_after_extract,
                minimum_cash_balance=candidate_minimum_cash_balance,
                minimum_cash_balance_month=candidate_minimum_cash_balance_month,
                cash_stress_ok=candidate_cash_stress_ok and transaction_shortfall <= 0,
                cash_stress_shortfall=max(transaction_shortfall, -candidate_minimum_cash_balance, 0.0),
            )
            if candidate.cash_stress_ok:
                selected_candidate = candidate
                break
            candidate_rank = (
                candidate.cash_stress_shortfall,
                candidate_month,
                candidate.mix[4],
            )
            if best_failed_rank is None or candidate_rank < best_failed_rank:
                best_failed_rank = candidate_rank
                best_failed_result = candidate
        if selected_candidate is not None:
            return PurchaseCandidateSearchResult(
                months=selected_candidate.purchase_month,
                candidate=selected_candidate,
                required_liquidity_reserve=required_liquidity_reserve,
            )

    if best_failed_result is not None:
        return PurchaseCandidateSearchResult(
            months=None,
            candidate=best_failed_result,
            required_liquidity_reserve=max(
                0.0,
                expense_at_month(best_failed_result.purchase_month) * household.required_liquidity_months,
            ),
        )

    fallback_target = price * micro_ratio_candidates[-1] if variant_spec.use_micro_strategy else target_commercial_loan
    fallback_mix = compute_mix_at(horizon_months, fallback_target)
    (
        pf_upfront_extractable,
        family_pf_upfront_extractable,
        pf_post_transaction_extractable,
        cash_account_before_purchase,
        investment_balance_before_purchase,
        investment_sell_gross_at_purchase,
        investment_sell_proceeds_at_purchase,
        investment_balance_after_purchase,
        cash_after_transaction,
        cash_after_purchase,
        pf_after_extract,
    ) = purchase_state_for_mix(horizon_months, fallback_mix)
    required_liquidity_reserve = max(
        0.0,
        expense_at_month(horizon_months) * household.required_liquidity_months,
    )
    minimum_cash_balance, minimum_cash_balance_month, _ = cash_stress_for_mix(
        horizon_months,
        fallback_mix,
        cash_after_purchase,
        pf_after_extract,
    )
    return PurchaseCandidateSearchResult(
        months=None,
        required_liquidity_reserve=required_liquidity_reserve,
        candidate=PurchaseCandidate(
            purchase_month=horizon_months,
            mix=fallback_mix,
            pf_upfront_extractable=pf_upfront_extractable,
            family_pf_upfront_extractable=family_pf_upfront_extractable,
            pf_post_transaction_extractable=pf_post_transaction_extractable,
            cash_account_before_purchase=cash_account_before_purchase,
            investment_balance_before_purchase=investment_balance_before_purchase,
            investment_sell_gross_at_purchase=investment_sell_gross_at_purchase,
            investment_sell_proceeds_at_purchase=investment_sell_proceeds_at_purchase,
            investment_balance_after_purchase=investment_balance_after_purchase,
            cash_after_transaction=cash_after_transaction,
            cash_after_purchase=cash_after_purchase,
            pf_after_extract=pf_after_extract,
            minimum_cash_balance=minimum_cash_balance,
            minimum_cash_balance_month=minimum_cash_balance_month,
            cash_stress_ok=False,
            cash_stress_shortfall=max(
                0.0,
                required_liquidity_reserve - cash_after_transaction,
                -minimum_cash_balance,
            ),
        ),
    )


def _money_text(amount: float) -> str:
    if abs(amount) >= 10000:
        return f"{amount / 10000:.1f} 万"
    return f"{amount:.0f} 元"


def _repayment_method_label(method: str) -> str:
    return "等额本金" if method == "equal_principal" else "等额本息"


def family_down_payment_support_mode(household: HouseholdData) -> str:
    mode = str(getattr(household, "family_down_payment_support_mode", "provident") or "provident")
    return mode if mode in {"provident", "savings"} else "provident"


def family_down_payment_support_label(household: HouseholdData) -> str:
    if not household.family_provident_support_enabled:
        return ""
    configured = (household.family_provident_support_label or "").strip()
    if configured:
        return configured
    return "亲属积蓄首付支持" if family_down_payment_support_mode(household) == "savings" else "亲属异地公积金首付支持"


def family_down_payment_upfront_support(
    household: HouseholdData,
    scenario: ScenarioData,
    purchase_month: int,
    remaining_upfront_cash_required: float,
) -> float:
    if not household.family_provident_support_enabled:
        return 0.0
    if remaining_upfront_cash_required <= 0:
        return 0.0
    if family_down_payment_support_mode(household) == "savings":
        return round(min(max(0.0, household.family_savings_support_amount), remaining_upfront_cash_required), 2)
    if not is_new_home_property(scenario):
        return 0.0
    monthly_deposit = max(0.0, household.family_provident_monthly_salary * household.family_provident_total_rate)
    available_balance = max(0.0, household.family_provident_initial_balance + monthly_deposit * max(0, purchase_month))
    return round(min(available_balance, remaining_upfront_cash_required), 2)


def purchase_cash_state_at_month(
    *,
    month: int,
    upfront_cash_required: float,
    planned_down_payment: float,
    household: HouseholdData,
    rules: RulePackData,
    initial_cash: float,
    monthly_cash_savings: float,
    monthly_cash_savings_at: Callable[[int], float] | None = None,
    monthly_pf_net_growth: float,
    monthly_pf_net_growth_at: Callable[[int], float] | None = None,
    annual_return: float,
    property_price: float,
    scenario: ScenarioData,
    initial_provident_balance: float,
    monthly_household_expense_at: Callable[[int], float],
    family_down_payment_upfront_support: Callable[[int, float], float],
    cash_value_by_month: list[float] | None = None,
    investment_value_by_month: list[float] | None = None,
    pf_value_by_month: list[float] | None = None,
) -> tuple[float, float, float, float, float, float, float, float, float, float, float]:
    buy_fee_rate = _clamp(household.investment_buy_fee_rate, 0.0, 0.05)
    sell_fee_rate = _clamp(household.investment_sell_fee_rate, 0.0, 0.05)
    cash_value = (
        cash_value_by_month[month]
        if cash_value_by_month is not None and month < len(cash_value_by_month)
        else (
            future_cash_value_with_schedule(initial_cash, annual_return, month, monthly_cash_savings_at, buy_fee_rate)
            if monthly_cash_savings_at is not None
            else future_cash_value(initial_cash, monthly_cash_savings, annual_return, month)
        )
    )
    investment_value = (
        investment_value_by_month[month]
        if investment_value_by_month is not None and month < len(investment_value_by_month)
        else 0.0
    )
    if pf_value_by_month is not None and month < len(pf_value_by_month):
        pf_available = pf_value_by_month[month]
    else:
        pf_interest_rate = float(rules.params.get("provident_balance_annual_interest_rate", 0.015))
        pf_available = (
            future_provident_value_with_schedule(
                initial_provident_balance,
                pf_interest_rate,
                month,
                monthly_pf_net_growth_at,
            )
            if monthly_pf_net_growth_at is not None
            else future_provident_value(
                initial_provident_balance,
                monthly_pf_net_growth,
                pf_interest_rate,
                month,
            )
        )
    default_upfront_ratio = float(rules.params.get("provident_upfront_purchase_extract_ratio", 0.0))
    if is_second_hand_property(scenario):
        upfront_ratio_key = "provident_upfront_purchase_extract_ratio_second_hand"
        ratio_fallback = 0.0
    elif is_new_home_property(scenario):
        upfront_ratio_key = "provident_upfront_purchase_extract_ratio_new_home"
        ratio_fallback = 1.0
    else:
        upfront_ratio_key = "provident_upfront_purchase_extract_ratio"
        ratio_fallback = default_upfront_ratio
    upfront_extract_ratio = max(
        0,
        min(1, float(rules.params.get(upfront_ratio_key, ratio_fallback))),
    )
    post_transaction_extract_ratio = max(
        0,
        min(1, float(rules.params.get("provident_post_transaction_extract_ratio", 1.0))),
    )
    pf_upfront_extractable = min(pf_available, planned_down_payment * upfront_extract_ratio)
    family_pf_upfront_extractable = family_down_payment_upfront_support(
        month,
        max(0.0, upfront_cash_required - pf_upfront_extractable),
    )
    required_cash_after_pf = max(0, upfront_cash_required - pf_upfront_extractable - family_pf_upfront_extractable)
    withdrawal = investment_withdrawal_at_purchase(
        scenario=scenario,
        cash_before_transaction=cash_value,
        investment_before_transaction=investment_value,
        required_cash_after_pf=required_cash_after_pf,
        required_liquidity_reserve=monthly_household_expense_at(month) * household.required_liquidity_months,
        sell_fee_rate=sell_fee_rate,
        investment_enabled=household.investment_plan_name != "cash_only",
    )
    cash_after_transaction = withdrawal.cash_after_transaction
    pf_after_upfront_extract = max(0, pf_available - pf_upfront_extractable)
    pf_post_transaction_extractable = min(pf_after_upfront_extract, property_price * post_transaction_extract_ratio)
    return (
        round(pf_upfront_extractable, 2),
        round(family_pf_upfront_extractable, 2),
        round(pf_post_transaction_extractable, 2),
        round(withdrawal.cash_before_transaction, 2),
        round(withdrawal.investment_before_transaction, 2),
        round(withdrawal.gross_sell, 2),
        round(withdrawal.sell_proceeds, 2),
        round(withdrawal.investment_after_transaction, 2),
        round(cash_after_transaction, 2),
        round(cash_after_transaction + pf_post_transaction_extractable, 2),
        round(pf_after_upfront_extract - pf_post_transaction_extractable, 2),
    )


def build_purchase_plan_analyses(
    household: HouseholdData,
    scenario: ScenarioData,
    rules: RulePackData,
    *,
    tax_summaries: Sequence[TaxSummaryLike],
    car_loan: CarLoanSummary,
    taxes_and_fees: float,
    income_profile_provider: Callable[[int], MonthlyIncomeProfileLike],
    expense_provider: Callable[[int, int | None], float],
    rent_withdrawal_before_purchase: Callable[[HouseholdData], float],
    quarterly_rent_withdrawal_before_purchase_at: Callable[[HouseholdData, int], float],
    vehicle_states_provider: Callable[[], list[VehicleLoanState]],
    car_monthly_cash_cost_provider: Callable[[list[VehicleLoanState], int], float],
    car_down_payment_provider: Callable[[list[VehicleLoanState], int], float],
    family_down_payment_upfront_support_provider: Callable[[int, float], float],
    initial_provident_balance: float,
    planning_window_delay_provider: Callable[[str], int | None] | None = None,
) -> list[PurchasePlanAnalysis]:
    price = scenario.total_price
    pf_account_strategy_preference = effective_pf_account_strategy(scenario, rules, household)
    selected_provident_loan_years, provident_year_reasons = policy_provident_loan_years(household, scenario, rules)
    effective_provident_rate = policy_provident_loan_rate(household, scenario, rules, selected_provident_loan_years)
    deed_tax_rate, broker_fee_rate, deed_tax_amount, broker_fee_amount = housing_transaction_rate_amounts(
        household,
        scenario,
        rules,
    )
    micro_ratio_candidates = micro_commercial_ratio_candidates(scenario, rules)
    planning_context = build_purchase_planning_context(
        household=household,
        scenario=scenario,
        rules=rules,
        tax_summaries=tax_summaries,
        income_profile_provider=income_profile_provider,
        expense_provider=expense_provider,
        rent_withdrawal_before_purchase=rent_withdrawal_before_purchase,
        quarterly_rent_withdrawal_before_purchase_at=quarterly_rent_withdrawal_before_purchase_at,
        vehicle_states_provider=vehicle_states_provider,
        car_monthly_cash_cost_provider=car_monthly_cash_cost_provider,
        car_down_payment_provider=car_down_payment_provider,
        family_down_payment_upfront_support=family_down_payment_upfront_support_provider,
        initial_provident_balance=initial_provident_balance,
    )
    required_liquidity_reserve = planning_context.required_liquidity_reserve
    vehicle_states = planning_context.vehicle_states
    expense_at_month = planning_context.expense_at_month
    income_at_month = planning_context.income_at_month
    car_monthly_cash_cost_at = planning_context.car_monthly_cash_cost_at
    car_down_payment_at = planning_context.car_down_payment_at

    variant_specs = purchase_variant_specs(scenario, rules)

    scenario_prepayment_mode = scenario_commercial_prepayment_mode(scenario)

    analyses: list[PurchasePlanAnalysis] = []
    for variant_spec in variant_specs:
        name = variant_spec.name
        description = variant_spec.description
        target_commercial = variant_spec.target_commercial_loan
        use_min_down = variant_spec.use_min_down_payment
        use_manual_mix = variant_spec.use_manual_mix
        use_micro_strategy = variant_spec.use_micro_strategy
        provident_cap = 0.0
        provident_policy_bonus = 0.0
        min_down_payment = 0.0
        planned_down = 0.0
        commercial_loan = 0.0
        provident_loan = 0.0
        upfront_cash = 0.0
        months: int | None = 0
        minimum_cash_balance = 0.0
        minimum_cash_balance_month: int | None = 0
        cash_stress_ok = True
        cash_stress_shortfall = 0.0
        pf_upfront_extractable = 0.0
        family_pf_upfront_extractable = 0.0
        pf_post_transaction_extractable = 0.0
        pf_extractable = 0.0
        cash_account_before_purchase = 0.0
        investment_balance_before_purchase = 0.0
        investment_sell_gross_at_purchase = 0.0
        investment_sell_proceeds_at_purchase = 0.0
        investment_balance_after_purchase = 0.0
        cash_after_transaction = 0.0
        cash_after_purchase = 0.0
        pf_after_extract = 0.0

        scenario_window_start_delay = (planning_window_delay_provider(scenario.planning_window_start_month) if planning_window_delay_provider else None) or 0
        search_start_month = min(360, max(0, scenario.manual_purchase_delay_months, scenario_window_start_delay))
        candidate_search = planning_context.find_candidate(
            variant_spec=variant_spec,
            micro_ratio_candidates=micro_ratio_candidates,
            search_start_month=search_start_month,
            target_commercial_loan=target_commercial,
            taxes_and_fees=taxes_and_fees,
            effective_provident_rate=effective_provident_rate,
            provident_loan_years=selected_provident_loan_years,
            commercial_repayment_method=scenario_commercial_repayment_method(scenario),
            provident_repayment_method=scenario_provident_repayment_method(scenario),
            commercial_prepayment_mode=scenario_prepayment_mode,
            strategy_preference=pf_account_strategy_preference,
        )
        candidate_result = candidate_search.candidate
        months = candidate_search.months
        required_liquidity_reserve = candidate_search.required_liquidity_reserve
        (
            provident_cap,
            provident_policy_bonus,
            min_down_payment,
            planned_down,
            commercial_loan,
            provident_loan,
            upfront_cash,
        ) = candidate_result.mix
        pf_upfront_extractable = candidate_result.pf_upfront_extractable
        family_pf_upfront_extractable = candidate_result.family_pf_upfront_extractable
        pf_post_transaction_extractable = candidate_result.pf_post_transaction_extractable
        cash_account_before_purchase = candidate_result.cash_account_before_purchase
        investment_balance_before_purchase = candidate_result.investment_balance_before_purchase
        investment_sell_gross_at_purchase = candidate_result.investment_sell_gross_at_purchase
        investment_sell_proceeds_at_purchase = candidate_result.investment_sell_proceeds_at_purchase
        investment_balance_after_purchase = candidate_result.investment_balance_after_purchase
        cash_after_transaction = candidate_result.cash_after_transaction
        cash_after_purchase = candidate_result.cash_after_purchase
        pf_after_extract = candidate_result.pf_after_extract
        minimum_cash_balance = candidate_result.minimum_cash_balance
        minimum_cash_balance_month = candidate_result.minimum_cash_balance_month
        cash_stress_ok = candidate_result.cash_stress_ok
        cash_stress_shortfall = candidate_result.cash_stress_shortfall
        pf_extractable = pf_upfront_extractable + family_pf_upfront_extractable + pf_post_transaction_extractable

        selected_commercial_prepayment_mode = scenario_prepayment_mode
        commercial_prepayment_plan = build_commercial_prepayment_plan(
            scenario,
            commercial_loan=commercial_loan,
            commercial_repayment_method=scenario_commercial_repayment_method(scenario),
            commercial_prepayment_mode=selected_commercial_prepayment_mode,
        )
        commercial_payment = commercial_prepayment_plan.regular_payment
        commercial_prepayment_allowed_after_month = commercial_prepayment_plan.allowed_after_month
        commercial_prepayment_start_month = commercial_prepayment_plan.start_month
        commercial_prepayment_monthly = commercial_prepayment_plan.monthly_amount
        immediate_commercial_prepayment = commercial_prepayment_plan.immediate_monthly_amount
        commercial_projection = commercial_prepayment_plan.projection
        commercial_interest = commercial_prepayment_plan.interest
        post_purchase_month = months if months is not None else 360
        post_purchase_monthly_expense = expense_at_month(post_purchase_month)
        post_purchase_income = income_at_month(post_purchase_month)
        post_purchase_car_cost = car_monthly_cash_cost_at(post_purchase_month)
        provident_repayment_choice = choose_provident_repayment_choice(
            household=household,
            rules=rules,
            provident_loan=provident_loan,
            effective_provident_rate=effective_provident_rate,
            provident_loan_years=selected_provident_loan_years,
            default_repayment_method=scenario_provident_repayment_method(scenario),
            use_manual_mix=use_manual_mix,
            commercial_first_month_payment=commercial_payment.first_month_payment,
            post_purchase_income_net=post_purchase_income.net_income,
            post_purchase_pf_deposit=post_purchase_income.monthly_pf_deposit,
            post_purchase_monthly_expense=post_purchase_monthly_expense,
            post_purchase_car_cost=post_purchase_car_cost,
            immediate_commercial_prepayment=immediate_commercial_prepayment,
            purchase_month=post_purchase_month,
            starting_pf_balance=pf_after_extract,
            strategy_preference=pf_account_strategy_preference,
        )
        provident_equal_installment_payment = provident_repayment_choice.equal_installment_payment
        provident_equal_principal_payment = provident_repayment_choice.equal_principal_payment
        selected_provident_repayment_method = provident_repayment_choice.selected_method
        provident_payment = provident_repayment_choice.selected_payment
        total_monthly_payment = commercial_payment.first_month_payment + provident_payment.first_month_payment
        post_purchase_cash_flow = (
            post_purchase_income.net_income
            - post_purchase_monthly_expense
            - household.monthly_debt_payment
            - post_purchase_car_cost
            - total_monthly_payment
            - immediate_commercial_prepayment
        )
        monthly_pf_withdrawal, monthly_pf_withdrawal_mode = post_purchase_pf_strategy(
            household=household,
            purchase_month=post_purchase_month,
            starting_pf_balance=pf_after_extract,
            free_cash_flow=post_purchase_cash_flow,
            monthly_pf_deposit=post_purchase_income.monthly_pf_deposit,
            provident_monthly_payment=provident_payment.first_month_payment,
            total_monthly_payment=total_monthly_payment,
            post_purchase_monthly_expense=post_purchase_monthly_expense,
            rules=rules,
            strategy_preference=pf_account_strategy_preference,
        )
        post_purchase_cash_flow_with_pf = post_purchase_cash_flow + monthly_pf_withdrawal
        if selected_commercial_prepayment_mode == "auto" and commercial_loan > 0:
            (
                commercial_auto_prepayment_enabled,
                commercial_prepayment_start_month,
                commercial_prepayment_allowed_after_month,
                commercial_prepayment_monthly,
            ) = choose_auto_commercial_prepayment(
                scenario,
                commercial_loan=commercial_loan,
                regular_payment=commercial_payment,
                post_purchase_cash_flow_with_pf=post_purchase_cash_flow_with_pf,
                post_purchase_monthly_expense=post_purchase_monthly_expense,
                required_liquidity_reserve=required_liquidity_reserve,
                cash_after_purchase=cash_after_purchase,
                minimum_cash_balance=minimum_cash_balance,
                commercial_repayment_method=scenario_commercial_repayment_method(scenario),
                investment_buy_fee_rate=household.investment_buy_fee_rate,
                investment_sell_fee_rate=household.investment_sell_fee_rate,
            )
            if not commercial_auto_prepayment_enabled:
                commercial_prepayment_monthly = 0.0
            commercial_prepayment_plan = build_commercial_prepayment_plan(
                scenario,
                commercial_loan=commercial_loan,
                commercial_repayment_method=scenario_commercial_repayment_method(scenario),
                commercial_prepayment_mode=selected_commercial_prepayment_mode,
                prepayment_monthly_amount=commercial_prepayment_monthly,
                prepayment_start_month=commercial_prepayment_start_month,
                prepayment_allowed_after_month=commercial_prepayment_allowed_after_month,
            )
            commercial_prepayment_allowed_after_month = commercial_prepayment_plan.allowed_after_month
            commercial_prepayment_start_month = commercial_prepayment_plan.start_month
            commercial_prepayment_monthly = commercial_prepayment_plan.monthly_amount
            immediate_commercial_prepayment = commercial_prepayment_plan.immediate_monthly_amount
            commercial_projection = commercial_prepayment_plan.projection
            commercial_interest = commercial_prepayment_plan.interest
            if commercial_prepayment_monthly > 0 and months is not None:
                minimum_cash_balance, minimum_cash_balance_month, cash_stress_ok = post_purchase_cash_stress(
                    household=household,
                    rules=rules,
                    purchase_month=post_purchase_month,
                    starting_cash=cash_after_purchase,
                    starting_pf_balance=pf_after_extract,
                    total_monthly_payment=total_monthly_payment,
                    provident_monthly_payment=provident_payment.first_month_payment,
                    expense_at_month=expense_at_month,
                    income_at_month=income_at_month,
                    car_monthly_cash_cost_at=car_monthly_cash_cost_at,
                    car_down_payment_at=car_down_payment_at,
                    extra_monthly_payment=commercial_prepayment_monthly,
                    extra_payment_start_month=commercial_prepayment_start_month,
                    strategy_preference=pf_account_strategy_preference,
                )
                cash_stress_shortfall = max(
                    0.0,
                    required_liquidity_reserve - cash_after_transaction,
                    -minimum_cash_balance,
                )
        provident_interest_saving_if_equal_principal = provident_repayment_choice.interest_saving_if_equal_principal
        equal_principal_extra_first_payment = provident_repayment_choice.equal_principal_extra_first_payment
        equal_principal_cash_flow = (
            post_purchase_income.net_income
            - post_purchase_monthly_expense
            - household.monthly_debt_payment
            - post_purchase_car_cost
            - commercial_payment.first_month_payment
            - provident_equal_principal_payment.first_month_payment
            - immediate_commercial_prepayment
            + monthly_pf_withdrawal
        )
        provident_repayment_advice_text = provident_repayment_advice(
            provident_loan=provident_loan,
            selected_provident_repayment_method=selected_provident_repayment_method,
            equal_principal_extra_first_payment=equal_principal_extra_first_payment,
            provident_interest_saving_if_equal_principal=provident_interest_saving_if_equal_principal,
            equal_principal_cash_flow=equal_principal_cash_flow,
        )
        renovation_plan = build_renovation_funding_plan(
            scenario,
            cash_after_purchase=cash_after_purchase,
            required_liquidity_reserve=required_liquidity_reserve,
            post_purchase_cash_flow=post_purchase_cash_flow,
        )
        renovation_included_upfront = renovation_plan.included_upfront
        renovation_saving_months = renovation_plan.saving_months
        post_purchase_renovation_monthly_saving = renovation_plan.monthly_saving
        dti = (
            household.monthly_debt_payment
            + post_purchase_car_cost
            + total_monthly_payment
        ) / max(post_purchase_income.net_income, 1)
        pre_home_vehicle_down_payment = sum(
            loan.down_payment
            for _, _, loan, vehicle_purchase_month in vehicle_states
            if vehicle_purchase_month is not None and months is not None and vehicle_purchase_month <= months
        )
        pre_home_vehicle_monthly_cost = car_monthly_cash_cost_at(post_purchase_month)
        happiness_score, happiness_breakdown = build_purchase_happiness_breakdown(
            household=household,
            scenario=scenario,
            rules=rules,
            months=months,
            price=price,
            required_liquidity_reserve=required_liquidity_reserve,
            upfront_cash=upfront_cash,
            cash_after_transaction=cash_after_transaction,
            cash_after_purchase=cash_after_purchase,
            minimum_cash_balance=minimum_cash_balance,
            investment_balance_after_purchase=investment_balance_after_purchase,
            post_purchase_cash_flow=post_purchase_cash_flow,
            post_purchase_cash_flow_with_pf=post_purchase_cash_flow_with_pf,
            post_purchase_monthly_expense=post_purchase_monthly_expense,
            post_purchase_income_net=post_purchase_income.net_income,
            post_purchase_car_cost=post_purchase_car_cost,
            pre_home_vehicle_down_payment=pre_home_vehicle_down_payment,
            pre_home_vehicle_monthly_cost=pre_home_vehicle_monthly_cost,
            dti=dti,
            total_monthly_payment=total_monthly_payment,
            commercial_prepayment_monthly=commercial_prepayment_monthly,
            commercial_loan=commercial_loan,
            commercial_interest=commercial_interest,
            provident_interest=provident_payment.total_interest,
            cash_stress_ok=cash_stress_ok,
            cash_stress_shortfall=cash_stress_shortfall,
            renovation_included_upfront=renovation_included_upfront,
            renovation_saving_months=renovation_saving_months,
            monthly_pf_withdrawal_mode=monthly_pf_withdrawal_mode,
        )
        analyses.append(
            PurchasePlanAnalysis(
                variant=name,
                description=description,
                months_to_buy=months,
                years_to_buy=round(months / 12, 1) if months is not None else None,
                minimum_down_payment=round(min_down_payment, 2),
                planned_down_payment=round(planned_down, 2),
                provident_fund_extractable=pf_extractable,
                provident_upfront_extractable=round(pf_upfront_extractable, 2),
                family_provident_upfront_extractable=round(family_pf_upfront_extractable, 2),
                family_down_payment_support_amount=round(family_pf_upfront_extractable, 2),
                family_down_payment_support_mode=(
                    family_down_payment_support_mode(household)
                    if family_pf_upfront_extractable > 0
                    else "none"
                ),
                family_down_payment_support_label=(
                    family_down_payment_support_label(household)
                    if family_pf_upfront_extractable > 0
                    else ""
                ),
                provident_post_transaction_extractable=round(pf_post_transaction_extractable, 2),
                required_cash_after_pf_extract=round(max(0, upfront_cash - pf_upfront_extractable - family_pf_upfront_extractable), 2),
                upfront_cash_required=round(upfront_cash, 2),
                commercial_loan_amount=round(commercial_loan, 2),
                provident_loan_amount=round(provident_loan, 2),
                provident_policy_bonus=round(provident_policy_bonus, 2),
                provident_policy_cap=round(provident_cap, 2),
                commercial_rate=round(scenario.commercial_rate, 6),
                provident_rate=round(effective_provident_rate, 6),
                deed_tax_rate=round(deed_tax_rate, 6),
                broker_fee_rate=round(broker_fee_rate, 6),
                deed_tax_amount=round(deed_tax_amount, 2),
                broker_fee_amount=round(broker_fee_amount, 2),
                commercial_loan_years=scenario.loan_years,
                provident_loan_years=selected_provident_loan_years,
                provident_loan_year_limit_reasons=provident_year_reasons,
                commercial_repayment_method=scenario_commercial_repayment_method(scenario),  # type: ignore[arg-type]
                provident_repayment_method=selected_provident_repayment_method,  # type: ignore[arg-type]
                commercial_monthly_payment=round(commercial_payment.first_month_payment, 2),
                provident_monthly_payment=round(provident_payment.first_month_payment, 2),
                commercial_prepayment_mode=selected_commercial_prepayment_mode,  # type: ignore[arg-type]
                commercial_prepayment_enabled=commercial_prepayment_monthly > 0,
                commercial_prepayment_start_month=commercial_prepayment_start_month,
                commercial_prepayment_allowed_after_month=commercial_prepayment_allowed_after_month,
                commercial_prepayment_monthly_amount=round(commercial_prepayment_monthly, 2),
                commercial_actual_payoff_months=commercial_projection.actual_payoff_months if commercial_loan > 0 else 0,
                commercial_interest_saved_by_prepayment=round(commercial_projection.interest_saved_by_prepayment, 2),
                total_monthly_payment=round(total_monthly_payment, 2),
                total_interest=round(commercial_interest + provident_payment.total_interest, 2),
                provident_contract_months=selected_provident_loan_years * 12 if provident_loan > 0 else 0,
                provident_interest_saving_if_equal_principal=round(provident_interest_saving_if_equal_principal, 2),
                provident_equal_principal_first_payment=round(provident_equal_principal_payment.first_month_payment, 2),
                provident_equal_installment_payment=round(provident_equal_installment_payment.first_month_payment, 2),
                provident_repayment_advice=provident_repayment_advice_text,
                renovation_cost=round(scenario.renovation_cost, 2),
                renovation_funding_mode=scenario.renovation_funding_mode,
                renovation_included_in_upfront_cash=renovation_included_upfront,
                months_to_renovation=renovation_saving_months,
                years_to_renovation=round(renovation_saving_months / 12, 1)
                if renovation_saving_months is not None
                else None,
                post_purchase_renovation_monthly_saving=round(post_purchase_renovation_monthly_saving, 2),
                investment_withdrawal_mode=investment_withdrawal_mode(scenario),  # type: ignore[arg-type]
                investment_withdrawal_mode_label=investment_withdrawal_mode_label(
                    investment_withdrawal_mode(scenario)
                ),
                cash_account_before_purchase=round(cash_account_before_purchase, 2),
                investment_balance_before_purchase=round(investment_balance_before_purchase, 2),
                investment_sell_gross_at_purchase=round(investment_sell_gross_at_purchase, 2),
                investment_sell_proceeds_at_purchase=round(investment_sell_proceeds_at_purchase, 2),
                investment_balance_after_purchase=round(investment_balance_after_purchase, 2),
                cash_after_transaction=round(cash_after_transaction, 2),
                cash_after_purchase=round(cash_after_purchase, 2),
                provident_balance_after_extract=round(pf_after_extract, 2),
                required_liquidity_reserve=round(required_liquidity_reserve, 2),
                liquidity_ok=cash_after_transaction >= required_liquidity_reserve and cash_stress_ok,
                minimum_cash_balance=round(max(0.0, minimum_cash_balance), 2),
                minimum_cash_balance_month=minimum_cash_balance_month,
                cash_stress_ok=cash_stress_ok,
                cash_stress_shortfall=round(max(0.0, cash_stress_shortfall, -minimum_cash_balance), 2),
                post_purchase_cash_flow=round(post_purchase_cash_flow, 2),
                post_purchase_pf_strategy=monthly_pf_withdrawal_mode,
                post_purchase_pf_strategy_label=post_purchase_pf_withdrawal_label(monthly_pf_withdrawal_mode),
                monthly_post_purchase_pf_withdrawal=round(monthly_pf_withdrawal, 2),
                post_purchase_cash_flow_with_pf_withdrawal=round(post_purchase_cash_flow_with_pf, 2),
                debt_to_income_ratio=round(dti, 4),
                happiness_score=round(clamp_score(happiness_score), 2),
                provident_extraction_notes=provident_extraction_notes(
                    monthly_pf_withdrawal_mode,
                    monthly_relief=monthly_pf_withdrawal,
                ),
                happiness_breakdown=happiness_breakdown,
            )
        )
    return with_purchase_plan_recommendations(analyses, scenario)
