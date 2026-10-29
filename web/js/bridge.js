// PythonBridge loads Pyodide and the yowd package, then forwards every
// call to yowd.web.api.WebApi. DocumentStore keeps the saved records in
// the browser's localStorage so they survive a page reload.

export class DocumentStore {
  static #KEY = "yowd-dms-documents-v1";

  load() {
    try { return localStorage.getItem(DocumentStore.#KEY) || "{}"; }
    catch { return "{}"; }
  }

  save(json) {
    try { localStorage.setItem(DocumentStore.#KEY, json); return true; }
    catch { return false; }
  }

  clear() {
    try { localStorage.removeItem(DocumentStore.#KEY); } catch { /* storage blocked */ }
  }
}

export class ApiError extends Error {
  constructor(message, kind, notices) {
    super(message);
    this.kind = kind || "Error";
    this.notices = notices || [];
  }
}

export class PythonBridge {
  static CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
  #pyodide = null;
  #api = null;
  #store;
  #listeners = [];

  constructor(store) { this.#store = store; }

  /** Subscribe to the notifications attached to every reply. */
  onNotices(listener) { this.#listeners.push(listener); }

  async start(progress = () => {}) {
    progress("Loading the Python runtime");
    const local = new URL("./pyodide/", document.baseURI).href;
    const base = await this.#exists(local + "pyodide.mjs") ? local : PythonBridge.CDN;
    const { loadPyodide } = await import(base + "pyodide.mjs");
    this.#pyodide = await loadPyodide({ indexURL: base });
    progress("Loading the delivery system");
    const bundle = await fetch(new URL("./app.zip", document.baseURI));
    if (!bundle.ok) throw new Error("app.zip is missing - run tools/build_web.py");
    this.#pyodide.unpackArchive(await bundle.arrayBuffer(), "zip", { extractDir: "/app" });
    this.#pyodide.runPython("import sys; sys.path.insert(0, '/app')");
    const config = this.#pyodide.FS.readFile("/app/config.json", { encoding: "utf8" });
    const WebApi = this.#pyodide.pyimport("yowd.web.api").WebApi;
    progress("Opening your saved records");
    this.#api = WebApi(config, this.#store.load());
  }

  /** Run a command; resolves with data or rejects with ApiError. */
  call(command, payload = {}) {
    const reply = JSON.parse(this.#api.call(command, JSON.stringify(payload)));
    this.#store.save(this.#api.documents());
    for (const listener of this.#listeners) listener(reply.notices || []);
    if (!reply.ok) throw new ApiError(reply.error, reply.kind, reply.notices);
    return reply.data;
  }

  async #exists(url) {
    try { return (await fetch(url, { method: "HEAD" })).ok; }
    catch { return false; }
  }
}
