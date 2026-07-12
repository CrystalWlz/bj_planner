from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import date, timedelta
from statistics import median

import httpx

from ..schemas import (
    PersonalPensionReturnEvidenceData,
    PersonalPensionReturnSnapshotData,
    PersonalPensionReturnSourceData,
)
from ..source_monitor import html_to_text


DEFAULT_PERSONAL_PENSION_RETURN_SOURCES = [
    PersonalPensionReturnSourceData(
        name="东方财富公开 FOF 基金排行",
        url="https://fund.eastmoney.com/data/rankhandler.aspx",
        source_type="institution",
        product_type="fund",
        credibility_score=0.72,
        parser="eastmoney_fof_rank",
    ),
    PersonalPensionReturnSourceData(
        name="中国理财网个人养老金理财产品信息",
        url="https://www.chinawealth.com.cn/zzlc/jgxx/yljlc/",
        source_type="registry",
        product_type="wealth",
        credibility_score=0.9,
    ),
    PersonalPensionReturnSourceData(
        name="中证指数养老主题与目标日期指数信息",
        url="https://www.csindex.com.cn/",
        source_type="index_provider",
        product_type="fund",
        credibility_score=0.85,
    ),
    PersonalPensionReturnSourceData(
        name="个人养老金制度官方政策",
        url="https://www.gov.cn/zhengce/zhengceku/202412/content_6992279.htm",
        source_type="government",
        product_type="mixed",
        credibility_score=1.0,
    ),
]

SOURCE_WEIGHTS = {
    "government": 1.0,
    "registry": 0.95,
    "index_provider": 0.88,
    "institution": 0.75,
    "media": 0.4,
    "other": 0.5,
}
RETURN_CONTEXT = re.compile(
    r"(?:近一年|过去一年|年化收益率|年化回报率|成立以来年化|收益率|回报率|业绩比较基准)"
    r"[^%]{0,48}?(-?\d{1,2}(?:\.\d{1,4})?)\s*%",
    re.IGNORECASE,
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _limited_update(previous: float, target: float, limit: float) -> float:
    return _clamp(target, previous - limit, previous + limit)


def extract_observed_returns(text: str) -> list[float]:
    values: list[float] = []
    for raw in RETURN_CONTEXT.findall(text):
        value = float(raw) / 100
        if -0.15 <= value <= 0.20:
            values.append(value)
    return values


async def fetch_return_evidence(
    source: PersonalPensionReturnSourceData,
    *,
    client: httpx.AsyncClient,
    today: date,
) -> PersonalPensionReturnEvidenceData:
    fetch_url = str(source.url)
    headers: dict[str, str] = {}
    if source.parser == "eastmoney_fof_rank":
        fetch_url = (
            f"{fetch_url}?op=ph&dt=kf&ft=fof&rs=&gs=0&sc=1nzf&st=desc"
            f"&sd={(today - timedelta(days=365)).isoformat()}&ed={today.isoformat()}"
            "&qdii=&tabSubtype=,,,,,&pi=1&pn=200&dx=1&v=0.1"
        )
        headers["Referer"] = "https://fund.eastmoney.com/data/fundranking.html"
    try:
        response = await client.get(fetch_url, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return PersonalPensionReturnEvidenceData(
            source_name=source.name,
            source_url=str(source.url),
            source_type=source.source_type,
            product_type=source.product_type,
            fetched_at=today.isoformat(),
            status="fetch_failed",
            note=f"抓取失败：{type(exc).__name__}",
        )
    values: list[float]
    if source.parser == "eastmoney_fof_rank":
        values = []
        match = re.search(r"datas:(\[[\s\S]*?\]),allRecords", response.text)
        if match:
            try:
                rows = json.loads(match.group(1))
            except json.JSONDecodeError:
                rows = []
            for row in rows:
                parts = row.split(",") if isinstance(row, str) else []
                if len(parts) <= 11:
                    continue
                try:
                    annual_return = float(parts[11]) / 100
                except (TypeError, ValueError):
                    continue
                if -0.30 <= annual_return <= 0.50:
                    values.append(annual_return)
    else:
        values = extract_observed_returns(html_to_text(response.text))
    return PersonalPensionReturnEvidenceData(
        source_name=source.name,
        source_url=str(source.url),
        source_type=source.source_type,
        product_type=source.product_type,
        fetched_at=today.isoformat(),
        observed_annual_return=round(median(values), 6) if values else None,
        sample_count=len(values),
        status="parsed" if values else "no_rate",
        note=(
            f"从含收益语义的文本中提取 {len(values)} 个年化样本并取中位数。"
            if values
            else "页面可访问，但未发现可安全识别的年化收益数据；不据此修改收益假设。"
        ),
    )


def build_personal_pension_return_snapshot(
    evidence: list[PersonalPensionReturnEvidenceData],
    *,
    today: date,
    previous: PersonalPensionReturnSnapshotData | None = None,
) -> PersonalPensionReturnSnapshotData:
    parsed = [item for item in evidence if item.status == "parsed" and item.observed_annual_return is not None]
    weighted_values: list[tuple[float, float]] = []
    for item in parsed:
        weight = SOURCE_WEIGHTS.get(item.source_type, 0.5) * min(1.0, 0.65 + math.log1p(item.sample_count) / 10)
        weighted_values.append((float(item.observed_annual_return), weight))
    observed = (
        sum(value * weight for value, weight in weighted_values) / sum(weight for _, weight in weighted_values)
        if weighted_values
        else None
    )
    previous_pre = previous.pre_retirement_annual_return if previous else 0.025
    previous_post = previous.post_retirement_annual_return if previous else 0.015
    if previous is not None and previous.snapshot_date == today.isoformat():
        pre = previous_pre
        post = previous_post
    elif observed is None:
        pre = previous_pre
        post = previous_post
    else:
        anchored_target = 0.70 * 0.025 + 0.30 * _clamp(observed, -0.05, 0.10)
        pre = _limited_update(previous_pre, anchored_target, 0.005)
        post_target = _clamp(pre * 0.60, 0.005, min(0.03, pre if pre > 0 else 0.005))
        post = _limited_update(previous_post, post_target, 0.003)
    conservative = _clamp(min(pre, post) - 0.008, -0.03, 0.04)
    optimistic = _clamp(max(pre + 0.015, observed or pre), 0.015, 0.08)
    warnings: list[str] = []
    if not parsed:
        warnings.append("本次没有抓取到可安全解析的收益率，继续沿用上一期或系统长期锚，不做静默修改。")
    if parsed and all(item.product_type == "fund" for item in parsed):
        warnings.append("本次有效样本仅来自基金/指数，不足以代表存款、理财和保险产品，退休后假设仍采用保守折减。")
    return PersonalPensionReturnSnapshotData(
        snapshot_date=today.isoformat(),
        pre_retirement_annual_return=round(pre, 6),
        post_retirement_annual_return=round(post, 6),
        conservative_annual_return=round(conservative, 6),
        optimistic_annual_return=round(optimistic, 6),
        observed_market_return=round(observed, 6) if observed is not None else None,
        source_count=len(evidence),
        parsed_source_count=len(parsed),
        next_due_date=(today + timedelta(days=30)).isoformat(),
        evidence=evidence,
        drivers=[
            "自动模式以长期锚为主，仅用多来源市场样本作有限修正。",
            "单次刷新退休前年化最多调整 0.5 个百分点，退休后最多调整 0.3 个百分点。",
            "短期产品收益或指数涨跌不会直接外推为几十年的固定收益。",
        ],
        warnings=warnings,
    )


async def refresh_personal_pension_return_snapshot(
    sources: list[PersonalPensionReturnSourceData],
    *,
    today: date,
    previous: PersonalPensionReturnSnapshotData | None = None,
) -> PersonalPensionReturnSnapshotData:
    effective_sources = sources or DEFAULT_PERSONAL_PENSION_RETURN_SOURCES
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        evidence = list(
            await asyncio.gather(
                *(fetch_return_evidence(source, client=client, today=today) for source in effective_sources)
            )
        )
    return build_personal_pension_return_snapshot(evidence, today=today, previous=previous)


__all__ = [
    "DEFAULT_PERSONAL_PENSION_RETURN_SOURCES",
    "build_personal_pension_return_snapshot",
    "extract_observed_returns",
    "refresh_personal_pension_return_snapshot",
]
