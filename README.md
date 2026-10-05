# Matching Engine

Uma **Matching Engine** desenvolvida em Python para um único ativo, operando 100% em memória volátil.

O projeto foi construído passo a passo seguindo boas práticas de arquitetura (SOLID), código limpo, precisão financeira e testes automatizados.

---

## 🎯 Como o Sistema Funciona

O sistema gerencia o livro de ofertas e executa negociações seguindo a regra de **Prioridade Preço-Tempo (FIFO)**:
1. **Melhor Preço Primeiro:** Na compra, quem paga mais tem prioridade; na venda, quem cobra menos tem prioridade.
2. **Tempo de Chegada:** Em caso de empate de preço, a ordem que chegou primeiro é executada primeiro.
3. **100% em Memória:** Não utiliza banco de dados. Todas as informações vivem na memória durante a execução.
4. **Precisão com `Decimal`:** Utiliza o tipo `Decimal` do Python para valores monetários, evitando erros de arredondamento comuns de ponto flutuante (`float`).
5. **Apenas Biblioteca Padrão:** Não requer nenhuma biblioteca externa para rodar (`main.py`). Apenas o `pytest` é usado para executar os testes.

---

## 🏗️ Estrutura do Código

O código está dividido em módulos simples e com responsabilidades claras:

```text
matching-engine/
├── main.py                          # Ponto de entrada do terminal interativo
├── DECISIONS.md                     # Justificativas das decisões tomadas
├── src/
│   ├── domain/
│   │   └── models.py                # Classes de dados: Order, Trade e Enums (Side, OrderType)
│   ├── engine/
│   │   ├── price_level.py           # Fila de ordens de um mesmo preço (FIFO por sequence)
│   │   ├── order_book.py            # Guarda compras e vendas e organiza os níveis de preço
│   │   ├── matching_engine.py       # Cruza compras com vendas e gera os trades
│   │   ├── peg_manager.py           # Gerencia ordens pegged e seu repique dinâmico
│   │   └── order_manager.py         # Coordena IDs, submissão, cancelamento e alteração
│   └── interface/
│       ├── book_presenter.py        # Formata o livro em duas colunas (Compra | Venda)
│       └── command_parser.py        # Valida comandos de texto e repassa para o sistema
└── tests/                           # Suíte de testes unitários e de integração
```

### O que cada parte faz:

* **`models.py`:** Define o que é uma `Order` (com ID numérico, preço `Decimal`, quantidade inteira e contador de prioridade) e o que é um `Trade`.
* **`price_level.py`:** Guarda todas as ordens de um mesmo preço em uma lista mantida ordenada pelo contador de criação (`sequence`).
* **`order_book.py`:** Mantém os lados de compra e venda organizados e permite consultar o melhor preço em tempo constante.
* **`matching_engine.py`:** Compara a ordem que chega com o topo do livro. Se houver cruzamento de preços, executa o trade pelo preço da ordem que já estava no livro (*maker*).
* **`peg_manager.py`:** Acompanha as ordens do tipo *pegged* (`peg bid buy` e `peg offer sell`). Quando o melhor preço muda, move a ordem pegged para o novo patamar mantendo sua prioridade original.
* **`order_manager.py`:** Gera os IDs sequenciais (`1, 2, 3...`), recebe os pedidos de compra/venda, cancela ordens e altera ordens ativas.
* **`command_parser.py`:** Lê o texto digitado pelo usuário, valida os dados (rejeitando números negativos, `NaN` ou textos inválidos) e formata a resposta.

---

## 📋 Comandos Disponíveis

| Comando | O que faz | Exemplo |
| :--- | :--- | :--- |
| `limit <buy\|sell> <preço> <qtd>` | Insere ordem limitada a um preço fixo | `limit buy 10 100` |
| `market <buy\|sell> <qtd>` | Compra ou vende imediatamente no melhor preço | `market buy 150` |
| `peg <bid\|offer> <buy\|sell> <qtd>` | Cria ordem que acompanha o melhor preço | `peg bid buy 150` |
| `cancel order <id>` | Cancela uma ordem ativa pelo seu identificador | `cancel order 1` |
| `modify order <id> price=<p> qty=<q>` | Altera o preço e/ou quantidade de uma ordem | `modify order 1 price=9.98` |
| `print book` | Imprime a tabela do livro de ofertas | `print book` |
| `exit` ou `quit` | Sai do programa | `exit` |

---

## 🚀 Como Executar

### Iniciar o programa no terminal
```bash
python main.py
```

---

## 🧪 Testes Automatizados

O projeto conta com **57 testes automatizados** utilizando `pytest`.

Para rodar todos os testes:
```bash
python -m pytest -v
```

---

## ⏱️ Complexidade das Operações (Notação Big-O)

Considerando $N$ como o número de ordens ativas no livro:

* **Buscar ou cancelar uma ordem por ID: $O(1)$**  
  Utiliza o dicionário nativo do Python (`dict`), que faz a busca por chave via tabela hash de forma direta.

* **Consultar o melhor preço (Best Bid / Best Ask): $O(1)$**  
  A lista interna de preços é mantida ordenada. O melhor preço é obtido imediatamente acessando a primeira ou última posição (`prices[0]` ou `prices[-1]`).

* **Inserir uma nova ordem: $O(\log N) + O(N)$**  
  * O Python usa busca binária (`bisect`) para encontrar a posição correta da ordem em **$O(\log N)$**.
  * Em seguida, insere o elemento na lista (`list.insert`), que no pior caso precisa deslocar elementos adjacentes em **$O(N)$**.

* **Casamento de ofertas (Matching):**  
  O tempo de execução é proporcional apenas à quantidade de ordens consumidas no topo do livro até preencher o volume solicitado.