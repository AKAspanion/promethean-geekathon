"use client";

import { RecordForm } from "./RecordForm";
import type { RecordItem } from "@/lib/types";

interface RecordModalProps {
  record?: RecordItem | null;
  onClose: () => void;
  onSubmit: (data: Record<string, unknown>) => void;
  isPending?: boolean;
  title?: string;
}

export function RecordModal({
  record,
  onClose,
  onSubmit,
  isPending = false,
  title,
}: RecordModalProps) {
  const isEdit = !!record;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="record-modal-title"
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="record-modal-title" className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {title ?? (isEdit ? "Edit record" : "New record")}
        </h2>
        <RecordForm
          record={record}
          onSubmit={onSubmit}
          onCancel={onClose}
          isPending={isPending}
          submitLabel={isEdit ? "Update" : "Create"}
        />
      </div>
    </div>
  );
}
