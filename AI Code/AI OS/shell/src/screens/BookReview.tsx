import { BookOpen, Check, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import type { BookIdentityPending } from "../api/client";
import { ActionBar, type ActionDescriptor } from "../components/ActionBar";
import { AdapterFrame, Button, Metric } from "../components/primitives";
import type { AdapterProps } from "./types";

/**
 * Book photos need trustworthy identity before extraction and filing. The user
 * confirms the proposed identity, or submits a correction that triggers a fresh
 * lookup and another confirmation.
 */
export function BookReview({
  pending,
  busy,
  submit,
  onUnsupported,
}: AdapterProps<BookIdentityPending>) {
  const { payload } = pending;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(payload.proposed_title ?? "");
  const [author, setAuthor] = useState(payload.proposed_author ?? "");

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    {
      action: "confirm",
      label: <>Confirm identity <Check size={17} /></>,
      tone: "primary",
      // A correction is being composed; confirming the proposed identity now
      // would discard it silently.
      disabled: editing,
      buildPayload: () => ({}),
    },
    {
      action: "correct",
      label: <>Look up correction <RefreshCw size={16} /></>,
      tone: editing ? "primary" : "quiet",
      disabled: !editing || !title.trim(),
      buildPayload: () => ({ title, author: author || null }),
    },
  ], [author, editing, title]);

  return (
    <AdapterFrame
      title="Confirm the book"
      eyebrow="Identity before extraction"
      icon={<BookOpen />}
      aside={
        <>
          <Metric label="Confidence" value={payload.confidence ?? "Unknown"} />
          <Metric label="Source" value={payload.meta_source ?? "Unknown"} />
          <Metric label="Photos" value={payload.photo_count} />
        </>
      }
    >
      <div className="book-title">
        <p className="folio">{payload.proposed_year ?? "Year unknown"}</p>
        <h2>{payload.proposed_title ?? "No title found"}</h2>
        <p>{payload.proposed_author ?? "Author unknown"}</p>
      </div>
      <div className="slug">
        Filing as <code>{payload.resolved_slug ?? "unresolved"}</code>
      </div>
      {editing && (
        <div className="edit-grid">
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            Author
            <input value={author} onChange={(event) => setAuthor(event.target.value)} />
          </label>
        </div>
      )}
      <ActionBar
        adapter="book_identity"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      >
        {/* Local only: these controls never call the server. */}
        {editing ? (
          <Button onClick={() => setEditing(false)}>Cancel editing</Button>
        ) : (
          <Button onClick={() => setEditing(true)}>Edit fields</Button>
        )}
      </ActionBar>
    </AdapterFrame>
  );
}
