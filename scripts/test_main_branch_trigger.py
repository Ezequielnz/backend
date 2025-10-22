import uuid

import psycopg2


def main():
    conn = psycopg2.connect(
        host="aws-0-us-west-1.pooler.supabase.com",
        port=5432,
        dbname="postgres",
        user="postgres.aupmnxxauxasetwnqkma",
        password="kJAupLuJOgZdrIUy",
    )
    conn.autocommit = False
    cur = conn.cursor()

    negocio_id = None
    creator_id = None
    usuario_id = None
    try:
        # Create temporary creator user required by FK
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

        # Create a new negocio
        cur.execute(
            """
            INSERT INTO public.negocios (nombre, direccion, telefono, email, creada_por)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                "Negocio Test Trigger",
                "Calle Falsa 123",
                "+54 11 5555-5555",
                "negocio.trigger@test.com",
                creator_id,
            ),
        )
        negocio_id = cur.fetchone()[0]
        print(f"Created negocio: {negocio_id}")

        # Verify sucursal creation
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

        main_sucursal_id = next(
            (row[0] for row in sucursales if row[3]), None
        )
        if not main_sucursal_id:
            raise RuntimeError("Main sucursal not found")

        # Create owner user
        owner_email = f"owner.{uuid.uuid4().hex[:8]}@test.com"
        cur.execute(
            """
            INSERT INTO public.usuarios (email, nombre, apellido, negocio_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id, sucursal_id
            """,
            (owner_email, "Owner", "Trigger", negocio_id),
        )
        usuario_id, sucursal_id = cur.fetchone()
        print(f"Created usuario: {usuario_id}, sucursal_id after insert: {sucursal_id}")

        # Verify assignment in usuarios_sucursales
        cur.execute(
            """
            SELECT sucursal_id, rol_sucursal, activo
            FROM public.usuarios_sucursales
            WHERE usuario_id = %s
            """,
            (usuario_id,),
        )
        assignments = cur.fetchall()
        print("Usuarios sucursales assignments:", assignments)

        if not assignments:
            raise RuntimeError("User was not assigned to any sucursal")

        if assignments[0][0] != main_sucursal_id:
            raise RuntimeError("User not assigned to main sucursal")

        # Ensure usuarios table reflects sucursal_id
        cur.execute(
            "SELECT sucursal_id FROM public.usuarios WHERE id = %s",
            (usuario_id,),
        )
        usuario_sucursal = cur.fetchone()[0]
        print("Usuario sucursal_id stored:", usuario_sucursal)

        if usuario_sucursal != main_sucursal_id:
            raise RuntimeError("Usuario.sucursal_id not updated")

        conn.commit()
        print("Test completed successfully")
    except Exception as exc:
        conn.rollback()
        raise
    finally:
        # Cleanup inserted data
        with conn:
            with conn.cursor() as cleanup_cur:
                if usuario_id:
                    cleanup_cur.execute(
                        "DELETE FROM public.usuarios WHERE id = %s", (usuario_id,)
                    )
                if creator_id:
                    cleanup_cur.execute(
                        "DELETE FROM public.usuarios WHERE id = %s", (creator_id,)
                    )
                if negocio_id:
                    cleanup_cur.execute(
                        "DELETE FROM public.negocios WHERE id = %s", (negocio_id,)
                    )
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
