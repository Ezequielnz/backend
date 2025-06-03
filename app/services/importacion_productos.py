from typing import List, Dict, Any, Optional, Tuple
from app.db.supabase_client import get_supabase_client
from app.services.importacion_excel import ExcelProcessor
from app.schemas.importacion import (
    ProductoImportacionTemporal, 
    ImportacionResultado,
    ResumenImportacion,
    ColumnaMapeada,
    ConfirmacionImportacion,
    ResultadoImportacionFinal
)
import json

class ImportacionProductosService:
    """Servicio para manejar la importación masiva de productos."""
    
    def __init__(self):
        self.excel_processor = ExcelProcessor()
        self.supabase = get_supabase_client()
    
    async def procesar_archivo_excel(
        self, 
        file_content: bytes, 
        negocio_id: str,
        usuario_id: str,
        sheet_name: Optional[str] = None
    ) -> ImportacionResultado:
        """
        Procesa un archivo Excel y guarda los datos en la tabla temporal.
        
        Args:
            file_content: Contenido del archivo Excel
            negocio_id: ID del negocio
            usuario_id: ID del usuario que realiza la importación
            sheet_name: Nombre de la hoja a procesar (opcional)
            
        Returns:
            Resultado de la importación
        """
        try:
            # Validar archivo
            is_valid, message = self.excel_processor.validate_excel_file(file_content)
            if not is_valid:
                raise ValueError(message)
            
            # Procesar Excel
            excel_data = self.excel_processor.process_excel(file_content, sheet_name)
            
            # Limpiar importaciones anteriores del usuario para este negocio
            await self._limpiar_importaciones_anteriores(negocio_id, usuario_id)
            
            # Guardar productos temporales
            productos_temporales = []
            filas_con_errores = 0
            filas_validas = 0
            
            for producto_data in excel_data['productos_data']:
                try:
                    producto_temporal = await self._guardar_producto_temporal(
                        producto_data, negocio_id, usuario_id
                    )
                    productos_temporales.append(producto_temporal)
                    
                    if producto_temporal.errores:
                        filas_con_errores += 1
                    else:
                        filas_validas += 1
                        
                except Exception as e:
                    filas_con_errores += 1
                    excel_data['errores_generales'].append(
                        f"Error al guardar fila {producto_data.get('fila_excel', '?')}: {str(e)}"
                    )
            
            return ImportacionResultado(
                total_filas=excel_data['total_filas'],
                filas_procesadas=len(productos_temporales),
                filas_con_errores=filas_con_errores,
                filas_validas=filas_validas,
                productos_temporales=productos_temporales,
                errores_generales=excel_data['errores_generales']
            )
            
        except Exception as e:
            raise ValueError(f"Error al procesar archivo: {str(e)}")
    
    async def obtener_resumen_importacion(
        self, 
        negocio_id: str, 
        usuario_id: str
    ) -> ResumenImportacion:
        """
        Obtiene un resumen de la importación actual.
        
        Args:
            negocio_id: ID del negocio
            usuario_id: ID del usuario
            
        Returns:
            Resumen de la importación
        """
        try:
            # Obtener productos temporales
            response = self.supabase.table("productos_importacion_temporal").select("*").eq(
                "negocio_id", negocio_id
            ).eq("usuario_id", usuario_id).execute()
            
            productos_temporales = response.data or []
            
            if not productos_temporales:
                raise ValueError("No hay importación en curso")
            
            # Calcular estadísticas
            total_filas = len(productos_temporales)
            productos_validos = len([p for p in productos_temporales if not p.get('errores')])
            productos_con_errores = len([p for p in productos_temporales if p.get('errores')])
            productos_pendientes = len([p for p in productos_temporales if p.get('estado') == 'pendiente'])
            
            # Obtener categorías nuevas
            categorias_nuevas = set()
            for producto in productos_temporales:
                categoria_nombre = producto.get('categoria_nombre')
                if categoria_nombre:
                    # Verificar si la categoría existe
                    cat_response = self.supabase.table("categorias").select("id").eq(
                        "nombre", categoria_nombre
                    ).eq("negocio_id", negocio_id).execute()
                    
                    if not cat_response.data:
                        categorias_nuevas.add(categoria_nombre)
            
            # Simular columnas detectadas (esto vendría del procesamiento inicial)
            columnas_detectadas = [
                ColumnaMapeada(
                    nombre_original="Nombre",
                    campo_mapeado="nombre",
                    confianza=0.95,
                    sugerencias=[]
                )
            ]
            
            return ResumenImportacion(
                total_filas=total_filas,
                columnas_detectadas=columnas_detectadas,
                productos_validos=productos_validos,
                productos_con_errores=productos_con_errores,
                productos_pendientes=productos_pendientes,
                categorias_nuevas=list(categorias_nuevas)
            )
            
        except Exception as e:
            raise ValueError(f"Error al obtener resumen: {str(e)}")
    
    async def obtener_productos_temporales(
        self, 
        negocio_id: str, 
        usuario_id: str,
        estado: Optional[str] = None
    ) -> List[ProductoImportacionTemporal]:
        """
        Obtiene los productos temporales de una importación.
        
        Args:
            negocio_id: ID del negocio
            usuario_id: ID del usuario
            estado: Filtrar por estado (opcional)
            
        Returns:
            Lista de productos temporales
        """
        try:
            query = self.supabase.table("productos_importacion_temporal").select("*").eq(
                "negocio_id", negocio_id
            ).eq("usuario_id", usuario_id)
            
            if estado:
                query = query.eq("estado", estado)
            
            response = query.order("fila_excel").execute()
            
            productos = []
            for item in response.data or []:
                # Convertir errores de JSONB a lista
                errores = item.get('errores', [])
                if isinstance(errores, str):
                    errores = json.loads(errores)
                
                producto = ProductoImportacionTemporal(
                    id=item['id'],
                    negocio_id=item['negocio_id'],
                    usuario_id=item['usuario_id'],
                    nombre=item.get('nombre'),
                    descripcion=item.get('descripcion'),
                    codigo=item.get('codigo'),
                    precio_compra=item.get('precio_compra'),
                    precio_venta=item.get('precio_venta'),
                    stock_actual=item.get('stock_actual'),
                    stock_minimo=item.get('stock_minimo'),
                    categoria_nombre=item.get('categoria_nombre'),
                    categoria_id=item.get('categoria_id'),
                    fila_excel=item['fila_excel'],
                    estado=item['estado'],
                    errores=errores,
                    datos_originales=item.get('datos_originales'),
                    confianza_nombre=item.get('confianza_nombre', 0.0),
                    confianza_precio_venta=item.get('confianza_precio_venta', 0.0),
                    confianza_precio_compra=item.get('confianza_precio_compra', 0.0),
                    confianza_stock=item.get('confianza_stock', 0.0),
                    confianza_codigo=item.get('confianza_codigo', 0.0),
                    creado_en=item['creado_en'],
                    actualizado_en=item['actualizado_en']
                )
                productos.append(producto)
            
            return productos
            
        except Exception as e:
            raise ValueError(f"Error al obtener productos temporales: {str(e)}")
    
    async def actualizar_producto_temporal(
        self,
        producto_id: str,
        negocio_id: str,
        usuario_id: str,
        datos_actualizacion: Dict[str, Any]
    ) -> ProductoImportacionTemporal:
        """
        Actualiza un producto temporal.
        
        Args:
            producto_id: ID del producto temporal
            negocio_id: ID del negocio
            usuario_id: ID del usuario
            datos_actualizacion: Datos a actualizar
            
        Returns:
            Producto temporal actualizado
        """
        try:
            # Verificar que el producto pertenece al usuario
            response = self.supabase.table("productos_importacion_temporal").select("*").eq(
                "id", producto_id
            ).eq("negocio_id", negocio_id).eq("usuario_id", usuario_id).single().execute()
            
            if not response.data:
                raise ValueError("Producto temporal no encontrado")
            
            # Actualizar
            update_response = self.supabase.table("productos_importacion_temporal").update(
                datos_actualizacion
            ).eq("id", producto_id).execute()
            
            if not update_response.data:
                raise ValueError("Error al actualizar producto temporal")
            
            # Retornar producto actualizado
            productos = await self.obtener_productos_temporales(negocio_id, usuario_id)
            return next((p for p in productos if p.id == producto_id), None)
            
        except Exception as e:
            raise ValueError(f"Error al actualizar producto temporal: {str(e)}")
    
    async def confirmar_importacion(
        self,
        negocio_id: str,
        usuario_id: str,
        confirmacion: ConfirmacionImportacion
    ) -> ResultadoImportacionFinal:
        """
        Confirma la importación y crea los productos definitivos.
        
        Args:
            negocio_id: ID del negocio
            usuario_id: ID del usuario
            confirmacion: Datos de confirmación
            
        Returns:
            Resultado de la importación final
        """
        try:
            productos_creados = 0
            productos_actualizados = 0
            categorias_creadas = 0
            errores = []
            productos_creados_ids = []
            
            # Obtener productos temporales a importar
            productos_temporales = await self.obtener_productos_temporales(negocio_id, usuario_id)
            productos_a_importar = [
                p for p in productos_temporales 
                if p.id in confirmacion.productos_ids
            ]
            
            # Crear categorías nuevas si es necesario
            categorias_map = {}
            if confirmacion.crear_categorias_nuevas:
                categorias_map = await self._crear_categorias_nuevas(
                    productos_a_importar, negocio_id
                )
                categorias_creadas = len(categorias_map)
            
            # Procesar cada producto
            for producto_temporal in productos_a_importar:
                try:
                    # Resolver categoría
                    categoria_id = None
                    if producto_temporal.categoria_nombre:
                        if producto_temporal.categoria_nombre in categorias_map:
                            categoria_id = categorias_map[producto_temporal.categoria_nombre]
                        else:
                            # Buscar categoría existente
                            cat_response = self.supabase.table("categorias").select("id").eq(
                                "nombre", producto_temporal.categoria_nombre
                            ).eq("negocio_id", negocio_id).execute()
                            
                            if cat_response.data:
                                categoria_id = cat_response.data[0]['id']
                    
                    # Verificar si el producto ya existe (por código)
                    producto_existente = None
                    if producto_temporal.codigo:
                        existing_response = self.supabase.table("productos").select("id").eq(
                            "codigo", producto_temporal.codigo
                        ).eq("negocio_id", negocio_id).execute()
                        
                        if existing_response.data:
                            producto_existente = existing_response.data[0]
                    
                    # Preparar datos del producto
                    producto_data = {
                        "negocio_id": negocio_id,
                        "nombre": producto_temporal.nombre,
                        "descripcion": producto_temporal.descripcion,
                        "codigo": producto_temporal.codigo,
                        "precio_compra": producto_temporal.precio_compra,
                        "precio_venta": producto_temporal.precio_venta,
                        "stock_actual": producto_temporal.stock_actual or 0,
                        "stock_minimo": producto_temporal.stock_minimo or 0,
                        "categoria_id": categoria_id,
                        "activo": True
                    }
                    
                    # Crear o actualizar producto
                    if producto_existente and confirmacion.sobrescribir_existentes:
                        # Actualizar producto existente
                        update_response = self.supabase.table("productos").update(
                            producto_data
                        ).eq("id", producto_existente['id']).execute()
                        
                        if update_response.data:
                            productos_actualizados += 1
                            productos_creados_ids.append(producto_existente['id'])
                        else:
                            errores.append(f"Error al actualizar producto en fila {producto_temporal.fila_excel}")
                    
                    elif not producto_existente:
                        # Crear nuevo producto
                        create_response = self.supabase.table("productos").insert(
                            producto_data
                        ).execute()
                        
                        if create_response.data:
                            productos_creados += 1
                            productos_creados_ids.append(create_response.data[0]['id'])
                        else:
                            errores.append(f"Error al crear producto en fila {producto_temporal.fila_excel}")
                    
                    else:
                        errores.append(
                            f"Producto con código '{producto_temporal.codigo}' ya existe en fila {producto_temporal.fila_excel}"
                        )
                
                except Exception as e:
                    errores.append(f"Error al procesar fila {producto_temporal.fila_excel}: {str(e)}")
            
            # Limpiar datos temporales
            await self._limpiar_importaciones_anteriores(negocio_id, usuario_id)
            
            return ResultadoImportacionFinal(
                productos_creados=productos_creados,
                productos_actualizados=productos_actualizados,
                categorias_creadas=categorias_creadas,
                errores=errores,
                productos_creados_ids=productos_creados_ids
            )
            
        except Exception as e:
            raise ValueError(f"Error al confirmar importación: {str(e)}")
    
    async def cancelar_importacion(self, negocio_id: str, usuario_id: str) -> bool:
        """
        Cancela una importación en curso eliminando los datos temporales.
        
        Args:
            negocio_id: ID del negocio
            usuario_id: ID del usuario
            
        Returns:
            True si se canceló correctamente
        """
        try:
            await self._limpiar_importaciones_anteriores(negocio_id, usuario_id)
            return True
        except Exception as e:
            raise ValueError(f"Error al cancelar importación: {str(e)}")
    
    # Métodos privados
    
    async def _limpiar_importaciones_anteriores(self, negocio_id: str, usuario_id: str) -> None:
        """
        Limpia importaciones anteriores del usuario para el negocio.
        También limpia importaciones antiguas (más de 24 horas) de todos los usuarios.
        """
        try:
            # Limpiar importaciones del usuario actual
            response = self.supabase.table("productos_importacion_temporal").delete().eq(
                "negocio_id", negocio_id
            ).eq("usuario_id", usuario_id).execute()
            
            # Limpiar importaciones antiguas (más de 24 horas) de todos los usuarios
            # para evitar acumulación de datos temporales
            from datetime import datetime, timedelta
            hace_24_horas = (datetime.now() - timedelta(hours=24)).isoformat()
            
            self.supabase.table("productos_importacion_temporal").delete().lt(
                "creado_en", hace_24_horas
            ).execute()
            
        except Exception as e:
            # Log del error pero no fallar la operación principal
            print(f"Advertencia: Error al limpiar datos temporales: {str(e)}")
    
    async def limpiar_importaciones_antiguas(self) -> int:
        """
        Método público para limpiar importaciones antiguas.
        Útil para tareas de mantenimiento programadas.
        
        Returns:
            Número de registros eliminados
        """
        try:
            from datetime import datetime, timedelta
            
            # Eliminar registros más antiguos que 24 horas
            hace_24_horas = (datetime.now() - timedelta(hours=24)).isoformat()
            
            # Primero contar cuántos registros se van a eliminar
            count_response = self.supabase.table("productos_importacion_temporal").select(
                "id", count="exact"
            ).lt("creado_en", hace_24_horas).execute()
            
            registros_a_eliminar = count_response.count or 0
            
            if registros_a_eliminar > 0:
                # Eliminar los registros antiguos
                self.supabase.table("productos_importacion_temporal").delete().lt(
                    "creado_en", hace_24_horas
                ).execute()
            
            return registros_a_eliminar
            
        except Exception as e:
            print(f"Error al limpiar importaciones antiguas: {str(e)}")
            return 0
    
    async def _guardar_producto_temporal(
        self, 
        producto_data: Dict[str, Any], 
        negocio_id: str, 
        usuario_id: str
    ) -> ProductoImportacionTemporal:
        """Guarda un producto en la tabla temporal."""
        
        # Preparar datos para insertar
        insert_data = {
            "negocio_id": negocio_id,
            "usuario_id": usuario_id,
            "fila_excel": producto_data['fila_excel'],
            "datos_originales": producto_data['datos_originales'],
            "errores": producto_data['errores'],
            "estado": "error" if producto_data['errores'] else "pendiente"
        }
        
        # Agregar campos del producto
        for field in ['nombre', 'descripcion', 'codigo', 'precio_compra', 'precio_venta', 
                     'stock_actual', 'stock_minimo', 'categoria_nombre']:
            if field in producto_data:
                insert_data[field] = producto_data[field]
        
        # Mapeo de confianzas para coincidir con las columnas de la base de datos
        confidence_mapping = {
            'confianza_nombre': 'confianza_nombre',
            'confianza_descripcion': 'confianza_descripcion', 
            'confianza_codigo': 'confianza_codigo',
            'confianza_precio_venta': 'confianza_precio_venta',
            'confianza_precio_compra': 'confianza_precio_compra',
            'confianza_stock_actual': 'confianza_stock',  # Mapear a la columna existente
            'confianza_stock_minimo': 'confianza_stock_minimo',
            'confianza_categoria': 'confianza_categoria'
        }
        
        # Agregar confianzas con el mapeo correcto
        for original_field, db_field in confidence_mapping.items():
            if original_field in producto_data.get('confianzas', {}):
                insert_data[db_field] = producto_data['confianzas'][original_field]
        
        # Insertar en base de datos
        response = self.supabase.table("productos_importacion_temporal").insert(
            insert_data
        ).execute()
        
        if not response.data:
            raise ValueError("Error al guardar producto temporal")
        
        # Convertir a objeto ProductoImportacionTemporal
        item = response.data[0]
        return ProductoImportacionTemporal(
            id=item['id'],
            negocio_id=item['negocio_id'],
            usuario_id=item['usuario_id'],
            nombre=item.get('nombre'),
            descripcion=item.get('descripcion'),
            codigo=item.get('codigo'),
            precio_compra=item.get('precio_compra'),
            precio_venta=item.get('precio_venta'),
            stock_actual=item.get('stock_actual'),
            stock_minimo=item.get('stock_minimo'),
            categoria_nombre=item.get('categoria_nombre'),
            categoria_id=item.get('categoria_id'),
            fila_excel=item['fila_excel'],
            estado=item['estado'],
            errores=item.get('errores', []),
            datos_originales=item.get('datos_originales'),
            confianza_nombre=item.get('confianza_nombre', 0.0),
            confianza_precio_venta=item.get('confianza_precio_venta', 0.0),
            confianza_precio_compra=item.get('confianza_precio_compra', 0.0),
            confianza_stock=item.get('confianza_stock', 0.0),
            confianza_codigo=item.get('confianza_codigo', 0.0),
            creado_en=item['creado_en'],
            actualizado_en=item['actualizado_en']
        )
    
    async def _crear_categorias_nuevas(
        self, 
        productos_temporales: List[ProductoImportacionTemporal], 
        negocio_id: str
    ) -> Dict[str, str]:
        """
        Crea las categorías nuevas necesarias.
        
        Returns:
            Diccionario con nombre_categoria -> categoria_id
        """
        categorias_map = {}
        categorias_nuevas = set()
        
        # Recopilar categorías nuevas
        for producto in productos_temporales:
            if producto.categoria_nombre:
                categorias_nuevas.add(producto.categoria_nombre)
        
        # Verificar cuáles ya existen
        for categoria_nombre in categorias_nuevas:
            response = self.supabase.table("categorias").select("id").eq(
                "nombre", categoria_nombre
            ).eq("negocio_id", negocio_id).execute()
            
            if response.data:
                categorias_map[categoria_nombre] = response.data[0]['id']
            else:
                # Crear nueva categoría
                create_response = self.supabase.table("categorias").insert({
                    "nombre": categoria_nombre,
                    "negocio_id": negocio_id
                }).execute()
                
                if create_response.data:
                    categorias_map[categoria_nombre] = create_response.data[0]['id']
        
        return categorias_map 