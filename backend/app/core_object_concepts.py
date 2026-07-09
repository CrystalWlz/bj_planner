from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountConceptDefinition:
    code: str
    name: str
    category: str
    description: str
    managed_by: str


@dataclass(frozen=True)
class CoreObjectGroupDefinition:
    code: str
    name: str
    category: str
    concept_codes: tuple[str, ...]
    description: str


CASH_ACCOUNT_CONCEPT = "cash_account"
INVESTMENT_ACCOUNT_CONCEPT = "investment_account"
LIQUID_ASSET_ACCOUNT_CONCEPT = "liquid_asset_account"
PROVIDENT_ACCOUNT_CONCEPT = "provident_account"
SOCIAL_SECURITY_PERSONAL_ACCOUNTS_CONCEPT = "social_security_personal_accounts"
PENSION_ACCOUNT_CONCEPT = "pension_account"
MEDICAL_ACCOUNT_CONCEPT = "medical_account"
PERSONAL_PENSION_ACCOUNT_CONCEPT = "personal_pension_account"
FIXED_ASSET_ACCOUNT_CONCEPT = "fixed_asset_account"
LOAN_ACCOUNT_CONCEPT = "loan_account"
ACCOUNT_CALIBRATION_CONCEPT = "account_calibration"

ACCOUNT_CONCEPT_DEFINITIONS: tuple[AccountConceptDefinition, ...] = (
    AccountConceptDefinition(
        code=CASH_ACCOUNT_CONCEPT,
        name="现金账户",
        category="cash",
        description="由后端逐月推演的自由现金余额，只记录工资现金入账、日常支出、交易现金、车贷房贷现金还款、理财买卖资金等可以真实动用的现金。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=INVESTMENT_ACCOUNT_CONCEPT,
        name="投资账户",
        category="investment",
        description="由后端根据定投策略、买入手续费、卖出手续费和月度收益复利推演，不直接等同于现金，交易月需要先变现再进入现金账户。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=LIQUID_ASSET_ACCOUNT_CONCEPT,
        name="流动资产",
        category="account",
        description="现金账户和投资账户的合计，用于观察可较快动用的资产规模；不包含公积金账户、固定资产和贷款。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=PROVIDENT_ACCOUNT_CONCEPT,
        name="公积金账户",
        category="provident",
        description="按政策口径单独管理，个人和单位缴存、账户利息、租房季度提取、购房相关提取、按月抵月供和半年度冲本金都在后端逐月记账；默认不作为自由现金收入。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=SOCIAL_SECURITY_PERSONAL_ACCOUNTS_CONCEPT,
        name="养老与医保个人账户",
        category="social_security",
        description="后端按成员工资阶段和规则包逐月推演养老保险个人账户与医保个人账户。养老账户按个人缴费累积并在退休后按计发月数消耗；医保账户按个人医保缴费、退休后定额划入、医保可支付医疗支出和大额互助扣缴记账。这类账户受政策用途限制，不作为现金账户或流动资产。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=PENSION_ACCOUNT_CONCEPT,
        name="基本养老个人账户",
        category="social_security",
        description="按成员工资阶段、个人养老缴费和政策计息逐月累积，退休后按计发月数形成个人账户养老金支出；账户余额不能作为自由现金提取。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=MEDICAL_ACCOUNT_CONCEPT,
        name="医保个人账户",
        category="social_security",
        description="按成员医保缴费、退休后北京定额划入、医保可支付医疗支出和大额互助扣缴逐月记账；专款专用，不作为现金收入。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=PERSONAL_PENSION_ACCOUNT_CONCEPT,
        name="个人养老金账户",
        category="social_security",
        description="由税务策略或用户手动决定是否开户、何时缴费和缴多少。缴费作为现金转出进入受限养老账户，年度限额内可税前扣除；账户收益单独累积，不计入流动资产。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=FIXED_ASSET_ACCOUNT_CONCEPT,
        name="固定资产",
        category="fixed_asset",
        description="记录房产和车辆等不动产/耐用品估值，用于看家庭资产结构，不作为首付或应急现金来源。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=LOAN_ACCOUNT_CONCEPT,
        name="贷款账户",
        category="loan",
        description="统一管理已有贷款和已纳入规划的目标贷款。实际逐月余额、月供和提前还款影响仍以后端策略推演结果为准，规划贷款对象只用于说明目标可能形成的负债结构。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code=ACCOUNT_CALIBRATION_CONCEPT,
        name="账户校准",
        category="account",
        description="记录用户按真实账单对现金、投资、公积金、养老医保、固定资产或贷款余额做出的月份校准。校准记录用于重置后续推演状态，不作为资产或负债重复计入分组余额。",
        managed_by="user_input",
    ),
    AccountConceptDefinition(
        code="net_worth",
        name="净资产",
        category="account",
        description="总资产扣除贷款余额后的家庭净值。账户余额、固定资产估值和贷款余额本身不会为负，但净资产可能因为负债高于资产而为负。",
        managed_by="backend",
    ),
    AccountConceptDefinition(
        code="policy_pack",
        name="政策规则包",
        category="policy",
        description="税、公积金、购房资格、贷款上限、贷款年限、冲还贷月份等由政策规则包控制；用户只调整真实可选参数和情景假设。",
        managed_by="policy",
    ),
)

ACCOUNT_CORE_OBJECT_CATEGORY_TO_CONCEPT: dict[str, str] = {
    "cash": CASH_ACCOUNT_CONCEPT,
    "investment": INVESTMENT_ACCOUNT_CONCEPT,
    "provident": PROVIDENT_ACCOUNT_CONCEPT,
    "pension": PENSION_ACCOUNT_CONCEPT,
    "medical": MEDICAL_ACCOUNT_CONCEPT,
    "personal_pension": PERSONAL_PENSION_ACCOUNT_CONCEPT,
}
ASSET_CORE_OBJECT_CATEGORIES = frozenset(
    {"property_asset", "vehicle_asset", "child_goal", "planning_goal"}
)
ADJUSTMENT_CORE_OBJECT_CATEGORY_TO_CONCEPT: dict[str, str] = {
    "manual_adjustment": ACCOUNT_CALIBRATION_CONCEPT,
}

CORE_OBJECT_GROUP_DEFINITIONS: tuple[CoreObjectGroupDefinition, ...] = (
    CoreObjectGroupDefinition(
        code="liquid_assets",
        name="流动资产",
        category="liquid_asset",
        concept_codes=(CASH_ACCOUNT_CONCEPT, INVESTMENT_ACCOUNT_CONCEPT),
        description="现金账户和投资账户合计，表示较快能调度的家庭资产；不包含公积金、养老医保、个人养老金、固定资产和贷款。",
    ),
    CoreObjectGroupDefinition(
        code="restricted_accounts",
        name="政策受限账户",
        category="restricted_account",
        concept_codes=(
            PROVIDENT_ACCOUNT_CONCEPT,
            SOCIAL_SECURITY_PERSONAL_ACCOUNTS_CONCEPT,
            PERSONAL_PENSION_ACCOUNT_CONCEPT,
        ),
        description="公积金、基本养老医保个人账户和个人养老金等受政策用途限制的账户，后端单独推演，不作为自由现金。",
    ),
    CoreObjectGroupDefinition(
        code="fixed_assets",
        name="固定资产与目标",
        category="fixed_asset",
        concept_codes=(FIXED_ASSET_ACCOUNT_CONCEPT,),
        description="房产、车辆和养娃等目标资产或目标预算，用于观察长期资产结构，不作为短期现金来源。",
    ),
    CoreObjectGroupDefinition(
        code="loan_accounts",
        name="贷款账户",
        category="loan",
        concept_codes=(LOAN_ACCOUNT_CONCEPT,),
        description="已有贷款和已纳入规划的房贷、公积金贷、车贷等负债口径。规划贷款不等于已经发生的现金流，实际余额曲线由后端策略逐月生成。",
    ),
)

CALIBRATION_TARGET_LABELS: dict[str, str] = {
    "cash": "现金账户",
    "investment": "投资账户",
    "provident": "公积金账户",
    "pension": "基本养老个人账户",
    "medical": "医保个人账户",
    "property_asset": "房产资产",
    "vehicle_asset": "车辆资产",
    "fixed_asset": "固定资产",
    "total_loan": "贷款余额",
}


def account_concept_code_for_core_object(object_type: str, category: str) -> str | None:
    if object_type == "account":
        return ACCOUNT_CORE_OBJECT_CATEGORY_TO_CONCEPT.get(category)
    if object_type == "asset" and category in ASSET_CORE_OBJECT_CATEGORIES:
        return FIXED_ASSET_ACCOUNT_CONCEPT
    if object_type == "loan":
        return LOAN_ACCOUNT_CONCEPT
    if object_type == "adjustment":
        return ADJUSTMENT_CORE_OBJECT_CATEGORY_TO_CONCEPT.get(category)
    return None


def calibration_target_label(target: str) -> str:
    return CALIBRATION_TARGET_LABELS.get(target, "账户")
