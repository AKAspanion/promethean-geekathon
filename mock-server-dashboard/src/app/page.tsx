"use client";

import { useState, useCallback } from "react";
import { CollectionTable } from "@/components/Collections/CollectionTable";
import { CollectionModal } from "@/components/Collections/CollectionModal";
import {
  useCollectionsList,
  useCreateCollection,
  useUpdateCollection,
  useDeleteCollection,
} from "@/lib/queries/collections";
import type { Collection, CreateCollectionInput } from "@/lib/types";

export default function HomePage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCollection, setEditingCollection] = useState<Collection | null>(
    null
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { data, isLoading, error } = useCollectionsList();
  const createMutation = useCreateCollection();

  const openCreate = useCallback(() => {
    setEditingCollection(null);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((c: Collection) => {
    setEditingCollection(c);
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setEditingCollection(null);
    if (createMutation.isSuccess) createMutation.reset();
  }, [createMutation]);

  const handleCreate = useCallback(
    (body: CreateCollectionInput) => {
      createMutation.mutate(body, {
        onSuccess: () => closeModal(),
      });
    },
    [createMutation, closeModal]
  );

  const updateMutation = useUpdateCollection(editingCollection?.id ?? "");

  const handleUpdate = useCallback(
    (_idOrSlug: string, body: CreateCollectionInput) => {
      updateMutation.mutate(body, { onSuccess: () => closeModal() });
    },
    [updateMutation, closeModal]
  );
  const deleteMutation = useDeleteCollection();

  const handleDelete = useCallback(
    (c: Collection) => {
      if (!confirm(`Delete collection "${c.name}"? This will delete all its records.`))
        return;
      setDeletingId(c.id);
      deleteMutation.mutate(c.id, {
        onSettled: () => setDeletingId(null),
      });
    },
    [deleteMutation]
  );

  const collections = data?.items ?? [];

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
          Collections
        </h1>
        <button
          type="button"
          onClick={openCreate}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          New collection
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {error.message}
        </div>
      )}

      {isLoading ? (
        <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : (
        <CollectionTable
          collections={collections}
          onEdit={openEdit}
          onDelete={handleDelete}
          isDeletingId={deletingId}
        />
      )}

      {modalOpen && (
        <CollectionModal
          collection={editingCollection}
          onClose={closeModal}
          onCreate={handleCreate}
          onUpdate={editingCollection ? handleUpdate : undefined}
          isCreatePending={createMutation.isPending}
          isUpdatePending={updateMutation.isPending}
        />
      )}
    </main>
  );
}
