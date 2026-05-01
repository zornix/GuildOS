import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "./api-client";

function jsonResponse(body: unknown, ok: boolean, status: number) {
  const text = JSON.stringify(body);
  return {
    ok,
    status,
    text: async () => text,
  };
}

describe("ApiClient requestRead (GET retries)", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE = "http://test.local";
    process.env.NEXT_PUBLIC_USE_CROSS_ORIGIN_API = "true";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_API_BASE;
    delete process.env.NEXT_PUBLIC_USE_CROSS_ORIGIN_API;
  });

  it("retries on 503 then succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "unavailable" }, false, 503))
      .mockResolvedValueOnce(jsonResponse([], true, 200));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient();
    const result = await client.getMembers();
    expect(result).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry on 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "Unauthorized" }, false, 401));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient();
    await expect(client.getMembers()).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
