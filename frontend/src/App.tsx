import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  Banknote,
  CalendarClock,
  Car,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  Database,
  Download,
  Gauge,
  Home,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  Trash2,
  TrendingUp,
  WalletCards
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  calculateAffordability,
  createScenario,
  fetchSourcePreview,
  loadInitialData,
  saveHousehold,
  saveRulePack,
  saveScenario
} from "./api";
import { money, numberInput, percent } from "./format";
import type {
  AffordabilityResult,
  BonusTaxMethod,
  CarPlanAnalysis,
  CarPlanData,
  ElderlyDependentData,
  HouseholdData,
  IncomeMember,
  IncomeStageData,
  PurchasePlanAnalysis,
  RecordEnvelope,
  RepaymentMethod,
  RenovationFundingMode,
  RulePackData,
  ScenarioData,
  ScheduledExpenseData,
  SourceDocumentRecord,
  PhasedLoanData
} from "./types";

const visualColors = {
  cash: "#2563eb",
  investment: "#16a34a",
  provident: "#0891b2",
  debt: "#dc6b35",
  expense: "#c65d5d",
  deduction: "#b98b2f",
  property: "#8b5cf6",
  vehicle: "#d97706",
  fixedAsset: "#0f766e",
  totalAsset: "#111827",
  baseline: "#7c3aed",
  safe: "#28724f",
  warning: "#d09632",
  danger: "#b23b3b"
};

const piePalette = [
  visualColors.cash,
  visualColors.investment,
  visualColors.warning,
  visualColors.expense,
  visualColors.property,
  visualColors.provident,
  "#8a6b42",
  "#4d7c0f",
  "#64748b",
  "#be185d"
];

const sourceDefaults = [
  "https://gjj.beijing.gov.cn/web/zwgk61/2024zcwj/436433464/436433465/743726695/index.html",
  "https://gjj.beijing.gov.cn/web/zwgk61/2024zcjd/743726745/index.html",
  "https://gjj.beijing.gov.cn/web/zwgk61/2024zcwj/436433464/436433467/743889727/index.html",
  "https://zjw.beijing.gov.cn/bjjs/fwgl/fdcjy/index.shtml"
];

const defaultCarPlan: CarPlanData = {
  enabled: false,
  name: "车辆计划",
  selected_strategy_variant: "手动设置",
  total_price: 0,
  down_payment_ratio: 0.5,
  down_payment: 0,
  purchase_delay_months: 0,
  total_months: 60,
  interest_free_months: 24,
  later_annual_rate: 0.0199,
  current_month_index: 1,
  saving_start_date: "2026-07-01",
  monthly_operating_cost: 0,
  no_car_monthly_commute_cost: 0,
  annual_mileage_km: 0,
  electricity_kwh_per_100km: 14,
  electricity_price_per_kwh: 0.8,
  monthly_parking_cost: 0,
  annual_maintenance_cost: 0,
  annual_maintenance_growth_rate: 0.03,
  annual_insurance_rate: 0.018,
  annual_insurance_min: 0,
  annual_insurance_growth_rate: 0.02,
  depreciation_years: 8,
  vehicle_service_years: 15,
  vehicle_retirement_mileage_km: 600000,
  second_car_enabled: false,
  second_car_total_price: 0,
  second_car_down_payment_ratio: 0.4,
  second_car_purchase_delay_months: 60,
  second_car_total_months: 60,
  second_car_interest_free_months: 24,
  second_car_later_annual_rate: 0.0199,
  second_car_annual_mileage_km: 0,
  second_car_monthly_parking_cost: 0,
  happiness_score: 6.5,
  notes: ""
};

const defaultCareerShock = {
  enabled: false,
  layoff_member_name: "成员 1",
  layoff_age: 35,
  self_birth_month: "",
  spouse_birth_month: "",
  self_current_age: 30,
  spouse_current_age: 30,
  auto_unemployment_benefit: true,
  auto_self_social_insurance: true,
  unemployment_benefit_months: 24,
  unemployment_benefit_monthly: 0,
  self_social_insurance_monthly: 0,
  self_retirement_age: 63,
  spouse_retirement_age: 58,
  self_pension_monthly: 0,
  spouse_pension_monthly: 0
};

const defaultScheduledExpenses: ScheduledExpenseData[] = [
  {
    name: "定时支出",
    monthly_amount: 0,
    start_month: "2026-07",
    end_month: null,
    tax_deductible_elderly_care: false,
    notes: ""
  }
];

function completeHouseholdDefaults(record: RecordEnvelope<HouseholdData>): RecordEnvelope<HouseholdData> {
  return {
    ...record,
    data: {
      ...record.data,
      members: record.data.members,
      career_shock: {
        ...defaultCareerShock,
        ...(record.data.career_shock ?? {})
      },
      car_plan: {
        ...defaultCarPlan,
        ...record.data.car_plan,
        no_car_monthly_commute_cost: record.data.car_plan.no_car_monthly_commute_cost ?? 0
      },
      phased_loans: record.data.phased_loans ?? [],
      scheduled_expenses: record.data.scheduled_expenses ?? [],
      elderly_dependents: record.data.elderly_dependents ?? [],
      borrower_member_index: record.data.borrower_member_index ?? 0,
      family_provident_support_enabled: record.data.family_provident_support_enabled ?? false,
      family_provident_support_label: record.data.family_provident_support_label ?? "亲属异地公积金首付支持",
      family_down_payment_support_mode: record.data.family_down_payment_support_mode ?? "provident",
      family_savings_support_amount: record.data.family_savings_support_amount ?? 0,
      family_provident_initial_balance: record.data.family_provident_initial_balance ?? 0,
      family_provident_monthly_salary: record.data.family_provident_monthly_salary ?? 0,
      family_provident_total_rate: record.data.family_provident_total_rate ?? 0.24,
      investment_buy_fee_rate: record.data.investment_buy_fee_rate ?? 0.0015,
      investment_sell_fee_rate: record.data.investment_sell_fee_rate ?? 0.005
    }
  };
}

const pages = ["家庭财务", "理财计划", "购房计划", "买车计划", "政策规则", "可视化", "导出方案"] as const;
type PageName = (typeof pages)[number];
type SaveState = "idle" | "dirty" | "saving" | "saved";
type StrategyRecommendation = {
  plan: PurchasePlanAnalysis;
  score: number;
  reasons: string[];
};

type InvestmentPlanRecommendation = {
  variant: string;
  planName: string;
  riskLevel: string;
  riskLabel: string;
  description: string;
  monthlyInvestment: number;
  annualReturn: number;
  cashReserveMonths: number;
  equityRatio: number;
  bondRatio: number;
  cashRatio: number;
  score: number;
  reasons: string[];
};

type ScenarioComparison = {
  scenario: RecordEnvelope<ScenarioData>;
  result: AffordabilityResult;
  recommendation: StrategyRecommendation | null;
  selectedPlan: PurchasePlanAnalysis | null;
};

const parameterExplanations: Record<string, string> = {
  家庭名称: "仅用于区分方案，不参与计算。建议写成便于识别的版本，例如“当前家庭基准版”。",
  租房提取公积金等效月额: "购房前按租房提取公积金的等效月额度；输入月均口径，现金流和可视化里按季度到账处理，不是工资公积金缴存额。",
  亲属首付支持: "可选情景：亲属用积蓄或符合条件的异地公积金帮助首付。积蓄支持按可支持金额计入；公积金支持按新房场景和账户余额增长估算，启用前应按实际政策核验。",
  支持资金来源: "选择亲属支持来自普通积蓄还是公积金账户。普通积蓄不受新房/二手房性质限制；公积金支持会按当前规则更保守地只在符合条件的新房里计入。",
  可支持首付金额: "亲属愿意且能够在购房交易时拿出的积蓄金额，用来减少家庭自己需要覆盖的交易现金。",
  支持账户当前余额: "亲属公积金账户今天的余额。系统会按当前余额加上未来每月入账额，估算购房当月可用于首付的上限。",
  支持账户月工资: "用于估算亲属公积金每月入账额的工资基数。",
  支持账户双边比例: "亲属个人和单位合计公积金缴存比例。默认 24% 表示个人 12% + 单位 12%。",
  购后安全垫月数: "买房或买车后希望保留的生活费月数。数值越高，系统越倾向延后买入或提高现金留存。",
  理财计划: "选择当前理财策略。手动指定会使用你填写的定投、费率和资产比例；自动方案会推荐更合适的配置。",
  当前投资资产: "今天已经在基金、股票、债券、理财等账户里的资产。后续会按年化收益、定投和手续费滚动。",
  测算年化: "对投资资产使用的预期年化收益率，不是保证收益。风险越高，建议同时保留更厚现金垫。",
  预估年收益: "按当前投资资产和测算年化粗略估算的一年收益，用于直觉参考。",
  折合月收益: "把预估年收益平均到每个月，仅用于展示；真实收益会波动。",
  当前可动用现金: "今天可随时用于首付、应急和日常支出的现金，不包含已投入理财的资产。",
  基础月支出: "从现在起每月固定发生的生活支出，不含家庭支持支出、房贷、车贷和目前贷款等单独项目。",
  当前实际月支出: "基础月支出加上当前已经生效的定时支出，用于判断现金安全垫。",
  "其他固定债务/月": "除下方单独建模的目前贷款外的每月既有债务；目前贷款会自动加进测算。",
  支出名称: "定时支出的名称，会直接显示在月现金流里，例如家庭支持支出。",
  定时月支出: "从开始月份起每月发生的额外家庭支出。用于现金流，不一定能抵扣个税。",
  开始月份: "该项支出从哪个月份开始计入现金流。",
  结束月份: "可选；填了以后，结束月份之后不再计入现金流。",
  归属成员: "老人专项扣除归属于哪位收入成员。按政策通常只能扣自己的父母，不能夫妻互转。",
  称谓: "用于界面识别老人来源，例如成员一方直系亲属老人。",
  出生月份: "用于判断老人满 60 周岁的月份；系统从满 60 周岁当月开始计算赡养老人专项附加扣除。",
  本人分摊扣除: "非独生子女时本人每月可申报的分摊额，个人上限通常为 1500 元/月。",
  成员名称: "收入成员名称。老人专项扣除、工资阶段和可视化明细会按这个名称关联。",
  阶段名称: "工资阶段的名称，例如当前收入、换工作后。用于识别不同收入时期。",
  开始日期: "该工资阶段从哪天开始生效；税费和公积金会按月份匹配阶段。",
  结束日期: "该工资阶段结束日期；留空表示一直持续。",
  月工资税前: "每月税前工资，是社保、公积金、个税预扣和现金流收入的基础。",
  年终奖年额: "预计全年年终奖金额。现金流按该收入阶段设置的发放月份一次性入账，不均摊到每个月；系统会按单独计税或并入综合所得择优测算。",
  发放月份: "该收入阶段年终奖实际入账月份。不同成员、不同工作阶段可以不同；税率和单独计税有效期仍由政策规则控制。",
  "非税收入/月": "每月进入现金流但不并入工资薪金计税的收入，例如失业金、基础养老金等估算项。",
  "额外现金支出/月": "该收入阶段每月额外发生的现金支出，例如灵活就业自缴社保。",
  工资社保扣缴: "开启时按工资薪金自动估算北京社保、公积金和个税；失业金、养老金等阶段应关闭。",
  个人公积金比例: "个人缴纳住房公积金比例，会减少税后现金但增加公积金账户余额。",
  单位公积金比例: "单位缴纳住房公积金比例，会进入公积金账户，但不是当月现金工资。",
  "专项附加/月": "除赡养老人外的每月专项附加扣除，例如子女教育、住房租金等。",
  其他年收入: "工资薪金以外但需要并入综合所得测算的年度收入。",
  年终奖计税: "选择年终奖按单独计税、并入工资或由系统自动择优。",
  被裁员成员: "选择职业冲击压力情景作用到哪个收入成员。关闭该情景时不会生成失业金或自缴社保阶段。",
  第一成员出生年月: "优先用于把裁员年龄和退休年龄换算成真实月份；留空时使用当前年龄兜底。",
  第二成员出生年月: "优先用于把第二位成员的退休年龄换算成真实月份；留空时使用当前年龄兜底。",
  第一成员当前年龄: "仅在出生年月缺失或格式错误时兜底使用。",
  第二成员当前年龄: "仅在出生年月缺失或格式错误时兜底使用。",
  裁员年龄: "压力情景触发年龄。达到该年龄当月起，系统自动切换到失业金和自缴社保收入阶段。",
  自动估算失业保险待遇: "开启后按家庭画像里的累计社保/个税月数估算待遇期限，并按规则包里的北京失业保险金标准分档生成现金流；关闭后使用手动月数和月额。",
  自动估算灵活就业自缴: "开启后按规则包里的灵活就业缴费基数、养老比例、失业比例和医保月额合计生成裁员后的自缴社保支出。",
  估算失业金月数: "根据累计社保/个税月数估算：不足 12 个月为 0，1-5 年为 12 个月，5-10 年为 18 个月，10 年以上为 24 个月。",
  估算失业金月额: "按规则包里的北京失业保险金分档金额展示；如果超过 12 个月，斜杠后是第 13 个月起的后续期金额。",
  "估算自缴社保/月": "按规则包自动估算的灵活就业养老、失业和医保合计月支出。",
  失业金月数: "手动覆盖失业保险待遇期限；自动估算关闭时才参与计算，最长按 24 个月建模。",
  失业金月额: "手动覆盖失业保险金月额；自动估算关闭时才参与计算，作为非税现金收入进入家庭现金流。",
  "自缴社保/月": "手动覆盖裁员后以灵活就业身份自行缴纳养老、医保等的月现金支出；自动估算关闭时才参与计算。",
  第一成员退休年龄: "第一位成员退休年龄假设，用于养老金阶段测算。请按自己的职业和政策口径填写。",
  第二成员退休年龄: "第二位成员退休年龄假设，用于养老金阶段测算。请按自己的职业和政策口径填写。",
  "第一成员养老金/月": "第一位成员退休后每月养老金估算，按非税现金收入进入收入阶段。实际养老金取决于缴费年限、基数和个人账户。",
  "第二成员养老金/月": "第二位成员退休后每月养老金估算，按非税现金收入进入收入阶段。",
  借款人: "贷款归属人，只用于展示和汇总，不改变还款计算公式。",
  贷款名称: "用于区分多笔贷款，例如低息贷款 A、教育贷款 A 或亲友借款 A。",
  本金: "当前仍需偿还或进入测算的贷款本金。",
  年利率: "贷款年化利率。等额本息/本金会按该利率计算还款。",
  还款方式: "等额本息月供较稳定，等额本金前期压力更高但总利息更少。",
  剩余期数: "从当前开始还剩多少个月需要还款。",
  计息开始月: "从哪个月份开始产生利息。",
  只还利息至: "政策宽限期结束月份；此前只还利息，之后进入本金偿还。",
  每月定投: "计划每月投入理财的现金上限。现金安全垫不足时系统会自动减少或暂停。",
  现金安全垫月数: "理财策略要求保留的现金月数。月数越高，越保守。",
  权益比例: "投资组合中股票、偏股基金等权益资产占比。收益弹性更高，波动也更大。",
  固收比例: "债券、固收类基金等相对稳健资产占比。",
  现金比例: "投资组合中货币基金、活期、短债等低波动现金类资产占比。",
  买入手续费率: "每月定投买入时扣除的费用比例。定投现金支出不变，但进入投资资产的净额会减少。",
  卖出手续费率: "买房交易月卖出投资资产时扣除的费用比例。会减少可用于首付的现金。",
  规则包: "当前使用的政策和参数集合。修改规则会影响税费、公积金、贷款和可买时间。",
  当前采用: "当前正在用于计算和可视化的策略。",
  目标总价: "目标房源总价。直接决定首付、税费、贷款规模和可买时间。",
  建筑面积: "用于对比房源性价比和居住体验评分，不直接改变贷款本金。",
  手动首付: "手动指定的首付金额。自动策略会在政策最低首付和现金约束之间校正。",
  手动商贷: "手动指定商业贷款金额。用于模拟特定贷款结构。",
  手动公积金贷: "手动指定公积金贷款金额，仍会受到北京公积金政策上限约束。",
  微量商贷手动比例: "微量商贷策略下可手动指定商贷占房价比例；留空或为 0 时由系统自动选择。",
  商贷利率: "商业贷款年利率，用于计算月供和总利息。",
  公积金利率: "公积金贷款年利率，用于计算公积金月供和总利息。",
  贷款年限: "贷款总年限。公积金贷款还会额外受年龄、房龄、土地年限等政策约束。",
  商贷还款: "商业贷款还款方式。等额本息稳定，等额本金前高后低。",
  公积金还款: "公积金贷款还款方式。会影响首月月供、平均月供和现金流压力。",
  契税比例: "交易契税占房价比例，计入买房交易现金需求。",
  中介费比例: "中介服务费占房价比例，计入交易现金需求。",
  装修预算: "预计装修需要的总资金。可选择交易前准备或买房后慢慢攒。",
  装修资金: "决定装修预算是计入交易现金，还是买房后用月结余逐步积累。",
  搬家杂费: "搬家、家电、维修、临时周转等一次性杂费，计入交易现金需求。",
  居住幸福度: "房源本身带来的居住体验评分，会进入幸福指数。",
  通勤评分: "通勤便利程度评分，会进入幸福指数。",
  教育评分: "教育资源匹配程度评分，会进入幸福指数。",
  流动性偏好: "越重视流动性，系统越倾向保留更多现金、降低买后压力。",
  房屋性质: "新房、二手房等性质会影响公积金提取、贷款年限和部分政策适用。",
  绿色建筑: "符合绿色建筑条件的新房可能提高公积金贷款上限。",
  装配式等级: "装配式建筑等级可能提高公积金贷款上限。",
  二手房房龄: "二手房房龄会影响公积金贷款年限。",
  建筑结构: "二手房结构影响房屋耐用年限口径，从而影响公积金贷款年限。",
  剩余土地年限: "老旧小区改造等情形下用于约束公积金贷款年限。",
  车辆总价: "目标车辆落地前的购车总价，用于生成首付和贷款方案。",
  首付比例: "买车首付占车价比例。比例越高，贷款越少但短期现金压力越大。",
  首付金额: "买车首付现金金额。可由首付比例自动估算，也可手动微调。",
  延后买车月数: "从现在起延后多少个月买车，用于保留现金或等待收入提升。",
  总期数: "车贷总还款月数。",
  "0息期数": "车贷前多少期为 0 息。主流电车金融常见前段免息、后段低息。",
  后段年利率: "0 息期结束后的年化利率。",
  当前期数: "当前已经处在车贷第几期，用于计算当前月供。",
  攒车首付开始: "从哪个月份开始为买车首付积累现金。",
  年行驶里程: "估算电费、保养和折旧时使用的年行驶里程。",
  百公里电耗: "车辆每 100 公里耗电量，用于估算每月电费。",
  充电单价: "每度电价格，用于估算电费。",
  月停车费: "每月固定停车成本。",
  无车通勤月成本: "不买车或延后买车期间的打车、公交、地铁、共享出行等月均成本，会计入日常现金流。",
  年保养杂费: "保险外的保养、洗车、小维修等年度成本。",
  保养年增长: "车辆使用年限增加后，保养、小维修和耗材成本可能逐年上升。系统只在年度保养付款月计入增长后的现金支出。",
  保险费率: "按车价估算年度保险费用的比例。",
  年保险下限: "保险估算的最低年度金额，防止新车保险被低估。",
  保险年增长: "用于估算后续年份车险价格变化。系统只在年度保险付款月计入增长后的现金支出。",
  折旧年限: "用于估算车辆折旧成本，不代表真实卖车价格。",
  车辆使用年限: "用于提示家庭何时考虑更新车辆。私家小微非营运车通常不是固定年限强制报废。",
  "报废/更新里程": "按小微非营运载客汽车 60 万公里引导报废口径作为提示阈值，可按实际用车强度调整。",
  第二辆车: "启用后会在指定月份之后把第二辆车首付、车贷和养车成本叠加到购房现金流和可视化。",
  第二辆车总价: "第二辆车预算总价。",
  第二车首付比例: "第二辆车贷款方案的首付比例。",
  第二车延后月数: "从现在起第几个月购买第二辆车。",
  第二车总期数: "第二辆车贷款总期数。",
  第二车0息期数: "第二辆车贷款中 0 息分期的期数。",
  第二车后段利率: "第二辆车 0 息期结束后的年化贷款利率。",
  第二车年里程: "第二辆车预计年行驶里程，用于估算电费和报废里程时间。",
  第二车月停车费: "第二辆车每月新增停车费。",
  买车幸福度: "车辆对家庭便利、舒适、时间节省的主观评分。",
  "社保/个税月数": "在京社保或个税累计月数，用于购房资格和公积金缴存年限相关测算。",
  借款申请人: "选择用于公积金贷款年限测算的家庭成员。借款申请人年龄会自动取该成员的出生年月或当前年龄。",
  借款申请人年龄: "自动取所选借款申请人的年龄，用于判断公积金可贷年限；年龄越大可贷年限可能越短。",
  子女数: "用于家庭状态、幸福指数和部分政策判断，不能为负。",
  现有住房套数: "影响购房资格、首付比例和贷款政策。",
  现有房贷笔数: "影响贷款认定和风险判断。",
  公积金余额: "当前家庭公积金账户余额，用于估算提取、贷款和账户变化。",
  失业金1至5年: "累计缴费满 1 年不满 5 年时使用的北京失业保险金月标准。",
  失业金5至10年: "累计缴费满 5 年不满 10 年时使用的北京失业保险金月标准。",
  失业金10至15年: "累计缴费满 10 年不满 15 年时使用的北京失业保险金月标准。",
  失业金15至20年: "累计缴费满 15 年不满 20 年时使用的北京失业保险金月标准。",
  失业金20年以上: "累计缴费满 20 年以上时使用的北京失业保险金月标准。",
  失业金13月后: "失业保险待遇领取第 13 个月起使用的后续期月标准。",
  灵活就业基数: "自动估算自缴社保时使用的灵活就业缴费基数，系统会限制在社保基数上下限之间。",
  灵活养老比例: "灵活就业人员基本养老保险缴费比例。",
  灵活失业比例: "灵活就业人员失业保险缴费比例。",
  灵活医保月额: "灵活就业人员基本医疗保险月缴费额，按北京当期固定标准维护。",
  首套商贷首付: "首套房商业贷款最低首付比例。",
  首套公积金首付: "首套房使用公积金贷款时的最低首付比例。",
  首套公积金额度: "首套房公积金贷款基础额度上限，不含绿色建筑等上浮。",
  每缴存年可贷额度: "北京公积金按缴存年限累积的可贷额度口径。",
  微量商贷自动下限: "系统自动生成微量商贷策略时尝试的最低商贷比例。",
  微量商贷默认比例: "微量商贷策略的默认比例，用于平衡买房速度和负债压力。",
  微量商贷自动上限: "系统自动生成微量商贷策略时允许尝试的最高商贷比例。",
  "谨慎 DTI": "负债收入比较舒适的阈值，低于该值通常现金流压力较小。",
  "高风险 DTI": "负债收入比较高的阈值，超过该值会显著压低幸福指数和可行性。"
};

type MonthlyInvestmentAllocation = {
  baseInvestment: number;
  cashSweepInvestment: number;
  totalInvestment: number;
};

const repaymentMethodLabels: Record<RepaymentMethod, string> = {
  equal_installment: "等额本息",
  equal_principal: "等额本金"
};

const existingLoanTypeLabels: Record<NonNullable<PhasedLoanData["loan_type"]>, string> = {
  mortgage: "房贷",
  car: "车贷",
  education: "教育贷款",
  consumer: "消费贷款",
  other: "其他贷款"
};

const renovationFundingLabels: Record<RenovationFundingMode, string> = {
  after_purchase_saving: "买后攒钱装修",
  upfront_cash: "交易前准备装修款"
};

function familySupportAmount(plan: PurchasePlanAnalysis) {
  return plan.family_down_payment_support_amount ?? plan.family_provident_upfront_extractable ?? 0;
}

function familySupportLabel(plan: PurchasePlanAnalysis) {
  if (familySupportAmount(plan) <= 0) return "";
  return plan.family_down_payment_support_label || (
    plan.family_down_payment_support_mode === "savings" ? "亲属积蓄首付支持" : "亲属公积金首付支持"
  );
}

function familySupportPhrase(plan: PurchasePlanAnalysis) {
  const amount = familySupportAmount(plan);
  const label = familySupportLabel(plan);
  return amount > 0 && label ? `，${label} ${money(amount)}` : "";
}

function providentStrategyLabel(plan: PurchasePlanAnalysis) {
  return plan.post_purchase_pf_strategy_label || "默认留存在公积金账户";
}

const greenBuildingLabels = {
  none: "不适用",
  two_star: "二星绿色建筑",
  three_star: "三星绿色建筑"
} as const;

const prefabBuildingLabels = {
  none: "不适用",
  A: "装配式 A",
  AA: "装配式 AA",
  AAA: "装配式 AAA"
} as const;

function addMonths(baseDate: Date, months: number) {
  return new Date(baseDate.getFullYear(), baseDate.getMonth() + months, 1);
}

function formatMonthDate(baseDate: Date, monthsFromNow: number) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  return `${targetDate.getFullYear()}年${targetDate.getMonth() + 1}月`;
}

function formatMonthInputValue(baseDate: Date, monthsFromNow: number) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  return `${targetDate.getFullYear()}-${String(targetDate.getMonth() + 1).padStart(2, "0")}`;
}

function formatTodayDate(baseDate: Date) {
  return `${baseDate.getFullYear()}年${baseDate.getMonth() + 1}月${baseDate.getDate()}日`;
}

function parseMonthValue(value: string | null | undefined) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{1,2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
  return { year, month };
}

function compareMonth(left: { year: number; month: number }, right: { year: number; month: number }) {
  return (left.year - right.year) * 12 + left.month - right.month;
}

function formatAgeFromBirthMonth(value: string | null | undefined, today = new Date()) {
  const birthMonth = parseMonthValue(value);
  if (!birthMonth) return "待填写";
  const ageInMonths = compareMonth(
    { year: today.getFullYear(), month: today.getMonth() + 1 },
    birthMonth
  );
  if (ageInMonths < 0) return "待填写";
  const years = Math.floor(ageInMonths / 12);
  const months = ageInMonths % 12;
  return months > 0 ? `${years}岁${months}个月` : `${years}岁`;
}

function ageYearsFromBirthMonth(value: string | null | undefined, today = new Date()) {
  const birthMonth = parseMonthValue(value);
  if (!birthMonth) return null;
  const ageInMonths = compareMonth(
    { year: today.getFullYear(), month: today.getMonth() + 1 },
    birthMonth
  );
  return ageInMonths >= 0 ? Math.floor(ageInMonths / 12) : null;
}

function birthMonthFromAge(age: number, today = new Date()) {
  const safeAge = Math.max(0, Math.floor(age));
  const birthYear = today.getFullYear() - safeAge;
  return `${birthYear}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function householdExpenseAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  return Math.max(
    0,
    household.monthly_expense +
      scheduledExpenseRowsAt(household, baseDate, monthsFromNow).reduce((sum, item) => sum + item.amount, 0)
  );
}

function scheduledExpenseRowsAt(household: HouseholdData, baseDate: Date, monthsFromNow = 0) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  return (household.scheduled_expenses ?? []).flatMap((item) => {
    const start = parseMonthValue(item.start_month);
    const end = parseMonthValue(item.end_month);
    if (!start || compareMonth(targetMonth, start) < 0) return [];
    if (end && compareMonth(targetMonth, end) > 0) return [];
    const amount = Math.max(0, item.monthly_amount);
    return amount > 0 ? [{ name: item.name || "定时支出", amount }] : [];
  });
}

function elderlyDeductionStartMonth(dependent: ElderlyDependentData) {
  const birthMonth = parseMonthValue(dependent.birth_month);
  if (!birthMonth) return null;
  return { year: birthMonth.year + 60, month: birthMonth.month };
}

function elderlyCareDeductionForMemberAt(household: HouseholdData, memberName: string, targetDate: Date) {
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const total = (household.elderly_dependents ?? []).reduce((sum, dependent) => {
    if (dependent.member_name !== memberName) return sum;
    const startMonth = elderlyDeductionStartMonth(dependent);
    if (!startMonth || compareMonth(targetMonth, startMonth) < 0) return sum;
    return sum + (dependent.is_only_child ? 3000 : Math.min(Math.max(0, dependent.shared_monthly_deduction ?? 1500), 1500));
  }, 0);
  return Math.min(total, 3000);
}

function elderlyDeductionPolicyStatus(
  elderlyDependents: ElderlyDependentData[],
  targetDate = new Date()
) {
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const items = elderlyDependents
    .map((dependent) => {
      const startMonth = elderlyDeductionStartMonth(dependent);
      const monthlyDeduction = dependent.is_only_child
        ? 3000
        : Math.min(Math.max(0, dependent.shared_monthly_deduction ?? 1500), 1500);
      return { dependent, startMonth, monthlyDeduction };
    })
    .filter((item) => item.startMonth && item.monthlyDeduction > 0);
  const activeItems = items.filter((item) => item.startMonth && compareMonth(targetMonth, item.startMonth) >= 0);
  const nextItem = items
    .filter((item) => item.startMonth && compareMonth(targetMonth, item.startMonth) < 0)
    .sort((left, right) => compareMonth(left.startMonth!, right.startMonth!))[0];

  if (activeItems.length > 0) {
    const total = Math.min(3000, activeItems.reduce((sum, item) => sum + item.monthlyDeduction, 0));
    return {
      active: true,
      tone: "good" as const,
      label: `当前可按老人专项扣除测算，月扣除约 ${money(total)}`,
      detail: activeItems
        .map((item) => `${item.dependent.relationship_label || "直系亲属老人"}已满60岁`)
        .join("；")
    };
  }
  if (nextItem?.startMonth) {
    return {
      active: false,
      tone: "warn" as const,
      label: `暂未生效，预计 ${nextItem.startMonth.year}年${nextItem.startMonth.month}月 起满足老人专项扣除年龄条件`,
      detail: "系统会按老人出生月份自动判断，不需要在家庭支持支出里手动勾选。"
    };
  }
  return {
    active: false,
    tone: "warn" as const,
    label: "待填写老人出生月份后自动判断是否满足专项扣除",
    detail: "家庭支持支出只影响现金流；税收扣除请在“父母老人专项扣除”里维护老人信息。"
  };
}

function incomeStageFromMember(member: IncomeMember): IncomeStageData {
  return {
    name: "当前收入",
    start_date: member.employment_start_date || "2026-07-01",
    end_date: null,
    monthly_salary_gross: member.monthly_salary_gross,
    annual_bonus: member.annual_bonus,
    annual_bonus_payout_month: 4,
    monthly_non_taxable_income: 0,
    monthly_extra_cash_expense: 0,
    monthly_social_insurance: member.monthly_social_insurance,
    monthly_housing_fund: member.monthly_housing_fund,
    housing_fund_personal_rate: member.housing_fund_personal_rate,
    housing_fund_employer_rate: member.housing_fund_employer_rate,
    monthly_special_additional_deduction: member.monthly_special_additional_deduction,
    other_annual_deductions: member.other_annual_deductions,
    other_annual_taxable_income: member.other_annual_taxable_income,
    bonus_tax_method: member.bonus_tax_method,
    payroll_contributions_enabled: true
  };
}

function incomeStagesForMember(member: IncomeMember) {
  const stages = member.income_stages?.length ? member.income_stages : [incomeStageFromMember(member)];
  return stages.map((stage) => ({
    ...stage,
    annual_bonus_payout_month: stage.annual_bonus_payout_month ?? 4,
    monthly_non_taxable_income: stage.monthly_non_taxable_income ?? 0,
    monthly_extra_cash_expense: stage.monthly_extra_cash_expense ?? 0,
    payroll_contributions_enabled: stage.payroll_contributions_enabled ?? true
  }));
}

function monthStartForAge(baseDate: Date, currentAge: number, targetAge: number) {
  return addMonths(new Date(baseDate.getFullYear(), baseDate.getMonth(), 1), Math.max(0, targetAge - currentAge) * 12);
}

function monthStartForBirthMonthOrAge(baseDate: Date, birthMonth: string | undefined, currentAge: number, targetAge: number) {
  const parsed = parseMonthValue(birthMonth);
  if (parsed) {
    const target = new Date(parsed.year + targetAge, parsed.month - 1, 1);
    const currentMonth = new Date(baseDate.getFullYear(), baseDate.getMonth(), 1);
    return target < currentMonth ? currentMonth : target;
  }
  return monthStartForAge(baseDate, currentAge, targetAge);
}

function unemploymentBenefitMonthsFromService(serviceMonths: number) {
  if (serviceMonths < 12) return 0;
  if (serviceMonths < 60) return 12;
  if (serviceMonths < 120) return 18;
  return 24;
}

function unemploymentBenefitMonthlyFromService(serviceMonths: number, rulePack: RulePackData) {
  const params = rulePack.params ?? {};
  if (serviceMonths >= 240) return Number(params.beijing_unemployment_benefit_20y_plus ?? 2286);
  if (serviceMonths >= 180) return Number(params.beijing_unemployment_benefit_15_to_20y ?? 2215);
  if (serviceMonths >= 120) return Number(params.beijing_unemployment_benefit_10_to_15y ?? 2188);
  if (serviceMonths >= 60) return Number(params.beijing_unemployment_benefit_5_to_10y ?? 2156);
  if (serviceMonths >= 12) return Number(params.beijing_unemployment_benefit_under_5y ?? 2129);
  return 0;
}

function autoSelfSocialInsuranceMonthly(rulePack: RulePackData) {
  const params = rulePack.params ?? {};
  const floor = Number(params.beijing_social_base_floor ?? 7162);
  const ceiling = Number(params.beijing_social_base_ceiling ?? 35811);
  const rawBase = Number(params.flexible_employment_social_base ?? floor);
  const base = Math.max(floor, Math.min(rawBase, ceiling));
  const pension = base * Number(params.flexible_employment_pension_rate ?? 0.2);
  const unemployment = base * Number(params.flexible_employment_unemployment_rate ?? 0.01);
  const medical = Number(params.flexible_employment_medical_monthly ?? 584.92);
  return Math.max(0, pension + unemployment + medical);
}

function monthsBetween(baseDate: Date, targetDate: Date) {
  return Math.max(
    0,
    (targetDate.getFullYear() - baseDate.getFullYear()) * 12 + targetDate.getMonth() - baseDate.getMonth()
  );
}

function formatDateInputValue(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function endOfPreviousMonth(monthStart: Date) {
  return new Date(monthStart.getFullYear(), monthStart.getMonth(), 0);
}

function zeroCashStage(template: IncomeStageData, name: string, start: Date, end: Date | null = null): IncomeStageData {
  return {
    ...template,
    name,
    start_date: formatDateInputValue(start),
    end_date: end ? formatDateInputValue(end) : null,
    monthly_salary_gross: 0,
    annual_bonus: 0,
    annual_bonus_payout_month: template.annual_bonus_payout_month ?? 4,
    monthly_non_taxable_income: 0,
    monthly_extra_cash_expense: 0,
    monthly_social_insurance: 0,
    monthly_housing_fund: 0,
    housing_fund_personal_rate: 0,
    housing_fund_employer_rate: 0,
    monthly_special_additional_deduction: 0,
    other_annual_deductions: 0,
    other_annual_taxable_income: 0,
    payroll_contributions_enabled: false
  };
}

function effectiveIncomeMembers(household: HouseholdData, rulePack: RulePackData, baseDate = new Date()): IncomeMember[] {
  const shock = household.career_shock ?? defaultCareerShock;
  if (!shock.enabled) return household.members;
  const syntheticPrefix = "自动情景：";
  const unemploymentMonths = shock.auto_unemployment_benefit
    ? unemploymentBenefitMonthsFromService(household.social_security_months ?? 0)
    : Math.max(0, Math.min(shock.unemployment_benefit_months ?? 0, 24));
  const firstUnemploymentMonthly = shock.auto_unemployment_benefit
    ? unemploymentBenefitMonthlyFromService(household.social_security_months ?? 0, rulePack)
    : shock.unemployment_benefit_monthly;
  const laterUnemploymentMonthly = Number(rulePack.params.beijing_unemployment_benefit_after_12_months ?? 2129);
  const selfSocialMonthly = shock.auto_self_social_insurance
    ? autoSelfSocialInsuranceMonthly(rulePack)
    : shock.self_social_insurance_monthly;
  return household.members.map((member, memberIndex) => {
    const originalStages = incomeStagesForMember(member).filter((stage) => !stage.name.startsWith(syntheticPrefix));
    const template = originalStages[originalStages.length - 1] ?? incomeStageFromMember(member);
    const memberCurrentAge = memberIndex === 0 ? shock.self_current_age : shock.spouse_current_age;
    const memberBirthMonth = memberIndex === 0 ? shock.self_birth_month : shock.spouse_birth_month;
    const retirementAge = memberIndex === 0 ? shock.self_retirement_age : shock.spouse_retirement_age;
    const pensionMonthly = memberIndex === 0 ? shock.self_pension_monthly : shock.spouse_pension_monthly;
    const retirementStart = monthStartForBirthMonthOrAge(baseDate, memberBirthMonth, memberCurrentAge, retirementAge);
    const stages = [...originalStages];

    if (member.name === shock.layoff_member_name) {
      const layoffStart = monthStartForBirthMonthOrAge(baseDate, shock.self_birth_month, shock.self_current_age, shock.layoff_age);
      if (unemploymentMonths > 0 && layoffStart < retirementStart) {
        const firstPeriodMonths = Math.min(unemploymentMonths, 12);
        const firstEnd = addMonths(layoffStart, firstPeriodMonths - 1);
        const boundedFirstEnd = firstEnd < retirementStart ? firstEnd : endOfPreviousMonth(retirementStart);
        stages.push({
          ...zeroCashStage(template, `${syntheticPrefix}${shock.layoff_age}岁被裁员-失业金期`, layoffStart, boundedFirstEnd),
          monthly_non_taxable_income: firstUnemploymentMonthly
        });
        if (shock.auto_unemployment_benefit && unemploymentMonths > 12) {
          const laterStart = addMonths(layoffStart, 12);
          const laterEnd = addMonths(layoffStart, unemploymentMonths - 1);
          const boundedLaterEnd = laterEnd < retirementStart ? laterEnd : endOfPreviousMonth(retirementStart);
          if (laterStart < retirementStart) {
            stages.push({
              ...zeroCashStage(template, `${syntheticPrefix}${shock.layoff_age}岁被裁员-失业金后续期`, laterStart, boundedLaterEnd),
              monthly_non_taxable_income: laterUnemploymentMonthly
            });
          }
        }
      }
      const selfSocialStart = addMonths(layoffStart, unemploymentMonths);
      if (selfSocialStart < retirementStart) {
        stages.push({
          ...zeroCashStage(template, `${syntheticPrefix}${shock.layoff_age}岁被裁员-灵活就业自缴社保期`, selfSocialStart, endOfPreviousMonth(retirementStart)),
          monthly_extra_cash_expense: selfSocialMonthly
        });
      }
    }

    if (pensionMonthly > 0) {
      stages.push({
        ...zeroCashStage(template, `${syntheticPrefix}${retirementAge}岁退休-养老金`, retirementStart),
        monthly_non_taxable_income: pensionMonthly
      });
    }

    return { ...member, income_stages: stages };
  });
}

function incomeStageAt(member: IncomeMember, baseDate: Date, monthsFromNow = 0) {
  const targetDate = addMonths(baseDate, monthsFromNow);
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const stages = incomeStagesForMember(member);
  return (
    stages.find((stage) => {
      const start = parseMonthValue(stage.start_date.slice(0, 7));
      const end = parseMonthValue(stage.end_date?.slice(0, 7));
      if (!start || compareMonth(targetMonth, start) < 0) return false;
      if (end && compareMonth(targetMonth, end) > 0) return false;
      return true;
    }) ?? stages[0]
  );
}

type TaxBracket = { threshold: number; rate: number; quick_deduction: number };

const defaultComprehensiveTaxBrackets: TaxBracket[] = [
  { threshold: 36000, rate: 0.03, quick_deduction: 0 },
  { threshold: 144000, rate: 0.1, quick_deduction: 2520 },
  { threshold: 300000, rate: 0.2, quick_deduction: 16920 },
  { threshold: 420000, rate: 0.25, quick_deduction: 31920 },
  { threshold: 660000, rate: 0.3, quick_deduction: 52920 },
  { threshold: 960000, rate: 0.35, quick_deduction: 85920 },
  { threshold: 999999999, rate: 0.45, quick_deduction: 181920 }
];

const defaultBonusTaxBrackets: TaxBracket[] = [
  { threshold: 3000, rate: 0.03, quick_deduction: 0 },
  { threshold: 12000, rate: 0.1, quick_deduction: 210 },
  { threshold: 25000, rate: 0.2, quick_deduction: 1410 },
  { threshold: 35000, rate: 0.25, quick_deduction: 2660 },
  { threshold: 55000, rate: 0.3, quick_deduction: 4410 },
  { threshold: 80000, rate: 0.35, quick_deduction: 7160 },
  { threshold: 999999999, rate: 0.45, quick_deduction: 15160 }
];

function ruleParamNumber(rulePack: RulePackData, key: string, fallback: number) {
  const value = Number(rulePack.params[key]);
  return Number.isFinite(value) ? value : fallback;
}

function ruleBrackets(rulePack: RulePackData, key: string, fallback: TaxBracket[]) {
  const value = rulePack.params[key];
  if (!Array.isArray(value)) return fallback;
  const parsed = value
    .map((item) => {
      const bracket = item as Partial<TaxBracket>;
      return {
        threshold: Number(bracket.threshold),
        rate: Number(bracket.rate),
        quick_deduction: Number(bracket.quick_deduction)
      };
    })
    .filter((item) => Number.isFinite(item.threshold) && Number.isFinite(item.rate) && Number.isFinite(item.quick_deduction));
  return parsed.length ? parsed : fallback;
}

function progressiveTax(taxableIncome: number, brackets: TaxBracket[]) {
  if (taxableIncome <= 0) return 0;
  const bracket = brackets.find((item) => taxableIncome <= item.threshold) ?? brackets[brackets.length - 1];
  return Math.max(0, taxableIncome * bracket.rate - bracket.quick_deduction);
}

function bonusTax(annualBonus: number, brackets: TaxBracket[]) {
  if (annualBonus <= 0) return 0;
  const convertedMonthly = annualBonus / 12;
  const bracket = brackets.find((item) => convertedMonthly <= item.threshold) ?? brackets[brackets.length - 1];
  return Math.max(0, annualBonus * bracket.rate - bracket.quick_deduction);
}

function estimateStageContributionsByRules(stage: IncomeStageData, rulePack: RulePackData) {
  if (stage.payroll_contributions_enabled === false || stage.monthly_salary_gross <= 0) {
    return { personalSocial: 0, personalHousingFund: 0, employerHousingFund: 0 };
  }
  const socialBase = Math.max(
    ruleParamNumber(rulePack, "beijing_social_base_floor", 7162),
    Math.min(stage.monthly_salary_gross, ruleParamNumber(rulePack, "beijing_social_base_ceiling", 35811))
  );
  const fundBase = Math.max(
    ruleParamNumber(rulePack, "beijing_housing_fund_base_floor", 2540),
    Math.min(stage.monthly_salary_gross, ruleParamNumber(rulePack, "beijing_housing_fund_base_ceiling", 35811))
  );
  const fundRateFloor = ruleParamNumber(rulePack, "housing_fund_min_rate", 0.05);
  const fundRateCeiling = ruleParamNumber(rulePack, "housing_fund_max_rate", 0.12);
  const personalFundRate = Math.max(fundRateFloor, Math.min(stage.housing_fund_personal_rate ?? 0.12, fundRateCeiling));
  const employerFundRate = Math.max(fundRateFloor, Math.min(stage.housing_fund_employer_rate ?? 0.12, fundRateCeiling));
  const personalSocial =
    socialBase * ruleParamNumber(rulePack, "employee_pension_rate", 0.08) +
    socialBase * ruleParamNumber(rulePack, "employee_medical_rate", 0.02) +
    ruleParamNumber(rulePack, "employee_medical_fixed", 3) +
    socialBase * ruleParamNumber(rulePack, "employee_unemployment_rate", 0.005);
  const personalHousingFund = fundBase * personalFundRate;
  const employerHousingFund = fundBase * employerFundRate;
  return { personalSocial, personalHousingFund, employerHousingFund };
}

function stageIsActiveInMonth(stage: IncomeStageData, targetDate: Date) {
  const targetMonth = { year: targetDate.getFullYear(), month: targetDate.getMonth() + 1 };
  const start = parseMonthValue(stage.start_date.slice(0, 7));
  const end = parseMonthValue(stage.end_date?.slice(0, 7));
  if (!start || compareMonth(targetMonth, start) < 0) return false;
  if (end && compareMonth(targetMonth, end) > 0) return false;
  return true;
}

function activeMonthsInStageYear(stage: IncomeStageData, year: number) {
  const start = parseMonthValue(stage.start_date.slice(0, 7)) ?? { year, month: 1 };
  const end = parseMonthValue(stage.end_date?.slice(0, 7)) ?? { year, month: 12 };
  const startMonth = Math.max(1, start.year < year ? 1 : start.year > year ? 13 : start.month);
  const endMonth = Math.min(12, end.year > year ? 12 : end.year < year ? 0 : end.month);
  return Math.max(0, endMonth - startMonth + 1);
}

function stageBonusPayoutMonth(stage: IncomeStageData, year: number) {
  if (stage.annual_bonus <= 0 || activeMonthsInStageYear(stage, year) <= 0) return null;
  const payoutMonth = Math.max(1, Math.min(12, stage.annual_bonus_payout_month ?? 4));
  return stageIsActiveInMonth(stage, new Date(year, payoutMonth - 1, 1)) ? payoutMonth : null;
}

function stageBonusPayoutAmount(stage: IncomeStageData, year: number, month: number) {
  if (stageBonusPayoutMonth(stage, year) !== month) return 0;
  return stage.annual_bonus * activeMonthsInStageYear(stage, year) / 12;
}

function selectedStageBonusMethod(stage: IncomeStageData, rulePack: RulePackData): BonusTaxMethod {
  if (stage.bonus_tax_method === "merged" || stage.bonus_tax_method === "separate") return stage.bonus_tax_method;
  const annualBrackets = ruleBrackets(rulePack, "comprehensive_tax_brackets", defaultComprehensiveTaxBrackets);
  const bonusBrackets = ruleBrackets(rulePack, "monthly_converted_bonus_tax_brackets", defaultBonusTaxBrackets);
  const estimated = estimateStageContributionsByRules(stage, rulePack);
  const commonDeductions =
    ruleParamNumber(rulePack, "personal_standard_deduction_annual", 60000) +
    (estimated.personalSocial + estimated.personalHousingFund) * 12 +
    stage.monthly_special_additional_deduction * 12 +
    stage.other_annual_deductions;
  const salaryTaxable = Math.max(0, stage.monthly_salary_gross * 12 + stage.other_annual_taxable_income - commonDeductions);
  const separate = progressiveTax(salaryTaxable, annualBrackets) + bonusTax(stage.annual_bonus, bonusBrackets);
  const merged = progressiveTax(Math.max(0, salaryTaxable + stage.annual_bonus), annualBrackets);
  return merged < separate ? "merged" : "separate";
}

function cumulativeSalaryTax(
  member: IncomeMember,
  rulePack: RulePackData,
  year: number,
  throughMonth: number,
  household: HouseholdData
) {
  if (throughMonth <= 0) return 0;
  const annualBrackets = ruleBrackets(rulePack, "comprehensive_tax_brackets", defaultComprehensiveTaxBrackets);
  const monthlyStandardDeduction = ruleParamNumber(rulePack, "personal_standard_deduction_annual", 60000) / 12;
  let activeMonths = 0;
  let cumulativeIncome = 0;
  let cumulativeSocialAndFund = 0;
  let cumulativeSpecialDeduction = 0;
  let cumulativeOtherDeduction = 0;

  for (let month = 1; month <= throughMonth; month += 1) {
    const targetDate = new Date(year, month - 1, 1);
    const stage = incomeStagesForMember(member).find((item) => stageIsActiveInMonth(item, targetDate));
    if (!stage) continue;
    const estimated = estimateStageContributionsByRules(stage, rulePack);
    activeMonths += 1;
    cumulativeIncome += stage.monthly_salary_gross + stage.other_annual_taxable_income / 12;
    if (selectedStageBonusMethod(stage, rulePack) === "merged") {
      cumulativeIncome += stageBonusPayoutAmount(stage, year, month);
    }
    cumulativeSocialAndFund += estimated.personalSocial + estimated.personalHousingFund;
    cumulativeSpecialDeduction += stage.monthly_special_additional_deduction;
    cumulativeSpecialDeduction += elderlyCareDeductionForMemberAt(household, member.name, targetDate);
    cumulativeOtherDeduction += stage.other_annual_deductions / 12;
  }

  return progressiveTax(
    Math.max(
      0,
      cumulativeIncome -
        monthlyStandardDeduction * activeMonths -
        cumulativeSocialAndFund -
        cumulativeSpecialDeduction -
        cumulativeOtherDeduction
    ),
    annualBrackets
  );
}

function memberMonthlyIncomeRow(
  member: IncomeMember,
  rulePack: RulePackData,
  household: HouseholdData,
  baseDate: Date,
  absoluteMonth: number
) {
  const targetDate = addMonths(baseDate, absoluteMonth);
  const stages = incomeStagesForMember(member);
  const stage =
    stages
      .filter((item) => stageIsActiveInMonth(item, targetDate))
      .sort((left, right) => right.start_date.localeCompare(left.start_date))[0] ?? null;
  if (!stage) {
    return {
      name: member.name,
      stageName: "未生效",
      grossMonthly: 0,
      bonusMonthly: 0,
      otherMonthly: 0,
      nonTaxableMonthly: 0,
      salaryNetMonthly: 0,
      bonusNetMonthly: 0,
      otherNetMonthly: 0,
      nonTaxableNetMonthly: 0,
      extraCashExpense: 0,
      netMonthly: 0,
      personalSocial: 0,
      personalHousingFund: 0,
      employerHousingFund: 0,
      incomeTax: 0
    };
  }
  const estimated = estimateStageContributionsByRules(stage, rulePack);
  const selectedMethod = selectedStageBonusMethod(stage, rulePack);
  const elderlyCareDeduction = elderlyCareDeductionForMemberAt(household, member.name, targetDate);
  const currentCumulativeTax = cumulativeSalaryTax(
    member,
    rulePack,
    targetDate.getFullYear(),
    targetDate.getMonth() + 1,
    household
  );
  const previousCumulativeTax = cumulativeSalaryTax(
    member,
    rulePack,
    targetDate.getFullYear(),
    targetDate.getMonth(),
    household
  );
  const salaryTax = Math.max(0, currentCumulativeTax - previousCumulativeTax);
  const bonusPayout = stageBonusPayoutAmount(stage, targetDate.getFullYear(), targetDate.getMonth() + 1);
  const bonusTaxDue =
    selectedMethod === "separate"
      ? bonusTax(bonusPayout, ruleBrackets(rulePack, "monthly_converted_bonus_tax_brackets", defaultBonusTaxBrackets))
      : 0;
  const otherMonthly = stage.other_annual_taxable_income / 12;
  const nonTaxableMonthly = stage.monthly_non_taxable_income ?? 0;
  const extraCashExpense = stage.monthly_extra_cash_expense ?? 0;
  const incomeTax = salaryTax + bonusTaxDue;
  const taxableCashBeforeTax = stage.monthly_salary_gross + bonusPayout + otherMonthly;
  const salaryTaxShare = taxableCashBeforeTax > 0 ? stage.monthly_salary_gross / taxableCashBeforeTax : 0;
  const bonusTaxShare = taxableCashBeforeTax > 0 ? bonusPayout / taxableCashBeforeTax : 0;
  const otherTaxShare = taxableCashBeforeTax > 0 ? otherMonthly / taxableCashBeforeTax : 0;
  const salaryNetMonthly = Math.max(
    0,
    stage.monthly_salary_gross - estimated.personalSocial - estimated.personalHousingFund - incomeTax * salaryTaxShare
  );
  const bonusNetMonthly = Math.max(0, bonusPayout - incomeTax * bonusTaxShare);
  const otherNetMonthly = Math.max(0, otherMonthly - incomeTax * otherTaxShare);
  return {
    name: member.name,
    stageName: stage.name,
    grossMonthly: stage.monthly_salary_gross,
    bonusMonthly: bonusPayout,
    otherMonthly,
    nonTaxableMonthly,
    salaryNetMonthly,
    bonusNetMonthly,
    otherNetMonthly,
    nonTaxableNetMonthly: nonTaxableMonthly,
    extraCashExpense,
    netMonthly: Math.max(
      -999999,
      stage.monthly_salary_gross + bonusPayout + otherMonthly + nonTaxableMonthly - estimated.personalSocial - estimated.personalHousingFund - incomeTax - extraCashExpense
    ),
    personalSocial: estimated.personalSocial,
    personalHousingFund: estimated.personalHousingFund,
    employerHousingFund: estimated.employerHousingFund,
    incomeTax,
    elderlyCareDeduction
  };
}

const investmentPlanOptions = [
  { value: "manual_investment", label: "手动指定" },
  { value: "cash_only", label: "只放现金" },
  { value: "conservative_monthly_investment", label: "稳健理财" },
  { value: "balanced_monthly_investment", label: "均衡投资" },
  { value: "growth_monthly_investment", label: "进取定投" }
] as const;

const investmentRiskLabels: Record<string, string> = {
  cash: "现金保守",
  conservative: "稳健",
  balanced: "均衡",
  growth: "进取"
};

function calculateMonthlyInvestmentAllocation({
  monthlySurplus,
  cashValue,
  reserveTarget,
  monthlyInvestmentSetting,
  autoRebalance
}: {
  monthlySurplus: number;
  cashValue: number;
  reserveTarget: number;
  monthlyInvestmentSetting: number;
  autoRebalance: boolean;
}): MonthlyInvestmentAllocation {
  if (monthlyInvestmentSetting <= 0) {
    return { baseInvestment: 0, cashSweepInvestment: 0, totalInvestment: 0 };
  }

  if (!autoRebalance) {
    const baseInvestment = Math.min(monthlyInvestmentSetting, Math.max(0, monthlySurplus));
    return { baseInvestment, cashSweepInvestment: 0, totalInvestment: baseInvestment };
  }

  const projectedCashBeforeInvestment = cashValue + monthlySurplus;
  const availableAboveReserve = Math.max(0, projectedCashBeforeInvestment - reserveTarget);
  if (availableAboveReserve <= 0) {
    return { baseInvestment: 0, cashSweepInvestment: 0, totalInvestment: 0 };
  }

  const baseInvestment = Math.min(monthlyInvestmentSetting, Math.max(0, monthlySurplus), availableAboveReserve);
  const excessCash = Math.max(0, cashValue - reserveTarget);
  const cashSweepInvestment = Math.min(excessCash / 12, Math.max(0, availableAboveReserve - baseInvestment));
  return {
    baseInvestment,
    cashSweepInvestment,
    totalInvestment: baseInvestment + cashSweepInvestment
  };
}

function buildStrategyRecommendations(
  plans: PurchasePlanAnalysis[],
  scenario: ScenarioData
): StrategyRecommendation[] {
  if (!plans.length) return [];
  const finiteMonths = plans
    .map((plan) => plan.months_to_buy)
    .filter((month): month is number => month !== null);
  const maxMonths = Math.max(...finiteMonths, 1);
  const maxPayment = Math.max(...plans.map((plan) => plan.total_monthly_payment), 1);
  const maxCashAfterPurchase = Math.max(...plans.map((plan) => Math.max(plan.cash_after_transaction, 0)), 1);
  const liquidityWeight = Math.max(0, Math.min(10, scenario.liquidity_priority_score ?? 7)) / 10;

  return plans
    .map((plan) => {
      const speedScore =
        plan.months_to_buy === null ? 0 : Math.max(0, 100 - (plan.months_to_buy / maxMonths) * 36);
      const cashScore = Math.max(0, Math.min(100, (Math.max(plan.cash_after_transaction, 0) / maxCashAfterPurchase) * 100));
      const effectiveCashFlow = plan.post_purchase_cash_flow_with_pf_withdrawal;
      const flowScore = effectiveCashFlow >= 0
        ? 100
        : Math.max(0, 100 + effectiveCashFlow / 1000);
      const debtScore = Math.max(0, 100 - plan.debt_to_income_ratio * 150);
      const liquidityScore = plan.liquidity_ok ? 100 : 45;
      const paymentScore = Math.max(0, 100 - (plan.total_monthly_payment / maxPayment) * 42);
      const happinessScore = Math.max(0, Math.min(100, plan.happiness_score * 10));
      const score =
        speedScore * (0.2 + (1 - liquidityWeight) * 0.12) +
        cashScore * (0.16 + liquidityWeight * 0.14) +
        flowScore * 0.18 +
        debtScore * 0.16 +
        liquidityScore * 0.12 +
        paymentScore * 0.1 +
        happinessScore * 0.08;
      const reasons = [
        plan.months_to_buy === null
          ? "当前现金路径暂未达成买入条件"
          : `${plan.years_to_buy} 年左右可执行买入`,
        plan.liquidity_ok
          ? `买后仍覆盖 ${money(plan.required_liquidity_reserve)} 安全垫`
          : "买后安全垫偏紧，需要提高现金留存",
        effectiveCashFlow >= 0
          ? `策略后现金压力每月结余 ${money(effectiveCashFlow)}`
          : `策略后现金压力每月缺口 ${money(Math.abs(effectiveCashFlow))}`,
        plan.monthly_post_purchase_pf_withdrawal > 0
          ? `${providentStrategyLabel(plan)}，月均减少现金压力 ${money(plan.monthly_post_purchase_pf_withdrawal)}`
          : "公积金继续留存在账户，不进入自由现金流",
        plan.commercial_loan_amount === 0
          ? "不使用商贷，利息压力最低"
          : `商贷控制在 ${money(plan.commercial_loan_amount)}`
      ];
      return { plan, score: Math.round(score), reasons };
    })
    .sort((left, right) => right.score - left.score);
}

function buildInvestmentPlanRecommendations(
  household: HouseholdData,
  scenario: ScenarioData,
  result: AffordabilityResult | null
): InvestmentPlanRecommendation[] {
  const netIncome = result?.household_net_monthly_income ?? household.monthly_income;
  const carPurchasedNow =
    Boolean(result && household.car_plan.enabled && result.car_loan.enabled && result.car_loan.purchase_delay_months <= 0);
  const carMonthlyCashCost =
    result && carPurchasedNow
      ? result.car_loan.current_monthly_payment + result.car_loan.monthly_cash_operating_cost
      : Math.max(0, household.car_plan.no_car_monthly_commute_cost ?? 0);
  const effectiveDebt = result?.effective_monthly_debt_payment ?? household.monthly_debt_payment;
  const currentMonthlyExpense = householdExpenseAt(household, new Date(), 0);
  const monthlySurplus = Math.max(0, netIncome - currentMonthlyExpense - effectiveDebt - carMonthlyCashCost);
  const currentCash = household.liquid_assets;
  const totalAssets = Math.max(1, household.liquid_assets + household.investments);
  const currentInvestmentRatio = household.investments / totalAssets;
  const configuredReserveMonths = Math.max(
    1,
    household.investment_cash_reserve_months ?? household.required_liquidity_months ?? 6
  );
  const emergencyTarget = currentMonthlyExpense * configuredReserveMonths;
  const emergencyGap = Math.max(0, emergencyTarget - currentCash);
  const emergencySurplus = Math.max(0, currentCash - emergencyTarget);
  const gapPressure = Math.min(1, emergencyGap / Math.max(emergencyTarget, 1));
  const housePressure = Math.min(1, Math.max(0, (scenario.liquidity_priority_score ?? 7) / 10));
  const baseMonthlyInvestable = Math.max(0, monthlySurplus - emergencyGap / 12);
  const specs = [
    {
      variant: "暂停定投保现金",
      planName: "cash_only",
      riskLevel: "cash",
      riskLabel: "现金保守",
      description: "现金安全垫未达标或购房窗口较近时，先把月结余留在现金池。",
      ratio: 0,
      annualReturn: 0.005,
      cashReserveMonths: Math.max(9, configuredReserveMonths),
      equityRatio: 0.05,
      bondRatio: 0.15,
      cashRatio: 0.8
    },
    {
      variant: "稳健定投",
      planName: "conservative_monthly_investment",
      riskLevel: "conservative",
      riskLabel: "稳健",
      description: "以购房安全垫为优先，少量定投，组合波动控制在较低水平。",
      ratio: 0.3,
      annualReturn: 0.025,
      cashReserveMonths: 9,
      equityRatio: 0.25,
      bondRatio: 0.45,
      cashRatio: 0.3
    },
    {
      variant: "均衡定投",
      planName: "balanced_monthly_investment",
      riskLevel: "balanced",
      riskLabel: "均衡",
      description: "现金垫基本满足后，把一半左右月结余投入长期组合。",
      ratio: 0.5,
      annualReturn: 0.04,
      cashReserveMonths: 6,
      equityRatio: 0.45,
      bondRatio: 0.35,
      cashRatio: 0.2
    },
    {
      variant: "进取定投",
      planName: "growth_monthly_investment",
      riskLevel: "growth",
      riskLabel: "进取",
      description: "现金垫充足且购房弹性较高时，提高权益比例和定投强度。",
      ratio: 0.65,
      annualReturn: 0.06,
      cashReserveMonths: 6,
      equityRatio: 0.65,
      bondRatio: 0.25,
      cashRatio: 0.1
    }
  ];

  return specs
    .map((spec) => {
      const baseInvestment = spec.ratio === 0 ? 0 : baseMonthlyInvestable * spec.ratio;
      const cashSweepInvestment = spec.ratio === 0 ? 0 : (emergencySurplus / 12) * Math.min(1, spec.ratio + 0.2);
      const monthlyInvestment = Math.round((baseInvestment + cashSweepInvestment) / 100) * 100;
      const reserveScore = Math.max(0, 100 - Math.abs(spec.cashReserveMonths - configuredReserveMonths) * 6);
      const riskFitScore =
        spec.riskLevel === "cash"
          ? 70 + gapPressure * 30
          : Math.max(0, 100 - gapPressure * 45 - housePressure * spec.equityRatio * 35);
      const returnScore = Math.max(0, Math.min(100, spec.annualReturn / 0.06 * 100));
      const allocationDriftScore = Math.max(0, 100 - Math.abs(currentInvestmentRatio - spec.equityRatio) * 80);
      const score = Math.round(
        riskFitScore * 0.38 +
          reserveScore * 0.24 +
          returnScore * 0.18 +
          allocationDriftScore * 0.12 +
          (monthlySurplus > 0 ? 8 : 0)
      );
      const reasons = [
        emergencyGap > 0
          ? `现金安全垫缺口约 ${money(emergencyGap)}，定投会先让位给现金池`
          : emergencySurplus > 0
            ? `现金安全垫已覆盖，超额现金约 ${money(emergencySurplus)} 会分 12 个月逐步加到定投`
            : `当前现金已覆盖约 ${Math.floor(currentCash / Math.max(currentMonthlyExpense, 1))} 个月支出`,
        monthlyInvestment > 0
          ? `建议月定投 ${money(monthlyInvestment)}，其中含基础结余定投和现金超额滚入`
          : "暂不定投，把月结余优先留作购房和应急现金",
        `目标配置：权益 ${percent(spec.equityRatio)}、固收 ${percent(spec.bondRatio)}、现金 ${percent(spec.cashRatio)}`
      ];
      return { ...spec, monthlyInvestment, score, reasons };
    })
    .sort((left, right) => right.score - left.score);
}

function investmentStrategyDetails(variant: string) {
  if (variant.includes("暂停")) {
    return ["适合现金安全垫不足、购房窗口较近或收入波动较大的阶段。", "月结余优先留在现金池，减少市场波动对首付计划的影响。"];
  }
  if (variant.includes("稳健")) {
    return ["适合首付目标明确、但仍希望获得少量理财收益的阶段。", "控制权益比例，把更多资金放在固收和现金类资产，降低买房前被迫卖出的风险。"];
  }
  if (variant.includes("均衡")) {
    return ["适合现金垫基本达标、购房时间仍有弹性的阶段。", "在现金、固收和权益之间折中，收益和波动都居中。"];
  }
  if (variant.includes("进取")) {
    return ["适合现金垫充足、购房可延后且能承受净值波动的阶段。", "提高权益比例和定投强度，追求更高预期收益，但买房前回撤风险也更高。"];
  }
  return ["完全按上方手动参数执行，适合已经有明确基金、股票或现金管理方案时使用。", "手动方案不会自动修正风险比例，请重点检查现金安全垫和交易手续费。"];
}

function purchaseStrategyDetails(plan: PurchasePlanAnalysis) {
  const providentStrategy = plan.post_purchase_pf_strategy_label || plan.monthly_post_purchase_pf_withdrawal > 0
    ? [`贷后公积金策略：${providentStrategyLabel(plan)}，月均改善约 ${money(plan.monthly_post_purchase_pf_withdrawal)}。`]
    : [];
  if (plan.variant.includes("0商贷")) {
    return ["目标是尽量只使用公积金贷款，降低利息和月供波动。", "缺点是可能需要更久攒首付，且受缴存年限、房源性质和贷款年限限制。", ...providentStrategy];
  }
  if (plan.variant.includes("微量商贷")) {
    return ["目标是在保持低商贷压力的同时，适当加快买房时间。", "系统会在规则包允许的微量商贷比例内逐月试算，只采用交易后现金和压力情景都不穿底的月份，并结合购房月份对应的公积金上限。", ...providentStrategy];
  }
  if (plan.variant.includes("较多商贷")) {
    return ["目标是压低首付门槛、加快买入，但会增加月供和总利息。", "适合看重买入时间，且买后月结余和负债收入比仍可接受的情况。", ...providentStrategy];
  }
  return ["完全按你设置的首付、商贷、公积金贷、还款方式和买入时间测算。", "系统会从手动买入月份开始校验；如果当月现金不安全，会继续向后寻找可执行月份。", ...providentStrategy];
}

function carStrategyDetails(variant: string) {
  if (variant.includes("全款")) {
    return ["不产生车贷利息，长期总成本最低。", "短期现金占用最高，可能推迟买房或压低购后安全垫。"];
  }
  if (variant.includes("高首付")) {
    return ["用较高首付换取较低贷款本金和月供。", "适合现金较充裕、希望控制负债收入比的家庭。"];
  }
  if (variant.includes("低首付")) {
    return ["保留更多现金在手里，降低买车当月冲击。", "月供、总利息和买后现金流压力会更高，需要看可视化现金曲线。"];
  }
  if (variant.includes("延后")) {
    return ["把买车时间后移，让收入、现金垫或买房首付先积累。", "适合当前现金紧张但未来收入确定性较高的情况。"];
  }
  return ["按当前买车目标和贷款参数生成，重点看买后现金、月结余和幸福指数是否匹配家庭优先级。"];
}

export function App() {
  const [households, setHouseholds] = useState<RecordEnvelope<HouseholdData>[]>([]);
  const [scenarios, setScenarios] = useState<RecordEnvelope<ScenarioData>[]>([]);
  const [rulePacks, setRulePacks] = useState<RecordEnvelope<RulePackData>[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [scenarioResults, setScenarioResults] = useState<Record<string, AffordabilityResult>>({});
  const [sourceUrl, setSourceUrl] = useState(sourceDefaults[0]);
  const [sourcePreview, setSourcePreview] = useState<SourceDocumentRecord | null>(null);
  const [activePage, setActivePage] = useState<PageName>("可视化");
  const [selectedPlanVariants, setSelectedPlanVariants] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [calculationVersion, setCalculationVersion] = useState(0);
  const [calculatedVersion, setCalculatedVersion] = useState(-1);
  const dirtyRef = useRef(false);
  const calculationSeqRef = useRef(0);

  const household = households[0];
  const selectedScenario = scenarios.find((item) => item.id === selectedScenarioId) ?? scenarios[0];
  const activeRulePack = rulePacks.find((item) => item.data.status === "active") ?? rulePacks[0];
  const hasCurrentCalculation = calculatedVersion === calculationVersion && !isCalculating;
  const calculationPending = !hasCurrentCalculation;
  const displayScenarioResults = hasCurrentCalculation ? scenarioResults : {};
  const result = selectedScenario ? displayScenarioResults[selectedScenario.id] ?? null : null;
  const incomeMembers = household?.data.members ?? [];
  const carPlan = household?.data.car_plan ?? defaultCarPlan;
  const phasedLoans = household?.data.phased_loans ?? [];
  const scheduledExpenses = household?.data.scheduled_expenses ?? [];
  const elderlyDependents = household?.data.elderly_dependents ?? [];
  const selectedPlanVariant = selectedScenario
    ? selectedScenario.data.selected_purchase_plan_variant || selectedPlanVariants[selectedScenario.id] || ""
    : "";
  const currentRecommendation = useMemo(
    () =>
      result && selectedScenario
        ? buildStrategyRecommendations(result.purchase_plan_analyses, selectedScenario.data)[0] ?? null
        : null,
    [result, selectedScenario]
  );
  const selectedPlan =
    result?.purchase_plan_analyses.find((plan) => plan.variant === selectedPlanVariant) ??
    currentRecommendation?.plan ??
    result?.purchase_plan_analyses[0] ??
    null;
  const scenarioComparisons = useMemo<ScenarioComparison[]>(
    () =>
      scenarios
        .map((scenario): ScenarioComparison | null => {
          const scenarioResult = displayScenarioResults[scenario.id];
          if (!scenarioResult) return null;
          const recommendation =
            buildStrategyRecommendations(scenarioResult.purchase_plan_analyses, scenario.data)[0] ?? null;
          const selectedVariant = scenario.data.selected_purchase_plan_variant || selectedPlanVariants[scenario.id];
          const selectedPlan =
            scenarioResult.purchase_plan_analyses.find((plan) => plan.variant === selectedVariant) ??
            recommendation?.plan ??
            scenarioResult.purchase_plan_analyses[0] ??
            null;
          return { scenario, result: scenarioResult, recommendation, selectedPlan };
        })
        .filter((item): item is ScenarioComparison => item !== null),
    [displayScenarioResults, scenarios, selectedPlanVariants]
  );
  const ruleNumber = (key: string, fallback: number) => {
    const value = Number(activeRulePack?.data.params[key]);
    return Number.isFinite(value) ? value : fallback;
  };

  const runCalculation = useCallback(async () => {
    if (!household || !activeRulePack || scenarios.length === 0) return;
    const requestSeq = ++calculationSeqRef.current;
    const requestVersion = calculationVersion;
    setIsCalculating(true);
    setError(null);
    try {
      const calculated = await Promise.all(
        scenarios.map(async (scenario) => [
          scenario.id,
          await calculateAffordability(household.data, scenario.data, activeRulePack.data)
        ] as const)
      );
      if (requestSeq !== calculationSeqRef.current) return;
      const nextResults = Object.fromEntries(calculated);
      setScenarioResults(nextResults);
      setCalculatedVersion(requestVersion);
      setIsCalculating(false);
    } catch (err) {
      if (requestSeq !== calculationSeqRef.current) return;
      setError(err instanceof Error ? err.message : "计算失败");
      setIsCalculating(false);
    }
  }, [activeRulePack, calculationVersion, household, scenarios]);

  useEffect(() => {
    let active = true;
    loadInitialData()
      .then(([householdRecords, scenarioRecords, ruleRecords]) => {
        if (!active) return;
        setHouseholds(householdRecords.map(completeHouseholdDefaults));
        setScenarios(scenarioRecords);
        setRulePacks(ruleRecords);
        setSelectedScenarioId(scenarioRecords[0]?.id ?? "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void runCalculation();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [runCalculation]);

  useEffect(() => {
    if (!selectedScenario || !result?.purchase_plan_analyses.length) return;
    const currentVariant = selectedScenario.data.selected_purchase_plan_variant || selectedPlanVariants[selectedScenario.id];
    if (result.purchase_plan_analyses.some((plan) => plan.variant === currentVariant)) return;
    const recommended =
      buildStrategyRecommendations(result.purchase_plan_analyses, selectedScenario.data)[0]?.plan.variant ??
      result.purchase_plan_analyses[0].variant;
    setSelectedPlanVariants((items) => ({ ...items, [selectedScenario.id]: recommended }));
  }, [result, selectedPlanVariants, selectedScenario]);

  const markDirty = (affectsCalculation = true) => {
    dirtyRef.current = true;
    setSaveState("dirty");
    if (affectsCalculation) {
      setCalculationVersion((version) => version + 1);
    }
  };

  const updateHousehold = <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => {
    if (!household) return;
    markDirty(key !== "name");
    setHouseholds((items) =>
      items.map((item, index) =>
        index === 0 ? { ...item, data: { ...item.data, [key]: value } } : item
      )
    );
  };

  const updateScenario = <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => {
    if (!selectedScenario) return;
    const affectsCalculation = !["selected_purchase_plan_variant", "name", "district", "ring_area"].includes(String(key));
    markDirty(affectsCalculation);
    setScenarios((items) =>
      items.map((item) =>
        item.id === selectedScenario.id ? { ...item, data: { ...item.data, [key]: value } } : item
      )
    );
  };

  const updateIncomeMember = <K extends keyof IncomeMember>(
    index: number,
    key: K,
    value: IncomeMember[K]
  ) => {
    if (!household) return;
    const nextMembers = incomeMembers.map((member, memberIndex) =>
      memberIndex === index ? { ...member, [key]: value } : member
    );
    updateHousehold("members", nextMembers);
  };

  const addIncomeMember = () => {
    const nextMember: IncomeMember = {
      name: `成员 ${incomeMembers.length + 1}`,
      monthly_salary_gross: 0,
      annual_bonus: 0,
      monthly_social_insurance: 0,
      monthly_housing_fund: 0,
      housing_fund_personal_rate: 0.12,
      housing_fund_employer_rate: 0.12,
      monthly_special_additional_deduction: 0,
      other_annual_deductions: 0,
      other_annual_taxable_income: 0,
      employment_start_date: "2027-01-01",
      bonus_tax_method: "best",
      income_stages: [
        {
          name: "当前收入",
          start_date: "2027-01-01",
          end_date: null,
          monthly_salary_gross: 0,
          annual_bonus: 0,
          annual_bonus_payout_month: 4,
          monthly_non_taxable_income: 0,
          monthly_extra_cash_expense: 0,
          monthly_social_insurance: 0,
          monthly_housing_fund: 0,
          housing_fund_personal_rate: 0.12,
          housing_fund_employer_rate: 0.12,
          monthly_special_additional_deduction: 0,
          other_annual_deductions: 0,
          other_annual_taxable_income: 0,
          bonus_tax_method: "best",
          payroll_contributions_enabled: true
        }
      ]
    };
    updateHousehold("members", [...incomeMembers, nextMember]);
  };

  const removeIncomeMember = (index: number) => {
    if (incomeMembers.length <= 1) return;
    updateHousehold(
      "members",
      incomeMembers.filter((_, memberIndex) => memberIndex !== index)
    );
  };

  const updateIncomeStage = <K extends keyof IncomeStageData>(
    memberIndex: number,
    stageIndex: number,
    key: K,
    value: IncomeStageData[K]
  ) => {
    const nextMembers = incomeMembers.map((member, currentMemberIndex) => {
      if (currentMemberIndex !== memberIndex) return member;
      const stages = incomeStagesForMember(member);
      const nextStages = stages.map((stage, currentStageIndex) =>
        currentStageIndex === stageIndex ? { ...stage, [key]: value } : stage
      );
      const nextMember = { ...member, income_stages: nextStages };
      if (stageIndex === 0) {
        const firstStage = nextStages[0];
        return {
          ...nextMember,
          monthly_salary_gross: firstStage.monthly_salary_gross,
          annual_bonus: firstStage.annual_bonus,
          monthly_social_insurance: firstStage.monthly_social_insurance,
          monthly_housing_fund: firstStage.monthly_housing_fund,
          housing_fund_personal_rate: firstStage.housing_fund_personal_rate,
          housing_fund_employer_rate: firstStage.housing_fund_employer_rate,
          monthly_special_additional_deduction: firstStage.monthly_special_additional_deduction,
          other_annual_deductions: firstStage.other_annual_deductions,
          other_annual_taxable_income: firstStage.other_annual_taxable_income,
          employment_start_date: firstStage.start_date,
          bonus_tax_method: firstStage.bonus_tax_method
        };
      }
      return nextMember;
    });
    updateHousehold("members", nextMembers);
  };

  const addIncomeStage = (memberIndex: number) => {
    const nextMembers = incomeMembers.map((member, currentMemberIndex) => {
      if (currentMemberIndex !== memberIndex) return member;
      const stages = incomeStagesForMember(member);
      const lastStage = stages[stages.length - 1] ?? incomeStageFromMember(member);
      const nextStage: IncomeStageData = {
        ...lastStage,
        name: `收入阶段 ${stages.length + 1}`,
        start_date: "2028-01-01",
        end_date: null
      };
      return { ...member, income_stages: [...stages, nextStage] };
    });
    updateHousehold("members", nextMembers);
  };

  const removeIncomeStage = (memberIndex: number, stageIndex: number) => {
    const nextMembers = incomeMembers.map((member, currentMemberIndex) => {
      if (currentMemberIndex !== memberIndex) return member;
      const stages = incomeStagesForMember(member);
      if (stages.length <= 1) return member;
      const nextStages = stages.filter((_, currentStageIndex) => currentStageIndex !== stageIndex);
      const firstStage = nextStages[0];
      return {
        ...member,
        income_stages: nextStages,
        monthly_salary_gross: firstStage.monthly_salary_gross,
        annual_bonus: firstStage.annual_bonus,
        monthly_social_insurance: firstStage.monthly_social_insurance,
        monthly_housing_fund: firstStage.monthly_housing_fund,
        housing_fund_personal_rate: firstStage.housing_fund_personal_rate,
        housing_fund_employer_rate: firstStage.housing_fund_employer_rate,
        monthly_special_additional_deduction: firstStage.monthly_special_additional_deduction,
        other_annual_deductions: firstStage.other_annual_deductions,
        other_annual_taxable_income: firstStage.other_annual_taxable_income,
        employment_start_date: firstStage.start_date,
        bonus_tax_method: firstStage.bonus_tax_method
      };
    });
    updateHousehold("members", nextMembers);
  };

  const updatePhasedLoan = <K extends keyof PhasedLoanData>(
    index: number,
    key: K,
    value: PhasedLoanData[K]
  ) => {
    const nextLoans = phasedLoans.map((loan, loanIndex) =>
      loanIndex === index ? { ...loan, [key]: value } : loan
    );
    updateHousehold("phased_loans", nextLoans);
  };

  const addPhasedLoan = () => {
    const nextLoan: PhasedLoanData = {
      borrower: incomeMembers[0]?.name ?? "成员 1",
      name: `目前贷款 ${phasedLoans.length + 1}`,
      loan_type: "other",
      principal: 0,
      annual_rate: 0.028,
      repayment_method: "equal_installment",
      remaining_months: 120,
      interest_start_month: "2026-07",
      interest_only_until: "2028-07"
    };
    updateHousehold("phased_loans", [...phasedLoans, nextLoan]);
  };

  const removePhasedLoan = (index: number) => {
    updateHousehold(
      "phased_loans",
      phasedLoans.filter((_, loanIndex) => loanIndex !== index)
    );
  };

  const updateScheduledExpense = <K extends keyof ScheduledExpenseData>(
    index: number,
    key: K,
    value: ScheduledExpenseData[K]
  ) => {
    const nextExpenses = scheduledExpenses.map((expense, expenseIndex) =>
      expenseIndex === index ? { ...expense, [key]: value } : expense
    );
    updateHousehold("scheduled_expenses", nextExpenses);
  };

  const addScheduledExpense = () => {
    const nextExpense: ScheduledExpenseData = {
      name: `定时支出 ${scheduledExpenses.length + 1}`,
      monthly_amount: 1000,
      start_month: "2027-07",
      end_month: null,
      tax_deductible_elderly_care: false,
      notes: ""
    };
    updateHousehold("scheduled_expenses", [...scheduledExpenses, nextExpense]);
  };

  const removeScheduledExpense = (index: number) => {
    updateHousehold(
      "scheduled_expenses",
      scheduledExpenses.filter((_, expenseIndex) => expenseIndex !== index)
    );
  };

  const updateElderlyDependent = <K extends keyof ElderlyDependentData>(
    index: number,
    key: K,
    value: ElderlyDependentData[K]
  ) => {
    const nextDependents = elderlyDependents.map((dependent, dependentIndex) =>
      dependentIndex === index ? { ...dependent, [key]: value } : dependent
    );
    updateHousehold("elderly_dependents", nextDependents);
  };

  const addElderlyDependent = () => {
    const nextDependent: ElderlyDependentData = {
      member_name: incomeMembers[0]?.name ?? "成员 1",
      relationship_label: `直系亲属老人 ${elderlyDependents.length + 1}`,
      birth_month: "",
      is_only_child: false,
      shared_monthly_deduction: 1500
    };
    updateHousehold("elderly_dependents", [...elderlyDependents, nextDependent]);
  };

  const removeElderlyDependent = (index: number) => {
    updateHousehold(
      "elderly_dependents",
      elderlyDependents.filter((_, dependentIndex) => dependentIndex !== index)
    );
  };

  const updateCarPlan = <K extends keyof CarPlanData>(key: K, value: CarPlanData[K]) => {
    updateHousehold("car_plan", { ...carPlan, [key]: value });
  };
  const updateCarPlanPatch = (patch: Partial<CarPlanData>) => {
    updateHousehold("car_plan", { ...carPlan, ...patch });
  };

  const updateRulePack = <K extends keyof RulePackData>(key: K, value: RulePackData[K]) => {
    if (!activeRulePack) return;
    markDirty();
    setRulePacks((items) =>
      items.map((item) =>
        item.id === activeRulePack.id ? { ...item, data: { ...item.data, [key]: value } } : item
      )
    );
  };

  const updateRuleParam = (key: string, value: number | string | boolean) => {
    if (!activeRulePack) return;
    markDirty();
    setRulePacks((items) =>
      items.map((item) =>
        item.id === activeRulePack.id
          ? {
              ...item,
              data: {
                ...item.data,
                params: { ...item.data.params, [key]: value }
              }
            }
          : item
      )
    );
  };

  const persistAll = useCallback(async () => {
    if (!household || !selectedScenario || !activeRulePack) return;
    setSaving(true);
    setSaveState("saving");
    setError(null);
    try {
      const [savedHousehold, savedScenario, savedRulePack] = await Promise.all([
        saveHousehold(household.id, household.data),
        saveScenario(selectedScenario.id, selectedScenario.data),
        saveRulePack(activeRulePack.id, activeRulePack.data)
      ]);
      setHouseholds((items) =>
        items.map((item) => (item.id === savedHousehold.id ? savedHousehold : item))
      );
      setScenarios((items) =>
        items.map((item) => (item.id === savedScenario.id ? savedScenario : item))
      );
      setRulePacks((items) =>
        items.map((item) => (item.id === savedRulePack.id ? savedRulePack : item))
      );
      dirtyRef.current = false;
      setSaveState("saved");
    } catch (err) {
      setSaveState("dirty");
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }, [activeRulePack, household, selectedScenario]);

  useEffect(() => {
    if (!dirtyRef.current || loading) return;
    const timer = window.setTimeout(() => {
      void persistAll();
    }, 900);
    return () => window.clearTimeout(timer);
  }, [households, loading, persistAll, rulePacks, scenarios, selectedScenarioId]);

  const addScenario = async () => {
    if (!selectedScenario) return;
    const cloned = {
      ...selectedScenario.data,
      name: `${selectedScenario.data.name} 副本`,
      total_price: Math.round(selectedScenario.data.total_price * 1.03)
    };
    const created = await createScenario(cloned);
    setScenarios((items) => [...items, created]);
    setSelectedScenarioId(created.id);
  };

  const previewSource = async () => {
    setSaving(true);
    setError(null);
    try {
      const preview = await fetchSourcePreview(sourceUrl, "手动抓取来源");
      setSourcePreview(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "抓取失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="loading-screen">
        <Loader2 className="spin" size={28} />
        <span>正在加载本地规划数据</span>
      </main>
    );
  }

  if (!household || !selectedScenario || !activeRulePack) {
    return <main className="loading-screen">本地数据库没有可用初始数据。</main>;
  }

  const setCurrentScenarioPlanVariant = (variant: string) => {
    setSelectedPlanVariants((items) => ({ ...items, [selectedScenario.id]: variant }));
    updateScenario("selected_purchase_plan_variant", variant);
  };

  const pageContent = {
    家庭财务: (
      <HouseholdPage
        household={household.data}
        scenario={selectedScenario.data}
        incomeMembers={incomeMembers}
        phasedLoans={phasedLoans}
        scheduledExpenses={scheduledExpenses}
        elderlyDependents={elderlyDependents}
        result={result}
        activeRulePack={activeRulePack.data}
        updateHousehold={updateHousehold}
        updateIncomeMember={updateIncomeMember}
        addIncomeMember={addIncomeMember}
        removeIncomeMember={removeIncomeMember}
        updateIncomeStage={updateIncomeStage}
        addIncomeStage={addIncomeStage}
        removeIncomeStage={removeIncomeStage}
        updatePhasedLoan={updatePhasedLoan}
        addPhasedLoan={addPhasedLoan}
        removePhasedLoan={removePhasedLoan}
        updateScheduledExpense={updateScheduledExpense}
        addScheduledExpense={addScheduledExpense}
        removeScheduledExpense={removeScheduledExpense}
        updateElderlyDependent={updateElderlyDependent}
        addElderlyDependent={addElderlyDependent}
        removeElderlyDependent={removeElderlyDependent}
      />
    ),
    理财计划: (
      <InvestmentPlanPage
        household={household.data}
        scenario={selectedScenario.data}
        result={result}
        updateHousehold={updateHousehold}
        updateScenario={updateScenario}
      />
    ),
    购房计划: (
      <ScenarioPage
        scenarios={scenarios}
        selectedScenario={selectedScenario}
        setSelectedScenarioId={setSelectedScenarioId}
        updateScenario={updateScenario}
        addScenario={addScenario}
        result={result}
        scenarioComparisons={scenarioComparisons}
        selectedPlanVariant={selectedPlan?.variant ?? ""}
        setSelectedPlanVariant={setCurrentScenarioPlanVariant}
        calculationPending={calculationPending}
      />
    ),
    买车计划: (
      <CarPlanPage
        carPlan={carPlan}
        result={result}
        updateCarPlan={updateCarPlan}
        updateCarPlanPatch={updateCarPlanPatch}
      />
    ),
    政策规则: (
      <RulePage
        activeRulePack={activeRulePack.data}
        ruleNumber={ruleNumber}
        updateRulePack={updateRulePack}
        updateRuleParam={updateRuleParam}
        sourceUrl={sourceUrl}
        setSourceUrl={setSourceUrl}
        sourcePreview={sourcePreview}
        previewSource={previewSource}
        saving={saving}
      />
    ),
    可视化: (
      <VisualizationPage
        result={result}
        household={household.data}
        selectedScenario={selectedScenario}
        scenarioComparisons={scenarioComparisons}
        setSelectedScenarioId={setSelectedScenarioId}
        selectedPlan={selectedPlan}
        selectedPlanVariant={selectedPlan?.variant ?? ""}
        setSelectedPlanVariant={setCurrentScenarioPlanVariant}
        activeRulePack={activeRulePack.data}
        calculationPending={calculationPending}
      />
    ),
    导出方案: (
      <ExportPage
        result={result}
        scenario={selectedScenario.data}
        selectedPlan={selectedPlan}
        selectedPlanVariant={selectedPlan?.variant ?? ""}
        setSelectedPlanVariant={setCurrentScenarioPlanVariant}
        runCalculation={runCalculation}
      />
    )
  } satisfies Record<PageName, ReactNode>;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Home size={22} />
          <div>
            <h1>北京买房可行性规划计算器</h1>
            <p>本机数据 · 手动规则包 · 抓取预览不自动生效</p>
          </div>
        </div>
        <div className="topbar-actions">
          {error ? <span className="error-text">{error}</span> : null}
          {calculationPending ? (
            <span className="save-state calculating">
              <Loader2 className="spin" size={14} /> 正在计算策略
            </span>
          ) : null}
          {saveState !== "idle" ? (
            <span className={`save-state ${saveState}`}>
              {saveState === "dirty"
                ? "有未保存修改"
                : saveState === "saving"
                  ? "自动保存中"
                  : "已自动保存"}
            </span>
          ) : null}
          <button className="ghost-button" onClick={runCalculation}>
            <RefreshCw size={16} /> 重新计算
          </button>
          <button className="primary-button" onClick={persistAll} disabled={saving}>
            {saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
            保存本地
          </button>
        </div>
      </header>

      <nav className="page-nav">
        {pages.map((page) => (
          <button
            key={page}
            className={page === activePage ? "page-tab active" : "page-tab"}
            onClick={() => setActivePage(page)}
          >
            {page}
          </button>
        ))}
      </nav>

      <section className="page-workspace">{pageContent[activePage]}</section>
    </main>
  );
}

function HouseholdPage({
  household,
  scenario,
  incomeMembers,
  phasedLoans,
  scheduledExpenses,
  elderlyDependents,
  result,
  activeRulePack,
  updateHousehold,
  updateIncomeMember,
  addIncomeMember,
  removeIncomeMember,
  updateIncomeStage,
  addIncomeStage,
  removeIncomeStage,
  updatePhasedLoan,
  addPhasedLoan,
  removePhasedLoan,
  updateScheduledExpense,
  addScheduledExpense,
  removeScheduledExpense,
  updateElderlyDependent,
  addElderlyDependent,
  removeElderlyDependent
}: {
  household: HouseholdData;
  scenario: ScenarioData;
  incomeMembers: IncomeMember[];
  phasedLoans: PhasedLoanData[];
  scheduledExpenses: ScheduledExpenseData[];
  elderlyDependents: ElderlyDependentData[];
  result: AffordabilityResult | null;
  activeRulePack: RulePackData;
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
  updateIncomeMember: <K extends keyof IncomeMember>(
    index: number,
    key: K,
    value: IncomeMember[K]
  ) => void;
  addIncomeMember: () => void;
  removeIncomeMember: (index: number) => void;
  updateIncomeStage: <K extends keyof IncomeStageData>(
    memberIndex: number,
    stageIndex: number,
    key: K,
    value: IncomeStageData[K]
  ) => void;
  addIncomeStage: (memberIndex: number) => void;
  removeIncomeStage: (memberIndex: number, stageIndex: number) => void;
  updatePhasedLoan: <K extends keyof PhasedLoanData>(
    index: number,
    key: K,
    value: PhasedLoanData[K]
  ) => void;
  addPhasedLoan: () => void;
  removePhasedLoan: (index: number) => void;
  updateScheduledExpense: <K extends keyof ScheduledExpenseData>(
    index: number,
    key: K,
    value: ScheduledExpenseData[K]
  ) => void;
  addScheduledExpense: () => void;
  removeScheduledExpense: (index: number) => void;
  updateElderlyDependent: <K extends keyof ElderlyDependentData>(
    index: number,
    key: K,
    value: ElderlyDependentData[K]
  ) => void;
  addElderlyDependent: () => void;
  removeElderlyDependent: (index: number) => void;
}) {
  const currentMonthlyExpense = householdExpenseAt(household, new Date(), 0);
  const careerShock = { ...defaultCareerShock, ...(household.career_shock ?? {}) };
  const estimatedUnemploymentBenefitMonths = unemploymentBenefitMonthsFromService(household.social_security_months ?? 0);
  const estimatedUnemploymentBenefitMonthly = unemploymentBenefitMonthlyFromService(household.social_security_months ?? 0, activeRulePack);
  const estimatedLaterUnemploymentBenefitMonthly = Number(activeRulePack.params.beijing_unemployment_benefit_after_12_months ?? 2129);
  const estimatedSelfSocialInsuranceMonthly = autoSelfSocialInsuranceMonthly(activeRulePack);
  const elderlyPolicyStatus = elderlyDeductionPolicyStatus(elderlyDependents, new Date());
  const phasedLoanPhaseSummary = (result?.phased_loan_summaries ?? []).reduce<Record<string, number>>((summary, loan) => {
    summary[loan.phase] = (summary[loan.phase] ?? 0) + 1;
    return summary;
  }, {});
  const phasedLoanSummaryText = phasedLoans.length > 0
    ? Object.entries(phasedLoanPhaseSummary).map(([phase, count]) => `${phase} ${count} 笔`).join("，") || "等待计算"
    : "暂无目前贷款";
  const updateCareerShock = (patch: Partial<typeof defaultCareerShock>) => {
    const normalizedPatch: Partial<typeof defaultCareerShock> = { ...patch };
    if (patch.self_birth_month !== undefined) {
      const age = ageYearsFromBirthMonth(patch.self_birth_month, new Date());
      if (age !== null) normalizedPatch.self_current_age = age;
    } else if (patch.self_current_age !== undefined) {
      normalizedPatch.self_birth_month = birthMonthFromAge(patch.self_current_age, new Date());
    }
    if (patch.spouse_birth_month !== undefined) {
      const age = ageYearsFromBirthMonth(patch.spouse_birth_month, new Date());
      if (age !== null) normalizedPatch.spouse_current_age = age;
    } else if (patch.spouse_current_age !== undefined) {
      normalizedPatch.spouse_birth_month = birthMonthFromAge(patch.spouse_current_age, new Date());
    }
    updateHousehold("career_shock", { ...careerShock, ...normalizedPatch });
  };
  const today = new Date();
  const selfAgeFromBirthMonth = ageYearsFromBirthMonth(careerShock.self_birth_month, today);
  const spouseAgeFromBirthMonth = ageYearsFromBirthMonth(careerShock.spouse_birth_month, today);
  const displayedSelfCurrentAge = selfAgeFromBirthMonth ?? careerShock.self_current_age;
  const displayedSpouseCurrentAge = spouseAgeFromBirthMonth ?? careerShock.spouse_current_age;
  const normalizedBorrowerMemberIndex = Math.min(
    Math.max(0, household.borrower_member_index ?? 0),
    Math.max(0, incomeMembers.length - 1)
  );
  const borrowerMember = incomeMembers[normalizedBorrowerMemberIndex] ?? incomeMembers[0];
  const borrowerMemberName = borrowerMember?.name || `成员 ${normalizedBorrowerMemberIndex + 1}`;
  const borrowerDisplayAge =
    normalizedBorrowerMemberIndex === 0
      ? displayedSelfCurrentAge
      : normalizedBorrowerMemberIndex === 1
        ? displayedSpouseCurrentAge
        : household.borrower_age ?? 30;
  const borrowerAgeForPolicy = Math.min(68, Math.max(18, Math.round(borrowerDisplayAge ?? household.borrower_age ?? 30)));
  const memberCompositionText = incomeMembers.length > 0
    ? `${incomeMembers.length} 人：${incomeMembers.map((member) => member.name || "未命名成员").join("、")}`
    : "待添加成员";
  const memberAgeText = incomeMembers.length > 0
    ? incomeMembers
        .map((member, index) => {
          const age = index === 0 ? displayedSelfCurrentAge : index === 1 ? displayedSpouseCurrentAge : null;
          return `${member.name || `成员 ${index + 1}`} ${age !== null && age !== undefined ? `${age} 岁` : "年龄待填"}`;
        })
        .join("、")
    : "待填写";
  const updateSelfBirthMonth = (birthMonth: string) => {
    updateCareerShock({ self_birth_month: birthMonth });
  };
  const updateSpouseBirthMonth = (birthMonth: string) => {
    updateCareerShock({ spouse_birth_month: birthMonth });
  };
  const updateSelfCurrentAge = (age: number) => {
    updateCareerShock({ self_current_age: age });
  };
  const updateSpouseCurrentAge = (age: number) => {
    updateCareerShock({ spouse_current_age: age });
  };
  useEffect(() => {
    const selfAge = ageYearsFromBirthMonth(careerShock.self_birth_month, today);
    const spouseAge = ageYearsFromBirthMonth(careerShock.spouse_birth_month, today);
    const patch: Partial<typeof defaultCareerShock> = {};
    if (selfAge !== null && selfAge !== careerShock.self_current_age) {
      patch.self_current_age = selfAge;
    }
    if (spouseAge !== null && spouseAge !== careerShock.spouse_current_age) {
      patch.spouse_current_age = spouseAge;
    }
    if (Object.keys(patch).length > 0) {
      updateCareerShock(patch);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [careerShock.self_birth_month, careerShock.spouse_birth_month]);
  useEffect(() => {
    if ((household.borrower_member_index ?? 0) !== normalizedBorrowerMemberIndex) {
      updateHousehold("borrower_member_index", normalizedBorrowerMemberIndex);
      return;
    }
    if ((household.borrower_age ?? 30) !== borrowerAgeForPolicy) {
      updateHousehold("borrower_age", borrowerAgeForPolicy);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedBorrowerMemberIndex, borrowerAgeForPolicy]);
  const layoffMonthOffset = monthsBetween(
    today,
    monthStartForBirthMonthOrAge(today, careerShock.self_birth_month, careerShock.self_current_age, careerShock.layoff_age)
  );
  const selfRetirementMonthOffset = monthsBetween(
    today,
    monthStartForBirthMonthOrAge(today, careerShock.self_birth_month, careerShock.self_current_age, careerShock.self_retirement_age)
  );
  const spouseRetirementMonthOffset = monthsBetween(
    today,
    monthStartForBirthMonthOrAge(today, careerShock.spouse_birth_month, careerShock.spouse_current_age, careerShock.spouse_retirement_age)
  );
  const layoffDate = formatMonthDate(today, layoffMonthOffset);
  const selfRetirementDate = formatMonthDate(today, selfRetirementMonthOffset);
  const spouseRetirementDate = formatMonthDate(today, spouseRetirementMonthOffset);
  const setupChecklist = [
    { label: "家庭成员与工资阶段", done: incomeMembers.some((member) => incomeStagesForMember(member).some((stage) => stage.monthly_salary_gross > 0 || stage.annual_bonus > 0)) },
    { label: "基础支出与定时支出", done: household.monthly_expense > 0 || scheduledExpenses.some((expense) => expense.monthly_amount > 0) },
    { label: "现金、投资和公积金余额", done: household.liquid_assets > 0 || household.investments > 0 || household.provident_fund_balance > 0 },
    { label: "目前贷款、老人扣除和职业冲击", done: phasedLoans.length > 0 || elderlyDependents.length > 0 || Boolean(household.career_shock?.enabled) },
  ];
  const memberIncomeSection = (
    <section className="form-panel">
      <div className="member-header">
        <PanelTitle icon={<Banknote size={18} />} title="成员收入" />
        <button className="ghost-button" onClick={addIncomeMember}>
          <Plus size={16} /> 新增成员
        </button>
      </div>
      <div className="member-list roomy">
        {incomeMembers.map((member, index) => (
          <section className="member-card" key={`member-${index}`}>
            <div className="member-card-head">
              <Field label="成员名称">
                <input
                  value={member.name}
                  onChange={(event) => updateIncomeMember(index, "name", event.target.value)}
                />
              </Field>
              <button
                className="icon-button"
                onClick={() => removeIncomeMember(index)}
                disabled={incomeMembers.length <= 1}
                title="删除成员"
              >
                <Trash2 size={15} />
              </button>
            </div>
            <div className="member-header compact-heading">
              <strong>收入阶段</strong>
              <button className="ghost-button" onClick={() => addIncomeStage(index)} type="button">
                <Plus size={15} /> 新增阶段
              </button>
            </div>
            <div className="stage-list">
              {incomeStagesForMember(member).map((stage, stageIndex) => (
                <section className="stage-row" key={`member-${index}-stage-${stageIndex}`}>
                  <div className="member-card-head">
                    <Field label="阶段名称">
                      <input
                        value={stage.name}
                        onChange={(event) => updateIncomeStage(index, stageIndex, "name", event.target.value)}
                      />
                    </Field>
                    <button
                      className="icon-button"
                      onClick={() => removeIncomeStage(index, stageIndex)}
                      disabled={incomeStagesForMember(member).length <= 1}
                      title="删除收入阶段"
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                  <div className="form-grid">
                    <Field label="开始日期">
                      <input
                        type="date"
                        value={stage.start_date}
                        onChange={(event) => updateIncomeStage(index, stageIndex, "start_date", event.target.value)}
                      />
                    </Field>
                    <Field label="结束日期">
                      <input
                        type="date"
                        value={stage.end_date ?? ""}
                        onChange={(event) => updateIncomeStage(index, stageIndex, "end_date", event.target.value || null)}
                      />
                    </Field>
                    <NumberField
                      label="月工资税前"
                      value={stage.monthly_salary_gross}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_salary_gross", value)}
                    />
                    <NumberField
                      label="年终奖年额"
                      value={stage.annual_bonus}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "annual_bonus", value)}
                    />
                    <NumberField
                      label="发放月份"
                      value={stage.annual_bonus_payout_month ?? 4}
                      min={1}
                      max={12}
                      step={1}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "annual_bonus_payout_month", Math.round(value))}
                    />
                    <NumberField
                      label="非税收入/月"
                      value={stage.monthly_non_taxable_income ?? 0}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_non_taxable_income", value)}
                    />
                    <NumberField
                      label="额外现金支出/月"
                      value={stage.monthly_extra_cash_expense ?? 0}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_extra_cash_expense", value)}
                    />
                    <label className="check-row inline-check">
                      <input
                        type="checkbox"
                        checked={stage.payroll_contributions_enabled ?? true}
                        onChange={(event) =>
                          updateIncomeStage(index, stageIndex, "payroll_contributions_enabled", event.target.checked)
                        }
                      />
                      工资社保扣缴
                    </label>
                    <NumberField
                      label="个人公积金比例"
                      value={stage.housing_fund_personal_rate ?? 0.12}
                      step={0.01}
                      min={0}
                      max={0.12}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "housing_fund_personal_rate", value)}
                    />
                    <NumberField
                      label="单位公积金比例"
                      value={stage.housing_fund_employer_rate ?? 0.12}
                      step={0.01}
                      min={0}
                      max={0.12}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "housing_fund_employer_rate", value)}
                    />
                    <NumberField
                      label="专项附加/月"
                      value={stage.monthly_special_additional_deduction}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "monthly_special_additional_deduction", value)}
                    />
                    <NumberField
                      label="其他年收入"
                      value={stage.other_annual_taxable_income}
                      min={0}
                      step={100}
                      onChange={(value) => updateIncomeStage(index, stageIndex, "other_annual_taxable_income", value)}
                    />
                    <Field label="年终奖计税">
                      <select
                        value={stage.bonus_tax_method}
                        onChange={(event) =>
                          updateIncomeStage(index, stageIndex, "bonus_tax_method", event.target.value as BonusTaxMethod)
                        }
                      >
                        <option value="best">自动择优</option>
                        <option value="separate">单独计税</option>
                        <option value="merged">并入综合所得</option>
                      </select>
                    </Field>
                  </div>
                </section>
              ))}
            </div>
            <p className="field-hint">
              默认只有一段收入；新增阶段后，后端会按各阶段实际生效月份折算税费、年终奖和公积金。五险按北京社保基数、个人养老 8%、医疗 2%+3、失业 0.5% 自动计算。
            </p>
          </section>
        ))}
      </div>
    </section>
  );

  const assetCashSection = (
    <section className="form-panel income-overview-panel">
      <PanelTitle icon={<ShieldCheck size={18} />} title="资产与现金流参数" />
      <div className="form-grid two">
        <NumberField
          label="当前可动用现金"
          value={household.liquid_assets}
          min={0}
          step={1000}
          onChange={(value) => updateHousehold("liquid_assets", value)}
        />
        <NumberField
          label="当前投资资产"
          value={household.investments}
          min={0}
          step={1000}
          onChange={(value) => updateHousehold("investments", value)}
        />
        <NumberField
          label="公积金余额"
          value={household.provident_fund_balance}
          min={0}
          step={1000}
          onChange={(value) => updateHousehold("provident_fund_balance", value)}
        />
        <NumberField
          label="租房提取公积金等效月额"
          value={household.monthly_rent_from_housing_fund ?? 0}
          min={0}
          step={100}
          onChange={(value) => updateHousehold("monthly_rent_from_housing_fund", value)}
        />
        <NumberField
          label="购后安全垫月数"
          value={household.required_liquidity_months ?? 6}
          step={1}
          min={0}
          max={36}
          onChange={(value) => updateHousehold("required_liquidity_months", value)}
        />
      </div>
      <div className="family-support-box">
        <label className="check-row inline-check">
          <input
            type="checkbox"
            checked={household.family_provident_support_enabled ?? false}
            onChange={(event) => updateHousehold("family_provident_support_enabled", event.target.checked)}
          />
          亲属首付支持
        </label>
        {household.family_provident_support_enabled ? (
          <div className="form-grid two">
            <Field label="支持情景名称">
              <input
                value={household.family_provident_support_label ?? (household.family_down_payment_support_mode === "savings" ? "亲属积蓄首付支持" : "亲属异地公积金首付支持")}
                onChange={(event) => updateHousehold("family_provident_support_label", event.target.value)}
              />
            </Field>
            <Field label="支持资金来源">
              <select
                value={household.family_down_payment_support_mode ?? "provident"}
                onChange={(event) => {
                  const mode = event.target.value as HouseholdData["family_down_payment_support_mode"];
                  updateHousehold("family_down_payment_support_mode", mode);
                  updateHousehold(
                    "family_provident_support_label",
                    mode === "savings" ? "亲属积蓄首付支持" : "亲属异地公积金首付支持"
                  );
                }}
              >
                <option value="savings">亲属积蓄支持</option>
                <option value="provident">亲属公积金支持</option>
              </select>
            </Field>
            {household.family_down_payment_support_mode === "savings" ? (
              <NumberField
                label="可支持首付金额"
                value={household.family_savings_support_amount ?? 0}
                min={0}
                step={1000}
                onChange={(value) => updateHousehold("family_savings_support_amount", value)}
              />
            ) : (
              <>
                <NumberField
                  label="支持账户当前余额"
                  value={household.family_provident_initial_balance ?? 0}
                  min={0}
                  step={1000}
                  onChange={(value) => updateHousehold("family_provident_initial_balance", value)}
                />
                <NumberField
                  label="支持账户月工资"
                  value={household.family_provident_monthly_salary ?? 0}
                  min={0}
                  step={100}
                  onChange={(value) => updateHousehold("family_provident_monthly_salary", value)}
                />
                <NumberField
                  label="支持账户双边比例"
                  value={household.family_provident_total_rate ?? 0.24}
                  min={0}
                  max={0.5}
                  step={0.01}
                  onChange={(value) => updateHousehold("family_provident_total_rate", value)}
                />
              </>
            )}
          </div>
        ) : null}
      </div>
      <p className="field-hint">
        当前可动用现金和当前投资资产是今天手动录入的资产快照；租房提取公积金按等效月额录入，但可视化和现金流按季度到账；亲属积蓄支持按可支持金额直接减少交易现金需求，亲属公积金支持仅在购买新房且开关启用时计入首付抵扣；购后安全垫月数 = 买房后希望至少保留的生活费月数。
      </p>
    </section>
  );

  return (
    <div className="page-stack income-page-stack">
      <SectionHeader icon={<ClipboardCheck size={20} />} title="家庭财务" />
      <section className="form-panel setup-guide">
        <PanelTitle icon={<Sparkles size={18} />} title="初始化指引" />
        <p className="field-hint">
          首次使用建议按下面顺序填写家庭画像、收入支出、资产负债和计划目标，完成后点击“保存本地”写入本机数据库。
        </p>
        <div className="setup-steps">
          {setupChecklist.map((item, index) => (
            <span className={item.done ? "setup-step done" : "setup-step"} key={item.label}>
              <CheckCircle2 size={15} />
              {index + 1}. {item.label}
            </span>
          ))}
        </div>
      </section>

      <div className="income-overview-grid">
      <section className="form-panel income-overview-panel">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="家庭画像" />
        <div className="form-grid income-profile-grid">
          <Field label="家庭名称">
            <input
              value={household.name}
              onChange={(event) => updateHousehold("name", event.target.value)}
            />
          </Field>
          <Metric label="成员组成" value={memberCompositionText} />
          <Metric label="成员年龄" value={memberAgeText} />
          <Metric label="赡养老人对象" value={`${elderlyDependents.length} 人`} />
          <Field label="借款申请人">
            <select
              value={normalizedBorrowerMemberIndex}
              onChange={(event) => updateHousehold("borrower_member_index", Number(event.target.value))}
            >
              {incomeMembers.map((member, index) => (
                <option key={`${member.name}-${index}`} value={index}>
                  {member.name || `成员 ${index + 1}`}
                </option>
              ))}
            </select>
          </Field>
          <Metric label="借款申请人年龄" value={`${borrowerAgeForPolicy} 岁，按${borrowerMemberName}自动同步`} />
          <NumberField
            label="子女数"
            value={household.child_count}
            min={0}
            max={10}
            step={1}
            onChange={(value) => updateHousehold("child_count", value)}
          />
          <label className="check-row inline-check">
            <input
              type="checkbox"
              checked={household.has_beijing_hukou}
              onChange={(event) => updateHousehold("has_beijing_hukou", event.target.checked)}
            />
            北京户籍家庭
          </label>
          <NumberField
            label="社保/个税月数"
            value={household.social_security_months}
            step={1}
            min={0}
            onChange={(value) => updateHousehold("social_security_months", value)}
          />
          <NumberField
            label="现有住房套数"
            value={household.existing_home_count}
            min={0}
            max={10}
            step={1}
            onChange={(value) => updateHousehold("existing_home_count", value)}
          />
          <NumberField
            label="现有房贷笔数"
            value={household.existing_mortgage_count}
            min={0}
            max={10}
            step={1}
            onChange={(value) => updateHousehold("existing_mortgage_count", value)}
          />
        </div>
        <p className="field-hint">
          家庭画像只放家庭成员、年龄、子女和购房资格相关信息；资产快照在右侧同步维护，收入、支出和负债在下方分区配置。
        </p>
      </section>
      {assetCashSection}
      </div>

      {memberIncomeSection}

      <div className="income-detail-grid">
      <section className="form-panel income-workbench-card expense-panel">
        <div className="member-header">
          <PanelTitle icon={<WalletCards size={18} />} title="家庭支出" />
          <button className="ghost-button" onClick={addScheduledExpense}>
            <Plus size={16} /> 新增定时支出
          </button>
        </div>
        <div className="loan-summary-strip">
          <Metric label="基础月支出" value={money(household.monthly_expense)} />
          <Metric label="当前实际月支出" value={money(currentMonthlyExpense)} />
          <Metric
            label="定时月支出"
            value={money(Math.max(0, currentMonthlyExpense - household.monthly_expense))}
          />
        </div>
        <div className="form-grid">
          <NumberField
            label="基础月支出"
            value={household.monthly_expense}
            min={0}
            step={100}
            onChange={(value) => updateHousehold("monthly_expense", value)}
          />
          <NumberField
            label="其他固定债务/月"
            value={household.monthly_debt_payment}
            min={0}
            step={100}
            onChange={(value) => updateHousehold("monthly_debt_payment", value)}
          />
        </div>
        <div className="member-list compact-list">
          {scheduledExpenses.map((expense, index) => (
            <section className="member-card loan-card" key={`scheduled-expense-${index}`}>
              <div className="member-card-head">
                <strong>{expense.name || "定时支出"}</strong>
                <button
                  className="icon-button"
                  onClick={() => removeScheduledExpense(index)}
                  aria-label="删除定时支出"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="form-grid">
                <Field label="支出名称">
                  <input
                    value={expense.name}
                    onChange={(event) => updateScheduledExpense(index, "name", event.target.value)}
                  />
                </Field>
                <NumberField
                  label="每月金额"
                  value={expense.monthly_amount}
                  min={0}
                  step={100}
                  onChange={(value) => updateScheduledExpense(index, "monthly_amount", value)}
                />
                <Field label="开始月份">
                  <input
                    type="month"
                    value={expense.start_month}
                    onChange={(event) => updateScheduledExpense(index, "start_month", event.target.value)}
                  />
                </Field>
                <Field label="结束月份">
                  <input
                    type="month"
                    value={expense.end_month ?? ""}
                    onChange={(event) => updateScheduledExpense(index, "end_month", event.target.value || null)}
                  />
                </Field>
                <Metric
                  label="养老专项扣除判断"
                  value={elderlyPolicyStatus.label}
                  tone={elderlyPolicyStatus.tone}
                />
                <Field label="备注">
                  <input
                    value={expense.notes}
                    onChange={(event) => updateScheduledExpense(index, "notes", event.target.value)}
                    placeholder="例如：仅为父母家里花销，不进入个税扣除"
                  />
                </Field>
              </div>
            </section>
          ))}
        </div>
        <p className="field-hint">
          基础月支出从现在起计入现金流；定时支出只在开始月份后计入。家庭支持支出本身只影响现金流；老人专项附加扣除由下方“父母老人专项扣除”的出生月份、归属成员和分摊方式自动判断，{elderlyPolicyStatus.detail}
        </p>
      </section>

      <section className="form-panel income-workbench-card career-panel">
        <PanelTitle icon={<AlertTriangle size={18} />} title="职业冲击与退休养老金" />
        <label className="check-row">
          <input
            type="checkbox"
            checked={careerShock.enabled}
            onChange={(event) => updateCareerShock({ enabled: event.target.checked })}
          />
          {careerShock.enabled ? "启用职业冲击压力情景" : "关闭职业冲击情景"}
        </label>
        <div className="loan-summary-strip">
          <Metric label="预计裁员月份" value={layoffDate} tone={careerShock.enabled ? "warn" : undefined} />
          <Metric label="第一成员退休月份" value={selfRetirementDate} />
          <Metric label="第二成员退休月份" value={spouseRetirementDate} />
        </div>
        <div className="form-grid">
          <Field label="被裁员成员">
            <select
              value={careerShock.layoff_member_name}
              onChange={(event) => updateCareerShock({ layoff_member_name: event.target.value })}
            >
              {incomeMembers.map((member) => (
                <option key={member.name} value={member.name}>
                  {member.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="第一成员出生年月">
            <input
              type="month"
              value={careerShock.self_birth_month ?? ""}
              onInput={(event) => updateSelfBirthMonth(event.currentTarget.value)}
              onChange={(event) => updateSelfBirthMonth(event.target.value)}
            />
          </Field>
          <Field label="第二成员出生年月">
            <input
              type="month"
              value={careerShock.spouse_birth_month ?? ""}
              onInput={(event) => updateSpouseBirthMonth(event.currentTarget.value)}
              onChange={(event) => updateSpouseBirthMonth(event.target.value)}
            />
          </Field>
          <AgeField label="第一成员当前年龄" value={displayedSelfCurrentAge} onChange={updateSelfCurrentAge} />
          <AgeField label="第二成员当前年龄" value={displayedSpouseCurrentAge} onChange={updateSpouseCurrentAge} />
          <NumberField label="裁员年龄" value={careerShock.layoff_age} min={18} max={80} step={1} onChange={(value) => updateCareerShock({ layoff_age: value })} />
          <label className="check-row inline-check">
            <input
              type="checkbox"
              checked={careerShock.auto_unemployment_benefit}
              onChange={(event) => updateCareerShock({ auto_unemployment_benefit: event.target.checked })}
            />
            自动估算失业保险待遇
          </label>
          <label className="check-row inline-check">
            <input
              type="checkbox"
              checked={careerShock.auto_self_social_insurance}
              onChange={(event) => updateCareerShock({ auto_self_social_insurance: event.target.checked })}
            />
            自动估算灵活就业自缴
          </label>
          {careerShock.auto_unemployment_benefit ? (
            <>
              <Metric label="估算失业金月数" value={`${estimatedUnemploymentBenefitMonths} 个月`} />
              <Metric
                label="估算失业金月额"
                value={
                  estimatedUnemploymentBenefitMonths > 12
                    ? `${money(estimatedUnemploymentBenefitMonthly)} / ${money(estimatedLaterUnemploymentBenefitMonthly)}`
                    : money(estimatedUnemploymentBenefitMonthly)
                }
              />
            </>
          ) : (
            <>
              <NumberField label="失业金月数" value={careerShock.unemployment_benefit_months} min={0} max={24} step={1} onChange={(value) => updateCareerShock({ unemployment_benefit_months: value })} />
              <NumberField label="失业金月额" value={careerShock.unemployment_benefit_monthly} min={0} step={100} onChange={(value) => updateCareerShock({ unemployment_benefit_monthly: value })} />
            </>
          )}
          {careerShock.auto_self_social_insurance ? (
            <Metric label="估算自缴社保/月" value={money(estimatedSelfSocialInsuranceMonthly)} />
          ) : (
            <NumberField label="自缴社保/月" value={careerShock.self_social_insurance_monthly} min={0} step={100} onChange={(value) => updateCareerShock({ self_social_insurance_monthly: value })} />
          )}
          <NumberField label="第一成员退休年龄" value={careerShock.self_retirement_age} min={50} max={70} step={1} onChange={(value) => updateCareerShock({ self_retirement_age: value })} />
          <NumberField label="第二成员退休年龄" value={careerShock.spouse_retirement_age} min={50} max={70} step={1} onChange={(value) => updateCareerShock({ spouse_retirement_age: value })} />
          <NumberField label="第一成员养老金/月" value={careerShock.self_pension_monthly} min={0} step={500} onChange={(value) => updateCareerShock({ self_pension_monthly: value })} />
          <NumberField label="第二成员养老金/月" value={careerShock.spouse_pension_monthly} min={0} step={500} onChange={(value) => updateCareerShock({ spouse_pension_monthly: value })} />
        </div>
        <p className="field-hint">
          该情景会自动生成收入阶段：被裁员成员在设定年龄后先进入失业金期，之后到退休前按灵活就业自缴社保；其他成员只会在退休年龄后切换为养老金收入。自动估算依赖家庭画像里的累计社保/个税月数和政策规则页参数，真实申领仍需满足非本人意愿中断就业、失业登记等条件。
        </p>
      </section>

      <section className="form-panel income-workbench-card elderly-panel">
        <div className="member-header">
          <PanelTitle icon={<ShieldCheck size={18} />} title="父母老人专项扣除" />
          <button className="ghost-button" onClick={addElderlyDependent}>
            <Plus size={16} /> 新增老人
          </button>
        </div>
        <div className="member-list compact-list">
          {elderlyDependents.map((dependent, index) => {
            const startMonth = elderlyDeductionStartMonth(dependent);
            const monthlyDeduction = dependent.is_only_child
              ? 3000
              : Math.min(Math.max(0, dependent.shared_monthly_deduction ?? 1500), 1500);
            return (
              <section className="member-card loan-card" key={`elderly-dependent-${index}`}>
                <div className="member-card-head">
                  <strong>{dependent.relationship_label || "直系亲属老人"}</strong>
                  <button
                    className="icon-button"
                    onClick={() => removeElderlyDependent(index)}
                    aria-label="删除老人"
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="form-grid">
                  <Field label="归属成员">
                    <select
                      value={dependent.member_name}
                      onChange={(event) => updateElderlyDependent(index, "member_name", event.target.value)}
                    >
                      {incomeMembers.map((member) => (
                        <option key={member.name} value={member.name}>
                          {member.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="称谓">
                    <input
                      value={dependent.relationship_label}
                      onChange={(event) => updateElderlyDependent(index, "relationship_label", event.target.value)}
                    />
                  </Field>
                  <Field label="出生月份">
                    <input
                      type="month"
                      value={dependent.birth_month}
                      onChange={(event) => updateElderlyDependent(index, "birth_month", event.target.value)}
                    />
                  </Field>
                  <Metric label="当前年龄" value={formatAgeFromBirthMonth(dependent.birth_month)} />
                  <label className="check-row inline-check">
                    <input
                      type="checkbox"
                      checked={dependent.is_only_child}
                      onChange={(event) => updateElderlyDependent(index, "is_only_child", event.target.checked)}
                    />
                    独生子女
                  </label>
                  <NumberField
                    label="本人分摊扣除"
                    value={dependent.shared_monthly_deduction ?? 1500}
                    min={0}
                    max={3000}
                    step={100}
                    onChange={(value) => updateElderlyDependent(index, "shared_monthly_deduction", value)}
                  />
                  <Metric
                    label="预计生效"
                    value={startMonth ? `${startMonth.year}年${startMonth.month}月` : "待填写"}
                    tone={startMonth ? "good" : "warn"}
                  />
                  <Metric label="月扣除额" value={money(monthlyDeduction)} />
                </div>
              </section>
            );
          })}
        </div>
        <p className="field-hint">
          老人从年满 60 周岁的当月开始满足赡养老人专项附加扣除条件。常见用法：独生子女由对应成员每月扣 3000；非独生子女在兄弟姐妹间分摊 3000，当前成员尽量按本人上限 1500 申报。扣除归属应按真实亲属关系和政策口径填写。
        </p>
      </section>

      <section className="form-panel income-workbench-card current-loans-panel income-span-full">
        <div className="member-header">
          <PanelTitle icon={<WalletCards size={18} />} title="目前贷款" />
          <button className="ghost-button" onClick={addPhasedLoan}>
            <Plus size={16} /> 新增贷款
          </button>
        </div>
        <div className="loan-summary-strip">
          <Metric label="目前贷款笔数" value={`${phasedLoans.length} 笔`} tone={phasedLoans.length > 0 ? "good" : undefined} />
          <Metric label="当前阶段分布" value={phasedLoanSummaryText} />
          <Metric label="目前贷款本月应还" value={money(result?.phased_loan_monthly_payment ?? 0)} />
          <Metric label="计入测算的月债务" value={money(result?.effective_monthly_debt_payment ?? household.monthly_debt_payment)} />
        </div>
        <div className="member-list compact-list">
          {phasedLoans.map((loan, index) => {
            const summary = result?.phased_loan_summaries?.[index];
            return (
              <section className="member-card loan-card" key={`phased-loan-${index}`}>
                <div className="member-card-head">
                  <strong>{index + 1}. {loan.name || "目前贷款"} · {existingLoanTypeLabels[loan.loan_type ?? "other"]} · {summary?.phase ?? "待计算"}</strong>
                  <button
                    className="icon-button"
                    onClick={() => removePhasedLoan(index)}
                    aria-label="删除目前贷款"
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="form-grid">
                  <Field label="借款人">
                    <input
                      value={loan.borrower}
                      onChange={(event) => updatePhasedLoan(index, "borrower", event.target.value)}
                    />
                  </Field>
                  <Field label="贷款名称">
                    <input
                      value={loan.name}
                      onChange={(event) => updatePhasedLoan(index, "name", event.target.value)}
                    />
                  </Field>
                  <Field label="贷款类型">
                    <select
                      value={loan.loan_type ?? "other"}
                      onChange={(event) =>
                        updatePhasedLoan(index, "loan_type", event.target.value as NonNullable<PhasedLoanData["loan_type"]>)
                      }
                    >
                      <option value="mortgage">房贷</option>
                      <option value="car">车贷</option>
                      <option value="education">教育贷款</option>
                      <option value="consumer">消费贷款</option>
                      <option value="other">其他贷款</option>
                    </select>
                  </Field>
                  <NumberField
                    label="本金"
                    value={loan.principal}
                    min={0}
                    step={1000}
                    onChange={(value) => updatePhasedLoan(index, "principal", value)}
                  />
                  <NumberField
                    label="年利率"
                    value={loan.annual_rate}
                    min={0}
                    max={0.2}
                    step={0.0005}
                    onChange={(value) => updatePhasedLoan(index, "annual_rate", value)}
                  />
                  <Field label="还款方式">
                    <select
                      value={loan.repayment_method ?? "equal_installment"}
                      onChange={(event) =>
                        updatePhasedLoan(index, "repayment_method", event.target.value as RepaymentMethod)
                      }
                    >
                      <option value="equal_installment">等额本息</option>
                      <option value="equal_principal">等额本金</option>
                    </select>
                  </Field>
                  <NumberField
                    label="剩余期数"
                    value={loan.remaining_months}
                    min={1}
                    max={360}
                    step={1}
                    onChange={(value) => updatePhasedLoan(index, "remaining_months", value)}
                  />
                  <Field label="计息开始月">
                    <input
                      value={loan.interest_start_month}
                      onChange={(event) => updatePhasedLoan(index, "interest_start_month", event.target.value)}
                      placeholder="2026-07"
                    />
                  </Field>
                  <Field label="只还利息至">
                    <input
                      value={loan.interest_only_until}
                      onChange={(event) => updatePhasedLoan(index, "interest_only_until", event.target.value)}
                      placeholder="2028-07"
                    />
                  </Field>
                  <Metric label="当前月供" value={money(summary?.current_monthly_payment ?? 0)} />
                  <Metric
                    label="还款方式"
                    value={repaymentMethodLabels[summary?.repayment_method ?? loan.repayment_method ?? "equal_installment"]}
                  />
                </div>
              </section>
            );
          })}
        </div>
        <p className="field-hint">
          “其他固定债务/月”适合没有本金、利率或还款阶段明细的普通月债务；目前贷款适合已有房贷、车贷、消费贷、教育贷款等可建模账户。若某笔贷款有“到某月前只还利息、之后等额本息/等额本金”的安排，可填写“计息开始月”和“只还利息至”，后端会按当前日期自动折算本月应还，并额外计入有效月债务。
        </p>
      </section>
      </div>
    </div>
  );
}

function InvestmentPlanPage({
  household,
  scenario,
  result,
  updateHousehold,
  updateScenario
}: {
  household: HouseholdData;
  scenario: ScenarioData;
  result: AffordabilityResult | null;
  updateHousehold: <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => void;
  updateScenario: <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => void;
}) {
  const recommendations = useMemo(
    () => buildInvestmentPlanRecommendations(household, scenario, result),
    [household, result, scenario]
  );
  const recommendedInvestment = recommendations[0];
  const netIncome = result?.household_net_monthly_income ?? household.monthly_income;
  const effectiveDebt = result?.effective_monthly_debt_payment ?? household.monthly_debt_payment;
  const carPurchasedNow =
    Boolean(result && household.car_plan.enabled && result.car_loan.enabled && result.car_loan.purchase_delay_months <= 0);
  const carMonthlyCashCost =
    result && carPurchasedNow
      ? result.car_loan.current_monthly_payment + result.car_loan.monthly_cash_operating_cost
      : Math.max(0, household.car_plan.no_car_monthly_commute_cost ?? 0);
  const currentMonthlyExpense = householdExpenseAt(household, new Date(), 0);
  const monthlySurplus = Math.max(0, netIncome - currentMonthlyExpense - effectiveDebt - carMonthlyCashCost);
  const reserveTarget = currentMonthlyExpense * (household.investment_cash_reserve_months ?? 6);
  const reserveGap = Math.max(0, reserveTarget - household.liquid_assets);
  const currentInvestmentAllocation = calculateMonthlyInvestmentAllocation({
    monthlySurplus,
    cashValue: household.liquid_assets,
    reserveTarget,
    monthlyInvestmentSetting: household.investment_plan_name === "cash_only" ? 0 : household.monthly_investment_amount ?? 0,
    autoRebalance: household.investment_auto_rebalance ?? true
  });
  const manualRecommendation: InvestmentPlanRecommendation = {
    variant: "手动指定",
    planName: "manual_investment",
    riskLevel: household.investment_risk_level ?? "conservative",
    riskLabel: investmentRiskLabels[household.investment_risk_level ?? "conservative"] ?? "自定义",
    description: "按上方手动填写的月定投、现金安全垫、资产比例和年化收益测算。",
    monthlyInvestment: household.monthly_investment_amount ?? 0,
    annualReturn: scenario.annual_investment_return ?? 0,
    cashReserveMonths: household.investment_cash_reserve_months ?? 6,
    equityRatio: household.investment_equity_ratio ?? 0.25,
    bondRatio: household.investment_bond_ratio ?? 0.45,
    cashRatio: household.investment_cash_ratio ?? 0.3,
    score: Math.round(Math.max(0, Math.min(100, 72 + (reserveGap > 0 ? -8 : 8) + (monthlySurplus > 0 ? 6 : -10)))),
    reasons: [
      `使用当前已设定投 ${money(household.monthly_investment_amount ?? 0)}/月`,
      `现金安全垫按 ${household.investment_cash_reserve_months ?? 6} 个月支出控制`,
      `目标配置：权益 ${percent(household.investment_equity_ratio ?? 0.25)}、固收 ${percent(household.investment_bond_ratio ?? 0.45)}、现金 ${percent(household.investment_cash_ratio ?? 0.3)}`
    ]
  };
  const displayedRecommendations = [manualRecommendation, ...recommendations];
  const activeRecommendation =
    displayedRecommendations.find((item) => item.planName === household.investment_plan_name) ?? manualRecommendation;
  const investmentReasonText =
    (recommendedInvestment?.monthlyInvestment ?? 0) > 0
      ? `系统建议先保留现金安全垫 ${money(reserveTarget)}；现金垫不足时先补现金，现金垫超额时把超额现金分 12 个月滚入定投。当前最高分方案建议 ${money(recommendedInvestment?.monthlyInvestment ?? 0)}/月。`
      : reserveGap > 0
        ? `系统建议月定投为 0，是因为现金安全垫还差 ${money(reserveGap)}，当前月结余会优先补足现金池和购房首付，不先进入波动资产。`
        : "系统建议月定投为 0，是因为当前最高分方案选择了“暂停定投保现金”；可在下方采用稳健/均衡/进取方案后再手动微调。";
  const allocationData = [
    { name: "权益", 比例: Math.round((household.investment_equity_ratio ?? 0.25) * 100) },
    { name: "固收", 比例: Math.round((household.investment_bond_ratio ?? 0.45) * 100) },
    { name: "现金", 比例: Math.round((household.investment_cash_ratio ?? 0.3) * 100) }
  ];
  const applyInvestmentPlan = (plan: InvestmentPlanRecommendation) => {
    updateHousehold("investment_plan_name", plan.planName);
    updateHousehold("investment_risk_level", plan.riskLevel);
    updateHousehold("monthly_investment_amount", plan.monthlyInvestment);
    updateHousehold("investment_cash_reserve_months", plan.cashReserveMonths);
    updateHousehold("investment_equity_ratio", plan.equityRatio);
    updateHousehold("investment_bond_ratio", plan.bondRatio);
    updateHousehold("investment_cash_ratio", plan.cashRatio);
    updateHousehold("investment_auto_rebalance", true);
    updateScenario("annual_investment_return", plan.annualReturn);
  };
  const updateManualInvestmentHousehold = <K extends keyof HouseholdData>(key: K, value: HouseholdData[K]) => {
    updateHousehold("investment_plan_name", "manual_investment");
    updateHousehold(key, value);
  };
  const updateManualInvestmentScenario = <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => {
    updateHousehold("investment_plan_name", "manual_investment");
    updateScenario(key, value);
  };

  return (
    <div className="page-stack">
      <SectionHeader icon={<TrendingUp size={20} />} title="理财计划" />
      <section className="result-panel investment-dashboard">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Sparkles size={18} />} title="自动管理概览" compact />
          <span>用于购房测算的年化和资产增长口径，不代表具体产品建议</span>
        </div>
        <div className="metric-grid">
          <Metric label="当前投资资产" value={money(household.investments)} />
          <Metric label="系统建议月定投" value={money(recommendedInvestment?.monthlyInvestment ?? 0)} />
          <Metric label="当前已设定投" value={money(household.monthly_investment_amount ?? 0)} />
          <Metric label="当前月结余" value={money(monthlySurplus)} tone={monthlySurplus > 0 ? "good" : "bad"} />
          <Metric label="现金安全垫目标" value={money(reserveTarget)} />
          <Metric label="安全垫缺口" value={money(reserveGap)} tone={reserveGap > 0 ? "warn" : "good"} />
          <Metric label="超额现金滚入" value={money(currentInvestmentAllocation.cashSweepInvestment)} tone={currentInvestmentAllocation.cashSweepInvestment > 0 ? "good" : undefined} />
          <Metric label="测算年化" value={percent(household.investment_plan_name === "cash_only" ? 0 : scenario.annual_investment_return ?? 0)} />
        </div>
        <p className="field-hint investment-explain">{investmentReasonText}</p>
        <div className="investment-layout">
          <section className="investment-settings">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="手动参数" compact />
            <div className="form-grid two">
              <Field label="理财计划">
                <select
                  value={household.investment_plan_name ?? "conservative_monthly_investment"}
                  onChange={(event) => updateHousehold("investment_plan_name", event.target.value)}
                >
                  {investmentPlanOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="风险类型">
                <select
                  value={household.investment_risk_level ?? "conservative"}
                  onChange={(event) => updateManualInvestmentHousehold("investment_risk_level", event.target.value)}
                >
                  {Object.entries(investmentRiskLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <NumberField label="每月定投" value={household.monthly_investment_amount ?? 0} min={0} step={100} onChange={(value) => updateManualInvestmentHousehold("monthly_investment_amount", value)} />
              <NumberField label="现金安全垫月数" value={household.investment_cash_reserve_months ?? 6} min={0} max={36} step={1} onChange={(value) => updateManualInvestmentHousehold("investment_cash_reserve_months", value)} />
              <NumberField label="权益比例" value={household.investment_equity_ratio ?? 0.25} min={0} max={1} step={0.05} onChange={(value) => updateManualInvestmentHousehold("investment_equity_ratio", value)} />
              <NumberField label="固收比例" value={household.investment_bond_ratio ?? 0.45} min={0} max={1} step={0.05} onChange={(value) => updateManualInvestmentHousehold("investment_bond_ratio", value)} />
              <NumberField label="现金比例" value={household.investment_cash_ratio ?? 0.3} min={0} max={1} step={0.05} onChange={(value) => updateManualInvestmentHousehold("investment_cash_ratio", value)} />
              <NumberField label="测算年化" value={scenario.annual_investment_return ?? 0.025} min={-0.5} max={0.5} step={0.001} onChange={(value) => updateManualInvestmentScenario("annual_investment_return", value)} />
              <NumberField label="买入手续费率" value={household.investment_buy_fee_rate ?? 0.0015} min={0} max={0.05} step={0.0005} onChange={(value) => updateManualInvestmentHousehold("investment_buy_fee_rate", value)} />
              <NumberField label="卖出手续费率" value={household.investment_sell_fee_rate ?? 0.005} min={0} max={0.05} step={0.0005} onChange={(value) => updateManualInvestmentHousehold("investment_sell_fee_rate", value)} />
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={household.investment_auto_rebalance ?? true}
                onChange={(event) => updateManualInvestmentHousehold("investment_auto_rebalance", event.target.checked)}
              />
              自动再平衡：现金垫不足时暂停定投，现金垫达标后按目标比例恢复
            </label>
            <p className="field-hint">
              达到现金安全垫后，系统会把超额现金分 12 个月追加到定投；买入手续费从定投资金里扣除，理财收益留在投资资产里继续复利，买房变现时再扣卖出手续费。
            </p>
          </section>
          <section className="investment-allocation">
            <PanelTitle icon={<Gauge size={18} />} title="目标配置" compact />
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={allocationData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} width={42} />
                <Tooltip formatter={(value) => `${Number(value).toFixed(0)}%`} />
                <Bar dataKey="比例" fill="#3d6fb6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="investment-rule-list">
              <Row label="安全垫规则" value={reserveGap > 0 ? "先补现金" : "允许定投"} />
              <Row label="基础定投" value={money(currentInvestmentAllocation.baseInvestment)} />
              <Row label="超额现金追加" value={money(currentInvestmentAllocation.cashSweepInvestment)} />
              <Row label="实际本月定投" value={money(currentInvestmentAllocation.totalInvestment)} />
              <Row label="买入手续费率" value={percent(household.investment_buy_fee_rate ?? 0.0015)} />
              <Row label="卖出手续费率" value={percent(household.investment_sell_fee_rate ?? 0.005)} />
              <Row label="月定投占结余" value={monthlySurplus > 0 ? percent(currentInvestmentAllocation.totalInvestment / monthlySurplus) : "0.0%"} />
              <Row label="当前采用" value={activeRecommendation?.variant ?? "手动设置"} />
            </div>
          </section>
        </div>
      </section>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Target size={18} />} title="理财策略方案" compact />
          <span>包含手动指定和自动生成方案，采用后会影响可视化里的资产曲线</span>
        </div>
        <div className="strategy-grid">
          {displayedRecommendations.map((plan) => {
            const active = household.investment_plan_name === plan.planName;
            return (
              <article className={`strategy-card investment-card ${active ? "active" : ""}`} key={plan.variant}>
                <div className="strategy-card-head">
                  <strong>{plan.variant}</strong>
                  <span>{plan.score} 分</span>
                </div>
                <p>{plan.description}</p>
                <ul className="strategy-explain-list">
                  {investmentStrategyDetails(plan.variant).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <div className="strategy-metrics">
                  <Metric label="月定投" value={money(plan.monthlyInvestment)} />
                  <Metric label="测算年化" value={percent(plan.annualReturn)} />
                  <Metric label="风险类型" value={plan.riskLabel} />
                  <Metric label="现金垫" value={`${plan.cashReserveMonths} 个月`} />
                </div>
                <div className="investment-ratio-row">
                  <span style={{ width: `${plan.equityRatio * 100}%` }} />
                  <span style={{ width: `${plan.bondRatio * 100}%` }} />
                  <span style={{ width: `${plan.cashRatio * 100}%` }} />
                </div>
                <p className="strategy-note">{plan.reasons.join("；")}</p>
                <button
                  type="button"
                  className={active ? "ghost-button" : "primary-button"}
                  onClick={() => applyInvestmentPlan(plan)}
                >
                  {active ? <CheckCircle2 size={16} /> : <Sparkles size={16} />}
                  {active ? "当前采用" : "采用方案"}
                </button>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function ScenarioPage({
  scenarios,
  selectedScenario,
  setSelectedScenarioId,
  updateScenario,
  addScenario,
  result,
  scenarioComparisons,
  selectedPlanVariant,
  setSelectedPlanVariant,
  calculationPending
}: {
  scenarios: RecordEnvelope<ScenarioData>[];
  selectedScenario: RecordEnvelope<ScenarioData>;
  setSelectedScenarioId: (id: string) => void;
  updateScenario: <K extends keyof ScenarioData>(key: K, value: ScenarioData[K]) => void;
  addScenario: () => void;
  result: AffordabilityResult | null;
  scenarioComparisons: ScenarioComparison[];
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  calculationPending: boolean;
}) {
  const generatedPlans = result?.purchase_plan_analyses ?? [];
  const recommendations = useMemo(
    () => buildStrategyRecommendations(generatedPlans, selectedScenario.data),
    [generatedPlans, selectedScenario.data]
  );
  const recommended = recommendations[0] ?? null;
  const selectedPlan =
    generatedPlans.find((plan) => plan.variant === selectedPlanVariant) ??
    recommended?.plan ??
    generatedPlans[0] ??
    null;
  const recommendationByVariant = useMemo(
    () => new Map(recommendations.map((item) => [item.plan.variant, item])),
    [recommendations]
  );

  return (
    <div className="page-stack strategy-workbench">
      <SectionHeader
        icon={<Target size={20} />}
        title="策略制定"
        action={
          <button className="ghost-button" onClick={addScenario}>
            <Plus size={16} /> 新增方案
          </button>
        }
      />

      <section className="strategy-hero">
        <div className="strategy-hero-main">
          <PanelTitle icon={<Sparkles size={18} />} title="自动推荐" compact />
          {recommended ? (
            <>
              <div className="recommend-title">
                <h3>{recommended.plan.variant}</h3>
                <span>{recommended.score} 分</span>
              </div>
              <p>{recommended.plan.description}</p>
              <button
                className="primary-button recommend-action"
                onClick={() => setSelectedPlanVariant(recommended.plan.variant)}
              >
                <Sparkles size={16} /> 查看推荐策略
              </button>
              <div className="recommend-reasons">
                {recommended.reasons.slice(0, 3).map((reason) => (
                  <span key={reason}>{reason}</span>
                ))}
              </div>
            </>
          ) : (
            <p>{calculationPending ? "正在按最新条件重新生成推荐策略。" : "调整购房目标后会自动生成推荐策略。"}</p>
          )}
        </div>
        <div className="strategy-hero-side">
          <Metric
            label="目标总价"
            value={money(selectedScenario.data.total_price)}
          />
          <Metric
            label="选中策略"
            value={selectedPlan?.variant ?? "待生成"}
            tone={selectedPlan?.liquidity_ok ? "good" : "warn"}
          />
          <Metric
            label="预计买入"
            value={selectedPlan?.years_to_buy === null ? "暂不可达" : `${selectedPlan?.years_to_buy ?? "-"} 年`}
          />
        </div>
      </section>

      <div className="strategy-layout">
        <aside className="strategy-side-panel">
          <PanelTitle icon={<Home size={18} />} title="目标房源" compact />
          <div className="scenario-tabs compact-tabs">
            {scenarios.map((item) => (
              <button
                key={item.id}
                className={item.id === selectedScenario.id ? "tab active" : "tab"}
                onClick={() => setSelectedScenarioId(item.id)}
              >
                <span>{item.data.name}</span>
                <strong>{money(item.data.total_price)}</strong>
              </button>
            ))}
          </div>
          <div className="side-form">
            <Field label="方案名称">
              <input
                value={selectedScenario.data.name}
                onChange={(event) => updateScenario("name", event.target.value)}
              />
            </Field>
            <Field label="区域">
              <input
                value={selectedScenario.data.district}
                onChange={(event) => updateScenario("district", event.target.value)}
              />
            </Field>
            <Field label="环线">
              <input
                value={selectedScenario.data.ring_area}
                onChange={(event) => updateScenario("ring_area", event.target.value)}
              />
            </Field>
            <Field label="房屋性质">
              <select
                value={selectedScenario.data.property_type}
                onChange={(event) => updateScenario("property_type", event.target.value)}
              >
                <option value="二手房">二手房</option>
                <option value="新房">新房</option>
                <option value="共有产权房">共有产权房</option>
                <option value="其他">其他</option>
              </select>
            </Field>
            <NumberField
              label="二手房房龄"
              value={selectedScenario.data.building_age_years ?? 0}
              min={0}
              max={100}
              step={1}
              onChange={(value) => updateScenario("building_age_years", value)}
            />
            <Field label="建筑结构">
              <select
                value={selectedScenario.data.building_structure ?? "unknown"}
                onChange={(event) => updateScenario("building_structure", event.target.value as ScenarioData["building_structure"])}
              >
                <option value="unknown">未知（按砖混保守测算）</option>
                <option value="brick_mixed">砖混结构</option>
                <option value="steel_concrete">钢混结构</option>
              </select>
            </Field>
            <label className="check-row inline-check">
              <input
                type="checkbox"
                checked={selectedScenario.data.is_old_community_renovated ?? false}
                onChange={(event) => updateScenario("is_old_community_renovated", event.target.checked)}
              />
              已完成老旧小区改造
            </label>
            <NumberField
              label="剩余土地年限"
              value={selectedScenario.data.remaining_land_use_years ?? 70}
              min={0}
              max={70}
              step={1}
              onChange={(value) => updateScenario("remaining_land_use_years", value)}
            />
            <Field label="绿色建筑">
              <select
                value={selectedScenario.data.green_building_level ?? "none"}
                onChange={(event) => updateScenario("green_building_level", event.target.value as ScenarioData["green_building_level"])}
              >
                <option value="none">不适用</option>
                <option value="two_star">二星绿色建筑</option>
                <option value="three_star">三星绿色建筑</option>
              </select>
            </Field>
            <Field label="装配式等级">
              <select
                value={selectedScenario.data.prefab_building_level ?? "none"}
                onChange={(event) => updateScenario("prefab_building_level", event.target.value as ScenarioData["prefab_building_level"])}
              >
                <option value="none">不适用</option>
                <option value="A">A</option>
                <option value="AA">AA</option>
                <option value="AAA">AAA</option>
              </select>
            </Field>
            <label className="check-row inline-check">
              <input
                type="checkbox"
                checked={selectedScenario.data.is_ultra_low_energy_building ?? false}
                onChange={(event) => updateScenario("is_ultra_low_energy_building", event.target.checked)}
              />
              超低能耗建筑
            </label>
            <NumberField label="目标总价" value={selectedScenario.data.total_price} min={0} step={10000} onChange={(value) => updateScenario("total_price", value)} />
            <NumberField label="建筑面积" value={selectedScenario.data.area_sqm} min={0} step={1} onChange={(value) => updateScenario("area_sqm", value)} />
            <NumberField label="贷款年限" value={selectedScenario.data.loan_years} min={1} max={30} step={1} onChange={(value) => updateScenario("loan_years", value)} />
            <Field label="商贷还款">
              <select
                value={selectedScenario.data.commercial_repayment_method ?? selectedScenario.data.repayment_method}
                onChange={(event) =>
                  updateScenario("commercial_repayment_method", event.target.value as RepaymentMethod)
                }
              >
                <option value="equal_installment">等额本息</option>
                <option value="equal_principal">等额本金</option>
              </select>
            </Field>
            <Field label="公积金还款">
              <select
                value={selectedScenario.data.provident_repayment_method ?? selectedScenario.data.repayment_method}
                onChange={(event) =>
                  updateScenario("provident_repayment_method", event.target.value as RepaymentMethod)
                }
              >
                <option value="equal_installment">等额本息</option>
                <option value="equal_principal">等额本金</option>
              </select>
            </Field>
          </div>
        </aside>

        <section className="strategy-main-panel">
          <div className="strategy-panel-head">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="手动调整策略参数" compact />
            <span>修改后会自动重算推荐、贷款结构和现金流</span>
          </div>
          <div className="adjustment-grid">
            <NumberField label="手动首付" value={selectedScenario.data.down_payment_amount} min={0} step={10000} onChange={(value) => updateScenario("down_payment_amount", value)} />
            <NumberField label="手动商贷" value={selectedScenario.data.commercial_loan_amount} min={0} step={10000} onChange={(value) => updateScenario("commercial_loan_amount", value)} />
            <NumberField label="手动公积金贷" value={selectedScenario.data.provident_loan_amount} min={0} step={10000} onChange={(value) => updateScenario("provident_loan_amount", value)} />
            <NumberField
              label="手动买入延后月数"
              value={selectedScenario.data.manual_purchase_delay_months ?? 0}
              min={0}
              max={360}
              step={1}
              onChange={(value) => updateScenario("manual_purchase_delay_months", value)}
            />
            <NumberField label="微量商贷手动比例" value={selectedScenario.data.micro_commercial_loan_ratio ?? 0} min={0} max={1} step={0.01} onChange={(value) => updateScenario("micro_commercial_loan_ratio", value)} />
            <NumberField label="商贷利率" value={selectedScenario.data.commercial_rate} min={0} max={0.2} step={0.0005} onChange={(value) => updateScenario("commercial_rate", value)} />
            <NumberField label="公积金利率" value={selectedScenario.data.provident_rate} min={0} max={0.2} step={0.0005} onChange={(value) => updateScenario("provident_rate", value)} />
            <NumberField label="契税比例" value={selectedScenario.data.deed_tax_rate} min={0} max={0.2} step={0.001} onChange={(value) => updateScenario("deed_tax_rate", value)} />
            <NumberField label="中介费比例" value={selectedScenario.data.broker_fee_rate} min={0} max={0.2} step={0.001} onChange={(value) => updateScenario("broker_fee_rate", value)} />
            <NumberField label="装修预算" value={selectedScenario.data.renovation_cost} min={0} step={10000} onChange={(value) => updateScenario("renovation_cost", value)} />
            <Field label="装修资金">
              <select
                value={selectedScenario.data.renovation_funding_mode ?? "after_purchase_saving"}
                onChange={(event) =>
                  updateScenario("renovation_funding_mode", event.target.value as RenovationFundingMode)
                }
              >
                <option value="after_purchase_saving">买后攒钱装修</option>
                <option value="upfront_cash">交易前准备装修款</option>
              </select>
            </Field>
            <NumberField label="搬家杂费" value={selectedScenario.data.moving_and_misc_cost} min={0} step={1000} onChange={(value) => updateScenario("moving_and_misc_cost", value)} />
            <NumberField label="理财年化" value={selectedScenario.data.annual_investment_return ?? 0.025} min={-0.5} max={0.5} step={0.001} onChange={(value) => updateScenario("annual_investment_return", value)} />
            <NumberField label="居住幸福度" value={selectedScenario.data.happiness_score ?? 7} min={0} max={10} step={0.5} onChange={(value) => updateScenario("happiness_score", value)} />
            <NumberField label="通勤评分" value={selectedScenario.data.commute_score ?? 7} min={0} max={10} step={0.5} onChange={(value) => updateScenario("commute_score", value)} />
            <NumberField label="教育评分" value={selectedScenario.data.school_score ?? 6} min={0} max={10} step={0.5} onChange={(value) => updateScenario("school_score", value)} />
            <NumberField label="流动性偏好" value={selectedScenario.data.liquidity_priority_score ?? 7} min={0} max={10} step={0.5} onChange={(value) => updateScenario("liquidity_priority_score", value)} />
          </div>
          <p className="field-hint">
            手动买入延后月数只作用于“手动指定”策略，系统会从该月份开始校验现金安全；微量商贷手动比例填 0 时由系统在政策规则上下限内自动寻找更早可买且商贷尽量少的比例，填入比例后按该比例固定测算。
          </p>
        </section>
      </div>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Home size={18} />} title="房源对比" compact />
          <span>按每个目标房源当前选中的策略比较</span>
        </div>
        {scenarioComparisons.length ? (
          <div className="comparison-table">
            <div className="comparison-row comparison-head">
              <span>房源</span>
              <span>当前策略</span>
              <span>可买时间</span>
              <span>交易现金</span>
              <span>买后自由月结余</span>
              <span>幸福指数</span>
            </div>
            {scenarioComparisons.map(({ scenario, selectedPlan: plan }) => {
              const stressShortfall = Math.max(0, plan?.cash_stress_shortfall ?? 0);
              return (
                <button
                  type="button"
                  className={scenario.id === selectedScenario.id ? "comparison-row active" : "comparison-row"}
                  key={scenario.id}
                  onClick={() => setSelectedScenarioId(scenario.id)}
                >
                  <span>
                    <strong>{scenario.data.name}</strong>
                    <small>{scenario.data.property_type} · {money(scenario.data.total_price)}</small>
                  </span>
                  <span>{plan?.variant ?? "待生成"}</span>
                  <span>{plan?.months_to_buy === null ? "暂不可达" : plan ? formatMonthDate(new Date(), plan.months_to_buy) : "-"}</span>
                  <span>{plan ? (stressShortfall > 0 ? `缺口 ${money(stressShortfall)}` : money(plan.cash_after_transaction)) : "-"}</span>
                  <span>{plan ? money(plan.post_purchase_cash_flow) : "-"}</span>
                  <span>{plan ? `${plan.happiness_score.toFixed(1)} / 10` : "-"}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">{calculationPending ? "正在计算房源对比" : "等待计算房源对比"}</div>
        )}
      </section>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Gauge size={18} />} title="候选策略" compact />
          <span>系统生成，选择后作为当前策略，可到可视化页查看图表</span>
        </div>
        {generatedPlans.length ? (
          <div className="strategy-grid">
            {generatedPlans.map((plan) => {
              const recommendation = recommendationByVariant.get(plan.variant);
              const isRecommended = recommended?.plan.variant === plan.variant;
              const isSelected = plan.variant === selectedPlan?.variant;
              const planStressShortfall = Math.max(0, plan.cash_stress_shortfall ?? 0);
              const planFamilySupportAmount = familySupportAmount(plan);
              const planFamilySupportLabel = familySupportLabel(plan);
              return (
                <button
                  key={plan.variant}
                  className={isSelected ? "strategy-card active" : "strategy-card"}
                  onClick={() => setSelectedPlanVariant(plan.variant)}
                >
                  <div className="strategy-card-head">
                    <strong>{plan.variant}</strong>
                    <span>{isRecommended ? "推荐" : `${recommendation?.score ?? 0} 分`}</span>
                  </div>
                  <p>{plan.description}</p>
                  <ul className="strategy-explain-list">
                    {purchaseStrategyDetails(plan).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <div className="strategy-scorebar">
                    <i style={{ width: `${Math.max(6, recommendation?.score ?? 0)}%` }} />
                  </div>
                  <div className="strategy-metrics">
                    <Metric label="可买时间" value={plan.years_to_buy === null ? "暂不可达" : `${plan.years_to_buy} 年`} />
                    <Metric label="计划首付" value={money(plan.planned_down_payment)} />
                    <Metric label="公积金贷" value={money(plan.provident_loan_amount)} />
                    <Metric label="公积金上限" value={money(plan.provident_policy_cap)} />
                    <Metric label="政策上浮" value={money(plan.provident_policy_bonus)} />
                    <Metric label="商贷" value={money(plan.commercial_loan_amount)} />
                    <Metric label="公积金年限" value={`${plan.provident_loan_years} 年`} />
                    <Metric label="商贷年限" value={`${plan.commercial_loan_years} 年`} />
                    <Metric label="公积金还款" value={repaymentMethodLabels[plan.provident_repayment_method]} />
                    <Metric label="商贷还款" value={repaymentMethodLabels[plan.commercial_repayment_method]} />
                    <Metric label="本人公积金首付抵扣" value={money(plan.provident_upfront_extractable)} />
                    {planFamilySupportAmount > 0 ? (
                      <Metric label={planFamilySupportLabel || "亲属首付支持"} value={money(planFamilySupportAmount)} tone="good" />
                    ) : null}
                    <Metric label="购房后预计提取到账" value={money(plan.provident_post_transaction_extractable)} />
                    <Metric label={planStressShortfall > 0 ? "压力现金缺口" : "交易当下现金"} value={planStressShortfall > 0 ? money(planStressShortfall) : money(plan.cash_after_transaction)} tone={planStressShortfall > 0 ? "bad" : plan.liquidity_ok ? "good" : "warn"} />
                    <Metric label="总月供" value={money(plan.total_monthly_payment)} />
                    <Metric label="买后自由月结余" value={money(plan.post_purchase_cash_flow)} tone={plan.post_purchase_cash_flow >= 0 ? "good" : "bad"} />
                  </div>
                  <p className="strategy-note">
                    首付现金：本人公积金可直接抵首付 {money(plan.provident_upfront_extractable)}
                    {planFamilySupportAmount > 0 ? `，${planFamilySupportLabel || "亲属首付支持"} ${money(planFamilySupportAmount)}` : ""}
                    ；购房后预计可提到银行卡 {money(plan.provident_post_transaction_extractable)}；年限：{plan.provident_loan_year_limit_reasons.join("；")}
                  </p>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">{calculationPending ? "正在计算生成购房策略" : "等待计算生成购房策略"}</div>
        )}
      </section>

      {selectedPlan ? (
        <StrategyNarrative
          plan={selectedPlan}
          scenario={selectedScenario.data}
          recommendation={recommendationByVariant.get(selectedPlan.variant)}
          isRecommended={recommended?.plan.variant === selectedPlan.variant}
        />
      ) : null}
    </div>
  );
}

function StrategyNarrative({
  plan,
  scenario,
  recommendation,
  isRecommended
}: {
  plan: PurchasePlanAnalysis;
  scenario: ScenarioData;
  recommendation?: StrategyRecommendation;
  isRecommended: boolean;
}) {
  const timelineBaseDate = useMemo(() => new Date(), []);
  const purchaseMonthText =
    plan.months_to_buy === null ? "暂未形成可执行日期" : formatMonthDate(timelineBaseDate, plan.months_to_buy);
  const propertyNatureText = [
    scenario.property_type,
    scenario.green_building_level !== "none" ? greenBuildingLabels[scenario.green_building_level] : "",
    scenario.prefab_building_level !== "none" ? prefabBuildingLabels[scenario.prefab_building_level] : "",
    scenario.is_ultra_low_energy_building ? "超低能耗建筑" : ""
  ].filter(Boolean).join(" / ");
  const timingText =
    plan.months_to_buy === null
      ? "按当前收入和资产路径，30 年内暂时无法满足买入所需现金。"
      : `预计 ${purchaseMonthText}、约 ${plan.years_to_buy} 年后可以执行买入；该日期用于同步计算届时公积金缴存年限、可贷额度和现金积累。`;
  const loanText = `执行时采用 ${money(plan.planned_down_payment)} 首付，贷款合计 ${money(plan.provident_loan_amount + plan.commercial_loan_amount)}：其中公积金贷 ${money(plan.provident_loan_amount)}，商贷 ${money(plan.commercial_loan_amount)}。首付、贷款和交易现金按 ${purchaseMonthText} 的资产路径测算。`;
  const policyBasisText = `政策依据采用北京住房公积金官方口径：首套/二套分别读取规则包中的商贷和公积金最低首付比例，系统取更严格者；公积金贷款按“每缴存一年可贷 15 万元”随 ${purchaseMonthText} 的缴存时间增长，并受首套 ${money(1200000)}、二套 ${money(1000000)} 的基础最高额度、购房月收入还款能力和基本生活费保留约束。当前房源性质为「${propertyNatureText || "未标注"}」，符合绿色建筑、装配式建筑或超低能耗建筑时只取最高一项上浮，本方案上浮 ${money(plan.provident_policy_bonus)}，最终政策上限 ${money(plan.provident_policy_cap)}。`;
  const termBasisText = `贷款年限依据同时看手动设定年限、北京公积金最长 30 年、借款申请人年龄上限，以及二手房/老旧小区房龄或土地剩余年限；本方案采用公积金 ${plan.provident_loan_years} 年，理由：${plan.provident_loan_year_limit_reasons.join("；")}。`;
  const repaymentDetailText = `买后还款按两笔贷款分开计算：公积金贷 ${money(plan.provident_loan_amount)}，${plan.provident_loan_years} 年，${repaymentMethodLabels[plan.provident_repayment_method]}，首月/月供约 ${money(plan.provident_monthly_payment)}；商贷 ${money(plan.commercial_loan_amount)}，${plan.commercial_loan_years} 年，${repaymentMethodLabels[plan.commercial_repayment_method]}，首月/月供约 ${money(plan.commercial_monthly_payment)}。两者合计月供约 ${money(plan.total_monthly_payment)}，全周期利息约 ${money(plan.total_interest)}。${plan.provident_repayment_advice ? ` ${plan.provident_repayment_advice}` : ""}`;
  const extractionNotesText = plan.provident_extraction_notes
    .map((note) => note.replace(/[。；\s]+$/u, ""))
    .join("；");
  const familySupportText = familySupportAmount(plan) > 0
    ? `另有${familySupportLabel(plan) || "亲属首付支持"} ${money(familySupportAmount(plan))}，用于减少家庭自己需要覆盖的首付现金。`
    : "";
  const extractionDetailText = `公积金提取按房源性质处理：符合条件的新房可按规则把本人公积金中的 ${money(plan.provident_upfront_extractable)} 直接用于抵扣首付；二手房默认更保守，主要把购房完成后、审核通过后预计可提到银行卡的金额单独列出，本方案预计到账 ${money(plan.provident_post_transaction_extractable)}，不是交易当天可用首付现金。剩余公积金余额约 ${money(plan.provident_balance_after_extract)}。${familySupportText}${extractionNotesText}。`;
  const cashText = plan.liquidity_ok
    ? `交易当下现金约 ${money(plan.cash_after_transaction)}，购房后公积金预计到账后约 ${money(plan.cash_after_purchase)}，覆盖 ${money(plan.required_liquidity_reserve)} 安全垫。`
    : `交易当下现金约 ${money(plan.cash_after_transaction)}，低于 ${money(plan.required_liquidity_reserve)} 安全垫要求。`;
  const flowText =
    plan.post_purchase_cash_flow >= 0
      ? `买后自由现金流约 ${money(plan.post_purchase_cash_flow)}；贷后公积金策略为「${providentStrategyLabel(plan)}」，策略后现金压力折算约 ${money(plan.post_purchase_cash_flow_with_pf_withdrawal)}/月。冲还贷只抵扣公积金贷款月供，不作为工资类收入。`
      : `买后自由现金流约 ${money(plan.post_purchase_cash_flow)}；贷后公积金策略为「${providentStrategyLabel(plan)}」，系统会优先判断半年度冲还贷能否缓解月供压力，但不会把公积金当作自由现金收入。`;
  const renovationText =
    scenario.renovation_cost <= 0
      ? "当前房源未设置装修预算。"
      : plan.renovation_included_in_upfront_cash
        ? `装修预算 ${money(scenario.renovation_cost)} 已计入交易现金需求。`
        : plan.months_to_renovation === null
          ? `装修预算 ${money(scenario.renovation_cost)} 不计入交易现金；买后月结余不足，暂无法估算装修启动时间。`
          : plan.months_to_renovation === 0
            ? `装修预算 ${money(scenario.renovation_cost)} 不计入交易现金；买后回流现金已可覆盖装修。`
            : `装修预算 ${money(scenario.renovation_cost)} 不计入交易现金；买后按月结余约 ${money(plan.post_purchase_renovation_monthly_saving)} 攒钱，预计 ${formatMonthDate(timelineBaseDate, (plan.months_to_buy ?? 0) + plan.months_to_renovation)} 可启动装修。`;
  const risks = [
    plan.debt_to_income_ratio > 0.5 ? "负债收入比较高，需要压低总价或延后买入。" : "负债收入比处在可观察区间。",
    plan.liquidity_ok ? "现金留存满足当前安全垫设定。" : "现金留存偏薄，建议提高流动性偏好或增加等待时间。",
    plan.post_purchase_cash_flow >= 0 ? "买后自由现金流为正，日常压力相对可控。" : "买后自由现金流为负，需要重新调整目标或贷款结构。"
  ];

  return (
    <section className="result-panel strategy-narrative">
      <div className="strategy-panel-head">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="当前策略说明" compact />
        <span>{isRecommended ? "系统推荐策略" : `${recommendation?.score ?? 0} 分候选策略`}</span>
      </div>
      <div className="narrative-grid">
        <article>
          <span>执行路径</span>
          <strong>{timingText}</strong>
          <p>{loanText}</p>
        </article>
        <article>
          <span>政策依据</span>
          <strong>按北京公积金贷款额度、房源上浮、最低首付和贷款年限规则计算。</strong>
          <p>{policyBasisText} {termBasisText}</p>
        </article>
        <article>
          <span>买后还款方案</span>
          <strong>公积金贷和商贷分开测算月供、期限、还款方式和总利息。</strong>
          <p>{repaymentDetailText} {flowText}</p>
        </article>
        <article>
          <span>公积金提取</span>
          <strong>按房源性质区分交易前首付提取、交易后购房提取；买房后的月缴公积金默认留存在账户。</strong>
          <p>{extractionDetailText}</p>
        </article>
        <article>
          <span>资金结论</span>
          <strong>{cashText}</strong>
          <p>{flowText}</p>
        </article>
        <article>
          <span>装修安排</span>
          <strong>{renovationText}</strong>
          <p>{plan.renovation_included_in_upfront_cash ? "装修资金会随首付和税费一起占用交易前现金。" : "默认不把装修款硬塞进交易日现金需求，买后按真实月结余判断启动时间。"}</p>
        </article>
        <article>
          <span>推荐理由</span>
          <strong>{recommendation?.reasons[0] ?? plan.description}</strong>
          <p>{recommendation?.reasons.slice(1, 3).join("；") || plan.description}</p>
        </article>
      </div>
      <div className="narrative-list">
        {risks.map((risk) => (
          <div key={risk}>
            <CheckCircle2 size={16} />
            <span>{risk}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function CarPlanPage({
  carPlan,
  result,
  updateCarPlan,
  updateCarPlanPatch
}: {
  carPlan: CarPlanData;
  result: AffordabilityResult | null;
  updateCarPlan: <K extends keyof CarPlanData>(key: K, value: CarPlanData[K]) => void;
  updateCarPlanPatch: (patch: Partial<CarPlanData>) => void;
}) {
  const carStrategies = result?.car_plan_analyses ?? [];
  const applyStrategy = (strategy: CarPlanAnalysis) => {
    updateCarPlanPatch({
      enabled: true,
      selected_strategy_variant: strategy.variant,
      down_payment_ratio: strategy.down_payment_ratio,
      down_payment: strategy.down_payment,
      purchase_delay_months: strategy.purchase_delay_months,
      total_months: strategy.total_months,
      interest_free_months: strategy.interest_free_months,
      later_annual_rate: strategy.later_annual_rate,
      monthly_operating_cost: strategy.monthly_cash_operating_cost,
    });
  };
  const updateDownPaymentRatio = (value: number) => {
    updateCarPlanPatch({
      selected_strategy_variant: "手动设置",
      down_payment_ratio: value,
      down_payment: Math.round((carPlan.total_price ?? 0) * value),
    });
  };
  const updateDownPaymentAmount = (value: number) => {
    const ratio = carPlan.total_price > 0 ? Math.min(1, Math.max(0, value / carPlan.total_price)) : 0;
    updateCarPlanPatch({
      selected_strategy_variant: "手动设置",
      down_payment: value,
      down_payment_ratio: ratio,
    });
  };
  const updateTotalPrice = (value: number) => {
    updateCarPlanPatch({
      selected_strategy_variant: "手动设置",
      total_price: value,
      down_payment: Math.round(value * (carPlan.down_payment_ratio ?? 0)),
    });
  };
  const addSecondCar = () => {
    updateCarPlanPatch({
      selected_strategy_variant: "手动设置",
      second_car_enabled: true,
      second_car_total_price: carPlan.second_car_total_price && carPlan.second_car_total_price > 0
        ? carPlan.second_car_total_price
        : 200000,
      second_car_down_payment_ratio: carPlan.second_car_down_payment_ratio ?? 0.4,
      second_car_purchase_delay_months: carPlan.second_car_purchase_delay_months ?? 60,
      second_car_total_months: carPlan.second_car_total_months ?? 60,
      second_car_interest_free_months: carPlan.second_car_interest_free_months ?? 24,
      second_car_later_annual_rate: carPlan.second_car_later_annual_rate ?? 0.0199,
      second_car_annual_mileage_km: carPlan.second_car_annual_mileage_km && carPlan.second_car_annual_mileage_km > 0
        ? carPlan.second_car_annual_mileage_km
        : 8000,
      second_car_monthly_parking_cost: carPlan.second_car_monthly_parking_cost && carPlan.second_car_monthly_parking_cost > 0
        ? carPlan.second_car_monthly_parking_cost
        : 400,
    });
  };
  const removeSecondCar = () => {
    updateCarPlanPatch({
      selected_strategy_variant: "手动设置",
      second_car_enabled: false,
    });
  };
  const selectedCarStrategy = carPlan.enabled ? (carPlan.selected_strategy_variant ?? "手动设置") : "不买车模式";
  const carLoan = result?.car_loan;

  return (
    <div className="page-stack">
      <SectionHeader icon={<Car size={20} />} title="买车计划" />
      <section className="form-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<CircleDollarSign size={18} />} title="买车目标" compact />
          <span className="status-pill">当前采用：{selectedCarStrategy}</span>
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={carPlan.enabled}
            onChange={(event) => updateCarPlan("enabled", event.target.checked)}
          />
          {carPlan.enabled ? "计划买车并纳入现金流" : "不买车模式：仅计入无车通勤成本"}
        </label>
        <div className="form-grid">
          <Field label="计划名称">
            <input
              value={carPlan.name}
              onChange={(event) => updateCarPlan("name", event.target.value)}
            />
          </Field>
          <NumberField label="车辆总价" value={carPlan.total_price} min={0} step={10000} onChange={updateTotalPrice} />
          <NumberField label="首付比例" value={carPlan.down_payment_ratio ?? 0.5} min={0} max={1} step={0.05} onChange={updateDownPaymentRatio} />
          <NumberField label="首付金额" value={carPlan.down_payment ?? 0} min={0} step={1000} onChange={updateDownPaymentAmount} />
          <NumberField label="延后买车月数" value={carPlan.purchase_delay_months ?? 0} min={0} max={120} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", purchase_delay_months: value })} />
          <NumberField label="总期数" value={carPlan.total_months} min={1} max={120} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", total_months: value })} />
          <NumberField label="0息期数" value={carPlan.interest_free_months} min={0} max={120} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", interest_free_months: value })} />
          <NumberField label="后段年利率" value={carPlan.later_annual_rate} min={0} max={0.5} step={0.0001} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", later_annual_rate: value })} />
          <NumberField label="当前期数" value={carPlan.current_month_index} min={1} max={carPlan.total_months || 120} step={1} onChange={(value) => updateCarPlan("current_month_index", value)} />
          <NumberField label="年行驶里程" value={carPlan.annual_mileage_km ?? 12000} min={0} max={100000} step={1000} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", annual_mileage_km: value })} />
          <NumberField label="百公里电耗" value={carPlan.electricity_kwh_per_100km ?? 14} min={0} max={50} step={0.5} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", electricity_kwh_per_100km: value })} />
          <NumberField label="充电单价" value={carPlan.electricity_price_per_kwh ?? 0.8} min={0} max={5} step={0.05} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", electricity_price_per_kwh: value })} />
          <NumberField label="月停车费" value={carPlan.monthly_parking_cost ?? 600} min={0} step={100} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", monthly_parking_cost: value })} />
          <NumberField label="无车通勤月成本" value={carPlan.no_car_monthly_commute_cost ?? 800} min={0} step={100} onChange={(value) => updateCarPlan("no_car_monthly_commute_cost", value)} />
          <NumberField label="年保养杂费" value={carPlan.annual_maintenance_cost ?? 2400} min={0} step={500} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", annual_maintenance_cost: value })} />
          <NumberField label="保养年增长" value={carPlan.annual_maintenance_growth_rate ?? 0.03} min={0} max={0.2} step={0.005} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", annual_maintenance_growth_rate: value })} />
          <NumberField label="保险费率" value={carPlan.annual_insurance_rate ?? 0.018} min={0} max={0.2} step={0.001} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", annual_insurance_rate: value })} />
          <NumberField label="年保险下限" value={carPlan.annual_insurance_min ?? 4500} min={0} step={500} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", annual_insurance_min: value })} />
          <NumberField label="保险年增长" value={carPlan.annual_insurance_growth_rate ?? 0.02} min={0} max={0.2} step={0.005} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", annual_insurance_growth_rate: value })} />
          <NumberField label="折旧年限" value={carPlan.depreciation_years ?? 8} min={1} max={20} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", depreciation_years: value })} />
          <NumberField label="车辆使用年限" value={carPlan.vehicle_service_years ?? 15} min={1} max={30} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", vehicle_service_years: value })} />
          <NumberField label="报废/更新里程" value={carPlan.vehicle_retirement_mileage_km ?? 600000} min={0} max={1000000} step={10000} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", vehicle_retirement_mileage_km: value })} />
          <NumberField label="买车幸福度" value={carPlan.happiness_score ?? 6.5} min={0} max={10} step={0.5} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", happiness_score: value })} />
          <Field label="攒车首付开始">
            <input
              value={carPlan.saving_start_date ?? "2026-07-01"}
              onChange={(event) => updateCarPlan("saving_start_date", event.target.value)}
            />
          </Field>
        </div>
        <section className="sub-plan-panel">
          <div className="member-header compact-heading">
            <strong>第二辆车</strong>
            {carPlan.second_car_enabled ? (
              <button className="ghost-button" onClick={removeSecondCar} type="button">
                <Trash2 size={15} /> 移除第二辆车
              </button>
            ) : (
              <button className="ghost-button" onClick={addSecondCar} type="button">
                <Plus size={15} /> 添加第二辆车
              </button>
            )}
          </div>
          {carPlan.second_car_enabled ? (
            <>
              <div className="form-grid">
                <NumberField label="第二辆车总价" value={carPlan.second_car_total_price ?? 200000} min={0} step={10000} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_total_price: value })} />
                <NumberField label="第二车首付比例" value={carPlan.second_car_down_payment_ratio ?? 0.4} min={0} max={1} step={0.05} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_down_payment_ratio: value })} />
                <NumberField label="第二车延后月数" value={carPlan.second_car_purchase_delay_months ?? 60} min={0} max={240} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_purchase_delay_months: value })} />
                <NumberField label="第二车总期数" value={carPlan.second_car_total_months ?? 60} min={1} max={120} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_total_months: value })} />
                <NumberField label="第二车0息期数" value={carPlan.second_car_interest_free_months ?? 24} min={0} max={120} step={1} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_interest_free_months: value })} />
                <NumberField label="第二车后段利率" value={carPlan.second_car_later_annual_rate ?? 0.0199} min={0} max={0.5} step={0.0001} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_later_annual_rate: value })} />
                <NumberField label="第二车年里程" value={carPlan.second_car_annual_mileage_km ?? 8000} min={0} max={100000} step={1000} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_annual_mileage_km: value })} />
                <NumberField label="第二车月停车费" value={carPlan.second_car_monthly_parking_cost ?? 400} min={0} step={100} onChange={(value) => updateCarPlanPatch({ selected_strategy_variant: "手动设置", second_car_monthly_parking_cost: value })} />
              </div>
              <p className="field-hint">第二辆车会从指定月份起叠加首付、车贷、电费、保险、保养和停车费，并同步进入购房现金流、事件时间线和可视化。</p>
            </>
          ) : (
            <p className="field-hint">当前没有第二辆车计划。需要时点击添加，系统才会把第二辆车纳入后续现金流。</p>
          )}
        </section>
        <p className="field-hint">
          这里是买车目标、贷款参数和使用假设；不买车时系统会把无车通勤月成本计入现金流，延后买车时买车前也先按无车通勤测算。
        </p>
        {carLoan ? (
          <div className="car-cost-breakdown">
            {carPlan.enabled ? (
              <>
                <Metric label="月均现金养车" value={money(carLoan.monthly_cash_operating_cost)} />
                <Metric label="年保险" value={money(carLoan.monthly_insurance_cost * 12)} />
                <Metric label="电费/月" value={money(carLoan.monthly_energy_cost)} />
                <Metric label="年保养" value={money(carLoan.monthly_maintenance_cost * 12)} />
                <Metric label="保险/保养年增长" value={`${percent(carPlan.annual_insurance_growth_rate ?? 0.02)} / ${percent(carPlan.annual_maintenance_growth_rate ?? 0.03)}`} />
                <Metric label="停车/月" value={money(carLoan.monthly_parking_cost)} />
                <Metric label="含折旧总成本" value={money(carLoan.monthly_total_ownership_cost)} />
                {carPlan.second_car_enabled ? (
                  <>
                    <Metric label="第二车首付" value={money((carPlan.second_car_total_price ?? 0) * (carPlan.second_car_down_payment_ratio ?? 0))} />
                    <Metric label="第二车购入" value={formatMonthDate(new Date(), carPlan.second_car_purchase_delay_months ?? 0)} />
                  </>
                ) : null}
              </>
            ) : (
              <>
                <Metric label="无车通勤月成本" value={money(carPlan.no_car_monthly_commute_cost ?? 0)} />
                <Metric label="当前方案" value="不买车" />
              </>
            )}
          </div>
        ) : null}
      </section>

      <section className="result-panel">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Gauge size={18} />} title="自动生成买车策略" compact />
          <span>采用方案后会写回当前买车计划，并影响购房测算</span>
        </div>
        {carStrategies.length ? (
          <div className="strategy-grid">
            {carStrategies.map((strategy) => (
              <article className={selectedCarStrategy === strategy.variant ? "strategy-card car-strategy-card active" : "strategy-card car-strategy-card"} key={strategy.variant}>
                <div className="strategy-card-head">
                  <strong>{strategy.variant}</strong>
                  <span>{selectedCarStrategy === strategy.variant ? "已采用" : strategy.years_to_buy === null ? "暂不可达" : `${strategy.years_to_buy} 年`}</span>
                </div>
                <p>{strategy.description}</p>
                <ul className="strategy-explain-list">
                  {carStrategyDetails(strategy.variant).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <div className="strategy-metrics">
                  <Metric label="首付" value={money(strategy.down_payment)} />
                  <Metric label="贷款本金" value={money(strategy.loan_principal)} />
                  <Metric label="预计月供" value={money(strategy.expected_monthly_payment_after_purchase)} />
                  <Metric label="月均现金养车" value={money(strategy.monthly_cash_operating_cost)} />
                  <Metric label="月均总拥有成本" value={money(strategy.monthly_total_ownership_cost)} />
                  <Metric label="买后现金" value={money(strategy.cash_after_purchase)} tone={strategy.cash_after_purchase >= 0 ? "good" : "warn"} />
                  <Metric label="买后月结余" value={money(strategy.monthly_cash_flow_after_car)} tone={strategy.monthly_cash_flow_after_car >= 0 ? "good" : "bad"} />
                  <Metric label="总利息" value={money(strategy.total_interest)} />
                  <Metric label="幸福指数" value={`${strategy.happiness_score.toFixed(1)} / 10`} tone={strategy.happiness_score >= 7 ? "good" : strategy.happiness_score >= 5 ? "warn" : "bad"} />
                </div>
                <div className="car-notes">
                  {strategy.notes.map((note) => (
                    <span key={note}>{note}</span>
                  ))}
                </div>
                <button className={selectedCarStrategy === strategy.variant ? "primary-button" : "ghost-button"} onClick={() => applyStrategy(strategy)}>
                  <CheckCircle2 size={16} /> {selectedCarStrategy === strategy.variant ? "当前方案" : "采用方案"}
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">当前为不买车模式：每月无车通勤成本会进入现金流；启用买车计划并填写目标车价后，会自动生成买车策略。</div>
        )}
      </section>
    </div>
  );
}

function RulePage({
  activeRulePack,
  ruleNumber,
  updateRulePack,
  updateRuleParam,
  sourceUrl,
  setSourceUrl,
  sourcePreview,
  previewSource,
  saving
}: {
  activeRulePack: RulePackData;
  ruleNumber: (key: string, fallback: number) => number;
  updateRulePack: <K extends keyof RulePackData>(key: K, value: RulePackData[K]) => void;
  updateRuleParam: (key: string, value: number | string | boolean) => void;
  sourceUrl: string;
  setSourceUrl: (value: string) => void;
  sourcePreview: SourceDocumentRecord | null;
  previewSource: () => void;
  saving: boolean;
}) {
  return (
    <div className="page-stack">
      <SectionHeader icon={<Database size={20} />} title="政策规则" />
      <section className="rule-panel">
        <PanelTitle icon={<Database size={18} />} title="规则包与来源" />
        <div className="rule-grid">
          <Field label="规则包">
            <input
              value={activeRulePack.name}
              onChange={(event) => updateRulePack("name", event.target.value)}
            />
          </Field>
          <Field label="生效日期">
            <input
              value={activeRulePack.effective_date}
              onChange={(event) => updateRulePack("effective_date", event.target.value)}
            />
          </Field>
          <NumberField label="最低首付比例" value={Number(activeRulePack.params.minimum_down_payment_ratio)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("minimum_down_payment_ratio", value)} />
          <NumberField label="谨慎 DTI" value={Number(activeRulePack.params.caution_dti)} min={0} max={2} step={0.01} onChange={(value) => updateRuleParam("caution_dti", value)} />
          <NumberField label="高风险 DTI" value={Number(activeRulePack.params.danger_dti)} min={0} max={2} step={0.01} onChange={(value) => updateRuleParam("danger_dti", value)} />
          <NumberField label="推荐应急月数" value={Number(activeRulePack.params.recommended_emergency_months)} min={0} max={36} step={1} onChange={(value) => updateRuleParam("recommended_emergency_months", value)} />
          <NumberField label="年度基本扣除" value={ruleNumber("personal_standard_deduction_annual", 60000)} min={0} step={1000} onChange={(value) => updateRuleParam("personal_standard_deduction_annual", value)} />
          <NumberField label="社保基数下限" value={ruleNumber("beijing_social_base_floor", 7162)} min={0} step={100} onChange={(value) => updateRuleParam("beijing_social_base_floor", value)} />
          <NumberField label="社保基数上限" value={ruleNumber("beijing_social_base_ceiling", 35811)} min={0} step={100} onChange={(value) => updateRuleParam("beijing_social_base_ceiling", value)} />
          <NumberField label="公积金基数下限" value={ruleNumber("beijing_housing_fund_base_floor", 2540)} min={0} step={100} onChange={(value) => updateRuleParam("beijing_housing_fund_base_floor", value)} />
          <NumberField label="公积金基数上限" value={ruleNumber("beijing_housing_fund_base_ceiling", 35811)} min={0} step={100} onChange={(value) => updateRuleParam("beijing_housing_fund_base_ceiling", value)} />
          <NumberField label="失业金1至5年" value={ruleNumber("beijing_unemployment_benefit_under_5y", 2129)} min={0} step={10} onChange={(value) => updateRuleParam("beijing_unemployment_benefit_under_5y", value)} />
          <NumberField label="失业金5至10年" value={ruleNumber("beijing_unemployment_benefit_5_to_10y", 2156)} min={0} step={10} onChange={(value) => updateRuleParam("beijing_unemployment_benefit_5_to_10y", value)} />
          <NumberField label="失业金10至15年" value={ruleNumber("beijing_unemployment_benefit_10_to_15y", 2188)} min={0} step={10} onChange={(value) => updateRuleParam("beijing_unemployment_benefit_10_to_15y", value)} />
          <NumberField label="失业金15至20年" value={ruleNumber("beijing_unemployment_benefit_15_to_20y", 2215)} min={0} step={10} onChange={(value) => updateRuleParam("beijing_unemployment_benefit_15_to_20y", value)} />
          <NumberField label="失业金20年以上" value={ruleNumber("beijing_unemployment_benefit_20y_plus", 2286)} min={0} step={10} onChange={(value) => updateRuleParam("beijing_unemployment_benefit_20y_plus", value)} />
          <NumberField label="失业金13月后" value={ruleNumber("beijing_unemployment_benefit_after_12_months", 2129)} min={0} step={10} onChange={(value) => updateRuleParam("beijing_unemployment_benefit_after_12_months", value)} />
          <NumberField label="灵活就业基数" value={ruleNumber("flexible_employment_social_base", 7162)} min={0} step={100} onChange={(value) => updateRuleParam("flexible_employment_social_base", value)} />
          <NumberField label="灵活养老比例" value={ruleNumber("flexible_employment_pension_rate", 0.2)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("flexible_employment_pension_rate", value)} />
          <NumberField label="灵活失业比例" value={ruleNumber("flexible_employment_unemployment_rate", 0.01)} min={0} max={1} step={0.001} onChange={(value) => updateRuleParam("flexible_employment_unemployment_rate", value)} />
          <NumberField label="灵活医保月额" value={ruleNumber("flexible_employment_medical_monthly", 584.92)} min={0} step={10} onChange={(value) => updateRuleParam("flexible_employment_medical_monthly", value)} />
          <NumberField label="首套商贷首付" value={ruleNumber("first_home_commercial_min_down_payment_ratio", 0.15)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("first_home_commercial_min_down_payment_ratio", value)} />
          <NumberField label="首套公积金首付" value={ruleNumber("first_home_provident_min_down_payment_ratio", 0.2)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("first_home_provident_min_down_payment_ratio", value)} />
          <NumberField label="二套商贷首付" value={ruleNumber("second_home_commercial_min_down_payment_ratio", 0.2)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("second_home_commercial_min_down_payment_ratio", value)} />
          <NumberField label="二套公积金首付" value={ruleNumber("second_home_provident_min_down_payment_ratio", 0.25)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("second_home_provident_min_down_payment_ratio", value)} />
          <NumberField label="每缴存年可贷额度" value={ruleNumber("provident_loan_amount_per_deposit_year", 150000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_loan_amount_per_deposit_year", value)} />
          <NumberField label="首套公积金额度" value={ruleNumber("provident_first_home_loan_cap", 1200000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_first_home_loan_cap", value)} />
          <NumberField label="二套公积金额度" value={ruleNumber("provident_second_home_loan_cap", 1000000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_second_home_loan_cap", value)} />
          <NumberField label="公积金还款收入占比" value={ruleNumber("provident_repayment_income_ratio", 0.6)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("provident_repayment_income_ratio", value)} />
          <NumberField label="公积金基本生活费/人" value={ruleNumber("provident_basic_living_cost_per_person", 1778)} min={0} step={50} onChange={(value) => updateRuleParam("provident_basic_living_cost_per_person", value)} />
          <NumberField label="新房交易前可提" value={ruleNumber("provident_upfront_purchase_extract_ratio_new_home", 1)} min={0} max={1} step={0.05} onChange={(value) => updateRuleParam("provident_upfront_purchase_extract_ratio_new_home", value)} />
          <NumberField label="二手房交易前可提" value={ruleNumber("provident_upfront_purchase_extract_ratio_second_hand", 0)} min={0} max={1} step={0.05} onChange={(value) => updateRuleParam("provident_upfront_purchase_extract_ratio_second_hand", value)} />
          <NumberField label="购房后提取到账比例" value={ruleNumber("provident_post_transaction_extract_ratio", 1)} min={0} max={1} step={0.05} onChange={(value) => updateRuleParam("provident_post_transaction_extract_ratio", value)} />
          <label className="check-row inline-check">
            <input
              type="checkbox"
              checked={Boolean(activeRulePack.params.provident_post_purchase_cashflow_enabled ?? false)}
              onChange={(event) => updateRuleParam("provident_post_purchase_cashflow_enabled", event.target.checked ? true : false)}
            />
            购后公积金计入现金改善
          </label>
          <Field label="购后改善模式">
            <select
              value={String(activeRulePack.params.provident_post_purchase_withdrawal_mode ?? "purchase_agreed")}
              onChange={(event) => updateRuleParam("provident_post_purchase_withdrawal_mode", event.target.value)}
            >
              <option value="purchase_agreed">购房约定提取</option>
              <option value="loan_offset">公积金贷款冲还贷</option>
            </select>
          </Field>
          <p className="field-hint policy-hint">
            默认关闭：买房后月缴公积金继续进入公积金账户，不作为家庭自由现金收入。只有确认符合购房约定提取或冲还贷办理条件时，才建议开启这个情景开关。
          </p>
          <NumberField label="公积金余额年利率" value={ruleNumber("provident_balance_annual_interest_rate", 0.015)} min={0} max={0.1} step={0.0005} onChange={(value) => updateRuleParam("provident_balance_annual_interest_rate", value)} />
          <NumberField label="二星绿色上浮" value={ruleNumber("provident_green_two_star_bonus", 200000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_green_two_star_bonus", value)} />
          <NumberField label="三星绿色上浮" value={ruleNumber("provident_green_three_star_bonus", 300000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_green_three_star_bonus", value)} />
          <NumberField label="装配式A上浮" value={ruleNumber("provident_prefab_a_bonus", 100000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_prefab_a_bonus", value)} />
          <NumberField label="装配式AA上浮" value={ruleNumber("provident_prefab_aa_bonus", 200000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_prefab_aa_bonus", value)} />
          <NumberField label="装配式AAA上浮" value={ruleNumber("provident_prefab_aaa_bonus", 300000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_prefab_aaa_bonus", value)} />
          <NumberField label="超低能耗上浮" value={ruleNumber("provident_ultra_low_energy_bonus", 400000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_ultra_low_energy_bonus", value)} />
          <NumberField label="上浮封顶" value={ruleNumber("provident_policy_bonus_cap", 400000)} min={0} step={10000} onChange={(value) => updateRuleParam("provident_policy_bonus_cap", value)} />
          <NumberField label="微量商贷默认比例" value={ruleNumber("micro_commercial_loan_ratio", 0.05)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("micro_commercial_loan_ratio", value)} />
          <NumberField label="微量商贷自动下限" value={ruleNumber("micro_commercial_loan_ratio_min", 0.02)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("micro_commercial_loan_ratio_min", value)} />
          <NumberField label="微量商贷自动上限" value={ruleNumber("micro_commercial_loan_ratio_max", 0.12)} min={0} max={1} step={0.01} onChange={(value) => updateRuleParam("micro_commercial_loan_ratio_max", value)} />
          <Field label="年终奖单独计税至">
            <input
              value={String(activeRulePack.params.annual_bonus_separate_tax_valid_until ?? "2027-12-31")}
              onChange={(event) =>
                updateRuleParam("annual_bonus_separate_tax_valid_until", event.target.value)
              }
            />
          </Field>
        </div>

        <div className="source-row">
          <select value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)}>
            {sourceDefaults.map((url) => (
              <option key={url} value={url}>
                {url}
              </option>
            ))}
          </select>
          <button className="ghost-button" onClick={previewSource} disabled={saving}>
            <RefreshCw size={16} /> 抓取预览
          </button>
        </div>
        {sourcePreview ? (
          <div className="source-preview">
            <strong>{sourcePreview.changed_from_previous ? "发现新内容或首次抓取" : "内容未变化"}</strong>
            <span>{sourcePreview.summary}</span>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function VisualizationPage({
  result,
  household,
  selectedScenario,
  scenarioComparisons,
  setSelectedScenarioId,
  selectedPlan,
  selectedPlanVariant,
  setSelectedPlanVariant,
  activeRulePack,
  calculationPending
}: {
  result: AffordabilityResult | null;
  household: HouseholdData;
  selectedScenario: RecordEnvelope<ScenarioData>;
  scenarioComparisons: ScenarioComparison[];
  setSelectedScenarioId: (id: string) => void;
  selectedPlan: PurchasePlanAnalysis | null;
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  activeRulePack: RulePackData;
  calculationPending: boolean;
}) {
  const availablePlans = result?.purchase_plan_analyses ?? [];
  const scenario = selectedScenario.data;
  const comparisonDecision = (plan: PurchasePlanAnalysis | null) => {
    if (!plan) return { label: "待生成", tone: "muted" };
    if (plan.months_to_buy === null) return { label: "暂不可达", tone: "bad" };
    if (plan.cash_stress_ok === false || (plan.cash_stress_shortfall ?? 0) > 0) return { label: "先修现金缺口", tone: "bad" };
    if (!plan.liquidity_ok) return { label: "现金垫偏紧", tone: "warn" };
    if (plan.post_purchase_cash_flow < 0) return { label: "月供压力高", tone: "warn" };
    if (plan.happiness_score >= 7 && plan.debt_to_income_ratio <= 0.45) return { label: "优先关注", tone: "good" };
    return { label: "可比较", tone: "neutral" };
  };

  return (
    <div className="page-stack">
      <SectionHeader icon={<TrendingUp size={20} />} title="可视化" />
      <section className="result-panel decision-board">
        <div className="strategy-panel-head">
          <PanelTitle icon={<Home size={18} />} title="房源决策表" compact />
          <span>先看哪套房、哪种策略更值得继续推演；点击一行后，下方故事线会切换到对应房源和策略。</span>
        </div>
        {scenarioComparisons.length ? (
          <div className="comparison-table">
            <div className="comparison-row comparison-head">
              <span>房源与策略</span>
              <span>可买时间</span>
              <span>交易后现金</span>
              <span>压力现金</span>
              <span>买后月结余</span>
              <span>贷款压力</span>
              <span>幸福指数</span>
              <span>判断</span>
            </div>
            {scenarioComparisons.map(({ scenario: comparedScenario, recommendation, selectedPlan: plan }) => {
              const decision = comparisonDecision(plan);
              const minimumCash =
                plan?.minimum_cash_balance !== undefined && plan.minimum_cash_balance !== null
                  ? plan.minimum_cash_balance
                  : plan?.cash_after_transaction;
              const stressShortfall = Math.max(0, plan?.cash_stress_shortfall ?? 0);
              const isRecommended = recommendation?.plan.variant === plan?.variant;
              return (
                <button
                  type="button"
                  className={comparedScenario.id === selectedScenario.id ? "comparison-row active" : "comparison-row"}
                  key={comparedScenario.id}
                  onClick={() => setSelectedScenarioId(comparedScenario.id)}
                >
                  <span>
                    <strong>{comparedScenario.data.name}</strong>
                    <small>
                      {comparedScenario.data.property_type} · {money(comparedScenario.data.total_price)}
                      {plan ? ` · ${plan.variant}` : ""}
                      {isRecommended ? " · 系统推荐" : ""}
                    </small>
                  </span>
                  <span>{plan?.months_to_buy === null ? "暂不可达" : plan ? formatMonthDate(new Date(), plan.months_to_buy) : "-"}</span>
                  <span>{plan ? money(plan.cash_after_purchase) : "-"}</span>
                  <span>{plan && stressShortfall > 0 ? `缺口 ${money(stressShortfall)}` : plan && minimumCash !== undefined ? money(minimumCash) : "-"}</span>
                  <span>{plan ? money(plan.post_purchase_cash_flow) : "-"}</span>
                  <span>{plan ? `${percent(plan.debt_to_income_ratio)} · 息 ${money(plan.total_interest)}` : "-"}</span>
                  <span>{plan ? `${plan.happiness_score.toFixed(1)} / 10` : "-"}</span>
                  <span className={`decision-pill ${decision.tone}`}>{decision.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">{calculationPending ? "正在计算房源对比" : "等待计算房源对比"}</div>
        )}
      </section>
      <section className="result-panel">
        {result && selectedPlan ? (
          <>
            <div className="visual-header">
              <div>
                <PanelTitle icon={<TrendingUp size={18} />} title="选中策略" />
                <h3>{selectedPlan.variant}</h3>
                <p>{selectedPlan.description}</p>
              </div>
              <select
                value={selectedPlanVariant}
                onChange={(event) => setSelectedPlanVariant(event.target.value)}
              >
                {availablePlans.map((plan) => (
                  <option key={plan.variant} value={plan.variant}>
                    {plan.variant}
                  </option>
                ))}
              </select>
            </div>

            <SelectedPlanVisualization
              result={result}
              household={household}
              scenario={scenario}
              plan={selectedPlan}
              rulePack={activeRulePack}
            />
          </>
        ) : (
          <PanelTitle
            icon={<Loader2 className="spin" size={18} />}
            title={calculationPending ? "正在计算生成策略" : "等待计算生成策略"}
          />
        )}
      </section>
    </div>
  );
}

function SelectedPlanVisualization({
  result,
  household,
  scenario,
  plan,
  rulePack
}: {
  result: AffordabilityResult;
  household: HouseholdData;
  scenario: ScenarioData;
  plan: PurchasePlanAnalysis;
  rulePack: RulePackData;
}) {
  const timelineBaseDate = useMemo(() => new Date(), []);
  const [selectedMonthIndex, setSelectedMonthIndex] = useState(1);
  const [viewStartMonth, setViewStartMonth] = useState(0);
  const [viewWindowMonths, setViewWindowMonths] = useState(120);
  const [isCompactChart, setIsCompactChart] = useState(() =>
    typeof window === "undefined" ? false : window.innerWidth < 640
  );
  useEffect(() => {
    const syncCompactChart = () => setIsCompactChart(window.innerWidth < 640);
    syncCompactChart();
    window.addEventListener("resize", syncCompactChart);
    return () => window.removeEventListener("resize", syncCompactChart);
  }, []);
  const loanVisualizationSeries = useMemo(
    () => (result.loan_visualization ?? []).filter((item) => item.plan_variant === plan.variant),
    [result.loan_visualization, plan.variant]
  );
  const loanVisualizationByMonth = useMemo(
    () => new Map(loanVisualizationSeries.map((item) => [item.month, item])),
    [loanVisualizationSeries]
  );
  const providentVisualizationSeries = useMemo(
    () => (result.provident_visualization ?? []).filter((item) => item.plan_variant === plan.variant),
    [result.provident_visualization, plan.variant]
  );
  const providentVisualizationByMonth = useMemo(
    () => new Map(providentVisualizationSeries.map((item) => [item.month, item])),
    [providentVisualizationSeries]
  );
  const backendCashflowSeries = useMemo(
    () => (result.monthly_cashflow_visualization ?? []).filter((item) => item.plan_variant === plan.variant),
    [result.monthly_cashflow_visualization, plan.variant]
  );
  const requiredCashAfterPf = plan.required_cash_after_pf_extract;
  const purchaseYearText = plan.years_to_buy === null ? "超过 30 年" : `${plan.years_to_buy} 年`;
  const annualReturn = scenario.annual_investment_return ?? 0;
  const investmentEnabled = household.investment_plan_name !== "cash_only";
  const investmentBuyFeeRate = Math.min(Math.max(0, household.investment_buy_fee_rate ?? 0.0015), 0.05);
  const investmentSellFeeRate = Math.min(Math.max(0, household.investment_sell_fee_rate ?? 0.005), 0.05);
  const monthlyInvestmentSetting = investmentEnabled ? Math.max(0, household.monthly_investment_amount ?? 0) : 0;
  const renovationTimingText =
    scenario.renovation_cost <= 0
      ? "无装修预算"
      : plan.renovation_included_in_upfront_cash
        ? "交易时已备"
        : plan.months_to_renovation === null
          ? "暂无法估算"
          : plan.months_to_renovation === 0
            ? "买后可启动"
            : `买后 ${plan.months_to_renovation} 个月`;
  const effectiveMembers = useMemo(() => effectiveIncomeMembers(household, rulePack, timelineBaseDate), [household, rulePack, timelineBaseDate]);
  const effectiveHousehold = useMemo(() => ({ ...household, members: effectiveMembers }), [household, effectiveMembers]);
  const getMemberIncomeRows = (absoluteMonth: number) =>
    effectiveMembers.length > 0
      ? effectiveMembers.map((member) => memberMonthlyIncomeRow(member, rulePack, effectiveHousehold, timelineBaseDate, absoluteMonth))
      : [
          {
            name: "家庭",
            stageName: "当前收入",
            grossMonthly: result.household_gross_monthly_income,
            bonusMonthly: 0,
            otherMonthly: 0,
            nonTaxableMonthly: 0,
            salaryNetMonthly: result.household_net_monthly_income,
            bonusNetMonthly: 0,
            otherNetMonthly: 0,
            nonTaxableNetMonthly: 0,
            extraCashExpense: 0,
            netMonthly: result.household_net_monthly_income,
            personalSocial: 0,
            personalHousingFund: 0,
            employerHousingFund: 0,
            incomeTax: 0,
            elderlyCareDeduction: 0
          }
        ];
  const horizonMonths = Math.min(
    840,
    Math.max(
      180,
      backendCashflowSeries[backendCashflowSeries.length - 1]?.month ?? 0,
      loanVisualizationSeries[loanVisualizationSeries.length - 1]?.month ?? 0,
      providentVisualizationSeries[providentVisualizationSeries.length - 1]?.month ?? 0
    )
  );
  const chartMaxTicks = isCompactChart ? 4 : 8;
  const chartMonthTickInterval = Math.max(0, Math.ceil(Math.min(horizonMonths + 1, viewWindowMonths) / chartMaxTicks) - 1);
  const formatChartMonthTick = (value: unknown) => {
    const month = Number(value);
    if (!Number.isFinite(month)) return "";
    const targetDate = addMonths(timelineBaseDate, month);
    return `${targetDate.getFullYear()}.${targetDate.getMonth() + 1}`;
  };
  const chartXAxisProps = {
    dataKey: "month",
    tickLine: false,
    axisLine: false,
    interval: chartMonthTickInterval,
    minTickGap: isCompactChart ? 34 : 52,
    tickMargin: 10,
    height: 34,
    tickFormatter: formatChartMonthTick
  };
  const monthlySeries =
    backendCashflowSeries
      .filter((item) => item.month <= horizonMonths)
      .map((item) => {
            const loanPoint = loanVisualizationByMonth.get(item.month);
            const providentPoint = providentVisualizationByMonth.get(item.month);
            const houseContractPayment = item.house_contract_payment ?? loanPoint?.home_monthly_payment ?? 0;
            const providentHouseOffsetPayment =
              item.provident_house_offset_payment ?? loanPoint?.provident_offset_payment ?? providentPoint?.loan_offset_payment ?? 0;
            const housePayment = item.house_payment ?? Math.max(0, houseContractPayment - providentHouseOffsetPayment);
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
            return {
              month: item.month,
              name: formatMonthDate(timelineBaseDate, item.month),
              period: item.phase,
              现金池: Math.round(item.cash_balance),
              投资资产: Math.round(item.investment_balance),
              固定资产: Math.round(item.fixed_asset_value),
              房产估值: Math.round(propertyAssetValue),
              车辆估值: Math.round(vehicleAssetValue),
              第一辆车估值: Math.round(firstVehicleAssetValue),
              第二辆车估值: Math.round(secondVehicleAssetValue),
              总资产: Math.round(item.cash_balance + item.investment_balance),
              家庭总资产: Math.round(item.cash_balance + item.investment_balance + item.fixed_asset_value),
              公积金余额: Math.round(item.provident_balance),
              安全垫: Math.round(plan.required_liquidity_reserve),
              cashIncome: item.cash_income,
              livingExpense: item.living_expense + item.scheduled_expense,
              baseLivingExpense: item.living_expense,
              scheduledLivingExpense: item.scheduled_expense,
              scheduledExpenseRows: scheduledExpenseRowsAt(household, timelineBaseDate, item.month),
              debtPayment,
              regularDebtPayment: item.regular_debt_payment ?? Math.max(0, debtPayment - (item.phased_loan_payment ?? 0)),
              phasedLoanPayment: item.phased_loan_payment ?? Math.max(0, debtPayment - household.monthly_debt_payment),
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
              housePayment,
              houseContractPayment,
              providentHouseOffsetPayment,
              providentHousePayment: Math.max(
                0,
                (loanPoint?.provident_monthly_payment ?? 0) - providentHouseOffsetPayment
              ),
              providentHouseContractPayment: loanPoint?.provident_monthly_payment ?? 0,
              commercialHousePayment: loanPoint?.commercial_monthly_payment ?? 0,
              monthlyInvestment: investmentContribution,
              monthlyInvestmentBase: item.investment_contribution_base ?? investmentContribution,
              monthlyInvestmentCashSweep: item.investment_contribution_cash_sweep ?? 0,
              monthlyInvestmentBuyFee: investmentBuyFee,
              monthlyInvestmentNet: Math.max(0, investmentContribution - investmentBuyFee),
              investmentReturn: item.investment_return,
              investmentSellFee,
              investmentSellProceeds: item.investment_sell_proceeds ?? 0,
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
              providentLoanOffsetPayment: providentHouseOffsetPayment,
              providentMonthlyWithdrawal: item.provident_withdrawal,
              backendLedgerEntries: item.ledger_entries
            };
          });
  const hasBackendMonthlySeries = monthlySeries.length > 0;
  const timelineEndMonth = Math.max(
    0,
    monthlySeries[monthlySeries.length - 1]?.month ?? monthlySeries.length - 1,
    loanVisualizationSeries[loanVisualizationSeries.length - 1]?.month ?? 0,
    providentVisualizationSeries[providentVisualizationSeries.length - 1]?.month ?? 0
  );
  const clampTimelineMonth = (month: number) => Math.max(0, Math.min(timelineEndMonth, Math.round(month)));
  const safeSelectedMonthIndex = clampTimelineMonth(selectedMonthIndex);
  const selectedMonth =
    monthlySeries.find((item) => item.month === safeSelectedMonthIndex) ??
    monthlySeries[Math.min(safeSelectedMonthIndex, monthlySeries.length - 1)] ??
    {
      month: 0,
      name: formatMonthDate(timelineBaseDate, 0),
      period: "等待后端计算",
      现金池: 0,
      投资资产: 0,
      固定资产: 0,
      房产估值: 0,
      车辆估值: 0,
      第一辆车估值: 0,
      第二辆车估值: 0,
      总资产: 0,
      家庭总资产: 0,
      公积金余额: 0,
      安全垫: Math.round(plan.required_liquidity_reserve),
      cashIncome: 0,
      livingExpense: 0,
      baseLivingExpense: 0,
      scheduledLivingExpense: 0,
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
      housePayment: 0,
      houseContractPayment: 0,
      providentHouseOffsetPayment: 0,
      providentHousePayment: 0,
      providentHouseContractPayment: 0,
      commercialHousePayment: 0,
      monthlyInvestment: 0,
      monthlyInvestmentBase: 0,
      monthlyInvestmentCashSweep: 0,
      monthlyInvestmentBuyFee: 0,
      monthlyInvestmentNet: 0,
      investmentReturn: 0,
      investmentSellFee: 0,
      investmentSellProceeds: 0,
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
      providentLoanOffsetPayment: 0,
      providentMonthlyWithdrawal: 0,
      backendLedgerEntries: []
    };
  const plannedHomeLoanAmount = Math.max(0, plan.commercial_loan_amount + plan.provident_loan_amount);
  const plannedVehicleLoanAmount = Math.max(0, result.car_loan.loan_principal ?? 0);
  const selectedLoanPoint = loanVisualizationByMonth.get(safeSelectedMonthIndex);
  const selectedProvidentPoint = providentVisualizationByMonth.get(safeSelectedMonthIndex);
  const maxViewStartMonth = Math.max(0, timelineEndMonth - viewWindowMonths + 1);
  const viewEndMonth = Math.min(timelineEndMonth, viewStartMonth + viewWindowMonths - 1);
  const visibleMonthlySeries = useMemo(
    () => monthlySeries.filter((item) => item.month >= viewStartMonth && item.month <= viewEndMonth),
    [monthlySeries, viewEndMonth, viewStartMonth]
  );
  const selectedMonthInputValue = formatMonthInputValue(timelineBaseDate, safeSelectedMonthIndex);
  const timelineStartInputValue = formatMonthInputValue(timelineBaseDate, 0);
  const timelineEndInputValue = formatMonthInputValue(timelineBaseDate, timelineEndMonth);
  const currentViewLabel =
    viewStartMonth <= 0 && viewEndMonth >= timelineEndMonth
      ? "全生命周期"
      : `${formatMonthDate(timelineBaseDate, viewStartMonth)} - ${formatMonthDate(timelineBaseDate, viewEndMonth)}`;
  const viewWindowChoices = [
    { label: "5年", months: 60 },
    { label: "10年", months: 120 },
    { label: "20年", months: 240 },
    { label: "全部", months: timelineEndMonth + 1 }
  ];
  const selectVisualMonth = (month: number) => {
    setSelectedMonthIndex(clampTimelineMonth(month));
  };
  const setMonthFromInput = (value: string) => {
    const parsed = parseMonthValue(value);
    if (!parsed) return;
    const base = { year: timelineBaseDate.getFullYear(), month: timelineBaseDate.getMonth() + 1 };
    selectVisualMonth(compareMonth(parsed, base));
  };
  useEffect(() => {
    const nextSelectedMonth = clampTimelineMonth(selectedMonthIndex);
    if (nextSelectedMonth !== selectedMonthIndex) {
      setSelectedMonthIndex(nextSelectedMonth);
    }
  }, [selectedMonthIndex, timelineEndMonth]);
  useEffect(() => {
    setViewStartMonth((current) => Math.max(0, Math.min(current, maxViewStartMonth)));
  }, [maxViewStartMonth]);
  useEffect(() => {
    setViewStartMonth((current) => {
      const clampedCurrent = Math.max(0, Math.min(current, maxViewStartMonth));
      if (safeSelectedMonthIndex < clampedCurrent) {
        return Math.max(0, Math.min(safeSelectedMonthIndex, maxViewStartMonth));
      }
      if (safeSelectedMonthIndex > clampedCurrent + viewWindowMonths - 1) {
        return Math.max(0, Math.min(safeSelectedMonthIndex - viewWindowMonths + 1, maxViewStartMonth));
      }
      return clampedCurrent;
    });
  }, [maxViewStartMonth, safeSelectedMonthIndex, viewWindowMonths]);
  const loanChartData = useMemo(
    () =>
      loanVisualizationSeries
        .map((item) => ({
          month: item.month,
          总贷款余额: Math.round(item.total_loan_balance),
          房贷余额: Math.round(item.home_loan_balance),
          商贷余额: Math.round(item.commercial_loan_balance),
          公积金贷余额: Math.round(item.provident_loan_balance),
          车贷余额: Math.round(item.vehicle_loan_balance),
          既有贷款余额: Math.round(item.existing_loan_balance),
          当月合同还款: Math.round(item.total_monthly_payment),
          商贷月供: Math.round(item.commercial_monthly_payment),
          公积金贷月供: Math.round(item.provident_monthly_payment),
          公积金账户冲抵: Math.round(item.provident_offset_payment ?? 0),
          当月现金还款: Math.round(item.cash_monthly_payment)
        })),
    [loanVisualizationSeries]
  );
  const visibleLoanChartData = useMemo(
    () => loanChartData.filter((item) => item.month >= viewStartMonth && item.month <= viewEndMonth),
    [loanChartData, viewEndMonth, viewStartMonth]
  );
  const hasLoanChartActivity = loanChartData.some(
    (item) =>
      item.总贷款余额 > 0 ||
      item.房贷余额 > 0 ||
      item.车贷余额 > 0 ||
      item.既有贷款余额 > 0 ||
      item.当月合同还款 > 0 ||
      item.当月现金还款 > 0
  );
  const providentChartData = useMemo(
    () =>
      providentVisualizationSeries
        .map((item) => ({
          month: item.month,
          公积金余额: Math.round(item.balance_end),
          当月缴存: Math.round(item.total_deposit),
          当月利息: Math.round(item.interest),
          还款支出: Math.round(item.loan_offset_payment),
          提取支出: Math.round(item.rent_withdrawal + item.upfront_withdrawal + item.post_transaction_withdrawal + item.agreed_withdrawal)
        })),
    [providentVisualizationSeries]
  );
  const visibleProvidentChartData = useMemo(
    () => providentChartData.filter((item) => item.month >= viewStartMonth && item.month <= viewEndMonth),
    [providentChartData, viewEndMonth, viewStartMonth]
  );
  const selectedMemberIncomeRows = getMemberIncomeRows(safeSelectedMonthIndex);
  const monthlyEmployerHousingFund = selectedMemberIncomeRows.reduce(
    (sum, member) => sum + member.employerHousingFund,
    0
  );
  const investmentSummaryEndMonth = plan.months_to_buy ?? monthlySeries[monthlySeries.length - 1]?.month ?? 0;
  const investmentSummaryRows = monthlySeries.filter((item) => item.month <= investmentSummaryEndMonth);
  const investmentSummaryPoint =
    monthlySeries.find((item) => item.month === investmentSummaryEndMonth) ??
    investmentSummaryRows[investmentSummaryRows.length - 1] ??
    monthlySeries[monthlySeries.length - 1];
  const displayedInvestmentContribution = investmentSummaryRows.reduce(
    (sum, item) => sum + item.monthlyInvestment,
    0
  );
  const displayedInvestmentReturn = investmentSummaryRows.reduce(
    (sum, item) => sum + item.investmentReturn,
    0
  );
  const displayedInvestmentFees = investmentSummaryRows.reduce(
    (sum, item) => sum + item.monthlyInvestmentBuyFee + item.investmentSellFee,
    0
  );
  const investmentEffectAtPurchase = investmentSummaryPoint?.投资资产 ?? 0;
  const visualMinimumCashPoint = monthlySeries.reduce(
    (lowest, item) => (item.现金池 < lowest.现金池 ? item : lowest),
    selectedMonth
  );
  const minimumCashBalance = plan.minimum_cash_balance ?? visualMinimumCashPoint.现金池;
  const minimumCashMonth =
    plan.minimum_cash_balance_month !== undefined && plan.minimum_cash_balance_month !== null
      ? formatMonthDate(timelineBaseDate, plan.minimum_cash_balance_month)
      : visualMinimumCashPoint.name;
  const stressCashShortfall = Math.max(0, plan.cash_stress_shortfall ?? 0, -minimumCashBalance);
  const cashStressOk = plan.cash_stress_ok ?? stressCashShortfall <= 0;
  const stressCashMetricLabel = cashStressOk ? "压力最低现金" : "压力现金缺口";
  const stressCashMetricValue = cashStressOk ? money(minimumCashBalance) : money(stressCashShortfall);
  const stressCashSummary = cashStressOk
    ? `压力情景下最低现金出现在 ${minimumCashMonth}，仍保留 ${money(minimumCashBalance)}。`
    : `压力情景下 ${minimumCashMonth} 会出现 ${money(stressCashShortfall)} 资金缺口；现金不能为负，这表示该方案需要延后买入、降低目标、增加可用现金或重新调整贷款结构。`;
  const purchaseTimelineText =
    plan.months_to_buy === null
      ? "暂无法达到购房现金要求"
      : cashStressOk
        ? `${purchaseYearText} 可执行购房`
        : `${purchaseYearText} 交易现金可达，但压力情景有 ${money(stressCashShortfall)} 现金缺口`;
  const investmentSummaryText =
    monthlyInvestmentSetting > 0
      ? `当前理财方案以 ${money(monthlyInvestmentSetting)}/月为基础定投、${percent(annualReturn)} 年化测算；买入费率 ${percent(investmentBuyFeeRate)}，卖出费率 ${percent(investmentSellFeeRate)}；现金账户不足安全垫时先补现金，超过安全垫的存量现金会按滚动节奏转入投资账户，让现金账户尽量贴近风险防范目标，收益留在投资账户里继续复利。`
      : "当前理财方案未设置月定投或选择只放现金，因此曲线主要体现现有投资账户的收益假设。";
  const advisorTone = cashStressOk && plan.liquidity_ok && plan.post_purchase_cash_flow >= 0
    ? "good"
    : !cashStressOk || plan.post_purchase_cash_flow < 0
      ? "bad"
      : "warn";
  const advisorTitle =
    advisorTone === "good"
      ? "这套方案可以进入细化比较"
      : advisorTone === "bad"
        ? "这套方案需要先修现金安全"
        : "这套方案可执行但要留意压力点";
  const advisorSummary =
    plan.months_to_buy === null
      ? `按当前收入、资产、理财和贷款策略，30 年内仍不能覆盖 ${scenario.name} 的交易现金要求。优先动作是降低目标总价、延后装修或提高可动用现金。`
      : advisorTone === "good"
        ? `${scenario.name} 采用「${plan.variant}」时，预计 ${formatMonthDate(timelineBaseDate, plan.months_to_buy)} 可以买入；交易后现金和买后月结余都留在安全区，适合继续比较居住体验、通勤和房源本身。`
        : advisorTone === "bad"
          ? `${scenario.name} 采用「${plan.variant}」时，时间上可能接近目标，但现金账户在压力情景下不够稳。先不要只看可买时间，应优先调整首付、商贷量、买车节奏或理财变现。`
          : `${scenario.name} 采用「${plan.variant}」时能形成方案，但交易现金、月结余或债务收入比里至少有一项偏紧，适合作为备选而不是默认执行。`;
  const advisorActions = [
    plan.months_to_buy === null
      ? "把目标房源总价、装修现金或首付要求往下调，先让方案进入可达区间。"
      : `把 ${formatMonthDate(timelineBaseDate, plan.months_to_buy)} 当作当前计划锚点，观察这个月的现金流和资产构成。`,
    !cashStressOk
      ? `压力现金缺口约 ${money(stressCashShortfall)}，优先延后购房或减少同步买车支出。`
      : `压力最低现金仍有 ${money(minimumCashBalance)}，下一步主要比较等待时间和幸福指数。`,
    plan.post_purchase_cash_flow < 0
      ? `买后自由现金流为负 ${money(Math.abs(plan.post_purchase_cash_flow))}，需要减少月供、降低用车成本或提高收入阶段。`
      : `买后自由现金流结余约 ${money(plan.post_purchase_cash_flow)}，贷后公积金策略为「${providentStrategyLabel(plan)}」，可继续评估装修和车贷节奏。`
  ];
  const selectedFamilySupportAmount = familySupportAmount(plan);
  const selectedFamilySupportLabel = familySupportLabel(plan);
  const cashNeedBreakdown = [
    { name: "首付", value: plan.planned_down_payment, color: visualColors.cash },
    { name: "交易税费与杂费", value: Math.max(0, plan.upfront_cash_required - plan.planned_down_payment - plan.renovation_cost), color: visualColors.expense },
    { name: "装修现金", value: plan.renovation_included_in_upfront_cash ? plan.renovation_cost : 0, color: visualColors.property },
    { name: "本人公积金首付抵扣", value: -plan.provident_upfront_extractable, color: visualColors.provident },
    { name: selectedFamilySupportLabel || "亲属首付支持", value: -selectedFamilySupportAmount, color: visualColors.safe },
    { name: "实际现金覆盖", value: plan.required_cash_after_pf_extract, color: visualColors.totalAsset }
  ].filter((item) => Math.abs(item.value) > 1);
  const monthlyPressureBreakdown = [
    { name: "公积金贷合同月供", value: plan.provident_monthly_payment, color: visualColors.provident },
    { name: "商贷月供", value: plan.commercial_monthly_payment, color: visualColors.debt },
    { name: "既有债务", value: result.effective_monthly_debt_payment, color: visualColors.expense },
    { name: "通勤/用车", value: selectedMonth.carCost, color: visualColors.vehicle },
    { name: "基础生活支出", value: householdExpenseAt(household, timelineBaseDate, 0), color: visualColors.deduction }
  ].filter((item) => item.value > 0);
  const keyAttributionItems = [
    {
      title: "交易现金为什么是这个数",
      body: `首付 ${money(plan.planned_down_payment)}，税费杂费约 ${money(Math.max(0, plan.upfront_cash_required - plan.planned_down_payment - plan.renovation_cost))}，${plan.renovation_included_in_upfront_cash ? `装修 ${money(plan.renovation_cost)} 也提前占用现金` : "装修默认买后另攒"}；本人公积金首付抵扣 ${money(plan.provident_upfront_extractable)}${familySupportPhrase(plan)}，因此家庭自己还需覆盖 ${money(plan.required_cash_after_pf_extract)}。`
    },
    {
      title: "买后月结余由什么决定",
      body: `月供合计 ${money(plan.total_monthly_payment)}，其中公积金贷 ${money(plan.provident_monthly_payment)}、商贷 ${money(plan.commercial_monthly_payment)}；买后自由现金月结余 ${money(plan.post_purchase_cash_flow)}。系统选择「${providentStrategyLabel(plan)}」，按北京 1 月/7 月集中冲抵规则折算的现金压力改善约 ${money(plan.monthly_post_purchase_pf_withdrawal)}/月，收入构成里不计为工资或自由现金。`
    },
    {
      title: "还款方式怎样影响还清速度",
      body: plan.provident_repayment_advice || "本方案没有可比较的公积金贷款还款方式。"
    },
    {
      title: "理财对买房时间的影响",
      body: `买房前累计定投约 ${money(displayedInvestmentContribution)}，累计收益约 ${money(displayedInvestmentReturn)}，交易手续费约 ${money(displayedInvestmentFees)}；到买房节点，后端推演的投资账户余额约 ${money(investmentEffectAtPurchase)}，交易月会按卖出手续费后进入现金账户。`
    },
    {
      title: "幸福指数为什么不是只看钱",
      body: `幸福指数同时看居住、通勤、教育、现金安全、月结余、负债压力、商贷利息和等待时间；所以更快买入不一定更高分，现金更稳也不一定代表居住体验最好。`
    }
  ];
  const selectChartMonth = (state: unknown) => {
    const chartState = state as
      | {
          activeLabel?: unknown;
          activePayload?: Array<{ payload?: { month?: unknown } }>;
          activeTooltipIndex?: unknown;
        }
      | undefined;
    const payloadMonth = chartState?.activePayload?.find((item) => typeof item.payload?.month === "number")?.payload?.month;
    const labelMonth =
      typeof chartState?.activeLabel === "number"
        ? chartState.activeLabel
        : typeof chartState?.activeLabel === "string"
          ? Number(chartState.activeLabel)
          : null;
    const rawMonth =
      typeof payloadMonth === "number"
        ? payloadMonth
        : labelMonth !== null
          ? labelMonth
          : typeof chartState?.activeTooltipIndex === "number"
            ? viewStartMonth + chartState.activeTooltipIndex
            : null;

    if (typeof rawMonth === "number" && Number.isFinite(rawMonth)) {
      selectVisualMonth(rawMonth);
    }
  };
  const cashFlowData = [
    ...(selectedMonth.cashIncome > 0
      ? selectedMemberIncomeRows.flatMap((member) => [
          { name: `${member.name}税前工资`, amount: Math.round(member.grossMonthly), kind: "income" },
          ...(member.bonusMonthly > 0
            ? [{ name: `${member.name}年终奖入账`, amount: Math.round(member.bonusMonthly), kind: "income" }]
            : []),
          ...(member.otherMonthly > 0
            ? [{ name: `${member.name}其他收入`, amount: Math.round(member.otherMonthly), kind: "income" }]
            : []),
          ...(member.nonTaxableMonthly > 0
            ? [{ name: `${member.name}非税收入`, amount: Math.round(member.nonTaxableMonthly), kind: "income" }]
            : []),
          { name: `${member.name}税后现金`, amount: Math.round(member.netMonthly), kind: "income" }
        ])
      : []),
    ...(selectedMonth.cashIncome > 0
      ? selectedMemberIncomeRows.flatMap((member) => [
          { name: `${member.name}社保`, amount: -Math.round(member.personalSocial), kind: "deduction" },
          { name: `${member.name}公积金`, amount: -Math.round(member.personalHousingFund), kind: "deduction" },
          { name: `${member.name}个税`, amount: -Math.round(member.incomeTax), kind: "deduction" },
          ...(member.extraCashExpense > 0
            ? [{ name: `${member.name}自缴/额外支出`, amount: -Math.round(member.extraCashExpense), kind: "expense" }]
            : [])
        ])
      : []),
    { name: "定投买入净额", amount: -Math.round(selectedMonth.monthlyInvestmentNet), kind: "asset" },
    { name: "理财买入手续费", amount: -Math.round(selectedMonth.monthlyInvestmentBuyFee), kind: "expense" },
    { name: "复利收益留存", amount: Math.round(selectedMonth.investmentReturn), kind: "asset" },
    { name: "投资卖出到账", amount: Math.round(selectedMonth.investmentSellProceeds), kind: "income" },
    { name: "投资卖出手续费", amount: -Math.round(selectedMonth.investmentSellFee), kind: "expense" },
    { name: "公积金现金到账", amount: Math.round(selectedMonth.providentRentWithdrawal + selectedMonth.providentPostTransactionWithdrawal + (selectedMonth.providentAgreedWithdrawal ?? 0)), kind: "income" },
    { name: "公积金冲抵月供", amount: Math.round(selectedMonth.providentLoanOffsetPayment ?? 0), kind: "asset" },
    { name: "基础生活支出", amount: -Math.round(selectedMonth.baseLivingExpense), kind: "expense" },
    ...selectedMonth.scheduledExpenseRows.map((item) => ({
      name: item.name,
      amount: -Math.round(item.amount),
      kind: "expense"
    })),
    { name: "债务还款", amount: -Math.round(selectedMonth.debtPayment), kind: "expense" },
    { name: "通勤/用车成本", amount: -Math.round(selectedMonth.carCost), kind: "expense" },
    { name: "房贷现金还款", amount: -Math.round(selectedMonth.housePayment), kind: "expense" },
    { name: "公积金账户代扣房贷", amount: Math.round(selectedMonth.providentHouseOffsetPayment ?? 0), kind: "asset" },
    { name: "交易现金", amount: Math.round(selectedMonth.purchaseCashIn - selectedMonth.purchaseCashOut), kind: "expense" },
    { name: "当月现金净流入", amount: Math.round(selectedMonth.monthlyCashDelta), kind: "result" }
  ].filter((item) => item.amount !== 0 || item.kind === "result");
  const cashFlowChartHeight = Math.max(360, cashFlowData.length * 28);
  const cashFlowColor = (kind: string) => {
    if (kind === "income") return visualColors.cash;
    if (kind === "asset") return visualColors.investment;
    if (kind === "deduction") return visualColors.deduction;
    if (kind === "result") return selectedMonth.monthlyCashDelta >= 0 ? visualColors.safe : visualColors.danger;
    return visualColors.expense;
  };
  const selectedMonthDrivers = cashFlowData
    .filter((item) => item.kind !== "result" && Math.abs(item.amount) > 0)
    .sort((left, right) => Math.abs(right.amount) - Math.abs(left.amount))
    .slice(0, 5);
  const monthAdvisorText =
    selectedMonth.monthlyCashDelta >= 0
      ? `${selectedMonth.name} 现金净流入 ${money(selectedMonth.monthlyCashDelta)}，这个月现金账户在变厚。主要正向项来自工资入账、公积金现金到账、冲还贷抵扣、投资卖出或收益留存；主要压力项见下方归因。`
      : `${selectedMonth.name} 现金净流出 ${money(Math.abs(selectedMonth.monthlyCashDelta))}，这个月需要确认是否是交易、定投、车贷、房贷或生活支出的阶段性压力。`;
  const incomeMemberLegendData = selectedMemberIncomeRows
    .flatMap((member) => [
      { name: `${member.name}工资净入账`, value: Math.max(0, member.salaryNetMonthly) },
      { name: `${member.name}奖金净入账`, value: Math.max(0, member.bonusNetMonthly) },
      { name: `${member.name}其他净入账`, value: Math.max(0, member.otherNetMonthly) },
      { name: `${member.name}非税收入`, value: Math.max(0, member.nonTaxableNetMonthly) },
    ])
    .filter((item) => item.value > 0);
  const incomeHouseholdFlowData = [
    { name: "复利收益", value: selectedMonth.investmentReturn },
    { name: "租房公积金提取", value: selectedMonth.providentRentWithdrawal },
    { name: "交易后公积金回流", value: selectedMonth.providentPostTransactionWithdrawal },
    { name: "投资卖出到账", value: selectedMonth.investmentSellProceeds },
    { name: "交易现金流入", value: Math.max(0, selectedMonth.purchaseCashIn - selectedMonth.investmentSellProceeds) }
  ];
  const incomeLegendData = [
    ...incomeMemberLegendData,
    ...incomeHouseholdFlowData.filter((item) => item.value > 0)
  ];
  const incomePieData = [
    ...incomeMemberLegendData,
    ...incomeHouseholdFlowData
  ].filter((item) => item.value > 0);
  const expensePieData = [
    ...selectedMemberIncomeRows.flatMap((member) => [
      { name: `${member.name}个人社保`, value: member.personalSocial },
      { name: `${member.name}个人公积金`, value: member.personalHousingFund },
      { name: `${member.name}个税`, value: member.incomeTax },
      { name: `${member.name}阶段额外支出`, value: member.extraCashExpense }
    ]),
    { name: "基础生活支出", value: selectedMonth.baseLivingExpense },
    ...selectedMonth.scheduledExpenseRows.map((item) => ({ name: item.name, value: item.amount })),
    { name: "普通既有债务", value: selectedMonth.regularDebtPayment },
    { name: "目前贷款", value: selectedMonth.phasedLoanPayment },
    { name: "无车通勤成本", value: selectedMonth.noCarCommuteCost },
    { name: "车辆车贷", value: selectedMonth.firstCarLoanPayment },
    { name: "车辆电费", value: selectedMonth.firstCarEnergyCost },
    { name: "车辆保险", value: selectedMonth.firstCarInsuranceCost },
    { name: "车辆保养", value: selectedMonth.firstCarMaintenanceCost },
    { name: "车辆停车", value: selectedMonth.firstCarParkingCost },
    { name: "第二辆车车贷", value: selectedMonth.secondCarLoanPayment },
    { name: "第二辆车电费", value: selectedMonth.secondCarEnergyCost },
    { name: "第二辆车保险", value: selectedMonth.secondCarInsuranceCost },
    { name: "第二辆车保养", value: selectedMonth.secondCarMaintenanceCost },
    { name: "第二辆车停车", value: selectedMonth.secondCarParkingCost },
    { name: "公积金贷现金支付", value: selectedMonth.providentHousePayment },
    { name: "公积金账户代扣", value: selectedMonth.providentHouseOffsetPayment ?? 0 },
    { name: "商贷月供", value: selectedMonth.commercialHousePayment },
    { name: "理财买入净额", value: selectedMonth.monthlyInvestmentNet },
    { name: "理财手续费", value: selectedMonth.monthlyInvestmentBuyFee + selectedMonth.investmentSellFee },
    { name: "购房交易现金", value: selectedMonth.houseTransactionCashOut },
    { name: "车辆首付", value: selectedMonth.carDownPaymentCashOut },
    { name: "第二辆车首付", value: selectedMonth.secondCarDownPaymentCashOut }
  ].filter((item) => item.value > 0);
  const pieTooltipFormatter = (value: unknown) => money(Number(value));
  const cashFlowTooltipFormatter = (value: unknown, _name: unknown, item: { payload?: { name?: string } }) => [
    money(Number(value)),
    item.payload?.name ?? "金额"
  ];
  const providentInflowPieData = [
    { name: "个人缴存", value: selectedProvidentPoint?.personal_deposit ?? 0 },
    { name: "单位缴存", value: selectedProvidentPoint?.employer_deposit ?? 0 },
    { name: "账户利息", value: selectedProvidentPoint?.interest ?? 0 }
  ].filter((item) => item.value > 0);
  const providentOutflowPieData = [
    { name: "租房提取", value: selectedProvidentPoint?.rent_withdrawal ?? 0 },
    { name: "交易前提取", value: selectedProvidentPoint?.upfront_withdrawal ?? 0 },
    { name: "交易后提取", value: selectedProvidentPoint?.post_transaction_withdrawal ?? 0 },
    { name: "购后约定提取", value: selectedProvidentPoint?.agreed_withdrawal ?? 0 },
    { name: "公积金冲还贷", value: selectedProvidentPoint?.loan_offset_payment ?? 0 }
  ].filter((item) => item.value > 0);
  const cashFlowGroups: Array<{ title: string; rows: Array<[string, number]> }> = [
    {
      title: "收入与入账",
      rows: [
        ...(selectedMonth.cashIncome > 0
          ? selectedMemberIncomeRows.flatMap((member): Array<[string, number]> => [
              [`${member.name}月税前工资`, member.grossMonthly],
              ...(member.bonusMonthly > 0 ? [[`${member.name}年终奖入账`, member.bonusMonthly] as [string, number]] : []),
              ...(member.otherMonthly > 0 ? [[`${member.name}其他收入折月`, member.otherMonthly] as [string, number]] : []),
              ...(member.nonTaxableMonthly > 0 ? [[`${member.name}非税收入`, member.nonTaxableMonthly] as [string, number]] : []),
              [`${member.name}税后现金工资`, member.netMonthly]
            ])
          : []),
        ["复利收益留存", selectedMonth.investmentReturn],
        ["投资卖出到账", selectedMonth.investmentSellProceeds],
        ["当月公积金现金到账", selectedMonth.providentRentWithdrawal + selectedMonth.providentPostTransactionWithdrawal + (selectedMonth.providentAgreedWithdrawal ?? 0)],
        ["单位公积金缴存", monthlyEmployerHousingFund],
        ["公积金冲抵月供（非收入）", selectedMonth.providentLoanOffsetPayment ?? 0]
      ]
    },
    {
      title: "工资扣缴",
      rows: [
        ...(selectedMonth.cashIncome > 0
          ? selectedMemberIncomeRows.flatMap((member): Array<[string, number]> => [
              [`${member.name}个人社保`, -member.personalSocial],
              [`${member.name}个人公积金`, -member.personalHousingFund],
              ...((member.elderlyCareDeduction ?? 0) > 0
                ? [[`${member.name}赡养老人专项附加扣除`, member.elderlyCareDeduction ?? 0] as [string, number]]
                : []),
              [`${member.name}工资个税（累计预扣）`, -member.incomeTax],
              ...(member.extraCashExpense > 0 ? [[`${member.name}自缴社保/额外现金支出`, -member.extraCashExpense] as [string, number]] : [])
            ])
          : [])
      ]
    },
    {
      title: "购房后月支出",
      rows: [
        ["基础生活支出", -selectedMonth.baseLivingExpense],
        ...selectedMonth.scheduledExpenseRows.map((item): [string, number] => [item.name, -item.amount]),
        ["债务与目前贷款", -selectedMonth.debtPayment],
        ["通勤/用车", -selectedMonth.carCost],
        ["房贷现金还款", -selectedMonth.housePayment],
        ["公积金账户代扣房贷", selectedMonth.providentHouseOffsetPayment ?? 0],
        ["基础定投现金支出", -selectedMonth.monthlyInvestmentBase],
        ["超额现金滚入支出", -selectedMonth.monthlyInvestmentCashSweep],
        ["定投买入净额", -selectedMonth.monthlyInvestmentNet],
        ["理财买入手续费", -selectedMonth.monthlyInvestmentBuyFee],
        ["投资卖出手续费", -selectedMonth.investmentSellFee],
        ["交易现金净额", selectedMonth.purchaseCashIn - selectedMonth.purchaseCashOut]
      ]
    },
    {
      title: "月度结果",
      rows: [
        ["当月现金净流入", selectedMonth.monthlyCashDelta],
        ["月末现金账户", selectedMonth.现金池],
        ["月末投资账户", selectedMonth.投资资产],
        ["月末公积金余额", selectedMonth.公积金余额]
      ]
    }
  ];
  const selectedMonthExplanationItems = [
    {
      title: "收入为什么这样入账",
      body:
        selectedMonth.cashIncome > 0
          ? `工资按各家庭成员当前生效的收入阶段逐月入账；年终奖不均摊到 12 个月，只在发放月进入现金流，所以 ${selectedMonth.name} 会看到对应月份的跳升或回落。税后现金工资已经扣除了个人社保、个人公积金和当月累计预扣个税。`
          : `${selectedMonth.name} 没有工资现金入账，通常是收入阶段尚未开始、已进入失业/退休等自动情景，或该月是交易月只展示资产转换。`
    },
    {
      title: "年度/阶段性支出为什么不是均摊",
      body:
        selectedMonth.firstCarInsuranceCost + selectedMonth.firstCarMaintenanceCost + selectedMonth.secondCarInsuranceCost + selectedMonth.secondCarMaintenanceCost > 0
          ? `车辆保险和保养按实际发生月计入现金流，不做月度均摊；当前月出现 ${money(selectedMonth.firstCarInsuranceCost + selectedMonth.secondCarInsuranceCost)} 保险和 ${money(selectedMonth.firstCarMaintenanceCost + selectedMonth.secondCarMaintenanceCost)} 保养，并按设定年增长率随持有年份递增。`
          : `车辆保险、保养这类年度支出不会平均摊到每个月；只有到车辆购入后的年度节点才进入当月现金流，并会按设定年增长率随持有年份递增。平时只保留电费、停车、通勤等更接近月度发生的项目。`
    },
    {
      title: "贷款还款策略为什么这样",
      body:
        selectedLoanPoint && selectedLoanPoint.total_monthly_payment > 0
          ? `房贷、车贷和既有贷款都属于贷款。当前月合同还款 ${money(selectedLoanPoint.total_monthly_payment)}，其中房贷 ${money(selectedLoanPoint.home_monthly_payment)}、车贷 ${money(selectedLoanPoint.vehicle_monthly_payment)}、既有债务 ${money(selectedLoanPoint.existing_monthly_payment)}；公积金冲还贷只降低现金还款压力，不把它记成收入。`
          : `当前月还没有实际贷款还款进入现金流；如果计划中有房贷或车贷，它们会从买房/买车发生月起进入贷款余额与月供曲线。`
    },
    {
      title: "公积金账户为什么这样流动",
      body: `公积金账户由后端逐月计算：个人缴存和单位缴存进入账户，账户利息留在账户内；购房前租房提取按季度到账，买房后不再把租房提取当作后续来源。若采用北京冲还贷策略，支出只在规则口径下的冲抵月份出现，属于账户支出，不属于自由现金收入。`
    },
    {
      title: "理财定投为什么这样执行",
      body:
        selectedMonth.monthlyInvestment > 0
          ? `本月定投 ${money(selectedMonth.monthlyInvestment)}，买入净额 ${money(selectedMonth.monthlyInvestmentNet)}，手续费 ${money(selectedMonth.monthlyInvestmentBuyFee)}。策略先保护现金安全垫：当月结余用于基础定投，安全垫以上的存量现金会分期追加到投资账户；若当月净流入为负，通常代表主动调仓而不是日常支出失控。`
          : `本月没有执行定投，通常是月结余不足、现金账户低于安全垫，或理财策略选择了现金保守模式。已有投资账户的收益仍留在投资账户中复利。`
    },
    {
      title: "当月净流入怎么看",
      body:
        selectedMonth.monthlyCashDelta >= 0
          ? `${selectedMonth.name} 现金净流入为 ${money(selectedMonth.monthlyCashDelta)}，说明工资、到账、冲抵或投资变现足以覆盖本月支出和定投。`
          : `${selectedMonth.name} 现金净流出为 ${money(Math.abs(selectedMonth.monthlyCashDelta))}。如果不是交易、买车首付、年度保险保养或装修等特殊时点，就应优先检查定投、用车、房贷和家庭支出是否需要调整。`
    }
  ];
  const happinessData = result.purchase_plan_analyses.map((item) => ({
    name: item.variant,
    幸福指数: Number(item.happiness_score.toFixed(1)),
    selected: item.variant === plan.variant
  }));
  const timelineItems = (result.plan_events ?? [])
    .filter((item) => item.plan_variant === plan.variant)
    .sort((left, right) => left.month - right.month || left.title.localeCompare(right.title, "zh-Hans-CN"))
    .map((item) => ({
      month: item.month,
      label: `${formatMonthDate(timelineBaseDate, item.month)} · ${item.title}`,
      value: item.detail,
      severity: item.severity
    }));

  return (
    <>
      <section className={`advisor-panel ${advisorTone}`}>
        <div>
          <PanelTitle icon={<ShieldCheck size={18} />} title="顾问摘要" compact />
          <h3>{advisorTitle}</h3>
          <p>{advisorSummary}</p>
        </div>
        <div className="advisor-actions">
          {advisorActions.map((action) => (
            <span key={action}>
              <CheckCircle2 size={15} />
              {action}
            </span>
          ))}
        </div>
      </section>

      <div className="metric-grid">
        <Metric label="预计买入时间" value={purchaseYearText} tone={plan.months_to_buy === null ? "bad" : "good"} />
        <Metric label="交易现金需覆盖" value={money(requiredCashAfterPf)} />
        <Metric label="购后安全垫" value={money(plan.required_liquidity_reserve)} />
        <Metric label="交易当下现金" value={money(plan.cash_after_transaction)} tone={plan.liquidity_ok ? "good" : "warn"} />
        <Metric label="购房后预计提取到账" value={money(plan.provident_post_transaction_extractable)} />
        <Metric label="到账后现金" value={money(plan.cash_after_purchase)} tone={plan.liquidity_ok ? "good" : "warn"} />
        <Metric label={stressCashMetricLabel} value={stressCashMetricValue} tone={cashStressOk ? "good" : "bad"} />
        <Metric label="买后自由月结余" value={money(plan.post_purchase_cash_flow)} tone={plan.post_purchase_cash_flow >= 0 ? "good" : "bad"} />
        <Metric label="装修资金" value={renovationTimingText} tone={plan.months_to_renovation === null ? "warn" : "good"} />
        <Metric label="负债收入比" value={percent(plan.debt_to_income_ratio)} tone={plan.debt_to_income_ratio > 0.5 ? "bad" : "warn"} />
        <Metric label="幸福指数" value={`${plan.happiness_score.toFixed(1)} / 10`} tone={plan.happiness_score >= 7 ? "good" : plan.happiness_score >= 5 ? "warn" : "bad"} />
        <Metric label="理财月定投" value={money(monthlyInvestmentSetting)} />
        <Metric label="买房前理财增益" value={money(investmentEffectAtPurchase)} tone={investmentEffectAtPurchase >= 0 ? "good" : "warn"} />
        <Metric label="累计定投转入" value={money(displayedInvestmentContribution)} />
        <Metric label="累计投资收益" value={money(displayedInvestmentReturn)} tone={displayedInvestmentReturn >= 0 ? "good" : "warn"} />
        <Metric label="累计交易手续费" value={money(displayedInvestmentFees)} tone={displayedInvestmentFees > 0 ? "warn" : undefined} />
      </div>
      <p className={cashStressOk ? "field-hint" : "field-hint danger-text"}>
        {stressCashSummary}
      </p>

      <section className="visual-story-block">
        <div className="strategy-panel-head">
          <PanelTitle icon={<WalletCards size={18} />} title="关键归因" compact />
          <span>把结果拆成可调整的原因，便于反推策略。</span>
        </div>
        <div className="attribution-grid">
          {keyAttributionItems.map((item) => (
            <article key={item.title}>
              <strong>{item.title}</strong>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
        <div className="attribution-bars">
          <div>
            <strong>交易现金构成</strong>
            {cashNeedBreakdown.map((item) => (
              <span key={item.name}>
                <i style={{ background: item.color }} />
                <em>{item.name}</em>
                <b>{money(item.value)}</b>
              </span>
            ))}
          </div>
          <div>
            <strong>买后月压力构成</strong>
            {monthlyPressureBreakdown.map((item) => (
              <span key={item.name}>
                <i style={{ background: item.color }} />
                <em>{item.name}</em>
                <b>{money(item.value)}</b>
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="loan-structure visual-story-block">
        <PanelTitle icon={<WalletCards size={18} />} title="资金结构" compact />
        <div className="loan-stack" aria-label="资金结构">
          <span
            className="down-payment"
            style={{ width: `${Math.max(0, (plan.planned_down_payment / scenario.total_price) * 100)}%` }}
          />
          <span
            className="provident-loan"
            style={{ width: `${Math.max(0, (plan.provident_loan_amount / scenario.total_price) * 100)}%` }}
          />
          <span
            className="commercial-loan"
            style={{ width: `${Math.max(0, (plan.commercial_loan_amount / scenario.total_price) * 100)}%` }}
          />
        </div>
        <div className="loan-legend">
          <span><i className="down-payment" />首付 {money(plan.planned_down_payment)}</span>
          <span><i className="provident-loan" />公积金贷 {money(plan.provident_loan_amount)} · {plan.provident_loan_years}年 · 上限 {money(plan.provident_policy_cap)} · {repaymentMethodLabels[plan.provident_repayment_method]}</span>
          <span><i className="commercial-loan" />商贷 {money(plan.commercial_loan_amount)} · {plan.commercial_loan_years}年 · {repaymentMethodLabels[plan.commercial_repayment_method]}</span>
        </div>
      </section>

      <section className="linked-month-panel">
        <div>
          <PanelTitle icon={<CalendarClock size={18} />} title="联动月份查看" compact />
          <p>{monthAdvisorText}</p>
        </div>
        <div className="month-control-grid">
          <label className="month-picker">
            <span>精确年月</span>
            <input
              type="month"
              min={timelineStartInputValue}
              max={timelineEndInputValue}
              value={selectedMonthInputValue}
              onInput={(event) => setMonthFromInput(event.currentTarget.value)}
              onChange={(event) => setMonthFromInput(event.target.value)}
            />
          </label>
          <label className="month-slider">
            <span>查看月份</span>
            <input
              type="range"
              min={0}
              max={timelineEndMonth}
              value={safeSelectedMonthIndex}
              onInput={(event) => selectVisualMonth(Number(event.currentTarget.value))}
              onChange={(event) => selectVisualMonth(Number(event.target.value))}
            />
            <strong>{selectedMonth.name}</strong>
          </label>
          <div className="chart-window-control">
            <span>曲线窗口</span>
            <div className="segmented-control">
              {viewWindowChoices.map((choice) => (
                <button
                  key={choice.label}
                  className={viewWindowMonths === choice.months ? "active" : ""}
                  type="button"
                  onClick={() => setViewWindowMonths(choice.months)}
                >
                  {choice.label}
                </button>
              ))}
            </div>
          </div>
          <label className="month-slider window-slider">
            <span>窗口位置</span>
            <input
              type="range"
              min={0}
              max={maxViewStartMonth}
              value={Math.min(viewStartMonth, maxViewStartMonth)}
              disabled={maxViewStartMonth <= 0}
              onInput={(event) => setViewStartMonth(Number(event.currentTarget.value))}
              onChange={(event) => setViewStartMonth(Number(event.target.value))}
            />
            <strong>{currentViewLabel}</strong>
          </label>
        </div>
        <div className="month-driver-list">
          {selectedMonthDrivers.map((item) => (
            <span className={item.amount >= 0 ? "positive" : "negative"} key={item.name}>
              <em>{item.name}</em>
              <strong>{money(item.amount)}</strong>
            </span>
          ))}
        </div>
      </section>

      <div className="visual-grid">
        <section className="chart-block asset-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title="资产" compact />
          {hasBackendMonthlySeries ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                data={visibleMonthlySeries}
                onMouseMove={selectChartMonth}
                onClick={selectChartMonth}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis {...chartXAxisProps} />
                <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
                <Tooltip formatter={(value) => money(Number(value))} />
                <Line type="monotone" dataKey="现金池" name="现金账户" stroke={visualColors.cash} strokeWidth={2.3} dot={false} />
                <Line type="monotone" dataKey="投资资产" name="投资账户" stroke={visualColors.investment} strokeWidth={2.3} dot={false} />
                <Line type="monotone" dataKey="总资产" name="现金+投资账户" stroke={visualColors.totalAsset} strokeWidth={2.8} dot={false} />
                <Line type="monotone" dataKey="安全垫" stroke={visualColors.warning} strokeWidth={2.1} strokeDasharray="5 5" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty-state">
              <strong>等待后端生成账户曲线</strong>
              <span>资产、现金、投资和公积金变化只展示后端推演结果；当前没有可用月度序列。</span>
            </div>
          )}
          <div className="month-inspector">
            <div>
              <span>当前选中月份</span>
              <strong>{selectedMonth.name}</strong>
              <small>{selectedMonth.period}</small>
            </div>
            <div>
              <span>现金账户</span>
              <strong>{money(selectedMonth.现金池)}</strong>
              <small>当月净流入 {money(selectedMonth.monthlyCashDelta)}，{stressCashSummary}</small>
            </div>
            <div>
              <span>投资账户</span>
              <strong>{money(selectedMonth.投资资产)}</strong>
              <small>定投 {money(selectedMonth.monthlyInvestment)}，买入净额 {money(selectedMonth.monthlyInvestmentNet)}，手续费 {money(selectedMonth.monthlyInvestmentBuyFee)}，复利收益 {money(selectedMonth.investmentReturn)}</small>
            </div>
            <div>
              <span>固定资产</span>
              <strong>{money(selectedMonth.固定资产)}</strong>
              <small>房产 {money(selectedMonth.房产估值)}，车辆 {money(selectedMonth.车辆估值)}</small>
            </div>
          </div>
          <div className="loan-legend investment-legend">
            <span><i className="cash-line" />现金账户：首付、安全垫和日常结余</span>
            <span><i className="investment-line" />投资账户：当前投资、定投净买入和复利收益</span>
            <span><i className="total-line" />现金+投资账户：不含公积金账户</span>
          </div>
          <p className="field-hint">
            {investmentSummaryText} 到选中买房时点，后端推演的投资账户余额约 {money(investmentEffectAtPurchase)}。
          </p>
        </section>

        <section className="chart-block fixed-asset-chart">
          <PanelTitle icon={<Home size={18} />} title="固定资产" compact />
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={visibleMonthlySeries}
              onMouseMove={selectChartMonth}
              onClick={selectChartMonth}
              margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis {...chartXAxisProps} />
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
              <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
              <Line type="monotone" dataKey="房产估值" stroke={visualColors.property} strokeWidth={2.4} dot={false} />
              <Line type="monotone" dataKey="车辆估值" stroke={visualColors.vehicle} strokeWidth={2.2} dot={false} />
              <Line type="monotone" dataKey="固定资产" stroke={visualColors.fixedAsset} strokeWidth={2.8} dot={false} />
              <Line type="monotone" dataKey="家庭总资产" name="账户与固定资产合计" stroke={visualColors.totalAsset} strokeWidth={2.1} strokeDasharray="4 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="month-inspector fixed-asset-inspector">
            <div>
              <span>房产估值</span>
              <strong>{money(selectedMonth.房产估值)}</strong>
              <small>{selectedMonth.房产估值 > 0 ? `${scenario.name} 已计入固定资产` : "购房前暂未计入房产资产"}</small>
            </div>
            <div>
              <span>车辆估值</span>
              <strong>{money(selectedMonth.车辆估值)}</strong>
              <small>第一辆 {money(selectedMonth.第一辆车估值)}，第二辆 {money(selectedMonth.第二辆车估值)}</small>
            </div>
            <div>
              <span>固定资产合计</span>
              <strong>{money(selectedMonth.固定资产)}</strong>
              <small>房产按目标总价、车辆按折旧年限线性估算</small>
            </div>
            <div>
              <span>账户与固定资产合计</span>
              <strong>{money(selectedMonth.家庭总资产)}</strong>
              <small>现金账户、投资账户和固定资产合计；公积金账户单独查看</small>
            </div>
          </div>
          <div className="loan-legend fixed-asset-legend">
            <span><i className="home-asset-line" />房产估值</span>
            <span><i className="car-asset-line" />车辆估值</span>
            <span><i className="fixed-asset-line" />固定资产合计</span>
            <span><i className="net-asset-line" />账户与固定资产合计</span>
          </div>
          <p className="field-hint">
            固定资产用于观察资产结构，不直接代表可用于首付或应急的现金。房产按目标房源总价入账；车辆从购车月起按折旧年限线性递减，未考虑市场溢价、房价涨跌或真实二手车成交价。
          </p>
        </section>

        <section className="chart-block loan-balance-chart">
          <PanelTitle icon={<Banknote size={18} />} title="贷款余额与月供" compact />
          {hasLoanChartActivity ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart
                data={visibleLoanChartData}
                onMouseMove={selectChartMonth}
                onClick={selectChartMonth}
                margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis {...chartXAxisProps} />
                <YAxis yAxisId="balance" tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
                <YAxis yAxisId="payment" orientation="right" tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
                <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
                <Line yAxisId="balance" type="monotone" dataKey="总贷款余额" stroke={visualColors.debt} strokeWidth={2.8} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="商贷余额" stroke={visualColors.property} strokeWidth={2.4} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="公积金贷余额" stroke={visualColors.provident} strokeWidth={2.4} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="车贷余额" stroke={visualColors.vehicle} strokeWidth={2.2} dot={false} />
                <Line yAxisId="balance" type="monotone" dataKey="既有贷款余额" stroke={visualColors.expense} strokeWidth={2.1} strokeDasharray="4 4" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="当月合同还款" stroke={visualColors.warning} strokeWidth={2.0} strokeDasharray="3 3" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="公积金账户冲抵" stroke={visualColors.provident} strokeWidth={2.0} strokeDasharray="2 5" dot={false} />
                <Line yAxisId="payment" type="monotone" dataKey="当月现金还款" stroke={visualColors.totalAsset} strokeWidth={2.1} strokeDasharray="6 4" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="chart-empty-state">
              <strong>当前方案没有贷款账户变化</strong>
              <span>
                当前已选策略没有商贷、公积金贷、车贷或可推演余额的既有贷款。
              </span>
            </div>
          )}
          <div className="month-inspector loan-balance-inspector">
            <div>
              <span>总贷款余额</span>
              <strong>{money(selectedLoanPoint?.total_loan_balance ?? 0)}</strong>
              <small>后端按已选购房方案、车贷和目前贷款逐月测算</small>
            </div>
            <div>
              <span>房贷余额</span>
              <strong>{money(selectedLoanPoint?.home_loan_balance ?? 0)}</strong>
              <small>商贷 {money(selectedLoanPoint?.commercial_loan_balance ?? 0)}，公积金贷 {money(selectedLoanPoint?.provident_loan_balance ?? 0)}；计划房贷 {money(plannedHomeLoanAmount)}</small>
            </div>
            <div>
              <span>车贷与既有贷款</span>
              <strong>{money((selectedLoanPoint?.vehicle_loan_balance ?? 0) + (selectedLoanPoint?.existing_loan_balance ?? 0))}</strong>
              <small>车贷 {money(selectedLoanPoint?.vehicle_loan_balance ?? 0)}，既有贷款 {money(selectedLoanPoint?.existing_loan_balance ?? 0)}；计划车贷 {money(plannedVehicleLoanAmount)}</small>
            </div>
            <div>
              <span>当月还款压力</span>
              <strong>{money(selectedLoanPoint?.cash_monthly_payment ?? 0)}</strong>
              <small>合同还款 {money(selectedLoanPoint?.total_monthly_payment ?? 0)}；公积金账户冲抵 {money(selectedLoanPoint?.provident_offset_payment ?? 0)}</small>
            </div>
          </div>
          <div className="loan-legend loan-balance-legend">
            <span><i className="total-loan-line" />总贷款余额</span>
            <span><i className="home-loan-line" />商贷余额</span>
            <span><i className="provident-loan" />公积金贷余额</span>
            <span><i className="vehicle-loan-line" />车贷余额</span>
            <span><i className="existing-loan-line" />既有贷款余额</span>
            <span><i className="provident-loan" />公积金账户冲抵</span>
            <span><i className="cash-payment-line" />当月现金还款</span>
          </div>
          <p className="field-hint">
            贷款余额由后端统一生成，前端只展示结果。目前贷款按“未开始计息、只还利息、进入等额还款”逐月推进；普通既有债务如果没有本金配置，只计入还款压力，不推导余额。
          </p>
        </section>

        <section className="chart-block provident-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title="公积金账户变化" compact />
          <ResponsiveContainer width="100%" height={240}>
            <LineChart
              data={visibleProvidentChartData}
              onMouseMove={selectChartMonth}
              onClick={selectChartMonth}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis {...chartXAxisProps} />
              <YAxis tickLine={false} axisLine={false} width={58} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
              <Tooltip formatter={(value) => money(Number(value))} labelFormatter={(value) => formatMonthDate(timelineBaseDate, Number(value))} />
              <Line type="monotone" dataKey="公积金余额" stroke={visualColors.provident} strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="当月缴存" stroke={visualColors.investment} strokeWidth={1.8} dot={false} />
              <Line type="monotone" dataKey="还款支出" stroke={visualColors.debt} strokeWidth={2.1} strokeDasharray="5 4" dot={false} />
              <Line type="monotone" dataKey="提取支出" stroke={visualColors.warning} strokeWidth={1.8} strokeDasharray="3 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="cash-flow-sections provident-month-detail">
            <div className="cash-flow-section">
              <strong>{selectedMonth.name} 公积金流水</strong>
              <Row label="月初余额" value={money(selectedProvidentPoint?.balance_start ?? 0)} />
              <Row label="当月缴存" value={money(selectedMonth.providentDeposit)} />
              <Row label="当月利息估算" value={money(selectedMonth.providentInterest)} />
              <Row label="租房季度提取到账" value={money(selectedMonth.providentRentWithdrawal)} />
              <Row label="购后约定提取" value={money(selectedMonth.providentAgreedWithdrawal ?? 0)} />
              <Row label="公积金冲还贷支出" value={money(selectedMonth.providentLoanOffsetPayment ?? 0)} />
              <Row label="交易前/交易后提取" value={money(selectedMonth.providentUpfrontWithdrawal + selectedMonth.providentPostTransactionWithdrawal)} />
              <Row label="月末余额" value={money(selectedMonth.公积金余额)} />
            </div>
          </div>
          <div className="cash-flow-pies provident-pies">
            {[
              { title: "公积金账户收入", data: providentInflowPieData },
              { title: "公积金账户支出", data: providentOutflowPieData }
            ].map((pie) => (
              <div className="cash-flow-pie" key={pie.title}>
                <strong>{pie.title}</strong>
                {pie.data.length > 0 ? (
                  <div className="pie-layout">
                    <ResponsiveContainer width="100%" height={190}>
                      <PieChart>
                        <Tooltip formatter={pieTooltipFormatter} />
                        <Pie data={pie.data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                          {pie.data.map((item, index) => (
                            <Cell key={`${pie.title}-${item.name}`} fill={piePalette[index % piePalette.length]} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pie-legend">
                      {pie.data.map((item, index) => (
                        <span key={`${pie.title}-legend-${item.name}`}>
                          <i style={{ background: piePalette[index % piePalette.length] }} />
                          <em>{item.name}</em>
                          <strong>{money(item.value)}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="field-hint">当前月份没有可展示的{pie.title}。</p>
                )}
              </div>
            ))}
          </div>
          <p className="field-hint">
            公积金账户变化由后端逐月计算。北京冲还贷按规则包口径在 1 月、7 月合同约定还款日优先冲抵公积金贷款，冲抵资金属于公积金账户支出，不作为自由现金收入。
          </p>
        </section>

        <section className="chart-block cash-flow-chart">
          <PanelTitle icon={<TrendingUp size={18} />} title={`${selectedMonth.name} 月现金流`} compact />
          <ResponsiveContainer width="100%" height={cashFlowChartHeight}>
            <BarChart data={cashFlowData} layout="vertical" margin={{ top: 4, right: 14, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
              <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={isCompactChart ? 152 : 196} tick={{ fontSize: 11 }} />
              <Tooltip formatter={cashFlowTooltipFormatter} />
              <Bar dataKey="amount" radius={[4, 4, 4, 4]}>
                {cashFlowData.map((item) => (
                  <Cell key={item.name} fill={cashFlowColor(item.kind)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="cash-flow-pies">
            {[
              { title: "收入构成", data: incomePieData, legendData: incomeLegendData },
              { title: "支出构成", data: expensePieData }
            ].map((pie) => (
              <div className="cash-flow-pie" key={pie.title}>
                <strong>{pie.title}</strong>
                {pie.data.length > 0 ? (
                  <div className="pie-layout">
                    <ResponsiveContainer width="100%" height={210}>
                      <PieChart>
                        <Tooltip formatter={pieTooltipFormatter} />
                        <Pie
                          data={pie.data}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={48}
                          outerRadius={78}
                          paddingAngle={2}
                        >
                          {pie.data.map((item, index) => (
                            <Cell key={`${pie.title}-${item.name}`} fill={piePalette[index % piePalette.length]} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pie-legend">
                      {(pie.legendData ?? pie.data).map((item, index) => (
                        <span key={`${pie.title}-legend-${item.name}`}>
                          <i style={{ background: piePalette[index % piePalette.length] }} />
                          <em>{item.name}</em>
                          <strong>{money(item.value)}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="field-hint">当前月份没有可展示的{pie.title}。</p>
                )}
              </div>
            ))}
          </div>
          <div className="cash-flow-sections">
            {cashFlowGroups.map((group) => (
              <div className="cash-flow-section" key={group.title}>
                <strong>{group.title}</strong>
                {group.rows.map(([label, value]) => (
                  <Row key={label} label={label} value={money(Number(value))} />
                ))}
              </div>
            ))}
          </div>
          <div className="explanation-grid month-explanation-grid">
            {selectedMonthExplanationItems.map((item) => (
              <article key={item.title}>
                <strong>{item.title}</strong>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
          <p className="field-hint">
            投资账户收益留在投资账户继续复利；买入手续费从定投资金中扣除，卖出手续费在交易月变现时扣除。单位公积金缴存进入单独的公积金账户，不作为固定工资口径直接计入购房后月结余。
          </p>
        </section>
      </div>

      <section className="chart-block happiness-chart">
        <PanelTitle icon={<TrendingUp size={18} />} title="幸福指数对比" compact />
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={happinessData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tickLine={false} axisLine={false} />
            <YAxis domain={[0, 10]} tickLine={false} axisLine={false} width={36} />
            <Tooltip formatter={(value) => `${Number(value).toFixed(1)} / 10`} />
            <Bar dataKey="幸福指数" radius={[4, 4, 0, 0]}>
              {happinessData.map((item) => (
                <Cell key={item.name} fill={item.selected ? visualColors.safe : "#9fb1c8"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="field-hint">
          幸福指数综合居住体验、通勤、教育、交易现金安全、买后自由现金月结余、负债压力、商贷利息压力和等待时间；流动性偏好越高，财务安全权重越高。
        </p>
        <div className="happiness-breakdown">
          {plan.happiness_breakdown.map((item) => (
            <div className="happiness-breakdown-item" key={item.name}>
              <span>
                <strong>{item.name}</strong>
                <small>{item.note}</small>
              </span>
              <b>{item.score.toFixed(1)}</b>
            </div>
          ))}
        </div>
      </section>

      <section className="timeline-panel">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="事件时间线" compact />
        <div className="timeline-list">
          {timelineItems.map((item, index) => (
            <div className="timeline-item" key={`${item.month}-${item.label}-${index}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function ExportPage({
  result,
  scenario,
  selectedPlan,
  selectedPlanVariant,
  setSelectedPlanVariant,
  runCalculation
}: {
  result: AffordabilityResult | null;
  scenario: ScenarioData;
  selectedPlan: PurchasePlanAnalysis | null;
  selectedPlanVariant: string;
  setSelectedPlanVariant: (variant: string) => void;
  runCalculation: () => void;
}) {
  const availablePlans = result?.purchase_plan_analyses ?? [];

  return (
    <div className="page-stack">
      <SectionHeader
        icon={<Download size={20} />}
        title="导出方案"
        action={
          <button className="ghost-button" onClick={runCalculation}>
            <RefreshCw size={16} /> 刷新结果
          </button>
        }
      />
      <section className="result-panel export-panel">
        {result && selectedPlan ? (
          <>
            <div className="visual-header">
              <div>
                <PanelTitle icon={<Download size={18} />} title="当前导出方案" />
                <h3>{selectedPlan.variant}</h3>
                <p>{selectedPlan.description}</p>
              </div>
              <select
                value={selectedPlanVariant}
                onChange={(event) => setSelectedPlanVariant(event.target.value)}
              >
                {availablePlans.map((plan) => (
                  <option key={plan.variant} value={plan.variant}>
                    {plan.variant}
                  </option>
                ))}
              </select>
            </div>
            <PlanStatus plan={selectedPlan} />
            <div className="metric-grid">
              <Metric
                label="预计买入时间"
                value={selectedPlan.months_to_buy === null ? "暂不可达" : formatMonthDate(new Date(), selectedPlan.months_to_buy)}
                tone={selectedPlan.months_to_buy === null ? "bad" : "good"}
              />
              <Metric label="首付" value={money(selectedPlan.planned_down_payment)} />
              <Metric label="公积金贷" value={money(selectedPlan.provident_loan_amount)} />
              <Metric label="商贷" value={money(selectedPlan.commercial_loan_amount)} />
              <Metric
                label="买后自由月结余"
                value={money(selectedPlan.post_purchase_cash_flow)}
                tone={selectedPlan.post_purchase_cash_flow >= 0 ? "good" : "bad"}
              />
              <Metric
                label="装修资金"
                value={
                  selectedPlan.renovation_included_in_upfront_cash
                    ? "交易时已备"
                    : selectedPlan.months_to_renovation === null
                      ? "暂无法估算"
                      : selectedPlan.months_to_renovation === 0
                        ? "买后可启动"
                        : `买后 ${selectedPlan.months_to_renovation} 个月`
                }
                tone={selectedPlan.months_to_renovation === null ? "warn" : "good"}
              />
              <Metric label="幸福指数" value={`${selectedPlan.happiness_score.toFixed(1)} / 10`} />
            </div>
            <div className="export-actions">
              <button className="primary-button" onClick={() => exportText(result, scenario, selectedPlan)}>
                <Download size={16} /> 导出文字
              </button>
              <button className="ghost-button" onClick={() => exportCsv(selectedPlan)}>
                <Download size={16} /> 导出表格
              </button>
            </div>
            <section className="notes">
              <p>导出内容以当前选中的“{selectedPlan.variant}”为准；全局即时可行性仅作为背景参考。</p>
              {result.eligibility_notes.map((note) => (
                <p key={note}>{note}</p>
              ))}
              {result.assumptions.map((note) => (
                <p key={note}>{note}</p>
              ))}
            </section>
          </>
        ) : (
          <PanelTitle icon={<Loader2 className="spin" size={18} />} title="等待计算" />
        )}
      </section>
    </div>
  );
}

function getPlanStatus(plan: PurchasePlanAnalysis) {
  if (plan.months_to_buy === null) {
    const shortfall = Math.max(0, plan.cash_stress_shortfall ?? 0);
    return {
      status: "不可行",
      statusClass: "bad",
      reason:
        shortfall > 0
          ? `系统已尝试延后买入和调整贷款结构，但 30 年内仍会留下约 ${money(shortfall)} 的压力现金缺口；这类方案不应直接执行。`
          : "当前收入、资产和现金流路径下，30 年内无法达到该方案的购房现金要求。"
    };
  }
  if (plan.cash_stress_ok === false) {
    const shortfall = Math.max(0, plan.cash_stress_shortfall ?? 0, -(plan.minimum_cash_balance ?? 0));
    return {
      status: "不可行",
      statusClass: "bad",
      reason: `${formatMonthDate(new Date(), plan.months_to_buy)} 虽然可达到交易现金要求，但压力情景下会出现 ${money(shortfall)} 现金缺口；现金不能为负，需要延后买入、降低目标或重新调整贷款结构。`
    };
  }
  const riskNotes = [
    !plan.liquidity_ok ? "交易当下现金低于安全垫" : "",
    plan.post_purchase_cash_flow < 0 ? "买后自由现金流为负" : "",
    plan.debt_to_income_ratio > 0.5 ? "负债收入比较高" : ""
  ].filter(Boolean);
  if (riskNotes.length > 0) {
    return {
      status: "谨慎可行",
      statusClass: "warn",
      reason: `${formatMonthDate(new Date(), plan.months_to_buy)} 可执行，但${riskNotes.join("、")}，建议保留为有条件方案。`
    };
  }
  return {
    status: "可行",
    statusClass: "good",
    reason: `${formatMonthDate(new Date(), plan.months_to_buy)} 可执行，交易当下现金安全垫和买后自由现金流均满足当前设定。`
  };
}

function PlanStatus({ plan }: { plan: PurchasePlanAnalysis }) {
  const planStatus = getPlanStatus(plan);

  return (
    <div className={`status-block ${planStatus.statusClass}`}>
      {planStatus.status === "不可行" ? <AlertTriangle size={22} /> : <CheckCircle2 size={22} />}
      <div>
        <strong>{plan.variant}：{planStatus.status}</strong>
        <span>{planStatus.reason}</span>
      </div>
    </div>
  );
}

function downloadFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function exportText(result: AffordabilityResult, scenario: ScenarioData, plan: PurchasePlanAnalysis) {
  const planStatus = getPlanStatus(plan);
  const renovationText =
    scenario.renovation_cost <= 0
      ? "装修预算：未设置"
      : plan.renovation_included_in_upfront_cash
        ? `装修预算：${money(scenario.renovation_cost)}，资金方式：${renovationFundingLabels[plan.renovation_funding_mode]}，已计入交易现金需求`
        : plan.months_to_renovation === null
          ? `装修预算：${money(scenario.renovation_cost)}，资金方式：${renovationFundingLabels[plan.renovation_funding_mode]}，买后月结余暂不足以估算装修启动时间`
          : `装修预算：${money(scenario.renovation_cost)}，资金方式：${renovationFundingLabels[plan.renovation_funding_mode]}，预计买后 ${plan.months_to_renovation} 个月可启动装修`;
  const lines = [
    `当前导出方案：${plan.variant}`,
    `方案结论：${planStatus.status}`,
    planStatus.reason,
    plan.description,
    "",
    `税后月收入：${money(result.household_net_monthly_income)}`,
    `年度个税：${money(result.annual_income_tax)}`,
    `目前贷款月供：${money(result.phased_loan_monthly_payment)}`,
    "",
    "当前方案购房路径：",
    `预计买入时间：${plan.months_to_buy === null ? "30 年内暂不可达" : formatMonthDate(new Date(), plan.months_to_buy)}（约 ${plan.years_to_buy ?? "超过30"} 年）`,
    `首付：${money(plan.planned_down_payment)}，本人公积金首付抵扣：${money(plan.provident_upfront_extractable)}${familySupportPhrase(plan)}，交易现金需覆盖：${money(plan.required_cash_after_pf_extract)}`,
    `购房后预计公积金提取到账：${money(plan.provident_post_transaction_extractable)}，剩余公积金余额：${money(plan.provident_balance_after_extract)}`,
    renovationText,
    `公积金贷：${money(plan.provident_loan_amount)}，${plan.provident_loan_years} 年，${repaymentMethodLabels[plan.provident_repayment_method]}，政策上限 ${money(plan.provident_policy_cap)}，政策上浮 ${money(plan.provident_policy_bonus)}`,
    `商贷：${money(plan.commercial_loan_amount)}，${plan.commercial_loan_years} 年，${repaymentMethodLabels[plan.commercial_repayment_method]}`,
    `合计月供：${money(plan.total_monthly_payment)}，交易当下现金：${money(plan.cash_after_transaction)}，购房后公积金到账后现金：${money(plan.cash_after_purchase)}`,
    `买后自由现金月结余：${money(plan.post_purchase_cash_flow)}，贷后公积金策略：${providentStrategyLabel(plan)}，按策略折算后的现金压力：${money(plan.post_purchase_cash_flow_with_pf_withdrawal)}/月`,
    `公积金还款方式建议：${plan.provident_repayment_advice || "无"}`,
    `负债收入比：${percent(plan.debt_to_income_ratio)}，幸福指数：${plan.happiness_score.toFixed(1)} / 10`,
    "幸福指数明细：",
    ...plan.happiness_breakdown.map((item) => `- ${item.name}：${item.score.toFixed(1)} 分。${item.note}`),
    `公积金年限依据：${plan.provident_loan_year_limit_reasons.join("；")}`,
    "",
    `全局即时评估：${result.status}。${result.status_reason}`
  ];
  downloadFile(`house-plan-${plan.variant}.txt`, lines.join("\n"), "text/plain;charset=utf-8");
}

function csvCell(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function exportCsv(plan: PurchasePlanAnalysis) {
  const planStatus = getPlanStatus(plan);
  const header = "路径,年限,计划首付,本人公积金首付抵扣,亲属首付支持,购房后预计公积金提取到账,交易现金需覆盖,装修预算,装修资金方式,装修是否计入交易现金,预计装修等待月数,公积金贷,公积金上限,政策上浮,公积金年限,公积金年限依据,公积金还款,公积金还款建议,商贷,商贷年限,商贷还款,月供,交易当下现金,到账后现金,买后自由现金月结余,贷后公积金策略,冲还贷折算改善,策略后现金压力,幸福度";
  const row = [
    plan.variant,
    plan.months_to_buy === null ? "30年内暂不可达" : formatMonthDate(new Date(), plan.months_to_buy),
    plan.planned_down_payment,
    plan.provident_upfront_extractable,
    familySupportAmount(plan),
    plan.provident_post_transaction_extractable,
    plan.required_cash_after_pf_extract,
    plan.renovation_cost,
    renovationFundingLabels[plan.renovation_funding_mode],
    plan.renovation_included_in_upfront_cash ? "是" : "否",
    plan.months_to_renovation ?? "暂无法估算",
    plan.provident_loan_amount,
    plan.provident_policy_cap,
    plan.provident_policy_bonus,
    plan.provident_loan_years,
    plan.provident_loan_year_limit_reasons.join("；"),
    repaymentMethodLabels[plan.provident_repayment_method],
    plan.provident_repayment_advice,
    plan.commercial_loan_amount,
    plan.commercial_loan_years,
    repaymentMethodLabels[plan.commercial_repayment_method],
    plan.total_monthly_payment,
    plan.cash_after_transaction,
    plan.cash_after_purchase,
    plan.post_purchase_cash_flow,
    providentStrategyLabel(plan),
    plan.monthly_post_purchase_pf_withdrawal,
    plan.post_purchase_cash_flow_with_pf_withdrawal,
    `${plan.happiness_score.toFixed(1)} / 10，${planStatus.status}`
  ].map(csvCell).join(",");
  downloadFile(`house-plan-${plan.variant}.csv`, [header, row].join("\n"), "text/csv;charset=utf-8");
}

function SectionHeader({
  icon,
  title,
  action
}: {
  icon: ReactNode;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-header">
      <div>
        {icon}
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

function PanelTitle({ icon, title, compact = false }: { icon: ReactNode; title: string; compact?: boolean }) {
  return (
    <div className={compact ? "panel-title compact" : "panel-title"}>
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function Field({ label, children, description }: { label: string; children: ReactNode; description?: string }) {
  const helpText = description ?? parameterExplanations[label];
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {helpText ? <small className="parameter-help">{helpText}</small> : null}
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
  min,
  max,
  description
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  min?: number;
  max?: number;
  description?: string;
}) {
  const [draftValue, setDraftValue] = useState(numberInput(value));

  useEffect(() => {
    setDraftValue(numberInput(value));
  }, [value]);

  const clampValue = (nextValue: number) => {
    if (!Number.isFinite(nextValue)) return value;
    if (min !== undefined && nextValue < min) return min;
    if (max !== undefined && nextValue > max) return max;
    return nextValue;
  };

  const commitValue = (rawValue: string) => {
    const trimmed = rawValue.trim();
    if (trimmed === "" || trimmed === "-" || trimmed === "." || trimmed === "-.") {
      setDraftValue(numberInput(value));
      return;
    }
    const nextValue = clampValue(Number(trimmed));
    setDraftValue(numberInput(nextValue));
    if (nextValue !== value) {
      onChange(nextValue);
    }
  };

  return (
    <Field label={label} description={description}>
      <input
        type="text"
        inputMode={step % 1 === 0 ? "numeric" : "decimal"}
        value={draftValue}
        onFocus={(event) => event.currentTarget.select()}
        onMouseUp={(event) => event.preventDefault()}
        onChange={(event) => setDraftValue(event.target.value)}
        onBlur={(event) => commitValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
      />
    </Field>
  );
}

function AgeField({
  label,
  value,
  onChange,
  min = 18,
  max = 80
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}) {
  const commitValue = (rawValue: string) => {
    const parsed = Math.floor(Number(rawValue));
    if (!Number.isFinite(parsed)) return;
    const nextValue = Math.max(min, Math.min(max, parsed));
    if (nextValue !== value) {
      onChange(nextValue);
    }
  };

  return (
    <Field label={label}>
      <input
        aria-label={label}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        step={1}
        value={value}
        onInput={(event) => commitValue(event.currentTarget.value)}
        onChange={(event) => commitValue(event.target.value)}
      />
    </Field>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
