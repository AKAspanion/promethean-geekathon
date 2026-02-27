"use client";

import { useCallback } from "react";
import { CollectionForm } from "./CollectionForm";
import type { Collection, CreateCollectionInput } from "@/lib/types";

interface CollectionModalProps {
  collection?: Collection | null;
  onClose: () => void;
  onCreate: (data: CreateCollectionInput) => void;
  onUpdate?: (idOrSlug: string, data: CreateCollectionInput) => void;
  isCreatePending?: boolean;
  isUpdatePending?: boolean;
}

export function CollectionModal({
  collection,
  onClose,
  onCreate,
  onUpdate,
  isCreatePending = false,
  isUpdatePending = false,
}: CollectionModalProps) {
  const isEdit = !!collection;

  const handleSubmit = useCallback(
    (data: CreateCollectionInput) => {
      if (isEdit && collection && onUpdate) {
        onUpdate(collection.id, data);
      } else {
        onCreate(data);
      }
    },
    [isEdit, collection, onCreate, onUpdate]
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="collection-modal-title"
    >
      <div
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="collection-modal-title" className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {isEdit ? "Edit collection" : "New collection"}
        </h2>
        <CollectionForm
          collection={collection}
          onSubmit={handleSubmit}
          onCancel={onClose}
          isPending={isCreatePending || isUpdatePending}
          submitLabel={isEdit ? "Update" : "Create"}
        />
      </div>
    </div>
  );
}
