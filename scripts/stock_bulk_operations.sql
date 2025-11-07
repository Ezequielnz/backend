-- Bulk stock adjustments for purchases and sales.
-- These routines unify stock updates in transactional batches.

create schema if not exists inventory;

create table if not exists inventory.stock_event_queue (
    id bigserial primary key,
    negocio_id uuid not null,
    item_id uuid not null,
    tipo text not null check (tipo in ('venta', 'compra', 'ajuste')),
    cantidad numeric not null,
    referencia uuid,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    processed_at timestamptz
);

create index if not exists idx_stock_event_queue_pending
    on inventory.stock_event_queue (negocio_id, processed_at nulls first, created_at)
    where processed_at is null;

create or replace function inventory.enqueue_stock_events(
    p_negocio_id uuid,
    p_events jsonb
)
returns integer
language plpgsql
as $$
declare
    ev jsonb;
    inserted integer := 0;
begin
    if p_events is null or jsonb_array_length(p_events) = 0 then
        return 0;
    end if;

    foreach ev in array select jsonb_array_elements(p_events)
    loop
        insert into inventory.stock_event_queue (
            negocio_id,
            item_id,
            tipo,
            cantidad,
            referencia,
            metadata
        )
        values (
            p_negocio_id,
            (ev->>'item_id')::uuid,
            coalesce(ev->>'tipo', 'ajuste'),
            coalesce((ev->>'cantidad')::numeric, 0),
            nullif(ev->>'referencia', '')::uuid,
            coalesce(ev->'metadata', '{}'::jsonb)
        );
        inserted := inserted + 1;
    end loop;
    return inserted;
end;
$$;

create or replace function inventory.apply_stock_queue(p_limit integer default 200)
returns integer
language plpgsql
as $$
declare
    updated integer := 0;
    rec record;
begin
    for rec in
        select *
        from inventory.stock_event_queue
        where processed_at is null
        order by created_at
        limit greatest(p_limit, 1)
        for update skip locked
    loop
        update productos
        set stock_actual = stock_actual + case rec.tipo when 'venta' then -rec.cantidad else rec.cantidad end,
            updated_at = now()
        where id = rec.item_id
          and negocio_id = rec.negocio_id;

        insert into productos_stock_historial (
            id,
            producto_id,
            negocio_id,
            tipo_movimiento,
            cantidad,
            metadata,
            creado_en
        )
        values (
            gen_random_uuid(),
            rec.item_id,
            rec.negocio_id,
            rec.tipo,
            rec.cantidad,
            rec.metadata,
            now()
        );

        update inventory.stock_event_queue
        set processed_at = now()
        where id = rec.id;

        updated := updated + 1;
    end loop;
    return updated;
end;
$$;

comment on function inventory.apply_stock_queue(integer) is
    'Consumes queued stock events to keep productos.stock_actual in sync.';

create or replace function inventory.apply_stock_batch(
    p_negocio_id uuid,
    p_batch jsonb,
    p_context text default 'ajuste_manual'
)
returns integer
language plpgsql
as $$
declare
    ev jsonb;
    processed integer := 0;
    delta numeric;
    tipo text;
begin
    foreach ev in array select jsonb_array_elements(p_batch)
    loop
        tipo := coalesce(ev->>'tipo', 'ajuste');
        delta := coalesce((ev->>'cantidad')::numeric, 0);
        if tipo = 'venta' then
            delta := -delta;
        end if;

        update productos
        set stock_actual = stock_actual + delta,
            updated_at = now()
        where id = (ev->>'item_id')::uuid
          and negocio_id = p_negocio_id;

        insert into productos_stock_historial (
            id,
            producto_id,
            negocio_id,
            tipo_movimiento,
            cantidad,
            metadata,
            creado_en
        )
        values (
            gen_random_uuid(),
            (ev->>'item_id')::uuid,
            p_negocio_id,
            tipo,
            abs(delta),
            jsonb_build_object(
                'context', p_context,
                'referencia', ev->>'referencia'
            ),
            now()
        );
        processed := processed + 1;
    end loop;
    return processed;
end;
$$;

-- Optional pg_cron job every minute
-- select cron.schedule(
--   'process-stock-queue',
--   '* * * * *',
--   $$select inventory.apply_stock_queue(500);$$
-- );
