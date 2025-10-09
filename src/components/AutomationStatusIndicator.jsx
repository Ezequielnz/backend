import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useBusinessContext } from '../contexts/BusinessContext';
import { Zap, Shield, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

function AutomationStatusIndicator({ compact = false }) {
  const { currentBusiness } = useBusinessContext();
  const businessId = currentBusiness?.id;

  // Fetch automation settings
  const { data: settings, isLoading } = useQuery({
    queryKey: ['action-settings', businessId],
    queryFn: async () => {
      if (!businessId) return null;
      // TODO: Implement API call to get automation settings
      return {
        automation_enabled: false,
        approval_required: true,
        safety_mode: 'strict',
        canary_percentage: 0.0
      };
    },
    enabled: !!businessId,
    staleTime: 60000 // 1 minute
  });

  if (isLoading || !settings) {
    return null;
  }

  const getStatusInfo = () => {
    if (!settings.automation_enabled) {
      return {
        status: 'disabled',
        label: 'Automatización Deshabilitada',
        description: 'Las acciones se ejecutan manualmente',
        icon: XCircle,
        color: 'text-gray-500',
        bgColor: 'bg-gray-100'
      };
    }

    if (settings.canary_percentage < 1.0) {
      return {
        status: 'canary',
        label: 'Modo Canary',
        description: `${(settings.canary_percentage * 100).toFixed(0)}% de activación`,
        icon: AlertTriangle,
        color: 'text-yellow-600',
        bgColor: 'bg-yellow-100'
      };
    }

    if (settings.approval_required) {
      return {
        status: 'supervised',
        label: 'Automatización Supervisada',
        description: 'Requiere aprobación manual',
        icon: Shield,
        color: 'text-blue-600',
        bgColor: 'bg-blue-100'
      };
    }

    return {
      status: 'full_auto',
      label: 'Automatización Completa',
      description: 'Ejecución automática con límites',
      icon: Zap,
      color: 'text-green-600',
      bgColor: 'bg-green-100'
    };
  };

  const statusInfo = getStatusInfo();
  const StatusIcon = statusInfo.icon;

  if (compact) {
    return (
      <div className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${statusInfo.bgColor} ${statusInfo.color}`}>
        <StatusIcon style={{ width: '0.75rem', height: '0.75rem' }} />
        <span className="font-medium">{statusInfo.label}</span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg ${statusInfo.bgColor} border`}>
      <div className={`p-2 rounded-full ${statusInfo.bgColor} ${statusInfo.color}`}>
        <StatusIcon style={{ width: '1.25rem', height: '1.25rem' }} />
      </div>
      <div>
        <p className={`font-medium ${statusInfo.color}`}>{statusInfo.label}</p>
        <p className="text-sm text-gray-600">{statusInfo.description}</p>
      </div>
    </div>
  );
}

export default AutomationStatusIndicator;