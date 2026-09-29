import { useEffect, useState } from 'react';
import moment from 'moment';
import { fetchBatches } from './api';
import type { Batch } from './types';

const STATUS_COLORS: Record<string, string> = {
  draft: '#9e9e9e',
  in_progress: '#1e88e5',
  pending_review: '#fbc02d',
  released: '#43a047',
  rejected: '#e53935',
};

type SortKey = 'batchNo' | 'product' | 'createdAt';

interface Props {
  site: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function BatchTable({ site, selectedId, onSelect }: Props) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('createdAt');
  const [ascending, setAscending] = useState(false);

  useEffect(() => {
    fetchBatches({ site })
      .then(setBatches)
      .catch(() => setError('Could not load batches.'));
  }, []);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setAscending(!ascending);
    } else {
      setSortKey(key);
      setAscending(true);
    }
  }

  function ariaSort(key: SortKey) {
    if (key !== sortKey) return 'none';
    return ascending ? 'ascending' : 'descending';
  }

  const rows = batches
    .filter((b) => b.batchNo.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => {
      const result =
        sortKey === 'createdAt'
          ? new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
          : a[sortKey].localeCompare(b[sortKey]);
      return ascending ? result : -result;
    });

  if (error) {
    return <p className="error">{error}</p>;
  }

  return (
    <section className="batch-table">
      <input
        type="search"
        placeholder="Search batch number"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <table>
        <thead>
          <tr>
            <th aria-sort={ariaSort('batchNo')}>
              <button type="button" onClick={() => toggleSort('batchNo')}>
                Batch No.
              </button>
            </th>
            <th aria-sort={ariaSort('product')}>
              <button type="button" onClick={() => toggleSort('product')}>
                Product
              </button>
            </th>
            <th>Status</th>
            <th>Actual / Planned</th>
            <th aria-sort={ariaSort('createdAt')}>
              <button type="button" onClick={() => toggleSort('createdAt')}>
                Created
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, index) => (
            <tr key={index} className={b.id === selectedId ? 'selected' : undefined}>
              <td>
                <div className="link" onClick={() => onSelect(b.id)}>
                  {b.batchNo}
                </div>
              </td>
              <td>{b.product}</td>
              <td>
                <span
                  className="status-dot"
                  style={{ backgroundColor: STATUS_COLORS[b.status] }}
                />
              </td>
              <td>{b.actualQty + ' / ' + b.plannedQty + ' kg'}</td>
              <td>{moment(b.createdAt).format('DD MMM YYYY')}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Showing {rows.length} of {batches.length} batches
      </p>
    </section>
  );
}
