import { apiUrl } from "@/lib/api";
import { parseItems } from "@/lib/menu";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const response = await fetch(apiUrl("/menu/items"), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok)
      return Response.json(
        { detail: "Меню временно недоступно" },
        { status: 503 },
      );
    return Response.json(parseItems(await response.json()), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { detail: "Меню временно недоступно" },
      { status: 503 },
    );
  }
}
