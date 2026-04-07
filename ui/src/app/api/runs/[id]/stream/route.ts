import { getRunService } from "@/lib/server";
import type { RunEvent } from "@/lib/types";

export const runtime = "nodejs";

function encodeSse(event: string, payload: unknown): Uint8Array {
  const data = `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
  return new TextEncoder().encode(data);
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const service = getRunService();

  const run = service.getRun(id);
  if (!run) {
    return new Response(JSON.stringify({ error: "Run not found." }), {
      status: 404,
      headers: {
        "Content-Type": "application/json",
      },
    });
  }

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encodeSse("snapshot", { run, logs: service.getLogTail(id) }));

      const unsubscribe = service.subscribe(id, (event: RunEvent) => {
        controller.enqueue(encodeSse(event.type, event.payload));
      });

      const heartbeat = setInterval(() => {
        controller.enqueue(encodeSse("ping", { runId: id }));
      }, 15000);

      request.signal.addEventListener("abort", () => {
        clearInterval(heartbeat);
        unsubscribe();
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
