/**
 * Git Arc Data Hook
 * Fetches and manages git arc diagram data
 */

import { useState, useEffect, useCallback } from 'react';
import type { GitArcData, ModuleDetailData } from './types';

interface UseGitArcDataResult {
  data: GitArcData | null;
  moduleDetail: ModuleDetailData | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  loadModuleDetail: (modulePath: string) => Promise<void>;
  clearModuleDetail: () => void;
}

/**
 * Hook to fetch and manage git arc diagram data
 */
export function useGitArcData(projectId: string | null): UseGitArcDataResult {
  const [data, setData] = useState<GitArcData | null>(null);
  const [moduleDetail, setModuleDetail] = useState<ModuleDetailData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!projectId) {
      setData(null);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await window.electronAPI.getGitArcData(projectId);

      if (result.success && result.data) {
        setData(result.data as GitArcData);
      } else {
        setError(result.error || 'Failed to fetch git arc data');
        setData(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  const loadModuleDetail = useCallback(async (modulePath: string) => {
    if (!projectId) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await window.electronAPI.getGitArcModuleDetail(projectId, modulePath);

      if (result.success && result.data) {
        setModuleDetail(result.data as ModuleDetailData);
      } else {
        setError(result.error || 'Failed to fetch module detail');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  const clearModuleDetail = useCallback(() => {
    setModuleDetail(null);
  }, []);

  // Fetch data on mount and when projectId changes
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    data,
    moduleDetail,
    isLoading,
    error,
    refresh: fetchData,
    loadModuleDetail,
    clearModuleDetail
  };
}
