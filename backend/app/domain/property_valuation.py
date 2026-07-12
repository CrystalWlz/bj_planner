from __future__ import annotations

import math
from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from ..schemas import (
    HousingMarketEvidenceData,
    MarketSnapshotData,
    PropertyValuationData,
    PropertyValuationProjectionPoint,
    ScenarioData,
)


SOURCE_TYPE_WEIGHT = {
    "government": 1.0,
    "research": 0.88,
    "agency": 0.82,
    "brokerage": 0.72,
    "media": 0.42,
    "other": 0.5,
}

SOURCE_TYPE_LABEL = {
    "government": "政府统计",
    "research": "研究机构",
    "agency": "专业机构",
    "brokerage": "经纪/平台",
    "media": "媒体新闻",
    "other": "其它来源",
}


@dataclass(frozen=True)
class MarketSignalSummary:
    signal: float
    local_signal: float | None
    local_unit_price: float
    city_unit_price: float
    matched_location_name: str
    matched_ring_area: str
    drivers: list[str]
    signal_count: int
    source_names: list[str]
    source_types: set[str]
    weighted_quality: float
    media_only: bool


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _parse_date(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def _add_months(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(absolute, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _months_between(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month)


def _annualized_monthly(monthly_rate: float | None) -> float | None:
    if monthly_rate is None:
        return None
    return _clamp((1 + monthly_rate) ** 12 - 1, -0.18, 0.18)


def _normalized_location(value: str) -> str:
    return (
        value.strip()
        .replace("北京市", "")
        .replace("北京", "")
        .replace("市", "")
        .replace("区", "")
        .replace("县", "")
        .replace(" ", "")
    )


def _normalized_ring(value: str) -> str:
    compact = value.strip().replace(" ", "").replace("到", "至").replace("—", "至").replace("-", "至")
    aliases = {
        "二环以内": "二环内",
        "2环内": "二环内",
        "二环至三环": "二至三环",
        "2至3环": "二至三环",
        "三环至四环": "三至四环",
        "3至4环": "三至四环",
        "四环至五环": "四至五环",
        "4至5环": "四至五环",
        "五环至六环": "五至六环",
        "5至6环": "五至六环",
        "六环以外": "六环外",
        "6环外": "六环外",
    }
    canonical = aliases.get(compact, compact)
    return canonical if canonical in {"二环内", "二至三环", "三至四环", "四至五环", "五至六环", "六环外"} else ""


def _evidence_matches_property(evidence: HousingMarketEvidenceData, *, is_new_home: bool) -> bool:
    return evidence.property_segment == "all" or (
        evidence.property_segment == "new_home" if is_new_home else evidence.property_segment == "resale"
    )


def _ring_match(scenario: ScenarioData, evidence: HousingMarketEvidenceData) -> bool:
    return evidence.ring_scope == "all" or _normalized_ring(scenario.ring_area) == evidence.ring_scope


def _location_match(scenario: ScenarioData, evidence: HousingMarketEvidenceData) -> bool:
    if not _ring_match(scenario, evidence):
        return False
    if evidence.scope_type == "city":
        return evidence.ring_scope != "all"
    scope = _normalized_location(evidence.scope_name)
    if not scope:
        return False
    district = _normalized_location(scenario.district)
    property_name = _normalized_location(scenario.name)
    return scope in district or district in scope or scope in property_name


def _evidence_weight(
    evidence: HousingMarketEvidenceData,
    *,
    valued_on: date,
    location_match: bool,
) -> float:
    published_on = _parse_date(evidence.published_date, valued_on)
    age_months = _months_between(published_on, valued_on)
    recency = math.exp(-age_months / 18)
    scope_boost = 1.35 if evidence.scope_type == "community" and location_match else 1.2 if location_match else 1.0
    sample_boost = 1.0
    if evidence.sample_size is not None:
        sample_boost = 0.75 + min(0.25, math.log1p(evidence.sample_size) / 40)
    return max(
        0.01,
        SOURCE_TYPE_WEIGHT[evidence.source_type]
        * evidence.credibility_score
        * recency
        * scope_boost
        * sample_boost,
    )


def _snapshot_evidence(snapshot: MarketSnapshotData, *, is_new_home: bool) -> HousingMarketEvidenceData:
    return HousingMarketEvidenceData(
        source_name=snapshot.source_name,
        source_url=snapshot.source_url,
        source_type=snapshot.source_type,
        published_date=snapshot.snapshot_date,
        scope_type="city",
        scope_name=snapshot.region,
        ring_scope="all",
        property_segment="new_home" if is_new_home else "resale",
        price_mom=snapshot.new_home_price_mom if is_new_home else snapshot.resale_price_mom,
        price_yoy=snapshot.new_home_price_yoy if is_new_home else snapshot.resale_price_yoy,
        avg_unit_price=snapshot.avg_unit_price,
        sample_size=snapshot.transaction_count,
        credibility_score=snapshot.housing_data_quality_score,
        notes=snapshot.notes,
    )


def _market_signal(
    scenario: ScenarioData,
    snapshot: MarketSnapshotData,
    *,
    valued_on: date,
) -> MarketSignalSummary:
    is_new_home = "新房" in scenario.property_type
    evidence_items = [_snapshot_evidence(snapshot, is_new_home=is_new_home), *snapshot.housing_market_evidence]
    source_signals: list[tuple[float, float, HousingMarketEvidenceData, bool]] = []
    local_prices: list[tuple[float, float, HousingMarketEvidenceData]] = []
    city_prices: list[tuple[float, float, HousingMarketEvidenceData]] = []
    source_names: list[str] = []
    source_types: set[str] = set()
    quality_pairs: list[tuple[float, float]] = []
    drivers: list[str] = []
    matched_location_name = ""
    matched_ring_area = ""

    for evidence in evidence_items:
        if not _evidence_matches_property(evidence, is_new_home=is_new_home):
            continue
        if not _ring_match(scenario, evidence):
            continue
        matched = _location_match(scenario, evidence)
        weight = _evidence_weight(evidence, valued_on=valued_on, location_match=matched)
        signal_parts: list[tuple[float, float]] = []
        if evidence.price_yoy is not None:
            signal_parts.append((evidence.price_yoy, 0.78))
        annualized_mom = _annualized_monthly(evidence.price_mom)
        if annualized_mom is not None:
            signal_parts.append((annualized_mom, 0.22))
        if signal_parts:
            part_weight = sum(item_weight for _, item_weight in signal_parts)
            signal = sum(value * item_weight for value, item_weight in signal_parts) / part_weight
            source_signals.append((_clamp(signal, -0.15, 0.15), weight, evidence, matched))
            if matched:
                matched_location_name = evidence.scope_name or matched_location_name
                if evidence.ring_scope != "all":
                    matched_ring_area = evidence.ring_scope
        if matched and evidence.avg_unit_price is not None and evidence.avg_unit_price > 0:
            local_prices.append((evidence.avg_unit_price, weight, evidence))
            matched_location_name = evidence.scope_name or matched_location_name
            if evidence.ring_scope != "all":
                matched_ring_area = evidence.ring_scope
        elif evidence.scope_type == "city" and evidence.avg_unit_price is not None and evidence.avg_unit_price > 0:
            city_prices.append((evidence.avg_unit_price, weight, evidence))
        if signal_parts or (evidence.avg_unit_price is not None and evidence.avg_unit_price > 0):
            if evidence.source_name and evidence.source_name not in source_names:
                source_names.append(evidence.source_name)
            source_types.add(evidence.source_type)
            quality_pairs.append((evidence.credibility_score, weight))

    if source_signals:
        total_weight = sum(weight for _, weight, _, _ in source_signals)
        signal = sum(value * weight for value, weight, _, _ in source_signals) / total_weight
        local_signals = [(value, weight) for value, weight, _, matched in source_signals if matched]
        local_signal = (
            sum(value * weight for value, weight in local_signals) / sum(weight for _, weight in local_signals)
            if local_signals
            else None
        )
        top_sources = sorted(source_signals, key=lambda item: item[1], reverse=True)[:5]
        for value, weight, evidence, matched in top_sources:
            scope_text = (
                f"，命中{evidence.scope_name}{' · ' + evidence.ring_scope if evidence.ring_scope != 'all' else ''}"
                if matched
                else ""
            )
            drivers.append(
                f"{SOURCE_TYPE_LABEL[evidence.source_type]}“{evidence.source_name or '未命名来源'}”"
                f"提供 {value:.1%} 周期信号{scope_text}，综合权重 {weight:.2f}"
            )
    else:
        signal = snapshot.long_term_anchor_growth_rate
        local_signal = None
        drivers.append("所有来源均缺少可用同比/环比，当前仅使用长期锚定增速")

    if local_prices:
        price_weight = sum(weight for _, weight, _ in local_prices)
        local_unit_price = sum(price * weight for price, weight, _ in local_prices) / price_weight
        if not matched_location_name:
            matched_location_name = local_prices[0][2].scope_name
        drivers.append(f"命中{matched_location_name or scenario.district}地段样本，区域加权单价约 {local_unit_price:,.0f} 元/㎡")
    else:
        local_unit_price = 0.0
    if city_prices:
        city_price_weight = sum(weight for _, weight, _ in city_prices)
        city_unit_price = sum(price * weight for price, weight, _ in city_prices) / city_price_weight
    else:
        city_unit_price = 0.0

    quality_weight = sum(weight for _, weight in quality_pairs)
    weighted_quality = (
        sum(value * weight for value, weight in quality_pairs) / quality_weight
        if quality_weight > 0
        else snapshot.housing_data_quality_score
    )
    return MarketSignalSummary(
        signal=_clamp(signal, -0.15, 0.15),
        local_signal=_clamp(local_signal, -0.15, 0.15) if local_signal is not None else None,
        local_unit_price=max(0.0, local_unit_price),
        city_unit_price=max(0.0, city_unit_price),
        matched_location_name=matched_location_name,
        matched_ring_area=matched_ring_area,
        drivers=drivers,
        signal_count=len(source_signals),
        source_names=source_names,
        source_types=source_types,
        weighted_quality=_clamp(weighted_quality, 0.0, 1.0),
        media_only=bool(source_types) and source_types == {"media"},
    )


def _structural_adjustment(scenario: ScenarioData) -> tuple[float, float, float, list[str]]:
    annual_adjustment = 0.0
    age_adjustment = 0.0
    liquidity_discount = 0.02
    drivers: list[str] = []
    if scenario.building_age_years > 20:
        age_adjustment = -min(0.012, (scenario.building_age_years - 20) * 0.0005)
        annual_adjustment += age_adjustment
        liquidity_discount += min(0.03, (scenario.building_age_years - 20) * 0.001)
        drivers.append(f"房龄 {scenario.building_age_years} 年，对长期保值率作 {age_adjustment:.1%} 年化修正")
    if scenario.is_old_community_renovated:
        annual_adjustment += 0.002
        liquidity_discount = max(0.01, liquidity_discount - 0.01)
        drivers.append("老旧小区已改造，小幅改善长期保值与流动性")
    if scenario.building_structure == "brick_mixed":
        annual_adjustment -= 0.003
        liquidity_discount += 0.01
        drivers.append("砖混结构提高了长期折旧与成交折价假设")
    elif scenario.building_structure in {"steel_concrete", "steel"}:
        annual_adjustment += 0.001
        drivers.append("钢混/钢结构给予轻微保值修正")
    if scenario.remaining_land_use_years is not None and scenario.remaining_land_use_years < 40:
        land_adjustment = -min(0.008, (40 - scenario.remaining_land_use_years) * 0.0004)
        annual_adjustment += land_adjustment
        liquidity_discount += min(0.025, (40 - scenario.remaining_land_use_years) * 0.001)
        drivers.append(f"剩余土地年限 {scenario.remaining_land_use_years} 年，降低长期增速并扩大流动性折价")
    if scenario.area_sqm < 40 or scenario.area_sqm > 140:
        liquidity_discount += 0.01
        drivers.append("面积处于非主流成交区间，净变现价值采用更高流动性折价")
    if scenario.green_building_level in {"two_star", "three_star"} or scenario.is_ultra_low_energy_building:
        annual_adjustment += 0.002
        drivers.append("绿色/超低能耗属性给予轻微长期保值修正")
    ring_area = scenario.ring_area
    if any(label in ring_area for label in ("六环外", "远郊")):
        liquidity_discount += 0.015
        drivers.append(f"地段位于{ring_area}，提高快速变现折价，但不直接假设长期必然下跌")
    elif any(label in ring_area for label in ("五环外", "五至六环")):
        liquidity_discount += 0.008
        drivers.append(f"地段位于{ring_area}，轻微提高流动性折价")
    elif any(label in ring_area for label in ("二环", "三环", "四环内")):
        liquidity_discount = max(0.01, liquidity_discount - 0.005)
        drivers.append(f"地段位于{ring_area}，流动性折价小幅降低；价格水平仍优先使用区域样本")
    return (
        _clamp(annual_adjustment, -0.025, 0.015),
        _clamp(age_adjustment, -0.02, 0.01),
        _clamp(liquidity_discount, 0.01, 0.10),
        drivers,
    )


def estimate_property_value(
    scenario: ScenarioData,
    snapshot: MarketSnapshotData,
    *,
    valuation_date: date | None = None,
) -> PropertyValuationData:
    valued_on = valuation_date or date.today()
    snapshot_date = _parse_date(snapshot.snapshot_date, valued_on)
    reference_date = _parse_date(scenario.valuation_reference_date, snapshot_date)
    reference_value = scenario.valuation_reference_value or scenario.total_price
    market_summary = _market_signal(scenario, snapshot, valued_on=valued_on)
    local_comparable_value = market_summary.local_unit_price * scenario.area_sqm if scenario.area_sqm > 0 else 0.0
    city_comparable_value = market_summary.city_unit_price * scenario.area_sqm if scenario.area_sqm > 0 else 0.0
    if scenario.valuation_comparable_unit_price > 0 and scenario.area_sqm > 0:
        comparable_value = scenario.valuation_comparable_unit_price * scenario.area_sqm
        if local_comparable_value > 0:
            reference_value = (
                reference_value * 0.45 + comparable_value * 0.35 + local_comparable_value * 0.20
                if reference_value > 0
                else comparable_value * 0.65 + local_comparable_value * 0.35
            )
        else:
            reference_value = reference_value * 0.65 + comparable_value * 0.35 if reference_value > 0 else comparable_value
    elif local_comparable_value > 0:
        reference_value = reference_value * 0.55 + local_comparable_value * 0.45 if reference_value > 0 else local_comparable_value
    elif city_comparable_value > 0:
        reference_value = reference_value * 0.85 + city_comparable_value * 0.15 if reference_value > 0 else city_comparable_value
    reference_value = max(0.0, reference_value)

    market_signal = market_summary.signal
    structural_adjustment, age_adjustment, liquidity_discount, structural_drivers = _structural_adjustment(scenario)
    anchor = _clamp(snapshot.long_term_anchor_growth_rate, -0.05, 0.08)
    location_adjustment = (
        _clamp((market_summary.local_signal - market_signal) * 0.2, -0.015, 0.015)
        if market_summary.local_signal is not None
        else 0.0
    )
    if location_adjustment:
        structural_drivers.append(
            f"{market_summary.matched_location_name or scenario.district}区域周期相对全市形成 {location_adjustment:.1%} 年化地段修正"
        )
    long_term_rate = _clamp(anchor + structural_adjustment + location_adjustment, -0.04, 0.06)
    cycle_gap = _clamp(market_signal - anchor, -0.12, 0.12)
    near_term_rate = _clamp(long_term_rate + cycle_gap * 0.55, -0.08, 0.08)

    elapsed_months = _months_between(reference_date, valued_on)
    elapsed_years = elapsed_months / 12
    long_factor = (1 + long_term_rate) ** elapsed_years
    cycle_years = min(elapsed_months, 12) / 12
    cycle_factor = (1 + cycle_gap * 0.55) ** cycle_years
    district_factor = 1 + _clamp(scenario.valuation_district_adjustment_rate, -0.3, 0.3)
    estimated_value = max(0.0, reference_value * long_factor * cycle_factor * district_factor)

    confidence = 0.30 + market_summary.weighted_quality * 0.25
    confidence += min(0.16, market_summary.signal_count * 0.04)
    confidence += min(0.08, max(0, len(market_summary.source_types) - 1) * 0.025)
    if scenario.valuation_comparable_unit_price > 0:
        confidence += 0.10
    if market_summary.local_unit_price > 0:
        confidence += 0.10
    if elapsed_months <= 24:
        confidence += 0.06
    confidence = _clamp(confidence, 0.35, 0.9)
    interval_rate = _clamp(0.04 + (1 - confidence) * 0.18, 0.05, 0.16)
    lower_value = estimated_value * (1 - interval_rate)
    upper_value = estimated_value * (1 + interval_rate)
    sale_cost_rate = 0.03
    net_realisable_value = estimated_value * (1 - sale_cost_rate - liquidity_discount)

    projection: list[PropertyValuationProjectionPoint] = []
    for month in (0, 12, 24, 36, 48, 60):
        years = month / 12
        decayed_cycle = cycle_gap * 0.55 * math.exp(-month / 18)
        projected_rate = _clamp(long_term_rate + decayed_cycle, -0.08, 0.08)
        projected_value = estimated_value * (1 + projected_rate) ** years
        widening = min(0.26, interval_rate + month / 600)
        projection.append(
            PropertyValuationProjectionPoint(
                month=month,
                label=str(_add_months(valued_on, month).year),
                estimated_value=round(max(0.0, projected_value), 2),
                lower_value=round(max(0.0, projected_value * (1 - widening)), 2),
                upper_value=round(max(0.0, projected_value * (1 + widening)), 2),
            )
        )

    warnings = [
        "估值是决策区间，不是可成交承诺；真实成交还受楼层、朝向、装修、学区、噪音和具体小区供需影响。",
        "短期环比只影响近端周期项，并在未来 18 个月指数衰减，不会按当前涨跌幅长期外推。",
    ]
    if market_summary.signal_count == 0:
        warnings.append("当前市场快照缺少房价变化指标，估值置信度较低。")
    if market_summary.media_only:
        warnings.append("当前有效市场信号全部来自媒体新闻，只能低权重影响近端判断，建议补充政府、研究机构或成交平台数据。")
    if len(market_summary.source_types) <= 1:
        warnings.append("市场来源类型较单一，建议至少交叉核对政府统计、专业机构和经纪/平台中的两类来源。")
    if not market_summary.matched_location_name:
        warnings.append(f"未找到直接命中“{scenario.district}”的区级或小区级样本，地段估计主要依赖手工修正与全市数据。")
    if scenario.valuation_comparable_unit_price <= 0:
        warnings.append("未填写同小区可比成交单价，区间会比有可比成交时更宽。")

    next_due = _add_months(valued_on, scenario.valuation_interval_months)
    return PropertyValuationData(
        property_name=scenario.name,
        valuation_date=valued_on.isoformat(),
        reference_date=reference_date.isoformat(),
        reference_value=round(reference_value, 2),
        estimated_market_value=round(estimated_value, 2),
        estimated_unit_price=round(estimated_value / scenario.area_sqm, 2) if scenario.area_sqm > 0 else 0,
        lower_value=round(lower_value, 2),
        upper_value=round(upper_value, 2),
        net_realisable_value=round(max(0.0, net_realisable_value), 2),
        confidence_score=round(confidence, 4),
        market_signal_rate=round(market_signal, 6),
        near_term_annual_rate=round(near_term_rate, 6),
        long_term_annual_rate=round(long_term_rate, 6),
        structural_rate_adjustment=round(structural_adjustment, 6),
        location_rate_adjustment=round(location_adjustment, 6),
        building_age_rate_adjustment=round(age_adjustment, 6),
        location_reference_unit_price=round(market_summary.local_unit_price, 2),
        sale_cost_rate=sale_cost_rate,
        liquidity_discount_rate=round(liquidity_discount, 6),
        market_snapshot_date=snapshot_date.isoformat(),
        market_source_name="、".join(market_summary.source_names[:3]) or snapshot.source_name,
        market_source_names=market_summary.source_names,
        market_source_count=len(market_summary.source_names),
        matched_location_name=market_summary.matched_location_name,
        matched_ring_area=market_summary.matched_ring_area,
        next_due_date=next_due.isoformat(),
        drivers=market_summary.drivers + structural_drivers,
        warnings=warnings,
        projection=projection,
    )


def projected_purchase_price(
    valuation: PropertyValuationData,
    *,
    asking_price: float,
    month: int,
) -> tuple[float, float, float]:
    """Return a prudent target transaction-price range for a future month.

    The current asking price remains a floor for the central planning budget:
    an appraisal below the listing price is negotiation evidence, not a promise
    that the seller will transact there.  The short-cycle component converges
    exponentially to the structural long-term anchor instead of being
    compounded unchanged across the planning horizon.
    """
    target_month = max(0, min(600, int(month)))
    estimated_now = max(0.0, valuation.estimated_market_value)
    prudent_now = max(max(0.0, asking_price), estimated_now)
    lower_now = max(0.0, min(prudent_now, valuation.lower_value))
    upper_now = max(prudent_now, valuation.upper_value)
    central = prudent_now
    lower = lower_now
    upper = upper_now
    long_rate = _clamp(valuation.long_term_annual_rate, -0.04, 0.06)
    cycle_spread = _clamp(valuation.near_term_annual_rate - long_rate, -0.08, 0.08)
    for current_month in range(1, target_month + 1):
        annual_rate = _clamp(
            long_rate + cycle_spread * math.exp(-(current_month - 1) / 18),
            -0.08,
            0.08,
        )
        monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
        central *= 1 + monthly_rate
        uncertainty_rate = min(0.0035, 0.0012 + current_month / (240 * 1_000))
        lower *= max(0.0, 1 + monthly_rate - uncertainty_rate)
        upper *= 1 + monthly_rate + uncertainty_rate
    return round(central, 2), round(lower, 2), round(upper, 2)


__all__ = ["estimate_property_value", "projected_purchase_price"]
