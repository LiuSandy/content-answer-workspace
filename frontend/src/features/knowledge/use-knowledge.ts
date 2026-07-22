import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchKnowledgeDocuments,
  uploadKnowledgeDocument,
  importKnowledgeUrl,
  fetchDocumentMarkdown,
  updateDocumentMarkdown,
  confirmKnowledgeDocument,
  reconvertKnowledgeDocument,
  deleteKnowledgeDocument,
} from "./knowledge-api";

export function useKnowledgeDocuments(workspaceId: string = "default", statusFilter?: string) {
  return useQuery({
    queryKey: ["knowledge-documents", workspaceId, statusFilter],
    queryFn: () => fetchKnowledgeDocuments(workspaceId, statusFilter),
    refetchInterval: (query) => {
      const docs = query.state.data?.documents || [];
      const hasActiveProcessing = docs.some(
        (doc) => doc.status === "pending" || doc.status === "indexing"
      );
      return hasActiveProcessing ? 2000 : false;
    },
  });
}

export function useKnowledgeMarkdown(documentId?: string, isCandidate: boolean = false) {
  return useQuery({
    queryKey: ["knowledge-markdown", documentId, isCandidate],
    queryFn: () => (documentId ? fetchDocumentMarkdown(documentId, isCandidate) : null),
    enabled: !!documentId,
  });
}

export function useKnowledgeMutations(workspaceId: string = "default") {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["knowledge-documents", workspaceId] });
    queryClient.invalidateQueries({ queryKey: ["knowledge-markdown"] });
  };

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadKnowledgeDocument(file, workspaceId),
    onSuccess: invalidate,
  });

  const importUrlMutation = useMutation({
    mutationFn: (url: string) => importKnowledgeUrl(url, workspaceId),
    onSuccess: invalidate,
  });

  const updateMarkdownMutation = useMutation({
    mutationFn: ({ documentId, markdown }: { documentId: string; markdown: string }) =>
      updateDocumentMarkdown(documentId, markdown, workspaceId),
    onSuccess: invalidate,
  });

  const confirmMutation = useMutation({
    mutationFn: (documentId: string) => confirmKnowledgeDocument(documentId),
    onSuccess: invalidate,
  });

  const reconvertMutation = useMutation({
    mutationFn: (documentId: string) => reconvertKnowledgeDocument(documentId),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (documentId: string) => deleteKnowledgeDocument(documentId),
    onSuccess: invalidate,
  });

  return {
    uploadMutation,
    importUrlMutation,
    updateMarkdownMutation,
    confirmMutation,
    reconvertMutation,
    deleteMutation,
  };
}
