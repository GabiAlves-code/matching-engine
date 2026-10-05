from decimal import Decimal
import pytest

from src.domain.models import Order, OrderType, Side, Trade
from src.engine.matching_engine import MatchingEngine
from src.engine.order_book import OrderBook


def make_order(
    order_id: int,
    side: Side,
    order_type: OrderType,
    qty: int,
    sequence: int,
    price: str = None,
) -> Order:
    """Helper para fabricação de ordens em testes."""
    return Order(
        id=order_id,
        side=side,
        order_type=order_type,
        qty=qty,
        initial_qty=qty,
        sequence=sequence,
        price=Decimal(price) if price is not None else None,
    )


def test_passive_limit_order_placed_in_book_no_trades():
    """Valida que uma limit order passiva é repousada no livro sem gerar trades."""
    engine = MatchingEngine()
    order = make_order(1, Side.BUY, OrderType.LIMIT, qty=100, sequence=1, price="10.00")

    trades = engine.process_order(order)

    assert trades == []
    assert engine.book.total_orders == 1
    assert engine.book.get_order(1) == order
    assert engine.book.best_price(Side.BUY) == Decimal("10.00")


def test_market_buy_aggregates_trades_by_price_pdf_scenario():
    """
    Reproduz fielmente o primeiro cenário de trade do PDF (página 2):
    >>> limit sell 20 100
    >>> limit sell 20 200
    >>> market buy 150
    Trade, price: 20, qty: 150
    
    A compra de 150 consome 100 da primeira ordem e 50 da segunda.
    Gera exatamente 1 trade agregado de 150 ao preço de 20.
    """
    engine = MatchingEngine()
    s1 = make_order(1, Side.SELL, OrderType.LIMIT, qty=100, sequence=1, price="20.00")
    s2 = make_order(2, Side.SELL, OrderType.LIMIT, qty=200, sequence=2, price="20.00")
    engine.process_order(s1)
    engine.process_order(s2)

    market_buy = make_order(3, Side.BUY, OrderType.MARKET, qty=150, sequence=3)
    trades = engine.process_order(market_buy)

    assert len(trades) == 1
    assert trades[0] == Trade(price=Decimal("20.00"), qty=150)

    # Primeira ordem de venda foi 100% preenchida e removida do livro
    assert engine.book.get_order(1) is None
    # Segunda ordem de venda sobrou com 150 de quantidade
    remaining_s2 = engine.book.get_order(2)
    assert remaining_s2 is not None
    assert remaining_s2.qty == 150


def test_market_order_discards_unfilled_quantity():
    """
    Valida a segunda execução da página 2 do PDF:
    Restavam 150 a 20 no livro.
    >>> market buy 200
    Trade, price: 20, qty: 150
    O livro zera e os 50 remanescentes da ordem a mercado são descartados.
    """
    engine = MatchingEngine()
    s1 = make_order(1, Side.SELL, OrderType.LIMIT, qty=150, sequence=1, price="20.00")
    engine.process_order(s1)

    market_buy = make_order(2, Side.BUY, OrderType.MARKET, qty=200, sequence=2)
    trades = engine.process_order(market_buy)

    assert len(trades) == 1
    assert trades[0] == Trade(price=Decimal("20.00"), qty=150)

    # Livro ficou 100% vazio e a ordem de mercado não repousou no livro
    assert engine.book.is_empty is True


def test_market_order_sweeps_multiple_price_levels():
    """
    Valida que uma ordem a mercado que consome múltiplos níveis de preço
    gera uma linha de trade para cada patamar de preço consumido.
    """
    engine = MatchingEngine()
    s1 = make_order(1, Side.SELL, OrderType.LIMIT, qty=100, sequence=1, price="20.00")
    s2 = make_order(2, Side.SELL, OrderType.LIMIT, qty=50, sequence=2, price="21.00")
    engine.process_order(s1)
    engine.process_order(s2)

    # Compra a mercado de 130 consome 100 @ 20 e 30 @ 21
    market_buy = make_order(3, Side.BUY, OrderType.MARKET, qty=130, sequence=3)
    trades = engine.process_order(market_buy)

    assert len(trades) == 2
    assert trades[0] == Trade(price=Decimal("20.00"), qty=100)
    assert trades[1] == Trade(price=Decimal("21.00"), qty=30)

    # Restam 20 @ 21 no livro
    assert engine.book.best_price(Side.SELL) == Decimal("21.00")
    assert engine.book.get_order(2).qty == 20


def test_marketable_limit_order_fills_and_rests_remainder():
    """
    Valida ordem limite agressora (Marketable Limit Order):
    - Executa ao preço da ordem passiva (maker);
    - Saldo remanescente não executado repousa no livro de ofertas.
    """
    engine = MatchingEngine()
    # Venda passiva de 100 a 20.00
    s1 = make_order(1, Side.SELL, OrderType.LIMIT, qty=100, sequence=1, price="20.00")
    engine.process_order(s1)

    # Compra limite agressora de 150 a 21.00 (cruza o spread)
    aggressive_buy = make_order(2, Side.BUY, OrderType.LIMIT, qty=150, sequence=2, price="21.00")
    trades = engine.process_order(aggressive_buy)

    # Executou 100 ao preço passivo de 20.00
    assert len(trades) == 1
    assert trades[0] == Trade(price=Decimal("20.00"), qty=100)

    # O lado de venda zerou
    assert engine.book.best_price(Side.SELL) is None

    # O saldo de 50 da ordem de compra a 21.00 repousa no livro
    assert engine.book.best_price(Side.BUY) == Decimal("21.00")
    resting_order = engine.book.get_order(2)
    assert resting_order is not None
    assert resting_order.qty == 50


def test_market_order_on_empty_book_generates_no_trades():
    """Valida que ordem a mercado sem liquidez no livro não falha e é descartada."""
    engine = MatchingEngine()
    market_buy = make_order(1, Side.BUY, OrderType.MARKET, qty=100, sequence=1)

    trades = engine.process_order(market_buy)

    assert trades == []
    assert engine.book.is_empty is True


def test_market_sell_aggregates_trades_by_price():
    """Valida a terceira execução da página 2 do PDF (venda a mercado consumindo compra)."""
    engine = MatchingEngine()
    b1 = make_order(1, Side.BUY, OrderType.LIMIT, qty=100, sequence=1, price="10.00")
    engine.process_order(b1)

    market_sell = make_order(2, Side.SELL, OrderType.MARKET, qty=200, sequence=2)
    trades = engine.process_order(market_sell)

    assert len(trades) == 1
    assert trades[0] == Trade(price=Decimal("10.00"), qty=100)
    assert engine.book.is_empty is True
