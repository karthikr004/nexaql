import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';

export default function HomeRedirect() {
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function checkConfig() {
      try {
        const [connRes, keysRes, domRes] = await Promise.all([
          fetch('/api/connectors'),
          fetch('/api/api-keys'),
          fetch('/api/domains'),
        ]);

        const connectors = await connRes.json();
        const keys = await keysRes.json();
        const domains = await domRes.json();

        if (cancelled) return;

        const connList = connectors.connectors ?? connectors;
        const hasConnector = Array.isArray(connList) && connList.length > 0;
        const hasApiKey = Array.isArray(keys.api_keys) && keys.api_keys.length > 0;
        const domList = domains.domains ?? domains;
        const hasDomain = Array.isArray(domList) && domList.length > 0;

        if (hasConnector && hasApiKey && hasDomain) {
          setTarget('/chat');
        } else {
          setTarget('/setup');
        }
      } catch {
        setTarget('/setup');
      }
    }

    checkConfig();
    return () => { cancelled = true; };
  }, []);

  if (!target) return null;
  return <Navigate to={target} replace />;
}
