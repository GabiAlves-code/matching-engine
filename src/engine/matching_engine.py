from decimal import Decimal
from typing import Optional

from src.domain.models import Order, OrderType, Side, Trade
from src.engine.order_book import OrderBook


class MatchingEngine:
    """
    Motor de Casamento de Ofertas (Matching & Execution Engine).
    
    Responsabilidade Estrita (Opção 3):
    - Receber uma ordem (LIMIT ou MARKET) e cruzá-la contra o OrderBook.
    - Casar ordens agressoras contra ordens passivas no topo do livro (Price-Time Priority).
    - Executar os trades sempre ao preço da ordem passiva (maker price).
    - Consolidar/agregar trades por nível de preço (requisito da página 2 do PDF).
    - Descartar saldo não preenchido de ordens MARKET.
    - Repousar saldo não preenchido de ordens LIMIT no livro como passiva.
    - Zero lógica de gerenciamento de pegs, cancelamento ou alteração (pertencem ao OrderManager).
    - Zero chamadas a print().
    """

    def __init__(self, book: Optional[OrderBook] = None) -> None:
        self._book: OrderBook = book if book is not None else OrderBook()

    @property
    def book(self) -> OrderBook:
        """Retorna o livro de ofertas associado a esta engine."""
        return self._book

    def process_order(self, order: Order, book: Optional[OrderBook] = None) -> list[Trade]:
        """
        Processa uma nova ordem no livro de ofertas.
        
        Retorna a lista de trades gerados consolidados por nível de preço atingido.
        Se a ordem for puramente passiva (não cruzar o spread), é inserida no livro
        e retorna uma lista vazia ([]).
        """
        target_book = book if book is not None else self._book
        opposite_side = Side.SELL if order.side == Side.BUY else Side.BUY

        aggregated_trades: list[Trade] = []
        current_trade_price: Optional[Decimal] = None
        current_trade_qty: int = 0

        # Loop de matching contra a liquidez disponível no topo da contraparte
        while order.qty > 0:
            maker = target_book.peek_best(opposite_side)
            if maker is None:
                # Sem mais contrapartes no livro
                break

            # Para ordens LIMIT: verifica se o preço cruza o spread
            if order.order_type == OrderType.LIMIT:
                if order.side == Side.BUY and maker.price > order.price:
                    # Melhor venda está mais cara do que o limite de compra -> não cruza mais
                    break
                if order.side == Side.SELL and maker.price < order.price:
                    # Melhor compra está mais barata do que o limite de venda -> não cruza mais
                    break

            trade_price = maker.price
            trade_qty = min(order.qty, maker.qty)

            # Executa o preenchimento em ambas as ordens
            order.fill(trade_qty)
            maker.fill(trade_qty)

            # Se a ordem passiva (maker) foi totalmente consumida, remove-a do livro
            if maker.qty == 0:
                target_book.remove_order(maker.id)

            # Agregação de trades por nível de preço (exigência da página 2 do PDF)
            if trade_price == current_trade_price:
                current_trade_qty += trade_qty
            else:
                if current_trade_price is not None:
                    aggregated_trades.append(
                        Trade(price=current_trade_price, qty=current_trade_qty)
                    )
                current_trade_price = trade_price
                current_trade_qty = trade_qty

        # Adiciona o último lote consolidado de trades
        if current_trade_price is not None:
            aggregated_trades.append(
                Trade(price=current_trade_price, qty=current_trade_qty)
            )

        # Tratamento de saldo remanescente da ordem agressora
        if order.qty > 0:
            if order.order_type == OrderType.LIMIT:
                # Saldo remanescente de Limit Order repousa no livro
                target_book.add_order(order)
            elif order.order_type == OrderType.MARKET:
                # Saldo remanescente de Market Order é descartado (não vai para o livro)
                pass

        return aggregated_trades
