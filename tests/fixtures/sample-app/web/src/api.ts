const API_BASE = '/api';

async function request(path: string, init: any = {}): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(init.headers || {}),
    },
  });
  return res.json();
}

export async function fetchBatches(filters: any): Promise<any> {
  const params = new URLSearchParams();
  Object.keys(filters).forEach((key) => {
    if (filters[key]) {
      params.set(key, String(filters[key]));
    }
  });
  const data = await request(`/batches?${params.toString()}`);
  return data.items;
}

export function fetchBatch(id: any): Promise<any> {
  return request(`/batches/${encodeURIComponent(id)}`);
}

export function fetchMaterials(batchId: any): Promise<any> {
  return request(`/batches/${encodeURIComponent(batchId)}/materials`);
}

export async function fetchSignatures(batchId: any): Promise<any> {
  const data = await request(`/batches/${encodeURIComponent(batchId)}/signatures`);
  return data.items;
}

export function signBatch(batchId: any, payload: any): Promise<any> {
  return request(`/batches/${encodeURIComponent(batchId)}/signatures`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateBatchStatus(batchId: any, status: any): Promise<any> {
  return request(`/batches/${encodeURIComponent(batchId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}
