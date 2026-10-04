from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """Lado da ordem no livro de ofertas."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Tipo da ordem suportado pela engine."""
    LIMIT = "limit"
    MARKET = "market"
    PEGGED = "pegged"


class PegReference(str, Enum):
    """Ponto de referência de preço para ordens pegged."""
    BID = "bid"
    OFFER = "offer"


class OrderStatus(str, Enum):
    """Ciclo de vida de uma ordem."""
    ACTIVE = "active"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """
    Representação de uma ordem no livro de ofertas.
    
    Regras de Negócio Atendidas:
    - Preço estritamente tipado como Decimal (evita erros de float binário).
    - Quantidade estritamente int > 0.
    - ID numérico inteiro sequencial (1, 2, 3...).
    - Prioridade temporal (FIFO) baseada em `sequence: int` (contador sequencial), não datetime.
    - Zero chamadas a print().
    """
    id: int
    side: Side
    order_type: OrderType
    qty: int
    initial_qty: int
    sequence: int
    price: Optional[Decimal] = None
    peg_ref: Optional[PegReference] = None
    status: OrderStatus = OrderStatus.ACTIVE

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError(f"Quantidade deve ser maior que 0, recebido: {self.qty}")
        if self.initial_qty <= 0:
            raise ValueError(f"Quantidade inicial deve ser maior que 0, recebido: {self.initial_qty}")
        if self.price is not None and self.price <= Decimal("0"):
            raise ValueError(f"Preço deve ser maior que 0, recebido: {self.price}")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Ordens a limite (LIMIT) exigem a definição de um preço.")
        if self.order_type == OrderType.PEGGED and self.peg_ref is None:
            raise ValueError("Ordens PEGGED exigem definição de referência peg_ref ('bid' ou 'offer').")

    @property
    def is_pegged(self) -> bool:
        return self.order_type == OrderType.PEGGED

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.ACTIVE, OrderStatus.PARTIALLY_FILLED)

    def fill(self, fill_qty: int) -> None:
        """Aplica uma execução parcial ou total na ordem."""
        if fill_qty <= 0:
            raise ValueError(f"Quantidade de preenchimento deve ser maior que 0, recebido: {fill_qty}")
        if fill_qty > self.qty:
            raise ValueError(f"Quantidade a preencher ({fill_qty}) excede o saldo remanescente ({self.qty})")

        self.qty -= fill_qty
        if self.qty == 0:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED


@dataclass(frozen=True)
class Trade:
    """
    Representação de uma execução (trade) gerada pela Matching Engine.
    
    Imutável, transporta as informações puras de negócio para serem
    consumidas e formatadas pela camada de apresentação (CLI).
    """
    price: Decimal
    qty: int
    maker_order_id: Optional[int] = None
    taker_order_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError(f"Quantidade do trade deve ser maior que 0, recebido: {self.qty}")
        if self.price <= Decimal("0"):
            raise ValueError(f"Preço do trade deve ser maior que 0, recebido: {self.price}")
