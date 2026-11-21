import React from 'react';

type BadgeType = 'SYNTHETIC' | 'PUBLIC_SOURCE' | 'MODEL_PREDICTION' | 'PHYSICAL_HOST' | 'SIMULATED_ACTION' | 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW';

interface BadgeProps {
  type: BadgeType;
  label?: string;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ type, label, className = '' }) => {
  const styles: Record<BadgeType, { bg: string; text: string; defaultLabel: string }> = {
    SYNTHETIC: {
      bg: 'bg-indigo-950/80 border-indigo-700/60',
      text: 'text-indigo-300',
      defaultLabel: 'SYNTHETIC',
    },
    PUBLIC_SOURCE: {
      bg: 'bg-cyan-950/80 border-cyan-700/60',
      text: 'text-cyan-300',
      defaultLabel: 'PUBLIC SOURCE',
    },
    MODEL_PREDICTION: {
      bg: 'bg-purple-950/80 border-purple-700/60',
      text: 'text-purple-300',
      defaultLabel: 'MODEL PREDICTION',
    },
    PHYSICAL_HOST: {
      bg: 'bg-emerald-950/80 border-emerald-700/60',
      text: 'text-emerald-300',
      defaultLabel: 'PHYSICAL HOST METRIC',
    },
    SIMULATED_ACTION: {
      bg: 'bg-amber-950/80 border-amber-700/60',
      text: 'text-amber-300',
      defaultLabel: 'SIMULATED ACTION',
    },
    CRITICAL: {
      bg: 'bg-red-950/80 border-red-700/60',
      text: 'text-red-400',
      defaultLabel: 'CRITICAL',
    },
    HIGH: {
      bg: 'bg-amber-950/80 border-amber-700/60',
      text: 'text-amber-400',
      defaultLabel: 'HIGH',
    },
    MODERATE: {
      bg: 'bg-yellow-950/80 border-yellow-700/60',
      text: 'text-yellow-400',
      defaultLabel: 'MODERATE',
    },
    LOW: {
      bg: 'bg-emerald-950/80 border-emerald-700/60',
      text: 'text-emerald-400',
      defaultLabel: 'LOW',
    },
  };

  const style = styles[type] || styles.SYNTHETIC;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold tracking-wider border ${style.bg} ${style.text} ${className}`}
    >
      {label || style.defaultLabel}
    </span>
  );
};
