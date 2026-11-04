# Testes unitários — PrevClima

## 1. Objetivo e escopo

Este documento descreve seis cenários de teste unitário escolhidos no código do
projeto. Os testes verificam regras de interpretação de dados meteorológicos e
de localização geográfica. Eles executam as funções diretamente, com dados de
entrada definidos no próprio teste, sem depender de banco de dados, rede ou da
disponibilidade da API do INMET. Assim, resultados reais de provedores externos
e o funcionamento integrado da aplicação não são demonstrados por esta entrega.

O código está em [`tests/test_scenarios_unit.py`](../tests/test_scenarios_unit.py).
As funções testadas ficam em `app/integrations/stations.py` e
`app/routers/weather.py`.

## 2. Cenários escolhidos

| Nº | Função testada | Situação e entradas | Resultado esperado e justificativa |
|---|---|---|---|
| 1 | `number` | Um número com vírgula decimal, o marcador de dado ausente `-9999`, `NaN`, um valor fora do limite e zero. | Converte `23,5` para `23.5`; descarta dados ausentes, não finitos e fora do intervalo; preserva zero. Evita interpretar dados inválidos como medições reais. |
| 2 | `station` | Código e estado em minúsculas, latitude fora do intervalo e, em seguida, um código inválido. | Normaliza código e estado para maiúsculas, classifica a estação, descarta latitude inválida e rejeita o código inválido. Protege a identificação e os dados geográficos da estação. |
| 3 | `observation` | Registro INMET com data, hora `1300`, temperatura com vírgula e chuva zero. | Produz data e hora em UTC, temperatura decimal e precipitação igual a zero, associadas à estação correta. Confirma que ausência de chuva não é tratada como dado ausente. |
| 4 | `parse_import` | CSV histórico com uma linha válida e outra com data inválida. | Importa a linha válida, informa uma linha ignorada, mantém chuva zero e identifica a origem como BDMEP. Evita perder todas as observações por causa de uma linha incorreta. |
| 5 | `point_in_polygon` | Pontos dentro, na borda e fora de um polígono, além de um ponto no interior de um buraco. | Considera interior e borda externa como pertencentes à área, mas exclui o interior do buraco e pontos externos. Isso sustenta a seleção de avisos por área. |
| 6 | `distance_km` | A mesma coordenada e o trajeto Brasília–São Paulo nos dois sentidos. | Retorna zero para pontos iguais, distância aproximada de 870 km para o trajeto e o mesmo resultado nos dois sentidos. Verifica a consistência do cálculo de distância. |

## 3. Código, execução e evidência

Requisitos: Python 3.11 ou superior e dependências de desenvolvimento do
projeto. Na raiz do repositório, execute:

```powershell
python -m pip install -e '.[dev]'
python -m pytest tests/test_scenarios_unit.py -v --junitxml=docs/evidencias/minha-execucao.xml
```

O comando mostra o resultado de cada cenário e gera um arquivo XML no formato
JUnit. Os arquivos de evidência desta entrega foram gerados em **03/11/2026**,
em Windows, com Python 3.12.14 e pytest 8.4.2:

- Primeira execução: [saída do terminal](evidencias/testes-unitarios.txt) e
  [resultado JUnit XML](evidencias/testes-unitarios.xml).
- Confirmação após ajuste de formatação do código: [saída do terminal](evidencias/testes-unitarios-confirmacao.txt)
  e [resultado JUnit XML](evidencias/testes-unitarios-confirmacao.xml).

As duas execuções registraram **6 testes aprovados, 0 falhas e 0 erros**. O
pytest também exibiu um aviso de descontinuação de uma dependência do ambiente;
esse aviso não impediu a execução dos testes.

## 4. Relatório de execuções

A tabela registra as execuções locais realizadas para esta entrega. Cada teste
passou na primeira tentativa; uma segunda execução confirmou o resultado após
um ajuste apenas de formatação. Execuções posteriores em CI ou por outras
pessoas não estão incluídas nessa contagem.

| Função testada | Execuções até o primeiro sucesso | Execuções locais registradas | Resultado final |
|---|---:|---:|---|
| `number` | 1 | 2 | Sucesso |
| `station` | 1 | 2 | Sucesso |
| `observation` | 1 | 2 | Sucesso |
| `parse_import` | 1 | 2 | Sucesso |
| `point_in_polygon` | 1 | 2 | Sucesso |
| `distance_km` | 1 | 2 | Sucesso |

Esses resultados se referem aos dados e casos listados acima; não representam
uma garantia de que todos os cenários possíveis estejam cobertos.
