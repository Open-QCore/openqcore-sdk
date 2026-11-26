// Compile-only: public types read well from a user's point of view.
import OpenQCore, { NotFoundError, type ChatChunk, type ChatCompletion, type Job } from "../src/index.js";

async function usage(): Promise<void> {
  const client = new OpenQCore({ apiKey: "k" });
  const session = await client.sessions.create({ title: "x" });
  const reply: ChatCompletion = await client.chat.create({ session_id: session.id, message: "hi" });
  const tokens: number = reply.usage.total_tokens;
  const stream = await client.chat.stream({ session_id: session.id, message: "hi" });
  for await (const c of stream) {
    const piece: string | undefined = c.content;
    const stage: string | undefined = c.status?.stage;
    void piece; void stage; void (c satisfies ChatChunk);
  }
  const job: Job = await client.images.generate({ prompt: "p", size: "1024x1024" });
  try {
    await client.knowledge.retrieve("k");
  } catch (e) {
    if (e instanceof NotFoundError) void e.traceId;
  }
  void tokens; void job;
}
void usage;
