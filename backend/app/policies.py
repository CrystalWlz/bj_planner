from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .schemas import HouseholdData, RulePackData, ScenarioData


class RegionalPolicy(Protocol):
    code: str

    def minimum_down_payment_ratio(self, household: HouseholdData, *, uses_provident_loan: bool) -> float:
        ...

    def provident_policy_bonus(self, scenario: ScenarioData) -> float:
        ...

    def provident_loan_years(self, household: HouseholdData, scenario: ScenarioData) -> tuple[int, list[str]]:
        ...


@dataclass(frozen=True)
class BeijingPolicy:
    rules: RulePackData
    code: str = "beijing"

    @property
    def params(self) -> dict:
        return self.rules.params

    def minimum_down_payment_ratio(self, household: HouseholdData, *, uses_provident_loan: bool) -> float:
        params = self.params
        if household.existing_home_count <= 0 and household.existing_mortgage_count <= 0:
            commercial_ratio = float(params.get("first_home_commercial_min_down_payment_ratio", 0.15))
            provident_ratio = float(params.get("first_home_provident_min_down_payment_ratio", 0.20))
        else:
            commercial_ratio = float(params.get("second_home_commercial_min_down_payment_ratio", 0.20))
            provident_ratio = float(params.get("second_home_provident_min_down_payment_ratio", 0.25))
        return max(commercial_ratio, provident_ratio if uses_provident_loan else 0.0)

    def provident_policy_bonus(self, scenario: ScenarioData) -> float:
        if not _is_new_home_property(scenario):
            return 0.0

        params = self.params
        bonuses: list[float] = []
        if scenario.green_building_level == "two_star":
            bonuses.append(float(params.get("provident_green_two_star_bonus", 0)))
        elif scenario.green_building_level == "three_star":
            bonuses.append(float(params.get("provident_green_three_star_bonus", 0)))

        prefab_bonus = {
            "A": float(params.get("provident_prefab_a_bonus", 0)),
            "AA": float(params.get("provident_prefab_aa_bonus", 0)),
            "AAA": float(params.get("provident_prefab_aaa_bonus", 0)),
        }.get(scenario.prefab_building_level, 0.0)
        if prefab_bonus > 0:
            bonuses.append(prefab_bonus)

        if scenario.is_ultra_low_energy_building:
            bonuses.append(float(params.get("provident_ultra_low_energy_bonus", 0)))

        cap = float(params.get("provident_policy_bonus_cap", 400000))
        return min(max(bonuses) if bonuses else 0.0, cap)

    def provident_loan_years(self, household: HouseholdData, scenario: ScenarioData) -> tuple[int, list[str]]:
        params = self.params
        requested_years = max(1, min(scenario.loan_years, 30))
        max_years = int(params.get("provident_max_loan_years", 30))
        borrower_age_limit = int(params.get("provident_max_borrower_age", 68))
        borrower_age_years = max(18, household.borrower_age)
        age_limited_years = max(1, borrower_age_limit - borrower_age_years)
        limits: list[tuple[int, str]] = [
            (requested_years, f"手动贷款年限 {requested_years} 年"),
            (max_years, f"北京公积金最长 {max_years} 年"),
            (age_limited_years, f"借款申请人年龄 {borrower_age_years} 岁，对应最长 {age_limited_years} 年"),
        ]

        if _is_second_hand_property(scenario):
            property_age = max(0, scenario.building_age_years)
            safety_deduction = int(params.get("provident_property_age_safety_deduction_years", 3))
            uses_renovated_land_limit = scenario.is_old_community_renovated and scenario.remaining_land_use_years is not None
            if uses_renovated_land_limit:
                land_limited_years = max(1, scenario.remaining_land_use_years - safety_deduction)
                limits.append((land_limited_years, f"剩余土地使用年限 {scenario.remaining_land_use_years} 年，扣减 {safety_deduction} 年后最长 {land_limited_years} 年"))
            else:
                if scenario.building_structure == "brick_mixed":
                    total_life = int(params.get("provident_brick_mixed_total_life_years", 50))
                    structure_label = "砖混结构"
                else:
                    total_life = int(params.get("provident_steel_concrete_total_life_years", 60))
                    structure_label = "钢混结构"
                structure_limited_years = max(1, total_life - property_age - safety_deduction)
                limits.append(
                    (
                        structure_limited_years,
                        f"二手房房龄 {property_age} 年，{structure_label} 最长 {structure_limited_years} 年",
                    )
                )
                if scenario.remaining_land_use_years is not None:
                    land_limited_years = max(1, scenario.remaining_land_use_years)
                    limits.append((land_limited_years, f"土地剩余年限 {land_limited_years} 年"))

        selected_years = min(years for years, _ in limits)
        reasons = [reason for years, reason in limits if years == selected_years]
        return selected_years, reasons


def _is_second_hand_property(scenario: ScenarioData) -> bool:
    text = scenario.property_type.strip()
    return "二手" in text or "存量" in text


def _is_new_home_property(scenario: ScenarioData) -> bool:
    return "新房" in scenario.property_type.strip()


def get_policy(rules: RulePackData) -> RegionalPolicy:
    jurisdiction = rules.jurisdiction.strip().lower()
    if jurisdiction in {"北京", "beijing", "bj"}:
        return BeijingPolicy(rules)
    return BeijingPolicy(rules)
