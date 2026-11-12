import { useEffect, useState } from "react";

import { api } from "../api/client";

/**
 * Fetches the evidence photo behind the currently pending item (ImageReview's
 * OCR passage, or a knowledge proposal's source page) as an object URL, and
 * revokes it on cleanup. Shared so both screens degrade the same way: a 404
 * (this item has no photo, or it's no longer the current one) surfaces as
 * `imageError`, never a thrown render.
 */
export function useEvidenceImage(token: string, runId: string, itemId: string) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setImageUrl(null);
    setImageError(null);
    void api.evidence(token, runId, itemId)
      .then((url) => {
        if (!active) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setImageUrl(url);
      })
      .catch((error: Error) => {
        if (active) setImageError(error.message);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, runId, itemId]);

  return { imageUrl, imageError };
}
