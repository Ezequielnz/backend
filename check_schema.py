from app.core.config import settings
from sqlalchemy import create_engine, text

try:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        print('Connected to DB')
        result1 = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'venta_detalle';"))
        print('venta_detalle:')
        for r in result1.fetchall():
            print(r)
            
        result2 = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'inventario_sucursal';"))
        print('inventario_sucursal:')
        for r in result2.fetchall():
            print(r)
            
        result3 = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'productos';"))
        print('productos:')
        for r in result3.fetchall():
            print(r)
            
except Exception as e:
    print('Error:', e)
