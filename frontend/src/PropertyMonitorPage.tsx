import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Building2, Database, Plus, RefreshCw, Save, ShieldCheck, Trash2, TrendingUp } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { createMarketSnapshot, fetchPropertyValuations, fetchSourcePreview, refreshPropertyValuation } from "./api";
import { money, percent } from "./format";
import type { HousingMarketEvidenceData, MarketSnapshotData, PropertyValuationRecord, PurchasePlanAnalysis, RecordEnvelope, ScenarioData, SourceDocumentRecord } from "./types";

type Props = {
  householdId: string;
  scenarios: RecordEnvelope<ScenarioData>[];
  marketSnapshots: RecordEnvelope<MarketSnapshotData>[];
  purchasePlans: PurchasePlanAnalysis[];
  onUpdateScenario: (id: string, patch: Partial<ScenarioData>) => void;
  onMarketSnapshotCreated: (snapshot: RecordEnvelope<MarketSnapshotData>) => void;
};

const today = () => new Date().toISOString().slice(0, 10);

function defaultMarketSnapshot(latest?: RecordEnvelope<MarketSnapshotData> | null): MarketSnapshotData {
  return {
    schema_version: latest?.data.schema_version ?? 54,
    region: "北京",
    snapshot_date: today(),
    source_name: latest?.data.source_name ?? "手动录入",
    source_url: latest?.data.source_url ?? "https://zjw.beijing.gov.cn/bjjs/fwgl/fdcjy/index.shtml",
    source_type: latest?.data.source_type ?? "government",
    commercial_loan_rate: latest?.data.commercial_loan_rate ?? null,
    default_broker_fee_rate: latest?.data.default_broker_fee_rate ?? null,
    seller_tax_pass_through_rate: latest?.data.seller_tax_pass_through_rate ?? null,
    avg_unit_price: latest?.data.avg_unit_price ?? null,
    transaction_count: latest?.data.transaction_count ?? null,
    listing_count: latest?.data.listing_count ?? null,
    resale_price_mom: latest?.data.resale_price_mom ?? null,
    resale_price_yoy: latest?.data.resale_price_yoy ?? null,
    new_home_price_mom: latest?.data.new_home_price_mom ?? null,
    new_home_price_yoy: latest?.data.new_home_price_yoy ?? null,
    long_term_anchor_growth_rate: latest?.data.long_term_anchor_growth_rate ?? 0.015,
    housing_data_quality_score: latest?.data.housing_data_quality_score ?? 0.6,
    housing_market_evidence: latest?.data.housing_market_evidence ?? [],
    notes: ""
  };
}

function defaultMarketEvidence(): HousingMarketEvidenceData {
  return {
    source_name: "",
    source_url: "",
    source_type: "research",
    published_date: today(),
    scope_type: "city",
    scope_name: "北京",
    ring_scope: "all",
    property_segment: "resale",
    price_mom: null,
    price_yoy: null,
    avg_unit_price: null,
    sample_size: null,
    credibility_score: 0.7,
    notes: ""
  };
}

function optionalNumber(value: string) {
  return value === "" ? null : Number(value);
}

export function PropertyMonitorPage({
  householdId,
  scenarios,
  marketSnapshots,
  purchasePlans,
  onUpdateScenario,
  onMarketSnapshotCreated
}: Props) {
  const latestMarketSnapshot = marketSnapshots.at(-1) ?? null;
  const [selectedId, setSelectedId] = useState(scenarios[0]?.id ?? "");
  const [valuations, setValuations] = useState<PropertyValuationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshingId, setRefreshingId] = useState("");
  const [error, setError] = useState("");
  const [previewingUrl, setPreviewingUrl] = useState("");
  const [sourcePreviews, setSourcePreviews] = useState<Record<string, SourceDocumentRecord>>({});
  const [marketDraft, setMarketDraft] = useState<MarketSnapshotData>(() => defaultMarketSnapshot(latestMarketSnapshot));
  const selectedScenario = scenarios.find((item) => item.id === selectedId) ?? scenarios[0] ?? null;
  const selectedGoalId = selectedScenario?.data.planning_goal_id || selectedScenario?.id || "";
  const selectedStrategyPlan = useMemo(() => {
    const plans = purchasePlans.filter((plan) => plan.planning_goal_id === selectedGoalId && plan.source !== "baseline");
    return plans.find((plan) => plan.is_recommended)
      ?? plans.find((plan) => plan.variant === selectedScenario?.data.selected_purchase_plan_variant)
      ?? plans[0]
      ?? null;
  }, [purchasePlans, selectedGoalId, selectedScenario?.data.selected_purchase_plan_variant]);

  useEffect(() => {
    if (selectedScenario || !scenarios.length) return;
    setSelectedId(scenarios[0].id);
  }, [scenarios, selectedScenario]);

  useEffect(() => {
    setMarketDraft(defaultMarketSnapshot(latestMarketSnapshot));
  }, [latestMarketSnapshot?.id]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        let records = await fetchPropertyValuations(householdId);
        if (latestMarketSnapshot) {
          const dueResults = await Promise.all(
            scenarios
              .filter((item) => item.data.valuation_monitoring_enabled)
              .map((item) => refreshPropertyValuation({
                household_id: householdId,
                planning_goal_id: item.data.planning_goal_id || item.id,
                property_data: item.data,
                market_snapshot_id: latestMarketSnapshot.id,
                market_snapshot: latestMarketSnapshot.data,
                force: false
              }))
          );
          if (dueResults.some((item) => item.refreshed)) {
            records = await fetchPropertyValuations(householdId);
          }
        }
        if (!cancelled) setValuations(records);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "加载房产估值失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [householdId, latestMarketSnapshot?.id]);

  const latestByGoal = useMemo(() => {
    const values = new Map<string, PropertyValuationRecord>();
    for (const valuation of valuations) {
      if (!values.has(valuation.planning_goal_id)) values.set(valuation.planning_goal_id, valuation);
    }
    return values;
  }, [valuations]);
  const latestValuation = selectedGoalId ? latestByGoal.get(selectedGoalId) ?? null : null;
  const selectedHistory = selectedGoalId
    ? valuations.filter((item) => item.planning_goal_id === selectedGoalId)
    : [];

  const refreshSelected = async (force: boolean) => {
    if (!selectedScenario || !latestMarketSnapshot) return;
    setRefreshingId(selectedScenario.id);
    setError("");
    try {
      const response = await refreshPropertyValuation({
        household_id: householdId,
        planning_goal_id: selectedGoalId,
        property_data: selectedScenario.data,
        market_snapshot_id: latestMarketSnapshot.id,
        market_snapshot: latestMarketSnapshot.data,
        force
      });
      setValuations((items) => [
        response.record,
        ...items.filter((item) => item.id !== response.record.id)
      ].sort((a, b) => b.valuation_date.localeCompare(a.valuation_date)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新房产估值失败");
    } finally {
      setRefreshingId("");
    }
  };

  const saveMarketSnapshot = async () => {
    setError("");
    try {
      const created = await createMarketSnapshot(marketDraft);
      onMarketSnapshotCreated(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存市场快照失败");
    }
  };

  const updateEvidence = (index: number, patch: Partial<HousingMarketEvidenceData>) => {
    setMarketDraft((current) => ({
      ...current,
      housing_market_evidence: current.housing_market_evidence.map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      ))
    }));
  };

  const addEvidence = () => {
    setMarketDraft((current) => ({
      ...current,
      housing_market_evidence: [...current.housing_market_evidence, defaultMarketEvidence()]
    }));
  };

  const removeEvidence = (index: number) => {
    setMarketDraft((current) => ({
      ...current,
      housing_market_evidence: current.housing_market_evidence.filter((_, itemIndex) => itemIndex !== index)
    }));
  };

  const previewEvidenceSource = async (evidence: HousingMarketEvidenceData) => {
    const sourceUrl = evidence.source_url.trim();
    if (!sourceUrl) {
      setError("请先填写第三方机构或新闻来源链接。");
      return;
    }
    setPreviewingUrl(sourceUrl);
    setError("");
    try {
      const preview = await fetchSourcePreview(sourceUrl, evidence.source_name || undefined);
      setSourcePreviews((current) => ({ ...current, [sourceUrl]: preview }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取第三方来源失败");
    } finally {
      setPreviewingUrl("");
    }
  };

  if (!scenarios.length) {
    return (
      <div className="page-stack property-monitor-page">
        <section className="planner-page-intro">
          <div className="property-monitor-title"><Building2 size={20} /><h2>房产价值监测</h2></div>
          <div className="planner-summary-band"><p>先在购房计划添加房产目标，再为目标建立估值基准和定期监测。</p></div>
        </section>
        <section className="empty-state">当前没有可监测的房产目标。</section>
      </div>
    );
  }

  return (
    <div className="page-stack property-monitor-page">
      <section className="planner-page-intro">
        <div className="property-monitor-title"><Building2 size={20} /><h2>房产价值监测</h2></div>
        <div className="planner-summary-band">
          <p>按多来源北京大盘、区/片区成交单价、环线地段、房龄、结构、改造和土地年限估算价值区间。买入前预测会逐月进入购房策略，重新计算成交税费、首付、贷款和现金风险；新闻只低权重影响近端周期，不会被永久外推。</p>
        </div>
      </section>

      {error ? <div className="property-monitor-error"><AlertTriangle size={16} />{error}</div> : null}

      <section className="property-monitor-summary">
        <article><span>当前估值</span><strong>{latestValuation ? money(latestValuation.data.estimated_market_value) : "待估值"}</strong></article>
        <article><span>估值区间</span><strong>{latestValuation ? `${money(latestValuation.data.lower_value)} - ${money(latestValuation.data.upper_value)}` : "-"}</strong></article>
        <article><span>净变现价值</span><strong>{latestValuation ? money(latestValuation.data.net_realisable_value) : "-"}</strong></article>
        <article><span>置信度</span><strong>{latestValuation ? percent(latestValuation.data.confidence_score) : "-"}</strong></article>
        <article><span>下次检查</span><strong>{latestValuation?.data.next_due_date ?? "首次更新后生成"}</strong></article>
      </section>

      {selectedStrategyPlan ? (
        <section className="property-monitor-summary property-strategy-impact">
          <article><span>当前采用策略</span><strong>{selectedStrategyPlan.variant}</strong></article>
          <article><span>预计买入月份</span><strong>{selectedStrategyPlan.months_to_buy === null ? "暂不可达" : `${selectedStrategyPlan.months_to_buy} 个月后`}</strong></article>
          <article><span>买入月预测价格</span><strong>{money(selectedStrategyPlan.projected_purchase_price || selectedStrategyPlan.original_target_price)}</strong></article>
          <article><span>预测区间</span><strong>{`${money(selectedStrategyPlan.projected_purchase_price_lower)} - ${money(selectedStrategyPlan.projected_purchase_price_upper)}`}</strong></article>
          <article><span>策略影响</span><strong>{selectedStrategyPlan.property_price_forecast_applied ? "已计入首付、贷款和现金风险" : "等待行情快照"}</strong></article>
        </section>
      ) : null}

      <section className="property-monitor-card-list" aria-label="房产监测列表">
        {scenarios.map((scenario) => {
          const goalId = scenario.data.planning_goal_id || scenario.id;
          const valuation = latestByGoal.get(goalId);
          return (
            <button
              className={scenario.id === selectedScenario?.id ? "property-monitor-card active" : "property-monitor-card"}
              key={scenario.id}
              onClick={() => setSelectedId(scenario.id)}
              type="button"
            >
              <span>{scenario.data.valuation_asset_status === "owned" ? "已持有" : "规划目标"}</span>
              <strong>{scenario.data.name}</strong>
              <small>{scenario.data.district} · {scenario.data.property_type} · {scenario.data.area_sqm}㎡</small>
              <b>{valuation ? money(valuation.data.estimated_market_value) : money(scenario.data.total_price)}</b>
              <em>{scenario.data.valuation_monitoring_enabled ? "定期监测中" : "未启用监测"}</em>
            </button>
          );
        })}
      </section>

      <section className="property-monitor-workspace">
        <div className="property-monitor-panel">
          <div className="property-monitor-panel-title"><ShieldCheck size={18} /><div><strong>估值基准与频率</strong><p>基准价值不会被估值结果反向覆盖。</p></div></div>
          {selectedScenario ? (
            <div className="property-monitor-form-grid">
              <label className="property-monitor-switch">
                <input type="checkbox" checked={selectedScenario.data.valuation_monitoring_enabled} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_monitoring_enabled: event.target.checked })} />
                <span>启用定期监测</span>
              </label>
              <label><span>资产状态</span><select value={selectedScenario.data.valuation_asset_status} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_asset_status: event.target.value as ScenarioData["valuation_asset_status"] })}><option value="planned">规划目标</option><option value="owned">已持有房产</option></select></label>
              <label><span>更新间隔（月）</span><input type="number" min={1} max={24} value={selectedScenario.data.valuation_interval_months} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_interval_months: Number(event.target.value) })} /></label>
              <label><span>基准日期</span><input type="date" value={selectedScenario.data.valuation_reference_date} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_reference_date: event.target.value })} /></label>
              <label><span>基准价值</span><input type="number" min={0} step={10000} value={selectedScenario.data.valuation_reference_value} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_reference_value: Number(event.target.value) })} /></label>
              <label><span>同小区可比成交单价</span><input type="number" min={0} step={100} value={selectedScenario.data.valuation_comparable_unit_price} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_comparable_unit_price: Number(event.target.value) })} /></label>
              <label><span>片区相对修正</span><input type="number" min={-0.3} max={0.3} step={0.01} value={selectedScenario.data.valuation_district_adjustment_rate} onChange={(event) => onUpdateScenario(selectedScenario.id, { valuation_district_adjustment_rate: Number(event.target.value) })} /></label>
              <button className="primary-button" type="button" disabled={!latestMarketSnapshot || refreshingId === selectedScenario.id} onClick={() => void refreshSelected(true)}><RefreshCw size={16} className={refreshingId === selectedScenario.id ? "spin" : ""} />立即更新估值</button>
            </div>
          ) : null}
        </div>

        <div className="property-monitor-panel">
          <div className="property-monitor-panel-title"><Database size={18} /><div><strong>多来源行情快照</strong><p>主来源可采用政府统计，也可增加研究机构、专业机构、经纪平台和新闻证据。</p></div></div>
          <div className="property-monitor-form-grid compact">
            <label><span>快照日期</span><input type="date" value={marketDraft.snapshot_date} onChange={(event) => setMarketDraft((item) => ({ ...item, snapshot_date: event.target.value }))} /></label>
            <label><span>二手房环比</span><input type="number" step={0.001} value={marketDraft.resale_price_mom ?? ""} onChange={(event) => setMarketDraft((item) => ({ ...item, resale_price_mom: optionalNumber(event.target.value) }))} /></label>
            <label><span>二手房同比</span><input type="number" step={0.001} value={marketDraft.resale_price_yoy ?? ""} onChange={(event) => setMarketDraft((item) => ({ ...item, resale_price_yoy: optionalNumber(event.target.value) }))} /></label>
            <label><span>新房环比</span><input type="number" step={0.001} value={marketDraft.new_home_price_mom ?? ""} onChange={(event) => setMarketDraft((item) => ({ ...item, new_home_price_mom: optionalNumber(event.target.value) }))} /></label>
            <label><span>新房同比</span><input type="number" step={0.001} value={marketDraft.new_home_price_yoy ?? ""} onChange={(event) => setMarketDraft((item) => ({ ...item, new_home_price_yoy: optionalNumber(event.target.value) }))} /></label>
            <label><span>长期名义锚</span><input type="number" min={-0.05} max={0.08} step={0.001} value={marketDraft.long_term_anchor_growth_rate} onChange={(event) => setMarketDraft((item) => ({ ...item, long_term_anchor_growth_rate: Number(event.target.value) }))} /></label>
            <label><span>数据质量</span><input type="number" min={0} max={1} step={0.05} value={marketDraft.housing_data_quality_score} onChange={(event) => setMarketDraft((item) => ({ ...item, housing_data_quality_score: Number(event.target.value) }))} /></label>
            <label><span>主来源类型</span><select value={marketDraft.source_type} onChange={(event) => setMarketDraft((item) => ({ ...item, source_type: event.target.value as MarketSnapshotData["source_type"] }))}><option value="government">政府统计</option><option value="research">研究机构</option><option value="agency">专业机构</option><option value="brokerage">经纪/平台</option><option value="media">媒体新闻</option><option value="other">其它来源</option></select></label>
            <label><span>来源名称</span><input value={marketDraft.source_name} onChange={(event) => setMarketDraft((item) => ({ ...item, source_name: event.target.value }))} /></label>
            <label className="wide"><span>来源链接</span><input value={marketDraft.source_url} onChange={(event) => setMarketDraft((item) => ({ ...item, source_url: event.target.value }))} /></label>
          </div>
          <div className="property-evidence-head"><div><strong>补充市场证据</strong><p>区级/小区级证据会优先用于匹配地段；媒体新闻默认权重较低。</p></div><button className="ghost-button small" type="button" onClick={addEvidence}><Plus size={15} />添加来源</button></div>
          <div className="property-evidence-list">
            {marketDraft.housing_market_evidence.map((evidence, index) => (
              <div className="property-evidence-card" key={`${evidence.source_name}-${index}`}>
                <div className="property-evidence-card-head"><strong>来源 {index + 1}</strong><button className="icon-button danger" type="button" aria-label={`删除来源 ${index + 1}`} onClick={() => removeEvidence(index)}><Trash2 size={15} /></button></div>
                <div className="property-monitor-form-grid compact">
                  <label><span>来源类型</span><select value={evidence.source_type} onChange={(event) => updateEvidence(index, { source_type: event.target.value as HousingMarketEvidenceData["source_type"] })}><option value="government">政府统计</option><option value="research">研究机构</option><option value="agency">专业机构</option><option value="brokerage">经纪/平台</option><option value="media">媒体新闻</option><option value="other">其它来源</option></select></label>
                  <label><span>来源名称</span><input value={evidence.source_name} onChange={(event) => updateEvidence(index, { source_name: event.target.value })} /></label>
                  <label><span>发布日期</span><input type="date" value={evidence.published_date} onChange={(event) => updateEvidence(index, { published_date: event.target.value })} /></label>
                  <label><span>覆盖层级</span><select value={evidence.scope_type} onChange={(event) => updateEvidence(index, { scope_type: event.target.value as HousingMarketEvidenceData["scope_type"] })}><option value="city">全市</option><option value="district">区/片区</option><option value="community">小区</option></select></label>
                  <label><span>覆盖区域</span><input value={evidence.scope_name} onChange={(event) => updateEvidence(index, { scope_name: event.target.value })} placeholder="例如朝阳、望京或具体小区" /></label>
                  <label><span>覆盖环线</span><select value={evidence.ring_scope} onChange={(event) => updateEvidence(index, { ring_scope: event.target.value as HousingMarketEvidenceData["ring_scope"] })}><option value="all">不限环线</option><option value="二环内">二环内</option><option value="二至三环">二至三环</option><option value="三至四环">三至四环</option><option value="四至五环">四至五环</option><option value="五至六环">五至六环</option><option value="六环外">六环外</option></select></label>
                  <label><span>房屋市场</span><select value={evidence.property_segment} onChange={(event) => updateEvidence(index, { property_segment: event.target.value as HousingMarketEvidenceData["property_segment"] })}><option value="all">全部住宅</option><option value="resale">二手房</option><option value="new_home">新房</option></select></label>
                  <label><span>价格环比</span><input type="number" step={0.001} value={evidence.price_mom ?? ""} onChange={(event) => updateEvidence(index, { price_mom: optionalNumber(event.target.value) })} /></label>
                  <label><span>价格同比</span><input type="number" step={0.001} value={evidence.price_yoy ?? ""} onChange={(event) => updateEvidence(index, { price_yoy: optionalNumber(event.target.value) })} /></label>
                  <label><span>区域成交单价</span><input type="number" min={0} step={100} value={evidence.avg_unit_price ?? ""} onChange={(event) => updateEvidence(index, { avg_unit_price: optionalNumber(event.target.value) })} /></label>
                  <label><span>样本量</span><input type="number" min={0} step={1} value={evidence.sample_size ?? ""} onChange={(event) => updateEvidence(index, { sample_size: optionalNumber(event.target.value) })} /></label>
                  <label><span>可信度</span><input type="number" min={0} max={1} step={0.05} value={evidence.credibility_score} onChange={(event) => updateEvidence(index, { credibility_score: Number(event.target.value) })} /></label>
                  <label className="wide"><span>来源链接</span><input value={evidence.source_url} onChange={(event) => updateEvidence(index, { source_url: event.target.value })} /></label>
                </div>
                <button className="ghost-button small property-source-preview-button" type="button" disabled={!evidence.source_url.trim() || previewingUrl === evidence.source_url.trim()} onClick={() => void previewEvidenceSource(evidence)}><Database size={14} />{previewingUrl === evidence.source_url.trim() ? "正在读取" : "读取并留存来源摘要"}</button>
                {sourcePreviews[evidence.source_url.trim()] ? <div className="property-source-preview"><strong>{sourcePreviews[evidence.source_url.trim()].name}</strong><p>{sourcePreviews[evidence.source_url.trim()].summary || "来源可访问，但没有提取到正文摘要。"}</p><span>状态：待人工复核 · 抓取时间 {sourcePreviews[evidence.source_url.trim()].fetched_at}</span></div> : null}
              </div>
            ))}
            {!marketDraft.housing_market_evidence.length ? <div className="property-evidence-empty">暂无补充来源。仅使用主来源时置信区间会更宽。</div> : null}
          </div>
          <button className="ghost-button property-market-save" type="button" onClick={() => void saveMarketSnapshot()}><Save size={16} />保存为最新快照</button>
        </div>
      </section>

      <section className="property-monitor-analysis-grid">
        <div className="property-monitor-panel property-monitor-chart-panel">
          <div className="property-monitor-panel-title"><TrendingUp size={18} /><div><strong>估值区间与长期路径</strong><p>中线是模型估值，上下线体现数据与个体房源不确定性。</p></div></div>
          {latestValuation ? (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={latestValuation.data.projection} margin={{ top: 12, right: 18, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(value) => `${(Number(value) / 10000).toFixed(0)}万`} width={58} />
                <Tooltip formatter={(value) => money(Number(value))} />
                <Line type="monotone" dataKey="upper_value" name="区间上限" stroke="#d39b2a" strokeDasharray="6 4" dot={false} />
                <Line type="monotone" dataKey="estimated_value" name="估值中线" stroke="#3b6ca8" strokeWidth={3} />
                <Line type="monotone" dataKey="lower_value" name="区间下限" stroke="#d06b52" strokeDasharray="6 4" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div className="empty-state">点击“立即更新估值”生成第一条趋势。</div>}
        </div>

        <div className="property-monitor-panel">
          <div className="property-monitor-panel-title"><ShieldCheck size={18} /><div><strong>模型解释</strong><p>明确哪些因素推动或压低估值。</p></div></div>
          {latestValuation ? (
            <>
              <div className="property-rate-grid">
                <span>大盘信号<strong>{percent(latestValuation.data.market_signal_rate)}</strong></span>
                <span>近端年化<strong>{percent(latestValuation.data.near_term_annual_rate)}</strong></span>
                <span>长期年化<strong>{percent(latestValuation.data.long_term_annual_rate)}</strong></span>
                <span>地段修正<strong>{percent(latestValuation.data.location_rate_adjustment)}</strong></span>
                <span>房龄修正<strong>{percent(latestValuation.data.building_age_rate_adjustment)}</strong></span>
                <span>流动性折价<strong>{percent(latestValuation.data.liquidity_discount_rate)}</strong></span>
              </div>
              <p className="property-source-summary">采用 {latestValuation.data.market_source_count} 个市场来源{latestValuation.data.matched_location_name ? `，命中地段：${latestValuation.data.matched_location_name}` : "，尚未命中区级/小区级样本"}{latestValuation.data.matched_ring_area ? ` · ${latestValuation.data.matched_ring_area}` : ""}{latestValuation.data.location_reference_unit_price > 0 ? `；区域参考单价 ${money(latestValuation.data.location_reference_unit_price)}/㎡` : ""}。</p>
              <ul className="property-driver-list">{latestValuation.data.drivers.map((item) => <li key={item}>{item}</li>)}</ul>
              <div className="property-warning-list">{latestValuation.data.warnings.map((item) => <p key={item}><AlertTriangle size={14} />{item}</p>)}</div>
            </>
          ) : <div className="empty-state">暂无模型解释。</div>}
        </div>
      </section>

      <section className="property-monitor-panel">
        <div className="property-monitor-panel-title"><Database size={18} /><div><strong>估值历史</strong><p>{loading ? "正在同步历史记录" : `${selectedHistory.length} 条记录`}</p></div></div>
        <div className="property-history-table">
          <div className="property-history-row head"><span>估值日</span><span>市场价值</span><span>净变现</span><span>区间</span><span>置信度</span><span>行情来源</span></div>
          {selectedHistory.map((item) => <div className="property-history-row" key={item.id}><span>{item.valuation_date}</span><span>{money(item.data.estimated_market_value)}</span><span>{money(item.data.net_realisable_value)}</span><span>{money(item.data.lower_value)} - {money(item.data.upper_value)}</span><span>{percent(item.data.confidence_score)}</span><span>{item.data.market_source_name}</span></div>)}
        </div>
      </section>
    </div>
  );
}
