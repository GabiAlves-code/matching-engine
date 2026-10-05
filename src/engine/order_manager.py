from decimal import Decimal
from typing import Optional

from src.domain.models import Order, OrderStatus, OrderType, PegReference, Side, Trade
from src.engine.matching_engine import MatchingEngine
from src.engine.order_book import OrderBook
from src.engine.peg_manager import PegManager


class OrderManager:
    """
    Gerenciador de Ordens (Order Management System - OMS básico).

    Responsabilidades deste componente:
    - Ponto único de entrada da aplicação para criação e submissão de ordens.
    - Gerenciamento centralizado de IDs inteiros sequenciais (1, 2, 3...).
    - Gerenciamento do contador sequencial de prioridade temporal (sequence: 1, 2, 3...).
    - Validação de parâmetros de entrada (preço > 0, quantidade > 0).
    - Orquestração da execução delegando o cruzamento de ofertas à MatchingEngine.
    - Coordenação do PegManager para repique dinâmico de ordens pegged.
    - Retorno estruturado contendo a ordem criada e a lista de trades gerados.
    - Zero chamadas a print().
    """

    def __init__(
        self,
        book: Optional[OrderBook] = None,
        matching_engine: Optional[MatchingEngine] = None,
    ) -> None:
        self._book: OrderBook = book if book is not None else OrderBook()
        self._matching_engine: MatchingEngine = (
            matching_engine
            if matching_engine is not None
            else MatchingEngine(self._book)
        )
        self._peg_manager: PegManager = PegManager(self._book)
        self._next_order_id: int = 1
        self._next_sequence: int = 1

    @property
    def book(self) -> OrderBook:
        """Retorna o livro de ofertas gerenciado."""
        return self._book

    @property
    def matching_engine(self) -> MatchingEngine:
        """Retorna a matching engine utilizada."""
        return self._matching_engine

    @property
    def peg_manager(self) -> PegManager:
        """Retorna o gerenciador de ordens pegged."""
        return self._peg_manager

    def _get_next_order_id(self) -> int:
        """Gera o próximo ID sequencial numérico para ordens."""
        order_id = self._next_order_id
        self._next_order_id += 1
        return order_id

    def _get_next_sequence(self) -> int:
        """Gera o próximo contador de prioridade temporal FIFO."""
        seq = self._next_sequence
        self._next_sequence += 1
        return seq

    def submit_limit_order(
        self, side: Side, price: Decimal, qty: int
    ) -> tuple[Order, list[Trade]]:
        """
        Cria e submete uma Limit Order no sistema.
        """
        if price <= Decimal("0"):
            raise ValueError(f"Preço deve ser estritamente positivo, recebido: {price}")
        if qty <= 0:
            raise ValueError(f"Quantidade deve ser estritamente positiva, recebida: {qty}")

        order = Order(
            id=self._get_next_order_id(),
            side=side,
            order_type=OrderType.LIMIT,
            qty=qty,
            initial_qty=qty,
            sequence=self._get_next_sequence(),
            price=price,
        )

        trades = self._matching_engine.process_order(order, self._book)
        self._peg_manager.reprice()
        return order, trades

    def submit_market_order(
        self, side: Side, qty: int
    ) -> tuple[Order, list[Trade]]:
        """
        Cria e submete uma Market Order no sistema.
        """
        if qty <= 0:
            raise ValueError(f"Quantidade deve ser estritamente positiva, recebida: {qty}")

        order = Order(
            id=self._get_next_order_id(),
            side=side,
            order_type=OrderType.MARKET,
            qty=qty,
            initial_qty=qty,
            sequence=self._get_next_sequence(),
            price=None,
        )

        trades = self._matching_engine.process_order(order, self._book)
        self._peg_manager.reprice()
        return order, trades

    def submit_peg_order(
        self, peg_ref: PegReference, side: Side, qty: int
    ) -> tuple[Order, list[Trade]]:
        """
        Cria e registra uma Ordem Pegged

        Regras:
        - Aceita apenas 'peg bid buy' e 'peg offer sell'.
        - qty > 0.
        - Rejeita com ValueError se não houver ordens limites de referência,
          ANTES de consumir id e sequence.
        """
        if qty <= 0:
            raise ValueError(f"Quantidade deve ser estritamente positiva, recebida: {qty}")

        if not (
            (peg_ref == PegReference.BID and side == Side.BUY)
            or (peg_ref == PegReference.OFFER and side == Side.SELL)
        ):
            raise ValueError(
                f"Combinação inválida: suportado apenas 'peg bid buy' ou 'peg offer sell', recebido: peg {peg_ref.value} {side.value}"
            )

        ref_price = self._peg_manager.get_reference_price(side)
        if ref_price is None:
            raise ValueError(
                f"Não há ordens de referência não-pegged para ancorar a ordem peg {peg_ref.value} {side.value}."
            )

        order = Order(
            id=self._get_next_order_id(),
            side=side,
            order_type=OrderType.PEGGED,
            qty=qty,
            initial_qty=qty,
            sequence=self._get_next_sequence(),
            price=ref_price,
            peg_ref=peg_ref,
        )

        self._book.add_order(order)
        self._peg_manager.add(order)
        self._peg_manager.reprice()
        return order, []

    def cancel_order(self, order_id: int) -> Optional[Order]:
        """
        Cancela uma ordem ativa no livro pelo seu identificador único.
        """
        order = self._book.remove_order(order_id)
        if order is None:
            return None

        order.status = OrderStatus.CANCELLED
        self._peg_manager.reprice()
        return order

    def modify_order(
        self,
        order_id: int,
        new_price: Optional[Decimal] = None,
        new_qty: Optional[int] = None,
    ) -> tuple[Order, list[Trade]]:
        """
        Altera preço, quantidade ou ambos de uma ordem ativa no livro.
        - Alterar o preço faz a ordem perder prioridade na fila (ganha novo sequence).
        - Se o novo preço cruzar o spread, executa trades imediatamente.
        """
        order = self._book.get_order(order_id)
        if order is None:
            raise ValueError(f"Ordem {order_id} não encontrada ou não está ativa no livro.")

        if new_price is None and new_qty is None:
            raise ValueError("Informe pelo menos um novo preço ou uma nova quantidade.")

        if new_price is not None and new_price <= Decimal("0"):
            raise ValueError(f"Preço deve ser estritamente positivo, recebido: {new_price}")

        if new_qty is not None and new_qty <= 0:
            raise ValueError(f"Quantidade deve ser estritamente positiva, recebida: {new_qty}")

        # Remove do nível atual no livro
        self._book.remove_order(order_id)

        # Regra do PDF: alterar o preço faz a ordem perder prioridade na fila
        if new_price is not None and new_price != order.price:
            order.price = new_price
            order.sequence = self._get_next_sequence()

        if new_qty is not None:
            order.qty = new_qty
            order.initial_qty = max(order.initial_qty, new_qty)

        # Re-submete à engine (se cruzar o spread gera trades; se não, repousa no livro)
        trades = self._matching_engine.process_order(order, self._book)
        self._peg_manager.reprice()
        return order, trades
