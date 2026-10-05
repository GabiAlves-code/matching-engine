from decimal import Decimal

from src.domain.models import Order, OrderType, Side
from src.engine.order_book import OrderBook
from src.interface.book_presenter import format_price, render_book


def make_order(order_id: int, side: Side, sequence: int, price: str, qty: int) -> Order:
    return Order(
        id=order_id,
        side=side,
        order_type=OrderType.LIMIT,
        qty=qty,
        initial_qty=qty,
        sequence=sequence,
        price=Decimal(price),
    )


def test_format_price_decimal_cases():
    """Valida a formatação de preços sem zeros redundantes e sem notação científica."""
    assert format_price(Decimal("10.00")) == "10"
    assert format_price(Decimal("10.5")) == "10.5"
    assert format_price(Decimal("10.10")) == "10.1"
    assert format_price(Decimal("9.99")) == "9.99"
    assert format_price(Decimal("100")) == "100"
    assert format_price(Decimal("1000")) == "1000"


def test_render_empty_book():
    """Valida que o livro vazio renderiza apenas o cabeçalho e a linha divisória."""
    book = OrderBook()
    expected = (
        "Ordens de Compra    | Ordens de Venda\n"
        "--------------------|-----------------"
    )
    assert render_book(book) == expected


def test_render_book_with_bids_and_asks_fifo_order():
    """
    Valida a renderização tabular com múltiplas ordens e preservação da fila FIFO
    em níveis de mesmo preço.
    """
    book = OrderBook()
    # Duas ordens no mesmo nível de compra (10.1) respeitando a prioridade temporal
    book.add_order(make_order(1, Side.BUY, sequence=1, price="10.10", qty=150))
    book.add_order(make_order(2, Side.BUY, sequence=2, price="10.10", qty=300))
    book.add_order(make_order(3, Side.BUY, sequence=3, price="10.00", qty=200))
    book.add_order(make_order(4, Side.BUY, sequence=4, price="9.99", qty=100))

    # Uma ordem de venda a 10.5
    book.add_order(make_order(5, Side.SELL, sequence=5, price="10.50", qty=100))

    expected = (
        "Ordens de Compra    | Ordens de Venda\n"
        "--------------------|-----------------\n"
        "150 @ 10.1          | 100 @ 10.5\n"
        "300 @ 10.1          |\n"
        "200 @ 10            |\n"
        "100 @ 9.99          |"
    )
    assert render_book(book) == expected


def test_render_book_more_sells_than_buys():
    """Valida o alinhamento com células vazias na coluna de compra quando há mais vendas."""
    book = OrderBook()
    book.add_order(make_order(1, Side.BUY, sequence=1, price="10.00", qty=50))
    book.add_order(make_order(2, Side.SELL, sequence=2, price="10.50", qty=100))
    book.add_order(make_order(3, Side.SELL, sequence=3, price="11.00", qty=200))

    expected = (
        "Ordens de Compra    | Ordens de Venda\n"
        "--------------------|-----------------\n"
        "50 @ 10             | 100 @ 10.5\n"
        "                    | 200 @ 11"
    )
    assert render_book(book) == expected

