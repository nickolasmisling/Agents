import { FormEvent, useEffect, useState } from 'react';
import { fetchBatch, fetchMaterials, fetchSignatures, signBatch } from './api';
import type { Batch, Material, Signature, SignatureMeaning } from './types';

interface Props {
  id: number;
  onClose: () => void;
}

function formatNote(note: string) {
  return note.replace(/\r?\n/g, '<br />');
}

export default function BatchDetail({ id, onClose }: Props) {
  const [batch, setBatch] = useState<Batch>();
  const [materials, setMaterials] = useState<Material[]>();
  const [signatures, setSignatures] = useState<Signature[]>([]);
  const [signing, setSigning] = useState(false);
  const [meaning, setMeaning] = useState<SignatureMeaning>('reviewed');
  const [password, setPassword] = useState('');

  useEffect(() => {
    fetchBatch(id).then(setBatch);
    fetchMaterials(id).then(setMaterials);
    fetchSignatures(id).then(setSignatures);
  }, [id]);

  async function handleSign(e: FormEvent) {
    e.preventDefault();
    await signBatch(id, { meaning, password });
    setPassword('');
    setSigning(false);
    setSignatures(await fetchSignatures(id));
  }

  if (!batch) {
    return <aside className="detail">Loading…</aside>;
  }

  const approval = signatures.find((s) => s.meaning === 'approved');

  return (
    <aside className="detail">
      <h2>Batch {batch.batchNo}</h2>
      <p style={{ color: '#aaa', fontSize: 12 }}>
        {batch.product} · {batch.site} · Status: {batch.status}
      </p>
      <button type="button" onClick={onClose}>
        Close
      </button>

      {batch.note && (
        <div className="note" dangerouslySetInnerHTML={{ __html: formatNote(batch.note) }} />
      )}

      {batch.status === 'released' && (
        <p>Released after approval by user #{approval!.userId}</p>
      )}

      <h3>Materials</h3>
      <ul>
        {materials!.map((m) => (
          <li key={m.id}>
            {m.name} (lot {m.lotNo}): {m.qty + ' kg'}
          </li>
        ))}
      </ul>

      <h3>{signatures.length + ' signature' + (signatures.length === 1 ? '' : 's')}</h3>
      <ul>
        {signatures.map((s) => (
          <li key={s.id}>
            {s.meaning} by user #{s.userId} on {new Date(s.signedAt).toLocaleDateString()}
          </li>
        ))}
      </ul>

      <button type="button" onClick={() => setSigning(true)}>
        Sign batch record
      </button>

      {signing && (
        <div className="overlay">
          <div className="dialog">
            <h3>Sign batch {batch.batchNo}</h3>
            <form onSubmit={handleSign}>
              <label htmlFor="sig-meaning">Meaning of signature</label>
              <select
                id="sig-meaning"
                value={meaning}
                onChange={(e) => setMeaning(e.target.value as SignatureMeaning)}
              >
                <option value="reviewed">Reviewed</option>
                <option value="approved">Approved</option>
                <option value="released">Released</option>
              </select>
              <label htmlFor="sig-password">Password</label>
              <input
                id="sig-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <div>
                <button type="submit">Sign</button>
                <button type="button" onClick={() => setSigning(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
}
