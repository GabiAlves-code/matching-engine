from decimal import Decimal, InvalidOperation
from typing import List, Optional

from src.domain.models import PegReference, Side
from src.engine.order_manager import OrderManager
from src.interface.book_presenter import format_price, render_book


class CommandParser:
    """
    Parser e despachante de comandos da interface de terminal.

    Responsabilidade:
    - Interpretar linhas de texto do terminal.
    - Validar tipos de dados de entrada (rejeitando NaN, Infinity, strings inválidas e números <= 0).
    - Encaminhar para as operações correspondentes no OrderManager.
    - Formatar as linhas de saída textuais sem realizar chamadas a print().
    """

    def __init__(self, manager: OrderManager) -> None:
        self.manager: OrderManager = manager

    def _parse_price(self, price_str: str) -> Decimal:
        try:
            p = Decimal(price_str)
        except InvalidOperation:
            raise ValueError(f"Preço inválido: '{price_str}'")
        if p.is_nan() or p.is_infinite() or p <= Decimal("0"):
            raise ValueError(f"Preço deve ser um número positivo finito, recebido: '{price_str}'")
        return p

    def _parse_qty(self, qty_str: str) -> int:
        try:
            q = int(qty_str)
        except ValueError:
            raise ValueError(f"Quantidade deve ser um número inteiro, recebido: '{qty_str}'")
        if q <= 0:
            raise ValueError(f"Quantidade deve ser estritamente positiva, recebido: '{qty_str}'")
        return q

    def _parse_side(self, side_str: str) -> Side:
        side_clean = side_str.lower()
        if side_clean == "buy":
            return Side.BUY
        if side_clean == "sell":
            return Side.SELL
        raise ValueError(f"Lado inválido: '{side_str}'. Use 'buy' ou 'sell'")

    def parse_and_execute(self, line: str) -> List[str]:
        raw = line.strip()
        if not raw:
            return []

        tokens = raw.split()
        cmd = tokens[0].lower()

        try:
            # 1. Comando print book
            if cmd == "print" and len(tokens) >= 2 and tokens[1].lower() == "book":
                return [render_book(self.manager.book)]

            # 2. Comando limit <buy|sell> <price> <qty>
            if cmd == "limit":
                if len(tokens) != 4:
                    raise ValueError("Uso: limit <buy|sell> <price> <qty>")
                side = self._parse_side(tokens[1])
                price = self._parse_price(tokens[2])
                qty = self._parse_qty(tokens[3])

                order, trades = self.manager.submit_limit_order(side, price, qty)
                output_lines: List[str] = [
                    f"Trade, price: {format_price(t.price)}, qty: {t.qty}" for t in trades
                ]
                output_lines.append(
                    f"Order created: {order.side.value} {order.qty} @ {format_price(order.price)} {order.id}"
                )
                return output_lines

            # 3. Comando market <buy|sell> <qty>
            if cmd == "market":
                if len(tokens) != 3:
                    raise ValueError("Uso: market <buy|sell> <qty>")
                side = self._parse_side(tokens[1])
                qty = self._parse_qty(tokens[2])

                _, trades = self.manager.submit_market_order(side, qty)
                return [
                    f"Trade, price: {format_price(t.price)}, qty: {t.qty}" for t in trades
                ]

            # 4. Comando peg <bid|offer> <buy|sell> <qty>
            if cmd == "peg":
                if len(tokens) != 4:
                    raise ValueError("Uso: peg <bid|offer> <buy|sell> <qty>")
                ref_str = tokens[1].lower()
                if ref_str == "bid":
                    peg_ref = PegReference.BID
                elif ref_str == "offer":
                    peg_ref = PegReference.OFFER
                else:
                    raise ValueError(f"Referência peg inválida: '{tokens[1]}'. Use 'bid' ou 'offer'")

                side = self._parse_side(tokens[2])
                qty = self._parse_qty(tokens[3])

                order, _ = self.manager.submit_peg_order(peg_ref, side, qty)
                return [
                    f"Order created: {order.side.value} {order.qty} @ {format_price(order.price)} {order.id}"
                ]

            # 5. Comando cancel order <id>
            if cmd == "cancel" and len(tokens) >= 2 and tokens[1].lower() == "order":
                if len(tokens) != 3:
                    raise ValueError("Uso: cancel order <id>")
                try:
                    order_id = int(tokens[2])
                except ValueError:
                    raise ValueError(f"ID da ordem deve ser inteiro, recebido: '{tokens[2]}'")

                cancelled = self.manager.cancel_order(order_id)
                if cancelled is not None:
                    return ["Order cancelled"]
                return ["Error: order not found"]

            # 6. Comando modify order <id> [price=<p>] [qty=<q>]
            if cmd == "modify" and len(tokens) >= 2 and tokens[1].lower() == "order":
                if len(tokens) < 4:
                    raise ValueError("Uso: modify order <id> price=<p> qty=<q>")
                try:
                    order_id = int(tokens[2])
                except ValueError:
                    raise ValueError(f"ID da ordem deve ser inteiro, recebido: '{tokens[2]}'")

                new_price: Optional[Decimal] = None
                new_qty: Optional[int] = None

                for param in tokens[3:]:
                    if param.lower().startswith("price="):
                        val_str = param.split("=", 1)[1]
                        new_price = self._parse_price(val_str)
                    elif param.lower().startswith("qty="):
                        val_str = param.split("=", 1)[1]
                        new_qty = self._parse_qty(val_str)
                    else:
                        raise ValueError(f"Parâmetro de alteração não reconhecido: '{param}'")

                if new_price is None and new_qty is None:
                    raise ValueError("Informe pelo menos 'price=' ou 'qty=' para alteração")

                try:
                    _, trades = self.manager.modify_order(
                        order_id, new_price=new_price, new_qty=new_qty
                    )
                except ValueError as err:
                    if "não encontrada" in str(err).lower():
                        return ["Error: order not found"]
                    raise err

                output_lines: List[str] = [
                    f"Trade, price: {format_price(t.price)}, qty: {t.qty}" for t in trades
                ]
                output_lines.append("Order modified")
                return output_lines

            # Comando desconhecido
            return [f"Error: comando não reconhecido '{cmd}'"]

        except Exception as exc:
            return [f"Error: {exc}"]

