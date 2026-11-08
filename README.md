# PrevClima

Aplicação web, PWA móvel para navegadores compatíveis e API FastAPI para a plataforma de
avisos meteorológicos do TCC. O projeto usa MySQL no Docker e SQLite como opção
leve de desenvolvimento.

## Recursos concluídos

- Site responsivo em português do Brasil.
- Cadastro público sempre com a função `USER`, confirmado por código enviado ao e-mail.
- Dois níveis de acesso: usuário e meteorologista.
- Aplicativo móvel instalável em `/mobile/` e aplicativo Expo, exclusivos para contas `USER`.
- Sessão por cookie `HttpOnly`, proteção CSRF, senha Argon2 e revogação de sessão.
- Perfil, preferências, localização, previsão, avisos, mapa e conteúdo educativo conectados ao banco.
- Previsão atual e diária obtida do Open-Meteo, com geocodificação de cidades,
  cache de 15 minutos e fallback para o último dado salvo.
- Mapa baseado no OpenStreetMap com previsões, alertas e avisos oficiais do INMET.
- Meteorologista: emissão de previsões e alertas, consulta às estações do INMET,
  importação BDMEP e gestão de contas, com histórico de auditoria.
- Origem identificada em cada aviso: `MANUAL` ou `INMET`.

## Aplicativo React Native

O aplicativo nativo fica em `../prevclima-app` (Expo). Ele usa esta mesma API e o mesmo
banco de dados; não há backend separado. O login `POST /api/v1/auth/login-mobile` devolve
`access_token`, enviado pelo app em `Authorization: Bearer`. Para o celular acessar a API,
defina `PREVCLIMA_BIND=0.0.0.0` no `.env`. Instruções em `../prevclima-app/README.md`.

## Iniciar no Windows 11 com Docker

Requisitos: Git e Docker Desktop em execução.

```powershell
git clone https://github.com/iminvencible/TCC-backend.git
cd TCC-backend
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File .\iniciar-prevclima.ps1
```

O inicializador procura uma porta livre entre `18080` e `18090`. Se todas estiverem
ocupadas, solicita ao Windows uma porta livre, inicia os contêineres, aguarda
`/api/health` e abre o navegador. A escolha não remove volumes nem dados.

Para iniciar manualmente:

```powershell
docker compose up --build
Start-Process "http://127.0.0.1:18080"
```

Altere `PREVCLIMA_PORT` no arquivo `.env` se quiser escolher outra porta. O MySQL
não publica porta no computador: ele usa apenas a rede interna do Docker, portanto
uma porta local `3306` ou `3006` ocupada não interfere no projeto.

Endereços com a porta escolhida:

- Site: `http://127.0.0.1:PORTA/`
- Aplicativo móvel: `http://127.0.0.1:PORTA/mobile/`
- Documentação da API: `http://127.0.0.1:PORTA/docs`
- Estado da aplicação: `http://127.0.0.1:PORTA/api/health`

## Iniciar com dados reais

Não há contas nem dados meteorológicos de demonstração. Crie a conta principal do dono
com o nível de meteorologista:

```bash
docker compose exec api python -m app.create_owner
```

Sem Docker, após as migrações, execute `python -m app.seed` e `python -m app.create_owner`.
Outra opção é preencher `OWNER_EMAIL` e `OWNER_PASSWORD` no `.env` antes do seed.
Entre pela aba Profissional e credencie os demais meteorologistas em Usuários e equipe.

Para enviar os e-mails de confirmação e de nova senha, preencha `SMTP_HOST`, `SMTP_FROM` e
as credenciais no `.env`. Sem SMTP, em desenvolvimento, o código aparece no log do servidor;
em produção o SMTP é obrigatório.

## Open-Meteo e INMET

O Open-Meteo fornece as condições atuais, temperaturas mínima e máxima, umidade,
vento e chance de chuva. A consulta é feita automaticamente quando a tela inicial
ou `/api/v1/forecasts/current` solicita uma localidade sem cache recente. Não é
necessária chave de API.

O resultado é armazenado no banco por 15 minutos. Se o serviço ficar temporariamente
indisponível, o PrevClima pode exibir por até 24 horas o último resultado salvo,
identificado na interface como tal. A fonte e o link de atribuição permanecem
visíveis no site e no aplicativo móvel.

Variáveis do Open-Meteo:

| Variável | Finalidade |
| --- | --- |
| `OPEN_METEO_ENABLED` | Habilita a previsão automática |
| `OPEN_METEO_API_URL` | Endpoint de previsão |
| `OPEN_METEO_GEOCODING_URL` | Conversão de cidade/UF em coordenadas |
| `OPEN_METEO_TIMEOUT_SECONDS` | Limite de espera |
| `OPEN_METEO_MAX_RESPONSE_BYTES` | Tamanho máximo aceito |
| `OPEN_METEO_CACHE_MINUTES` | Validade do cache recente |
| `OPEN_METEO_STALE_HOURS` | Janela máxima do fallback salvo |

O INMET continua sendo a fonte oficial dos avisos meteorológicos brasileiros. Um
processo separado (`inmet-worker`) consulta o RSS oficial assim que a API estiver
pronta e repete a consulta a cada 60 minutos, por padrão:

`https://apiprevmet3.inmet.gov.br/avisos/rss`

O RSS oficial é um índice: cada item aponta para um documento CAP em
`https://apiprevmet3.inmet.gov.br/avisos/rss/{id}`. O importador segue esses links
restritos e obtém geometria, validade com fuso horário, instruções e cancelamentos
do CAP. O resumo HTML do RSS não é tratado como aviso: foi observado um item com
resumo “Alert” cujo CAP era “Cancel”. Mensagens de teste e de circulação restrita
continuam excluídas.

A integração valida domínio e HTTPS, limita transferência e tempo de resposta, faz
importação idempotente e mantém disponíveis os avisos já armazenados quando o INMET
está indisponível. Os avisos expiram pelo prazo indicado pela fonte; dados salvos não
significam que um aviso expirado seja exibido como ativo. Avisos sem polígono
parseável são preservados como informação textual e não recebem área inventada.

As previsões continuam vindo do Open-Meteo. Observações de estações são consultadas
separadamente no host oficial `https://apitempo.inmet.gov.br`, pelas rotas
`/estacoes/T` e `/estacao/{inicio}/{fim}/{codigo}`. Esses endpoints não possuem um
contrato de disponibilidade garantido pelo projeto: falhas retornam 503 e preservam
o histórico. Medições observadas não são apresentadas como previsão.

Variáveis disponíveis:

| Variável | Finalidade |
| --- | --- |
| `INMET_ENABLED` | Habilita sincronização automática e manual (`true` por padrão no Compose) |
| `INMET_WARNING_RSS_URL` | Endereço oficial do RSS |
| `INMET_TIMEOUT_SECONDS` | Limite de espera da consulta |
| `INMET_MAX_RESPONSE_BYTES` | Tamanho máximo aceito |
| `INMET_SYNC_INTERVAL_MINUTES` | Intervalo em minutos entre tentativas (10–1440; padrão 60) |

O painel do meteorologista continua oferecendo sincronização sob demanda. A linha de
comando também executa uma única tentativa:

```bash
python -m app.sync_inmet
```

Para verificar o processo automático no Docker: `docker compose logs -f inmet-worker`.
O documento CAP pode conter avisos sem polígono. Nesses casos, a página do mapa mostra
o aviso em texto, sem gerar uma área fictícia. Se não houver áreas compatíveis e
vigentes, o mapa não terá polígonos do INMET para mostrar.
A consulta aceita até 100 links CAP, com quatro transferências simultâneas, limite
por documento e limite total de cinco vezes `INMET_MAX_RESPONSE_BYTES`. Falha em
qualquer documento preserva o conjunto salvo e registra uma tentativa indisponível;
nenhum resumo incompleto é publicado. Cancelamentos são processados depois dos
avisos que podem referenciar.

A tela inicial, o mapa público e o mapa do painel mostram a situação do INMET:
aguardando, atualizado, atrasado, indisponível ou desativado, com a última consulta
concluída. O mapa oferece busca pública por cidade/UF, GPS autenticado, lista de
avisos, camadas independentes e atualização a cada cinco minutos enquanto visível.
As previsões diárias usam o fuso da localidade (`timezone=auto`).

Verificação em 26/10/2026: consultas reais pelo endpoint `/api/v1/map-data` para
Mongaguá/SP e Recife/PE; sincronização do RSS e dos CAP com 32 avisos importados com
polígonos, 42 itens ignorados/cancelamentos e dois avisos vigentes no momento da
consulta. Esses números são um registro da verificação, não valores fixos da aplicação.
O INMET também retornou 503 em tentativas anteriores; a integração continua
sujeita à disponibilidade da fonte. O histórico de estações é uma integração
separada e ainda depende da configuração e disponibilidade descritas abaixo.

## Banco de dados

O [MER](database/MER.md) documenta entidades, cardinalidades, chaves, unidades e
regras de integridade. A revisão `3b6f82078bcf` acrescenta `weather_stations` e
`station_observations`, sem remover contas, previsões ou avisos existentes.

- `migrations/` é a fonte executável e versionada do esquema.
- A revisão `c7d3f1a90e22` unifica os perfis profissionais, remove dados demonstrativos
  e cria as previsões de tempo severo e os códigos enviados por e-mail.
- A revisão `4a8c1e7d2b90` adiciona o link de atribuição da fonte às previsões.
- A revisão `5f0e7c29b4a1` guarda coordenadas das previsões e permite avisos
  oficiais do INMET sem geometria, preservando-os como informação textual.
- `banco tcc.sql` e `database/schema.mysql.sql` documentam a estrutura MySQL.
- `python -m app.seed` cria as funções, o conteúdo educativo e, se `OWNER_EMAIL` e
  `OWNER_PASSWORD` estiverem definidos, a conta principal.

## Painel conectado e importação INMET

`/painel.html` (também `/profissional.html`; `/meteorologista.html`
redireciona para ele) é a central meteorológica, com login próprio. Arquivos:
`public/painel.html`, `public/assets/css/painel.css` e `public/assets/js/painel/painel.js`.
O servidor preenche a chave do MapTiler (`MAPTILER_KEY`; sem chave, o mapa usa o
OpenFreeMap) e a logo, se existir `public/assets/img/logo.png`. A página tem uma
política de segurança (CSP) própria, que libera o MapLibre, as fontes, o mapa base e o INMET.

Tudo que a central mostra vem do banco pela rota `GET /api/v1/panel/state`. Previsões
(`/panel/forecasts`) podem ser editadas ou excluídas por 30 minutos após a emissão; alertas
(`POST /panel/alerts`, tipos tempestade severa e tornado) não podem ser editados nem excluídos.
Qualquer meteorologista busca, edita, promove e desativa contas em `/panel/accounts` e
credencia colegas em `/panel/meteorologists`. Avisos oficiais continuam vindo do INMET.

| Rota | Operação |
| --- | --- |
| `GET /api/v1/dashboard` | Contadores e atividade real; acesso profissional |
| `GET /api/v1/stations` | Catálogo; filtros `state`, `search`, `limit`, `offset` |
| `POST /api/v1/stations/sync-catalog` | Atualizar catálogo oficial; meteorologista |
| `POST /api/v1/stations/{code}/sync` | Consultar intervalo `{start, end}` de até 31 dias |
| `GET /api/v1/stations/{code}/observations` | Histórico; filtros `start`, `end`, `period`, `limit`, `offset` |
| `POST /api/v1/stations/import` | Importação autenticada de histórico (até 2 MB e 10.000 linhas) |

Configure `INMET_OBSERVATIONS_ENABLED=true` para consultas remotas. O serviço
`station-worker` consulta a lista JSON `INMET_STATION_CODES` no intervalo de
`INMET_SYNC_INTERVAL_MINUTES`. Uma lista vazia não faz consultas; selecione apenas
as estações monitoradas. Fora do Docker, execute `python -m app.sync_stations --loop`.

Os dois projetos solicitados foram usados como referências de compatibilidade:

- [Felipeandradee/INMET-API-REST](https://github.com/Felipeandradee/INMET-API-REST):
  salve a lista retornada por `ScrapperINMET.get_dados()` como JSON e selecione
  **INMET-API-REST · JSON** no painel.
- [fabinhojorge/INMET-API-temperature](https://github.com/fabinhojorge/INMET-API-temperature):
  importe o CSV separado por ponto e vírgula com `CodigoOMM`, `Data`, `Hora` e
  medidas. Selecione **Horário / DAYFULL**, **Diário** ou **Mensal** conforme o
  conteúdo. As amostras DAYFULL e MONTH do projeto são compatíveis.

Esses projetos extraem dados históricos do BDMEP e usam fluxos antigos de login e
scraping. O PrevClima não executa o ChromeDriver antigo nem armazena credenciais
BDMEP; importa seus resultados por adaptadores próprios. `-9999`, campos vazios e
valores fora da faixa viram `null`; zero de chuva continua sendo zero. Reimportar
a mesma estação, horário UTC e período atualiza a medição sem duplicá-la. A origem
`BDMEP` e a data original permanecem visíveis. Vento medido usa m/s; previsões
existentes usam km/h e mantêm seu próprio contrato.

Validação desta revisão: sincronização real de 672 estações pelo painel; parsing
de 4.633 registros DAYFULL e 3.847 mensais dos exemplos do projeto de temperatura;
respostas de medições, idempotência e indisponibilidade cobertas por testes.
O endpoint de medições não respondeu com dados válidos na consulta ao vivo deste
ambiente. Uma sincronização de medições ao vivo ainda precisa ser verificada na
rede de implantação. Consulte `docker compose logs station-worker inmet-worker`.

Para desenvolvimento sem Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export OPEN_METEO_ENABLED=true INMET_ENABLED=true
alembic upgrade head
uvicorn app.main:app --reload
```

Em outro terminal, no mesmo diretório e com o ambiente ativado, execute
`python -m app.sync_inmet --loop` para sincronizar o INMET também na instalação
sem Docker. No PowerShell, use `py -m venv .venv` e
`.\.venv\Scripts\Activate.ps1` no lugar das duas primeiras linhas; instale as
dependências e defina `$env:OPEN_METEO_ENABLED = "true"` e
`$env:INMET_ENABLED = "true"` antes de iniciar os processos.

## Verificação

```bash
ruff format --check app migrations tests
ruff check app migrations tests
pytest -q
node --test tests/*.test.cjs
find public -name '*.js' -print0 | xargs -0 -n1 node --check
```

As migrações também são verificadas em um banco novo. O fluxo automatizado do
GitHub executa os testes gerais e uma migração real em MySQL.
