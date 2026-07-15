import type { Metadata } from "next";
import { AddSourceForm } from "@/components/add-source-form";

export const metadata: Metadata = {
  title: "Add source | ResearchHub Ethiopia",
};
export default function NewSourcePage() {
  return <AddSourceForm />;
}
