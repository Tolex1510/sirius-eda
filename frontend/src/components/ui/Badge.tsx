import { labels } from "../../lib/format";

export function Badge({ status }: { status: string }) {
  return <span className={"badge " + status}>{labels[status] || status}</span>;
}
