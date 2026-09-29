import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import BatchTable from './BatchTable';
import BatchDetail from './BatchDetail';
import './index.css';

const SITES = ['PLANT-01', 'PLANT-02', 'PLANT-03'];

function App() {
  const [site, setSite] = useState(SITES[0]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <>
      <header className="topbar">
        <img src="/logo.svg" className="logo" />
        <h1>BatchTrack</h1>
        <label htmlFor="site-select">Site</label>
        <select
          id="site-select"
          value={site}
          onChange={(e) => {
            setSite(e.target.value);
            setSelectedId(null);
          }}
        >
          {SITES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </header>
      <main className="layout">
        <BatchTable site={site} selectedId={selectedId} onSelect={setSelectedId} />
        {selectedId !== null && (
          <BatchDetail id={selectedId} onClose={() => setSelectedId(null)} />
        )}
      </main>
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
