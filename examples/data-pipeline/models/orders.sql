create table marts.orders as
select
  id,
  customer_id,
  total,
  created_at
from raw.orders;
