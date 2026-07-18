from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .schemas import PaperOrderData, PaperPositionData


@dataclass(frozen=True)
class BrokerReconciliationResult:
    matched: bool
    freeze_new_orders: bool
    differences: list[str]


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

    def simulate(self, order: PaperOrderData, *, executed_date: str = "", executed_price: float | None = None) -> PaperOrderData:
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
                "executed_date": executed_date or date.today().isoformat(),
                "executed_price": round(price, 6),
                "executed_quantity": round(quantity, 6),
                "estimated_fee": round(executed_fee, 2),
            }
        )

    def submit(self, order: PaperOrderData) -> PaperOrderData:
        return self.simulate(order)

    def cancel(self, client_order_id: str) -> bool:
        return bool(client_order_id)

    def query_orders(self) -> list[PaperOrderData]:
        return []

    def query_positions(self) -> list[PaperPositionData]:
        return []

    def query_cash(self) -> float:
        return 0.0

    def reconcile(
        self,
        *,
        local_orders: list[PaperOrderData],
        local_positions: list[PaperPositionData],
        local_cash: float,
    ) -> BrokerReconciliationResult:
        return BrokerReconciliationResult(matched=True, freeze_new_orders=False, differences=[])


@dataclass(frozen=True)
class LocalFirstBrokerGateway:
    """Reject submission unless a local immutable order id already exists."""

    adapter: BrokerAdapter

    def submit(self, *, local_order_id: str, order: PaperOrderData) -> PaperOrderData:
        if not local_order_id:
            raise RuntimeError("订单必须先在本地账本落库，之后才允许发送到券商适配器")
        if not order.client_order_id:
            raise RuntimeError("订单缺少唯一 client_order_id")
        return self.adapter.submit(order)


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
