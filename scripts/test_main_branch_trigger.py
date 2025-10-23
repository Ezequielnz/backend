import os
import uuid
from typing import Optional

import psycopg2


def _resolve_dsn() -> Optional[str]:
    """
    Allow overriding the database connection via environment variables so this
    script can target staging safely.
    """
    for key in ("BRANCH_TRIGGER_TEST_DSN", "DB_DSN", "DATABASE_URL", "STAGING_DATABASE_URL"):
        value = os.getenv(key)
        if value:
            return value
    return None


def get_connection(*, autocommit: bool = False) -> psycopg2.extensions.connection:
    """
    Construct a psycopg2 connection using either a DSN or discrete parameters.
    Defaults keep backwards compatibility with the legacy hard-coded values.
    """
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


def _create_creator(cur) -> str:
    creator_email = f"creator.{uuid.uuid4().hex[:8]}@test.com"
    cur.execute(
        """
        INSERT INTO public.usuarios (email, nombre, apellido)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (creator_email, "Creator", "Trigger"),
    )
    creator_id = cur.fetchone()[0]
    print(f"Created creator usuario: {creator_id}")
    return creator_id


def _verify_contact_fields(cur, negocio_id: str, direccion: Optional[str], telefono: Optional[str], email: Optional[str]) -> None:
    cur.execute(
        """
        SELECT direccion, telefono, email
        FROM public.negocios
        WHERE id = %s
        """,
        (negocio_id,),
    )
    stored_direccion, stored_telefono, stored_email = cur.fetchone()

    if direccion is None and stored_direccion is not None:
        raise RuntimeError("Expected NULL direccion for incomplete negocio data")
    if direccion is not None and stored_direccion != direccion:
        raise RuntimeError("Direccion mismatch in negocios table")

    if telefono is None and stored_telefono is not None:
        raise RuntimeError("Expected NULL telefono for incomplete negocio data")
    if telefono is not None and stored_telefono != telefono:
        raise RuntimeError("Telefono mismatch in negocios table")

    if email is None and stored_email is not None:
        raise RuntimeError("Expected NULL email for incomplete negocio data")
    if email is not None and stored_email != email:
        raise RuntimeError("Email mismatch in negocios table")


def _validate_branch_trigger(
    *,
    scenario_label: str,
    direccion: Optional[str],
    telefono: Optional[str],
    email: Optional[str],
) -> None:
    print(f"\n--- Scenario: {scenario_label} ---")
    conn = get_connection()
    cur = conn.cursor()

    negocio_id = None
    creator_id = None
    usuario_id = None
    try:
        creator_id = _create_creator(cur)

        negocio_nombre = f"{scenario_label} {uuid.uuid4().hex[:8]}"
        cur.execute(
            """
            INSERT INTO public.negocios (nombre, direccion, telefono, email, creada_por)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (negocio_nombre, direccion, telefono, email, creator_id),
        )
        negocio_id = cur.fetchone()[0]
        print(f"Created negocio: {negocio_id} ({negocio_nombre})")

        _verify_contact_fields(cur, negocio_id, direccion, telefono, email)

        cur.execute(
            """
            SELECT id, nombre, codigo, is_main
            FROM public.sucursales
            WHERE negocio_id = %s
            """,
            (negocio_id,),
        )
        sucursales = cur.fetchall()
        print("Sucursales for negocio:", sucursales)

        if not sucursales:
            raise RuntimeError("No sucursal was created for the new negocio")

        main_sucursal_id = next((row[0] for row in sucursales if row[3]), None)
        if not main_sucursal_id:
            raise RuntimeError("Main sucursal not found")

        owner_email = f"owner.{uuid.uuid4().hex[:8]}@test.com"
        cur.execute(
            """
            INSERT INTO public.usuarios (email, nombre, apellido, negocio_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id, sucursal_id, negocio_id
            """,
            (owner_email, "Owner", "Trigger", negocio_id),
        )
        usuario_id, sucursal_id, usuario_negocio_id = cur.fetchone()
        print(f"Created usuario: {usuario_id}, sucursal_id after insert: {sucursal_id}")

        if usuario_negocio_id != negocio_id:
            raise RuntimeError("Usuario.negocio_id was not persisted correctly")

        cur.execute(
            """
            SELECT negocio_id, sucursal_id, rol_sucursal, activo
            FROM public.usuarios_sucursales
            WHERE usuario_id = %s
            """,
            (usuario_id,),
        )
        assignments = cur.fetchall()
        print("Usuarios sucursales assignments:", assignments)

        if not assignments:
            raise RuntimeError("User was not assigned to any sucursal")

        for assignment in assignments:
            if assignment[0] != negocio_id:
                raise RuntimeError("usuarios_sucursales.negocio_id mismatch")
            if assignment[1] != main_sucursal_id:
                raise RuntimeError("User not assigned to main sucursal")

        cur.execute(
            "SELECT sucursal_id FROM public.usuarios WHERE id = %s",
            (usuario_id,),
        )
        usuario_sucursal = cur.fetchone()[0]
        print("Usuario sucursal_id stored:", usuario_sucursal)
        if usuario_sucursal != main_sucursal_id:
            raise RuntimeError("Usuario.sucursal_id not updated")

        conn.commit()
        print("Scenario completed successfully")
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            with conn.cursor() as cleanup_cur:
                if usuario_id:
                    cleanup_cur.execute(
                        "DELETE FROM public.usuarios_sucursales WHERE usuario_id = %s",
                        (usuario_id,),
                    )
                    cleanup_cur.execute(
                        "DELETE FROM public.usuarios_negocios WHERE usuario_id = %s",
                        (usuario_id,),
                    )
                    cleanup_cur.execute(
                        "DELETE FROM public.usuarios WHERE id = %s",
                        (usuario_id,),
                    )
                if creator_id:
                    cleanup_cur.execute(
                        "DELETE FROM public.usuarios WHERE id = %s",
                        (creator_id,),
                    )
                if negocio_id:
                    cleanup_cur.execute(
                        "DELETE FROM public.negocios WHERE id = %s",
                        (negocio_id,),
                    )
            conn.commit()
        finally:
            cur.close()
            conn.close()


def main() -> None:
    _validate_branch_trigger(
        scenario_label="Negocio trigger full data",
        direccion="Calle Falsa 123",
        telefono="+54 11 5555-5555",
        email="negocio.trigger@test.com",
    )
    _validate_branch_trigger(
        scenario_label="Negocio trigger minimal data",
        direccion=None,
        telefono=None,
        email=None,
    )


if __name__ == "__main__":
    main()
