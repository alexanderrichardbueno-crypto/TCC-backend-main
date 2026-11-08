# Modelo Entidade-Relacionamento — PrevClima

O modelo separa identidade, comunicação meteorológica e dados medidos. As migrações Alembic são a fonte executável do esquema. A revisão `3b6f82078bcf` acrescenta estações e observações sem apagar dados existentes.

```mermaid
erDiagram
    roles ||--o{ users : autoriza
    users o|--o{ forecasts : publica
    users o|--o{ weather_alerts : emite
    users o|--o{ weather_alerts : altera_situacao
    users ||--o{ weather_reports : relata
    users o|--o{ weather_reports : revisa
    users ||--o{ alert_reviews : revisa
    weather_alerts ||--o{ alert_reviews : historico
    users ||--o{ alert_reads : le
    weather_alerts ||--o{ alert_reads : leitura
    users o|--o{ audit_events : executa
    users o|--o{ educational_contents : escreve
    users o|--o{ news : publica
    weather_stations ||--o{ station_observations : registra

    roles {
        int id PK
        varchar code UK
        varchar display_name
    }
    users {
        int id PK
        int role_id FK
        varchar public_code UK
        varchar email UK
        varchar password_hash
        boolean is_active
        int token_version
    }
    forecasts {
        int id PK
        int created_by FK
        varchar source_key UK
        varchar city
        varchar state
        decimal latitude
        decimal longitude
        decimal temperature_c
        datetime issued_at
        datetime valid_until
    }
    weather_alerts {
        int id PK
        int created_by FK
        int status_changed_by FK
        varchar source_key UK
        varchar origin
        varchar severity
        varchar validation_status
        json polygon
        datetime issued_at
        datetime valid_until
    }
    alert_reviews {
        int id PK
        int alert_id FK
        int reviewer_id FK
        varchar previous_status
        varchar new_status
        text reason
        datetime created_at
    }
    alert_reads {
        int id PK
        int user_id FK
        int alert_id FK
        datetime read_at
    }
    weather_reports {
        int id PK
        int reporter_id FK
        int reviewer_id FK
        text description
        varchar status
        datetime occurred_at
    }
    audit_events {
        int id PK
        int actor_id FK
        varchar action
        varchar target_type
        varchar target_id
        json details
        datetime created_at
    }
    educational_contents {
        int id PK
        int author_id FK
        varchar source_key UK
        varchar title
        text body
    }
    news {
        int id PK
        int author_id FK
        varchar title
        text body
    }
    weather_stations {
        varchar code PK
        varchar name
        varchar state
        varchar kind
        decimal latitude
        decimal longitude
        datetime updated_at
    }
    station_observations {
        int id PK
        varchar station_code FK
        datetime observed_at
        varchar period
        decimal temperature_c
        decimal minimum_c
        decimal maximum_c
        decimal humidity
        decimal precipitation_mm
        decimal wind_ms
        varchar source
        datetime imported_at
    }
```

## Regras e unidades

| Entidade | Regra |
|---|---|
| Estação | Código INMET/OMM único; metadados compartilhados por todas as medições. Coordenadas desconhecidas ficam nulas. |
| Observação | Chave natural única `(station_code, observed_at, period)`. Período `HOURLY`, `DAILY` ou `MONTHLY`; UTC no armazenamento e na API. |
| Medidas | Temperatura em °C, umidade em %, precipitação em mm e vento em m/s. Campo ausente ou sentinela `-9999` vira `NULL`, nunca zero. |
| Previsão | Produto previsto, separado da medição observada. A probabilidade de chuva não é inferida de precipitação medida. |
| Aviso | Origem `INMET` ou `MANUAL`; validade e situação de revisão independentes. |
| Revisão | Registra autor, motivo, situação anterior e nova. Não apaga o alerta. |
| Leitura | Restrição única `(user_id, alert_id)`. |
| Auditoria | `target_type` + `target_id` identificam vários tipos de entidade e não são uma chave estrangeira. |
| Conta | Desativação preserva histórico e revoga sessões via `token_version`. |

Os atributos do diagrama são os principais campos de cada entidade. O inventário completo, tipos, índices e restrições está em [schema.mysql.sql](schema.mysql.sql). O modelo usa tabelas relacionais para identidade e medições; JSON permanece apenas onde a estrutura é variável (geometrias, recomendações e detalhes de auditoria).

## Aplicação e reversão

Em uma cópia de desenvolvimento: `alembic upgrade head` e `alembic check`. Em um banco existente, faça backup e use a migração incremental. O SQL de criação completo é para bancos vazios. A reversão com `alembic downgrade 5f0e7c29b4a1` remove as duas novas tabelas e seus dados; não é necessária para atualizar.
