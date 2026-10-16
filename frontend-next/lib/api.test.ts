import { describe, expect, it } from "vitest";

import { readSseStream } from "./api";

// A reader that hands the stream over in the given pieces, the way the network may split it.
function readerOf(...pieces: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      pieces.forEach((piece) => controller.enqueue(encoder.encode(piece)));
      controller.close();
    }
  }).getReader();
}

async function collect(...pieces: string[]) {
  const tokens: string[] = [];
  const done: unknown[] = [];
  await readSseStream(readerOf(...pieces), {
    onToken: (token) => tokens.push(token),
    onDone: (meta) => done.push(meta)
  });
  return { tokens, done };
}

describe("readSseStream", () => {
  it("delivers delta tokens in order and the done payload", async () => {
    const result = await collect(
      'event: delta\ndata: {"token":"Hello "}\n\n',
      'event: delta\ndata: {"token":"world"}\n\n',
      'event: done\ndata: {"message_id":"m1"}\n\n'
    );

    expect(result.tokens).toEqual(["Hello ", "world"]);
    expect(result.done).toEqual([{ message_id: "m1" }]);
  });

  it("joins an event split across network chunks", async () => {
    const result = await collect('event: del', 'ta\ndata: {"tok', 'en":"split"}\r\n\r\n');

    expect(result.tokens).toEqual(["split"]);
  });

  it("skips malformed and unknown events without stopping", async () => {
    const result = await collect(
      "event: delta\ndata: {not json}\n\n",
      'event: ping\ndata: {"token":"ignored"}\n\n',
      'event: delta\ndata: {"token":"kept"}\n\n'
    );

    expect(result.tokens).toEqual(["kept"]);
    expect(result.done).toEqual([]);
  });
});
