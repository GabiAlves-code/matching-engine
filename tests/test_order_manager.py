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


def test_modify_order_price_repositions_pdf_page_3_scenario():
    """
    Livro inicial:
    Compra 200 @ 10.00 | Venda 100 @ 10.50
    Compra 100 @ 9.99  |
    
    Ao alterar a primeira ordem de compra (200 @ 10.00) para 9.98:
    A ordem de 100 @ 9.99 passa a ser o Best Bid e a de 200 @ 9.98 perde prioridade.
    """
    manager = OrderManager()
    o1, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 200)
    o2, _ = manager.submit_limit_order(Side.BUY, Decimal("9.99"), 100)
    o3, _ = manager.submit_limit_order(Side.SELL, Decimal("10.50"), 100)

    original_seq = o1.sequence

    # Altera o preço de o1 para 9.98
    modified, trades = manager.modify_order(o1.id, new_price=Decimal("9.98"))

    assert trades == []
    assert modified.price == Decimal("9.98")
    assert modified.sequence > original_seq  # Perdeu prioridade na fila (ganhou novo sequence)

    # Novo melhor preço de compra deve ser 9.99 (ordem o2)
    assert manager.book.best_price(Side.BUY) == Decimal("9.99")
    assert manager.book.peek_best(Side.BUY) == o2

    # Verifica a ordem dos níveis de compra
    buy_levels = list(manager.book.levels(Side.BUY))
    assert len(buy_levels) == 2
    assert buy_levels[0].price == Decimal("9.99")
    assert buy_levels[1].price == Decimal("9.98")
    assert buy_levels[1].peek_first() == modified


def test_modify_order_qty_only():
    """Valida alteração apenas de quantidade (preço inalterado, sequence preservado)."""
    manager = OrderManager()
    order, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)
    original_seq = order.sequence

    modified, trades = manager.modify_order(order.id, new_qty=150)

    assert trades == []
    assert modified.qty == 150
    assert modified.sequence == original_seq  # Preço não mudou, manteve sequence


def test_modify_order_crossing_spread_executes_as_taker():
    """Valida que alterar o preço para um valor que cruza o spread executa trade imediatamente."""
    manager = OrderManager()
    # Venda passiva em 20.00
    manager.submit_limit_order(Side.SELL, Decimal("20.00"), 100)
    # Compra passiva em 19.00
    buy_order, _ = manager.submit_limit_order(Side.BUY, Decimal("19.00"), 100)

    # Modifica compra para 20.00 (cruza com a venda)
    _, trades = manager.modify_order(buy_order.id, new_price=Decimal("20.00"))

    assert len(trades) == 1
    assert trades[0] == Trade(price=Decimal("20.00"), qty=100)
    assert manager.book.is_empty is True


def test_modify_order_validations():
    """Valida rejeição de parâmetros inválidos na alteração."""
    manager = OrderManager()
    order, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)

    # ID inexistente
    with pytest.raises(ValueError, match="não encontrada"):
        manager.modify_order(999, new_price=Decimal("11.00"))

    # Nenhum campo informado
    with pytest.raises(ValueError, match="Informe pelo menos um"):
        manager.modify_order(order.id)

    # Preço inválido
    with pytest.raises(ValueError, match="Preço deve ser estritamente positivo"):
        manager.modify_order(order.id, new_price=Decimal("0"))

    # Quantidade inválida
    with pytest.raises(ValueError, match="Quantidade deve ser estritamente positiva"):
        manager.modify_order(order.id, new_qty=-10)


