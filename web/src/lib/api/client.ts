import { artifacts, findings, studies } from "./fixtures";
import type { Artifact, Finding, ListResponse, Study, StudyApi } from "./types";
export type ApiMode = "fixture" | "live";
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export function parseApiMode(value?: string): ApiMode {
  if (!value || value === "fixture") return "fixture";
  if (value === "live") return "live";
  throw new ApiError("API mode must be fixture or live.", "INVALID_CONFIG");
}
export function createStudyApi(options: {
  mode: ApiMode;
  baseUrl?: string;
  fetcher?: typeof fetch;
}): StudyApi {
  if (options.mode === "fixture") {
    const copy = <T>(items: T[]): Promise<ListResponse<T>> =>
      Promise.resolve({ items: structuredClone(items) });
    const checkStudy = (id: string) => {
      if (!studies.some((study) => study.id === id))
        throw new ApiError("Study not found.", "NOT_FOUND", 404);
    };
    return {
      listStudies: () => copy(studies),
      listArtifacts: async (id) => {
        checkStudy(id);
        return copy(artifacts.filter((item) => item.study_id === id));
      },
      listFindings: async (id) => {
        checkStudy(id);
        return copy(findings.filter((item) => item.study_id === id));
      },
    };
  }
  const baseUrl = options.baseUrl?.trim().replace(/\/+$/, "");
  if (!baseUrl || !/^https?:\/\//.test(baseUrl))
    throw new ApiError(
      "Set NEXT_PUBLIC_API_BASE_URL to an HTTP API URL, including /api.",
      "INVALID_CONFIG",
    );
  const fetcher = options.fetcher ?? fetch;
  async function list<T>(path: string): Promise<ListResponse<T>> {
    let response: Response;
    try {
      response = await fetcher(`${baseUrl}${path}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
    } catch {
      throw new ApiError(
        "Could not reach the API. Check that the backend is running and permits this origin.",
        "NETWORK_ERROR",
      );
    }
    let body;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        "The API returned a response that is not JSON.",
        "INVALID_RESPONSE",
        response.status,
      );
    }
    if (!response.ok)
      throw new ApiError(
        body?.error?.message ?? `API request failed (${response.status}).`,
        body?.error?.code ?? "HTTP_ERROR",
        response.status,
      );
    if (!body || !Array.isArray(body.items))
      throw new ApiError(
        "The API response must contain an items array.",
        "INVALID_RESPONSE",
        response.status,
      );
    return body as ListResponse<T>;
  }
  return {
    listStudies: () => list<Study>("/studies"),
    listArtifacts: (id) =>
      list<Artifact>(`/studies/${encodeURIComponent(id)}/artifacts`),
    listFindings: (id) =>
      list<Finding>(`/studies/${encodeURIComponent(id)}/findings`),
  };
}
