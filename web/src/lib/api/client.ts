import { artifacts, changes, findings, graph, studies } from "./fixtures";
import type { Artifact, Finding, Graph, ListResponse, Study, StudyApi } from "./types";
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
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
      getDependencyData: async (id) => {
        checkStudy(id);
        return structuredClone({ graph, changes });
      },
      // Fixture artifacts do not include original binary files.
      getOriginalFileUrl: async () => null,
    };
  }
  const baseUrl = options.baseUrl?.trim().replace(/\/+$/, "");
  if (!baseUrl || !/^https?:\/\//.test(baseUrl))
    throw new ApiError(
      "Set NEXT_PUBLIC_API_BASE_URL to an HTTP API URL, including /api.",
      "INVALID_CONFIG",
    );
  const fetcher = options.fetcher ?? fetch;
  async function request(path: string): Promise<{ body: unknown; status: number }> {
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
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        "The API returned a response that is not JSON.",
        "INVALID_RESPONSE",
        response.status,
      );
    }
    if (!response.ok) {
      const error = isRecord(body) && isRecord(body.error) ? body.error : {};
      throw new ApiError(
        typeof error.message === "string"
          ? error.message
          : `API request failed (${response.status}).`,
        typeof error.code === "string" ? error.code : "HTTP_ERROR",
        response.status,
      );
    }
    return { body, status: response.status };
  }
  async function list<T>(path: string): Promise<ListResponse<T>> {
    const { body, status } = await request(path);
    if (!isRecord(body) || !Array.isArray(body.items))
      throw new ApiError(
        "The API response must contain an items array.",
        "INVALID_RESPONSE",
        status,
      );
    return body as unknown as ListResponse<T>;
  }
  async function dependencyGraph(studyId: string): Promise<Graph> {
    const { body, status } = await request(
      `/studies/${encodeURIComponent(studyId)}/graph`,
    );
    if (
      !isRecord(body) ||
      !Array.isArray(body.facts) ||
      !Array.isArray(body.dependencies)
    )
      throw new ApiError(
        "The API graph response must contain facts and dependencies arrays.",
        "INVALID_RESPONSE",
        status,
      );
    return body as unknown as Graph;
  }
  async function originalFileUrl(_artifactId: string, versionId: string) {
    let result: { body: unknown; status: number };
    try {
      result = await request(
        `/versions/${encodeURIComponent(versionId)}/source`,
      );
    } catch (error) {
      // A version without an uploaded original is documented as a 404.
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
    const { body, status } = result;
    if (!isRecord(body) || !("url" in body))
      throw new ApiError(
        "The source response must contain a URL or null.",
        "INVALID_RESPONSE",
        status,
      );
    if (body.url === null) return null;
    if (typeof body.url !== "string" || !body.url.trim())
      throw new ApiError("The source URL must be a non-empty string or null.", "INVALID_RESPONSE", status);
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(body.url, baseUrl);
    } catch {
      throw new ApiError("The source URL is invalid.", "INVALID_RESPONSE", status);
    }
    if (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:")
      throw new ApiError("The source URL must use HTTP or HTTPS.", "INVALID_RESPONSE", status);
    return parsedUrl.toString();
  }
  return {
    listStudies: () => list<Study>("/studies"),
    listArtifacts: (id) =>
      list<Artifact>(`/studies/${encodeURIComponent(id)}/artifacts`),
    listFindings: (id) =>
      list<Finding>(`/studies/${encodeURIComponent(id)}/findings`),
    getDependencyData: async (id) => ({
      graph: await dependencyGraph(id),
      // The backend does not expose change records yet; live highlights remain pending.
      changes: [],
    }),
    getOriginalFileUrl: originalFileUrl,
  };
}
