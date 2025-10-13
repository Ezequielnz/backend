"""
Monitoring Worker - Phase 5
Celery tasks for drift detection, metric aggregation, compliance reporting, and feedback processing.
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from celery import Task

from app.celery_app import celery_app
from app.services.drift_detector import drift_detector
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, soft_time_limit=300, time_limit=600)
def detect_drift_all_models(self: Task) -> Dict[str, Any]:
    """
    Periodic task to detect drift for all active models.
    Runs daily at 2 AM.
    
    Returns:
        Summary of drift detection results
    """
    try:
        logger.info("Starting drift detection for all active models")
        supabase = get_supabase_client()
        
        # Get all active models
        result = supabase.table('ml_models').select(
            'id, tenant_id, model_type, model_version'
        ).eq('is_active', True).execute()
        
        if not result.data:
            logger.info("No active models found for drift detection")
            return {'status': 'success', 'models_checked': 0, 'drift_detected': 0}
        
        models = result.data
        drift_detected_count = 0
        results = []
        
        for model in models:
            try:
                # Run drift detection (async)
                loop = asyncio.get_event_loop()
                drift_result = loop.run_until_complete(
                    drift_detector.detect_drift(
                        tenant_id=model['tenant_id'],
                        model_id=model['id'],
                        evaluation_period_days=7
                    )
                )
                
                if drift_result.drift_detected:
                    drift_detected_count += 1
                    logger.warning(
                        f"Drift detected for model {model['id']}: "
                        f"score={drift_result.drift_score:.3f}, type={drift_result.drift_type}"
                    )
                
                results.append({
                    'model_id': model['id'],
                    'tenant_id': model['tenant_id'],
                    'drift_detected': drift_result.drift_detected,
                    'drift_score': drift_result.drift_score,
                    'drift_type': drift_result.drift_type
                })
                
            except Exception as e:
                logger.error(f"Drift detection failed for model {model['id']}: {e}")
                results.append({
                    'model_id': model['id'],
                    'error': str(e)
                })
        
        summary = {
            'status': 'success',
            'models_checked': len(models),
            'drift_detected': drift_detected_count,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(
            f"Drift detection completed: {len(models)} models checked, "
            f"{drift_detected_count} drift detected"
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Drift detection task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, soft_time_limit=180, time_limit=300)
def aggregate_hourly_metrics(self: Task, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate performance metrics for the last hour.
    Runs every hour.
    
    Args:
        tenant_id: Optional tenant filter, aggregates all if None
        
    Returns:
        Summary of aggregation results
    """
    try:
        logger.info(f"Starting hourly metric aggregation for tenant: {tenant_id or 'all'}")
        supabase = get_supabase_client()
        
        # Calculate time window
        now = datetime.now()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        
        # Get tenants to process
        if tenant_id:
            tenants = [tenant_id]
        else:
            # Get all active tenants
            result = supabase.table('negocios').select('id').execute()
            tenants = [b['id'] for b in result.data] if result.data else []
        
        aggregated_count = 0
        
        for tid in tenants:
            try:
                # Aggregate ML metrics (sync for now)
                ml_metrics = _aggregate_ml_metrics_sync(tid, hour_start, hour_end)
                
                # Aggregate LLM metrics
                llm_metrics = _aggregate_llm_metrics_sync(tid, hour_start, hour_end)
                
                # Aggregate vector metrics
                vector_metrics = _aggregate_vector_metrics_sync(tid, hour_start, hour_end)
                
                # Aggregate action metrics
                action_metrics = _aggregate_action_metrics_sync(tid, hour_start, hour_end)
                
                # Store aggregated metrics
                metrics_data = {
                    'tenant_id': tid,
                    'metric_date': hour_start.date().isoformat(),
                    'metric_hour': hour_start.hour,
                    'aggregation_level': 'hourly',
                    **ml_metrics,
                    **llm_metrics,
                    **vector_metrics,
                    **action_metrics
                }
                
                supabase.table('system_performance_metrics').upsert(
                    metrics_data,
                    on_conflict='tenant_id,metric_date,metric_hour,aggregation_level'
                ).execute()
                
                aggregated_count += 1
                
            except Exception as e:
                logger.error(f"Metric aggregation failed for tenant {tid}: {e}")
        
        logger.info(f"Hourly metric aggregation completed: {aggregated_count} tenants processed")
        
        return {
            'status': 'success',
            'tenants_processed': aggregated_count,
            'hour': hour_start.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Hourly metric aggregation task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, soft_time_limit=600, time_limit=900)
def generate_weekly_compliance_report(self: Task, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate weekly privacy compliance reports.
    Runs every Monday at 3 AM.
    
    Args:
        tenant_id: Optional tenant filter
        
    Returns:
        Summary of report generation
    """
    try:
        logger.info(f"Starting weekly compliance report generation for tenant: {tenant_id or 'all'}")
        supabase = get_supabase_client()
        
        # Calculate report period (last 7 days)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)
        
        # Get tenants
        if tenant_id:
            tenants = [tenant_id]
        else:
            result = supabase.table('negocios').select('id').execute()
            tenants = [b['id'] for b in result.data] if result.data else []
        
        reports_generated = 0
        
        for tid in tenants:
            try:
                # Query privacy audit log for the period
                audit_result = supabase.table('privacy_audit_log').select('*').eq(
                    'tenant_id', tid
                ).gte(
                    'created_at', start_date.isoformat()
                ).lte(
                    'created_at', end_date.isoformat()
                ).execute()
                
                events = audit_result.data if audit_result.data else []
                
                # Calculate metrics
                total_events = len(events)
                pii_detections = sum(1 for e in events if e.get('event_type') == 'pii_detected')
                compliance_violations = sum(1 for e in events if not e.get('gdpr_compliant', True))
                high_risk_events = sum(1 for e in events if e.get('risk_level') in ['high', 'critical'])
                
                # Calculate compliance score (0-100)
                compliance_score = 100.0
                if total_events > 0:
                    violation_rate = compliance_violations / total_events
                    compliance_score = max(0, 100 - (violation_rate * 100))
                
                # Calculate risk score (0-100)
                risk_score = 0.0
                if total_events > 0:
                    risk_rate = high_risk_events / total_events
                    risk_score = min(100, risk_rate * 100)
                
                # Generate findings
                findings = []
                if compliance_violations > 0:
                    findings.append({
                        'type': 'violation',
                        'count': compliance_violations,
                        'description': f'{compliance_violations} GDPR compliance violations detected'
                    })
                if high_risk_events > 0:
                    findings.append({
                        'type': 'high_risk',
                        'count': high_risk_events,
                        'description': f'{high_risk_events} high-risk privacy events'
                    })
                
                # Generate recommendations
                recommendations = []
                if compliance_score < 95:
                    recommendations.append('Review PII handling procedures')
                if risk_score > 20:
                    recommendations.append('Implement additional privacy controls')
                if pii_detections > 100:
                    recommendations.append('Consider automated PII redaction')
                
                # Create report
                report_data = {
                    'tenant_id': tid,
                    'report_type': 'gdpr',
                    'report_period_start': start_date.isoformat(),
                    'report_period_end': end_date.isoformat(),
                    'total_events': total_events,
                    'pii_detections': pii_detections,
                    'compliance_violations': compliance_violations,
                    'high_risk_events': high_risk_events,
                    'compliance_score': compliance_score,
                    'risk_score': risk_score,
                    'summary': f'Weekly compliance report for {start_date} to {end_date}',
                    'findings': findings,
                    'recommendations': recommendations,
                    'report_data': {
                        'events_by_type': _count_by_field(events, 'event_type'),
                        'pii_types_detected': _count_by_field(events, 'pii_types'),
                        'risk_distribution': _count_by_field(events, 'risk_level')
                    }
                }
                
                supabase.table('compliance_reports').insert(report_data).execute()
                reports_generated += 1
                
                logger.info(
                    f"Compliance report generated for tenant {tid}: "
                    f"score={compliance_score:.1f}, risk={risk_score:.1f}"
                )
                
            except Exception as e:
                logger.error(f"Report generation failed for tenant {tid}: {e}")
        
        return {
            'status': 'success',
            'reports_generated': reports_generated,
            'period': f'{start_date} to {end_date}'
        }
        
    except Exception as e:
        logger.error(f"Weekly compliance report task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, soft_time_limit=300, time_limit=600)
def process_feedback_batch(self: Task, batch_size: int = 100) -> Dict[str, Any]:
    """
    Process unprocessed user feedback and generate improvement suggestions.
    Runs every 6 hours.
    
    Args:
        batch_size: Number of feedback items to process
        
    Returns:
        Summary of processing results
    """
    try:
        logger.info(f"Starting feedback processing batch (size: {batch_size})")
        supabase = get_supabase_client()
        
        # Get unprocessed feedback
        result = supabase.table('user_feedback').select('*').eq(
            'processed', False
        ).order('created_at', desc=False).limit(batch_size).execute()
        
        if not result.data:
            logger.info("No unprocessed feedback found")
            return {'status': 'success', 'processed': 0, 'suggestions_created': 0}
        
        feedback_items = result.data
        processed_count = 0
        suggestions_created = 0
        
        # Group feedback by type and target
        feedback_groups = _group_feedback(feedback_items)
        
        for group_key, items in feedback_groups.items():
            try:
                # Analyze feedback group
                analysis = _analyze_feedback_group(items)
                
                # Generate improvement suggestion if needed
                if analysis['should_create_suggestion']:
                    suggestion_data = {
                        'tenant_id': items[0]['tenant_id'],
                        'suggestion_type': analysis['suggestion_type'],
                        'priority': analysis['priority'],
                        'issue_identified': analysis['issue'],
                        'root_cause_analysis': analysis['root_cause'],
                        'expected_improvement': analysis['expected_improvement'],
                        'confidence_score': analysis['confidence'],
                        'recommendation': analysis['recommendation'],
                        'implementation_steps': analysis['steps'],
                        'estimated_effort': analysis['effort'],
                        'supporting_metrics': analysis['metrics'],
                        'related_feedback_ids': [item['id'] for item in items]
                    }
                    
                    supabase.table('improvement_suggestions').insert(suggestion_data).execute()
                    suggestions_created += 1
                    
                    logger.info(
                        f"Improvement suggestion created: type={analysis['suggestion_type']}, "
                        f"priority={analysis['priority']}"
                    )
                
                # Mark feedback as processed
                feedback_ids = [item['id'] for item in items]
                supabase.table('user_feedback').update({
                    'processed': True,
                    'processing_notes': analysis.get('notes', 'Processed in batch')
                }).in_('id', feedback_ids).execute()
                
                processed_count += len(items)
                
            except Exception as e:
                logger.error(f"Feedback processing failed for group {group_key}: {e}")
        
        logger.info(
            f"Feedback processing completed: {processed_count} items processed, "
            f"{suggestions_created} suggestions created"
        )
        
        return {
            'status': 'success',
            'processed': processed_count,
            'suggestions_created': suggestions_created
        }
        
    except Exception as e:
        logger.error(f"Feedback processing task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, soft_time_limit=180, time_limit=300)
def check_partitioning_needs(self: Task) -> Dict[str, Any]:
    """
    Check if tables need partitioning based on size thresholds.
    Runs daily at 4 AM.
    
    Returns:
        Summary of partitioning checks
    """
    try:
        logger.info("Checking partitioning needs for monitored tables")
        supabase = get_supabase_client()
        
        # Get partition management configuration
        result = supabase.table('partition_management').select('*').execute()
        
        if not result.data:
            logger.info("No tables configured for partition management")
            return {'status': 'success', 'tables_checked': 0, 'partitioning_needed': 0}
        
        tables = result.data
        partitioning_needed = []
        
        for table_config in tables:
            try:
                table_name = table_config['table_name']
                
                # Get table size and row count
                try:
                    size_result = supabase.rpc('get_table_size', {'table_name': table_name}).execute()
                    size_gb = size_result.data if size_result.data else 0
                except Exception:
                    size_gb = 0  # RPC might not exist yet
                
                try:
                    count_result = supabase.table(table_name).select('id').execute()
                    row_count = len(count_result.data) if count_result.data else 0
                except Exception:
                    row_count = 0
                
                # Check thresholds
                size_threshold = table_config['size_threshold_gb']
                row_threshold = table_config['row_count_threshold']
                
                needs_partitioning = (
                    size_gb >= size_threshold or 
                    row_count >= row_threshold
                ) and not table_config['is_partitioned']
                
                if needs_partitioning:
                    partitioning_needed.append({
                        'table_name': table_name,
                        'current_size_gb': size_gb,
                        'current_rows': row_count,
                        'size_threshold_gb': size_threshold,
                        'row_threshold': row_threshold
                    })
                    
                    logger.warning(
                        f"Table {table_name} needs partitioning: "
                        f"size={size_gb:.2f}GB (threshold={size_threshold}GB), "
                        f"rows={row_count} (threshold={row_threshold})"
                    )
                
            except Exception as e:
                logger.error(f"Partitioning check failed for table {table_config['table_name']}: {e}")
        
        # Log summary
        if partitioning_needed:
            logger.warning(
                f"Partitioning needed for {len(partitioning_needed)} tables: "
                f"{[t['table_name'] for t in partitioning_needed]}"
            )
        
        return {
            'status': 'success',
            'tables_checked': len(tables),
            'partitioning_needed': len(partitioning_needed),
            'tables': partitioning_needed
        }
        
    except Exception as e:
        logger.error(f"Partitioning check task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, soft_time_limit=120, time_limit=240)
def aggregate_daily_metrics(self: Task, date: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate daily metrics from hourly data.
    Runs daily at 1 AM for previous day.
    
    Args:
        date: Date to aggregate (YYYY-MM-DD), defaults to yesterday
        
    Returns:
        Summary of aggregation
    """
    try:
        # Determine date to aggregate
        if date:
            target_date = datetime.fromisoformat(date).date()
        else:
            target_date = (datetime.now() - timedelta(days=1)).date()
        
        logger.info(f"Starting daily metric aggregation for {target_date}")
        supabase = get_supabase_client()
        
        # Get all tenants
        result = supabase.table('negocios').select('id').execute()
        tenants = [b['id'] for b in result.data] if result.data else []
        
        aggregated_count = 0
        
        for tenant_id in tenants:
            try:
                # Get hourly metrics for the day
                hourly_result = supabase.table('system_performance_metrics').select('*').eq(
                    'tenant_id', tenant_id
                ).eq('metric_date', target_date.isoformat()).eq(
                    'aggregation_level', 'hourly'
                ).execute()
                
                if not hourly_result.data:
                    continue
                
                hourly_metrics = hourly_result.data
                
                # Aggregate metrics
                daily_data = {
                    'tenant_id': tenant_id,
                    'metric_date': target_date.isoformat(),
                    'metric_hour': None,
                    'aggregation_level': 'daily',
                    'ml_predictions_count': sum(m.get('ml_predictions_count', 0) for m in hourly_metrics),
                    'ml_avg_latency_ms': _safe_avg([m.get('ml_avg_latency_ms') for m in hourly_metrics]),
                    'ml_p95_latency_ms': _safe_max([m.get('ml_p95_latency_ms') for m in hourly_metrics]),
                    'ml_error_rate': _safe_avg([m.get('ml_error_rate') for m in hourly_metrics]),
                    'llm_calls_count': sum(m.get('llm_calls_count', 0) for m in hourly_metrics),
                    'llm_avg_latency_ms': _safe_avg([m.get('llm_avg_latency_ms') for m in hourly_metrics]),
                    'llm_cache_hit_rate': _safe_avg([m.get('llm_cache_hit_rate') for m in hourly_metrics]),
                    'llm_total_tokens': sum(m.get('llm_total_tokens', 0) for m in hourly_metrics),
                    'llm_total_cost': sum(m.get('llm_total_cost', 0) for m in hourly_metrics),
                    'vector_embeddings_created': sum(m.get('vector_embeddings_created', 0) for m in hourly_metrics),
                    'vector_searches_count': sum(m.get('vector_searches_count', 0) for m in hourly_metrics),
                    'actions_executed': sum(m.get('actions_executed', 0) for m in hourly_metrics),
                    'actions_auto_approved': sum(m.get('actions_auto_approved', 0) for m in hourly_metrics),
                    'actions_failed': sum(m.get('actions_failed', 0) for m in hourly_metrics),
                }
                
                supabase.table('system_performance_metrics').upsert(
                    daily_data,
                    on_conflict='tenant_id,metric_date,metric_hour,aggregation_level'
                ).execute()
                
                aggregated_count += 1
                
            except Exception as e:
                logger.error(f"Daily aggregation failed for tenant {tenant_id}: {e}")
        
        logger.info(f"Daily metric aggregation completed: {aggregated_count} tenants processed")
        
        return {
            'status': 'success',
            'date': target_date.isoformat(),
            'tenants_processed': aggregated_count
        }
        
    except Exception as e:
        logger.error(f"Daily metric aggregation task failed: {e}")
        return {'status': 'error', 'error': str(e)}


# Helper functions

def _aggregate_ml_metrics_sync(tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Aggregate ML pipeline metrics for time window"""
    # Simplified - would query ml_predictions and calculate metrics
    return {
        'ml_predictions_count': 0,
        'ml_avg_latency_ms': 0.0,
        'ml_p95_latency_ms': 0.0,
        'ml_error_rate': 0.0
    }


def _aggregate_llm_metrics_sync(tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Aggregate LLM metrics for time window"""
    # Simplified - would query llm_responses and calculate metrics
    return {
        'llm_calls_count': 0,
        'llm_avg_latency_ms': 0.0,
        'llm_cache_hit_rate': 0.0,
        'llm_total_tokens': 0,
        'llm_total_cost': 0.0
    }


def _aggregate_vector_metrics_sync(tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Aggregate vector operation metrics for time window"""
    # Simplified - would query vector_embeddings and vector_search_logs
    return {
        'vector_embeddings_created': 0,
        'vector_searches_count': 0,
        'vector_avg_search_latency_ms': 0.0
    }


def _aggregate_action_metrics_sync(tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Aggregate action system metrics for time window"""
    # Simplified - would query action_executions
    return {
        'actions_executed': 0,
        'actions_auto_approved': 0,
        'actions_manual_approved': 0,
        'actions_rejected': 0,
        'actions_failed': 0
    }


def _group_feedback(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group feedback by type and target"""
    groups = {}
    for item in items:
        key = f"{item.get('feedback_type', 'unknown')}:{item.get('target_id', 'none')}"
        if key not in groups:
            groups[key] = []
        groups[key].append(item)
    return groups


def _analyze_feedback_group(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze a group of feedback items and determine if suggestion needed"""
    # Calculate average rating
    ratings = [item.get('rating', 3) for item in items if item.get('rating')]
    avg_rating = sum(ratings) / len(ratings) if ratings else 3.0
    
    # Count negative feedback
    negative_count = sum(1 for item in items if item.get('sentiment') == 'negative')
    negative_rate = negative_count / len(items) if items else 0
    
    # Determine if suggestion needed
    should_create = avg_rating < 3.0 or negative_rate > 0.3
    
    # Determine suggestion type based on feedback type
    feedback_type = items[0].get('feedback_type', 'unknown')
    suggestion_type_map = {
        'prediction': 'model_retrain',
        'action': 'config_change',
        'explanation': 'prompt_optimization',
        'recommendation': 'feature_engineering'
    }
    suggestion_type = suggestion_type_map.get(feedback_type, 'config_change')
    
    # Determine priority
    if avg_rating < 2.0 or negative_rate > 0.5:
        priority = 'high'
    elif avg_rating < 3.0 or negative_rate > 0.3:
        priority = 'medium'
    else:
        priority = 'low'
    
    return {
        'should_create_suggestion': should_create,
        'suggestion_type': suggestion_type,
        'priority': priority,
        'issue': f'Low user satisfaction: avg rating {avg_rating:.1f}/5',
        'root_cause': f'{negative_count} negative feedback items out of {len(items)}',
        'expected_improvement': 0.15,
        'confidence': 0.7,
        'recommendation': f'Review and improve {feedback_type} quality',
        'steps': [
            'Analyze negative feedback patterns',
            'Identify common issues',
            'Implement improvements',
            'A/B test changes'
        ],
        'effort': 'medium',
        'metrics': {
            'avg_rating': avg_rating,
            'negative_rate': negative_rate,
            'sample_size': len(items)
        },
        'notes': f'Processed {len(items)} feedback items'
    }


def _count_by_field(items: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    """Count occurrences of field values"""
    counts = {}
    for item in items:
        value = item.get(field)
        if isinstance(value, list):
            for v in value:
                counts[str(v)] = counts.get(str(v), 0) + 1
        elif value:
            counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _safe_avg(values: List[Optional[float]]) -> float:
    """Calculate average, handling None values"""
    valid_values = [v for v in values if v is not None]
    return sum(valid_values) / len(valid_values) if valid_values else 0.0


def _safe_max(values: List[Optional[float]]) -> float:
    """Calculate max, handling None values"""
    valid_values = [v for v in values if v is not None]
    return max(valid_values) if valid_values else 0.0