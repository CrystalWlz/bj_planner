from __future__ import annotations

from datetime import date

from ..schemas import (
    CareerShockMemberProjection,
    CareerShockMemberSetting,
    CareerShockProjection,
    HouseholdData,
    IncomeMember,
    IncomeStageData,
    RulePackData,
)
from ..policies import get_policy
from .tax import clamp
from .time import (
    add_months,
    end_of_previous_month,
    month_start_for_birth_month_or_age,
    months_between_months,
    parse_iso_date,
)


def money_text(amount: float) -> str:
    return f"{round(amount):,} 元".replace(",", "")


def zero_cash_stage(template: IncomeStageData, name: str, start: date, end: date | None = None) -> IncomeStageData:
    return template.model_copy(
        update={
            "name": name,
            "stage_kind": "manual",
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else None,
            "monthly_salary_gross": 0,
            "annual_bonus_months": 0,
            "annual_bonus_payout_mode": "lump_sum",
            "annual_bonus_payout_month": template.annual_bonus_payout_month,
            "monthly_freelance_income": 0,
            "monthly_non_taxable_income": 0,
            "monthly_extra_cash_expense": 0,
            "monthly_social_insurance": 0,
            "monthly_housing_fund": 0,
            "housing_fund_personal_rate": 0,
            "housing_fund_employer_rate": 0,
            "monthly_special_additional_deduction": 0,
            "other_annual_deductions": 0,
            "other_annual_taxable_income": 0,
            "payroll_contributions_enabled": False,
        }
    )


def default_retirement_age_for_member(index: int) -> int:
    return 63 if index == 0 else 58


def policy_retirement_age_for_member_with_rules(member: IncomeMember, index: int, rules: RulePackData) -> int:
    return get_policy(rules).retirement_age_for_member(member, index)


def career_shock_settings_by_member(household: HouseholdData) -> dict[str, CareerShockMemberSetting | None]:
    shock = household.career_shock
    settings_by_name = {item.member_name: item for item in shock.member_settings}
    return {member.name: settings_by_name.get(member.name) for member in household.members}


def member_retirement_months_by_index(
    household: HouseholdData,
    *,
    rules: RulePackData,
    as_of: date | None = None,
) -> dict[int, int]:
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    settings_by_member = career_shock_settings_by_member(household)
    retirement_months: dict[int, int] = {}
    for index, member in enumerate(household.members):
        setting = settings_by_member.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = policy_retirement_age_for_member_with_rules(member, index, rules)
        retirement_start = month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        retirement_months[index] = max(0, months_between_months(current_month, retirement_start))
    return retirement_months


def unemployment_benefit_months_from_service(service_months: int) -> int:
    if service_months < 12:
        return 0
    if service_months < 60:
        return 12
    if service_months < 120:
        return 18
    return 24


def unemployment_benefit_monthly_from_service(service_months: int, rules: RulePackData) -> float:
    return get_policy(rules).unemployment_benefit_monthly_from_service(service_months)


def career_shock_unemployment_months(household: HouseholdData) -> int:
    shock = household.career_shock
    if not shock.auto_unemployment_benefit:
        return max(0, min(shock.unemployment_benefit_months, 24))
    return unemployment_benefit_months_from_service(max(0, household.social_security_months))


def career_shock_self_social_monthly(household: HouseholdData, rules: RulePackData) -> float:
    shock = household.career_shock
    if not shock.auto_self_social_insurance:
        return max(0.0, shock.self_social_insurance_monthly)
    return get_policy(rules).flexible_employment_social_monthly()


def career_shock_flexible_housing_fund_monthly(household: HouseholdData, rules: RulePackData) -> float:
    shock = household.career_shock
    if not shock.auto_flexible_housing_fund:
        return max(0.0, shock.self_housing_fund_monthly)
    return get_policy(rules).flexible_employment_housing_fund_monthly()


def career_shock_self_payment_monthly(household: HouseholdData, rules: RulePackData) -> float:
    return round(
        career_shock_self_social_monthly(household, rules)
        + career_shock_flexible_housing_fund_monthly(household, rules),
        2,
    )


def career_shock_self_payment_at_month(
    household: HouseholdData,
    rules: RulePackData,
    months_from_now: int = 0,
    *,
    as_of: date | None = None,
) -> float:
    shock = household.career_shock
    if not shock.enabled:
        return 0.0
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    target_month = add_months(current_month, max(0, months_from_now))
    settings_by_member = career_shock_settings_by_member(household)
    monthly_amount = career_shock_self_payment_monthly(household, rules)
    total = 0.0
    for index, member in enumerate(household.members):
        setting = settings_by_member.get(member.name)
        if not setting or not setting.enabled:
            continue
        effective_birth_month = member.birth_month or setting.birth_month
        effective_current_age = member.current_age if member.birth_month else setting.current_age
        layoff_start = month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            setting.layoff_age,
        )
        retirement_start = month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            policy_retirement_age_for_member_with_rules(member, index, rules),
        )
        self_payment_start = add_months(layoff_start, career_shock_unemployment_months(household))
        if self_payment_start <= target_month < retirement_start:
            total += monthly_amount
    return round(total, 2)


def estimate_auto_pension_monthly(
    member: IncomeMember,
    setting: CareerShockMemberSetting,
    rules: RulePackData,
    retirement_start: date,
    as_of: date,
) -> float:
    manual_value = max(0.0, setting.pension_monthly)
    if not setting.auto_pension_monthly:
        return manual_value
    pension_policy = get_policy(rules).pension_estimate_policy()

    current_month = date(as_of.year, as_of.month, 1)
    months_to_retirement = max(0, months_between_months(current_month, retirement_start))
    stages = sorted(
        member.income_stages or [],
        key=lambda stage: parse_iso_date(stage.start_date, date(1900, 1, 1)),
    )
    current_stage = stages[-1] if stages else IncomeStageData(
        monthly_salary_gross=member.monthly_salary_gross,
        annual_bonus=member.annual_bonus,
    )
    current_salary = max(member.monthly_salary_gross, current_stage.monthly_salary_gross)
    contribution_base = clamp(
        current_salary if current_salary > 0 else pension_policy.social_base_floor,
        pension_policy.social_base_floor,
        pension_policy.social_base_ceiling,
    )
    flexible_base = pension_policy.flexible_employment_social_base
    projected_avg_salary = pension_policy.reference_average_salary * ((1 + pension_policy.average_salary_growth_rate) ** (months_to_retirement / 12))
    existing_paid_years = max(
        pension_policy.default_paid_years,
        max(0, member.current_age - 22),
    )
    future_paid_years = months_to_retirement / 12
    total_paid_years = max(15.0, existing_paid_years + future_paid_years)
    indexed_base = (contribution_base + flexible_base) / 2
    basic_pension = projected_avg_salary * (1 + indexed_base / projected_avg_salary) / 2 * total_paid_years * 0.01
    existing_account = contribution_base * pension_policy.employee_pension_rate * 12 * existing_paid_years
    future_account = 0.0
    for _ in range(max(0, months_to_retirement)):
        future_account = (future_account + flexible_base * pension_policy.flexible_employment_pension_rate * 0.40) * ((1 + pension_policy.personal_account_annual_return) ** (1 / 12))
    personal_account_pension = (existing_account + future_account) / pension_policy.personal_account_months
    raw_pension = basic_pension + personal_account_pension
    floor_value = projected_avg_salary * pension_policy.replacement_rate_floor
    ceiling_value = projected_avg_salary * pension_policy.replacement_rate_ceiling
    return round(clamp(raw_pension, floor_value, ceiling_value), 2)


def household_with_career_income_stages(
    household: HouseholdData,
    rules: RulePackData,
    *,
    as_of: date | None = None,
) -> HouseholdData:
    shock = household.career_shock
    if household.career_shock_applied or not household.members:
        return household

    current = as_of or date.today()
    synthetic_prefix = "自动情景："
    updated_members: list[IncomeMember] = []
    settings_by_member = career_shock_settings_by_member(household)
    for index, member in enumerate(household.members):
        stages = [stage for stage in (member.income_stages or []) if not stage.name.startswith(synthetic_prefix)]
        if not stages:
            updated_members.append(member.model_copy(update={"income_stages": []}))
            continue
        template = max(stages, key=lambda stage: parse_iso_date(stage.start_date, date(1900, 1, 1)))
        setting = settings_by_member.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = policy_retirement_age_for_member_with_rules(member, index, rules)
        retirement_start = month_start_for_birth_month_or_age(
            current,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        pension_monthly = estimate_auto_pension_monthly(member, setting, rules, retirement_start, current) if setting else 0
        shock_freelance_income = max(0.0, setting.freelance_income_monthly) if setting else 0.0

        if shock.enabled and setting and setting.enabled:
            layoff_start = month_start_for_birth_month_or_age(
                current,
                effective_birth_month,
                effective_current_age,
                setting.layoff_age,
            )
            unemployment_months = career_shock_unemployment_months(household)
            if unemployment_months > 0 and layoff_start < retirement_start:
                if shock.auto_unemployment_benefit:
                    first_period_months = min(unemployment_months, 12)
                    first_end = min(add_months(layoff_start, first_period_months - 1), end_of_previous_month(retirement_start))
                    first_stage = zero_cash_stage(template, f"{synthetic_prefix}{setting.layoff_age}岁被裁员-失业金期", layoff_start, first_end)
                    stages.append(
                        first_stage.model_copy(
                            update={
                                "stage_kind": "unemployment",
                                "monthly_freelance_income": shock_freelance_income,
                                "monthly_non_taxable_income": unemployment_benefit_monthly_from_service(household.social_security_months, rules),
                            }
                        )
                    )
                    if unemployment_months > 12:
                        later_start = add_months(layoff_start, 12)
                        if later_start < retirement_start:
                            later_end = min(add_months(layoff_start, unemployment_months - 1), end_of_previous_month(retirement_start))
                            later_stage = zero_cash_stage(template, f"{synthetic_prefix}{setting.layoff_age}岁被裁员-失业金后续期", later_start, later_end)
                            stages.append(
                                later_stage.model_copy(
                                    update={
                                        "stage_kind": "unemployment",
                                        "monthly_freelance_income": shock_freelance_income,
                                        "monthly_non_taxable_income": get_policy(rules).later_unemployment_benefit_monthly(),
                                    }
                                )
                            )
                else:
                    unemployment_end = add_months(layoff_start, unemployment_months - 1)
                    end = min(unemployment_end, end_of_previous_month(retirement_start))
                    unemployment_stage = zero_cash_stage(template, f"{synthetic_prefix}{setting.layoff_age}岁被裁员-失业金期", layoff_start, end)
                    stages.append(
                        unemployment_stage.model_copy(
                            update={
                                "stage_kind": "unemployment",
                                "monthly_freelance_income": shock_freelance_income,
                                "monthly_non_taxable_income": shock.unemployment_benefit_monthly,
                            }
                        )
                    )
            self_social_start = add_months(layoff_start, unemployment_months)
            if self_social_start < retirement_start:
                stages.append(
                    zero_cash_stage(
                        template,
                        f"{synthetic_prefix}{setting.layoff_age}岁被裁员-灵活就业自缴社保期",
                        self_social_start,
                        end_of_previous_month(retirement_start),
                    ).model_copy(
                        update={
                            "stage_kind": "freelance",
                            "monthly_freelance_income": shock_freelance_income,
                            "housing_fund_personal_rate": 0,
                            "housing_fund_employer_rate": 0,
                            "payroll_contributions_enabled": False,
                        }
                    )
                )

        if pension_monthly > 0:
            stages.append(
                zero_cash_stage(template, f"{synthetic_prefix}{retirement_age}岁退休-养老金", retirement_start).model_copy(
                    update={"stage_kind": "pension", "monthly_non_taxable_income": pension_monthly}
                )
            )

        updated_members.append(member.model_copy(update={"income_stages": stages}))

    return household.model_copy(update={"members": updated_members, "career_shock_applied": True})


def has_pension_stage_after(stages: list[IncomeStageData], retirement_start: date) -> bool:
    for stage in stages:
        if stage.stage_kind != "pension":
            continue
        stage_start = parse_iso_date(stage.start_date, date(1900, 1, 1))
        if stage_start >= retirement_start and stage.monthly_non_taxable_income > 0:
            return True
    return False


def household_with_pension_income_stages(
    household: HouseholdData,
    rules: RulePackData,
    *,
    as_of: date | None = None,
) -> HouseholdData:
    household = household_with_career_income_stages(household, rules, as_of=as_of)
    if not household.members:
        return household

    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    settings_by_member = career_shock_settings_by_member(household)
    updated_members: list[IncomeMember] = []
    changed = False
    synthetic_prefix = "自动情景："

    for index, member in enumerate(household.members):
        stages = list(member.income_stages or [])
        retirement_age = policy_retirement_age_for_member_with_rules(member, index, rules)
        setting = settings_by_member.get(member.name)
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_start = month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        if has_pension_stage_after(stages, retirement_start):
            updated_members.append(member)
            continue

        template = max(stages, key=lambda stage: parse_iso_date(stage.start_date, date(1900, 1, 1)), default=IncomeStageData(name="退休前收入"))
        pension_setting = setting or CareerShockMemberSetting(
            member_name=member.name,
            enabled=False,
            retirement_age=retirement_age,
            birth_month=member.birth_month,
            current_age=member.current_age,
        )
        pension_monthly = estimate_auto_pension_monthly(member, pension_setting, rules, retirement_start, current_month)
        if pension_monthly <= 0:
            updated_members.append(member)
            continue

        stages.append(
            zero_cash_stage(template, f"{synthetic_prefix}{retirement_age}岁退休-养老金领取", retirement_start).model_copy(
                update={"stage_kind": "pension", "monthly_non_taxable_income": pension_monthly}
            )
        )
        changed = True
        updated_members.append(member.model_copy(update={"income_stages": stages}))

    if not changed:
        return household
    return household.model_copy(update={"members": updated_members})


def format_month(value: date | None) -> str | None:
    if value is None:
        return None
    return f"{value.year:04d}-{value.month:02d}"


def build_career_shock_projection(
    household: HouseholdData,
    rules: RulePackData,
    *,
    as_of: date | None = None,
) -> CareerShockProjection:
    current = as_of or date.today()
    current_month = date(current.year, current.month, 1)
    shock = household.career_shock
    effective_household = household_with_career_income_stages(household, rules, as_of=current_month)
    unemployment_months = career_shock_unemployment_months(household)
    first_unemployment = (
        unemployment_benefit_monthly_from_service(household.social_security_months, rules)
        if shock.auto_unemployment_benefit
        else max(0.0, shock.unemployment_benefit_monthly)
    )
    later_unemployment = get_policy(rules).later_unemployment_benefit_monthly()
    self_social = career_shock_self_social_monthly(household, rules)
    flexible_housing = career_shock_flexible_housing_fund_monthly(household, rules)
    self_payment = round(self_social + flexible_housing, 2)
    settings_by_member = career_shock_settings_by_member(household)
    member_projections: list[CareerShockMemberProjection] = []
    synthetic_prefix = "自动情景："

    for index, member in enumerate(household.members):
        setting = settings_by_member.get(member.name)
        effective_member = effective_household.members[index] if index < len(effective_household.members) else member
        generated_stages = [stage for stage in (effective_member.income_stages or []) if stage.name.startswith(synthetic_prefix)]
        effective_birth_month = member.birth_month or (setting.birth_month if setting else "")
        effective_current_age = member.current_age if member.birth_month else (setting.current_age if setting else member.current_age)
        retirement_age = policy_retirement_age_for_member_with_rules(member, index, rules)
        retirement_start = month_start_for_birth_month_or_age(
            current_month,
            effective_birth_month,
            effective_current_age,
            retirement_age,
        )
        layoff_age = setting.layoff_age if setting else 35
        layoff_start = (
            month_start_for_birth_month_or_age(current_month, effective_birth_month, effective_current_age, layoff_age)
            if setting
            else None
        )
        pension_monthly = estimate_auto_pension_monthly(member, setting, rules, retirement_start, current_month) if setting else 0.0
        notes = [
            "收入阶段由后端按职业冲击规则生成，前端只展示生成结果。",
            f"退休年龄按成员退休身份和规则包取 {retirement_age} 岁。",
        ]
        if setting and setting.enabled:
            notes.append(f"裁员后最多 {unemployment_months} 个月按失业金阶段测算，之后进入灵活就业自缴阶段直到退休。")
            if setting.freelance_income_monthly > 0:
                notes.append(f"冲击期自由职业收入按 {money_text(setting.freelance_income_monthly)}/月并入自动生成的收入阶段。")
        else:
            notes.append("该成员未启用职业冲击，只生成退休养老金阶段。")

        member_projections.append(
            CareerShockMemberProjection(
                member_name=member.name,
                enabled=bool(setting.enabled) if setting else False,
                layoff_age=layoff_age,
                retirement_age=retirement_age,
                layoff_month=format_month(layoff_start),
                retirement_month=format_month(retirement_start),
                unemployment_benefit_months=unemployment_months if setting and setting.enabled else 0,
                unemployment_benefit_monthly=round(first_unemployment, 2) if setting and setting.enabled else 0.0,
                later_unemployment_benefit_monthly=round(later_unemployment, 2) if setting and setting.enabled else 0.0,
                self_social_insurance_monthly=round(self_social, 2) if setting and setting.enabled else 0.0,
                flexible_housing_fund_monthly=round(flexible_housing, 2) if setting and setting.enabled else 0.0,
                self_payment_monthly=self_payment if setting and setting.enabled else 0.0,
                pension_monthly=round(pension_monthly, 2),
                generated_stages=generated_stages,
                notes=notes,
            )
        )

    return CareerShockProjection(
        enabled=bool(shock.enabled),
        unemployment_benefit_months=unemployment_months,
        unemployment_benefit_monthly=round(first_unemployment, 2),
        later_unemployment_benefit_monthly=round(later_unemployment, 2),
        self_social_insurance_monthly=round(self_social, 2),
        flexible_housing_fund_monthly=round(flexible_housing, 2),
        self_payment_monthly=self_payment,
        effective_members=effective_household.members,
        member_projections=member_projections,
        notes=[
            "职业冲击、失业金、自缴社保、自缴公积金和养老金估算均由后端计算。",
            "前端手动参数只改变输入配置，保存后由后端重新生成收入阶段和现金流。",
        ],
    )
