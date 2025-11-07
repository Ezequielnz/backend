-- Cached financial metrics with streaming-friendly chunks.

create schema if not exists analytics;

create table if not exists analytics.finance_metrics_cache (
    negocio_id uuid not null,
    periodo text not null,
    updated_at timestamptz not null default now(),
    payload jsonb not null,
    primary key (negocio_id, periodo)
);

comment on table analytics.finance_metrics_cache is
    'Stores precomputed finance stats (cashflow, accounts receivable/payable, KPIs).';

create or replace function analytics.refresh_finance_metrics_cache(
    p_negocio_id uuid,
    p_window interval default interval '30 days'
)
returns void
language plpgsql
as $$
declare
    desde timestamptz := now() - p_window;
    hasta timestamptz := now();
    payload jsonb;
begin
    with pagos as (
        select sum(monto) as cobranzas
        from pagos
        where negocio_id = p_negocio_id
          and fecha between desde and hasta
    ),
    compras as (
        select sum(total) as egresos
        from compras
        where negocio_id = p_negocio_id
          and fecha between desde and hasta
    ),
    cuentas as (
        select
            sum(case when estado = 'pendiente' then total else 0 end) as cuentas_pendientes,
            sum(case when estado = 'atrasado' then total else 0 end) as cuentas_atrasadas
        from cuentas_por_cobrar
        where negocio_id = p_negocio_id
    ),
    flujo as (
        select
            coalesce((select cobranzas from pagos), 0) -
            coalesce((select egresos from compras), 0) as flujo_neto
    )
    select jsonb_build_object(
        'desde', desde,
        'hasta', hasta,
        'cobranzas', coalesce((select cobranzas from pagos), 0),
        'egresos', coalesce((select egresos from compras), 0),
        'flujo_neto', (select flujo_neto from flujo),
        'cuentas_pendientes', coalesce((select cuentas_pendientes from cuentas), 0),
        'cuentas_atrasadas', coalesce((select cuentas_atrasadas from cuentas), 0)
    )
    into payload;

    insert into analytics.finance_metrics_cache (negocio_id, periodo, payload, updated_at)
    values (p_negocio_id, concat(date(desde), '_', date(hasta)), payload, now())
    on conflict (negocio_id, periodo) do update
        set payload = excluded.payload,
            updated_at = now();
end;
$$;

create or replace function analytics.stream_finance_metrics(
    p_negocio_id uuid,
    p_cursor timestamptz default null,
    p_limit integer default 5
)
returns table (
    periodo text,
    updated_at timestamptz,
    payload jsonb
)
language sql
stable
as $$
    select
        periodo,
        updated_at,
        payload
    from analytics.finance_metrics_cache
    where negocio_id = p_negocio_id
      and (p_cursor is null or updated_at < p_cursor)
    order by updated_at desc
    limit greatest(p_limit, 1);
$$;

comment on function analytics.stream_finance_metrics(uuid, timestamptz, integer) is
    'Returns cached finance summaries in descending order so the API can stream partial chunks.';

-- Example cron jobs
-- select cron.schedule(
--   'refresh-finance-cache',
--   '*/10 * * * *',
--   $$select analytics.refresh_finance_metrics_cache(id)
--     from negocios where activo = true;$$
-- );
