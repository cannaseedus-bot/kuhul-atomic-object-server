import { readFile } from "node:fs/promises";
import { getLlama, LlamaChatSession } from "node-llama-cpp";
import { pathToFileURL } from "node:url";

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const modelPath = arg("--model", "");
const word = arg("--word", "");
const contextSize = Number(arg("--num-ctx", "30000"));
const maxTokens = Number(arg("--max-tokens", "4096"));
const prompt = await new Promise((resolve, reject) => {
  let data = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", chunk => data += chunk);
  process.stdin.on("end", () => resolve(data));
  process.stdin.on("error", reject);
});

if (!modelPath || !word || !prompt) {
  console.error("Usage: distill-gguf.mjs --model <file.gguf> --word <word> [--num-ctx 30000] [--max-tokens 4096]");
  process.exit(2);
}

try {
  const schemaUrl = new URL("./neighborhood-output.schema.json", import.meta.url);
  const outputSchema = JSON.parse(await readFile(schemaUrl, "utf8"));
  const llama = await getLlama();
  const model = await llama.loadModel({ modelPath });
  const context = await model.createContext({ contextSize });
  const session = new LlamaChatSession({ contextSequence: context.getSequence() });
  const grammar = await llama.createGrammarForJsonSchema(outputSchema);
  const started = Date.now();
  let chars = 0;
  console.error(`Loading local GGUF: ${modelPath}`);
  const response = await session.prompt(prompt, {
    grammar,
    maxTokens,
    temperature: 0.2,
    onTextChunk(chunk) {
      chars += chunk.length;
      if (chars % 240 < chunk.length) {
        const seconds = (Date.now() - started) / 1000;
        console.error(`\rGenerating ${word}: ~${Math.round(chars / 4)} tokens, ${seconds.toFixed(0)}s`);
      }
    }
  });
  console.error(`\nCompleted ${word} in ${((Date.now() - started) / 1000).toFixed(1)}s`);
  process.stdout.write(response);
  await context.dispose();
  await model.dispose();
  await llama.dispose();
} catch (error) {
  console.error(`Local GGUF distillation failed: ${error?.stack ?? error}`);
  process.exitCode = 1;
}
