import { requestClient } from '#/api/request';

export interface PaperPosition { code: string; name: string; qty: number; cost: number; mark: number; date: string; stop: number; reason: string }
export interface PaperOrder { code: string; name: string; action: string; date: string; reason: string; status?: string; note?: string; price?: number; filledDate?: string }
export interface PaperAccount { cash: number; equity: number; returnPct: number; drawdownPct: number; positions: Record<string, PaperPosition>; orders: PaperOrder[]; trades: PaperOrder[]; curve: {date: string; equity: number; stale: string[]}[] }
export interface PaperSummary {
  accounts: Record<string, PaperAccount>;
  status: {running: boolean; error: null | string; message?: string};
  decisions: {date: string; plan: {review: string; model?: string; actions: PaperOrder[]}}[];
  rules: string;
}
export const getPaperSummary = () => requestClient.get<PaperSummary>('/paper/summary');
export const runPaper = () => requestClient.post('/paper/run');
