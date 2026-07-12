from __future__ import annotations

from .schemas import (
    AnnualFinancialSummary,
    AnnualVisualizationDetail,
    MonthlyCashflowPoint,
    MonthlyLedgerEntry,
    MonthlyVisualizationDetail,
    SocialSecurityVisualizationPoint,
    TaxMonthlyPoint,
    TaxVisualizationDetail,
    TaxYearSummary,
    VisualizationBreakdownItem,
)
from .projection.ledger import MonthlyProjectionState


def monthly_cashflow_point_from_state(
    state: MonthlyProjectionState,
    ledger_entries: list[MonthlyLedgerEntry],
) -> MonthlyCashflowPoint:
    return MonthlyCashflowPoint(
        plan_variant=state.plan_variant,
        month=state.month,
        cash_balance=round(state.cash_balance, 2),
        investment_balance=round(state.investment_balance, 2),
        liquid_asset_value=round(state.liquid_asset_value, 2),
        provident_balance=round(state.provident_balance, 2),
        pension_account_balance=round(state.pension_account_balance, 2),
        medical_account_balance=round(state.medical_account_balance, 2),
        social_security_account_balance=round(state.social_security_account_balance, 2),
        fixed_asset_value=round(state.fixed_asset_value, 2),
        total_asset_value=round(state.total_asset_value, 2),
        total_loan_balance=round(state.total_loan_balance, 2),
        net_worth=round(state.net_worth, 2),
        happiness_score=state.happiness_score,
        monthly_cash_delta=round(state.monthly_cash_delta, 2),
        cash_shortfall=round(max(0.0, -state.cash_balance), 2),
        cash_income=round(state.cash_income, 2),
        pension_income=round(state.pension_income, 2),
        living_expense=round(state.living_expense, 2),
        scheduled_expense=round(state.scheduled_expense, 2),
        renovation_expense=round(state.renovation_expense, 2),
        child_expense=round(state.child_expense, 2),
        career_shock_self_payment=round(state.career_shock_self_payment, 2),
        debt_payment=round(state.debt_payment, 2),
        regular_debt_payment=round(state.regular_debt_payment, 2),
        phased_loan_payment=round(state.phased_loan_payment, 2),
        house_payment=round(state.house_payment, 2),
        house_contract_payment=round(state.house_contract_payment, 2),
        provident_house_offset_payment=round(state.provident_house_offset_payment, 2),
        provident_house_payment_relief=round(state.provident_house_payment_relief, 2),
        vehicle_payment=round(state.vehicle_payment, 2),
        first_vehicle_payment=round(state.first_vehicle_payment, 2),
        second_vehicle_payment=round(state.second_vehicle_payment, 2),
        vehicle_operating_cost=round(state.vehicle_operating_cost, 2),
        first_vehicle_energy_cost=round(state.first_vehicle_energy_cost, 2),
        first_vehicle_insurance_cost=round(state.first_vehicle_insurance_cost, 2),
        first_vehicle_maintenance_cost=round(state.first_vehicle_maintenance_cost, 2),
        first_vehicle_parking_cost=round(state.first_vehicle_parking_cost, 2),
        second_vehicle_energy_cost=round(state.second_vehicle_energy_cost, 2),
        second_vehicle_insurance_cost=round(state.second_vehicle_insurance_cost, 2),
        second_vehicle_maintenance_cost=round(state.second_vehicle_maintenance_cost, 2),
        second_vehicle_parking_cost=round(state.second_vehicle_parking_cost, 2),
        no_car_commute_cost=round(state.no_car_commute_cost, 2),
        first_vehicle_down_payment=round(state.first_vehicle_down_payment, 2),
        second_vehicle_down_payment=round(state.second_vehicle_down_payment, 2),
        vehicle_down_payment=round(state.vehicle_down_payment, 2),
        vehicle_plate_rental_payment=round(state.vehicle_plate_rental_payment, 2),
        investment_contribution=round(state.investment_contribution, 2),
        investment_contribution_base=round(state.investment_contribution_base, 2),
        investment_contribution_cash_sweep=round(state.investment_contribution_cash_sweep, 2),
        investment_return=round(state.investment_return, 2),
        investment_tax=round(state.investment_tax, 2),
        investment_fee=round(state.investment_fee, 2),
        investment_buy_fee=round(state.investment_buy_fee, 2),
        investment_sell_fee=round(state.investment_sell_fee, 2),
        investment_sell_proceeds=round(state.investment_sell_proceeds, 2),
        personal_pension_contribution=round(state.personal_pension_contribution, 2),
        personal_pension_return=round(state.personal_pension_return, 2),
        personal_pension_withdrawal=round(state.personal_pension_withdrawal, 2),
        personal_pension_redemption_fee=round(state.personal_pension_redemption_fee, 2),
        personal_pension_withdrawal_tax=round(state.personal_pension_withdrawal_tax, 2),
        personal_pension_suspended_contribution=round(state.personal_pension_suspended_contribution, 2),
        personal_pension_balance=round(state.personal_pension_balance, 2),
        provident_deposit=round(state.provident_deposit, 2),
        provident_withdrawal=round(state.provident_withdrawal, 2),
        transaction_cash_out=round(state.transaction_cash_out, 2),
        transaction_cash_in=round(state.transaction_cash_in, 2),
        property_asset_value=round(state.property_asset_value, 2),
        vehicle_asset_value=round(state.vehicle_asset_value, 2),
        first_vehicle_asset_value=round(state.first_vehicle_asset_value, 2),
        second_vehicle_asset_value=round(state.second_vehicle_asset_value, 2),
        phase=state.phase,
        ledger_entries=ledger_entries,
    )


def build_monthly_cashflow_points(
    states: list[MonthlyProjectionState],
    ledger_entries: list[MonthlyLedgerEntry],
    *,
    risk_by_plan: dict[str, object] | None = None,
) -> list[MonthlyCashflowPoint]:
    entries_by_month: dict[tuple[str, int], list[MonthlyLedgerEntry]] = {}
    for entry in ledger_entries:
        entries_by_month.setdefault((entry.plan_variant, entry.month), []).append(entry)
    rows: list[MonthlyCashflowPoint] = []
    for state in states:
        risk = (risk_by_plan or {}).get(state.plan_variant)
        rows.append(
            monthly_cashflow_point_from_state(
                state,
                entries_by_month.get((state.plan_variant, state.month), []),
            ).model_copy(
                update={
                    "insolvency_month": getattr(risk, "insolvency_month", None),
                    "liquid_assets_exhausted_month": getattr(risk, "liquid_assets_exhausted_month", None),
                }
            )
        )
    return rows


def _breakdown_item(
    name: str,
    value: float,
    *,
    kind: str | None = None,
    amount: float | None = None,
) -> VisualizationBreakdownItem | None:
    if abs(value) <= 0.005 and (amount is None or abs(amount) <= 0.005):
        return None
    return VisualizationBreakdownItem(
        name=name,
        value=round(max(0.0, value), 2),
        amount=round(amount if amount is not None else value, 2),
        kind=kind,
    )


def _compact_items(items: list[VisualizationBreakdownItem | None]) -> list[VisualizationBreakdownItem]:
    return [item for item in items if item is not None and (item.value > 0 or (item.amount or 0) != 0)]


def monthly_visualization_detail_from_cashflow(row: MonthlyCashflowPoint) -> MonthlyVisualizationDetail:
    return monthly_visualization_detail_from_inputs(row, None)


def monthly_visualization_detail_from_inputs(
    row: MonthlyCashflowPoint,
    social_security_point: SocialSecurityVisualizationPoint | None,
) -> MonthlyVisualizationDetail:
    provident_cash_receipt = max(0.0, row.provident_withdrawal)
    provident_ledger_outflows = [
        entry for entry in row.ledger_entries if entry.account == "provident" and entry.amount < 0
    ]
    social_security_ledger_outflows = [
        entry for entry in row.ledger_entries if entry.account == "social_security" and entry.amount < 0
    ]
    income_pie = _compact_items(
        [
            _breakdown_item("工资与其他现金收入", row.cash_income, kind="income"),
            _breakdown_item("养老金领取", row.pension_income, kind="income"),
            _breakdown_item("个人养老金领取净到账", row.personal_pension_withdrawal, kind="income"),
            _breakdown_item("公积金现金到账", provident_cash_receipt, kind="income"),
            _breakdown_item("投资卖出到账", row.investment_sell_proceeds, kind="income"),
            _breakdown_item("交易现金流入", row.transaction_cash_in, kind="income"),
            _breakdown_item("投资账户收益", row.investment_return, kind="asset"),
            _breakdown_item("个人养老金账户收益", row.personal_pension_return, kind="asset"),
        ]
    )
    expense_pie = _compact_items(
        [
            _breakdown_item("基础生活支出", row.living_expense, kind="expense"),
            _breakdown_item("阶段性与定时支出", row.scheduled_expense, kind="expense"),
            _breakdown_item("装修规划事件", row.renovation_expense, kind="expense"),
            _breakdown_item("养娃计划支出", row.child_expense, kind="expense"),
            _breakdown_item("灵活就业自缴社保公积金", row.career_shock_self_payment, kind="expense"),
            _breakdown_item("已有固定还款", row.regular_debt_payment, kind="expense"),
            _breakdown_item("已有贷款还款", row.phased_loan_payment, kind="expense"),
            _breakdown_item("房贷现金还款", row.house_payment, kind="expense"),
            _breakdown_item("车贷现金还款", row.vehicle_payment, kind="expense"),
            _breakdown_item("车辆运营成本", row.vehicle_operating_cost, kind="expense"),
            _breakdown_item("车辆牌照租赁", row.vehicle_plate_rental_payment, kind="expense"),
            _breakdown_item("无车通勤成本", row.no_car_commute_cost, kind="expense"),
            _breakdown_item("理财买入净额", max(0.0, row.investment_contribution - row.investment_fee), kind="asset"),
            _breakdown_item("理财收益税", row.investment_tax, kind="expense"),
            _breakdown_item("理财交易手续费", row.investment_fee, kind="expense"),
            _breakdown_item("个人养老金缴费", row.personal_pension_contribution, kind="asset"),
            _breakdown_item("交易现金支出", row.transaction_cash_out, kind="expense"),
        ]
    )
    loan_payment_pie = _compact_items(
        [
            _breakdown_item("商贷合同还款", max(0.0, row.house_contract_payment - row.provident_house_offset_payment), kind="expense"),
            _breakdown_item("公积金账户抵扣/冲本金", row.provident_house_offset_payment, kind="asset"),
            _breakdown_item("车贷现金还款", row.vehicle_payment, kind="expense"),
            _breakdown_item("已有固定还款", row.regular_debt_payment, kind="expense"),
            _breakdown_item("已有贷款还款", row.phased_loan_payment, kind="expense"),
        ]
    )
    provident_inflow_pie = _compact_items(
        [
            _breakdown_item("公积金缴存", row.provident_deposit, kind="income"),
        ]
    )
    provident_outflow_pie = _compact_items(
        [
            _breakdown_item("公积金现金提取", row.provident_withdrawal, kind="expense"),
            _breakdown_item("公积金抵扣/冲本金", row.provident_house_offset_payment, kind="expense"),
            *[
                _breakdown_item(entry.label, abs(entry.amount), kind="expense")
                for entry in provident_ledger_outflows
                if entry.category not in {"provident_withdrawal"}
            ],
        ]
    )
    social_security_inflow_pie = _compact_items(
        [
            _breakdown_item(
                "养老个人缴入",
                social_security_point.pension_contribution if social_security_point else 0.0,
                kind="income",
            ),
            _breakdown_item(
                "医保个人划入",
                social_security_point.medical_contribution if social_security_point else 0.0,
                kind="income",
            ),
            _breakdown_item(
                "退休医保划入",
                social_security_point.medical_retiree_transfer if social_security_point else 0.0,
                kind="income",
            ),
            _breakdown_item(
                "养老医保账户利息",
                (
                    social_security_point.pension_interest + social_security_point.medical_interest
                    if social_security_point
                    else 0.0
                ),
                kind="income",
            ),
            _breakdown_item("个人养老金缴费", row.personal_pension_contribution, kind="asset"),
            _breakdown_item("个人养老金收益", row.personal_pension_return, kind="asset"),
        ]
    )
    social_security_outflow_pie = _compact_items(
        [
            _breakdown_item("个人养老金赎回或退保费用", row.personal_pension_redemption_fee, kind="expense"),
            _breakdown_item("个人养老金领取税", row.personal_pension_withdrawal_tax, kind="expense"),
            *[
                _breakdown_item(entry.label, abs(entry.amount), kind="expense")
                for entry in social_security_ledger_outflows
            ],
        ]
    )
    cash_flow_items = _compact_items(
        [
            _breakdown_item("现金收入", row.cash_income, kind="income", amount=row.cash_income),
            _breakdown_item("养老金领取", row.pension_income, kind="income", amount=row.pension_income),
            _breakdown_item("个人养老金领取净到账", row.personal_pension_withdrawal, kind="income", amount=row.personal_pension_withdrawal),
            _breakdown_item("公积金现金到账", provident_cash_receipt, kind="income", amount=provident_cash_receipt),
            _breakdown_item("投资卖出到账", row.investment_sell_proceeds, kind="income", amount=row.investment_sell_proceeds),
            _breakdown_item("基础生活支出", row.living_expense, kind="expense", amount=-row.living_expense),
            _breakdown_item("阶段性与定时支出", row.scheduled_expense, kind="expense", amount=-row.scheduled_expense),
            _breakdown_item("装修规划事件", row.renovation_expense, kind="expense", amount=-row.renovation_expense),
            _breakdown_item("养娃计划支出", row.child_expense, kind="expense", amount=-row.child_expense),
            _breakdown_item("债务还款", row.debt_payment, kind="expense", amount=-row.debt_payment),
            _breakdown_item("房贷现金还款", row.house_payment, kind="expense", amount=-row.house_payment),
            _breakdown_item("通勤/用车成本", row.vehicle_payment + row.vehicle_operating_cost + row.no_car_commute_cost, kind="expense", amount=-(row.vehicle_payment + row.vehicle_operating_cost + row.no_car_commute_cost)),
            _breakdown_item("理财买入净额", max(0.0, row.investment_contribution - row.investment_fee), kind="asset", amount=-max(0.0, row.investment_contribution - row.investment_fee)),
            _breakdown_item("个人养老金缴费", row.personal_pension_contribution, kind="asset", amount=-row.personal_pension_contribution),
            _breakdown_item("其它交易现金净额", abs(row.transaction_cash_in - max(0.0, row.transaction_cash_out - row.renovation_expense)), kind="expense", amount=row.transaction_cash_in - max(0.0, row.transaction_cash_out - row.renovation_expense)),
            _breakdown_item("当月现金净流入", abs(row.monthly_cash_delta), kind="result", amount=row.monthly_cash_delta),
        ]
    )
    drivers = sorted(
        [item for item in cash_flow_items if item.kind != "result" and abs(item.amount or 0) > 0],
        key=lambda item: abs(item.amount or 0),
        reverse=True,
    )[:5]
    advisor_text = (
        f"第 {row.month} 个月现金净流入 {row.monthly_cash_delta:.0f} 元，现金账户增加。"
        if row.monthly_cash_delta >= 0
        else f"第 {row.month} 个月现金净流出 {abs(row.monthly_cash_delta):.0f} 元，应重点检查交易、定投、车贷、房贷或阶段性支出。"
    )
    explanation_items = [
        {
            "title": "现金收入",
            "body": "工资、养老金、公积金现金到账和投资卖出到账由后端月度账本归集；税前工资、个人社保、公积金扣缴和个税不会混入现金收入饼图。",
        },
        {
            "title": "支出口径",
            "body": "支出构成只展示对现金账户或受限账户产生实际占用的项目；公积金账户抵扣、个人养老金缴费和理财买入按账户转移单独标识。",
        },
        {
            "title": "现金净流入",
            "body": "当月现金净流入来自后端账户推演结果，现金账户不会被解释为可为负余额；不足时应通过策略调整或现金缺口表达。",
        },
    ]
    return MonthlyVisualizationDetail(
        plan_variant=row.plan_variant,
        month=row.month,
        income_pie=income_pie,
        income_legend=income_pie,
        expense_pie=expense_pie,
        loan_payment_pie=loan_payment_pie,
        provident_inflow_pie=provident_inflow_pie,
        provident_outflow_pie=provident_outflow_pie,
        social_security_inflow_pie=social_security_inflow_pie,
        social_security_outflow_pie=social_security_outflow_pie,
        cash_flow_items=cash_flow_items,
        cash_flow_drivers=drivers,
        advisor_text=advisor_text,
        explanation_items=explanation_items,
    )


def build_monthly_visualization_details(
    monthly_cashflow: list[MonthlyCashflowPoint],
    social_security_visualization: list[SocialSecurityVisualizationPoint] | None = None,
) -> list[MonthlyVisualizationDetail]:
    social_security_by_plan_month = {
        (row.plan_variant, row.month): row
        for row in (social_security_visualization or [])
    }
    return [
        monthly_visualization_detail_from_inputs(
            row,
            social_security_by_plan_month.get((row.plan_variant, row.month)),
        )
        for row in monthly_cashflow
    ]


def annual_visualization_detail_from_summary(row: AnnualFinancialSummary) -> AnnualVisualizationDetail:
    cash_inflow = _compact_items(
        [
            _breakdown_item("工资及其他现金收入", max(0.0, row.cash_income - row.pension_income), kind="income"),
            _breakdown_item("养老金领取", row.pension_income, kind="income"),
            _breakdown_item("个人养老金领取净到账", row.personal_pension_withdrawal, kind="income"),
            _breakdown_item("公积金现金提取", row.provident_withdrawal, kind="income"),
            _breakdown_item("投资卖出到账", row.investment_sell_proceeds, kind="income"),
            _breakdown_item("交易现金流入", row.transaction_cash_in, kind="income"),
        ]
    )
    cash_outflow = _compact_items(
        [
            _breakdown_item("基础生活支出", row.living_expense, kind="expense"),
            _breakdown_item("计划支出", row.scheduled_expense, kind="expense"),
            _breakdown_item("装修规划事件", row.renovation_expense, kind="expense"),
            _breakdown_item("养娃计划支出", row.child_expense, kind="expense"),
            _breakdown_item("灵活就业自缴社保公积金", row.career_shock_self_payment, kind="expense"),
            _breakdown_item("已有贷款还款", row.debt_payment, kind="expense"),
            _breakdown_item("房贷现金还款", row.house_payment, kind="expense"),
            _breakdown_item("车贷现金还款", row.vehicle_payment, kind="expense"),
            _breakdown_item("养车现金支出", row.vehicle_operating_cost, kind="expense"),
            _breakdown_item("理财买入", row.investment_contribution, kind="asset"),
            _breakdown_item("理财收益税", row.investment_tax, kind="expense"),
            _breakdown_item("理财手续费", row.investment_fee, kind="expense"),
            _breakdown_item("个人养老金缴费", row.personal_pension_contribution, kind="asset"),
            _breakdown_item("其它交易现金流出", max(0.0, row.transaction_cash_out - row.renovation_expense), kind="expense"),
        ]
    )
    return AnnualVisualizationDetail(
        plan_variant=row.plan_variant,
        year=row.year,
        cash_inflow_pie=cash_inflow,
        cash_outflow_pie=cash_outflow,
        liquid_asset_pie=_compact_items(
            [
                _breakdown_item("现金账户", row.cash_balance_end, kind="asset"),
                _breakdown_item("投资账户", row.investment_balance_end, kind="asset"),
            ]
        ),
        fixed_asset_pie=_compact_items(
            [
                _breakdown_item("房产估值", row.property_asset_value_end, kind="asset"),
                _breakdown_item("车辆估值", row.vehicle_asset_value_end, kind="asset"),
            ]
        ),
        loan_payment_pie=_compact_items(
            [
                _breakdown_item("商贷合同还款", row.commercial_payment, kind="expense"),
                _breakdown_item("公积金贷银行卡还款", max(0.0, row.provident_payment - row.provident_monthly_withdrawal_payment), kind="expense"),
                _breakdown_item("公积金按月抵月供", row.provident_monthly_withdrawal_payment, kind="asset"),
                _breakdown_item("公积金半年度冲本金", row.provident_principal_offset_payment, kind="asset"),
                _breakdown_item("车贷现金还款", row.vehicle_loan_payment, kind="expense"),
                _breakdown_item("已有贷款还款", row.existing_loan_payment, kind="expense"),
                _breakdown_item("商贷额外还本", row.commercial_extra_principal_payment, kind="expense"),
                _breakdown_item("车贷额外还本", row.vehicle_extra_principal_payment, kind="expense"),
            ]
        ),
        loan_balance_pie=_compact_items(
            [
                _breakdown_item("商贷余额", row.commercial_loan_balance_end, kind="expense"),
                _breakdown_item("公积金贷余额", row.provident_loan_balance_end, kind="expense"),
                _breakdown_item("车贷余额", row.vehicle_loan_balance_end, kind="expense"),
                _breakdown_item("已有贷款余额", row.existing_loan_balance_end, kind="expense"),
            ]
        ),
        provident_flow_pie=_compact_items(
            [
                _breakdown_item("公积金缴存", row.provident_deposit, kind="income"),
                _breakdown_item("现金提取到账", row.provident_withdrawal, kind="income"),
                _breakdown_item("按月抵月供", row.provident_monthly_withdrawal_payment, kind="asset"),
                _breakdown_item("半年度冲本金", row.provident_principal_offset_payment, kind="asset"),
            ]
        ),
        social_security_inflow_pie=_compact_items(
            [
                _breakdown_item("养老个人缴入", row.pension_account_contribution, kind="income"),
                _breakdown_item("养老账户利息", row.pension_account_interest, kind="income"),
                _breakdown_item("医保个人划入", row.medical_account_contribution, kind="income"),
                _breakdown_item("退休医保划入", row.medical_account_retiree_transfer, kind="income"),
                _breakdown_item("医保账户利息", row.medical_account_interest, kind="income"),
            ]
        ),
        social_security_outflow_pie=_compact_items(
            [
                _breakdown_item("养老计发支出", row.pension_account_payout, kind="expense"),
                _breakdown_item("医保医疗支付", row.medical_account_healthcare_outflow, kind="expense"),
                _breakdown_item("医保互助扣缴", row.medical_account_mutual_aid_outflow, kind="expense"),
                _breakdown_item("个人养老金赎回或退保费用", row.personal_pension_redemption_fee, kind="expense"),
                _breakdown_item("个人养老金领取税", row.personal_pension_withdrawal_tax, kind="expense"),
            ]
        ),
        social_security_balance_pie=_compact_items(
            [
                _breakdown_item("养老保险个人账户", row.pension_account_balance_end, kind="asset"),
                _breakdown_item("医保个人账户", row.medical_account_balance_end, kind="asset"),
                _breakdown_item("个人养老金账户", row.personal_pension_balance_end, kind="asset"),
            ]
        ),
    )


def build_annual_visualization_details(
    annual_summaries: list[AnnualFinancialSummary],
) -> list[AnnualVisualizationDetail]:
    return [annual_visualization_detail_from_summary(row) for row in annual_summaries]


def build_tax_visualization_details(
    tax_year_summaries: list[TaxYearSummary],
    tax_monthly_points: list[TaxMonthlyPoint],
) -> list[TaxVisualizationDetail]:
    yearly_by_year = {row.year: row for row in tax_year_summaries}
    years = sorted(set(yearly_by_year) | {row.year for row in tax_monthly_points})
    rows: list[TaxVisualizationDetail] = []
    for year in years:
        annual = yearly_by_year.get(year)
        annual_member = _compact_items(
            [
                _breakdown_item(f"{member.member_name}年度个税", member.total_tax, kind="expense")
                for member in (annual.summaries if annual else [])
            ]
        )
        annual_type = _compact_items(
            [
                _breakdown_item("工资薪金个税", annual.salary_tax if annual else 0.0, kind="expense"),
                _breakdown_item("年终奖个税", annual.bonus_tax if annual else 0.0, kind="expense"),
            ]
        )
        rows.append(
            TaxVisualizationDetail(
                year=year,
                month=None,
                annual_tax_member_pie=annual_member,
                annual_tax_type_pie=annual_type,
            )
        )
    for row in tax_monthly_points:
        annual = yearly_by_year.get(row.year)
        annual_member = _compact_items(
            [
                _breakdown_item(f"{member.member_name}年度个税", member.total_tax, kind="expense")
                for member in (annual.summaries if annual else [])
            ]
        )
        rows.append(
            TaxVisualizationDetail(
                year=row.year,
                month=row.month,
                monthly_tax_member_pie=_compact_items(
                    [
                        _breakdown_item(f"{member.member_name}当月个税", member.total_income_tax, kind="expense")
                        for member in row.member_points
                    ]
                ),
                monthly_deduction_pie=_compact_items(
                    [
                        item
                        for member in row.member_points
                        for item in [
                            _breakdown_item(f"{member.member_name}个人社保", member.personal_social, kind="deduction"),
                            _breakdown_item(f"{member.member_name}个人公积金", member.personal_housing_fund, kind="deduction"),
                            _breakdown_item(
                                f"{member.member_name}专项附加扣除",
                                member.special_additional_deduction + member.elderly_care_deduction,
                                kind="deduction",
                            ),
                            _breakdown_item(f"{member.member_name}其他扣除", member.other_deduction, kind="deduction"),
                            _breakdown_item(f"{member.member_name}个人养老金扣除", member.personal_pension_contribution, kind="deduction"),
                        ]
                    ]
                ),
                annual_tax_member_pie=annual_member,
                annual_tax_type_pie=_compact_items(
                    [
                        _breakdown_item("工资薪金个税", annual.salary_tax if annual else 0.0, kind="expense"),
                        _breakdown_item("年终奖个税", annual.bonus_tax if annual else 0.0, kind="expense"),
                    ]
                ),
            )
        )
    return rows
