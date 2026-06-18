from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
import uuid

from app.api.deps import get_current_user_from_request as get_current_user
from app.api.context import BusinessScopedClientDep, ScopedClientContext
from app.types.auth import User
from app.services.ai_import_parser import AiImportParser
from pydantic import BaseModel

router = APIRouter()
parser_service = AiImportParser()

class ImportacionResultadoStateless(BaseModel):
    success: bool
    data_preview: List[Dict[str, Any]]
    mapeo_automatico: Dict[str, str]
    total_filas: int
    source: str
    session_id: str

class BulkUpsertPayload(BaseModel):
    data: List[Dict[str, Any]]
    tipo_precio: Optional[str] = "costo"  # Sólo para productos

@router.post("/parse-file/{entity_type}", response_model=ImportacionResultadoStateless)
async def parse_file(
    business_id: str,
    entity_type: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Sube un archivo (PDF o Excel) y devuelve los datos estructurados por IA.
    Es completamente stateless.
    """
    if entity_type not in ["productos", "clientes", "proveedores"]:
        raise HTTPException(status_code=400, detail="entity_type inválido")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede 10MB")

    filename = file.filename.lower() if file.filename else ""
    try:
        if filename.endswith('.pdf'):
            result = parser_service.parse_pdf(content, entity_type)
        elif filename.endswith(('.xls', '.xlsx')):
            result = parser_service.parse_excel(content, entity_type)
        else:
            raise HTTPException(status_code=400, detail="Formato no soportado (.pdf, .xlsx, .xls)")

        result['session_id'] = str(uuid.uuid4()) # Dummy session ID for frontend compatibility if needed
        return ImportacionResultadoStateless(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk-upsert/{entity_type}")
async def bulk_upsert(
    business_id: str,
    entity_type: str,
    payload: BulkUpsertPayload,
    current_user: User = Depends(get_current_user),
    scoped: ScopedClientContext = Depends(BusinessScopedClientDep),
):
    """
    Recibe la data curada del frontend y hace upsert inteligente.
    """
    if entity_type not in ["productos", "clientes", "proveedores"]:
        raise HTTPException(status_code=400, detail="entity_type inválido")

    client = scoped.client
    data = payload.data
    if not data:
        return {"success": True, "upserted": 0, "errors": []}

    # Asignar business_id a todos
    for item in data:
        item['business_id'] = business_id

    try:
        if entity_type == "productos":
            # Upsert para productos. Clave: codigo + business_id
            # Si no hay código, asignar UUID
            for item in data:
                if not item.get("codigo"):
                    # El prompt pedía buscar por nombre si no hay código. 
                    # Lo hacemos buscando en BD
                    existing = client.table("productos").select("id, codigo").eq("business_id", business_id).ilike("nombre", item.get("nombre", "")).execute()
                    if existing.data:
                        item["codigo"] = existing.data[0].get("codigo")
                    else:
                        item["codigo"] = str(uuid.uuid4())[:8].upper() # Generar código corto
                
                # Manejar tipo de precio
                if payload.tipo_precio == "costo" and "precio" in item:
                    item["precio_compra"] = item.pop("precio")
                    # Calcular precio venta sugerido (ej: +30%)
                    item["precio_venta"] = item["precio_compra"] * 1.3
                elif payload.tipo_precio == "venta" and "precio" in item:
                    item["precio_venta"] = item.pop("precio")

            res = client.table("productos").upsert(data, on_conflict="business_id,codigo").execute()
            return {"success": True, "upserted": len(data)}

        elif entity_type in ["clientes", "proveedores"]:
            # Upsert para clientes/proveedores. Clave: documento_numero + business_id
            for item in data:
                if not item.get("documento_numero"):
                    # Buscar por razon social
                    existing = client.table(entity_type).select("id, documento_numero").eq("business_id", business_id).ilike("razon_social", item.get("razon_social", "")).execute()
                    if existing.data and existing.data[0].get("documento_numero"):
                        item["documento_numero"] = existing.data[0].get("documento_numero")
                    else:
                        item["documento_numero"] = f"GEN-{str(uuid.uuid4())[:8].upper()}"

            res = client.table(entity_type).upsert(data, on_conflict="business_id,documento_numero").execute()
            return {"success": True, "upserted": len(data)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_import_status():
    return {
        "message": "AI Import System Active",
        "status": "active",
        "supported_formats": [".xlsx", ".xls", ".pdf"]
    }
