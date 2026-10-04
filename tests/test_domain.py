import pytest
from decimal import Decimal
from src.domain.models import Order, Side, OrderType, Trade, OrderStatus

def test_order_creation():
    # 1. Colocamos valores falsos para testar
    order = Order(
        id=1,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        qty=100,
        initial_qty=100,
        sequence=1,
        price=Decimal("10.50")
    )
    
    # 2. O assert verifica se o modelo salvou os valores corretamente
    assert order.id == 1
    assert order.side == Side.BUY
    assert order.price == Decimal("10.50")
    assert order.qty == 100
    assert order.order_type == OrderType.LIMIT
    assert order.status == OrderStatus.ACTIVE

def test_order_fill():
    # Testa a regra de preenchimento parcial da ordem
    order = Order(
        id=2, 
        side=Side.SELL, 
        order_type=OrderType.LIMIT,
        qty=100, 
        initial_qty=100, 
        sequence=2, 
        price=Decimal("20.00")
    )
    
    order.fill(40) # Consome 40 da quantidade
    assert order.qty == 60 # Verifica se sobraram 60
    assert order.status == OrderStatus.PARTIALLY_FILLED

def test_trade_creation():
    trade = Trade(
        price=Decimal("10.50"),
        qty=50
    )
    assert trade.price == Decimal("10.50")
    assert trade.qty == 50