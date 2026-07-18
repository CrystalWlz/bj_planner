from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .schemas import PaperOrderData


class BrokerAdapter(Protocol):
    """Broker boundary.  Live brokers must be explicitly enabled in a later phase."""

    def simulate(self, order: PaperOrderData, *, executed_date: str = "", executed_price: float | None = None) -> PaperOrderData: ...


@dataclass(frozen=True)
class PaperBrokerAdapter:
    """The only executable adapter in phase one; it never sends an order externally."""

    def simulate(self, order: PaperOrderData, *, executed_date: str = "", executed_price: float | None = None) -> PaperOrderData:
        price = executed_price if executed_price is not None else order.estimated_price
        if price <= 0:
            raise ValueError("模拟成交价格必须大于 0")
        quantity = max(0.0, (order.order_amount - order.estimated_fee) / price)
        return order.model_copy(
            update={
                "status": "simulated",
                "executed_date": executed_date or date.today().isoformat(),
                "executed_price": round(price, 6),
                "executed_quantity": round(quantity, 6),
            }
        )


class QmtBrokerAdapter:
    """Deliberately non-operational placeholder.

    A future implementation must require a broker-confirmed local MiniQMT
    connection, explicit order limits and a user confirmation step.  It may not
    read credentials from household records or call a remote broker by default.
    """

    def simulate(self, order: PaperOrderData, *, executed_date: str = "", executed_price: float | None = None) -> PaperOrderData:
        raise RuntimeError("QMT 实盘接口尚未启用；一期仅支持模拟成交和人工订单清单。")
