import bisect
from decimal import Decimal
from typing import Iterator, Optional

from src.domain.models import Order, OrderType, Side
from src.engine.price_level import PriceLevel


class OrderBook:
    """
    Representa o livro de ofertas em memória para um único ativo.
    
    Responsabilidade:
    - Armazenar e organizar as ordens passivas (LIMIT e PEGGED com preço definido).
    - Gerenciar os lados de Compra (Bids) e Venda (Asks).
    - Manter os níveis de preço (PriceLevel) ordenados:
        * Bids: decrescente (maior preço tem prioridade).
        * Asks: crescente (menor preço tem prioridade).
    - Índice global de busca rápida por ID em O(1).
    - Autolimpeza de níveis de preço esvaziados.
    - Zero lógica de apresentação/strings (sem print ou formatação visual).
    - Zero lógica de matching de mercado (pertence à MatchingEngine).
    """

    def __init__(self) -> None:
        # Dicionários de patamares de preço por lado
        self._bids: dict[Decimal, PriceLevel] = {}
        self._asks: dict[Decimal, PriceLevel] = {}

        # Listas ordenadas (sempre em ordem crescente) para busca binária eficiente via bisect
        self._bid_prices: list[Decimal] = []
        self._ask_prices: list[Decimal] = []

        # Índice global de ordens ativas: order_id -> Order (busca O(1))
        self._orders_by_id: dict[int, Order] = {}

    @property
    def is_empty(self) -> bool:
        """Indica se o livro está 100% vazio (sem ofertas ativas em nenhum lado)."""
        return len(self._orders_by_id) == 0

    @property
    def total_orders(self) -> int:
        """Quantidade total de ordens ativas registradas no livro."""
        return len(self._orders_by_id)

    def _get_side_structures(self, side: Side) -> tuple[dict[Decimal, PriceLevel], list[Decimal]]:
        """Retorna o dicionário de níveis e a lista ordenada de preços do lado indicado."""
        if side == Side.BUY:
            return self._bids, self._bid_prices
        return self._asks, self._ask_prices

    def add_order(self, order: Order) -> None:
        """
        Adiciona uma ordem passiva ao livro de ofertas.
        
        Regras:
        - Rejeita ordens MARKET (não repousam no livro).
        - Rejeita ordens sem preço ou com preço <= 0.
        - Rejeita ordens com ID já existente no livro.
        """
        if order.order_type == OrderType.MARKET:
            raise ValueError("Ordens a mercado (MARKET) não são registradas no livro de ofertas.")
        if order.price is None:
            raise ValueError("Apenas ordens com preço definido podem ser adicionadas ao livro.")
        if order.price <= Decimal("0"):
            raise ValueError(f"Preço da ordem deve ser maior que zero, recebido: {order.price}")
        if order.id in self._orders_by_id:
            raise ValueError(f"Ordem com id {order.id} já existe no livro de ofertas.")

        side_dict, price_list = self._get_side_structures(order.side)

        # Se o patamar de preço ainda não existe, cria um novo PriceLevel e insere o preço ordenado
        if order.price not in side_dict:
            side_dict[order.price] = PriceLevel(order.price)
            bisect.insort(price_list, order.price)

        level = side_dict[order.price]
        level.add_order(order)
        self._orders_by_id[order.id] = order

    def remove_order(self, order_id: int) -> Optional[Order]:
        """
        Remove uma ordem do livro pelo seu identificador único.
        
        Comportamento:
        - Retorna a ordem removida se encontrada.
        - Retorna None se o ID não existir no livro (idempotência segura).
        - Se o PriceLevel ficar sem ordens após a remoção, ele é expurgado
          do dicionário e da lista ordenada de preços.
        """
        order = self._orders_by_id.get(order_id)
        if order is None:
            return None

        side_dict, price_list = self._get_side_structures(order.side)
        level = side_dict.get(order.price)

        if level is not None:
            level.remove_order(order_id)
            if level.is_empty:
                del side_dict[order.price]
                # Remove o preço da lista ordenada via busca binária
                idx = bisect.bisect_left(price_list, order.price)
                if idx < len(price_list) and price_list[idx] == order.price:
                    price_list.pop(idx)

        del self._orders_by_id[order_id]
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        """Consulta uma ordem ativa no livro pelo seu ID em O(1)."""
        return self._orders_by_id.get(order_id)

    def best_price(self, side: Side) -> Optional[Decimal]:
        """
        Retorna o melhor preço disponível para o lado informado em O(1).
        
        - Side.BUY: maior preço de compra (Best Bid).
        - Side.SELL: menor preço de venda (Best Offer / Ask).
        - Retorna None se o lado estiver sem ofertas.
        """
        _, price_list = self._get_side_structures(side)
        if not price_list:
            return None

        if side == Side.BUY:
            return price_list[-1]  # Maior preço (final da lista ordenada crescente)
        return price_list[0]       # Menor preço (início da lista ordenada crescente)

    def peek_best(self, side: Side) -> Optional[Order]:
        """
        Retorna a primeira ordem do topo do livro (maior prioridade temporal FIFO
        dentro do melhor nível de preço) sem removê-la.
        
        Retorna None se o lado estiver vazio.
        """
        best_p = self.best_price(side)
        if best_p is None:
            return None

        side_dict, _ = self._get_side_structures(side)
        level = side_dict[best_p]
        return level.peek_first()

    def levels(self, side: Side) -> Iterator[PriceLevel]:
        """
        Itera sobre os PriceLevels do lado especificado em estrita ordem de prioridade:
        - Side.BUY: do maior preço para o menor (decrescente).
        - Side.SELL: do menor preço para o maior (crescente).
        """
        side_dict, price_list = self._get_side_structures(side)
        if side == Side.BUY:
            for price in reversed(price_list):
                yield side_dict[price]
        else:
            for price in price_list:
                yield side_dict[price]

    def __contains__(self, order_id: int) -> bool:
        """Verifica se uma ordem está ativa no livro em O(1)."""
        return order_id in self._orders_by_id

    def __len__(self) -> int:
        """Retorna o total de ordens ativas no livro."""
        return self.total_orders

    def __repr__(self) -> str:
        return (
            f"OrderBook(bids={len(self._bid_prices)} levels, "
            f"asks={len(self._ask_prices)} levels, "
            f"total_orders={self.total_orders})"
        )

