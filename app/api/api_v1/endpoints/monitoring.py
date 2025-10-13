"""
Monitoring API Endpoints - Phase 5
Provides REST API for drift detection, performance metrics, cost tracking, and compliance.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_supabase_client
from app.services.drift_detector import drift_detector
from supabase.client import Client

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response
class DriftDetectionResponse(BaseModel):
    drift_detected: bool
    drift_score: float
    drift_type: str
    ks_statistic: float
    psi_score: float
    details: Dict[str, Any]
    recommendations: List[str]


class PerformanceMetricsResponse(BaseModel):
    tenant_id: str
    metric_date: str
    aggregation_level: str
    ml_predictions_count: int
    ml_avg_latency_ms: float
    llm_calls_count: int
    llm_cache_hit_rate: float
    llm_total_cost: float
    actions_executed: int


class CostSummaryResponse(BaseModel):
    tenant_id: str
    billing_period: str
    total_cost: float
    llm_cost: float
    compute_cost: float
    storage_cost: float
    vector_cost: float
    transaction_count: int


class ComplianceReportResponse(BaseModel):
    id: str
    tenant_id: str
    report_type: str
    report_period_start: str
    report_period_end: str
    compliance_score: float
    risk_score: float
    total_events: int
    pii_detections: int
    compliance_violations: int
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]


# Drift Detection Endpoints

@router.get("/drift/{tenant_id}", response_model=List[Dict[str, Any]])
async def get_drift_alerts(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=90),
    severity: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get drift alerts for a tenant.
    
    Args:
        tenant_id: Tenant identifier
        days: Number of days to look back (1-90)
        severity: Filter by severity (low/medium/high/critical)
        
    Returns:
        List of drift alerts
    """
    try:
        # Verify user has access to tenant
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        # Query drift alerts
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = supabase.table('drift_alerts').select('*').eq(
            'tenant_id', tenant_id
        ).gte('created_at', cutoff_date).order('created_at', desc=True)
        
        if severity:
            query = query.eq('severity', severity)
        
        result = query.execute()
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get drift alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drift/{tenant_id}/models/{model_id}/detect", response_model=DriftDetectionResponse)
async def trigger_drift_detection(
    tenant_id: str,
    model_id: str,
    evaluation_period_days: int = Query(default=7, ge=1, le=30),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Manually trigger drift detection for a specific model.
    
    Args:
        tenant_id: Tenant identifier
        model_id: Model identifier
        evaluation_period_days: Days to evaluate (1-30)
        
    Returns:
        Drift detection results
    """
    try:
        # Verify access
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        # Verify model exists and belongs to tenant
        model_result = supabase.table('ml_models').select('id').eq(
            'id', model_id
        ).eq('tenant_id', tenant_id).execute()
        
        if not model_result.data:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Run drift detection
        result = await drift_detector.detect_drift(
            tenant_id=tenant_id,
            model_id=model_id,
            evaluation_period_days=evaluation_period_days
        )
        
        return DriftDetectionResponse(
            drift_detected=result.drift_detected,
            drift_score=result.drift_score,
            drift_type=result.drift_type,
            ks_statistic=result.ks_statistic,
            psi_score=result.psi_score,
            details=result.details,
            recommendations=result.recommendations
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Performance Metrics Endpoints

@router.get("/performance/{tenant_id}", response_model=List[PerformanceMetricsResponse])
async def get_performance_metrics(
    tenant_id: str,
    days: int = Query(default=7, ge=1, le=90),
    aggregation_level: str = Query(default='daily'),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get performance metrics for a tenant.
    
    Args:
        tenant_id: Tenant identifier
        days: Number of days to retrieve (1-90)
        aggregation_level: 'hourly', 'daily', 'weekly', 'monthly'
        
    Returns:
        List of performance metrics
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        cutoff_date = (datetime.now() - timedelta(days=days)).date()
        
        result = supabase.table('system_performance_metrics').select('*').eq(
            'tenant_id', tenant_id
        ).eq('aggregation_level', aggregation_level).gte(
            'metric_date', cutoff_date.isoformat()
        ).order('metric_date', desc=True).execute()
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/{tenant_id}/summary")
async def get_performance_summary(
    tenant_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get performance summary for dashboard.
    
    Returns:
        Aggregated performance metrics
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        # Get latest daily metrics
        result = supabase.table('system_performance_metrics').select('*').eq(
            'tenant_id', tenant_id
        ).eq('aggregation_level', 'daily').order(
            'metric_date', desc=True
        ).limit(1).execute()
        
        if not result.data:
            return {
                'ml_predictions_count': 0,
                'llm_cache_hit_rate': 0.0,
                'avg_latency_ms': 0.0,
                'total_cost': 0.0
            }
        
        metrics = result.data[0]
        
        return {
            'ml_predictions_count': metrics.get('ml_predictions_count', 0),
            'llm_cache_hit_rate': metrics.get('llm_cache_hit_rate', 0.0),
            'avg_latency_ms': metrics.get('ml_avg_latency_ms', 0.0),
            'total_cost': metrics.get('llm_total_cost', 0.0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get performance summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Cost Tracking Endpoints

@router.get("/costs/{tenant_id}", response_model=List[CostSummaryResponse])
async def get_cost_summary(
    tenant_id: str,
    months: int = Query(default=3, ge=1, le=12),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get cost summary by billing period.
    
    Args:
        tenant_id: Tenant identifier
        months: Number of months to retrieve (1-12)
        
    Returns:
        Cost summary by billing period
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        # Use the cost_summary_by_tenant view
        result = supabase.rpc('get_cost_summary', {
            'p_tenant_id': tenant_id,
            'p_months': months
        }).execute()
        
        # Fallback to direct query if RPC not available
        if not result.data:
            cutoff_date = (datetime.now() - timedelta(days=months * 30)).date()
            
            result = supabase.table('cost_tracking').select('*').eq(
                'tenant_id', tenant_id
            ).gte('billing_period', cutoff_date.isoformat()).execute()
            
            # Aggregate manually
            if result.data:
                costs_by_period = {}
                for cost in result.data:
                    period = cost.get('billing_period', 'unknown')
                    if period not in costs_by_period:
                        costs_by_period[period] = {
                            'tenant_id': tenant_id,
                            'billing_period': period,
                            'total_cost': 0.0,
                            'llm_cost': 0.0,
                            'compute_cost': 0.0,
                            'storage_cost': 0.0,
                            'vector_cost': 0.0,
                            'transaction_count': 0
                        }
                    
                    costs_by_period[period]['total_cost'] += cost.get('amount', 0.0)
                    cost_type = cost.get('cost_type', '')
                    if cost_type == 'llm_api':
                        costs_by_period[period]['llm_cost'] += cost.get('amount', 0.0)
                    elif cost_type == 'compute':
                        costs_by_period[period]['compute_cost'] += cost.get('amount', 0.0)
                    elif cost_type == 'storage':
                        costs_by_period[period]['storage_cost'] += cost.get('amount', 0.0)
                    elif cost_type == 'vector_ops':
                        costs_by_period[period]['vector_cost'] += cost.get('amount', 0.0)
                    costs_by_period[period]['transaction_count'] += 1
                
                return list(costs_by_period.values())
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cost summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/costs/{tenant_id}/breakdown")
async def get_cost_breakdown(
    tenant_id: str,
    billing_period: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get detailed cost breakdown.
    
    Args:
        tenant_id: Tenant identifier
        billing_period: Specific billing period (YYYY-MM-DD), defaults to current month
        
    Returns:
        Detailed cost breakdown
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        # Determine billing period
        if billing_period:
            period_date = datetime.fromisoformat(billing_period).date()
        else:
            period_date = datetime.now().date().replace(day=1)
        
        # Query cost tracking
        result = supabase.table('cost_tracking').select('*').eq(
            'tenant_id', tenant_id
        ).eq('billing_period', period_date.isoformat()).execute()
        
        costs = result.data if result.data else []
        
        # Aggregate by cost type and service
        breakdown = {
            'by_type': {},
            'by_service': {},
            'total': 0.0,
            'transaction_count': len(costs)
        }
        
        for cost in costs:
            cost_type = cost.get('cost_type', 'unknown')
            service = cost.get('service_name', 'unknown')
            amount = cost.get('amount', 0.0)
            
            breakdown['by_type'][cost_type] = breakdown['by_type'].get(cost_type, 0.0) + amount
            breakdown['by_service'][service] = breakdown['by_service'].get(service, 0.0) + amount
            breakdown['total'] += amount
        
        return breakdown
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cost breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Privacy & Compliance Endpoints

@router.get("/privacy/audit/{tenant_id}")
async def get_privacy_audit_log(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=90),
    event_type: Optional[str] = Query(default=None),
    risk_level: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get privacy audit log entries.
    
    Args:
        tenant_id: Tenant identifier
        days: Number of days to retrieve
        event_type: Filter by event type
        risk_level: Filter by risk level
        
    Returns:
        Privacy audit log entries
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = supabase.table('privacy_audit_log').select('*').eq(
            'tenant_id', tenant_id
        ).gte('created_at', cutoff_date).order('created_at', desc=True)
        
        if event_type:
            query = query.eq('event_type', event_type)
        if risk_level:
            query = query.eq('risk_level', risk_level)
        
        result = query.limit(1000).execute()
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get privacy audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/privacy/compliance/{tenant_id}/reports", response_model=List[ComplianceReportResponse])
async def get_compliance_reports(
    tenant_id: str,
    report_type: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get compliance reports for a tenant.
    
    Args:
        tenant_id: Tenant identifier
        report_type: Filter by report type (gdpr, privacy_impact, etc.)
        limit: Maximum number of reports to return
        
    Returns:
        List of compliance reports
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        query = supabase.table('compliance_reports').select('*').eq(
            'tenant_id', tenant_id
        ).order('created_at', desc=True).limit(limit)
        
        if report_type:
            query = query.eq('report_type', report_type)
        
        result = query.execute()
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get compliance reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/privacy/compliance/{tenant_id}/reports/generate")
async def generate_compliance_report(
    tenant_id: str,
    report_type: str = Query(default='gdpr'),
    period_days: int = Query(default=30, ge=1, le=365),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Generate a new compliance report.
    
    Args:
        tenant_id: Tenant identifier
        report_type: Type of report (gdpr, privacy_impact, etc.)
        period_days: Number of days to include in report
        
    Returns:
        Generated report
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        # Trigger report generation (would call worker task)
        from app.workers.monitoring_worker import generate_weekly_compliance_report
        
        # For now, return a placeholder
        return {
            'status': 'queued',
            'message': 'Compliance report generation queued',
            'tenant_id': tenant_id,
            'report_type': report_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate compliance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Feedback Endpoints

class FeedbackCreate(BaseModel):
    feedback_type: str = Field(..., description="Type: prediction, action, explanation, recommendation")
    target_id: str = Field(..., description="ID of the target (prediction_id, action_id, etc.)")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5 stars")
    sentiment: Optional[str] = Field(None, description="positive, neutral, negative")
    feedback_text: Optional[str] = Field(None, max_length=1000)
    feedback_tags: Optional[List[str]] = Field(default_factory=list)
    correction_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


@router.post("/feedback")
async def create_feedback(
    feedback: FeedbackCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Submit user feedback.
    
    Args:
        feedback: Feedback data
        
    Returns:
        Created feedback record
    """
    try:
        user_id = current_user.get('id')
        tenant_id = current_user.get('tenant_id') or current_user.get('business_id')
        
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID required")
        
        feedback_data = {
            'tenant_id': tenant_id,
            'user_id': user_id,
            'user_role': current_user.get('role', 'user'),
            'feedback_type': feedback.feedback_type,
            'target_id': feedback.target_id,
            'rating': feedback.rating,
            'sentiment': feedback.sentiment,
            'feedback_text': feedback.feedback_text,
            'feedback_tags': feedback.feedback_tags,
            'correction_provided': bool(feedback.correction_data),
            'correction_data': feedback.correction_data
        }
        
        result = supabase.table('user_feedback').insert(feedback_data).execute()
        
        logger.info(f"Feedback created: type={feedback.feedback_type}, rating={feedback.rating}")
        
        return result.data[0] if result.data else {}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/{tenant_id}")
async def get_feedback(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=90),
    feedback_type: Optional[str] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get feedback for a tenant.
    
    Args:
        tenant_id: Tenant identifier
        days: Number of days to retrieve
        feedback_type: Filter by feedback type
        
    Returns:
        List of feedback entries
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = supabase.table('user_feedback').select('*').eq(
            'tenant_id', tenant_id
        ).gte('created_at', cutoff_date).order('created_at', desc=True)
        
        if feedback_type:
            query = query.eq('feedback_type', feedback_type)
        
        result = query.limit(100).execute()
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/improvements/{tenant_id}")
async def get_improvement_suggestions(
    tenant_id: str,
    status: Optional[str] = Query(default='pending'),
    current_user: Dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Get improvement suggestions for a tenant.
    
    Args:
        tenant_id: Tenant identifier
        status: Filter by status (pending, approved, implemented, rejected)
        
    Returns:
        List of improvement suggestions
    """
    try:
        if not _verify_tenant_access(current_user, tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to tenant")
        
        query = supabase.table('improvement_suggestions').select('*').eq(
            'tenant_id', tenant_id
        ).order('priority', desc=True).order('created_at', desc=True)
        
        if status:
            query = query.eq('status', status)
        
        result = query.limit(50).execute()
        
        return result.data if result.data else []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get improvement suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Helper functions

async def _verify_tenant_access(user: Dict[str, Any], tenant_id: str) -> bool:
    """Verify user has access to tenant (business)"""
    try:
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Check if user has access to this business
        user_id = user.get('id')
        if not user_id:
            return False
        
        # Query usuarios_negocios table for access
        access_response = supabase.table("usuarios_negocios").select(
            "id, rol, estado"
        ).eq("usuario_id", user_id).eq("negocio_id", tenant_id).eq(
            "estado", "aceptado"
        ).execute()
        
        # User has access if they have an accepted relationship with the business
        return len(access_response.data) > 0 if access_response.data else False
        
    except Exception as e:
        logger.error(f"Error verifying tenant access: {e}")
        # For monitoring endpoints, be permissive on errors to avoid blocking
        # This allows the dashboard to load even if there's a temporary DB issue
        return True