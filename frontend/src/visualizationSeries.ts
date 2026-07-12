import type {
  LoanVisualizationPoint,
  MonthlyCashflowPoint,
  MonthlyLedgerEntry,
  ProvidentVisualizationPoint,
  SocialSecurityVisualizationPoint
} from "./types";

export interface MonthlyChartPoint {
  month: number;
  name: string;
  period: string;
  现金池: number;
  投资资产: number;
  固定资产: number;
  房产估值: number;
  车辆估值: number;
  第一辆车估值: number;
  第二辆车估值: number;
  流动资产: number;
  流动固定资产合计: number;
  净资产: number;
  happinessScore: number;
  公积金余额: number;
  安全垫: number;
  cashIncome: number;
  livingExpense: number;
  baseLivingExpense: number;
  scheduledLivingExpense: number;
  childExpense: number;
  careerShockSelfPayment: number;
  scheduledExpenseRows: Array<{ name: string; amount: number }>;
  debtPayment: number;
  regularDebtPayment: number;
  phasedLoanPayment: number;
  carCost: number;
  firstCarLoanPayment: number;
  firstCarEnergyCost: number;
  firstCarInsuranceCost: number;
  firstCarMaintenanceCost: number;
  firstCarParkingCost: number;
  secondCarLoanPayment: number;
  secondCarEnergyCost: number;
  secondCarInsuranceCost: number;
  secondCarMaintenanceCost: number;
  secondCarParkingCost: number;
  noCarCommuteCost: number;
  vehiclePlateRentalPayment: number;
  housePayment: number;
  houseContractPayment: number;
  providentHouseOffsetPayment: number;
  providentHousePaymentRelief: number;
  providentHousePayment: number;
  providentHouseContractPayment: number;
  commercialHousePayment: number;
  commercialExtraPrincipalPayment: number;
  vehicleExtraPrincipalPayment: number;
  monthlyInvestment: number;
  monthlyInvestmentBase: number;
  monthlyInvestmentCashSweep: number;
  monthlyInvestmentBuyFee: number;
  monthlyInvestmentNet: number;
  investmentReturn: number;
  investmentTax: number;
  investmentSellFee: number;
  investmentSellProceeds: number;
  personalPensionContribution: number;
  personalPensionReturn: number;
  personalPensionBalance: number;
  purchaseCashOut: number;
  purchaseCashIn: number;
  houseTransactionCashOut: number;
  carDownPaymentCashOut: number;
  secondCarDownPaymentCashOut: number;
  monthlyCashDelta: number;
  providentInterest: number;
  providentDeposit: number;
  providentRentWithdrawal: number;
  providentUpfrontWithdrawal: number;
  providentPostTransactionWithdrawal: number;
  providentAgreedWithdrawal: number;
  providentRetirementWithdrawal: number;
  providentLoanOffsetPayment: number;
  providentMonthlyRepaymentWithdrawal: number;
  providentPrincipalOffsetPayment: number;
  providentMonthlyWithdrawal: number;
  pensionAccountBalance: number;
  medicalAccountBalance: number;
  socialSecurityAccountBalance: number;
  backendLedgerEntries: MonthlyLedgerEntry[];
}

interface BuildMonthlyChartSeriesOptions {
  backendCashflowSeries: MonthlyCashflowPoint[];
  horizonMonths: number;
  requiredLiquidityReserve: number;
  loanVisualizationByMonth: Map<number, LoanVisualizationPoint>;
  providentVisualizationByMonth: Map<number, ProvidentVisualizationPoint>;
  socialSecurityVisualizationByMonth: Map<number, SocialSecurityVisualizationPoint>;
  formatMonthName: (month: number) => string;
  scheduledExpenseRowsAt: (month: number) => MonthlyChartPoint["scheduledExpenseRows"];
}

export function buildMonthlyChartSeries({
  backendCashflowSeries,
  horizonMonths,
  requiredLiquidityReserve,
  loanVisualizationByMonth,
  providentVisualizationByMonth,
  socialSecurityVisualizationByMonth,
  formatMonthName,
  scheduledExpenseRowsAt,
}: BuildMonthlyChartSeriesOptions): MonthlyChartPoint[] {
  return backendCashflowSeries
    .filter((item) => item.month <= horizonMonths)
    .map((item) => {
      const loanPoint = loanVisualizationByMonth.get(item.month);
      const providentPoint = providentVisualizationByMonth.get(item.month);
      const socialSecurityPoint = socialSecurityVisualizationByMonth.get(item.month);
      const houseContractPayment = item.house_contract_payment ?? loanPoint?.home_monthly_payment ?? 0;
      const providentHouseOffsetPayment =
        item.provident_house_offset_payment ??
        loanPoint?.provident_offset_payment ??
        (providentPoint
          ? (providentPoint.monthly_repayment_withdrawal ?? 0) + (providentPoint.loan_offset_payment ?? 0)
          : 0);
      const providentHousePaymentRelief =
        item.provident_house_payment_relief ??
        loanPoint?.provident_monthly_payment_relief ??
        Math.min(loanPoint?.provident_monthly_payment ?? 0, providentHouseOffsetPayment);
      const housePayment = item.house_payment ?? Math.max(0, houseContractPayment - providentHousePaymentRelief);
      const vehiclePayment = item.vehicle_payment ?? loanPoint?.vehicle_monthly_payment ?? 0;
      const debtPayment = item.debt_payment ?? loanPoint?.existing_monthly_payment ?? 0;
      const vehicleOperatingCost = item.vehicle_operating_cost ?? 0;
      const propertyAssetValue = item.property_asset_value ?? 0;
      const vehicleAssetValue = item.vehicle_asset_value ?? Math.max(0, item.fixed_asset_value - propertyAssetValue);
      const firstVehicleAssetValue = item.first_vehicle_asset_value ?? vehicleAssetValue;
      const secondVehicleAssetValue = item.second_vehicle_asset_value ?? 0;
      const investmentBuyFee = item.investment_buy_fee ?? item.investment_fee ?? 0;
      const investmentSellFee = item.investment_sell_fee ?? 0;
      const investmentContribution = item.investment_contribution ?? 0;
      const liquidAssetValue = item.liquid_asset_value ?? item.cash_balance + item.investment_balance;

      return {
        month: item.month,
        name: formatMonthName(item.month),
        period: item.phase,
        现金池: Math.round(item.cash_balance),
        投资资产: Math.round(item.investment_balance),
        固定资产: Math.round(item.fixed_asset_value),
        房产估值: Math.round(propertyAssetValue),
        车辆估值: Math.round(vehicleAssetValue),
        第一辆车估值: Math.round(firstVehicleAssetValue),
        第二辆车估值: Math.round(secondVehicleAssetValue),
        流动资产: Math.round(liquidAssetValue),
        流动固定资产合计: Math.round(liquidAssetValue + item.fixed_asset_value),
        净资产: Math.round(item.net_worth),
        happinessScore: item.happiness_score,
        公积金余额: Math.round(item.provident_balance),
        安全垫: Math.round(requiredLiquidityReserve),
        cashIncome: item.cash_income,
        livingExpense: item.living_expense + item.scheduled_expense + (item.child_expense ?? 0) + (item.career_shock_self_payment ?? 0),
        baseLivingExpense: item.living_expense,
        scheduledLivingExpense: item.scheduled_expense,
        childExpense: item.child_expense ?? 0,
        careerShockSelfPayment: item.career_shock_self_payment ?? 0,
        scheduledExpenseRows: scheduledExpenseRowsAt(item.month),
        debtPayment,
        regularDebtPayment: item.regular_debt_payment ?? Math.max(0, debtPayment - (item.phased_loan_payment ?? 0)),
        phasedLoanPayment: item.phased_loan_payment,
        carCost: vehiclePayment + vehicleOperatingCost,
        firstCarLoanPayment: item.first_vehicle_payment ?? vehiclePayment,
        firstCarEnergyCost: item.first_vehicle_energy_cost ?? 0,
        firstCarInsuranceCost: item.first_vehicle_insurance_cost ?? 0,
        firstCarMaintenanceCost: item.first_vehicle_maintenance_cost ?? 0,
        firstCarParkingCost: item.first_vehicle_parking_cost ?? 0,
        secondCarLoanPayment: item.second_vehicle_payment ?? 0,
        secondCarEnergyCost: item.second_vehicle_energy_cost ?? 0,
        secondCarInsuranceCost: item.second_vehicle_insurance_cost ?? 0,
        secondCarMaintenanceCost: item.second_vehicle_maintenance_cost ?? 0,
        secondCarParkingCost: item.second_vehicle_parking_cost ?? 0,
        noCarCommuteCost: item.no_car_commute_cost ?? 0,
        vehiclePlateRentalPayment: item.vehicle_plate_rental_payment ?? 0,
        housePayment,
        houseContractPayment,
        providentHouseOffsetPayment,
        providentHousePaymentRelief,
        providentHousePayment: Math.max(0, (loanPoint?.provident_monthly_payment ?? 0) - providentHousePaymentRelief),
        providentHouseContractPayment: loanPoint?.provident_monthly_payment ?? 0,
        commercialHousePayment: loanPoint?.commercial_monthly_payment ?? 0,
        commercialExtraPrincipalPayment: loanPoint?.commercial_extra_principal_payment ?? 0,
        vehicleExtraPrincipalPayment: loanPoint?.vehicle_extra_principal_payment ?? 0,
        monthlyInvestment: investmentContribution,
        monthlyInvestmentBase: item.investment_contribution_base ?? investmentContribution,
        monthlyInvestmentCashSweep: item.investment_contribution_cash_sweep ?? 0,
        monthlyInvestmentBuyFee: investmentBuyFee,
        monthlyInvestmentNet: Math.max(0, investmentContribution - investmentBuyFee),
        investmentReturn: item.investment_return,
        investmentTax: item.investment_tax ?? 0,
        investmentSellFee,
        investmentSellProceeds: item.investment_sell_proceeds ?? 0,
        personalPensionContribution: item.personal_pension_contribution ?? 0,
        personalPensionReturn: item.personal_pension_return ?? 0,
        personalPensionBalance: item.personal_pension_balance ?? 0,
        purchaseCashOut: item.transaction_cash_out,
        purchaseCashIn: item.transaction_cash_in,
        houseTransactionCashOut: Math.max(0, item.transaction_cash_out - (item.vehicle_down_payment ?? 0)),
        carDownPaymentCashOut: item.first_vehicle_down_payment ?? item.vehicle_down_payment ?? 0,
        secondCarDownPaymentCashOut: item.second_vehicle_down_payment ?? 0,
        monthlyCashDelta: item.monthly_cash_delta,
        providentInterest: providentPoint?.interest ?? 0,
        providentDeposit: item.provident_deposit,
        providentRentWithdrawal: providentPoint?.rent_withdrawal ?? 0,
        providentUpfrontWithdrawal: providentPoint?.upfront_withdrawal ?? 0,
        providentPostTransactionWithdrawal: providentPoint?.post_transaction_withdrawal ?? 0,
        providentAgreedWithdrawal: providentPoint?.agreed_withdrawal ?? 0,
        providentRetirementWithdrawal: providentPoint?.retirement_withdrawal ?? 0,
        providentLoanOffsetPayment: providentHouseOffsetPayment,
        providentMonthlyRepaymentWithdrawal: providentPoint?.monthly_repayment_withdrawal ?? 0,
        providentPrincipalOffsetPayment: providentPoint?.loan_offset_payment ?? 0,
        providentMonthlyWithdrawal: item.provident_withdrawal,
        pensionAccountBalance: item.pension_account_balance ?? socialSecurityPoint?.pension_balance_end ?? 0,
        medicalAccountBalance: item.medical_account_balance ?? socialSecurityPoint?.medical_balance_end ?? 0,
        socialSecurityAccountBalance: item.social_security_account_balance ?? socialSecurityPoint?.total_balance_end ?? 0,
        backendLedgerEntries: item.ledger_entries
      };
    });
}

export function emptyMonthlyChartPoint(
  name: string,
  requiredLiquidityReserve: number
): MonthlyChartPoint {
  return {
    month: 0,
    name,
    period: "等待后端计算",
    现金池: 0,
    投资资产: 0,
    固定资产: 0,
    房产估值: 0,
    车辆估值: 0,
    第一辆车估值: 0,
    第二辆车估值: 0,
    流动资产: 0,
    流动固定资产合计: 0,
    净资产: 0,
    happinessScore: 0,
    公积金余额: 0,
    安全垫: Math.round(requiredLiquidityReserve),
    cashIncome: 0,
    livingExpense: 0,
    baseLivingExpense: 0,
    scheduledLivingExpense: 0,
    childExpense: 0,
    careerShockSelfPayment: 0,
    scheduledExpenseRows: [],
    debtPayment: 0,
    regularDebtPayment: 0,
    phasedLoanPayment: 0,
    carCost: 0,
    firstCarLoanPayment: 0,
    firstCarEnergyCost: 0,
    firstCarInsuranceCost: 0,
    firstCarMaintenanceCost: 0,
    firstCarParkingCost: 0,
    secondCarLoanPayment: 0,
    secondCarEnergyCost: 0,
    secondCarInsuranceCost: 0,
    secondCarMaintenanceCost: 0,
    secondCarParkingCost: 0,
    noCarCommuteCost: 0,
    vehiclePlateRentalPayment: 0,
    housePayment: 0,
    houseContractPayment: 0,
    providentHouseOffsetPayment: 0,
    providentHousePaymentRelief: 0,
    providentHousePayment: 0,
    providentHouseContractPayment: 0,
    commercialHousePayment: 0,
    commercialExtraPrincipalPayment: 0,
    vehicleExtraPrincipalPayment: 0,
    monthlyInvestment: 0,
    monthlyInvestmentBase: 0,
    monthlyInvestmentCashSweep: 0,
    monthlyInvestmentBuyFee: 0,
    monthlyInvestmentNet: 0,
    investmentReturn: 0,
    investmentTax: 0,
    investmentSellFee: 0,
    investmentSellProceeds: 0,
    personalPensionContribution: 0,
    personalPensionReturn: 0,
    personalPensionBalance: 0,
    purchaseCashOut: 0,
    purchaseCashIn: 0,
    houseTransactionCashOut: 0,
    carDownPaymentCashOut: 0,
    secondCarDownPaymentCashOut: 0,
    monthlyCashDelta: 0,
    providentInterest: 0,
    providentDeposit: 0,
    providentRentWithdrawal: 0,
    providentUpfrontWithdrawal: 0,
    providentPostTransactionWithdrawal: 0,
    providentAgreedWithdrawal: 0,
    providentRetirementWithdrawal: 0,
    providentLoanOffsetPayment: 0,
    providentMonthlyRepaymentWithdrawal: 0,
    providentPrincipalOffsetPayment: 0,
    providentMonthlyWithdrawal: 0,
    pensionAccountBalance: 0,
    medicalAccountBalance: 0,
    socialSecurityAccountBalance: 0,
    backendLedgerEntries: []
  };
}
