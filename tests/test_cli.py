from src.engine.order_manager import OrderManager
from src.interface.command_parser import CommandParser


def setup_cli() -> CommandParser:
    return CommandParser(OrderManager())


def filter_trades(lines: list[str]) -> list[str]:
    """Filtra apenas as linhas de Trade para comparação de execuções."""
    return [line for line in lines if line.startswith("Trade,")]


def test_matching_trades_execution_flow():
    """
    Valida o fluxo completo de submissão de ordens limites e consumo agressivo por ordens a mercado:
    - Inserção de compra 100 @ 10
    - Inserção de vendas 100 @ 20 e 200 @ 20
    - Compra a mercado de 150 -> gera trade agregado: 150 @ 20
    - Compra a mercado de 200 -> gera trade agregado: 150 @ 20
    - Venda a mercado de 200 -> gera trade agregado: 100 @ 10
    """
    cli = setup_cli()

    cli.parse_and_execute("limit buy 10 100")
    cli.parse_and_execute("limit sell 20 100")
    cli.parse_and_execute("limit sell 20 200")

    # Compra a mercado de 150
    out1 = cli.parse_and_execute("market buy 150")
    assert filter_trades(out1) == ["Trade, price: 20, qty: 150"]

    # Compra a mercado de 200 (havia 150 remanescentes a 20)
    out2 = cli.parse_and_execute("market buy 200")
    assert filter_trades(out2) == ["Trade, price: 20, qty: 150"]

    # Venda a mercado de 200 (havia 100 a 10 na compra)
    out3 = cli.parse_and_execute("market sell 200")
    assert filter_trades(out3) == ["Trade, price: 10, qty: 100"]


def test_order_cancellation_flow():
    """Valida a criação de ordem e cancelamento pelo ID numérico."""
    cli = setup_cli()

    out_create = cli.parse_and_execute("limit buy 10 100")
    assert out_create[-1] == "Order created: buy 100 @ 10 1"

    out_cancel = cli.parse_and_execute("cancel order 1")
    assert out_cancel == ["Order cancelled"]

    # Cancelar novamente retorna erro de ordem não encontrada
    out_cancel_again = cli.parse_and_execute("cancel order 1")
    assert out_cancel_again == ["Error: order not found"]


def test_order_modification_and_book_presentation():
    """
    Valida a alteração de ordem e a visualização do livro de ofertas:
    - Monta livro com compras 200 @ 10 e 100 @ 9.99 | venda 100 @ 10.5
    - Altera a ordem de 200 para o preço de 9.98
    - Verifica a perda de prioridade na tabela do livro
    """
    cli = setup_cli()

    cli.parse_and_execute("limit buy 10 200")    # id 1
    cli.parse_and_execute("limit buy 9.99 100")  # id 2
    cli.parse_and_execute("limit sell 10.5 100") # id 3

    # Altera o preço da ordem 1 para 9.98
    out_modify = cli.parse_and_execute("modify order 1 price=9.98")
    assert out_modify == ["Order modified"]

    # Visualiza o livro de ofertas
    out_book = cli.parse_and_execute("print book")
    expected_table = (
        "Ordens de Compra    | Ordens de Venda\n"
        "--------------------|-----------------\n"
        "100 @ 9.99          | 100 @ 10.5\n"
        "200 @ 9.98          |"
    )
    assert out_book == [expected_table]


def test_pegged_order_repricing_and_priority_in_book():
    """
    Valida a ordem pegged acompanhando dinamicamente o melhor preço de compra:
    - Livro inicial com compras 200 @ 10 e 100 @ 9.99 | venda 100 @ 10.5
    - Entra ordem pegged de compra 150 (assume 10)
    - Entra nova ordem limite de compra 300 @ 10.1 (novo topo)
    - Ordem pegged move para 10.1 e fica à frente da ordem de 300 na tabela
    """
    cli = setup_cli()

    cli.parse_and_execute("limit buy 10 200")    # id 1
    cli.parse_and_execute("limit buy 9.99 100")  # id 2
    cli.parse_and_execute("limit sell 10.5 100") # id 3

    # Entra ordem pegged
    out_peg = cli.parse_and_execute("peg bid buy 150") # id 4
    assert out_peg == ["Order created: buy 150 @ 10 4"]

    # Entra nova ordem limite no topo: 300 @ 10.1
    cli.parse_and_execute("limit buy 10.1 300")  # id 5

    out_book = cli.parse_and_execute("print book")
    expected_table = (
        "Ordens de Compra    | Ordens de Venda\n"
        "--------------------|-----------------\n"
        "150 @ 10.1          | 100 @ 10.5\n"
        "300 @ 10.1          |\n"
        "200 @ 10            |\n"
        "100 @ 9.99          |"
    )
    assert out_book == [expected_table]


def test_print_empty_book():
    """Valida a exibição do livro quando 100% vazio."""
    cli = setup_cli()
    out = cli.parse_and_execute("print book")
    expected = (
        "Ordens de Compra    | Ordens de Venda\n"
        "--------------------|-----------------"
    )
    assert out == [expected]


def test_invalid_commands_and_inputs_do_not_crash_loop():
    """Valida tratamento defensivo de erros em entradas incorretas."""
    cli = setup_cli()

    # Comando desconhecido
    out1 = cli.parse_and_execute("foobar 123")
    assert out1[0].startswith("Error: comando não reconhecido")

    # Preço inválido (NaN, Infinity, texto, negativo)
    out2 = cli.parse_and_execute("limit buy nan 100")
    assert out2[0].startswith("Error: Preço deve ser um número positivo finito")

    out3 = cli.parse_and_execute("limit buy inf 100")
    assert out3[0].startswith("Error: Preço deve ser um número positivo finito")

    out4 = cli.parse_and_execute("limit buy abc 100")
    assert out4[0].startswith("Error: Preço inválido")

    out5 = cli.parse_and_execute("limit buy -10 100")
    assert out5[0].startswith("Error: Preço deve ser um número positivo finito")

    # Quantidade inválida (não inteira, negativa, zero)
    out6 = cli.parse_and_execute("limit buy 10.5 10.5")
    assert out6[0].startswith("Error: Quantidade deve ser um número inteiro")

    out7 = cli.parse_and_execute("limit buy 10 0")
    assert out7[0].startswith("Error: Quantidade deve ser estritamente positiva")

    # O parser continua ativo e funcional após os erros
    valid_out = cli.parse_and_execute("limit buy 10 100")
    assert valid_out[-1] == "Order created: buy 100 @ 10 1"


def test_cancel_nonexistent_order_error():
    """Valida tentativa de cancelar ordem inexistente."""
    cli = setup_cli()
    out = cli.parse_and_execute("cancel order 999")
    assert out == ["Error: order not found"]


def test_peg_without_reference_error():
    """Valida tentativa de criar ordem pegged sem ordens de referência no livro."""
    cli = setup_cli()
    out = cli.parse_and_execute("peg bid buy 100")
    assert out[0].startswith("Error: Não há ordens de referência não-pegged")
