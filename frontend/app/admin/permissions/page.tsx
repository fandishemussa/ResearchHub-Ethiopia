"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

export default function PermissionsPage() {
  const matrix = useQuery({
    queryKey: ["authorization-matrix"],
    queryFn: ({ signal }) => api.authorizationMatrix(signal),
  });

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[.2em] text-amber-700">
          Administration
        </p>
        <h1 className="mt-2 font-serif text-4xl font-bold">
          Permission matrix
        </h1>
        <p className="mt-2 text-stone-600 dark:text-stone-300">
          The canonical prototype grants used by backend authorization. Only
          platform role administrators can view this page.
        </p>
      </header>
      {matrix.isPending ? (
        <div
          className="h-96 animate-pulse rounded-2xl bg-stone-200 dark:bg-stone-800"
          aria-label="Loading permission matrix"
        />
      ) : matrix.isError || !matrix.data ? (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          The permission matrix is unavailable or access was denied.
          <button
            className="ml-3 underline"
            onClick={() => void matrix.refetch()}
          >
            Try again
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
          <table className="min-w-full border-collapse text-left text-sm">
            <caption className="sr-only">
              Roles and their granted permissions
            </caption>
            <thead className="sticky top-0 bg-stone-100 dark:bg-stone-800">
              <tr>
                <th scope="col" className="p-3 font-semibold">
                  Role
                </th>
                {matrix.data.permissions.map((permission) => (
                  <th
                    key={permission}
                    scope="col"
                    className="min-w-28 p-3 text-xs font-semibold"
                  >
                    {permission}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200 dark:divide-stone-800">
              {Object.entries(matrix.data.roles).map(([role, grants]) => (
                <tr key={role}>
                  <th scope="row" className="whitespace-nowrap p-3 font-medium">
                    {role.replaceAll("_", " ")}
                  </th>
                  {matrix.data.permissions.map((permission) => {
                    const granted = grants.includes(permission);
                    return (
                      <td key={permission} className="p-3 text-center">
                        {granted ? (
                          <Check
                            className="mx-auto text-emerald-700"
                            size={17}
                            aria-label="Granted"
                          />
                        ) : (
                          <span className="text-stone-300" aria-label="Denied">
                            —
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex gap-2 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
        <ShieldCheck className="shrink-0" size={18} aria-hidden="true" />
        University and department scope are additional constraints and are not
        represented as permission grants in this table.
      </div>
    </div>
  );
}
