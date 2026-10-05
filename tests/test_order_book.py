from decimal import Decimal
import pytest

from src.domain.models import Order, OrderType, Side
from src.engine.order_book import OrderBook


def make_order(
    order_id: int,
    side: Side,
    sequence: int,
    price: str,
    qty: int = 100,
    order_type: OrderType = OrderType.LIMIT,
) -> Order:
    """Helper para instanciar ordens nos testes."""
    return Order(
        id=order_id,
        side=side,
        order_type=order_type,
        qty=qty,
        initial_qty=qty,
        sequence=sequence,
        price=Decimal(price) if price is not None else None,
    )


def test_order_book_starts_empty():
    """Valida que o livro inicia 100% vazio, sem ativos ou preços pré-definidos."""
    book = OrderBook()
    assert book.is_empty is True
    assert book.total_orders == 0
    assert len(book) == 0
    assert book.best_price(Side.BUY) is None
    assert book.best_price(Side.SELL) is None
    assert book.peek_best(Side.BUY) is None
    assert book.peek_best(Side.SELL) is None
    assert list(book.levels(Side.BUY)) == []
    assert list(book.levels(Side.SELL)) == []


def test_best_bid_is_highest_and_best_offer_is_lowest():
    """
    Valida a prioridade de preço:
    - Compra (Bid): maior preço tem prioridade (ex: 10.00 > 9.90).
    - Venda (Offer): menor preço tem prioridade (ex: 10.50 < 11.00).
    """
    book = OrderBook()

    # Compras
    book.add_order(make_order(1, Side.BUY, sequence=1, price="9.90"))
    book.add_order(make_order(2, Side.BUY, sequence=2, price="10.00"))
    assert book.best_price(Side.BUY) == Decimal("10.00")

    # Vendas
    book.add_order(make_order(3, Side.SELL, sequence=3, price="11.00"))
    book.add_order(make_order(4, Side.SELL, sequence=4, price="10.50"))
    assert book.best_price(Side.SELL) == Decimal("10.50")


def test_multiple_orders_same_price_fifo_sequence():
    """Valida que duas ordens no mesmo preço ficam no mesmo PriceLevel, ordenadas por sequence."""
    book = OrderBook()
    o1 = make_order(1, Side.BUY, sequence=1, price="10.00", qty=100)
    o2 = make_order(2, Side.BUY, sequence=2, price="10.00", qty=200)

    book.add_order(o1)
    book.add_order(o2)

    levels = list(book.levels(Side.BUY))
    assert len(levels) == 1
    assert levels[0].price == Decimal("10.00")
    assert levels[0].order_count == 2
    assert levels[0].total_qty == 300
    assert list(levels[0]) == [o1, o2]
    assert book.peek_best(Side.BUY) == o1


def test_levels_iteration_priority_order():
    """Valida a ordem de iteração dos PriceLevels: Bids decrescente e Asks crescente."""
    book = OrderBook()

    # Inserção fora de ordem nas compras
    book.add_order(make_order(1, Side.BUY, 1, "9.90"))
    book.add_order(make_order(2, Side.BUY, 2, "10.00"))
    book.add_order(make_order(3, Side.BUY, 3, "9.95"))

    bid_prices = [lvl.price for lvl in book.levels(Side.BUY)]
    assert bid_prices == [Decimal("10.00"), Decimal("9.95"), Decimal("9.90")]

    # Inserção fora de ordem nas vendas
    book.add_order(make_order(4, Side.SELL, 4, "10.80"))
    book.add_order(make_order(5, Side.SELL, 5, "10.20"))
    book.add_order(make_order(6, Side.SELL, 6, "10.50"))

    ask_prices = [lvl.price for lvl in book.levels(Side.SELL)]
    assert ask_prices == [Decimal("10.20"), Decimal("10.50"), Decimal("10.80")]


def test_remove_last_order_prunes_empty_level_and_updates_best_price():
    """Valida que esvaziar um nível o remove do livro e atualiza o melhor preço."""
    book = OrderBook()
    o1 = make_order(1, Side.BUY, 1, "10.00")
    o2 = make_order(2, Side.BUY, 2, "9.90")
    book.add_order(o1)
    book.add_order(o2)

    assert book.best_price(Side.BUY) == Decimal("10.00")

    # Remove o único pedido em 10.00
    removed = book.remove_order(1)
    assert removed == o1
    assert 1 not in book
    assert book.get_order(1) is None

    # O nível 10.00 deve ter sido expurgado e o melhor preço agora é 9.90
    assert book.best_price(Side.BUY) == Decimal("9.90")
    assert len(list(book.levels(Side.BUY))) == 1

    # Remove a ordem remanescente
    book.remove_order(2)
    assert book.best_price(Side.BUY) is None
    assert book.is_empty is True


def test_remove_nonexistent_order_returns_none():
    """Valida que tentar remover um ID inexistente retorna None com segurança."""
    book = OrderBook()
    book.add_order(make_order(1, Side.BUY, 1, "10.00"))

    assert book.remove_order(999) is None
    assert book.total_orders == 1


def test_add_order_validations():
    """Valida rejeição de inputs inválidos no livro de ofertas."""
    book = OrderBook()

    # Market orders não vão para o livro
    market_order = Order(
        id=1,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        qty=100,
        initial_qty=100,
        sequence=1,
        price=None,
    )
    with pytest.raises(ValueError, match="Ordens a mercado"):
        book.add_order(market_order)

    # Ordem com preço None não vai para o livro
    with pytest.raises(ValueError, match="Apenas ordens com preço"):
        bad_order = make_order(2, Side.BUY, 2, "10.00")
        bad_order.price = None
        book.add_order(bad_order)

    # ID duplicado
    o1 = make_order(10, Side.BUY, 10, "10.00")
    book.add_order(o1)
    with pytest.raises(ValueError, match="já existe no livro"):
        duplicate = make_order(10, Side.BUY, 11, "10.00")
        book.add_order(duplicate)


def test_decimal_equivalence_vs_different_prices():
    """
    Validação explícita de precisão decimal:
    - 10.5 e 10.50 possuem o mesmo valor econômico e compartilham o mesmo PriceLevel.
    - 10.50 e 10.55 são preços diferentes e geram dois PriceLevels separados e ordenados.
    """
    book = OrderBook()

    # Mesma faixa de preço com formatações numéricas equivalentes
    o1 = make_order(1, Side.BUY, 1, "10.5", qty=100)
    o2 = make_order(2, Side.BUY, 2, "10.50", qty=200)
    book.add_order(o1)
    book.add_order(o2)

    # Preço diferente (10.55 é maior que 10.50)
    o3 = make_order(3, Side.BUY, 3, "10.55", qty=150)
    book.add_order(o3)

    levels = list(book.levels(Side.BUY))
    assert len(levels) == 2

    # Primeiro nível (melhor preço): 10.55
    assert levels[0].price == Decimal("10.55")
    assert levels[0].order_count == 1
    assert levels[0].total_qty == 150

    # Segundo nível: 10.5 (ou 10.50) agrupando as duas ordens equivalentes
    assert levels[1].price == Decimal("10.50")  # Comparação de valor Decimal
    assert levels[1].order_count == 2
    assert levels[1].total_qty == 300
    assert list(levels[1]) == [o1, o2]


def test_get_order_and_peek_best():
    """Valida consulta rápida de ordens ativas e observação do topo do livro."""
    book = OrderBook()
    o1 = make_order(1, Side.SELL, 1, "10.50", qty=50)
    book.add_order(o1)

    assert book.get_order(1) == o1
    assert book.get_order(2) is None
    assert book.peek_best(Side.SELL) == o1
    # peek_best não deve remover a ordem
    assert book.total_orders == 1

