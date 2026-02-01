import { useState, useEffect, useCallback } from 'react';

interface ProviderStatus {
  name: string;
  running: boolean;
  port: number;
  description: string;
  can_start: boolean;
  can_stop: boolean;
  models?: any;
}

export function useLLMStatus(pollInterval: number = 10000) {
  const [providers, setProviders] = useState<Record<string, ProviderStatus>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await fetch('http://localhost:8000/api/llm/status');
      if (!resp.ok) throw new Error('Failed to fetch status');
      const data = await resp.json();
      setProviders(data);
      setError(null);
    } catch (e) {
      setError('API not available');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, pollInterval);
    return () => clearInterval(interval);
  }, [fetchStatus, pollInterval]);

  const startProvider = async (provider: string) => {
    try {
      await fetch(`http://localhost:8000/api/llm/${provider}/start`, { method: 'POST' });
      setTimeout(fetchStatus, 2000);
    } catch (e) {
      console.error('Failed to start provider:', e);
    }
  };

  const stopProvider = async (provider: string) => {
    try {
      await fetch(`http://localhost:8000/api/llm/${provider}/stop`, { method: 'POST' });
      setTimeout(fetchStatus, 1000);
    } catch (e) {
      console.error('Failed to stop provider:', e);
    }
  };

  return {
    providers,
    loading,
    error,
    refresh: fetchStatus,
    startProvider,
    stopProvider,
  };
}
