from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from typing import Callable, Protocol

from .schemas import PaperOrderData, PaperPositionData


@dataclass(frozen=True)
class BrokerReconciliationResult:
    matched: bool
    freeze_new_orders: bool
    differences: list[str]
    local_state_hash: str
    remote_state_hash: str


def _order_state(order: PaperOrderData) -> dict[str, object]:
    return {
        "client_order_id": order.client_order_id,
        "instrument_id": order.instrument_id,
        "side": order.side,
        "status": order.status,
        "order_amount": round(float(order.order_amount), 2),
        "executed_date": order.executed_date,
        "executed_price": round(float(order.executed_price), 6) if order.executed_price is not None else None,
        "executed_quantity": round(float(order.executed_quantity), 6) if order.executed_quantity is not None else None,
    }


def _position_state(position: PaperPositionData) -> dict[str, object]:
    return {
        "instrument_id": position.instrument_id,
        "quantity": round(float(position.quantity), 6),
    }


def broker_state_hash(
    *,
    orders: list[PaperOrderData],
    positions: list[PaperPositionData],
    cash: float,
) -> str:
    payload = {
        "orders": sorted((_order_state(order) for order in orders), key=lambda item: str(item["client_order_id"])),
        "positions": sorted((_position_state(position) for position in positions), key=lambda item: str(item["instrument_id"])),
        "cash": round(float(max(0.0, cash)), 2),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def reconcile_broker_state(
    *,
    local_orders: list[PaperOrderData],
    local_positions: list[PaperPositionData],
    local_cash: float,
    remote_orders: list[PaperOrderData],
    remote_positions: list[PaperPositionData],
    remote_cash: float,
) -> BrokerReconciliationResult:
    differences: list[str] = []
    local_order_map = {order.client_order_id: order for order in local_orders}
    remote_order_map = {order.client_order_id: order for order in remote_orders}
    if len(local_order_map) != len(local_orders):
        differences.append("本地订单存在重复 client_order_id")
    if len(remote_order_map) != len(remote_orders):
        differences.append("适配器订单查询结果存在重复 client_order_id")
    for client_order_id in sorted(local_order_map.keys() - remote_order_map.keys()):
        differences.append(f"本地订单 {client_order_id} 未出现在适配器订单查询结果中")
    for client_order_id in sorted(remote_order_map.keys() - local_order_map.keys()):
        differences.append(f"适配器返回未在本地落账的订单 {client_order_id}")
    for client_order_id in sorted(local_order_map.keys() & remote_order_map.keys()):
        if _order_state(local_order_map[client_order_id]) != _order_state(remote_order_map[client_order_id]):
            differences.append(f"订单 {client_order_id} 的状态或成交字段与本地记录不一致")

    local_position_map = {position.instrument_id: position for position in local_positions}
    remote_position_map = {position.instrument_id: position for position in remote_positions}
    if len(local_position_map) != len(local_positions):
        differences.append("本地持仓存在重复标的记录")
    if len(remote_position_map) != len(remote_positions):
        differences.append("适配器持仓查询结果存在重复标的记录")
    for instrument_id in sorted(local_position_map.keys() | remote_position_map.keys()):
        local_position = local_position_map.get(instrument_id)
        remote_position = remote_position_map.get(instrument_id)
        if local_position is None:
            differences.append(f"适配器返回本地不存在的持仓 {instrument_id}")
        elif remote_position is None:
            differences.append(f"本地持仓 {instrument_id} 未出现在适配器持仓查询结果中")
        elif abs(local_position.quantity - remote_position.quantity) > 1e-6:
            differences.append(f"持仓 {instrument_id} 的数量与本地账本不一致")
    if abs(local_cash - remote_cash) > 0.01:
        differences.append("适配器现金余额与本地模拟现金不一致")

    local_hash = broker_state_hash(orders=local_orders, positions=local_positions, cash=local_cash)
    remote_hash = broker_state_hash(orders=remote_orders, positions=remote_positions, cash=remote_cash)
    matched = not differences and local_hash == remote_hash
    return BrokerReconciliationResult(
        matched=matched,
        freeze_new_orders=not matched,
        differences=differences,
        local_state_hash=local_hash,
        remote_state_hash=remote_hash,
    )


class BrokerAdapter(Protocol):
    """Stable broker boundary shared by paper and future QMT adapters."""

    def submit(self, order: PaperOrderData) -> PaperOrderData: ...

    def cancel(self, client_order_id: str) -> bool: ...

    def query_orders(self) -> list[PaperOrderData]: ...

    def query_positions(self) -> list[PaperPositionData]: ...

    def query_cash(self) -> float: ...

    def reconcile(
        self,
        *,
        local_orders: list[PaperOrderData],
        local_positions: list[PaperPositionData],
        local_cash: float,
    ) -> BrokerReconciliationResult: ...


@dataclass(frozen=True)
class PaperBrokerAdapter:
    """The only executable adapter; it never sends an order externally."""

    orders: tuple[PaperOrderData, ...] = ()
    positions: tuple[PaperPositionData, ...] = ()
    cash_balance: float = 0.0

    def simulate(self, order: PaperOrderData, *, executed_date: str = "", executed_price: float | None = None) -> PaperOrderData:
        trade_date = executed_date or order.expected_trade_date or date.today().isoformat()
        try:
            parsed_trade_date = date.fromisoformat(trade_date)
            expected_trade_date = date.fromisoformat(order.expected_trade_date) if order.expected_trade_date else None
        except ValueError:
            raise ValueError("模拟成交日期必须是有效的 YYYY-MM-DD 日期") from None
        if expected_trade_date is not None and parsed_trade_date < expected_trade_date:
            raise ValueError("模拟成交日期不能早于订单计划成交日")
        if parsed_trade_date > date.today():
            raise ValueError("模拟成交日期不能晚于当前日期")
        price = executed_price if executed_price is not None else order.estimated_price
        if price <= 0:
            raise ValueError("模拟成交价格必须大于 0")
        quantity = (
            max(0.0, (order.order_amount - order.estimated_fee) / price)
            if order.side == "buy"
            else order.estimated_quantity
        )
        if order.lot_size > 1:
            quantity = int(quantity // order.lot_size) * order.lot_size
        if quantity <= 0:
            raise ValueError("模拟订单金额不足以满足最小交易单位")
        planned_gross = order.estimated_price * order.estimated_quantity
        fee_rate = order.estimated_fee / planned_gross if planned_gross > 0 else 0.0
        executed_fee = price * quantity * fee_rate
        return order.model_copy(
            update={
                "status": "simulated",
                "executed_date": trade_date,
                "executed_price": round(price, 6),
                "executed_quantity": round(quantity, 6),
                "estimated_fee": round(executed_fee, 2),
            }
        )

    def submit(self, order: PaperOrderData) -> PaperOrderData:
        return self.simulate(order)

    def cancel(self, client_order_id: str) -> bool:
        return any(
            order.client_order_id == client_order_id and order.status in {"proposed", "cancel_requested"}
            for order in self.orders
        )

    def query_orders(self) -> list[PaperOrderData]:
        return list(self.orders)

    def query_positions(self) -> list[PaperPositionData]:
        return list(self.positions)

    def query_cash(self) -> float:
        return max(0.0, self.cash_balance)

    def reconcile(
        self,
        *,
        local_orders: list[PaperOrderData],
        local_positions: list[PaperPositionData],
        local_cash: float,
    ) -> BrokerReconciliationResult:
        return reconcile_broker_state(
            local_orders=local_orders,
            local_positions=local_positions,
            local_cash=local_cash,
            remote_orders=self.query_orders(),
            remote_positions=self.query_positions(),
            remote_cash=self.query_cash(),
        )


@dataclass(frozen=True)
class LocalFirstBrokerGateway:
    """Reject submission unless a local immutable order id already exists."""

    adapter: BrokerAdapter
    is_order_persisted: Callable[[str, str], bool] | None = None
    is_order_action_allowed: Callable[[str, str, str], bool] | None = None

    def _require_persisted(
        self,
        local_order_id: str,
        client_order_id: str,
        *,
        action: str,
    ) -> None:
        if not local_order_id:
            raise RuntimeError("订单必须先在本地账本落库，之后才允许调用券商适配器")
        if not client_order_id:
            raise RuntimeError("订单缺少唯一 client_order_id")
        if self.is_order_persisted is None:
            raise RuntimeError("未提供本地订单持久化校验器，禁止调用券商适配器")
        if not self.is_order_persisted(local_order_id, client_order_id):
            raise RuntimeError("本地订单 ID 与 client_order_id 无法在持久化账本中匹配")
        if self.is_order_action_allowed is None:
            raise RuntimeError("未提供本地订单动作状态校验器，禁止调用券商适配器")
        if not self.is_order_action_allowed(local_order_id, client_order_id, action):
            raise RuntimeError(f"本地订单当前状态不允许执行 {action} 动作")

    def submit(self, *, local_order_id: str, order: PaperOrderData) -> PaperOrderData:
        self._require_persisted(local_order_id, order.client_order_id, action="submit")
        return self.adapter.submit(order)

    def cancel(self, *, local_order_id: str, client_order_id: str) -> bool:
        self._require_persisted(local_order_id, client_order_id, action="cancel")
        return self.adapter.cancel(client_order_id)

    def reconcile(
        self,
        *,
        local_orders: list[PaperOrderData],
        local_positions: list[PaperPositionData],
        local_cash: float,
    ) -> BrokerReconciliationResult:
        return self.adapter.reconcile(
            local_orders=local_orders,
            local_positions=local_positions,
            local_cash=local_cash,
        )


class QmtBrokerAdapter:
    """Disabled until written broker confirmation and read-only reconciliation phase."""

    @staticmethod
    def _disabled() -> RuntimeError:
        return RuntimeError("QMT/XtQuant 尚未启用；需先完成券商权限确认、只读对账和人工二次确认。")

    def submit(self, order: PaperOrderData) -> PaperOrderData:
        raise self._disabled()

    def cancel(self, client_order_id: str) -> bool:
        raise self._disabled()

    def query_orders(self) -> list[PaperOrderData]:
        raise self._disabled()

    def query_positions(self) -> list[PaperPositionData]:
        raise self._disabled()

    def query_cash(self) -> float:
        raise self._disabled()

    def reconcile(
        self,
        *,
        local_orders: list[PaperOrderData],
        local_positions: list[PaperPositionData],
        local_cash: float,
    ) -> BrokerReconciliationResult:
        raise self._disabled()

    def simulate(self, order: PaperOrderData, *, executed_date: str = "", executed_price: float | None = None) -> PaperOrderData:
        raise self._disabled()
