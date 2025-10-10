#!/usr/bin/env python
"""
Phase 1–4 verification runner.

Performs:
- Table existence checks (Vector, LLM, Action System)
- Inserts tenant_action_settings for testing
- Phase 2: Embedding store + vector stats
- Phase 3: LLM Reasoning with simulated actions (async_call=False)
- Phase 4: Reads action_executions and action_approvals for the test tenant

Requirements:
- Redis running (for Celery/Cache where applicable)
- Supabase credentials in .env
- Migrations applied (as per scripts already executed)

Run:
  python scripts/phase_tests_runner.py
"""

import json
import asyncio
import os
import sys
from typing import Any, Dict

# Ensure project root is on sys.path so 'app' package imports resolve when executed as a script
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db.supabase_client import get_supabase_service_client
from app.services.ml.embedding_pipeline import EmbeddingPipeline, EmbeddingConfig
from app.services.ml.vector_db_service import VectorDBService
from app.services.llm_reasoning_service import LLMReasoningService


async def main() -> None:
    output: Dict[str, Any] = {}
    svc = get_supabase_service_client()

    def table_ok(name: str) -> Dict[str, Any]:
        try:
            res = svc.table(name).select("*").limit(1).execute()
            return {"ok": True, "sample_present": 0 if not res.data else 1}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # Phase 2/3/4 required tables
    tables = [
        # Vector
        "vector_embeddings",
        "embedding_queue",
        "pii_protection_log",
        "vector_search_logs",
        # LLM
        "tenant_llm_settings",
        "prompt_templates",
        "llm_responses",
        "llm_cache",
        "llm_review_queue",
        "llm_feedback_examples",
        # Actions
        "action_definitions",
        "tenant_action_settings",
        "action_executions",
        "action_approvals",
        "action_audit_log",
    ]

    output["tables"] = {t: table_ok(t) for t in tables}

    # Use a demo tenant for end-to-end test
    tenant_id = "tenant_demo"

    # Ensure action system settings for the tenant (enable automation for testing)
    try:
        svc.table("tenant_action_settings").upsert(
            {
                "tenant_id": tenant_id,
                "automation_enabled": True,
                "approval_required": True,  # keep approvals to validate Phase 4 flow
                "auto_approval_threshold": 0.8,
                "max_actions_per_hour": 100,
                "max_actions_per_day": 1000,
                "allowed_action_types": [
                    "create_task",
                    "send_notification",
                    "generate_report",
                    "update_inventory",
                ],
                "canary_percentage": 1.0,  # execute 100% for testing
                "safety_mode": "moderate",
                "notification_on_auto_action": True,
            },
            on_conflict="tenant_id",
        ).execute()
        output["tenant_settings_upsert"] = "ok"
    except Exception as e:
        output["tenant_settings_upsert"] = f"error: {e}"

    # Phase 2: store an embedding immediately (skip queue)
    embedding_result: Dict[str, Any]
    try:
        ep = EmbeddingPipeline(EmbeddingConfig())
        embedding_result_obj = await ep.process_content(
            tenant_id=tenant_id,
            content="Ejemplo base de conocimiento para verificación vectorial",
            content_type="product_description",
            content_id="demo-1",
            skip_queue=True,
        )
        embedding_result = {
            "success": embedding_result_obj.success,
            "error": embedding_result_obj.error_message,
            "vector_id": embedding_result_obj.vector_id,
        }
    except Exception as e:
        embedding_result = {"success": False, "error": str(e), "vector_id": None}
    output["embedding_store"] = embedding_result

    # Phase 2: vector stats
    try:
        vdb = VectorDBService()
        output["vector_stats"] = await vdb.get_tenant_statistics(tenant_id)
    except Exception as e:
        output["vector_stats"] = {"error": str(e)}

    # Phase 3: LLM Reasoning (simulated vendor, but full orchestration/caching/actions)
    try:
        svc_llm = LLMReasoningService()
        prediction = {
            "prediction_type": "sales_anomaly",
            "anomaly_score": 0.85,
            "context": {"period": "2025-09"},
        }
        llm_res = await svc_llm.reason(
            tenant_id=tenant_id,
            prediction_id="pred_123",
            prediction_data=prediction,
            impact_score=0.8,
            async_call=False,  # run synchronously to inspect action creations
        )
        output["llm_reasoning"] = llm_res
    except Exception as e:
        output["llm_reasoning"] = {"status": "error", "error": str(e)}

    # Phase 4: fetch latest action executions and approvals for the tenant
    def fetch_rows(name: str) -> Any:
        try:
            res = (
                svc.table(name)
                .select("*")
                .eq("tenant_id", tenant_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            return res.data or []
        except Exception as e:
            return [{"error": str(e)}]

    output["action_executions"] = fetch_rows("action_executions")
    output["action_approvals"] = fetch_rows("action_approvals")

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())