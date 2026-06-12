"use client";
import { useCallback } from "react";
import { useApi } from "./use-api";
import { api } from "../lib/api-client";
import type { MyPermissions } from "../lib/types";

/**
 * Resolved RBAC permissions for the signed-in member (GET /api/rbac/me/permissions).
 * `can(undefined)` is true so nav items without a requiredPermission stay visible.
 */
export function usePermissions() {
  const { data, loading, error, reload } = useApi<MyPermissions>(() => api.getMyPermissions(), []);
  const permissions = data?.permissions;

  const can = useCallback(
    (permission?: string) => !permission || (permissions ?? []).includes(permission),
    [permissions],
  );

  return { permissions: permissions ?? [], roles: data?.roles ?? [], loading, error, reload, can };
}
