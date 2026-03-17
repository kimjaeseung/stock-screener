import { useState, useEffect } from 'react';
import type { ScreeningData } from '../data/types';

export function useScreeningData() {
  const [data, setData] = useState<ScreeningData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const base = import.meta.env.BASE_URL;
    fetch(`${base}data/latest.json`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  return { data, loading, error };
}
