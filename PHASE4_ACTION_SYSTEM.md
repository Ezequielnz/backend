# Phase 4: Action System — Safe Automated Action Execution

## Overview

Phase 4 introduces a comprehensive **Action System** that enables safe, automated execution of actions recommended by the LLM reasoning engine. The system provides multiple layers of safety controls, gradual rollout capabilities, and human oversight to mitigate automation risks.

## Key Features

### 🛡️ Safety-First Design
- **Manual Approval Gates**: All automations require approval unless explicitly configured otherwise
- **Impact Assessment**: Pre-execution analysis of action consequences
- **Rollback Capabilities**: Ability to reverse actions when supported
- **Circuit Breaker Protection**: Automatic halting of failing action types

### 📊 Gradual Rollout Controls
- **Canary Deployment**: Percentage-based activation (0-100%)
- **Tenant-Specific Settings**: Individual control per business
- **Safety Modes**: Strict, Moderate, and Permissive configurations

### 👁️ Human Oversight
- **Approval Queues**: Manual review for high-risk or uncertain actions
- **Audit Logging**: Complete traceability of all automated activities
- **Override Options**: Users can manually intervene in automation

## Architecture

### Core Components

```
LLM Response → Action Parser → Safe Action Engine → Approval Gate → Action Worker → Execution
                        ↓              ↓                    ↓              ↓
                   Validation    Impact Assessment    Manual Review   Circuit Breaker
```

#### 1. Action Parser (`app/services/action_parser.py`)
**Purpose**: Extracts structured actions from LLM responses

**Features**:
- JSON and text-based action parsing
- Parameter validation against schemas
- Confidence scoring and reasoning extraction
- Support for multiple action types

**Supported Actions**:
- `create_task`: Create new tasks in the system
- `send_notification`: Send alerts to users/teams
- `update_inventory`: Adjust product stock levels
- `generate_report`: Create business reports

#### 2. Safe Action Engine (`app/services/safe_action_engine.py`)
**Purpose**: Orchestrates safe action execution with comprehensive controls

**Key Methods**:
- `process_actions_from_llm_response()`: Main entry point for processing LLM actions
- `approve_action()` / `reject_action()`: Manual approval workflow
- `rollback_action()`: Reverse completed actions
- `_assess_impact()`: Pre-execution risk analysis

**Safety Controls**:
- Tenant isolation and permission checks
- Budget and rate limiting
- Action type filtering
- Confidence threshold enforcement

#### 3. Action Worker (`app/workers/action_worker.py`)
**Purpose**: Asynchronous execution with retry logic and monitoring

**Features**:
- Celery-based task processing
- Automatic retry with exponential backoff
- Circuit breaker integration
- Periodic maintenance tasks

#### 4. API Endpoints (`app/api/api_v1/endpoints/action.py`)
**Purpose**: REST API for action management and monitoring

**Endpoints**:
- `GET /api/v1/actions/executions` - List action executions
- `POST /api/v1/actions/executions/{id}/approve` - Approve action
- `POST /api/v1/actions/executions/{id}/reject` - Reject action
- `GET /api/v1/actions/approvals` - Get pending approvals
- `GET /api/v1/actions/settings` - Get tenant settings

## Database Schema

### Core Tables

#### `action_definitions`
Defines available action types and their configurations.

```sql
CREATE TABLE action_definitions (
    id UUID PRIMARY KEY,
    action_type TEXT UNIQUE,
    name TEXT,
    description TEXT,
    category TEXT,
    requires_approval BOOLEAN,
    impact_level TEXT,
    rollback_supported BOOLEAN,
    config_schema JSONB,
    ui_component TEXT,
    is_active BOOLEAN
);
```

#### `tenant_action_settings`
Tenant-specific automation preferences.

```sql
CREATE TABLE tenant_action_settings (
    tenant_id TEXT PRIMARY KEY,
    automation_enabled BOOLEAN,
    approval_required BOOLEAN,
    auto_approval_threshold FLOAT,
    max_actions_per_hour INT,
    max_actions_per_day INT,
    allowed_action_types TEXT[],
    canary_percentage FLOAT,
    safety_mode TEXT,
    notification_on_auto_action BOOLEAN
);
```

#### `action_executions`
Records all action execution attempts.

```sql
CREATE TABLE action_executions (
    id UUID PRIMARY KEY,
    tenant_id TEXT,
    prediction_id UUID,
    llm_response_id UUID,
    action_definition_id UUID,
    action_type TEXT,
    action_params JSONB,
    execution_status TEXT,
    approval_status TEXT,
    confidence_score FLOAT,
    executed_at TIMESTAMP,
    execution_result JSONB,
    error_message TEXT
);
```

#### `action_approvals`
Manual approval queue for actions.

```sql
CREATE TABLE action_approvals (
    id UUID PRIMARY KEY,
    tenant_id TEXT,
    execution_id UUID,
    action_type TEXT,
    action_description TEXT,
    confidence_score FLOAT,
    status TEXT,
    expires_at TIMESTAMP
);
```

## Configuration

### Environment Variables

```bash
# Action System Settings
ACTION_SYSTEM_ENABLED=true
ACTION_DEFAULT_SAFETY_MODE=strict
ACTION_MAX_RETRY_ATTEMPTS=3
ACTION_CIRCUIT_BREAKER_THRESHOLD=5
ACTION_CIRCUIT_BREAKER_TIMEOUT=120

# Tenant Default Settings
TENANT_AUTO_APPROVAL_THRESHOLD=0.9
TENANT_MAX_ACTIONS_PER_HOUR=10
TENANT_MAX_ACTIONS_PER_DAY=50
TENANT_CANARY_PERCENTAGE=0.0
```

### Tenant Settings

Each tenant can configure:

- **Automation Enabled**: Master switch for action automation
- **Approval Required**: Whether manual approval is needed
- **Auto-Approval Threshold**: Minimum confidence for automatic execution
- **Rate Limits**: Maximum actions per hour/day
- **Allowed Action Types**: Which actions are permitted
- **Canary Percentage**: Gradual rollout control (0.0-1.0)
- **Safety Mode**: Strict/Moderate/Permissive

## Safety Mechanisms

### 1. Approval Gates

**Automatic Approval**:
- Actions with confidence ≥ threshold AND approval not required
- Low-impact actions (notifications, reports)
- Pre-approved action types

**Manual Approval Required**:
- High-impact actions (inventory updates)
- Low-confidence recommendations
- First-time action types for tenant
- Actions exceeding rate limits

### 2. Impact Assessment

Pre-execution analysis considers:
- **Risk Level**: Low/Medium/High/Critical
- **Affected Resources**: What systems/data will be modified
- **Rollback Possibility**: Can the action be reversed
- **Estimated Duration**: How long the action will take

### 3. Rate Limiting

- **Per-Tenant Limits**: Actions per hour/day
- **Global Circuit Breakers**: Halt automation if error rates are high
- **Action-Type Limits**: Specific limits per action category

### 4. Rollback Capabilities

Supported for:
- Task creation (delete created task)
- Inventory updates (reverse stock changes)
- Notifications (limited - can't "un-send")

Not supported for:
- Report generation (reports remain for audit)
- External system calls (emails, etc.)

## User Interface

### Action Dashboard (`src/components/dashboard/ActionDashboard.jsx`)

**Features**:
- Real-time action execution monitoring
- Approval queue management
- Automation status indicators
- Historical action logs
- Configuration management

**Tabs**:
1. **Overview**: Status cards, automation health, recent activity
2. **Executions**: Detailed execution history with filtering
3. **Approvals**: Pending manual approvals with one-click actions
4. **Settings**: Tenant-specific automation configuration

### Automation Status Indicator (`src/components/AutomationStatusIndicator.jsx`)

**Visual States**:
- 🔴 **Disabled**: Automation off, manual mode only
- 🟡 **Canary**: Partial activation with percentage
- 🔵 **Supervised**: Full automation with approval gates
- 🟢 **Full Auto**: Unrestricted automation (rare)

## Usage Examples

### 1. LLM Response with Actions

```json
{
  "analysis": "Sales anomaly detected with 85% confidence",
  "actions": [
    {
      "action_type": "create_task",
      "parameters": {
        "titulo": "Investigar anomalía en ventas Q4",
        "descripcion": "Anomalía detectada en patrón de ventas del cuarto trimestre",
        "prioridad": "alta"
      },
      "confidence": 0.85,
      "reasoning": "High-impact anomaly requires investigation"
    },
    {
      "action_type": "send_notification",
      "parameters": {
        "titulo": "Alerta: Anomalía en Ventas",
        "mensaje": "Se detectó una anomalía significativa en las ventas",
        "tipo": "warning"
      },
      "confidence": 0.9,
      "reasoning": "Management team should be notified"
    }
  ]
}
```

### 2. Action Execution Flow

```python
# Process actions from LLM response
executions = await safe_action_engine.process_actions_from_llm_response(
    tenant_id="tenant_123",
    llm_response=llm_output,
    prediction_id="pred_456",
    llm_response_id="resp_789"
)

# Check results
for execution in executions:
    if execution.approval_status == ApprovalStatus.PENDING:
        # Requires manual approval
        await safe_action_engine.approve_action(execution.id, approved_by="user_123")
    elif execution.approval_status == ApprovalStatus.AUTO_APPROVED:
        # Automatically approved, queued for execution
        pass
```

### 3. Manual Approval Process

```python
# Approve action
await safe_action_engine.approve_action(
    execution_id="exec_123",
    approved_by="user_456",
    notes="Approved - standard sales anomaly protocol"
)

# Or reject
await safe_action_engine.reject_action(
    execution_id="exec_123",
    rejected_by="user_456",
    reason="Insufficient evidence for action"
)
```

## Monitoring & Observability

### Metrics Collected

- `action_executions_total{tenant,action_type,status}`
- `action_approval_queue_size{tenant}`
- `action_execution_duration{tenant,action_type}`
- `action_failure_rate{tenant,action_type}`
- `action_rollback_total{tenant,action_type}`

### Alerts

- High failure rate (>10%) for any action type
- Approval queue growing (>50 pending)
- Rate limit exceeded
- Circuit breaker triggered

### Audit Logging

All actions logged with:
- Tenant and user context
- Action parameters and results
- Confidence scores and reasoning
- Approval/rejection details
- Execution timestamps and outcomes

## Testing Strategy

### Unit Tests
- Action parsing validation
- Parameter schema enforcement
- Safety control logic
- State transition handling

### Integration Tests
- End-to-end action execution
- Approval workflow testing
- Rollback functionality
- Rate limiting verification

### Safety Tests
- Circuit breaker activation
- Invalid action rejection
- Permission enforcement
- Tenant isolation

## Deployment Checklist

### Pre-Deployment
- [ ] Database migrations applied
- [ ] Action definitions populated
- [ ] Default tenant settings configured
- [ ] API endpoints tested
- [ ] Worker processes configured

### Safety Validation
- [ ] Automation disabled by default
- [ ] Approval required for all actions initially
- [ ] Rate limits set conservatively
- [ ] Rollback mechanisms tested
- [ ] Audit logging verified

### Gradual Rollout
1. **Week 1**: Enable for 10% of tenants, notification actions only
2. **Week 2**: Increase to 25%, add task creation
3. **Week 3**: 50% coverage, enable inventory actions
4. **Week 4**: Full rollout with monitoring

### Monitoring Setup
- [ ] Prometheus metrics configured
- [ ] Alerting rules defined
- [ ] Dashboard created
- [ ] Audit log retention policy set

## Security Considerations

### Data Protection
- Action parameters sanitized before logging
- PII detection in action inputs
- Tenant data isolation enforced
- Audit logs encrypted at rest

### Access Control
- Tenant-specific action permissions
- User role-based approval rights
- API authentication required
- Rate limiting prevents abuse

### Failure Handling
- Graceful degradation on service failures
- Action retries with backoff
- Circuit breakers prevent cascade failures
- Manual intervention always available

## Future Enhancements

### Planned Features
- **Action Templates**: Pre-defined action sequences
- **Conditional Actions**: If-then logic for complex workflows
- **Action Scheduling**: Time-based action execution
- **Multi-Step Actions**: Complex operations with dependencies
- **Action Analytics**: Performance and effectiveness metrics

### Integration Opportunities
- **External Systems**: API integrations for broader actions
- **Workflow Engines**: Integration with tools like Zapier
- **ML Model Updates**: Actions that retrain models
- **Custom Actions**: Tenant-defined action types

## Troubleshooting

### Common Issues

**Actions Not Executing**
- Check tenant automation settings
- Verify approval status
- Check rate limits and circuit breakers
- Review worker process logs

**High Failure Rates**
- Validate action parameters
- Check external service availability
- Review error messages in execution logs
- Consider circuit breaker activation

**Approval Queue Growing**
- Review approval thresholds
- Check user availability for approvals
- Consider auto-approval for low-risk actions
- Implement approval delegation

**Performance Issues**
- Monitor action execution times
- Check database query performance
- Review worker concurrency settings
- Consider action batching for high volume

## Support & Documentation

### User Guides
- [Action System User Guide](./docs/action_system_user_guide.md)
- [Administrator Configuration](./docs/action_system_admin_guide.md)
- [API Reference](./docs/action_system_api.md)

### Developer Resources
- [Action Development Guide](./docs/action_development.md)
- [Testing Guidelines](./docs/action_testing.md)
- [Security Best Practices](./docs/action_security.md)

---

**Phase 4 Status**: ✅ **COMPLETED**

The Action System provides a robust, safe foundation for AI-driven automation while maintaining human oversight and operational safety. The modular design allows for gradual rollout and continuous improvement based on real-world usage patterns.