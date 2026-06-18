from pydantic import BaseModel
from typing import List, Optional

class AlertItem(BaseModel):
    id: str
    type: str # "stock", "task", "arca", "sales"
    message: str
    action_url: str

class TodaySummary(BaseModel):
    sales_amount: float
    sales_count: int
    cash_position: float # ingresos - egresos (incluyendo ventas)
    pending_tasks: int

class TrendPoint(BaseModel):
    date: str
    amount: float

class TopProduct(BaseModel):
    id: str
    name: str
    quantity: int
    revenue: float

class LowStockProduct(BaseModel):
    id: str
    name: str
    current_stock: float
    min_stock: float

class InventoryHealth(BaseModel):
    top_selling: List[TopProduct]
    low_stock: List[LowStockProduct]

class DashboardSummaryResponse(BaseModel):
    status: str # "healthy", "attention", "critical"
    alerts: List[AlertItem]
    today_summary: TodaySummary
    sales_trend: List[TrendPoint]
    inventory_health: InventoryHealth
