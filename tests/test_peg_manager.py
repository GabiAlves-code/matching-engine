from decimal import Decimal
import pytest

from src.domain.models import PegReference, Side
from src.engine.order_manager import OrderManager


def test_peg_page_4_scenario():
    """
    1. Livro tem:
       Compra 200 @ 10.00 | Venda 100 @ 10.50
       Compra 100 @ 9.99  |
    2. Entra 'peg bid buy 150':
       Assume preço 10.00 e fica atrás da de 200 na fila.
    3. Entra 'limit buy 10.1 300':
       Novo Best Bid passa para 10.10.
       A ordem pegged reajusta para 10.10 e fica À FRENTE da ordem de 300 (mantém sequence original).
    """
    manager = OrderManager()
    manager.submit_limit_order(Side.BUY, Decimal("10.00"), 200)   # id=1, seq=1
    manager.submit_limit_order(Side.BUY, Decimal("9.99"), 100)    # id=2, seq=2
    manager.submit_limit_order(Side.SELL, Decimal("10.50"), 100)  # id=3, seq=3

    # Entra peg bid buy 150 (id=4, seq=4)
    peg_order, _ = manager.submit_peg_order(PegReference.BID, Side.BUY, 150)
    assert peg_order.price == Decimal("10.00")
    assert peg_order.id == 4
    assert peg_order.sequence == 4

    # No nível 10.00, a ordem passiva id=1 (seq=1) está à frente da peg id=4 (seq=4)
    assert manager.book.peek_best(Side.BUY).id == 1

    # Entra limit buy 10.1 300 (id=5, seq=5)
    limit_300, _ = manager.submit_limit_order(Side.BUY, Decimal("10.10"), 300)

    # O repique automático moveu a peg para 10.10
    assert peg_order.price == Decimal("10.10")
    assert manager.book.best_price(Side.BUY) == Decimal("10.10")

    # Ponto alto do PDF: No nível 10.10, a ordem pegged (seq=4) fica À FRENTE da limit de 300 (seq=5)!
    best_buy = manager.book.peek_best(Side.BUY)
    assert best_buy.id == peg_order.id
    assert best_buy.qty == 150

    # Confirma as duas ordens no nível 10.10 na ordem exata do PDF
    level_10_1 = next(manager.book.levels(Side.BUY))
    assert [o.id for o in level_10_1] == [peg_order.id, limit_300.id]


def test_peg_offer_sell_tracks_best_offer():
    """Valida ordem 'peg offer sell' acompanhando dinamicamente o menor preço de venda."""
    manager = OrderManager()
    manager.submit_limit_order(Side.SELL, Decimal("20.00"), 100)

    peg_sell, _ = manager.submit_peg_order(PegReference.OFFER, Side.SELL, 50)
    assert peg_sell.price == Decimal("20.00")

    # Nova melhor venda entra a 19.50
    manager.submit_limit_order(Side.SELL, Decimal("19.50"), 100)

    # A ordem pegged deve ter sido repicada para 19.50
    assert peg_sell.price == Decimal("19.50")
    assert manager.book.best_price(Side.SELL) == Decimal("19.50")
    assert manager.book.peek_best(Side.SELL).id == peg_sell.id


def test_peg_without_reference_rejected_without_consuming_id():
    """Valida que ordem peg sem referência no livro é rejeitada sem consumir ID/sequence."""
    manager = OrderManager()

    with pytest.raises(ValueError, match="Não há ordens de referência"):
        manager.submit_peg_order(PegReference.BID, Side.BUY, 100)

    # Próxima ordem limite deve receber id=1 e sequence=1
    order, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)
    assert order.id == 1
    assert order.sequence == 1


def test_cancel_reference_limit_keeps_peg_at_last_price():
    """Valida que cancelar a ordem limite de referência mantém a peg no último preço."""
    manager = OrderManager()
    o1, _ = manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)
    peg_order, _ = manager.submit_peg_order(PegReference.BID, Side.BUY, 50)

    assert peg_order.price == Decimal("10.00")

    # Cancela o único limit de referência
    manager.cancel_order(o1.id)

    # Sem limites de referência restantes, a peg deve permanecer ativa a 10.00
    assert manager.book.best_price(Side.BUY) == Decimal("10.00")
    assert manager.book.get_order(peg_order.id) is not None
    assert peg_order.price == Decimal("10.00")


def test_peg_filled_by_market_does_not_break_next_reprice():
    """Valida que ordem peg totalmente executada por ordem a mercado é descartada e não quebra o próximo repique."""
    manager = OrderManager()
    manager.submit_limit_order(Side.BUY, Decimal("10.00"), 100)
    peg_order, _ = manager.submit_peg_order(PegReference.BID, Side.BUY, 50)

    # Venda a mercado de 150 consome a limit de 100 e a peg de 50
    _, trades = manager.submit_market_order(Side.SELL, 150)
    assert len(trades) == 1
    assert trades[0].qty == 150

    # Livro de compra está vazio
    assert manager.book.is_empty is True

    # Entra nova compra limite a 11.00: repique roda sem erros e a peg antiga não volta ao livro
    manager.submit_limit_order(Side.BUY, Decimal("11.00"), 100)
    assert manager.book.total_orders == 1
    assert manager.book.get_order(peg_order.id) is None
