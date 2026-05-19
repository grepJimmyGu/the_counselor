/**
 * Community BFF helpers — all mutating calls go through /api/community/*
 * Next.js API routes which verify the Auth.js session before forwarding
 * to FastAPI with the INTERNAL_API_KEY.
 *
 * Read-only endpoints (signal scores, board, upvote counts) call FastAPI
 * directly from the browser like other public endpoints.
 */

import type {
  CommunityBoardResponse,
  CommentResponse,
  CommentsListResponse,
  SignalScore,
  StockThesis,
  StockThesisListResponse,
  UpvoteResponse,
  VoteSummary,
  WatchlistResponse,
} from "./contracts";

// ── Read (public, direct FastAPI calls) ──────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export const getSignalScore = (symbol: string) =>
  get<SignalScore>(`/api/community/signal/${symbol}`);

export const getCommunityBoard = (
  limit = 20,
  offset = 0,
  window: "today" | "7d" | "30d" | "all" = "7d",
  filter: "all" | "bullish" | "bearish" | "controversial" | "rising" = "all",
) =>
  get<CommunityBoardResponse>(
    `/api/community/board?limit=${limit}&offset=${offset}&window=${window}&filter=${filter}`,
  );

export const getVotes = (symbol: string, userId?: string) =>
  get<VoteSummary>(
    `/api/community/votes/${symbol}${userId ? `?user_id=${userId}` : ""}`
  );

export const getUpvotes = (slug: string, userId?: string) =>
  get<UpvoteResponse>(
    `/api/community/upvotes/${slug}${userId ? `?user_id=${userId}` : ""}`
  );

export const getComments = (slug: string) =>
  get<CommentsListResponse>(`/api/community/comments/${slug}`);

export const getStockTheses = (symbol?: string, limit = 12) =>
  get<StockThesisListResponse>(
    `/api/community/theses?limit=${limit}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`,
  );

// ── Write (auth-required, via Next.js BFF) ───────────────────────────────────

async function bff<T>(path: string, method = "POST", body?: object): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error ?? `${res.status} ${path}`);
  }
  return res.json();
}

export const getWatchlist = () =>
  bff<WatchlistResponse>("/api/community/watchlist", "GET");

export const addToWatchlist = (symbol: string) =>
  bff<{ symbol: string; action: string }>(`/api/community/watchlist/${symbol}`);

export const removeFromWatchlist = (symbol: string) =>
  bff<{ symbol: string; action: string }>(`/api/community/watchlist/${symbol}`, "DELETE");

export const getWatchlistStatus = (symbol: string) =>
  bff<{ symbol: string; in_watchlist: boolean }>(
    `/api/community/watchlist/${symbol}/status`, "GET"
  );

export const castVote = (symbol: string, vote: "bull" | "bear" | "hold") =>
  bff<VoteSummary>(`/api/community/vote/${symbol}`, "POST", { vote });

export const removeVote = (symbol: string) =>
  bff<{ symbol: string; action: string }>(`/api/community/vote/${symbol}`, "DELETE");

export const addComment = (slug: string, content: string) =>
  bff<CommentResponse>(`/api/community/comments/${slug}`, "POST", { content });

export const deleteComment = (commentId: number) =>
  bff<{ id: number; action: string }>(`/api/community/comments/${commentId}`, "DELETE");

export const toggleUpvote = (slug: string) =>
  bff<UpvoteResponse>(`/api/community/upvotes/${slug}`);

export const addStockThesis = (body: {
  symbol: string;
  stance: "bull" | "bear" | "hold";
  timeframe: string;
  thesis: string;
  risks: string;
  evidence_url?: string | null;
}) => bff<StockThesis>("/api/community/theses", "POST", body);
