import { useEffect, useState } from "react";
import { ApiError } from "../api/client";

interface Loaded<T> {
  key: string;
  data?: T;
  error?: ApiError;
}

/**
 * One place for "loading, failed, or here", so every page reports failure the same way.
 *
 * The key names the request. Anything not answered under the current key is still loading, which
 * is what keeps a stale answer from being shown next to a fresh question.
 */
export function useAsync<T>(key: string, load: () => Promise<T>) {
  const [loaded, setLoaded] = useState<Loaded<T>>({ key: "" });

  useEffect(() => {
    let live = true;
    load()
      .then((data) => live && setLoaded({ key, data }))
      .catch((error: unknown) => live && setLoaded({ key, error: asApiError(error) }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const current = loaded.key === key;
  return {
    data: current ? loaded.data : undefined,
    error: current ? loaded.error : undefined,
    loading: !current,
  };
}

export function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError(0, "unreachable", "The Hub could not be reached.");
}
