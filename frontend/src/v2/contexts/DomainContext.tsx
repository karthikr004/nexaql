import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';

interface Domain {
  name: string;
  description?: string;
}

interface DomainContextValue {
  domains: Domain[];
  activeDomain: string | null;
  switchDomain: (name: string) => Promise<void>;
  refreshDomains: () => Promise<void>;
  loading: boolean;
}

const DomainContext = createContext<DomainContextValue>({
  domains: [],
  activeDomain: null,
  switchDomain: async () => {},
  refreshDomains: async () => {},
  loading: true,
});

export function DomainProvider({ children }: { children: ReactNode }) {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [activeDomain, setActiveDomain] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshDomains = useCallback(async () => {
    try {
      const res = await fetch('/api/domains');
      if (!res.ok) return;
      const data = await res.json();
      const domainList: Domain[] = [];
      let active: string | null = null;
      if (data.domains) {
        for (const d of data.domains) {
          domainList.push({ name: d.domain, description: d.description });
        }
      }
      if (data.activeDomain) {
        active = data.activeDomain;
      }
      setDomains(domainList);
      setActiveDomain(active);
    } catch {
      // API might not be ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  const switchDomain = useCallback(async (name: string) => {
    try {
      const res = await fetch('/api/domains/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: name }),
      });
      if (res.ok) {
        setActiveDomain(name);
      }
    } catch {
      // handle error
    }
  }, []);

  useEffect(() => {
    refreshDomains();
  }, [refreshDomains]);

  return (
    <DomainContext.Provider value={{ domains, activeDomain, switchDomain, refreshDomains, loading }}>
      {children}
    </DomainContext.Provider>
  );
}

export function useDomain() {
  return useContext(DomainContext);
}
