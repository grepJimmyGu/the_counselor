"use client";

import { useState } from "react";
import { Check, Share2 } from "lucide-react";
import { useSession } from "next-auth/react";

import { Button } from "@/components/ui/button";

interface Props {
  /** URL path to share, e.g. "/s/my-strategy-abc123". */
  path: string;
}

/**
 * Stage 4a — share button.
 *
 * Builds an absolute URL and appends ?via=<current user's handle> when the
 * user is authenticated and has a handle. Anonymous viewers get the bare URL
 * (no attribution).
 *
 * Uses navigator.clipboard.writeText with a 1.5s "Copied!" confirmation.
 * Falls back to a manual prompt if clipboard isn't available.
 */
export function ShareButton({ path }: Props) {
  const { data: session } = useSession();
  const [copied, setCopied] = useState(false);

  const handle = (session?.user as unknown as { handle?: string } | null)?.handle;

  async function handleShare() {
    const base = typeof window !== "undefined" ? window.location.origin : "";
    const url = handle ? `${base}${path}?via=${encodeURIComponent(handle)}` : `${base}${path}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Some browsers (Safari without HTTPS, embedded webviews) block
      // clipboard. Fallback to prompt so the user can copy manually.
      // eslint-disable-next-line no-alert
      window.prompt("Copy this link:", url);
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={handleShare} className="gap-2">
      {copied ? (
        <>
          <Check className="h-4 w-4" />
          Copied!
        </>
      ) : (
        <>
          <Share2 className="h-4 w-4" />
          Share
        </>
      )}
    </Button>
  );
}
