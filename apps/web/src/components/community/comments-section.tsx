"use client";

import { useEffect, useRef, useState } from "react";
import { useSession, signIn } from "next-auth/react";
import { MessageSquare, Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getComments, addComment, deleteComment } from "@/lib/community-api";
import type { CommentResponse } from "@/lib/contracts";

interface CommentsSectionProps {
  slug: string;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function CommentsSection({ slug }: CommentsSectionProps) {
  const { data: session } = useSession();
  const [comments, setComments] = useState<CommentResponse[]>([]);
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    getComments(slug).then((r) => setComments(r.comments)).catch(() => {});
  }, [slug]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const comment = await addComment(slug, content.trim());
      setComments((prev) => [comment, ...prev]);
      setContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to post comment.");
    }
    finally { setSubmitting(false); }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteComment(id);
      setComments((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete comment.");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-semibold">
          Discussion{comments.length > 0 ? ` (${comments.length})` : ""}
        </span>
      </div>

      {/* Input */}
      {session?.user ? (
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e); }
            }}
            placeholder="Share your thoughts on this strategy…"
            rows={2}
            maxLength={2000}
            className="flex-1 resize-none rounded-lg border border-border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground"
          />
          <Button type="submit" size="sm" disabled={!content.trim() || submitting} className="self-end">
            <Send className="h-3.5 w-3.5" />
          </Button>
        </form>
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3 text-center text-xs text-muted-foreground">
          <button onClick={() => signIn("google")} className="text-primary cursor-pointer hover:underline">
            Sign in
          </button>{" "}
          to join the discussion
        </div>
      )}

      {error && (
        <p className="text-xs text-red-600" role="status">
          {error}
        </p>
      )}

      {/* Comments list */}
      {comments.length > 0 ? (
        <div className="space-y-3">
          {comments.map((c) => (
            <div key={c.id} className="flex gap-3">
              {/* Avatar */}
              <div className="h-7 w-7 shrink-0 overflow-hidden rounded-full border border-border bg-primary/10 flex items-center justify-center text-[10px] font-semibold text-primary">
                {c.avatar_url
                  ? <img src={c.avatar_url} alt={c.display_name ?? ""} className="h-full w-full object-cover" />
                  : (c.display_name ?? "?")[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold">{c.display_name ?? "User"}</span>
                  <span className="text-[10px] text-muted-foreground">{timeAgo(c.created_at)}</span>
                  {session?.user?.id === c.user_id && (
                    <button
                      onClick={() => handleDelete(c.id)}
                      className="ml-auto cursor-pointer text-muted-foreground hover:text-destructive transition-colors"
                      aria-label="Delete comment"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
                <p className="mt-0.5 text-sm leading-relaxed text-foreground/80 break-words">{c.content}</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground text-center py-2">
          No comments yet — be the first.
        </p>
      )}
    </div>
  );
}
