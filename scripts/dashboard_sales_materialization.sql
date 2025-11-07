-- Materialization layer for dashboard sales aggregates
-- This script creates analytics objects that can be refreshed via cron or webhooks.

create schema if not exists analytics;

create materialized view if not exists analytics.mv_dashboard_sales_daily as
with detalle as (
    select
        v.negocio_id,
        date_trunc('day', v.fecha)::date as dia,
        sum(vd.subtotal) as total_bruto,
        sum(
            case
                when vd.producto_id is not null then vd.cantidad * coalesce(p.precio_compra, 0)
                when vd.servicio_id is not null then coalesce(s.costo, 0) * greatest(vd.cantidad, 1)
                else 0
            end
        ) as costo_total,
        count(distinct v.cliente_id) filter (where v.cliente_id is not null) as clientes_unicos,
        count(distinct v.id) as total_ventas
    from ventas v
    join venta_detalle vd on vd.venta_id = v.id
    left join productos p on p.id = vd.producto_id
    left join servicios s on s.id = vd.servicio_id
    group by v.negocio_id, date_trunc('day', v.fecha)
)
select
    negocio_id,
    dia,
    total_bruto,
    costo_total,
    total_bruto - costo_total as ganancia,
    clientes_unicos,
    total_ventas
from detalle;

create unique index if not exists idx_mv_dashboard_sales_daily_pk
    on analytics.mv_dashboard_sales_daily (negocio_id, dia);

comment on materialized view analytics.mv_dashboard_sales_daily is
    'Aggregated totals per business/day for dashboard KPIs.';

create or replace function analytics.refresh_dashboard_sales_daily()
returns void
language plpgsql
as $$
declare
    got_lock boolean;
begin
    got_lock := pg_try_advisory_lock(94124, 1);
    if not got_lock then
        raise notice 'Skipping refresh_dashboard_sales_daily because another session holds the lock';
        return;
    end if;

    begin
        refresh materialized view concurrently analytics.mv_dashboard_sales_daily;
    exception when others then
        perform pg_advisory_unlock(94124, 1);
        raise;
    end;

    perform pg_advisory_unlock(94124, 1);
end;
$$;

create or replace function public.dashboard_sales_window(
    p_negocio_id uuid,
    p_since date default (current_date - interval '90 days'),
    p_until date default current_date,
    p_limit integer default 30,
    p_offset integer default 0
)
returns table (
    dia date,
    total numeric,
    costo numeric,
    ganancia numeric,
    clientes integer,
    total_ventas integer
)
language sql
stable
as $$
    select
        dia,
        total_bruto,
        costo_total,
        ganancia,
        clientes_unicos,
        total_ventas
    from analytics.mv_dashboard_sales_daily
    where negocio_id = p_negocio_id
      and dia between p_since and p_until
    order by dia desc
    limit greatest(p_limit, 1)
    offset greatest(p_offset, 0);
$$;

comment on function public.dashboard_sales_window(uuid, date, date, integer, integer) is
    'Windowed access to dashboard sales aggregates with pagination.';

-- Recommended pg_cron job (run every 15 minutes)
-- select cron.schedule(
--     'refresh-dashboard-sales',
--     '*/15 * * * *',
--     $$select analytics.refresh_dashboard_sales_daily();$$
-- );
