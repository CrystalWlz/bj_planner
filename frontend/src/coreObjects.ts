import { money } from "./format";
import type {
  AccountCalibrationTarget,
  AccountConceptSummary,
  CalculationContextCoreObjectSnapshot,
  CoreObjectGroupSummary,
  CoreObjectRecord,
  CoreObjectType,
  HouseholdData
} from "./types";

type CoreObjectLike = CalculationContextCoreObjectSnapshot | CoreObjectRecord;

export interface CoreObjectOwnerSummary {
  ownerKey: string;
  totalCount: number;
  visibleObjectCount: number;
  countsByType: Record<CoreObjectType, number>;
  balancesByType: Record<CoreObjectType, number>;
  assetBalance: number;
  loanBalance: number;
  adjustmentBalance: number;
}

export const CORE_OBJECT_GROUP_CODES = {
  liquidAssets: "liquid_assets",
  restrictedAccounts: "restricted_accounts",
  fixedAssets: "fixed_assets",
  loanAccounts: "loan_accounts",
} as const;

export const ACCOUNT_CONCEPT_CODES = {
  cash: "cash_account",
  investment: "investment_account",
  liquidAssets: "liquid_asset_account",
  provident: "provident_account",
  socialSecurity: "social_security_personal_accounts",
  pension: "pension_account",
  medical: "medical_account",
  personalPension: "personal_pension_account",
  fixedAsset: "fixed_asset_account",
  loan: "loan_account",
  accountCalibration: "account_calibration",
  netWorth: "net_worth",
  policyPack: "policy_pack",
} as const;

export const ACCOUNT_CONCEPT_DASHBOARD_CODES = [
  ACCOUNT_CONCEPT_CODES.cash,
  ACCOUNT_CONCEPT_CODES.investment,
  ACCOUNT_CONCEPT_CODES.provident,
  ACCOUNT_CONCEPT_CODES.pension,
  ACCOUNT_CONCEPT_CODES.medical,
  ACCOUNT_CONCEPT_CODES.personalPension,
  ACCOUNT_CONCEPT_CODES.loan,
] as const;

export const ACCOUNT_CALIBRATION_TARGET_OPTIONS: Array<{ value: AccountCalibrationTarget; label: string }> = [
  { value: "cash", label: "现金账户" },
  { value: "investment", label: "投资账户" },
  { value: "provident", label: "公积金账户" },
  { value: "pension", label: "基本养老个人账户" },
  { value: "medical", label: "医保个人账户" },
  { value: "property_asset", label: "房产资产" },
  { value: "vehicle_asset", label: "车辆资产" },
  { value: "fixed_asset", label: "固定资产" },
  { value: "total_loan", label: "贷款余额" }
];

export const CORE_OBJECT_OWNER_VISIBLE_TYPES = ["asset", "loan", "adjustment"] as const satisfies readonly CoreObjectType[];
export const CORE_OBJECT_OWNER_BALANCE_TYPES = ["asset", "loan"] as const satisfies readonly CoreObjectType[];

function coreObjectOwnerBalance(
  type: (typeof CORE_OBJECT_OWNER_BALANCE_TYPES)[number],
  balancesByType: Record<CoreObjectType, number>
) {
  return balancesByType[type];
}

export function accountConceptMap(accountConcepts: AccountConceptSummary[]) {
  return new Map(accountConcepts.map((item) => [item.code, item]));
}

export function coreObjectGroupMap(coreObjectGroups: CoreObjectGroupSummary[]) {
  return new Map(coreObjectGroups.map((item) => [item.code, item]));
}

export function coreObjectBalanceText(item: AccountConceptSummary | CoreObjectGroupSummary | undefined, waitingText = "等待后端同步") {
  return item ? money(item.current_balance) : waitingText;
}

export function coreObjectCountText(item: AccountConceptSummary | CoreObjectGroupSummary | undefined, unit = "个") {
  return item ? `${item.core_object_count} ${unit}` : "等待同步";
}

export function accountConceptBalanceText(
  accountConcepts: AccountConceptSummary[],
  code: string,
  waitingText = "等待后端同步"
) {
  return coreObjectBalanceText(accountConceptMap(accountConcepts).get(code), waitingText);
}

export function accountConceptBalanceTextWithHouseholdFallback(
  accountConcepts: AccountConceptSummary[],
  code: string,
  household: HouseholdData,
  waitingText = "等待后端同步"
) {
  const concept = accountConceptMap(accountConcepts).get(code);
  if (concept) return coreObjectBalanceText(concept, waitingText);
  const fallbackBalance = householdAccountConceptFallbackBalance(household, code);
  return fallbackBalance === undefined ? waitingText : money(fallbackBalance);
}

export function accountConceptBalanceValue(accountConcepts: AccountConceptSummary[], code: string) {
  return accountConceptMap(accountConcepts).get(code)?.current_balance;
}

export function householdAccountConceptFallbackBalance(household: HouseholdData, code: string) {
  const fallbackByCode: Partial<Record<string, number>> = {
    [ACCOUNT_CONCEPT_CODES.cash]: household.cash_account_balance ?? 0,
    [ACCOUNT_CONCEPT_CODES.investment]: household.investments ?? 0,
    [ACCOUNT_CONCEPT_CODES.provident]: household.members.reduce(
      (sum, member) => sum + (member.provident_account_enabled ? member.provident_fund_balance ?? 0 : 0),
      0
    ),
    [ACCOUNT_CONCEPT_CODES.pension]: household.members.reduce(
      (sum, member) => sum + (member.pension_account_enabled ? member.pension_account_balance ?? 0 : 0),
      0
    ),
    [ACCOUNT_CONCEPT_CODES.medical]: household.members.reduce(
      (sum, member) => sum + (member.medical_account_enabled ? member.medical_account_balance ?? 0 : 0),
      0
    ),
    [ACCOUNT_CONCEPT_CODES.personalPension]: household.members.reduce(
      (sum, member) => sum + (member.personal_pension_account_enabled ? member.personal_pension_account_balance ?? 0 : 0),
      0
    ),
  };
  return fallbackByCode[code];
}

export function calibrationDefaultAmountFromConcepts(
  accountConcepts: AccountConceptSummary[],
  coreObjectGroups: CoreObjectGroupSummary[],
  target: AccountCalibrationTarget,
  fallbackAmount: number
) {
  const conceptByTarget: Partial<Record<AccountCalibrationTarget, string>> = {
    cash: ACCOUNT_CONCEPT_CODES.cash,
    investment: ACCOUNT_CONCEPT_CODES.investment,
    provident: ACCOUNT_CONCEPT_CODES.provident,
    pension: ACCOUNT_CONCEPT_CODES.pension,
    medical: ACCOUNT_CONCEPT_CODES.medical,
  };
  const groupByTarget: Partial<Record<AccountCalibrationTarget, string>> = {
    fixed_asset: CORE_OBJECT_GROUP_CODES.fixedAssets,
    property_asset: CORE_OBJECT_GROUP_CODES.fixedAssets,
    vehicle_asset: CORE_OBJECT_GROUP_CODES.fixedAssets,
    total_loan: CORE_OBJECT_GROUP_CODES.loanAccounts,
  };
  const conceptCode = conceptByTarget[target];
  if (conceptCode) {
    return accountConceptBalanceValue(accountConcepts, conceptCode) ?? fallbackAmount;
  }
  const groupCode = groupByTarget[target];
  if (groupCode) {
    return coreObjectGroupMap(coreObjectGroups).get(groupCode)?.current_balance ?? fallbackAmount;
  }
  return fallbackAmount;
}

export function calibrationFallbackAmountFromHousehold(household: HouseholdData, target: AccountCalibrationTarget) {
  const fallbackByTarget: Record<AccountCalibrationTarget, number> = {
    cash: household.cash_account_balance ?? 0,
    investment: household.investments ?? 0,
    provident: household.members.reduce((sum, member) => sum + (member.provident_account_enabled ? member.provident_fund_balance ?? 0 : 0), 0),
    pension: household.members.reduce((sum, member) => sum + (member.pension_account_enabled ? member.pension_account_balance ?? 0 : 0), 0),
    medical: household.members.reduce((sum, member) => sum + (member.medical_account_enabled ? member.medical_account_balance ?? 0 : 0), 0),
    property_asset: 0,
    vehicle_asset: 0,
    fixed_asset: household.members.reduce((sum, member) => sum + (member.initial_other_asset_value ?? 0), 0),
    total_loan: household.phased_loans.reduce((sum, loan) => sum + (loan.principal ?? 0), 0)
  };
  return fallbackByTarget[target] ?? 0;
}

export function dashboardAccountConcepts(accountConcepts: AccountConceptSummary[]) {
  const conceptByCode = accountConceptMap(accountConcepts);
  return ACCOUNT_CONCEPT_DASHBOARD_CODES
    .map((code) => conceptByCode.get(code))
    .filter((item): item is AccountConceptSummary => Boolean(item));
}

export function coreObjectOwnerKey(item: CoreObjectLike) {
  return "data" in item ? item.data.owner_key : item.owner_key;
}

export function coreObjectType(item: CoreObjectLike) {
  return "data" in item ? item.data.object_type : item.object_type;
}

export function coreObjectBalance(item: CoreObjectLike) {
  return "data" in item ? item.data.current_balance : item.current_balance;
}

function emptyCoreObjectTypeMap() {
  return {
    account: 0,
    loan: 0,
    asset: 0,
    adjustment: 0,
  } satisfies Record<CoreObjectType, number>;
}

export function coreObjectOwnerSummaryByOwner(coreObjects: CoreObjectLike[]) {
  const objectsByOwner = new Map<string, CoreObjectLike[]>();
  for (const item of coreObjects) {
    const ownerKey = coreObjectOwnerKey(item);
    if (!ownerKey) continue;
    objectsByOwner.set(ownerKey, [...(objectsByOwner.get(ownerKey) ?? []), item]);
  }
  return new Map(
    Array.from(objectsByOwner.entries()).map(([ownerKey, ownedObjects]) => {
      const countsByType = emptyCoreObjectTypeMap();
      const balancesByType = emptyCoreObjectTypeMap();
      for (const item of ownedObjects) {
        const type = coreObjectType(item);
        const balance = Math.max(0, coreObjectBalance(item));
        countsByType[type] += 1;
        balancesByType[type] += balance;
      }
      const visibleObjectCount = CORE_OBJECT_OWNER_VISIBLE_TYPES.reduce(
        (sum, type) => sum + countsByType[type],
        0
      );
      return [ownerKey, {
        ownerKey,
        totalCount: ownedObjects.length,
        visibleObjectCount,
        countsByType,
        balancesByType,
        assetBalance: coreObjectOwnerBalance("asset", balancesByType),
        loanBalance: coreObjectOwnerBalance("loan", balancesByType),
        adjustmentBalance: balancesByType.adjustment,
      } satisfies CoreObjectOwnerSummary];
    })
  );
}

export function coreObjectOwnerSummaryText(summary: CoreObjectOwnerSummary | undefined) {
  if (!summary || !summary.visibleObjectCount) return "";
  const parts = [`对象 ${summary.visibleObjectCount}`];
  if (summary.assetBalance > 0) parts.push(`资产/目标 ${money(summary.assetBalance)}`);
  if (summary.loanBalance > 0) parts.push(`规划贷款 ${money(summary.loanBalance)}`);
  if (summary.countsByType.adjustment > 0) parts.push(`校准 ${summary.countsByType.adjustment}`);
  return parts.join(" · ");
}

export function coreObjectSummaryByOwner(coreObjects: CoreObjectLike[]) {
  const summaryByOwner = coreObjectOwnerSummaryByOwner(coreObjects);
  return new Map(
    Array.from(summaryByOwner.entries()).map(([ownerKey, summary]) => [
      ownerKey,
      coreObjectOwnerSummaryText(summary),
    ])
  );
}
