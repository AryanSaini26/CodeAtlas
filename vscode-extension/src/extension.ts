import * as vscode from "vscode";

type SearchHit = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  line: number | null;
};

type SymbolRef = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  line: number | null;
};

type SymbolDetails = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file: string;
  start_line: number | null;
  end_line: number | null;
  signature: string | null;
  docstring: string | null;
  language: string | null;
  incoming: SymbolRef[];
  outgoing: SymbolRef[];
};

function apiHeaders(): Record<string, string> {
  const key = vscode.workspace.getConfiguration("codeatlas").get<string>("apiKey") ?? "";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (key) headers["X-API-Key"] = key;
  return headers;
}

function apiBase(): string {
  return (
    vscode.workspace.getConfiguration("codeatlas").get<string>("apiBase") ?? "http://127.0.0.1:8080"
  ).replace(/\/$/, "");
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { headers: apiHeaders() });
  if (!res.ok) {
    throw new Error(`CodeAtlas API ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

async function openSymbolInEditor(file: string, line: number | null): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showWarningMessage("Open a workspace to jump to symbols.");
    return;
  }
  const uri = vscode.Uri.joinPath(folders[0].uri, file);
  const doc = await vscode.workspace.openTextDocument(uri);
  const editor = await vscode.window.showTextDocument(doc);
  if (line && line > 0) {
    const pos = new vscode.Position(line - 1, 0);
    editor.selection = new vscode.Selection(pos, pos);
    editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
  }
}

async function searchSymbols(): Promise<void> {
  const query = await vscode.window.showInputBox({
    prompt: "CodeAtlas: search symbols (FTS)",
    placeHolder: "auth, User, handleLogin…",
  });
  if (!query) return;

  try {
    const data = await apiGet<{ hits: SearchHit[] }>(
      `/api/v1/search?q=${encodeURIComponent(query)}&limit=50`,
    );
    if (!data.hits.length) {
      vscode.window.showInformationMessage(`No matches for "${query}"`);
      return;
    }
    const picked = await vscode.window.showQuickPick(
      data.hits.map((h) => ({
        label: `${h.name} ${h.kind === "function" ? "()" : ""}`,
        description: h.kind,
        detail: `${h.file}${h.line ? `:${h.line}` : ""}`,
        hit: h,
      })),
      { matchOnDescription: true, matchOnDetail: true, placeHolder: "Jump to symbol" },
    );
    if (picked) await openSymbolInEditor(picked.hit.file, picked.hit.line);
  } catch (err) {
    vscode.window.showErrorMessage(`CodeAtlas: ${err instanceof Error ? err.message : String(err)}`);
  }
}

async function showSymbolAtCursor(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showInformationMessage("No active editor");
    return;
  }
  const word = editor.document.getText(editor.document.getWordRangeAtPosition(editor.selection.active));
  if (!word) {
    vscode.window.showInformationMessage("Select or place the cursor on a symbol name.");
    return;
  }
  try {
    const data = await apiGet<{ hits: SearchHit[] }>(
      `/api/v1/search?q=${encodeURIComponent(word)}&limit=10`,
    );
    if (!data.hits.length) {
      vscode.window.showInformationMessage(`No CodeAtlas match for "${word}"`);
      return;
    }
    const first = data.hits[0];
    const details = await apiGet<SymbolDetails>(
      `/api/v1/symbols/${encodeURIComponent(first.id)}`,
    );
    const panel = vscode.window.createWebviewPanel(
      "codeatlasSymbol",
      `CodeAtlas: ${details.name}`,
      vscode.ViewColumn.Beside,
      { enableScripts: false },
    );
    panel.webview.html = renderSymbolHtml(details);
  } catch (err) {
    vscode.window.showErrorMessage(`CodeAtlas: ${err instanceof Error ? err.message : String(err)}`);
  }
}

function renderSymbolHtml(d: SymbolDetails): string {
  const esc = (s: string) =>
    s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c);
  const refList = (refs: SymbolRef[]) =>
    refs.length
      ? `<ul>${refs.map((r) => `<li><code>${esc(r.qualified_name)}</code> <em>(${esc(r.kind)})</em> — ${esc(r.file)}${r.line ? `:${r.line}` : ""}</li>`).join("")}</ul>`
      : "<p><em>none</em></p>";

  return `<!doctype html><html><body style="font-family: var(--vscode-font-family)">
<h2>${esc(d.name)} <small>(${esc(d.kind)})</small></h2>
<p><strong>File:</strong> ${esc(d.file)}${d.start_line ? `:${d.start_line}` : ""}</p>
${d.signature ? `<pre>${esc(d.signature)}</pre>` : ""}
${d.docstring ? `<blockquote>${esc(d.docstring)}</blockquote>` : ""}
<h3>Outgoing (${d.outgoing.length})</h3>${refList(d.outgoing)}
<h3>Incoming (${d.incoming.length})</h3>${refList(d.incoming)}
</body></html>`;
}

async function openUi(): Promise<void> {
  await vscode.env.openExternal(vscode.Uri.parse(apiBase()));
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("codeatlas.openUi", openUi),
    vscode.commands.registerCommand("codeatlas.searchSymbols", searchSymbols),
    vscode.commands.registerCommand("codeatlas.showSymbolDetails", showSymbolAtCursor),
  );
}

export function deactivate(): void {
  // nothing
}
