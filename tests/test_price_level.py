from decimal import Decimal
import pytest

from src.domain.models import Order, OrderType, Side
from src.engine.price_level import PriceLevel


def make_order(order_id: int, sequence: int, price: str = "10.0", qty: int = 100) -> Order:
    """Helper para fabricar instâncias de Order em testes."""
    return Order(
        id=order_id,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        qty=qty,
        initial_qty=qty,
        sequence=sequence,
        price=Decimal(price),
    )


def test_empty_price_level():
    """Valida o estado inicial de um PriceLevel vazio."""
    level = PriceLevel(Decimal("10.00"))
    assert level.price == Decimal("10.00")
    assert level.is_empty is True
    assert level.total_qty == 0
    assert level.order_count == 0
    assert len(level) == 0
    assert level.peek_first() is None
    assert level.pop_first() is None
    assert list(level) == []
    assert level.remove_order(999) is None


def test_add_single_order():
    """Valida a adição de uma única ordem no nível."""
    level = PriceLevel(Decimal("10.00"))
    order = make_order(order_id=1, sequence=1, price="10.00", qty=150)

    level.add_order(order)

    assert level.is_empty is False
    assert level.order_count == 1
    assert len(level) == 1
    assert level.total_qty == 150
    assert level.peek_first() == order
    assert 1 in level
    assert level.get_order(1) == order


def test_add_multiple_orders_preserves_fifo_by_sequence():
    """Valida que ordens inseridas em ordem crescente de sequence preservam a fila FIFO."""
    level = PriceLevel(Decimal("10.00"))
    o1 = make_order(order_id=1, sequence=1, qty=100)
    o2 = make_order(order_id=2, sequence=2, qty=200)
    o3 = make_order(order_id=3, sequence=3, qty=300)

    level.add_order(o1)
    level.add_order(o2)
    level.add_order(o3)

    assert level.order_count == 3
    assert level.total_qty == 600
    assert list(level) == [o1, o2, o3]
    assert level.peek_first() == o1


def test_order_with_lower_sequence_inserted_later_comes_first_pegged_scenario():
    """
    Cenário crucial da página 4 do PDF:
    Uma ordem com sequence menor (ex: peg criada anteriormente com seq=1)
    ao ser inserida depois de uma ordem normal (seq=2) em 10.1,
    deve se posicionar À FRENTE na fila de prioridade.
    """
    level = PriceLevel(Decimal("10.10"))
    # Ordem limite convencional criada depois (seq=2, id=2)
    limit_order = make_order(order_id=2, sequence=2, price="10.10", qty=300)
    level.add_order(limit_order)

    # Ordem pegged criada antes (seq=1, id=1), que foi repicada para este nível depois
    pegged_order = make_order(order_id=1, sequence=1, price="10.10", qty=150)
    level.add_order(pegged_order)

    # A ordem com menor sequence (seq=1) deve ser a primeira da fila!
    assert level.peek_first() == pegged_order
    assert list(level) == [pegged_order, limit_order]


def test_remove_order_from_beginning_middle_and_end():
    """Valida a remoção de ordens do início, meio e fim da fila."""
    # 1. Remoção do início
    level = PriceLevel(Decimal("10.00"))
    o1, o2, o3 = make_order(1, 1), make_order(2, 2), make_order(3, 3)
    for o in [o1, o2, o3]:
        level.add_order(o)
    removed = level.remove_order(1)
    assert removed == o1
    assert list(level) == [o2, o3]

    # 2. Remoção do meio
    level = PriceLevel(Decimal("10.00"))
    o1, o2, o3 = make_order(1, 1), make_order(2, 2), make_order(3, 3)
    for o in [o1, o2, o3]:
        level.add_order(o)
    removed = level.remove_order(2)
    assert removed == o2
    assert list(level) == [o1, o3]

    # 3. Remoção do fim
    level = PriceLevel(Decimal("10.00"))
    o1, o2, o3 = make_order(1, 1), make_order(2, 2), make_order(3, 3)
    for o in [o1, o2, o3]:
        level.add_order(o)
    removed = level.remove_order(3)
    assert removed == o3
    assert list(level) == [o1, o2]


def test_remove_nonexistent_order_returns_none():
    """
    Valida comportamento para ID inexistente: retorna None sem alterar o estado.
    Permite idempotência no cancelamento.
    """
    level = PriceLevel(Decimal("10.00"))
    o1 = make_order(1, 1, qty=100)
    level.add_order(o1)

    result = level.remove_order(999)
    assert result is None
    assert level.order_count == 1
    assert level.total_qty == 100
    assert 1 in level


def test_removed_order_does_not_remain_in_queue():
    """Garante que a ordem removida desaparece de todas as estruturas internas."""
    level = PriceLevel(Decimal("10.00"))
    o1 = make_order(1, 1)
    level.add_order(o1)

    level.remove_order(1)

    assert 1 not in level
    assert level.get_order(1) is None
    assert level.is_empty is True
    assert level.order_count == 0
    assert level.total_qty == 0
    assert level.peek_first() is None


def test_pop_first_order():
    """Valida o método pop_first para consumo sequencial de ordens."""
    level = PriceLevel(Decimal("10.00"))
    o1 = make_order(1, 1, qty=100)
    o2 = make_order(2, 2, qty=200)
    level.add_order(o1)
    level.add_order(o2)

    popped1 = level.pop_first()
    assert popped1 == o1
    assert level.order_count == 1
    assert level.peek_first() == o2

    popped2 = level.pop_first()
    assert popped2 == o2
    assert level.is_empty is True

    assert level.pop_first() is None


def test_total_qty_updates_after_partial_fill():
    """Garante que a quantidade total do nível reflete alterações de quantidade em ordens."""
    level = PriceLevel(Decimal("10.00"))
    o1 = make_order(1, 1, qty=100)
    level.add_order(o1)
    assert level.total_qty == 100

    o1.fill(30)
    assert level.total_qty == 70


def test_price_level_validations():
    """Valida checagens de integridade defensivas."""
    # Preço <= 0 não permitido
    with pytest.raises(ValueError, match="maior que zero"):
        PriceLevel(Decimal("0"))

    level = PriceLevel(Decimal("10.00"))
    # Preço divergente
    with pytest.raises(ValueError, match="diverge do preço do nível"):
        wrong_price_order = make_order(1, 1, price="10.50")
        level.add_order(wrong_price_order)

    # Ordem duplicada
    valid_order = make_order(1, 1, price="10.00")
    level.add_order(valid_order)
    with pytest.raises(ValueError, match="já existe neste nível"):
        level.add_order(valid_order)
