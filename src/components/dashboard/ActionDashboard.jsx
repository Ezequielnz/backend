import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useBusinessContext } from '../../contexts/BusinessContext';
import { useAuth } from '../../contexts/AuthContext';
import { tasksAPI } from '../../utils/api';
import { getErrorMessage } from '../../utils/errorHandler';
import Layout from '../Layout';
import PermissionGuard from '../PermissionGuard';
import {
  CheckCircle,
  Clock,
  AlertCircle,
  AlertTriangle,
  Play,
  X,
  Eye,
  Settings,
  TrendingUp,
  Activity,
  Shield,
  Zap,
  BarChart3
} from 'lucide-react';

// Action status configurations
const ACTION_STATUS = {
  pending: { label: 'Pendiente', cssClass: 'badge-pending', icon: Clock },
  approved: { label: 'Aprobada', cssClass: 'badge-completed', icon: CheckCircle },
  executing: { label: 'Ejecutando', cssClass: 'badge-in-progress', icon: Activity },
  completed: { label: 'Completada', cssClass: 'badge-completed', icon: CheckCircle },
  failed: { label: 'Fallida', cssClass: 'badge-cancelled', icon: AlertCircle },
  cancelled: { label: 'Cancelada', cssClass: 'badge-cancelled', icon: X }
};

const APPROVAL_STATUS = {
  pending: { label: 'Pendiente', cssClass: 'badge-pending' },
  auto_approved: { label: 'Auto-aprobada', cssClass: 'badge-completed' },
  manual_approved: { label: 'Aprobada', cssClass: 'badge-completed' },
  rejected: { label: 'Rechazada', cssClass: 'badge-cancelled' }
};

function ActionDashboard() {
  const { currentBusiness } = useBusinessContext();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const businessId = currentBusiness?.id;

  const [activeTab, setActiveTab] = useState('overview');
  const [selectedAction, setSelectedAction] = useState(null);

  // Fetch action executions
  const { data: executionsData = { executions: [], total: 0 }, isLoading: loadingExecutions } = useQuery({
    queryKey: ['action-executions', businessId],
    queryFn: async () => {
      if (!businessId) return { executions: [], total: 0 };
      // TODO: Implement API call
      return { executions: [], total: 0 };
    },
    enabled: !!businessId,
    staleTime: 30000 // 30 seconds
  });

  // Fetch pending approvals
  const { data: approvalsData = { approvals: [], total: 0 }, isLoading: loadingApprovals } = useQuery({
    queryKey: ['action-approvals', businessId],
    queryFn: async () => {
      if (!businessId) return { approvals: [], total: 0 };
      // TODO: Implement API call
      return { approvals: [], total: 0 };
    },
    enabled: !!businessId,
    staleTime: 15000 // 15 seconds
  });

  // Fetch action settings
  const { data: settings, isLoading: loadingSettings } = useQuery({
    queryKey: ['action-settings', businessId],
    queryFn: async () => {
      if (!businessId) return null;
      // TODO: Implement API call
      return {
        automation_enabled: false,
        approval_required: true,
        auto_approval_threshold: 0.9,
        max_actions_per_hour: 10,
        canary_percentage: 0.0,
        safety_mode: 'strict'
      };
    },
    enabled: !!businessId,
    staleTime: 60000 // 1 minute
  });

  // Approve action mutation
  const approveMutation = useMutation({
    mutationFn: async ({ executionId, notes }) => {
      // TODO: Implement API call
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['action-executions', businessId]);
      queryClient.invalidateQueries(['action-approvals', businessId]);
    }
  });

  // Reject action mutation
  const rejectMutation = useMutation({
    mutationFn: async ({ executionId, notes }) => {
      // TODO: Implement API call
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['action-executions', businessId]);
      queryClient.invalidateQueries(['action-approvals', businessId]);
    }
  });

  const handleApproveAction = async (executionId, notes = '') => {
    try {
      await approveMutation.mutateAsync({ executionId, notes });
    } catch (error) {
      console.error('Error approving action:', error);
    }
  };

  const handleRejectAction = async (executionId, reason = '') => {
    try {
      await rejectMutation.mutateAsync({ executionId, reason });
    } catch (error) {
      console.error('Error rejecting action:', error);
    }
  };

  const getStatusStats = () => {
    const executions = executionsData.executions || [];
    const stats = {
      total: executions.length,
      pending: executions.filter(e => e.status === 'pending').length,
      approved: executions.filter(e => e.status === 'approved').length,
      executing: executions.filter(e => e.status === 'executing').length,
      completed: executions.filter(e => e.status === 'completed').length,
      failed: executions.filter(e => e.status === 'failed').length
    };
    return stats;
  };

  const stats = getStatusStats();

  if (!currentBusiness) {
    return (
      <Layout activeSection="actions">
        <div className="px-3 sm:px-4 md:px-6 lg:px-8 py-4 md:py-8">
          <div className="alert alert-warning">
            <AlertTriangle style={{ width: '1rem', height: '1rem', marginRight: '0.5rem' }} />
            No hay negocio seleccionado. Por favor selecciona un negocio desde el menú superior.
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout activeSection="actions">
      <div className="px-3 sm:px-4 md:px-6 lg:px-8 py-4 md:py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex flex-wrap justify-between items-start gap-4">
            <div>
              <h1 className="text-xl md:text-3xl font-bold text-gray-900 mb-2">
                Sistema de Acciones Automatizadas
              </h1>
              <p className="text-gray-600">
                Monitorea y gestiona las acciones automatizadas generadas por IA
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className={`btn btn-sm ${activeTab === 'overview' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setActiveTab('overview')}
              >
                <BarChart3 style={{ width: '1rem', height: '1rem', marginRight: '0.5rem' }} />
                Resumen
              </button>
              <button
                className={`btn btn-sm ${activeTab === 'executions' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setActiveTab('executions')}
              >
                <Activity style={{ width: '1rem', height: '1rem', marginRight: '0.5rem' }} />
                Ejecuciones
              </button>
              <button
                className={`btn btn-sm ${activeTab === 'approvals' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setActiveTab('approvals')}
              >
                <Shield style={{ width: '1rem', height: '1rem', marginRight: '0.5rem' }} />
                Aprobaciones
              </button>
              <button
                className={`btn btn-sm ${activeTab === 'settings' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setActiveTab('settings')}
              >
                <Settings style={{ width: '1rem', height: '1rem', marginRight: '0.5rem' }} />
                Configuración
              </button>
            </div>
          </div>
        </div>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Status Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <div className="card">
                <div className="card-content p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-blue-600">{stats.total}</p>
                      <p className="text-sm text-gray-600">Total</p>
                    </div>
                    <Activity style={{ width: '2rem', height: '2rem', color: '#2563eb' }} />
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-content p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-yellow-600">{stats.pending}</p>
                      <p className="text-sm text-gray-600">Pendientes</p>
                    </div>
                    <Clock style={{ width: '2rem', height: '2rem', color: '#d97706' }} />
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-content p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-blue-600">{stats.approved}</p>
                      <p className="text-sm text-gray-600">Aprobadas</p>
                    </div>
                    <CheckCircle style={{ width: '2rem', height: '2rem', color: '#2563eb' }} />
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-content p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-green-600">{stats.completed}</p>
                      <p className="text-sm text-gray-600">Completadas</p>
                    </div>
                    <CheckCircle style={{ width: '2rem', height: '2rem', color: '#059669' }} />
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-content p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-red-600">{stats.failed}</p>
                      <p className="text-sm text-gray-600">Fallidas</p>
                    </div>
                    <AlertCircle style={{ width: '2rem', height: '2rem', color: '#dc2626' }} />
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-content p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold text-purple-600">{approvalsData.total}</p>
                      <p className="text-sm text-gray-600">Por Aprobar</p>
                    </div>
                    <Shield style={{ width: '2rem', height: '2rem', color: '#7c3aed' }} />
                  </div>
                </div>
              </div>
            </div>

            {/* Automation Status */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Estado de Automatización</h3>
              </div>
              <div className="card-content">
                {loadingSettings ? (
                  <div className="text-center py-4">Cargando configuración...</div>
                ) : settings ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div className="flex items-center gap-3">
                      <Zap style={{ width: '1.5rem', height: '1.5rem', color: settings.automation_enabled ? '#059669' : '#6b7280' }} />
                      <div>
                        <p className="font-medium">Automatización</p>
                        <p className="text-sm text-gray-600">
                          {settings.automation_enabled ? 'Habilitada' : 'Deshabilitada'}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <Shield style={{ width: '1.5rem', height: '1.5rem', color: settings.approval_required ? '#d97706' : '#059669' }} />
                      <div>
                        <p className="font-medium">Aprobación Requerida</p>
                        <p className="text-sm text-gray-600">
                          {settings.approval_required ? 'Sí' : 'No'}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <TrendingUp style={{ width: '1.5rem', height: '1.5rem', color: '#2563eb' }} />
                      <div>
                        <p className="font-medium">Modo Canary</p>
                        <p className="text-sm text-gray-600">
                          {settings.canary_percentage * 100}% de activación
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-4 text-gray-500">
                    No se pudo cargar la configuración
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Executions Tab */}
        {activeTab === 'executions' && (
          <div className="space-y-4">
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Ejecuciones de Acciones</h3>
              </div>
              <div className="card-content">
                {loadingExecutions ? (
                  <div className="text-center py-8">Cargando ejecuciones...</div>
                ) : executionsData.executions.length === 0 ? (
                  <div className="text-center py-8">
                    <Activity style={{ width: '3rem', height: '3rem', color: '#9ca3af', margin: '0 auto 1rem' }} />
                    <p className="text-gray-500">No hay ejecuciones de acciones</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {executionsData.executions.map((execution) => {
                      const StatusIcon = ACTION_STATUS[execution.status]?.icon || AlertCircle;
                      return (
                        <div key={execution.execution_id} className="border rounded-lg p-4">
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <h4 className="font-medium">{execution.action_description}</h4>
                                <span className={`badge ${ACTION_STATUS[execution.status]?.cssClass}`}>
                                  {ACTION_STATUS[execution.status]?.label}
                                </span>
                                <span className={`badge ${APPROVAL_STATUS[execution.approval_status]?.cssClass}`}>
                                  {APPROVAL_STATUS[execution.approval_status]?.label}
                                </span>
                              </div>
                              <div className="text-sm text-gray-600 space-y-1">
                                <p>ID: {execution.execution_id}</p>
                                <p>Tipo: {execution.action_type}</p>
                                <p>Confianza: {(execution.confidence_score * 100).toFixed(1)}%</p>
                                <p>Creado: {new Date(execution.created_at).toLocaleString()}</p>
                              </div>
                            </div>
                            <div className="flex gap-2">
                              <button
                                className="btn btn-sm btn-outline"
                                onClick={() => setSelectedAction(execution)}
                              >
                                <Eye style={{ width: '1rem', height: '1rem' }} />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Approvals Tab */}
        {activeTab === 'approvals' && (
          <div className="space-y-4">
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Aprobaciones Pendientes</h3>
              </div>
              <div className="card-content">
                {loadingApprovals ? (
                  <div className="text-center py-8">Cargando aprobaciones...</div>
                ) : approvalsData.approvals.length === 0 ? (
                  <div className="text-center py-8">
                    <Shield style={{ width: '3rem', height: '3rem', color: '#9ca3af', margin: '0 auto 1rem' }} />
                    <p className="text-gray-500">No hay aprobaciones pendientes</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {approvalsData.approvals.map((approval) => (
                      <div key={approval.approval_id} className="border rounded-lg p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h4 className="font-medium mb-2">{approval.action_description}</h4>
                            <div className="text-sm text-gray-600 space-y-1">
                              <p>ID: {approval.approval_id}</p>
                              <p>Tipo: {approval.action_type}</p>
                              <p>Prioridad: {approval.priority}</p>
                              <p>Riesgo: {approval.impact_summary}</p>
                              <p>Confianza: {(approval.confidence_score * 100).toFixed(1)}%</p>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => handleApproveAction(approval.execution_id)}
                              disabled={approveMutation.isPending}
                            >
                              <CheckCircle style={{ width: '1rem', height: '1rem', marginRight: '0.25rem' }} />
                              Aprobar
                            </button>
                            <button
                              className="btn btn-destructive btn-sm"
                              onClick={() => handleRejectAction(approval.execution_id)}
                              disabled={rejectMutation.isPending}
                            >
                              <X style={{ width: '1rem', height: '1rem', marginRight: '0.25rem' }} />
                              Rechazar
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <div className="space-y-6">
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Configuración de Automatización</h3>
              </div>
              <div className="card-content">
                {loadingSettings ? (
                  <div className="text-center py-8">Cargando configuración...</div>
                ) : (
                  <div className="space-y-6">
                    <div className="alert alert-info">
                      <AlertTriangle style={{ width: '1rem', height: '1rem' }} />
                      <div>
                        <p className="font-medium">Configuración de Seguridad</p>
                        <p className="text-sm">
                          Estas configuraciones afectan la seguridad y el comportamiento de las acciones automatizadas.
                          Los cambios se aplican inmediatamente.
                        </p>
                      </div>
                    </div>

                    {/* Settings form would go here */}
                    <div className="text-center py-8 text-gray-500">
                      Formulario de configuración en desarrollo
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Action Detail Modal */}
        {selectedAction && (
          <div className="modal-overlay" onClick={() => setSelectedAction(null)}>
            <div className="modal-content max-w-2xl" onClick={(e) => e.stopPropagation()}>
              <h3 className="text-lg font-bold mb-4">Detalles de Acción</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Descripción</label>
                  <p className="text-gray-900">{selectedAction.action_description}</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Estado</label>
                    <span className={`badge ${ACTION_STATUS[selectedAction.status]?.cssClass}`}>
                      {ACTION_STATUS[selectedAction.status]?.label}
                    </span>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Aprobación</label>
                    <span className={`badge ${APPROVAL_STATUS[selectedAction.approval_status]?.cssClass}`}>
                      {APPROVAL_STATUS[selectedAction.approval_status]?.label}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Parámetros</label>
                  <pre className="bg-gray-50 p-3 rounded text-sm overflow-x-auto">
                    {JSON.stringify(selectedAction.action_params, null, 2)}
                  </pre>
                </div>

                {selectedAction.impact_assessment && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Evaluación de Impacto</label>
                    <pre className="bg-gray-50 p-3 rounded text-sm overflow-x-auto">
                      {JSON.stringify(selectedAction.impact_assessment, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 mt-6">
                <button
                  className="btn btn-outline"
                  onClick={() => setSelectedAction(null)}
                >
                  Cerrar
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}

export default function ProtectedActionDashboard() {
  return (
    <PermissionGuard requiredModule="acciones" requiredAction="ver">
      <ActionDashboard />
    </PermissionGuard>
  );
}