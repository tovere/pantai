import { requestClient } from '#/api/request';

export interface PaperPosition { code: string; name: string; qty: number; cost: number; mark: number; date: string; stop: number; reason: string }
export interface DivergenceEvidence { code: string; name: string; source?: string; evidence?: { evolution?: {previousDate: null | string; changes: {feature: string; before: unknown; after: unknown}[]; note: string}; priceVolume: {volumeRatio: number; pullbackPct: number; supportIntact: boolean}; chan: {pivotCount: number; abovePivot: boolean; buyPointConfirmed: boolean}; wyckoff: {breakoutRetest: boolean; phaseConfirmed: boolean}; entry: {eligible: boolean; triggerPrice: number; maxPrice: number; stop: number}; sector: {match: null | {name: string; leaders: string[]}} } }
export interface PaperOrder { source?: string; code: string; name: string; action: string; date: string; reason: string; status?: string; note?: string; price?: number; filledDate?: string }
export interface PaperAccount { cash: number; equity: number; returnPct: number; drawdownPct: number; positions: Record<string, PaperPosition>; orders: PaperOrder[]; trades: PaperOrder[]; curve: {date: string; equity: number; stale: string[]}[] }
export interface PaperSummary {
  accounts: Record<string, PaperAccount>;
  status: {running: boolean; error: null | string; message?: string; requestId?: string; completedRequestId?: string};
  decisions: {date: string; revision?: number; generatedAt?: string; linkage?: {input?: {candidates: DivergenceEvidence[]; divergenceScan?: {sourceCount: number; matched: number; incompleteHistory: number; previousLimitDate: string}}; error?: string; plan?: {review: string; actions: PaperOrder[]}}; plan: {review: string; model?: string; actions: PaperOrder[]}}[];
  rules: string;
}
export const getPaperSummary = () => requestClient.get<PaperSummary>('/paper/summary');
export const runPaper = () => requestClient.post<{started: boolean; requestId?: string; message: string}>('/paper/run');

export interface PaperLiveStatus {
  features?: {code: string; name: string; state: string; reason: string; count?: number; time: string}[];
  heartbeat: null | {time: string; alive: boolean; session: boolean; watching?: number; fresh?: number; source?: string};
  orders: {id: string; state: string; body: string}[];
  events: {time: string; kind: string; body: string}[];
}
export const getPaperLive = () => requestClient.get<PaperLiveStatus>('/paper/live');
