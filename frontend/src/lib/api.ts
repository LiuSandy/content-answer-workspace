export type ApiEnvelope<T> = {
  ok: boolean;
  data: T;
  error?: {
    message: string;
  };
};

async function unwrap<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as ApiEnvelope<T> | Record<string, unknown>;

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? (payload as ApiEnvelope<T>).error?.message ?? "Request failed"
        : "Request failed";
    throw new Error(message);
  }

  if (typeof payload === "object" && payload && "ok" in payload) {
    return (payload as ApiEnvelope<T>).data;
  }

  return payload as T;
}

export async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url);
  return unwrap<T>(response);
}

export async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  return unwrap<T>(response);
}

export async function apiDelete<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "DELETE" });
  return unwrap<T>(response);
}

export async function apiPut<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  return unwrap<T>(response);
}

export async function apiUpload<T>(url: string, formData: FormData): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });
  return unwrap<T>(response);
}


