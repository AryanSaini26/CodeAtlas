create table marts.customer_ltv as
select
  c.id as customer_id,
  sum(o.total) as lifetime_value
from raw.customers c
join marts.orders o on o.customer_id = c.id
group by c.id;
