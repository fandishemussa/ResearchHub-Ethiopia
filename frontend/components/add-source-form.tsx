"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, LoaderCircle, Server } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { SourceCreate, SourceType } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui";

const types: Array<{ value: SourceType; label: string }> = [
  { value: "oai_pmh", label: "OAI-PMH Repository" },
  { value: "dspace_oai", label: "DSpace Repository" },
  { value: "ojs_oai", label: "OJS Journal" },
  { value: "xml_import", label: "XML Import Source" },
  { value: "json_import", label: "JSON Import Source" },
  { value: "csv_import", label: "CSV Import Source" },
];

export function AddSourceForm() {
  const router = useRouter();
  const universities = useQuery({
    queryKey: ["universities"],
    queryFn: ({ signal }) => api.universities(signal),
  });
  const [form, setForm] = useState<SourceCreate>({
    university_id: "",
    name: "",
    slug: "",
    source_type: "oai_pmh",
    metadata_prefix: "oai_dc",
    is_active: true,
    is_public: true,
  });
  const requiresEndpoint = ["oai_pmh", "dspace_oai", "ojs_oai"].includes(
    form.source_type,
  );
  const valid = useMemo(
    () =>
      Boolean(
        form.university_id &&
        form.name.trim().length >= 2 &&
        /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(form.slug) &&
        (!requiresEndpoint || form.oai_endpoint),
      ),
    [form, requiresEndpoint],
  );
  const test = useMutation({
    mutationFn: () => api.testSourceConfiguration(form),
  });
  const create = useMutation({
    mutationFn: () => api.createSource(form),
    onSuccess: () => router.push("/repositories"),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (valid) create.mutate();
  }
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link
        href="/repositories"
        className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800"
      >
        <ArrowLeft size={16} /> Back to repositories
      </Link>
      <header>
        <p className="text-xs font-bold uppercase tracking-[.2em] text-amber-700">
          Source management
        </p>
        <h1 className="mt-2 font-serif text-3xl font-bold">
          Add research source
        </h1>
        <p className="mt-2 text-sm text-stone-500">
          Configure and test a repository connection before saving it.
        </p>
      </header>
      <Card className="p-5 sm:p-7">
        <form onSubmit={submit} className="space-y-5">
          <Field label="Source type">
            <select
              value={form.source_type}
              onChange={(e) =>
                setForm({ ...form, source_type: e.target.value as SourceType })
              }
              className="input"
            >
              {types.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="University">
            {universities.isPending ? (
              <Skeleton className="h-11" />
            ) : (
              <select
                required
                value={form.university_id}
                onChange={(e) =>
                  setForm({ ...form, university_id: e.target.value })
                }
                className="input"
              >
                <option value="">Select university</option>
                {universities.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Source name">
              <input
                required
                minLength={2}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="input"
              />
            </Field>
            <Field label="Slug">
              <input
                required
                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                value={form.slug}
                onChange={(e) =>
                  setForm({ ...form, slug: e.target.value.toLowerCase() })
                }
                placeholder="haramaya-etd"
                className="input"
              />
            </Field>
          </div>
          {requiresEndpoint && (
            <>
              <Field label="OAI-PMH endpoint">
                <input
                  required
                  type="url"
                  value={form.oai_endpoint || ""}
                  onChange={(e) =>
                    setForm({ ...form, oai_endpoint: e.target.value })
                  }
                  placeholder="https://repository.example.edu/oai/request"
                  className="input"
                />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Metadata prefix">
                  <input
                    value={form.metadata_prefix}
                    onChange={(e) =>
                      setForm({ ...form, metadata_prefix: e.target.value })
                    }
                    className="input"
                  />
                </Field>
                <Field label="Set specification">
                  <input
                    value={form.set_spec || ""}
                    onChange={(e) =>
                      setForm({ ...form, set_spec: e.target.value })
                    }
                    className="input"
                  />
                </Field>
              </div>
            </>
          )}
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
              />{" "}
              Active
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_public}
                onChange={(e) =>
                  setForm({ ...form, is_public: e.target.checked })
                }
              />{" "}
              Public
            </label>
          </div>
          {test.data && (
            <div
              role="status"
              className={`rounded-xl p-4 text-sm ${test.data.success ? "bg-emerald-50 text-emerald-900" : "bg-red-50 text-red-900"}`}
            >
              <strong>
                {test.data.success
                  ? "Connection successful"
                  : "Connection failed"}
              </strong>
              <p className="mt-1">
                {test.data.repository_name ||
                  test.data.errors.join("; ") ||
                  test.data.warnings.join("; ")}
              </p>
              {test.data.protocol_version && (
                <p>
                  OAI-PMH {test.data.protocol_version} ·{" "}
                  {test.data.response_time_ms} ms
                </p>
              )}
            </div>
          )}
          {(test.isError || create.isError) && (
            <p role="alert" className="text-sm text-red-700">
              {(test.error || create.error)?.message}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              disabled={!valid || test.isPending}
              onClick={() => test.mutate()}
              className="inline-flex items-center gap-2 rounded-lg border border-stone-300 px-4 py-2 text-sm font-semibold disabled:opacity-50"
            >
              <Server size={16} />
              {test.isPending ? "Testing…" : "Test connection"}
            </button>
            <button
              disabled={!valid || create.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {create.isPending ? (
                <LoaderCircle className="animate-spin" size={16} />
              ) : (
                <CheckCircle2 size={16} />
              )}{" "}
              Save source
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm font-semibold">
      <span className="mb-2 block">{label}</span>
      {children}
    </label>
  );
}
