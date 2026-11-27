import { redirect } from "next/navigation";

/**
 * The People list lives at /admin/reviewers (AdminNav); /admin/people is the
 * parent of one person's page (/admin/people/[id]). Trimming a person's URL
 * back to here lands on the list rather than a 404.
 */
export default function PeopleIndex() {
  redirect("/admin/reviewers");
}
