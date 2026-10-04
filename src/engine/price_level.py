import bisect
from decimal import Decimal
from typing import Iterator, Optional

from src.domain.models import Order


class PriceLevel:
    """
    Representa uma faixa (nível) de preço no Order Book.
    
    Responsabilidade:
    - Armazenar e organizar as ordens de um mesmo preço.
    - Garantir que as ordens fiquem rigorosamente ordenadas pelo seu contador
      de criação original (sequence: int), e não pela ordem cronológica de inserção no nível.
      Isso garante o comportamento correto de ordens pegged quando reajustadas.
    - Zero lógica de matching ou chamadas a print().
    """

    def __init__(self, price: Decimal) -> None:
        if price <= Decimal("0"):
            raise ValueError(f"O preço do nível deve ser maior que zero, recebido: {price}")
        self._price: Decimal = price
        self._orders: list[Order] = []
        self._orders_by_id: dict[int, Order] = {}

    @property
    def price(self) -> Decimal:
        """Preço deste nível de ofertas."""
        return self._price

    @property
    def total_qty(self) -> int:
        """
        Quantidade total acumulada de contratos/ações disponíveis neste nível.
        Calculada dinamicamente para garantir consistência mesmo após preenchimentos parciais.
        """
        return sum(order.qty for order in self._orders)

    @property
    def order_count(self) -> int:
        """Quantidade de ordens ativas presentes neste nível."""
        return len(self._orders)

    @property
    def is_empty(self) -> bool:
        """Indica se o nível não possui ordens ativas."""
        return len(self._orders) == 0

    def add_order(self, order: Order) -> None:
        """
        Adiciona uma ordem ao nível de preço.
        
        A ordem é inserida na posição exata baseada em seu `sequence` (contador global
        de criação), preservando a prioridade temporal FIFO mesmo que ela tenha sido
        reajustada (caso de uma Pegged Order) ou inserida fora da ordem natural.
        """
        if order.price != self._price:
            raise ValueError(
                f"Preço da ordem ({order.price}) diverge do preço do nível ({self._price})"
            )
        if order.id in self._orders_by_id:
            raise ValueError(f"Ordem com id {order.id} já existe neste nível de preço")

        # Inserção ordenada pelo sequence (O(log N) busca + O(N) shift na lista)
        insert_idx = bisect.bisect_right(
            self._orders,
            order.sequence,
            key=lambda o: o.sequence,
        )
        self._orders.insert(insert_idx, order)
        self._orders_by_id[order.id] = order

    def remove_order(self, order_id: int) -> Optional[Order]:
        """
        Remove uma ordem do nível pelo seu identificador único.
        
        Comportamento para ID inexistente:
        Retorna `None` em vez de levantar exceção.
        Justificativa: Em sistemas de negociação e books de ofertas,
        tentativas de cancelamento ou remoção de ordens que já foram totalmente executadas
        ou previamente canceladas devem ser tratadas de forma idempotente e segura, permitindo
        ao chamador (OrderBook/Engine) verificar se a ordem estava presente sem provocar
        quebra de fluxo de execução.
        """
        order = self._orders_by_id.pop(order_id, None)
        if order is None:
            return None

        self._orders.remove(order)
        return order

    def peek_first(self) -> Optional[Order]:
        """
        Retorna a primeira ordem da fila (maior prioridade temporal FIFO) sem removê-la.
        Retorna None se o nível estiver vazio.
        """
        if self.is_empty:
            return None
        return self._orders[0]

    def pop_first(self) -> Optional[Order]:
        """
        Remove e retorna a primeira ordem da fila (maior prioridade).
        Retorna None se o nível estiver vazio.
        """
        if self.is_empty:
            return None
        order = self._orders.pop(0)
        self._orders_by_id.pop(order.id, None)
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        """Busca uma ordem pelo id em O(1)."""
        return self._orders_by_id.get(order_id)

    def __iter__(self) -> Iterator[Order]:
        """Permite iterar sobre as ordens na ordem de prioridade (FIFO por sequence)."""
        return iter(self._orders)

    def __len__(self) -> int:
        """Retorna a quantidade de ordens ativas neste nível."""
        return self.order_count

    def __contains__(self, order_id: int) -> bool:
        """Verifica se uma ordem pertence a este nível pelo id em O(1)."""
        return order_id in self._orders_by_id

    def __repr__(self) -> str:
        return f"PriceLevel(price={self._price}, orders={len(self._orders)}, total_qty={self.total_qty})"