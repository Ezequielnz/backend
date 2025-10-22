# Informe técnico - base de datos

| Tabla | Tiene `negocio_id` | Tiene `sucursal_id` | Nivel de dependencia | Observaciones |
| --- | --- | --- | --- | --- |
| `negocios` | — | — | Raíz (global) | Representa la empresa principal |
| `sucursales` | ✅ (`negocio_id`) | — | Depende de negocio | Puede tener `is_main` |
| `usuarios` | ✅ (`negocio_id`) | — | Depende de negocio | Usuario principal del negocio |
| `usuarios_sucursales` | ✅ | ✅ | Depende de negocio y sucursal | Asigna empleados a sucursales |
| `productos` | ✅ | — | Depende de negocio | Catálogo global del negocio |
| `inventario_sucursal` | ✅ | ✅ | Depende de sucursal | Control de stock por sucursal |
| `ventas` | ✅ | ✅ | Depende de sucursal | Venta realizada en sucursal |
| `venta_detalle` | — | — | Indirecto (via venta) | Depende de `ventas` |
| `compras` | ✅ | ✅ | Depende de sucursal | Entrada de stock o compra |
| `compra_detalle` | — | — | Indirecto (via compra) | Detalle de compra |
| `clientes` | ✅ | — | Depende de negocio | Clientes del negocio |
| `proveedores` | ✅ | — | Depende de negocio | Proveedores del negocio |
| `audit_log` | ✅ | ✅ | Depende de sucursal | Registro de acciones |
| `eventos` | ✅ | ✅ | Depende de sucursal | Logs o IA futura |
| `roles` | — | — | Global | Roles del sistema |
| `paises` | — | — | Global | Listado general |
| `provincias` | — | — | Global | Listado general |
| `planes` | — | — | Global | Configuración de planes SaaS |
| `configuracion_global` | — | — | Global | Variables o settings del sistema |
| `notificaciones` | ✅ | ✅ | Depende de sucursal | Puede extenderse a IA o alertas |
| `transferencias_stock` | ✅ | ✅ (origen y destino) | Depende de sucursal | Movimientos entre sucursales |

## 2. Confirmación de columnas `negocio_id` y `sucursal_id`

- **Presentes correctamente** en:
    
    `sucursales`, `usuarios`, `usuarios_sucursales`, `productos`, `inventario_sucursal`, `ventas`, `compras`, `audit_log`, `eventos`, `notificaciones`, `transferencias_stock`.
    
- **Faltantes o indirectas (a agregar o revisar):**
    - `venta_detalle` (debería obtener `negocio_id` y `sucursal_id` desde `venta`)
    - `compra_detalle` (igual caso)
    - `clientes` y `proveedores` (si querés mantenerlos independientes por negocio, deberían tener `negocio_id` explícito)
    - `roles`, `planes`, `paises`, `provincias` y `configuracion_global` deben mantenerse **sin `negocio_id`**, ya que son tablas globales.

## 3. Tablas globales (no dependen de negocio)

| Tabla | Tipo de contenido | Uso esperado |
| --- | --- | --- |
| `roles` | Sistema | Define permisos base |
| `planes` | SaaS / negocio | Define límites y precios |
| `paises` | Geo | Catálogo global |
| `provincias` | Geo | Catálogo global |
| `configuracion_global` | Sistema | Parámetros generales del ERP |

## 4. Relaciones principales y dependencias

### Jerarquía principal

```
negocio
 ├── sucursal
 │    ├── usuario_sucursal
 │    ├── inventario_sucursal
 │    ├── ventas
 │    │     └── venta_detalle
 │    ├── compras
 │    │     └── compra_detalle
 │    ├── notificaciones
 │    └── audit_log / eventos
 ├── usuarios
 ├── productos
 ├── clientes
 ├── proveedores
 └── transferencias_stock

```

### Relaciones clave (FKs)

- `sucursales.negocio_id → negocios.id`
- `usuarios.negocio_id → negocios.id`
- `usuarios_sucursales.sucursal_id → sucursales.id`
- `usuarios_sucursales.negocio_id → negocios.id`
- `ventas.sucursal_id → sucursales.id`
- `ventas.negocio_id → negocios.id`
- `venta_detalle.venta_id → ventas.id`
- `inventario_sucursal.sucursal_id → sucursales.id`
- `inventario_sucursal.producto_id → productos.id`
- `productos.negocio_id → negocios.id`
- `compras.sucursal_id → sucursales.id`
- `compras.negocio_id → negocios.id`
- `compra_detalle.compra_id → compras.id`
- `audit_log.sucursal_id → sucursales.id`
- `audit_log.negocio_id → negocios.id`
- `clientes.negocio_id → negocios.id`
- `proveedores.negocio_id → negocios.id`