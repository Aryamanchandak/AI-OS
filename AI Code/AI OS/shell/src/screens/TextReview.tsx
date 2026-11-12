import { BookOpen, Check } from "lucide-react";
import { useMemo, useState } from "react";

import type { TextFilePending } from "../api/client";
import { ActionBar, type ActionDescriptor } from "../components/ActionBar";
import { AdapterFrame } from "../components/primitives";
import type { AdapterProps } from "./types";

/**
 * PDF/DOCX/text extraction produces editable Markdown rather than image
 * evidence. The user edits and approves the Markdown, or discards the source.
 */
export function TextReview({
  pending,
  busy,
  submit,
  onUnsupported,
}: AdapterProps<TextFilePending>) {
  const [text, setText] = useState(pending.payload.markdown_text);

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    {
      action: "approve",
      label: <>Approve document <Check size={17} /></>,
      tone: "primary",
      disabled: !text.trim(),
      buildPayload: () => ({ markdown_text: text }),
    },
    {
      action: "discard",
      label: "Discard",
      buildPayload: () => ({}),
    },
  ], [text]);

  return (
    <AdapterFrame title="Review extracted text" eyebrow="Document intake" icon={<BookOpen />}>
      <label>
        Markdown draft
        <textarea
          className="document-editor"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={18}
        />
      </label>
      <ActionBar
        adapter="text_file"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </AdapterFrame>
  );
}
