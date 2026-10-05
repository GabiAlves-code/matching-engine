from decimal import Decimal
from itertools import zip_longest
from typing import List

from src.domain.models import Side
from src.engine.order_book import OrderBook

LEFT_COL_WIDTH = 20
RIGHT_COL_WIDTH = 17


def format_price(price: Decimal) -> str:
    """
    Formata o valor monetário de forma limpa:
    - Sem zeros decimais redundantes (ex: 10.00 vira 10; 10.50 vira 10.5).
    - Sem notação científica para valores inteiros ou elevados (ex: 100, 1000).
    """
    return format(price.normalize(), "f")


def render_book(book: OrderBook) -> str:
    """
    Renderiza a visualização do livro de ofertas em formato tabular de duas colunas:
    - Coluna da esquerda: Ordens de Compra ordenadas por prioridade (maior preço primeiro).
    - Coluna da direita: Ordens de Venda ordenadas por prioridade (menor preço primeiro).
    - Uma linha por ordem individual ativa no livro, preservando a fila FIFO por sequence.
    - Células em branco quando um lado possuir menos ofertas que o outro.
    """
    header = f"{'Ordens de Compra'.ljust(LEFT_COL_WIDTH)}| Ordens de Venda"
    divider = f"{'-' * LEFT_COL_WIDTH}|{'-' * RIGHT_COL_WIDTH}"

    lines: List[str] = [header, divider]

    buy_entries = [
        f"{order.qty} @ {format_price(order.price)}"
        for level in book.levels(Side.BUY)
        for order in level
    ]

    sell_entries = [
        f"{order.qty} @ {format_price(order.price)}"
        for level in book.levels(Side.SELL)
        for order in level
    ]

    for buy_text, sell_text in zip_longest(buy_entries, sell_entries, fillvalue=""):
        left_cell = buy_text.ljust(LEFT_COL_WIDTH)
        right_cell = f" {sell_text}" if sell_text else ""
        lines.append(f"{left_cell}|{right_cell}".rstrip())

    return "\n".join(lines)

