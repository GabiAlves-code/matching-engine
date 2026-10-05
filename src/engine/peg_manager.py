from decimal import Decimal
from typing import Optional

from src.domain.models import Order, Side
from src.engine.order_book import OrderBook


class PegManager:
    """
    Gerenciador de Ordens Pegged.

    Responsabilidades:
    - Calcular o preço de referência (melhor preço entre ordens não-pegged do lado).
    - Monitorar ordens pegged ativas.
    - Executar o repique dinâmico:
        * Descarta da monitoração ordens que não estão mais no livro.
        * Mantém o preço se não houver referência no livro.
        * Move para a nova referência mantendo estritamente o sequence original.
    """

    def __init__(self, book: OrderBook) -> None:
        self._book: OrderBook = book
        self._pegged_orders: dict[int, Order] = {}

    def get_reference_price(self, side: Side) -> Optional[Decimal]:
        """Retorna o melhor preço entre as ordens não-pegged do lado, ou None."""
        for level in self._book.levels(side):
            for order in level:
                if not order.is_pegged:
                    return level.price
        return None

    def add(self, order: Order) -> None:
        """Adiciona uma ordem pegged ao conjunto monitorado."""
        self._pegged_orders[order.id] = order

    def reprice(self) -> None:
        """
        Executa o repique para cada ordem pegged monitorada:
        - Se ela não está mais no livro: descarta da monitoração.
        - Se não há referência: mantém o preço.
        - Senão: move para a nova referência mantendo o sequence original.
        """
        for order_id in list(self._pegged_orders.keys()):
            order = self._book.get_order(order_id)
            if order is None:
                # Foi cancelada ou totalmente executada
                del self._pegged_orders[order_id]
                continue

            ref_price = self.get_reference_price(order.side)
            if ref_price is None:
                # Não há referência (todas as limits saíram): mantém o preço atual
                continue

            if ref_price != order.price:
                self._book.remove_order(order.id)
                order.price = ref_price
                self._book.add_order(order)  # Preserva order.sequence original!
