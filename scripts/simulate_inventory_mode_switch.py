#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulate_inventory_mode_switch.py
---------------------------------
Herramienta de QA para validar el cambio entre inventario centralizado y
distribuido por sucursal una vez aplicadas las migraciones multi-sucursal.

Flujo principal:
1. Verifica que existan las tablas claves (`negocio_configuracion`, `producto_sucursal`,
   `inventario_negocio`, etc.).
2. Selecciona el negocio objetivo (argumento --negocio-id o el mas reciente con datos).
3. Calcula el stock agregado por sucursal y lo compara con `inventario_negocio`
   al activar el modo centralizado.
4. Vuelve al modo original (a menos que se use --skip-revert) y reporta resultados.

Uso:
    python scripts/simulate_inventory_mode_switch.py --negocio-id <uuid>

Variables de entorno admitidas:
    SIM_MODE_SWITCH_NEGOCIO_ID  -> Negocio a ejercitar (prioridad sobre CLI)
    SIM_MODE_SWITCH_DSN         -> DSN completo para la conexion a la base
    DB_*, DATABASE_URL, STAGING_DATABASE_URL (fallback al helper existente)
"""

import argparse
import os
import sys
from collections import defaultdict
from decimal import Decimal, getcontext
from typing import Dict, Iterable, Optional, Sequence, Tuple

import psycopg2

# Aumentamos la precision para comparaciones de inventario (evitar ruido por floats)
getcontext().prec = 12


def _resolve_dsn() -> Optional[str]:
    for key in (
        "SIM_MODE_SWITCH_DSN",
        "BRANCH_TRIGGER_TEST_DSN",
        "DB_DSN",
        "DATABASE_URL",
        "STAGING_DATABASE_URL",
    ):
        value = os.getenv(key)
        if value:
            return value
    return None


def get_connection(*, autocommit: bool = False) -> psycopg2.extensions.connection:
    dsn = _resolve_dsn()
    if dsn:
        conn = psycopg2.connect(dsn)
    else:
        host = os.getenv("DB_HOST", "aws-0-us-west-1.pooler.supabase.com")
        port = int(os.getenv("DB_PORT", "5432"))
        dbname = os.getenv("DB_NAME", "postgres")
        user = os.getenv("DB_USER", "postgres.aupmnxxauxasetwnqkma")
        password = os.getenv("DB_PASSWORD", "kJAupLuJOgZdrIUy")
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    conn.autocommit = autocommit
    return conn


def ensure_tables(cur, tables: Iterable[str]) -> None:
    missing = []
    for table in tables:
        cur.execute("SELECT to_regclass(%s)", (table,))
        if cur.fetchone()[0] is None:
            missing.append(table)
    if missing:
        raise RuntimeError(
            "Tablas requeridas ausentes: {}. Ejecutar las migraciones estructurales antes de correr la simulacion.".format(
                ", ".join(missing)
            )
        )


def call_function_if_exists(cur, signature: str, params: Sequence) -> bool:
    cur.execute("SELECT to_regprocedure(%s)", (signature,))
    oid = cur.fetchone()[0]
    if oid is None:
        return False

    schema_func = signature.split("(")[0]
    placeholders = ", ".join(["%s"] * len(params))
    sql = f"SELECT {schema_func}({placeholders})"
    cur.execute(sql, params)
    return True


def pick_target_business(cur, explicit_negocio: Optional[str]) -> str:
    if explicit_negocio:
        cur.execute(
            """
            SELECT id
            FROM public.negocios
            WHERE id = %s
            """,
            (explicit_negocio,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Negocio {explicit_negocio} no existe.")
        return explicit_negocio

    cur.execute(
        """
        SELECT n.id
        FROM public.negocios n
        WHERE EXISTS (
            SELECT 1
            FROM public.sucursales s
            WHERE s.negocio_id = n.id
        )
          AND EXISTS (
            SELECT 1
            FROM public.producto_sucursal ps
            WHERE ps.negocio_id = n.id
        )
        ORDER BY n.updated_at DESC NULLS LAST, n.created_at DESC NULLS LAST, n.id
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No se encontro un negocio con sucursales y productos para simular.")
    return row[0]


def fetch_config(cur, negocio_id: str) -> Dict[str, str]:
    cur.execute(
        """
        SELECT inventario_modo,
               catalogo_producto_modo,
               servicios_modo,
               permite_transferencias,
               transferencia_auto_confirma
        FROM public.negocio_configuracion
        WHERE negocio_id = %s
        """,
        (negocio_id,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"No existe configuracion en negocio_configuracion para el negocio {negocio_id}."
        )
    keys = [
        "inventario_modo",
        "catalogo_producto_modo",
        "servicios_modo",
        "permite_transferencias",
        "transferencia_auto_confirma",
    ]
    return dict(zip(keys, row))


def fetch_stock_by_branch(cur, negocio_id: str) -> Dict[str, Decimal]:
    cur.execute(
        """
        SELECT producto_id::text, COALESCE(SUM(stock_actual), 0)::numeric
        FROM public.inventario_sucursal
        WHERE negocio_id = %s
        GROUP BY producto_id
        """,
        (negocio_id,),
    )
    return {prod: Decimal(stock) for prod, stock in cur.fetchall()}


def fetch_stock_central(cur, negocio_id: str) -> Dict[str, Decimal]:
    cur.execute(
        """
        SELECT producto_id::text, COALESCE(stock_total, 0)::numeric
        FROM public.inventario_negocio
        WHERE negocio_id = %s
        """,
        (negocio_id,),
    )
    return {prod: Decimal(stock) for prod, stock in cur.fetchall()}


def compare_stocks(branch_totals: Dict[str, Decimal], central_totals: Dict[str, Decimal]) -> Tuple[int, Dict[str, Tuple[Decimal, Decimal]]]:
    mismatches: Dict[str, Tuple[Decimal, Decimal]] = {}
    product_ids = set(branch_totals.keys()) | set(central_totals.keys())
    for pid in product_ids:
        branch_value = branch_totals.get(pid, Decimal("0"))
        central_value = central_totals.get(pid, Decimal("0"))
        if abs(branch_value - central_value) > Decimal("0.0001"):
            mismatches[pid] = (branch_value, central_value)
    return len(mismatches), mismatches


def set_inventario_mode(cur, negocio_id: str, modo: str) -> None:
    cur.execute(
        """
        UPDATE public.negocio_configuracion
        SET inventario_modo = %s,
            updated_at    = NOW()
        WHERE negocio_id = %s
        """,
        (modo, negocio_id),
    )


def describe_negocio(cur, negocio_id: str) -> None:
    cur.execute(
        """
        SELECT n.nombre,
               COUNT(DISTINCT s.id) AS sucursales,
               COUNT(DISTINCT ps.producto_id) AS productos,
               SUM(ps.visibilidad = 'publico')::int AS productos_visibles
        FROM public.negocios n
        LEFT JOIN public.sucursales s ON s.negocio_id = n.id
        LEFT JOIN public.producto_sucursal ps ON ps.negocio_id = n.id
        WHERE n.id = %s
        GROUP BY n.id
        """,
        (negocio_id,),
    )
    row = cur.fetchone()
    if row:
        nombre, sucursales, productos, visibles = row
        print(f"[INFO] Negocio: {nombre} ({negocio_id}) - sucursales: {sucursales}, productos: {productos}, visibles: {visibles}")


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Simula el cambio entre inventario centralizado y por sucursal.")
    parser.add_argument("--negocio-id", dest="negocio_id", help="Negocio objetivo (UUID).")
    parser.add_argument("--skip-revert", action="store_true", help="No regresar al modo original (util para staging controlado).")
    args = parser.parse_args(argv)

    negocio_id_env = os.getenv("SIM_MODE_SWITCH_NEGOCIO_ID")
    target_negocio = negocio_id_env or args.negocio_id

    conn = get_connection()
    try:
        cur = conn.cursor()
        ensure_tables(
            cur,
            (
                "public.negocio_configuracion",
                "public.producto_sucursal",
                "public.servicio_sucursal",
                "public.inventario_sucursal",
                "public.inventario_negocio",
            ),
        )

        negocio_id = pick_target_business(cur, target_negocio)
        describe_negocio(cur, negocio_id)

        original_cfg = fetch_config(cur, negocio_id)
        print(f"[INFO] Configuracion original: {original_cfg}")

        branch_stock = fetch_stock_by_branch(cur, negocio_id)
        central_stock_before = fetch_stock_central(cur, negocio_id)
        mismatches_before, details_before = compare_stocks(branch_stock, central_stock_before)
        if mismatches_before:
            print(f"[WARN] Diferencias previas entre inventario_sucursal e inventario_negocio ({mismatches_before} productos).")
        else:
            print("[INFO] Inventario central ya sincronizado antes del cambio.")

        print("[STEP] Cambiando inventario_modo -> 'centralizado'")
        set_inventario_mode(cur, negocio_id, "centralizado")
        conn.commit()

        # Opcionalmente invocar funciones de sincronizacion si existen.
        triggered_sync = False
        for signature in (
            "public.sync_catalog_for_business(uuid)",
            "public.rebuild_inventario_negocio(uuid)",
            "public.ensure_branch_catalog(uuid)",
        ):
            if call_function_if_exists(cur, signature, (negocio_id,)):
                triggered_sync = True
                print(f"[INFO] Ejecutada funcion auxiliar {signature}")
        if triggered_sync:
            conn.commit()

        central_stock_after = fetch_stock_central(cur, negocio_id)
        mismatches_after, details_after = compare_stocks(branch_stock, central_stock_after)
        if mismatches_after:
            print(f"[ERROR] Diferencias tras activar inventario centralizado ({mismatches_after} productos).")
            for pid, (branch_value, central_value) in details_after.items():
                print(f"    Producto {pid}: sucursales={branch_value}, central={central_value}")
            conn.rollback()
            return 2

        print("[OK] Inventario centralizado coincide con la suma de sucursales.")

        if not args.skip_revert:
            print(f"[STEP] Restaurando inventario_modo original -> '{original_cfg['inventario_modo']}'")
            set_inventario_mode(cur, negocio_id, original_cfg["inventario_modo"])
            conn.commit()
        else:
            print("[WARN] Modo original no restaurado (--skip-revert).")

        print("[DONE] Simulacion completada sin inconsistencias.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"[ERROR] {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
