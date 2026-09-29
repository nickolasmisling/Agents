export type BatchStatus =
  | 'draft'
  | 'in_progress'
  | 'pending_review'
  | 'released'
  | 'rejected';

export interface Batch {
  id: number;
  batchNo: string;
  product: string;
  site: string;
  status: BatchStatus;
  plannedQty: number;
  actualQty: number | null;
  createdAt: string;
  note?: string;
}

export interface Material {
  id: number;
  batchId: number;
  lotNo: string;
  name: string;
  qty: number;
}

export type SignatureMeaning = 'reviewed' | 'approved' | 'released';

export interface Signature {
  id: number;
  batchId: number;
  userId: number;
  meaning: SignatureMeaning;
  signedAt: string;
}

export interface SignatureRequest {
  meaning: SignatureMeaning;
  password: string;
}
