/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useApi } from "./use-api";

describe("useApi", () => {
  it("sets error on failure then clears on successful reload", async () => {
    let call = 0;
    const fetchFn = vi.fn(async () => {
      call += 1;
      if (call === 1) throw new Error("network boom");
      return [1, 2, 3];
    });

    const { result } = renderHook(() => useApi(() => fetchFn(), []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("network boom");
    expect(result.current.data).toBeNull();

    await act(async () => {
      result.current.reload();
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual([1, 2, 3]);
  });
});
