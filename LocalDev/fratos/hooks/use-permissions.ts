"use client";
import { useCallback } from "react";
import { useApi } from "./use-api";
import { api } from "../lib/api-client";
import { devAuthPermissions, isDevAuthBypassEnabled } from "../lib/dev-auth";
import type { MyPermissions } from "../lib/types";

/**
 * Resolved RBAC permissions for the signed-in member (GET /api/rbac/me/permissions).
 * `can(undefined)` is true so nav items without a requiredPermission stay visible.
 */
export function usePermissions() {
  const devAuthBypass = isDevAuthBypassEnabled();
  const { data, loading, error, reload } = useApi<MyPermissions>(
    () => (devAuthBypass ? Promise.resolve(devAuthPermissions) : api.getMyPermissions()),
    [devAuthBypass],
  );
  const resolved = devAuthBypass ? devAuthPermissions : data;
  const permissions = resolved?.permissions;

  const can = useCallback(
    (permission?: string) => !permission || devAuthBypass || (permissions ?? []).includes(permission),
    [devAuthBypass, permissions],
  );

  return {
    permissions: permissions ?? [],
    roles: resolved?.roles ?? [],
    loading: devAuthBypass ? false : loading,
    error: devAuthBypass ? null : error,
    reload,
    can,
  };
}
