/**
 * Git Arc Panel Component
 * Collapsible sidebar panel showing hierarchical git arc diagram
 */

import { useState, useCallback } from 'react';
import { ChevronDown, ChevronRight, GitBranch, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import { ArcDiagram } from './ArcDiagram';
import { ModuleDetailView } from './ModuleDetailView';
import { useGitArcData } from './useGitArcData';
import type { ArcDiagramView } from './types';

interface GitArcPanelProps {
  projectId: string | null;
  isGitRepo?: boolean;
}

export function GitArcPanel({ projectId, isGitRepo = true }: GitArcPanelProps) {
  const { t } = useTranslation(['navigation', 'common']);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [view, setView] = useState<ArcDiagramView>('overview');
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);

  const {
    data,
    moduleDetail,
    isLoading,
    error,
    refresh,
    loadModuleDetail,
    clearModuleDetail
  } = useGitArcData(projectId);

  const handleModuleClick = useCallback((moduleId: string) => {
    setSelectedModuleId(moduleId);
    setView('detail');
    loadModuleDetail(moduleId);
  }, [loadModuleDetail]);

  const handleBack = useCallback(() => {
    setView('overview');
    setSelectedModuleId(null);
    clearModuleDetail();
  }, [clearModuleDetail]);

  const handleRefresh = useCallback(() => {
    if (view === 'detail' && selectedModuleId) {
      loadModuleDetail(selectedModuleId);
    } else {
      refresh();
    }
  }, [view, selectedModuleId, loadModuleDetail, refresh]);

  // Don't show if not a git repo
  if (!isGitRepo) {
    return null;
  }

  return (
    <div className="border-t border-border">
      {/* Header */}
      <button
        className="flex items-center justify-between w-full px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div className="flex items-center gap-2">
          {isCollapsed ? (
            <ChevronRight className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
          <GitBranch className="w-3 h-3" />
          <span>{t('navigation:arcDiagram', 'Git Arc')}</span>
        </div>
        {!isCollapsed && (
          <Button
            variant="ghost"
            size="sm"
            className="h-5 w-5 p-0"
            onClick={(e) => {
              e.stopPropagation();
              handleRefresh();
            }}
            disabled={isLoading}
          >
            <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        )}
      </button>

      {/* Content */}
      {!isCollapsed && (
        <div className="px-1 pb-2">
          {error ? (
            <div className="px-2 py-4 text-xs text-center text-destructive">
              {error}
            </div>
          ) : view === 'overview' ? (
            <ArcDiagram
              data={data}
              onModuleClick={handleModuleClick}
              isLoading={isLoading}
              width={240}
              height={200}
            />
          ) : (
            <ModuleDetailView
              data={moduleDetail}
              onBack={handleBack}
              isLoading={isLoading}
              width={240}
              height={180}
            />
          )}

          {/* Branch info */}
          {data?.currentBranch && view === 'overview' && (
            <div className="flex items-center gap-1 px-2 mt-1 text-[10px] text-muted-foreground">
              <GitBranch className="w-3 h-3" />
              <span className="truncate">{data.currentBranch}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Export index
export { ArcDiagram } from './ArcDiagram';
export { ModuleDetailView } from './ModuleDetailView';
export { useGitArcData } from './useGitArcData';
export * from './types';
