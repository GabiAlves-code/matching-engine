from decimal import Decimal
import pytest

from src.domain.models import OrderStatus, OrderType, Side, Trade
from src.engine.order_manager import OrderManager


def test_submit_limit_order_generates_sequential_ids_and_sequence():
    """Valida que o OrderManager gera IDs e sequences sequenciais numéricos (1, 2, 3...)."""
    manager = OrderManager()

    o1, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)
    o2, _ = manager.submit_limit_order(Side.BUY, Decimal("9.90"), 50)
    o3, _ = manager.submit_market_order(Side.SELL, 20)

    assert o1.id == 1
    assert o1.sequence == 1

    assert o2.id == 2
    assert o2.sequence == 2

    assert o3.id == 3
    assert o3.sequence == 3


def test_submit_passive_limit_order_rests_in_book_no_trades():
    """Valida que uma Limit Order passiva é registrada no livro e retorna lista vazia de trades."""
    manager = OrderManager()

    order, trades = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)

    assert trades == []
    assert order.id == 1
    assert order.order_type == OrderType.LIMIT
    assert order.price == Decimal("10.00")
    assert order.qty == 100

    # Ordem repousa no livro de ofertas
    assert manager.book.total_orders == 1
    assert manager.book.get_order(1) == order
    assert manager.book.best_price(Side.BUY) == Decimal("10.00")


def test_submit_market_order_executes_trades_via_matching_engine():
    """Valida que uma Market Order submetida executa contra o livro via MatchingEngine."""
    manager = OrderManager()

    # Cria ordem de venda passiva no livro: 100 @ 20.00
    manager.submit_limit_order(Side.SELL, Decimal("20.00"), 100)

    # Submete compra a mercado de 60
    market_order, trades = manager.submit_market_order(Side.BUY, 60)

    assert len(trades) == 1
    assert trades[0] == Trade(price=Decimal("20.00"), qty=60)
    assert market_order.qty == 0

    # Sobraram 40 ações na ordem de venda
    sell_order = manager.book.get_order(1)
    assert sell_order is not None
    assert sell_order.qty == 40


def test_validation_errors():
    """Valida que o OrderManager rejeita preços e quantidades inválidas."""
    manager = OrderManager()

    # Preço <= 0
    with pytest.raises(ValueError, match="Preço deve ser estritamente positivo"):
        manager.submit_limit_order(Side.BUY, Decimal("0"), 100)

    with pytest.raises(ValueError, match="Preço deve ser estritamente positivo"):
        manager.submit_limit_order(Side.BUY, Decimal("-10.00"), 100)

    # Quantidade <= 0
    with pytest.raises(ValueError, match="Quantidade deve ser estritamente positiva"):
        manager.submit_limit_order(Side.BUY, Decimal("10.00"), 0)

    with pytest.raises(ValueError, match="Quantidade deve ser estritamente positiva"):
        manager.submit_market_order(Side.BUY, -5)


def test_cancel_active_order_success():
    """Valida o cancelamento de uma ordem ativa no livro (Requisito Adicional 3)."""
    manager = OrderManager()
    order, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)

    cancelled = manager.cancel_order(order.id)

    assert cancelled == order
    assert cancelled.status == OrderStatus.CANCELLED
    # Ordem deve ter sido retirada do livro
    assert manager.book.get_order(order.id) is None
    assert manager.book.is_empty is True


def test_cancel_nonexistent_order_returns_none():
    """Valida que tentar cancelar um ID que não existe retorna None com segurança."""
    manager = OrderManager()
    assert manager.cancel_order(999) is None


def test_cancel_already_filled_order_returns_none():
    """Valida que uma ordem 100% preenchida não pode ser cancelada (já saiu do livro)."""
    manager = OrderManager()
    manager.submit_limit_order(Side.SELL, Decimal("20.00"), 100)

    # Executa totalmente a ordem de venda com uma compra a mercado
    manager.submit_market_order(Side.BUY, 100)

    # Tenta cancelar a ordem de venda id=1
    assert manager.cancel_order(1) is None

