import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, PlayCircle, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import {
  createQuantInvestmentInstrument,
  createQuantInvestmentPolicy,
  createQuantInvestmentProposal,
  createQuantMarketSnapshot,
  fetchQuantInvestmentInstruments,
  fetchQuantInvestmentPolicies,
  fetchQuantInvestmentProposals,
  fetchQuantMarketSnapshots,
  fetchQuantPaperOrders,
  refreshQuantMarketData,
  runQuantInvestmentBacktest,
  saveQuantInvestmentPolicy,
  simulateQuantPaperOrder,
} from "./api";
import { money, numberInput, percent } from "./format";
import type {
  InvestmentInstrumentData,
  InvestmentInstrumentRecord,
  InvestmentMarketSnapshotData,
  InvestmentMarketSnapshotRecord,
  PaperOrderRecord,
  QuantBacktestResult,
  QuantInvestmentPolicyData,
  QuantInvestmentPolicyRecord,
  QuantInvestmentProposalRecord,
} from "./types";

const defaultPolicy = (): QuantInvestmentPolicyData => ({
  schema_version: 1,
  name: "港股通 / QDII ETF 月度定投",
  enabled: true,
  frequency: "monthly",
  equity_cap: 0.35,
  defensive_min: 0.65,
  rebalance_threshold: 0.05,
  drawdown_reduce_threshold: 0.08,
  drawdown_pause_threshold: 0.12,
  drawdown_freeze_threshold: 0.15,
  drawdown_reduced_equity_cap: 0.2,
  qdii_premium_threshold: 0.03,
  qdii_nav_max_stale_days: 3,
  default_monthly_budget: 0,
  slippage_rate: 0.001,
  notes: "一期仅生成模拟订单和人工确认清单，不接入真实券商下单。"
});

const defaultInstrument = (): InvestmentInstrumentData => ({
  schema_version: 1,
  symbol: "",
  name: "",
  market: "mainland_etf",
  trading_mode: "exchange",
  asset_class: "equity",
  currency: "CNY",
  enabled: true,
  hong_kong_connect_eligible: false,
  purchase_suspended: false,
  monthly_purchase_limit: null,
  buy_fee_rate: 0.0015,
  sell_fee_rate: 0.005,
  qdii_premium_threshold: null,
  notes: ""
});

function userFacingError(error: unknown) {
  const message = error instanceof Error ? error.message : "未知错误";
  if (message.includes("TUSHARE_TOKEN")) return "尚未配置 Tushare Pro 令牌。请在本机私有 tushare.env 填写，或设置环境变量；令牌不要填入本页面。";
  return `量化定投操作未完成：${message.replace(/^\{"detail":"?|"?\}$/g, "")}`;
}

export function QuantInvestmentPanel({ householdId }: { householdId: string }) {
  const [policies, setPolicies] = useState<QuantInvestmentPolicyRecord[]>([]);
  const [instruments, setInstruments] = useState<InvestmentInstrumentRecord[]>([]);
  const [snapshots, setSnapshots] = useState<InvestmentMarketSnapshotRecord[]>([]);
  const [proposals, setProposals] = useState<QuantInvestmentProposalRecord[]>([]);
  const [orders, setOrders] = useState<PaperOrderRecord[]>([]);
  const [backtest, setBacktest] = useState<QuantBacktestResult | null>(null);
  const [instrumentDraft, setInstrumentDraft] = useState<InvestmentInstrumentData>(defaultInstrument);
  const [manualPrice, setManualPrice] = useState(1);
  const [manualNav, setManualNav] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [nextPolicies, nextInstruments, nextSnapshots, nextProposals, nextOrders] = await Promise.all([
      fetchQuantInvestmentPolicies(householdId),
      fetchQuantInvestmentInstruments(householdId),
      fetchQuantMarketSnapshots(householdId),
      fetchQuantInvestmentProposals(householdId),
      fetchQuantPaperOrders(householdId),
    ]);
    setPolicies(nextPolicies);
    setInstruments(nextInstruments);
    setSnapshots(nextSnapshots);
    setProposals(nextProposals);
    setOrders(nextOrders);
  }, [householdId]);

  useEffect(() => {
    void refresh().catch((nextError) => setError(userFacingError(nextError)));
  }, [refresh]);

  const activePolicy = policies[0] ?? null;
  const latestProposal = proposals[0] ?? null;
  const instrumentById = useMemo(() => new Map(instruments.map((item) => [item.id, item])), [instruments]);
  const snapshotByInstrumentId = useMemo(() => new Map(snapshots.map((item) => [item.instrument_id, item])), [snapshots]);

  const runAction = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (nextError) {
      setError(userFacingError(nextError));
    } finally {
      setBusy(false);
    }
  };

  const addPolicy = () => runAction(async () => { await createQuantInvestmentPolicy(householdId, defaultPolicy()); });
  const savePolicy = () => activePolicy && runAction(async () => { await saveQuantInvestmentPolicy(activePolicy.id, householdId, activePolicy.data); });
  const addInstrument = () => runAction(async () => {
    if (!instrumentDraft.symbol.trim() || !instrumentDraft.name.trim()) {
      throw new Error("请填写标的代码和名称。系统不会自动推荐具体基金。 ");
    }
    await createQuantInvestmentInstrument(householdId, instrumentDraft);
    setInstrumentDraft(defaultInstrument());
  });
  const refreshMarketData = () => runAction(async () => { await refreshQuantMarketData(householdId); });
  const generateProposal = () => activePolicy && runAction(async () => { await createQuantInvestmentProposal(householdId, activePolicy.id); });
  const runBacktest = () => activePolicy && runAction(async () => {
    const result = await runQuantInvestmentBacktest(householdId, activePolicy.id, Math.max(1, activePolicy.data.default_monthly_budget || 1000));
    setBacktest(result);
  });
  const simulateOrder = (id: string) => runAction(async () => { await simulateQuantPaperOrder(id, householdId); });
  const writeManualSnapshot = (instrument: InvestmentInstrumentRecord) => runAction(async () => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const nav = instrument.data.market === "qdii_etf" ? manualNav : null;
    const data: InvestmentMarketSnapshotData = {
      schema_version: 1,
      source: "manual",
      snapshot_date: today.toISOString().slice(0, 10),
      status: "partial",
      bars: [
        { date: yesterday.toISOString().slice(0, 10), close: manualPrice, adjusted_close: manualPrice, nav, nav_date: nav ? yesterday.toISOString().slice(0, 10) : "", premium_rate: null, is_trading: true },
        { date: today.toISOString().slice(0, 10), close: manualPrice, adjusted_close: manualPrice, nav, nav_date: nav ? today.toISOString().slice(0, 10) : "", premium_rate: null, is_trading: true },
      ],
      warning: "手工快照仅用于验证模拟流程，不应用于三年回测。"
    };
    await createQuantMarketSnapshot(householdId, instrument.id, data);
  });

  return (
    <section className="form-panel quant-investment-panel">
      <div className="section-header">
        <div><Database size={18} /><h2>量化定投模拟盘</h2></div>
        <button className="ghost-button" type="button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={16} /> 刷新状态</button>
      </div>
      <p className="field-hint">后端按现金安全垫、近期重大目标、35% 权益上限和回撤阈值生成提案。这里不会保存券商或 Tushare 凭据，也不会提交真实订单。</p>
      {error ? <p className="error-text">{error}</p> : null}

      {!activePolicy ? (
        <button className="primary-button" type="button" onClick={() => void addPolicy()} disabled={busy}><Plus size={16} /> 创建默认月度策略</button>
      ) : (
        <>
          <div className="metric-grid">
            <Metric label="权益上限" value={percent(activePolicy.data.equity_cap)} />
            <Metric label="暂停阈值" value={percent(activePolicy.data.drawdown_pause_threshold)} tone="warn" />
            <Metric label="冻结阈值" value={percent(activePolicy.data.drawdown_freeze_threshold)} tone="bad" />
            <Metric label="当前行情快照" value={`${snapshots.length} 个`} />
          </div>
          <div className="form-grid four">
            <label className="field"><span>权益上限</span><input type="number" min="0" max="1" step="0.01" value={numberInput(activePolicy.data.equity_cap)} onChange={(event) => setPolicies((items) => items.map((item, index) => index ? item : { ...item, data: { ...item.data, equity_cap: Number(event.target.value) } }))} /></label>
            <label className="field"><span>月度预算</span><input type="number" min="0" step="100" value={numberInput(activePolicy.data.default_monthly_budget)} onChange={(event) => setPolicies((items) => items.map((item, index) => index ? item : { ...item, data: { ...item.data, default_monthly_budget: Number(event.target.value) } }))} /></label>
            <label className="field"><span>降仓回撤</span><input type="number" min="0" max="1" step="0.01" value={numberInput(activePolicy.data.drawdown_reduce_threshold)} onChange={(event) => setPolicies((items) => items.map((item, index) => index ? item : { ...item, data: { ...item.data, drawdown_reduce_threshold: Number(event.target.value) } }))} /></label>
            <label className="field"><span>暂停回撤</span><input type="number" min="0" max="1" step="0.01" value={numberInput(activePolicy.data.drawdown_pause_threshold)} onChange={(event) => setPolicies((items) => items.map((item, index) => index ? item : { ...item, data: { ...item.data, drawdown_pause_threshold: Number(event.target.value) } }))} /></label>
          </div>
          <div className="inline-actions"><button className="secondary-button" type="button" onClick={() => void savePolicy()} disabled={busy}>保存风险政策</button><button className="secondary-button" type="button" onClick={() => void refreshMarketData()} disabled={busy}>用 Tushare 刷新日线</button><button className="primary-button" type="button" onClick={() => void generateProposal()} disabled={busy}><ShieldCheck size={16} /> 生成本月模拟提案</button><button className="ghost-button" type="button" onClick={() => void runBacktest()} disabled={busy}><PlayCircle size={16} /> 运行三年回测</button></div>
        </>
      )}

      <div className="setting-group">
        <strong className="setting-group-title">手工标的池</strong>
        <p className="field-hint">仅加入你已核实可买的标的。港股通标的必须手动确认合资格；场外 QDII 不会生成交易所模拟订单。</p>
        <div className="form-grid four">
          <label className="field"><span>代码</span><input value={instrumentDraft.symbol} onChange={(event) => setInstrumentDraft((item) => ({ ...item, symbol: event.target.value }))} placeholder="例如 510300.SH" /></label>
          <label className="field"><span>名称</span><input value={instrumentDraft.name} onChange={(event) => setInstrumentDraft((item) => ({ ...item, name: event.target.value }))} placeholder="自定义名称" /></label>
          <label className="field"><span>市场</span><select value={instrumentDraft.market} onChange={(event) => setInstrumentDraft((item) => ({ ...item, market: event.target.value as InvestmentInstrumentData["market"], trading_mode: event.target.value === "qdii_fund" ? "fund_subscription" : "exchange" }))}><option value="mainland_etf">境内 ETF</option><option value="hong_kong_connect">港股通</option><option value="qdii_etf">场内跨境 QDII ETF</option><option value="qdii_fund">场外 QDII 基金</option></select></label>
          <button className="secondary-button" type="button" onClick={() => void addInstrument()} disabled={busy}><Plus size={16} /> 加入标的池</button>
        </div>
        <div className="strategy-grid horizontal-card-list">{instruments.map((instrument) => {
          const snapshot = snapshotByInstrumentId.get(instrument.id);
          return <article className="strategy-card" key={instrument.id}><strong>{instrument.data.name}</strong><span>{instrument.data.symbol} · {instrument.data.market}</span><p>{snapshot ? `快照 ${snapshot.data.snapshot_date} · ${snapshot.data.bars.length} 条日线` : "尚无行情快照"}</p><div className="inline-actions"><label className="field compact-field"><span>测试价</span><input type="number" min="0.0001" step="0.01" value={numberInput(manualPrice)} onChange={(event) => setManualPrice(Number(event.target.value))} /></label>{instrument.data.market === "qdii_etf" ? <label className="field compact-field"><span>测试净值</span><input type="number" min="0.0001" step="0.01" value={numberInput(manualNav)} onChange={(event) => setManualNav(Number(event.target.value))} /></label> : null}<button className="ghost-button" type="button" onClick={() => void writeManualSnapshot(instrument)} disabled={busy}>录入测试快照</button></div></article>;
        })}</div>
      </div>

      {latestProposal ? <div className="setting-group"><strong className="setting-group-title">最近模拟提案 · {latestProposal.data.risk_state}</strong><div className="metric-grid"><Metric label="受保护现金" value={money(latestProposal.data.protected_cash)} /><Metric label="可投资现金" value={money(latestProposal.data.investable_cash)} /><Metric label="提案金额" value={money(latestProposal.data.proposed_budget)} /><Metric label="风险篮子回撤" value={percent(latestProposal.data.estimated_drawdown)} tone={latestProposal.data.risk_state === "normal" ? "good" : "warn"} /></div><div className="warning-list">{latestProposal.data.reasons.map((reason) => <span key={reason}>{reason}</span>)}</div></div> : null}

      {orders.length ? <div className="setting-group"><strong className="setting-group-title">模拟订单</strong>{orders.map((order) => <div className="strategy-card" key={order.id}><strong>{instrumentById.get(order.data.instrument_id)?.data.name ?? "未知标的"} · {order.data.status === "simulated" ? "已模拟成交" : "待模拟"}</strong><p>{money(order.data.order_amount)}，预计价格 {order.data.estimated_price}，费用 {money(order.data.estimated_fee)}。{order.data.reason}</p>{order.data.status === "proposed" ? <button className="secondary-button" type="button" onClick={() => void simulateOrder(order.id)} disabled={busy}>按估算价模拟成交</button> : <span className="status-badge success">成交价 {order.data.executed_price}</span>}</div>)}</div> : null}

      {backtest ? <div className="setting-group"><strong className="setting-group-title">三年历史回测</strong><div className="metric-grid"><Metric label="策略终值" value={money(backtest.strategy_terminal_value)} /><Metric label="静态配置终值" value={money(backtest.static_terminal_value)} /><Metric label="策略最大回撤" value={percent(backtest.strategy_max_drawdown)} /><Metric label="静态最大回撤" value={percent(backtest.static_max_drawdown)} /></div><p className="field-hint">{backtest.warnings.join(" ")}</p></div> : null}
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "bad" }) {
  return <div className={`metric ${tone ? `metric-${tone}` : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}
