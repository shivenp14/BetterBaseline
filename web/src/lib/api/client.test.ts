import { describe, expect, it, vi } from "vitest";
import { ApiError, createStudyApi, parseApiMode } from "./client";
import { studyId } from "./fixtures";

describe("fixture API", () => {
  it("serves the synthetic study without fetching and preserves version history", async () => {
    const fetcher = vi.fn<typeof fetch>();
    const api = createStudyApi({ mode: "fixture", fetcher });
    expect((await api.listStudies()).items[0].id).toBe(studyId);
    const { items: artifacts } = await api.listArtifacts(studyId);
    const { items: findings } = await api.listFindings(studyId);
    expect(artifacts).toHaveLength(4);
    expect(findings).toHaveLength(2);
    expect(artifacts[0].versions.map((v) => v.version_number)).toEqual([1, 2]);
    expect(artifacts[0].versions[1].previous_version_id).toBe(
      artifacts[0].versions[0].id,
    );
    expect(
      findings.some((f) => f.affected_artifact_id === artifacts[3].id),
    ).toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("isolates returned fixtures and rejects unknown study IDs", async () => {
    const api = createStudyApi({ mode: "fixture" });
    (await api.listArtifacts(studyId)).items[0].name = "mutated";
    expect((await api.listArtifacts(studyId)).items[0].name).toBe(
      "Study protocol",
    );
    await expect(api.listArtifacts("missing")).rejects.toMatchObject({
      code: "NOT_FOUND",
      status: 404,
    });
    await expect(api.listFindings("missing")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("live API", () => {
  it("uses the shared routes, list envelope, and URL-encoded study ID", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => Response.json({ items: [] }));
    const api = createStudyApi({
      mode: "live",
      baseUrl: "http://localhost:8000/api/",
      fetcher,
    });
    await expect(api.listStudies()).resolves.toEqual({ items: [] });
    await api.listArtifacts("study/id");
    await api.listFindings(studyId);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8000/api/studies",
      "http://localhost:8000/api/studies/study%2Fid/artifacts",
      `http://localhost:8000/api/studies/${studyId}/findings`,
    ]);
  });
  it("preserves backend error code and message", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { error: { code: "UNAVAILABLE", message: "Study unavailable" } },
          { status: 503 },
        ),
      );
    await expect(
      createStudyApi({
        mode: "live",
        baseUrl: "https://example.test/api",
        fetcher,
      }).listStudies(),
    ).rejects.toMatchObject({
      code: "UNAVAILABLE",
      message: "Study unavailable",
      status: 503,
    });
  });
  it("reports network, non-JSON, and malformed list responses", async () => {
    for (const [response, code] of [
      [new Response("not JSON"), "INVALID_RESPONSE"],
      [Response.json({ studies: [] }), "INVALID_RESPONSE"],
    ] as const) {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response);
      await expect(
        createStudyApi({
          mode: "live",
          baseUrl: "https://example.test/api",
          fetcher,
        }).listStudies(),
      ).rejects.toMatchObject({ code });
    }
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      createStudyApi({
        mode: "live",
        baseUrl: "https://example.test/api",
        fetcher,
      }).listStudies(),
    ).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
  it("defaults to fixture mode and requires explicit valid configuration for live mode", () => {
    expect(parseApiMode()).toBe("fixture");
    expect(parseApiMode("live")).toBe("live");
    expect(() => parseApiMode("typo")).toThrow(
      "API mode must be fixture or live",
    );
    expect(() => createStudyApi({ mode: "live" })).toThrow(
      "NEXT_PUBLIC_API_BASE_URL",
    );
  });
});
