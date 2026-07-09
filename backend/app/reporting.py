from __future__ import annotations

from datetime import date

from .core_object_concepts import (
    ACCOUNT_CONCEPT_DEFINITIONS,
    CASH_ACCOUNT_CONCEPT,
    CORE_OBJECT_GROUP_DEFINITIONS,
    INVESTMENT_ACCOUNT_CONCEPT,
    LIQUID_ASSET_ACCOUNT_CONCEPT,
    MEDICAL_ACCOUNT_CONCEPT,
    PENSION_ACCOUNT_CONCEPT,
    SOCIAL_SECURITY_PERSONAL_ACCOUNTS_CONCEPT,
    account_concept_code_for_core_object,
)
from .domain.time import month_after
from .schemas import (
    AccountConceptSummary,
    AccountSnapshotPoint,
    AffordabilityResult,
    AnnualFinancialSummary,
    CalculationContextCoreObjectSnapshot,
    CalculationContextSnapshot,
    CoreObjectGroupSummary,
    ExportSheet,
    ExportTextDocument,
    LoanVisualizationPoint,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    ProvidentVisualizationPoint,
    PurchasePlanAnalysis,
    ScenarioData,
    SocialSecurityVisualizationPoint,
    StrategyExplanationPoint,
)


def money_text(amount: float) -> str:
    value = round(float(amount), 2)
    if abs(value) >= 10000:
        text = f"{value / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text} 万"
    text = f"{value:.0f}" if value == round(value) else f"{value:.2f}"
    return f"{text} 元"


def repayment_method_label(method: str) -> str:
    return "等额本金" if method == "equal_principal" else "等额本息"


def month_label(base_month: date, month: int) -> str:
    year, month_number = month_after(base_month, month)
    return f"{year:04d}-{month_number:02d}"


def build_annual_financial_summaries_from_ledger(
    ledger_entries: list[MonthlyLedgerEntry],
    account_snapshots: list[AccountSnapshotPoint],
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    base_date: date | None = None,
) -> list[AnnualFinancialSummary]:
    if not account_snapshots and not ledger_entries:
        return []

    start = base_date or date.today()
    base_month = date(start.year, start.month, 1)
    loans_by_plan_month = {(row.plan_variant, row.month): row for row in loan_visualization}
    provident_by_plan_month = {(row.plan_variant, row.month): row for row in provident_visualization}
    social_security_by_plan_month = {
        (row.plan_variant, row.month): row
        for row in (social_security_visualization or [])
    }
    sum_fields = [
        "cash_income",
        "pension_income",
        "living_expense",
        "scheduled_expense",
        "child_expense",
        "career_shock_self_payment",
        "debt_payment",
        "house_payment",
        "vehicle_payment",
        "vehicle_operating_cost",
        "investment_contribution",
        "investment_return",
        "investment_tax",
        "investment_fee",
        "investment_sell_proceeds",
        "personal_pension_contribution",
        "personal_pension_return",
        "provident_deposit",
        "provident_withdrawal",
        "pension_account_contribution",
        "pension_account_payout",
        "pension_account_interest",
        "medical_account_contribution",
        "medical_account_retiree_transfer",
        "medical_account_interest",
        "medical_account_healthcare_outflow",
        "medical_account_mutual_aid_outflow",
        "medical_account_outflow",
        "transaction_cash_out",
        "transaction_cash_in",
        "monthly_cash_delta",
    ]
    loan_sum_map = {
        "commercial_payment": "commercial_monthly_payment",
        "provident_payment": "provident_monthly_payment",
        "vehicle_loan_payment": "vehicle_monthly_payment",
        "existing_loan_payment": "existing_monthly_payment",
        "commercial_extra_principal_payment": "commercial_extra_principal_payment",
        "vehicle_extra_principal_payment": "vehicle_extra_principal_payment",
        "provident_offset_payment": "provident_offset_payment",
        "provident_monthly_withdrawal_payment": "provident_monthly_withdrawal_payment",
        "provident_principal_offset_payment": "provident_principal_offset_payment",
        "cash_monthly_payment": "cash_monthly_payment",
    }
    groups: dict[tuple[str, int], dict[str, object]] = {}
    previous_cash_balance_by_plan: dict[str, float] = {}

    def ensure_group(plan_variant: str, year: int) -> dict[str, object]:
        return groups.setdefault(
            (plan_variant, year),
            {
                "plan_variant": plan_variant,
                "year": year,
                "months": 0,
                "last_month": -1,
                "seen_months": set(),
                **{field: 0.0 for field in sum_fields},
                **{field: 0.0 for field in loan_sum_map},
            },
        )

    for snapshot in sorted(account_snapshots, key=lambda item: (item.plan_variant, item.month)):
        year, _ = month_after(base_month, snapshot.month)
        group = ensure_group(snapshot.plan_variant, year)
        previous_cash_balance = previous_cash_balance_by_plan.get(snapshot.plan_variant)
        if previous_cash_balance is not None:
            group["monthly_cash_delta"] = (
                float(group["monthly_cash_delta"])
                + snapshot.cash_balance
                - previous_cash_balance
            )
        previous_cash_balance_by_plan[snapshot.plan_variant] = snapshot.cash_balance
        seen_months = group["seen_months"]
        if isinstance(seen_months, set) and snapshot.month not in seen_months:
            seen_months.add(snapshot.month)
            group["months"] = int(group["months"]) + 1
        if snapshot.month >= int(group["last_month"]):
            loan_snapshot = loans_by_plan_month.get((snapshot.plan_variant, snapshot.month))
            provident_snapshot = provident_by_plan_month.get((snapshot.plan_variant, snapshot.month))
            social_security_snapshot = social_security_by_plan_month.get((snapshot.plan_variant, snapshot.month))
            group.update(
                {
                    "last_month": snapshot.month,
                    "cash_balance_end": snapshot.cash_balance,
                    "investment_balance_end": snapshot.investment_balance,
                    "liquid_asset_value_end": snapshot.liquid_asset_value,
                    "personal_pension_balance_end": snapshot.personal_pension_balance,
                    "provident_balance_end": (
                        provident_snapshot.balance_end
                        if provident_snapshot
                        else snapshot.provident_balance
                    ),
                    "pension_account_balance_end": (
                        social_security_snapshot.pension_balance_end
                        if social_security_snapshot
                        else snapshot.pension_account_balance
                    ),
                    "medical_account_balance_end": (
                        social_security_snapshot.medical_balance_end
                        if social_security_snapshot
                        else snapshot.medical_account_balance
                    ),
                    "social_security_account_balance_end": (
                        social_security_snapshot.total_balance_end
                        if social_security_snapshot
                        else snapshot.social_security_account_balance
                    ),
                    "fixed_asset_value_end": snapshot.fixed_asset_value,
                    "property_asset_value_end": snapshot.property_asset_value,
                    "vehicle_asset_value_end": snapshot.vehicle_asset_value,
                    "first_vehicle_asset_value_end": snapshot.first_vehicle_asset_value,
                    "second_vehicle_asset_value_end": snapshot.second_vehicle_asset_value,
                    "total_asset_value_end": snapshot.total_asset_value,
                    "total_loan_balance_end": (
                        loan_snapshot.total_loan_balance
                        if loan_snapshot
                        else snapshot.total_loan_balance
                    ),
                    "net_worth_end": snapshot.net_worth,
                    "commercial_loan_balance_end": loan_snapshot.commercial_loan_balance if loan_snapshot else 0.0,
                    "provident_loan_balance_end": loan_snapshot.provident_loan_balance if loan_snapshot else 0.0,
                    "vehicle_loan_balance_end": loan_snapshot.vehicle_loan_balance if loan_snapshot else 0.0,
                    "existing_loan_balance_end": loan_snapshot.existing_loan_balance if loan_snapshot else 0.0,
                }
            )

    for entry in ledger_entries:
        year, _ = month_after(base_month, entry.month)
        group = ensure_group(entry.plan_variant, year)
        seen_months = group["seen_months"]
        if isinstance(seen_months, set) and entry.month not in seen_months:
            seen_months.add(entry.month)
            group["months"] = int(group["months"]) + 1
        amount = float(entry.amount)
        outflow = abs(amount)
        category = entry.category
        if category == "income":
            group["cash_income"] = float(group["cash_income"]) + amount
        elif category == "pension_income":
            group["pension_income"] = float(group["pension_income"]) + amount
        elif category == "living_expense":
            group["living_expense"] = float(group["living_expense"]) + outflow
        elif category == "scheduled_expense":
            group["scheduled_expense"] = float(group["scheduled_expense"]) + outflow
        elif category == "child_expense":
            group["child_expense"] = float(group["child_expense"]) + outflow
        elif category == "career_shock_self_payment":
            group["career_shock_self_payment"] = float(group["career_shock_self_payment"]) + outflow
        elif category in {"regular_debt_payment", "phased_loan_payment"}:
            group["debt_payment"] = float(group["debt_payment"]) + outflow
        elif category == "house_payment":
            group["house_payment"] = float(group["house_payment"]) + outflow
        elif category == "vehicle_payment":
            group["vehicle_payment"] = float(group["vehicle_payment"]) + outflow
        elif category == "vehicle_operating_cost":
            group["vehicle_operating_cost"] = float(group["vehicle_operating_cost"]) + outflow
        elif category == "contribution":
            group["investment_contribution"] = float(group["investment_contribution"]) + amount
        elif category == "investment_return":
            group["investment_return"] = float(group["investment_return"]) + amount
        elif category == "investment_tax":
            group["investment_tax"] = float(group["investment_tax"]) + outflow
        elif category == "investment_fee":
            group["investment_fee"] = float(group["investment_fee"]) + outflow
        elif category in {"sell", "liquidity_redemption"}:
            group["investment_sell_proceeds"] = float(group["investment_sell_proceeds"]) + amount
            group["transaction_cash_in"] = float(group["transaction_cash_in"]) + amount
        elif category == "personal_pension_contribution":
            group["personal_pension_contribution"] = float(group["personal_pension_contribution"]) + outflow
        elif category == "personal_pension_return":
            group["personal_pension_return"] = float(group["personal_pension_return"]) + amount
        elif category == "provident_deposit":
            group["provident_deposit"] = float(group["provident_deposit"]) + amount
        elif category == "provident_withdrawal":
            group["provident_withdrawal"] = float(group["provident_withdrawal"]) + amount
            group["transaction_cash_in"] = float(group["transaction_cash_in"]) + amount
        elif category == "pension_account_payout":
            group["pension_account_payout"] = float(group["pension_account_payout"]) + outflow
        elif category == "medical_healthcare_outflow":
            group["medical_account_healthcare_outflow"] = float(group["medical_account_healthcare_outflow"]) + outflow
            group["medical_account_outflow"] = float(group["medical_account_outflow"]) + outflow
        elif category == "medical_mutual_aid_outflow":
            group["medical_account_mutual_aid_outflow"] = float(group["medical_account_mutual_aid_outflow"]) + outflow
            group["medical_account_outflow"] = float(group["medical_account_outflow"]) + outflow
        elif category in {"home_purchase", "vehicle_down_payment", "vehicle_plate_rental"}:
            group["transaction_cash_out"] = float(group["transaction_cash_out"]) + outflow

    for row in loan_visualization:
        year, _ = month_after(base_month, row.month)
        group = ensure_group(row.plan_variant, year)
        for summary_field, loan_field in loan_sum_map.items():
            group[summary_field] = float(group[summary_field]) + float(getattr(row, loan_field, 0.0))

    for row in social_security_visualization or []:
        year, _ = month_after(base_month, row.month)
        group = ensure_group(row.plan_variant, year)
        group["pension_account_contribution"] = float(group["pension_account_contribution"]) + row.pension_contribution
        group["pension_account_interest"] = float(group["pension_account_interest"]) + row.pension_interest
        group["medical_account_contribution"] = float(group["medical_account_contribution"]) + row.medical_contribution
        group["medical_account_retiree_transfer"] = float(group["medical_account_retiree_transfer"]) + row.medical_retiree_transfer
        group["medical_account_interest"] = float(group["medical_account_interest"]) + row.medical_interest

    summaries: list[AnnualFinancialSummary] = []
    for group in sorted(groups.values(), key=lambda item: (str(item["plan_variant"]), int(item["year"]))):
        payload = {
            key: value
            for key, value in group.items()
            if key not in {"last_month", "seen_months"}
        }
        for key, value in list(payload.items()):
            if isinstance(value, float):
                payload[key] = round(value, 2)
        summaries.append(AnnualFinancialSummary(**payload))
    return summaries


def build_annual_financial_summaries(
    monthly_cashflow: list[MonthlyCashflowPoint],
    account_snapshots: list[AccountSnapshotPoint],
    loan_visualization: list[LoanVisualizationPoint],
    provident_visualization: list[ProvidentVisualizationPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
    *,
    base_date: date | None = None,
) -> list[AnnualFinancialSummary]:
    if not monthly_cashflow:
        return []

    start = base_date or date.today()
    base_month = date(start.year, start.month, 1)
    snapshots_by_plan_month = {(row.plan_variant, row.month): row for row in account_snapshots}
    loans_by_plan_month = {(row.plan_variant, row.month): row for row in loan_visualization}
    provident_by_plan_month = {(row.plan_variant, row.month): row for row in provident_visualization}
    social_security_by_plan_month = {
        (row.plan_variant, row.month): row
        for row in (social_security_visualization or [])
    }
    groups: dict[tuple[str, int], dict[str, float | int | str]] = {}

    cashflow_sum_fields = [
        "cash_income",
        "pension_income",
        "living_expense",
        "scheduled_expense",
        "child_expense",
        "career_shock_self_payment",
        "debt_payment",
        "house_payment",
        "vehicle_payment",
        "vehicle_operating_cost",
        "investment_contribution",
        "investment_return",
        "investment_tax",
        "investment_fee",
        "investment_sell_proceeds",
        "personal_pension_contribution",
        "personal_pension_return",
        "provident_deposit",
        "provident_withdrawal",
        "pension_account_contribution",
        "pension_account_payout",
        "pension_account_interest",
        "medical_account_contribution",
        "medical_account_retiree_transfer",
        "medical_account_interest",
        "medical_account_healthcare_outflow",
        "medical_account_mutual_aid_outflow",
        "medical_account_outflow",
        "transaction_cash_out",
        "transaction_cash_in",
        "monthly_cash_delta",
    ]
    loan_sum_map = {
        "commercial_payment": "commercial_monthly_payment",
        "provident_payment": "provident_monthly_payment",
        "vehicle_loan_payment": "vehicle_monthly_payment",
        "existing_loan_payment": "existing_monthly_payment",
        "commercial_extra_principal_payment": "commercial_extra_principal_payment",
        "vehicle_extra_principal_payment": "vehicle_extra_principal_payment",
        "provident_offset_payment": "provident_offset_payment",
        "provident_monthly_withdrawal_payment": "provident_monthly_withdrawal_payment",
        "provident_principal_offset_payment": "provident_principal_offset_payment",
        "cash_monthly_payment": "cash_monthly_payment",
    }

    for row in sorted(monthly_cashflow, key=lambda item: (item.plan_variant, item.month)):
        year, _ = month_after(base_month, row.month)
        key = (row.plan_variant, year)
        group = groups.setdefault(
            key,
            {
                "plan_variant": row.plan_variant,
                "year": year,
                "months": 0,
                "last_month": -1,
                **{field: 0.0 for field in cashflow_sum_fields},
                **{field: 0.0 for field in loan_sum_map},
            },
        )
        group["months"] = int(group["months"]) + 1
        for field in cashflow_sum_fields:
            group[field] = float(group[field]) + float(getattr(row, field, 0.0))

        loan_row = loans_by_plan_month.get((row.plan_variant, row.month))
        if loan_row:
            for summary_field, loan_field in loan_sum_map.items():
                group[summary_field] = float(group[summary_field]) + float(getattr(loan_row, loan_field, 0.0))

        if row.month >= int(group["last_month"]):
            group["last_month"] = row.month
            snapshot = snapshots_by_plan_month.get((row.plan_variant, row.month))
            loan_snapshot = loan_row
            provident_snapshot = provident_by_plan_month.get((row.plan_variant, row.month))
            social_security_snapshot = social_security_by_plan_month.get((row.plan_variant, row.month))
            group.update(
                {
                    "cash_balance_end": snapshot.cash_balance if snapshot else row.cash_balance,
                    "investment_balance_end": snapshot.investment_balance if snapshot else row.investment_balance,
                    "liquid_asset_value_end": snapshot.liquid_asset_value if snapshot else row.liquid_asset_value,
                    "personal_pension_balance_end": row.personal_pension_balance,
                    "provident_balance_end": (
                        provident_snapshot.balance_end
                        if provident_snapshot
                        else snapshot.provident_balance if snapshot else row.provident_balance
                    ),
                    "pension_account_balance_end": (
                        social_security_snapshot.pension_balance_end
                        if social_security_snapshot
                        else snapshot.pension_account_balance if snapshot else row.pension_account_balance
                    ),
                    "medical_account_balance_end": (
                        social_security_snapshot.medical_balance_end
                        if social_security_snapshot
                        else snapshot.medical_account_balance if snapshot else row.medical_account_balance
                    ),
                    "social_security_account_balance_end": (
                        social_security_snapshot.total_balance_end
                        if social_security_snapshot
                        else snapshot.social_security_account_balance if snapshot else row.social_security_account_balance
                    ),
                    "fixed_asset_value_end": snapshot.fixed_asset_value if snapshot else row.fixed_asset_value,
                    "property_asset_value_end": row.property_asset_value,
                    "vehicle_asset_value_end": row.vehicle_asset_value,
                    "first_vehicle_asset_value_end": row.first_vehicle_asset_value,
                    "second_vehicle_asset_value_end": row.second_vehicle_asset_value,
                    "total_asset_value_end": snapshot.total_asset_value if snapshot else row.total_asset_value,
                    "total_loan_balance_end": (
                        loan_snapshot.total_loan_balance
                        if loan_snapshot
                        else snapshot.total_loan_balance if snapshot else row.total_loan_balance
                    ),
                    "net_worth_end": snapshot.net_worth if snapshot else row.net_worth,
                    "commercial_loan_balance_end": loan_snapshot.commercial_loan_balance if loan_snapshot else 0.0,
                    "provident_loan_balance_end": loan_snapshot.provident_loan_balance if loan_snapshot else 0.0,
                    "vehicle_loan_balance_end": loan_snapshot.vehicle_loan_balance if loan_snapshot else 0.0,
                    "existing_loan_balance_end": loan_snapshot.existing_loan_balance if loan_snapshot else 0.0,
                }
            )
        social_security_row = social_security_by_plan_month.get((row.plan_variant, row.month))
        if social_security_row:
            group["pension_account_contribution"] = float(group["pension_account_contribution"]) + social_security_row.pension_contribution
            group["pension_account_payout"] = float(group["pension_account_payout"]) + social_security_row.pension_account_payout
            group["pension_account_interest"] = float(group["pension_account_interest"]) + social_security_row.pension_interest
            group["medical_account_contribution"] = float(group["medical_account_contribution"]) + social_security_row.medical_contribution
            group["medical_account_retiree_transfer"] = float(group["medical_account_retiree_transfer"]) + social_security_row.medical_retiree_transfer
            group["medical_account_interest"] = float(group["medical_account_interest"]) + social_security_row.medical_interest
            group["medical_account_healthcare_outflow"] = float(group["medical_account_healthcare_outflow"]) + social_security_row.medical_healthcare_outflow
            group["medical_account_mutual_aid_outflow"] = float(group["medical_account_mutual_aid_outflow"]) + social_security_row.medical_mutual_aid_outflow
            group["medical_account_outflow"] = float(group["medical_account_outflow"]) + social_security_row.medical_outflow

    summaries: list[AnnualFinancialSummary] = []
    for group in sorted(groups.values(), key=lambda item: (str(item["plan_variant"]), int(item["year"]))):
        payload = {key: value for key, value in group.items() if key != "last_month"}
        for key, value in list(payload.items()):
            if isinstance(value, float):
                payload[key] = round(value, 2)
        summaries.append(AnnualFinancialSummary(**payload))
    return summaries


def _core_object_totals(
    core_objects: list[CalculationContextCoreObjectSnapshot],
) -> dict[str, tuple[int, float, float]]:
    groups: dict[str, tuple[int, float, float]] = {
        definition.code: (0, 0.0, 0.0) for definition in ACCOUNT_CONCEPT_DEFINITIONS
    }
    for item in core_objects:
        key = account_concept_code_for_core_object(item.object_type, item.category)
        if key is None:
            continue
        count, balance, monthly_flow = groups[key]
        groups[key] = (
            count + 1,
            balance + item.current_balance,
            monthly_flow + item.monthly_flow,
        )
    cash = groups[CASH_ACCOUNT_CONCEPT]
    investment = groups[INVESTMENT_ACCOUNT_CONCEPT]
    groups[LIQUID_ASSET_ACCOUNT_CONCEPT] = (
        cash[0] + investment[0],
        cash[1] + investment[1],
        cash[2] + investment[2],
    )
    pension = groups[PENSION_ACCOUNT_CONCEPT]
    medical = groups[MEDICAL_ACCOUNT_CONCEPT]
    groups[SOCIAL_SECURITY_PERSONAL_ACCOUNTS_CONCEPT] = (
        pension[0] + medical[0],
        pension[1] + medical[1],
        pension[2] + medical[2],
    )
    return groups


def _with_core_object_totals(
    concept: AccountConceptSummary,
    totals: dict[str, tuple[int, float, float]],
) -> AccountConceptSummary:
    count, balance, monthly_flow = totals.get(concept.code, (0, 0.0, 0.0))
    return concept.model_copy(
        update={
            "core_object_count": count,
            "current_balance": round(balance, 2),
            "monthly_flow": round(monthly_flow, 2),
        }
    )


def build_account_concepts_from_core_object_snapshots(
    core_objects: list[CalculationContextCoreObjectSnapshot],
) -> list[AccountConceptSummary]:
    totals = _core_object_totals(core_objects)
    concepts = [
        AccountConceptSummary(
            code=definition.code,
            name=definition.name,
            category=definition.category,  # type: ignore[arg-type]
            description=definition.description,
            managed_by=definition.managed_by,  # type: ignore[arg-type]
        )
        for definition in ACCOUNT_CONCEPT_DEFINITIONS
    ]
    return [_with_core_object_totals(concept, totals) for concept in concepts]


def build_account_concepts(calculation_context: CalculationContextSnapshot | None = None) -> list[AccountConceptSummary]:
    return build_account_concepts_from_core_object_snapshots(
        calculation_context.core_objects if calculation_context else []
    )


def build_core_object_group_summaries(
    account_concepts: list[AccountConceptSummary],
) -> list[CoreObjectGroupSummary]:
    concept_by_code = {item.code: item for item in account_concepts}

    def aggregate(codes: list[str]) -> tuple[int, float, float]:
        count = 0
        balance = 0.0
        monthly_flow = 0.0
        for code in codes:
            concept = concept_by_code.get(code)
            if concept is None:
                continue
            count += concept.core_object_count
            balance += concept.current_balance
            monthly_flow += concept.monthly_flow
        return count, round(balance, 2), round(monthly_flow, 2)

    groups: list[CoreObjectGroupSummary] = []
    for definition in CORE_OBJECT_GROUP_DEFINITIONS:
        concept_codes = list(definition.concept_codes)
        count, balance, monthly_flow = aggregate(concept_codes)
        groups.append(
            CoreObjectGroupSummary(
                code=definition.code,
                name=definition.name,
                category=definition.category,  # type: ignore[arg-type]
                concept_codes=concept_codes,
                description=definition.description,
                core_object_count=count,
                current_balance=balance,
                monthly_flow=monthly_flow,
            )
        )
    return groups


def build_strategy_explanations(
    purchase_plans: list[PurchasePlanAnalysis],
    account_concepts: list[AccountConceptSummary] | None = None,
    core_object_groups: list[CoreObjectGroupSummary] | None = None,
) -> list[StrategyExplanationPoint]:
    rows: list[StrategyExplanationPoint] = []
    concept_by_code = {item.code: item for item in (account_concepts or [])}
    group_by_code = {item.code: item for item in (core_object_groups or [])}

    def concept_summary(code: str, fallback: str) -> str:
        concept = concept_by_code.get(code)
        if concept is None:
            return fallback
        return f"{concept.name} {money_text(concept.current_balance)}（{concept.core_object_count} 个核心对象）"

    def group_summary(code: str, fallback: str) -> str:
        group = group_by_code.get(code)
        if group is None:
            return fallback
        return f"{group.name} {money_text(group.current_balance)}（{group.core_object_count} 个核心对象）"

    liquid_assets_text = group_summary("liquid_assets", "流动资产按现金账户和投资账户合计")
    loan_accounts_text = group_summary("loan_accounts", "贷款账户按房贷、车贷和已有贷款合计")
    provident_account_text = concept_summary("provident_account", "公积金账户单独作为受限账户展示")
    for plan in purchase_plans:
        if plan.months_to_buy is None:
            status_body = (
                f"当前方案在 30 年内没有找到现金安全的执行月份；压力情景短缺约 {money_text(plan.cash_stress_shortfall)}。"
                "后端不会把现金账户推成负数来制造可行结果，需要延后、降低目标或调整贷款结构。"
            )
        else:
            status_body = (
                f"后端选择第 {plan.months_to_buy} 个月作为执行锚点；交易现金需覆盖 {money_text(plan.required_cash_after_pf_extract)}，"
                f"交易当下现金约 {money_text(plan.cash_after_transaction)}，购后现金约 {money_text(plan.cash_after_purchase)}。"
            )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="summary",
                title="执行判断",
                body=status_body,
                priority=10,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="funding",
                title="资金结构",
                body=(
                    f"首付 {money_text(plan.planned_down_payment)}，本人公积金可用于交易前抵扣 {money_text(plan.provident_upfront_extractable)}，"
                    f"亲属首付支持 {money_text(plan.family_down_payment_support_amount)}；后端按房源性质、政策上限和现金安全要求共同决定现金缺口。"
                    f"核心对象口径：{liquid_assets_text}；{provident_account_text}。"
                ),
                priority=20,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="loan",
                title="贷款结构",
                body=(
                    f"公积金贷 {money_text(plan.provident_loan_amount)}，{plan.provident_loan_years} 年，"
                    f"{repayment_method_label(plan.provident_repayment_method)}；商贷 {money_text(plan.commercial_loan_amount)}，"
                    f"{plan.commercial_loan_years} 年，{repayment_method_label(plan.commercial_repayment_method)}。"
                    f"公积金政策上限 {money_text(plan.provident_policy_cap)}，上浮 {money_text(plan.provident_policy_bonus)}。"
                    f"核心对象口径：{loan_accounts_text}。"
                ),
                priority=30,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="provident",
                title="公积金策略",
                body=(
                    f"贷后公积金处理为“{plan.post_purchase_pf_strategy_label}”。"
                    + ("；".join(plan.provident_extraction_notes[:3]) if plan.provident_extraction_notes else "")
                ),
                priority=40,
            )
        )
        rows.append(
            StrategyExplanationPoint(
                plan_variant=plan.variant,
                section="risk",
                title="现金与幸福度",
                body=(
                    f"买后自由现金月结余 {money_text(plan.post_purchase_cash_flow)}，负债收入比 {plan.debt_to_income_ratio:.1%}，"
                    f"最低现金账户约 {money_text(plan.minimum_cash_balance)}；幸福指数 {plan.happiness_score:.1f}/10。"
                ),
                priority=50,
            )
        )
    return sorted(rows, key=lambda item: (item.plan_variant, item.priority))


def _selected_plan_rows(rows, plan_variant: str):
    return sorted(
        [row for row in rows if getattr(row, "plan_variant", "") == plan_variant],
        key=lambda row: getattr(row, "month", 0),
    )


def _sheet(
    *,
    plan_variant: str,
    title: str,
    headers: list[str],
    rows: list[list[object]],
) -> ExportSheet:
    return ExportSheet(
        plan_variant=plan_variant,
        title=title,
        headers=headers,
        rows=rows,
    )


def build_export_sheets(
    result: AffordabilityResult,
    scenario: ScenarioData,
    *,
    base_date: date | None = None,
) -> list[ExportSheet]:
    start = base_date or date.today()
    base_month = date(start.year, start.month, 1)
    sheets: list[ExportSheet] = []
    for plan in result.purchase_plan_analyses:
        plan_variant = plan.variant
        cashflow_rows = _selected_plan_rows(result.monthly_cashflow_visualization, plan_variant)
        snapshot_rows = _selected_plan_rows(result.account_snapshots, plan_variant)
        loan_rows = _selected_plan_rows(result.loan_visualization, plan_variant)
        provident_rows = _selected_plan_rows(result.provident_visualization, plan_variant)
        social_security_rows = _selected_plan_rows(result.social_security_visualization, plan_variant)
        ledger_rows = sorted(
            [row for row in result.monthly_ledger if row.plan_variant == plan_variant],
            key=lambda row: (row.month, row.account, row.category, row.label),
        )
        event_rows = sorted(
            [row for row in result.plan_events if row.plan_variant == plan_variant],
            key=lambda row: (row.month, row.category, row.title),
        )
        strategy_rows = sorted(
            [row for row in result.strategy_explanations if row.plan_variant == plan_variant],
            key=lambda row: (row.priority, row.section, row.title),
        )
        cashflow_by_month = {row.month: row for row in cashflow_rows}
        sheets.extend(
            [
                _sheet(
                    plan_variant=plan_variant,
                    title="导出说明",
                    headers=["项目", "内容"],
                    rows=[
                        ["房源/场景", scenario.name],
                        ["导出方案", plan_variant],
                        ["时间口径", "所有月份为从当前月份开始推演的真实年月；金额单位为元。"],
                        ["数据来源", "后端 export_sheets，由核心对象索引、月度账本、账户快照、贷款、公积金、养老医保和事件时间线生成。"],
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="核心对象与账户概念",
                    headers=["概念编码", "名称", "类别", "核心对象数量", "当前余额/目标金额", "月流量", "管理方", "说明"],
                    rows=[
                        [
                            row.code,
                            row.name,
                            row.category,
                            row.core_object_count,
                            row.current_balance,
                            row.monthly_flow,
                            row.managed_by,
                            row.description,
                        ]
                        for row in result.account_concepts
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="统一规划顺序",
                    headers=[
                        "目标ID",
                        "目标名称",
                        "目标类型",
                        "启用",
                        "解析顺序",
                        "时间模式",
                        "依赖目标",
                        "最早月份偏移",
                        "窗口开始偏移",
                        "窗口结束偏移",
                        "说明",
                    ],
                    rows=[
                        [
                            goal.id,
                            goal.name,
                            goal.goal_type,
                            goal.enabled,
                            goal.sequence_index,
                            goal.normalized_timing_mode,
                            goal.depends_on_goal_name,
                            goal.resolved_not_before_month,
                            goal.resolved_window_start_month,
                            "" if goal.resolved_window_end_month is None else goal.resolved_window_end_month,
                            goal.explanation,
                        ]
                        for goal in (
                            result.calculation_context.planning_goals
                            if result.calculation_context
                            else []
                        )
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="核心对象分组摘要",
                    headers=["分组编码", "名称", "类别", "包含概念", "核心对象数量", "当前余额/目标金额", "月流量", "说明"],
                    rows=[
                        [
                            row.code,
                            row.name,
                            row.category,
                            "、".join(row.concept_codes),
                            row.core_object_count,
                            row.current_balance,
                            row.monthly_flow,
                            row.description,
                        ]
                        for row in result.core_object_groups
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="方案摘要",
                    headers=["项目", "内容"],
                    rows=[
                        ["方案描述", plan.description],
                        ["预计买入月份", "" if plan.months_to_buy is None else month_label(base_month, plan.months_to_buy)],
                        ["距今约年数", "" if plan.years_to_buy is None else plan.years_to_buy],
                        ["计划首付", plan.planned_down_payment],
                        ["交易现金总需求", plan.upfront_cash_required],
                        ["本人公积金首付抵扣", plan.provident_upfront_extractable],
                        ["交易现金需家庭覆盖", plan.required_cash_after_pf_extract],
                        ["交易当下现金", plan.cash_after_transaction],
                        ["购房后现金", plan.cash_after_purchase],
                        ["现金安全垫要求", plan.required_liquidity_reserve],
                        ["压力现金缺口", plan.cash_stress_shortfall],
                        ["买后自由现金月结余", plan.post_purchase_cash_flow],
                        ["贷后公积金策略", plan.post_purchase_pf_strategy_label],
                        ["负债收入比", plan.debt_to_income_ratio],
                        ["幸福指数", plan.happiness_score],
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="贷款与购房资金",
                    headers=["项目", "内容"],
                    rows=[
                        ["公积金贷款金额", plan.provident_loan_amount],
                        ["公积金贷款政策上限", plan.provident_policy_cap],
                        ["公积金政策上浮", plan.provident_policy_bonus],
                        ["公积金贷款年限", plan.provident_loan_years],
                        ["公积金合同期数", plan.provident_contract_months],
                        ["公积金还款方式", repayment_method_label(plan.provident_repayment_method)],
                        ["公积金月供", plan.provident_monthly_payment],
                        ["公积金还款建议", plan.provident_repayment_advice],
                        ["商贷金额", plan.commercial_loan_amount],
                        ["商贷年限", plan.commercial_loan_years],
                        ["商贷还款方式", repayment_method_label(plan.commercial_repayment_method)],
                        ["商贷月供", plan.commercial_monthly_payment],
                        ["商贷提前还本是否启用", plan.commercial_prepayment_enabled],
                        ["商贷提前还本起始月", plan.commercial_prepayment_start_month],
                        ["商贷每月额外还本", plan.commercial_prepayment_monthly_amount],
                        ["商贷提前还本节省利息", plan.commercial_interest_saved_by_prepayment],
                        ["合计月供", plan.total_monthly_payment],
                        ["全周期利息", plan.total_interest],
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="账户月度快照",
                    headers=[
                        "月份序号",
                        "真实年月",
                        "阶段",
                        "现金账户",
                        "投资账户",
                        "流动资产",
                        "公积金账户",
                        "养老保险个人账户",
                        "医保个人账户",
                        "养老医保账户合计",
                        "个人养老金账户",
                        "房产估值",
                        "车辆估值",
                        "固定资产",
                        "总资产",
                        "贷款余额",
                        "净资产",
                    ],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            cashflow_by_month.get(row.month).phase if cashflow_by_month.get(row.month) else "",
                            row.cash_balance,
                            row.investment_balance,
                            row.liquid_asset_value,
                            row.provident_balance,
                            row.pension_account_balance,
                            row.medical_account_balance,
                            row.social_security_account_balance,
                            row.personal_pension_balance,
                            row.property_asset_value,
                            row.vehicle_asset_value,
                            row.fixed_asset_value,
                            row.total_asset_value,
                            row.total_loan_balance,
                            row.net_worth,
                        ]
                        for row in snapshot_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="月现金流明细",
                    headers=[
                        "月份序号",
                        "真实年月",
                        "阶段",
                        "现金净流入",
                        "现金收入",
                        "养老金领取",
                        "基础生活支出",
                        "计划支出",
                        "养娃计划支出",
                        "灵活就业自缴社保公积金",
                        "已有贷款还款",
                        "房贷现金还款",
                        "车贷还款",
                        "车辆运营成本",
                        "定投买入",
                        "投资收益",
                        "投资收益税",
                        "投资手续费",
                        "投资卖出到账",
                        "个人养老金缴费",
                        "个人养老金收益",
                        "公积金缴存",
                        "公积金现金提取",
                        "交易现金支出",
                        "交易现金流入",
                    ],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            row.phase,
                            row.monthly_cash_delta,
                            row.cash_income,
                            row.pension_income,
                            row.living_expense,
                            row.scheduled_expense,
                            row.child_expense,
                            row.career_shock_self_payment,
                            row.debt_payment,
                            row.house_payment,
                            row.vehicle_payment,
                            row.vehicle_operating_cost,
                            row.investment_contribution,
                            row.investment_return,
                            row.investment_tax,
                            row.investment_fee,
                            row.investment_sell_proceeds,
                            row.personal_pension_contribution,
                            row.personal_pension_return,
                            row.provident_deposit,
                            row.provident_withdrawal,
                            row.transaction_cash_out,
                            row.transaction_cash_in,
                        ]
                        for row in cashflow_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="贷款余额与月供",
                    headers=[
                        "月份序号",
                        "真实年月",
                        "商贷余额",
                        "公积金贷余额",
                        "房贷余额",
                        "车贷余额",
                        "已有贷款余额",
                        "总贷款余额",
                        "商贷月供",
                        "公积金贷合同月供",
                        "房贷合同月供",
                        "车贷月供",
                        "已有贷款月供",
                        "现金还款",
                        "公积金按月抵月供",
                        "公积金半年度冲本金",
                    ],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            row.commercial_loan_balance,
                            row.provident_loan_balance,
                            row.home_loan_balance,
                            row.vehicle_loan_balance,
                            row.existing_loan_balance,
                            row.total_loan_balance,
                            row.commercial_monthly_payment,
                            row.provident_monthly_payment,
                            row.home_monthly_payment,
                            row.vehicle_monthly_payment,
                            row.existing_monthly_payment,
                            row.cash_monthly_payment,
                            row.provident_monthly_withdrawal_payment,
                            row.provident_principal_offset_payment,
                        ]
                        for row in loan_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="后端月度流水",
                    headers=["月份序号", "真实年月", "账户", "类别", "项目", "金额", "方向", "来源"],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            row.account,
                            row.category,
                            row.label,
                            row.amount,
                            row.direction,
                            row.source,
                        ]
                        for row in ledger_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="关键事件时间线",
                    headers=["月份序号", "真实年月", "类别", "标题", "详情", "金额", "等级", "来源", "校准来源"],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            row.category,
                            row.title,
                            row.detail,
                            "" if row.amount is None else row.amount,
                            row.severity,
                            row.source,
                            row.calibration_source,
                        ]
                        for row in event_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="公积金家庭账户",
                    headers=[
                        "月份序号",
                        "真实年月",
                        "月初余额",
                        "缴存合计",
                        "利息",
                        "租房提取",
                        "交易前提取",
                        "交易后提取",
                        "约定提取",
                        "按月抵月供",
                        "半年度冲本金",
                        "退休销户提取",
                        "收入合计",
                        "支出合计",
                        "月末余额",
                        "策略",
                    ],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            row.balance_start,
                            row.total_deposit,
                            row.interest,
                            row.rent_withdrawal,
                            row.upfront_withdrawal,
                            row.post_transaction_withdrawal,
                            row.agreed_withdrawal,
                            row.monthly_repayment_withdrawal,
                            row.loan_offset_payment,
                            row.retirement_withdrawal,
                            row.total_inflow,
                            row.total_outflow,
                            row.balance_end,
                            row.strategy_label,
                        ]
                        for row in provident_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="养老与医保个人账户",
                    headers=[
                        "月份序号",
                        "真实年月",
                        "养老月初余额",
                        "养老个人缴入",
                        "养老计发支出",
                        "养老账户利息",
                        "养老月末余额",
                        "医保月初余额",
                        "医保个人划入",
                        "退休医保划入",
                        "医保账户利息",
                        "医保医疗支付",
                        "医保互助扣缴",
                        "医保账户支出合计",
                        "医保月末余额",
                        "政策账户合计",
                    ],
                    rows=[
                        [
                            row.month,
                            month_label(base_month, row.month),
                            row.pension_balance_start,
                            row.pension_contribution,
                            row.pension_account_payout,
                            row.pension_interest,
                            row.pension_balance_end,
                            row.medical_balance_start,
                            row.medical_contribution,
                            row.medical_retiree_transfer,
                            row.medical_interest,
                            row.medical_healthcare_outflow,
                            row.medical_mutual_aid_outflow,
                            row.medical_outflow,
                            row.medical_balance_end,
                            row.total_balance_end,
                        ]
                        for row in social_security_rows
                    ],
                ),
                _sheet(
                    plan_variant=plan_variant,
                    title="策略解释",
                    headers=["分区", "标题", "解释", "优先级"],
                    rows=[
                        [row.section, row.title, row.body, row.priority]
                        for row in strategy_rows
                    ],
                ),
            ]
        )
    sheets.append(
        _sheet(
            plan_variant="",
            title="账户与概念说明",
            headers=["代码", "名称", "类别", "管理方", "说明"],
            rows=[
                [row.code, row.name, row.category, row.managed_by, row.description]
                for row in result.account_concepts
            ],
        )
    )
    sheets.append(
        _sheet(
            plan_variant="",
            title="核心对象分组说明",
            headers=["代码", "名称", "类别", "包含概念", "说明"],
            rows=[
                [row.code, row.name, row.category, "、".join(row.concept_codes), row.description]
                for row in result.core_object_groups
            ],
        )
    )
    return sheets


def build_export_texts(
    result: AffordabilityResult,
    scenario: ScenarioData,
    *,
    base_date: date | None = None,
) -> list[ExportTextDocument]:
    start = base_date or date.today()
    base_month = date(start.year, start.month, 1)
    documents: list[ExportTextDocument] = []
    for plan in result.purchase_plan_analyses:
        plan_variant = plan.variant
        snapshot_rows = _selected_plan_rows(result.account_snapshots, plan_variant)
        loan_rows = _selected_plan_rows(result.loan_visualization, plan_variant)
        provident_rows = _selected_plan_rows(result.provident_visualization, plan_variant)
        social_security_rows = _selected_plan_rows(result.social_security_visualization, plan_variant)
        event_rows = sorted(
            [row for row in result.plan_events if row.plan_variant == plan_variant],
            key=lambda row: (row.month, row.category, row.title),
        )
        strategy_rows = sorted(
            [row for row in result.strategy_explanations if row.plan_variant == plan_variant],
            key=lambda row: (row.priority, row.section, row.title),
        )
        purchase_snapshot = (
            next((row for row in snapshot_rows if row.month == plan.months_to_buy), None)
            if plan.months_to_buy is not None
            else None
        )
        final_snapshot = snapshot_rows[-1] if snapshot_rows else None
        max_loan_balance = max((row.total_loan_balance for row in loan_rows), default=0.0)
        final_provident = provident_rows[-1] if provident_rows else None
        final_social_security = social_security_rows[-1] if social_security_rows else None
        lines = [
            f"当前导出方案：{plan_variant}",
            plan.description,
            "",
            f"税后月收入：{money_text(result.household_net_monthly_income)}",
            f"年度个税：{money_text(result.annual_income_tax)}",
            f"已有贷款月供：{money_text(result.phased_loan_monthly_payment)}",
            "",
            "当前方案购房路径：",
            (
                "预计买入时间：30 年内暂不可达"
                if plan.months_to_buy is None
                else f"预计买入时间：{month_label(base_month, plan.months_to_buy)}（距今约 {plan.years_to_buy} 年）"
            ),
            (
                f"首付：{money_text(plan.planned_down_payment)}，本人公积金首付抵扣：{money_text(plan.provident_upfront_extractable)}，"
                f"交易现金需覆盖：{money_text(plan.required_cash_after_pf_extract)}。"
            ),
            f"购房后预计公积金提取到账：{money_text(plan.provident_post_transaction_extractable)}，剩余公积金余额：{money_text(plan.provident_balance_after_extract)}。",
            (
                f"公积金贷：{money_text(plan.provident_loan_amount)}，{plan.provident_loan_years} 年，"
                f"{repayment_method_label(plan.provident_repayment_method)}；商贷：{money_text(plan.commercial_loan_amount)}，"
                f"{plan.commercial_loan_years} 年，{repayment_method_label(plan.commercial_repayment_method)}。"
            ),
            f"合计月供：{money_text(plan.total_monthly_payment)}，交易当下现金：{money_text(plan.cash_after_transaction)}，购房后现金：{money_text(plan.cash_after_purchase)}。",
            f"买后自由现金月结余：{money_text(plan.post_purchase_cash_flow)}，贷后公积金策略：{plan.post_purchase_pf_strategy_label}。",
            f"公积金还款方式建议：{plan.provident_repayment_advice or '无'}",
            f"负债收入比：{plan.debt_to_income_ratio:.1%}，幸福指数：{plan.happiness_score:.1f} / 10。",
            "",
            "幸福指数明细：",
            *[
                f"- {item.name}：{item.score:.1f} 分，权重 {item.weight:.1%}，贡献 {item.weighted_score:.2f} 分。{item.note}"
                for item in plan.happiness_breakdown
            ],
            f"公积金年限依据：{'；'.join(plan.provident_loan_year_limit_reasons)}",
            "",
            "关键事件时间线：",
            *(
                [
                    (
                        f"- {month_label(base_month, row.month)}｜{row.title}｜{row.detail}"
                        + ("" if row.amount is None else f"｜金额 {money_text(row.amount)}")
                    )
                    for row in event_rows
                ]
                if event_rows
                else ["- 当前方案暂无后端事件。"]
            ),
            "",
            "账户与贷款快照：",
            (
                f"买入月 {month_label(base_month, purchase_snapshot.month)}：现金账户 {money_text(purchase_snapshot.cash_balance)}，"
                f"投资账户 {money_text(purchase_snapshot.investment_balance)}，公积金账户 {money_text(purchase_snapshot.provident_balance)}，"
                f"固定资产 {money_text(purchase_snapshot.fixed_asset_value)}，贷款余额 {money_text(purchase_snapshot.total_loan_balance)}，"
                f"净资产 {money_text(purchase_snapshot.net_worth)}。"
                if purchase_snapshot
                else "买入月：当前方案 30 年内暂不可达或暂无对应账户快照。"
            ),
            (
                f"测算末月 {month_label(base_month, final_snapshot.month)}：现金账户 {money_text(final_snapshot.cash_balance)}，"
                f"投资账户 {money_text(final_snapshot.investment_balance)}，公积金账户 {money_text(final_snapshot.provident_balance)}，"
                f"固定资产 {money_text(final_snapshot.fixed_asset_value)}，贷款余额 {money_text(final_snapshot.total_loan_balance)}，"
                f"净资产 {money_text(final_snapshot.net_worth)}。"
                if final_snapshot
                else "测算末月：暂无后端账户快照。"
            ),
            (
                f"贷款曲线：共 {len(loan_rows)} 个月，最高总贷款余额 {money_text(max_loan_balance)}。"
                if loan_rows
                else "贷款曲线：当前方案暂无贷款曲线。"
            ),
            (
                f"公积金账户曲线：共 {len(provident_rows)} 个月，末月家庭公积金余额 {money_text(final_provident.balance_end)}。"
                if final_provident
                else "公积金账户曲线：当前方案暂无公积金曲线。"
            ),
            (
                f"养老与医保个人账户曲线：共 {len(social_security_rows)} 个月，末月养老个人账户 {money_text(final_social_security.pension_balance_end)}，医保个人账户 {money_text(final_social_security.medical_balance_end)}。"
                if final_social_security
                else "养老与医保个人账户曲线：当前方案暂无账户曲线。"
            ),
            "",
            "策略解释：",
            *(
                [f"- {row.title}：{row.body}" for row in strategy_rows]
                if strategy_rows
                else ["- 当前方案暂无后端策略解释。"]
            ),
            "",
            "详细表格提示：导出表格由后端 export_sheets 提供，包含账户快照、月现金流、贷款、公积金、养老医保、事件和月度流水。",
            "",
            f"全局即时评估：{result.status}。{result.status_reason}",
        ]
        documents.append(
            ExportTextDocument(
                plan_variant=plan_variant,
                filename=f"house-plan-{plan_variant}.txt",
                lines=lines,
            )
        )
    return documents
