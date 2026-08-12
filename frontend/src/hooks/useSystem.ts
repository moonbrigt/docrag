import { useQuery } from '@tanstack/react-query';
import { getBackends, getHealth } from '@/api/health';

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 15000,
    retry: 1,
  });
}

export function useBackends() {
  return useQuery({
    queryKey: ['backends'],
    queryFn: getBackends,
    refetchInterval: 30000,
    retry: 1,
  });
}
