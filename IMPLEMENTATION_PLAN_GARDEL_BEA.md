# Plan de Implementación: MicroPymes Desktop App
## Rama: `gardel_bea`

> **Última actualización:** Mayo 2026  
> **Repos involucrados:** `micro_pymes/backend`, `micro_pymes/client`, `api_facturacion_arca`

---

## Decisiones de Arquitectura Confirmadas

| Pregunta | Decisión |
|---|---|
| Módulos ML | ❌ Eliminados. Solo se conserva `pdf_parser.py` (OpenAI Vision para catálogos) |
| Multi-usuario | ❌ Un solo usuario por instalación (el dueño del negocio) |
| Versión web paralela | ❌ Se abandona. Solo desktop |
| Plataformas | ✅ Windows + macOS |
| Backup de datos | ✅ Sí, función de exportar/importar SQLite |
| Facturación electrónica | ✅ ARCA/AFIP integrada directamente en el backend (sin microservicio separado) |

---

## Arquitectura Final

```
┌──────────────────────────────────────────────────────────────┐
│  MicroPymes.exe / MicroPymes.app  (Electron)                 │
│                                                              │
│  ┌─────────────────────┐     ┌──────────────────────────┐   │
│  │  React Frontend     │────▶│  FastAPI (subproceso)    │   │
│  │  (build estático    │     │  127.0.0.1:PORT_RANDOM   │   │
│  │   servido local)    │     │  Solo accesible desde    │   │
│  └─────────────────────┘     │  dentro de la misma app  │   │
│                              └──────────┬───────────────┘   │
│                                         │                   │
│                    ┌────────────────────┼──────────────┐    │
│                    │                   │              │    │
│          ┌─────────▼──────┐  ┌─────────▼──────┐      │    │
│          │   SQLite DB    │  │  Motor AFIP     │      │    │
│          │  %APPDATA%\    │  │  (zeep+crypto)  │      │    │
│          │  micropymes.db │  │  wsfe/wsaa      │      │    │
│          └────────────────┘  └────────┬────────┘      │    │
│                                       │               │    │
│                              ┌────────▼────────┐      │    │
│                              │  ARCA/AFIP      │      │    │
│                              │  (internet req.)│      │    │
│                              └─────────────────┘      │    │
│                                                       │    │
│  [OpenAI API — solo para PDF parser, requiere internet]    │
└──────────────────────────────────────────────────────────────┘
```

**Seguridad:**
- FastAPI escucha SOLO en `127.0.0.1` (loopback), **nunca en `0.0.0.0`**
- Electron bloquea cualquier request desde URLs externas
- La API key de OpenAI se guarda en el keychain del SO

---

## Stack Final

### Backend — lo que QUEDA
```
fastapi, uvicorn, pydantic, pydantic-settings
sqlalchemy (SQLite)
passlib[bcrypt], PyJWT          ← auth local
python-decouple
openpyxl, xlrd                  ← importación Excel
pdf2image, Pillow               ← PDF parser catálogos
openai, tenacity                ← PDF parser (OpenAI Vision)
APScheduler                     ← tareas en background (sin Redis)
email-validator
# Facturación AFIP:
zeep                            ← cliente SOAP WSFE/WSAA
cryptography                    ← firma PKCS7 del ticket WSAA
lxml                            ← parseo XML respuestas AFIP
reportlab                       ← generación PDF de factura
qrcode[pil]                     ← QR del CAE (norma RG 5616/2024)
```

### Backend — lo que SE ELIMINÓ (Fase 1 ✅)
```
supabase                        ← reemplazado por SQLAlchemy + SQLite
redis, celery, flower           ← reemplazado por APScheduler
scikit-learn, prophet, xgboost  ← módulos ML eliminados
shap, statsmodels, holidays     ← ídem
torch, transformers             ← ídem
sentence-transformers, faiss    ← ídem
pgvector, asyncpg, psycopg2     ← ídem (solo PostgreSQL)
opentelemetry, prometheus       ← monitoreo cloud (innecesario en desktop)
pybreaker, tiktoken             ← ídem
```

---

## Estado actual de `api_facturacion_arca` (motor AFIP)

El repo `api_facturacion_arca` es una API standalone que se usó para desarrollar y testear el motor AFIP.
**No se integrará como microservicio.** Su lógica se copiará y adaptará directamente en `backend/app/services/afip/`.

### ✅ Lo que ya está listo en `api_facturacion_arca`

| Componente | Estado |
|---|---|
| Autenticación WSAA (firma PKCS7 + ticket) | ✅ Completo |
| Caché de tickets (en memoria + archivos) | ✅ Completo |
| Cliente WSFE con zeep + fallback raw SOAP | ✅ Completo |
| `FECAESolicitar` (crear factura electrónica) | ✅ Completo |
| `FECompUltimoAutorizado` (último número emitido) | ✅ Completo |
| `FECompConsultar` (consultar factura existente) | ✅ Completo |
| Parámetros AFIP (tipos cbte, iva, doc, moneda) | ✅ Completo |
| Modo dev/homo con mocks automáticos | ✅ Completo |
| Soporte IVA detallado, tributos, opcionales | ✅ Completo |

### ❌ Lo que falta (se implementa en Fase 3.5)

| Componente | Detalle |
|---|---|
| Configuración del negocio (CUIT, punto de venta, tipo cbte) | El CUIT está hardcodeado en `.env`, no en la DB del negocio |
| Modelo ORM para facturas emitidas | No hay tabla `facturas` ni campos en `Venta` |
| Integración automática con `ventas.py` | El endpoint `facturacion.py` es un stub vacío |
| Generación de PDF | No hay PDF de la factura |
| Código QR del CAE | Requerido por RG AFIP 5616/2024 |
| Pantalla de configuración AFIP | El usuario no puede configurar certificados desde la UI |
| Lógica de reintento ante error AFIP | Si AFIP no responde, no hay retry automático |

### Decisiones técnicas — Librerías de facturación

| Propósito | Librería elegida | Motivo |
|---|---|---|
| PDF de la factura | `reportlab` | Pura Python, compatible con PyInstaller, calidad comercial |
| QR del CAE | `qrcode[pil]` | Pura Python, cumple norma RG 5616/2024 |
| Motor SOAP WSFE/WSAA | `zeep` + `cryptography` + `lxml` | Ya en uso, funcionan correctamente |
| `pyafipws` | ❌ **Descartado** | No soporta Python 3.10+, problemas con PyInstaller |

---

## Fases de Ejecución

---

### ✅ FASE 1 — Limpieza y Simplificación del Backend — **COMPLETADA**

> **Estado: ✅ TERMINADA**

**Objetivo logrado:** Backend corriendo en SQLite sin Supabase ni ML.

**Lo que se hizo:**
1. ✅ `requirements.txt` limpiado (eliminadas ~25 dependencias ML, Supabase, Redis, Celery)
2. ✅ Modelos SQLAlchemy ORM creados en `app/models/orm_models.py`:
   - `Negocio`, `Usuario`, `Producto`, `Servicio`, `Cliente`, `Proveedor`
   - `Categoria`, `MetodoPago`, `Venta`, `VentaDetalle`
   - `Compra`, `CompraDetalle`, `StockTransfer`, `StockTransferItem`
   - `Tarea`, `MovimientoFinanciero`, `CuentaPendiente`, `CategoriaFinanciera`
3. ✅ Migración inicial con Alembic para SQLite
4. ✅ `app/db/session.py` reemplazado (SQLite puro, sin pool_size)
5. ✅ `app/db/supabase_client.py` reemplazado por `app/db/local_db.py`
6. ✅ Eliminados: servicios ML, workers Celery, `celery_app.py`, `tasks/`, `workers/`
7. ✅ `app/core/config.py` simplificado

**Entregable verificado:** `uvicorn main:app --host 127.0.0.1` arranca sin errores.

---

### 🔲 FASE 2 — Auth Local (1–2 días)

**Objetivo:** Login/logout 100% local, sin Supabase Auth.

**Pasos:**

1. Reescribir `app/api/api_v1/endpoints/auth.py`:
   - `POST /auth/login` → verificar password con bcrypt, devolver JWT firmado localmente
   - `POST /auth/logout` → invalidar sesión (simple, sin blacklist)
   - `GET /auth/me` → devolver datos del usuario logueado
2. Reescribir `app/api/deps.py` (`get_current_user` valida JWT local)
3. Reescribir `AuthContext.jsx` en el frontend
4. Crear endpoint de setup inicial: `POST /auth/setup` (crea el primer y único usuario + negocio)
5. Agregar campo `openai_api_key` en la tabla de configuración del negocio

**Entregable:** Login funciona 100% local, sin red.

---

### 🔲 FASE 3 — Migrar Endpoints a SQLAlchemy (5–7 días)

**Objetivo:** Todos los módulos funcionales del sistema operando con SQLite.

**Orden recomendado (de menor a mayor complejidad):**

1. `categorias.py`, `metodos_pago.py` — CRUD simples
2. `clientes.py`, `proveedores.py`
3. `productos.py`, `servicios.py`
4. `compras.py`, `stock.py`, `stock_transfers.py`
5. `ventas.py` — más complejo, maneja stock y finanzas
6. `finanzas.py`
7. `tareas.py`
8. `branch_settings.py`, `tenant_settings.py`
9. `importacion.py` — Excel
10. `businesses.py` — simplificar para un solo negocio
11. Eliminar: `monitoring.py`, `action.py`, `suscripciones.py`, `permissions.py`

**Archivos a modificar:**

| Archivo | Cambio |
|---|---|
| Todos los endpoints activos | Reemplazar llamadas `supabase.table(...)` por SQLAlchemy ORM |
| `app/api/api_v1/endpoints/monitoring.py` | **ELIMINAR** (métricas cloud) |
| `app/api/api_v1/endpoints/action.py` | **ELIMINAR** (AI actions) |
| `app/api/api_v1/endpoints/suscripciones.py` | **ELIMINAR** (modelo SaaS) |

**Entregable:** La app completa funciona en el browser con `uvicorn` + `vite dev`.

---

### 🆕 FASE 3.5 — Integración de Facturación ARCA (3–5 días)

**Objetivo:** Cuando el usuario confirma una venta, el sistema emite automáticamente la factura electrónica a AFIP, guarda el CAE y genera el PDF.

#### 3.5.1 — Copiar el motor AFIP al backend

Los servicios de `api_facturacion_arca` se copian (no se consumen por HTTP) al backend:

```
backend/app/services/afip/
    __init__.py
    afip_client.py       ← copiado y adaptado de api_facturacion_arca
    ticket_access.py     ← ídem
    pdf_factura.py       ← NUEVO: generación de PDF con reportlab
    qr_factura.py        ← NUEVO: generación QR norma RG 5616/2024
    factura_service.py   ← NUEVO: orquestador principal
```

#### 3.5.2 — Nuevos campos en `Negocio` y `Venta` (migración Alembic)

**`Negocio`** — campos de configuración AFIP:
- `cuit: str` — CUIT del negocio (ej: `"20123456789"`)
- `afip_punto_venta: int` — Punto de venta habilitado en AFIP (ej: `1`)
- `afip_tipo_comprobante: int` — Tipo cbte por defecto (`6`=B, `11`=C, `1`=A)
- `afip_cert_path: str` — Ruta al certificado `.crt`
- `afip_key_path: str` — Ruta a la clave privada `.key`
- `facturacion_habilitada: bool` — Activar/desactivar la integración
- `afip_ambiente: str` — `"homo"` (homologación) | `"prod"` (producción)

**`Venta`** — campos de estado de factura:
- `factura_estado: str` — `"pendiente"` | `"emitida"` | `"error"` | `"no_aplica"`
- `factura_cae: str` — CAE otorgado por AFIP
- `factura_cae_vto: str` — Fecha de vencimiento del CAE (YYYYMMDD)
- `factura_nro: int` — Número de comprobante asignado
- `factura_tipo: int` — Tipo de comprobante (1=A, 6=B, 11=C)
- `factura_punto_venta: int` — Punto de venta usado
- `factura_pdf_path: str` — Ruta al PDF generado
- `factura_error_detalle: str` — Mensaje de error si falló

#### 3.5.3 — `factura_service.py`: orquestador

Flujo al recibir una venta confirmada:
1. Lee configuración del negocio (CUIT, punto de venta, tipo cbte, paths cert)
2. Detecta tipo de documento del cliente (CUIT/DNI/consumidor final)
3. Calcula neto, IVA, total según el tipo de comprobante
4. Llama a `afip_client.create_invoice()`
5. Guarda CAE + nro de comprobante en la `Venta`
6. Llama a `pdf_factura.generar_pdf()` → guarda en `%APPDATA%/MicroPymes/facturas/`
7. Devuelve resultado (éxito o error con mensaje)

**Manejo de errores:**
- Si AFIP no responde (timeout/red): la venta se guarda con `factura_estado = "pendiente"`, APScheduler reintenta cada 5 minutos
- Si hay error de configuración (cert faltante, CUIT inválido): `factura_estado = "error"` con detalle
- Al arrancar la app, APScheduler procesa las facturas pendientes acumuladas

#### 3.5.4 — Endpoints `/api/v1/facturacion/`

Reemplaza el stub actual (`facturacion.py` con solo 24 líneas placeholder):

```
GET  /api/v1/facturacion/                     ← listado de facturas emitidas
GET  /api/v1/facturacion/{venta_id}           ← detalle de una factura
GET  /api/v1/facturacion/{venta_id}/pdf       ← descargar PDF
POST /api/v1/facturacion/{venta_id}/retry     ← reintentar factura con error/pendiente
GET  /api/v1/facturacion/config               ← obtener configuración AFIP del negocio
PUT  /api/v1/facturacion/config               ← actualizar configuración AFIP
POST /api/v1/facturacion/config/test          ← testear conexión AFIP (cert + WSAA)
POST /api/v1/facturacion/config/upload-cert   ← subir certificado .crt
POST /api/v1/facturacion/config/upload-key    ← subir clave privada .key
```

#### 3.5.5 — Hook en `ventas.py`

Luego de confirmar una venta, se dispara la facturación en background (sin bloquear la respuesta):

```python
# En POST /ventas/ (después de guardar la venta en la DB)
background_tasks.add_task(factura_service.emitir_factura, venta.id)
```

#### 3.5.6 — Contenido del PDF de factura

- Logo del negocio (si está configurado)
- Datos del emisor: razón social, CUIT, domicilio, condición IVA
- Datos del receptor: nombre, CUIT/DNI
- Tabla de ítems: descripción, cantidad, precio unitario, subtotal
- Totales: neto gravado, IVA discriminado, total
- CAE + fecha de vencimiento del CAE
- **Código QR** (norma RG AFIP 5616/2024)
- Número de comprobante, punto de venta, fecha

#### 3.5.7 — Pantalla de configuración AFIP (Frontend)

Nueva pantalla en `Settings > Facturación`:
- Campo: CUIT de la empresa
- Campo: Punto de venta (número habilitado en AFIP)
- Selector: Tipo de comprobante por defecto (A / B / C)
- Upload: Certificado AFIP (`.crt`)
- Upload: Clave privada (`.key`)
- Toggle: Habilitar/deshabilitar facturación automática
- Toggle: Ambiente — Homologación (tests) / Producción
- Botón: **"Probar conexión con AFIP"**

**Archivos a crear/modificar en esta fase:**

| Acción | Archivo | Descripción |
|---|---|---|
| 🆕 NUEVO | `app/services/afip/__init__.py` | Módulo AFIP |
| 🆕 NUEVO | `app/services/afip/afip_client.py` | Motor WSFE (de `api_facturacion_arca`) |
| 🆕 NUEVO | `app/services/afip/ticket_access.py` | Autenticación WSAA |
| 🆕 NUEVO | `app/services/afip/pdf_factura.py` | Generación PDF con reportlab |
| 🆕 NUEVO | `app/services/afip/qr_factura.py` | Generación QR RG 5616/2024 |
| 🆕 NUEVO | `app/services/afip/factura_service.py` | Orquestador principal |
| ✏️ MODIFICAR | `app/models/orm_models.py` | Nuevos campos en `Negocio` y `Venta` |
| ✏️ MODIFICAR | `app/api/api_v1/endpoints/facturacion.py` | Reemplazar stub por endpoints reales |
| ✏️ MODIFICAR | `app/api/api_v1/endpoints/ventas.py` | Agregar hook post-venta |
| ✏️ MODIFICAR | `app/core/config.py` | Variables AFIP (env, paths cert por defecto) |
| ✏️ MODIFICAR | `requirements.txt` | Agregar `reportlab`, `qrcode[pil]`, `zeep`, `lxml`, `cryptography` |
| ✏️ MODIFICAR | `alembic/` | Nueva migración para campos de facturación |
| 🆕 NUEVO (client) | `src/pages/settings/Facturacion.jsx` | Pantalla configuración AFIP |
| 🆕 NUEVO (client) | `src/components/FacturaPanel.jsx` | Panel estado factura en detalle de venta |

**Entregable:** Al completar una venta, el sistema emite la factura automáticamente, guarda el CAE y genera el PDF — sin intervención del usuario.

> **NOTA:** El certificado AFIP tiene vencimiento (generalmente 2 años). El sistema debe mostrar una alerta cuando falten 30 días para el vencimiento. Los archivos `.crt` y `.key` no deben guardarse en carpetas sincronizadas con la nube (OneDrive, Google Drive).

---

### 🔲 FASE 4 — Electron Shell (2–3 días)

**Objetivo:** La app se abre como programa nativo, no en el navegador.

**Pasos:**

1. Crear `electron/package.json`:
   ```json
   {
     "electron": "^31.0.0",
     "electron-builder": "^25.0.0"
   }
   ```

2. Crear `electron/main.js`:
   - Buscar puerto libre en `127.0.0.1`
   - Lanzar el ejecutable del backend como `child_process`
   - Esperar a que `/health` responda (polling)
   - Crear `BrowserWindow` cargando el build de React
   - Inyectar `window.__MICROPYMES_PORT__` en el renderer
   - Al cerrar la ventana: matar el backend **y** apagar APScheduler correctamente

3. Crear `electron/preload.js`:
   - Exponer IPC para: backup, importar DB, abrir diálogos de archivo nativos, abrir carpeta de facturas

4. Adaptar `src/main.tsx` para leer el puerto dinámico
5. Configurar `vite.config.ts` para build compatible con Electron (`base: './'`)

**Entregable:** Doble clic en `electron .` abre la app como programa.

---

### 🔲 FASE 5 — Funciones Nativas Desktop (2–3 días)

**Objetivo:** Funciones exclusivas de la versión desktop.

1. **Backup/Exportar:** Botón en Settings que copia `micropymes.db` a una ubicación elegida (diálogo nativo)
2. **Restaurar:** Importar un `.db` de backup (con confirmación de sobreescritura)
3. **Configurar API Key OpenAI:** Guardar/leer en Windows Credential Manager / macOS Keychain (`electron.safeStorage`)
4. **PDF Parser:** Endpoint de importación PDF lee la API key del keychain
5. **Visor de facturas:** Abrir PDF desde la app con el visor nativo del SO
6. **Carpeta de facturas:** Botón "Abrir carpeta de facturas" en Settings
7. **Auto-update:** `electron-updater` desde GitHub Releases (opcional)
8. Menú nativo (macOS: menú Apple + Dock; Windows: bandeja del sistema)

**Archivos a crear/modificar:**

| Acción | Archivo |
|---|---|
| ✏️ MODIFICAR | `electron/main.js` |
| ✏️ MODIFICAR | `electron/preload.js` |
| 🆕 NUEVO (client) | `src/pages/Setup.jsx` — Wizard de primer uso |
| 🆕 NUEVO (client) | `src/pages/settings/Backup.jsx` |
| 🆕 NUEVO (client) | `src/pages/settings/ApiConfig.jsx` |
| ❌ ELIMINAR (client) | `src/pages/Register.jsx` |
| ❌ ELIMINAR (client) | `src/pages/ConfirmEmail.jsx` |
| ❌ ELIMINAR (client) | `src/pages/EmailConfirmation.jsx` |
| ❌ ELIMINAR (client) | `src/pages/RequestPasswordReset.jsx` |
| ❌ ELIMINAR (client) | `src/pages/UpdatePassword.jsx` |
| ❌ ELIMINAR (client) | `src/pages/LandingPage.tsx` |
| ❌ ELIMINAR (client) | `src/pages/PendingApproval.jsx` |
| ❌ ELIMINAR (client) | `src/pages/CreateBusiness.jsx` |

---

### 🔲 FASE 6 — Empaquetado e Instalador (2–3 días)

**Objetivo:** Un archivo que el cliente descarga e instala sin tocar ninguna terminal.

#### Backend: PyInstaller
```bash
pyinstaller --onefile --name micropymes-backend main.py
```
Genera `micropymes-backend.exe` (Windows) / `micropymes-backend` (macOS).

> **Dependencias AFIP incluidas sin problema:** `reportlab`, `qrcode`, `Pillow`, `zeep`, `lxml`, `cryptography` son puras Python — PyInstaller las empaqueta sin binarios externos.

> **Poppler** (para `pdf2image` del PDF parser): incluir el binario precompilado en el instalador.

#### Frontend: Vite Build
```bash
npm run build
```

#### Empaquetado final: electron-builder
```yaml
# electron-builder.yml
appId: com.micropymes.desktop
productName: MicroPymes
directories:
  buildResources: electron/assets
files:
  - "dist/**"             ← build de React
  - "electron/**"         ← proceso principal
  - "backend-dist/**"     ← binario de PyInstaller
win:
  target: nsis            ← instalador Windows (.exe)
  icon: electron/assets/icon.ico
mac:
  target: dmg             ← imagen de disco macOS
  icon: electron/assets/icon.icns
```

**Resultado final:**
- `MicroPymes-Setup-1.0.0.exe` (~150–200 MB con Python embebido)
- `MicroPymes-1.0.0.dmg` para macOS

---

## Resumen de Tiempos

| Fase | Contenido | Estado | Días estimados |
|---|---|---|---|
| Fase 1 | Limpieza + SQLAlchemy models | ✅ COMPLETADA | — |
| Fase 2 | Auth local | 🔲 Pendiente | 1–2 |
| Fase 3 | Migrar 15+ endpoints a SQLAlchemy | 🔲 Pendiente | 5–7 |
| **Fase 3.5** | **Integración facturación ARCA** | 🔲 Pendiente | **3–5** |
| Fase 4 | Electron Shell | 🔲 Pendiente | 2–3 |
| Fase 5 | Funciones nativas (backup, PDF viewer, API key) | 🔲 Pendiente | 2–3 |
| Fase 6 | Empaquetado instalador | 🔲 Pendiente | 2–3 |
| **Total restante** | | | **15–23 días** |

> **Versión funcional sin instalador:** disponible al final de la Fase 4 (~10–14 días). Ideal para primeras pruebas con el cliente.

---

## Configuración AFIP para el Usuario Final

Al activar la facturación por primera vez, el usuario debe:

1. Ir a **Configuración > Facturación**
2. Ingresar el **CUIT** de la empresa
3. Subir el **certificado** `.crt` (generado en portal AFIP junto con la clave privada)
4. Subir la **clave privada** `.key`
5. Configurar el **punto de venta** (número habilitado en AFIP)
6. Seleccionar el **tipo de comprobante** por defecto:
   - **Factura A** → para clientes Responsables Inscriptos
   - **Factura B** → para consumidores finales (Responsable Inscripto emisor)
   - **Factura C** → Monotributistas
7. Elegir el **ambiente**: Homologación (testing) o Producción
8. Presionar **"Probar conexión"** para validar

De ahí en más, el sistema factura automáticamente con cada venta confirmada.

---

## Preguntas abiertas (Fase 3.5)

1. **¿El negocio es Responsable Inscripto, Monotributista u otro?** → determina tipo cbte por defecto y cálculo de IVA
2. **¿Los clientes tienen siempre CUIT o pueden ser consumidores finales?** → afecta `doc_tipo`/`doc_nro` en la solicitud AFIP
3. **¿Se quiere enviar el PDF por mail al cliente?** → requiere configuración SMTP
4. **¿El negocio tiene ya el par certificado/clave generado para wsfe en AFIP?**
