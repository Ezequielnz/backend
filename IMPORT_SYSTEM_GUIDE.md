# 📊 Sistema de Importación Masiva de Productos

## 🎯 Resumen del Sistema

El sistema de importación masiva permite a los usuarios subir archivos Excel (.xlsx, .xls) o CSV para importar productos de forma inteligente y eficiente.

## ✨ Características Principales

### 🧠 **Reconocimiento Inteligente de Columnas**
- **Fuzzy Matching**: Reconoce columnas incluso con errores tipográficos
- **Múltiples idiomas**: Soporta español e inglés
- **Algoritmos avanzados**: Usa 4 algoritmos de fuzzywuzzy para máxima precisión
- **Confianza**: Cada reconocimiento incluye un score de confianza

### 📁 **Soporte de Formatos**
- **Excel**: .xlsx, .xls (múltiples hojas)
- **CSV**: Archivos separados por comas
- **Detección automática**: El sistema detecta el formato automáticamente

### 🔍 **Validación y Limpieza**
- **Validación de datos**: Precios, stock, códigos, etc.
- **Limpieza automática**: Conversión de tipos, limpieza de texto
- **Reporte de errores**: Errores específicos por fila y campo

### 🗂️ **Gestión de Categorías**
- **Creación automática**: Crea categorías nuevas si no existen
- **Mapeo inteligente**: Reconoce categorías existentes

### 🔄 **Flujo de Trabajo**
1. **Subida**: Upload del archivo
2. **Revisión**: Visualización y edición de productos
3. **Confirmación**: Opciones de importación
4. **Finalización**: Creación de productos definitivos

## 🏗️ Arquitectura del Sistema

### Backend (FastAPI)
```
app/
├── api/api_v1/endpoints/importacion.py    # Endpoints REST
├── services/
│   ├── importacion_productos.py          # Lógica de negocio
│   └── importacion_excel.py              # Procesamiento de archivos
├── schemas/importacion.py                # Modelos Pydantic
└── tasks/maintenance.py                  # Limpieza automática
```

### Frontend (React)
```
src/
├── components/ImportProducts.jsx         # Componente principal
├── utils/api.js                         # Cliente API
└── pages/Products.jsx                   # Integración
```

### Base de Datos (Supabase)
```sql
productos_importacion_temporal            # Tabla temporal
├── Datos del producto (nombre, precios, stock, etc.)
├── Metadatos de importación (fila, errores, estado)
├── Confianzas de reconocimiento
└── RLS habilitado para seguridad
```

## 🚀 Cómo Usar el Sistema

### 1. **Preparar Archivo**
Crea un archivo Excel o CSV con las siguientes columnas (nombres flexibles):

| Campo | Ejemplos de Nombres |
|-------|-------------------|
| Nombre | `Nombre`, `Producto`, `Article`, `Item` |
| Descripción | `Descripcion`, `Detalle`, `Description` |
| Código | `Codigo`, `SKU`, `Code`, `Barcode` |
| Precio Venta | `Precio`, `Precio Venta`, `Price`, `PVP` |
| Precio Compra | `Costo`, `Precio Compra`, `Cost` |
| Stock | `Stock`, `Cantidad`, `Inventory`, `Qty` |
| Stock Mínimo | `Stock Minimo`, `Min Stock`, `Minimum` |
| Categoría | `Categoria`, `Category`, `Tipo`, `Grupo` |

### 2. **Acceder al Sistema**
- Ve a la página de Productos
- Haz clic en "Importar Excel" 
- O usa el botón de importación en el header

### 3. **Subir Archivo**
- Selecciona tu archivo Excel/CSV
- El sistema procesará automáticamente
- Verás un resumen del procesamiento

### 4. **Revisar Productos**
- Revisa los productos detectados
- Corrige errores si es necesario
- Selecciona productos a importar

### 5. **Configurar Opciones**
- ✅ Crear categorías nuevas automáticamente
- ✅ Sobrescribir productos existentes (por código)

### 6. **Confirmar Importación**
- Revisa el resumen final
- Confirma la importación
- ¡Listo! Productos creados

## 🧪 Probar el Sistema

### Archivo de Prueba
Usa el archivo `test_productos.csv` incluido:

```csv
Nombre,Descripcion,Codigo,Precio Venta,Precio Compra,Stock Actual,Stock Minimo,Categoria
"Laptop HP","Laptop HP Pavilion 15 pulgadas","LAP001","1200.00","1000.00","10","2","Electrónicos"
"Mouse Inalámbrico","Mouse inalámbrico Logitech","MOU001","25.99","18.00","50","10","Accesorios"
```

### Script de Prueba Backend
```bash
python test_import.py
```

## 🔧 Mantenimiento

### Limpieza Automática
El sistema incluye limpieza automática de datos temporales:

- **Al confirmar**: Limpia datos del usuario
- **Al cancelar**: Limpia datos del usuario  
- **Al iniciar nueva importación**: Limpia datos anteriores
- **Por tiempo**: Limpia datos > 24 horas automáticamente

### Script Manual
```bash
python scripts/maintenance.py
```

### Endpoint de Limpieza
```http
DELETE /businesses/{business_id}/import/limpiar-antiguos
```

## 📊 Endpoints API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/upload` | Subir y procesar archivo |
| GET | `/resumen` | Obtener resumen de importación |
| GET | `/productos-temporales` | Listar productos temporales |
| PUT | `/productos-temporales/{id}` | Actualizar producto temporal |
| POST | `/confirmar` | Confirmar importación final |
| DELETE | `/cancelar` | Cancelar importación |
| GET | `/hojas-excel` | Obtener hojas de Excel |

## 🛡️ Seguridad

- **RLS (Row Level Security)**: Cada usuario solo ve sus datos
- **Validación de archivos**: Tamaño máximo, formatos permitidos
- **Sanitización**: Limpieza de datos de entrada
- **Permisos**: Control de acceso por negocio

## 🎨 Características de UX

- **Wizard de 4 pasos**: Flujo guiado intuitivo
- **Feedback visual**: Estados de carga, errores, éxito
- **Plantilla descargable**: Template de ejemplo
- **Validación en tiempo real**: Errores mostrados inmediatamente
- **Responsive**: Funciona en móvil y desktop

## 🔍 Algoritmo de Reconocimiento

### Patrones Reconocidos
```python
COLUMN_PATTERNS = {
    'nombre': ['nombre', 'producto', 'article', 'item', ...],
    'precio_venta': ['precio', 'price', 'pvp', 'selling_price', ...],
    'stock_actual': ['stock', 'cantidad', 'inventory', 'qty', ...],
    # ... más patrones
}
```

### Algoritmos de Fuzzy Matching
1. **ratio**: Coincidencia general
2. **partial_ratio**: Coincidencia parcial
3. **token_sort_ratio**: Tokens ordenados
4. **token_set_ratio**: Conjuntos de tokens

### Sistema de Bonificaciones
- **Coincidencia exacta**: 100% confianza
- **Palabras clave**: +15% bonus
- **Contexto específico**: +10% bonus

## 📈 Métricas y Monitoreo

El sistema registra:
- Archivos procesados
- Productos importados exitosamente
- Errores por tipo
- Tiempo de procesamiento
- Uso de almacenamiento temporal

## 🚨 Solución de Problemas

### Error: "No se encontraron productos"
- Verifica que el archivo tenga headers
- Asegúrate de que las columnas tengan nombres reconocibles
- Revisa que el archivo no esté vacío

### Error: "Formato no válido"
- Usa archivos .xlsx, .xls o .csv
- Verifica que el archivo no esté corrupto
- Asegúrate de que el tamaño sea < 10MB

### Error: "Productos no se muestran"
- Revisa la consola del navegador para errores
- Verifica que el backend esté funcionando
- Comprueba la conexión a la base de datos

## 🎉 ¡Sistema Completamente Funcional!

El sistema de importación masiva está **100% operativo** con:

✅ **Backend completo** con API REST  
✅ **Frontend integrado** con UI moderna  
✅ **Base de datos** configurada con RLS  
✅ **Reconocimiento inteligente** de columnas  
✅ **Soporte Excel y CSV**  
✅ **Validación y limpieza** automática  
✅ **Gestión de categorías**  
✅ **Limpieza automática** de datos temporales  
✅ **Seguridad** y permisos implementados  
✅ **UX optimizada** con wizard de 4 pasos  

¡Listo para usar en producción! 🚀 