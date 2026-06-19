# CodeAtlas Data Lineage

- Nodes: 14
- Edges: 11

## Nodes
- `airflow:dag:daily_orders` (airflow_dag)
- `airflow:task:build_customer_ltv` (airflow_task)
- `airflow:task:extract_orders` (airflow_task)
- `dbt:exposure:exec_dashboard` (dbt_exposure)
- `dbt:model:customer_ltv` (dbt_model)
- `dbt:model:orders` (dbt_model)
- `dbt:source:raw_customers` (dbt_source)
- `dbt:source:raw_orders` (dbt_source)
- `sql:query:models/customer_ltv.sql` (sql_query)
- `sql:query:models/orders.sql` (sql_query)
- `sql:table:marts.customer_ltv` (sql_table)
- `sql:table:marts.orders` (sql_table)
- `sql:table:raw.customers` (sql_table)
- `sql:table:raw.orders` (sql_table)

## Edges
- `airflow:dag:daily_orders` --contains--> `airflow:task:build_customer_ltv`
- `airflow:dag:daily_orders` --contains--> `airflow:task:extract_orders`
- `dbt:model:customer_ltv` --depends_on--> `dbt:exposure:exec_dashboard`
- `dbt:model:orders` --depends_on--> `dbt:model:customer_ltv`
- `dbt:source:raw_customers` --depends_on--> `dbt:model:customer_ltv`
- `dbt:source:raw_orders` --depends_on--> `dbt:model:orders`
- `sql:query:models/customer_ltv.sql` --writes--> `sql:table:marts.customer_ltv`
- `sql:query:models/orders.sql` --writes--> `sql:table:marts.orders`
- `sql:table:marts.orders` --reads--> `sql:query:models/customer_ltv.sql`
- `sql:table:raw.customers` --reads--> `sql:query:models/customer_ltv.sql`
- `sql:table:raw.orders` --reads--> `sql:query:models/orders.sql`
