// Small DOM helpers. All text is set with textContent, never innerHTML,
// so data typed by users can never inject markup into the page.

export class Dom {
  /** Create an element: Dom.el("p", {class: "muted"}, "text", child). */
  static el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (key === "class") {
        node.className = value;
      } else if (value === true) {
        node.setAttribute(key, "");
      } else {
        node.setAttribute(key, String(value));
      }
    }
    Dom.append(node, children);
    return node;
  }

  static append(node, children) {
    for (const child of children.flat(Infinity)) {
      if (child === undefined || child === null || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  static clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  static replace(node, ...children) {
    Dom.clear(node);
    return Dom.append(node, children);
  }

  static notice(text, kind = "bad") {
    return Dom.el("div", { class: `notice ${kind}`, role: kind === "bad" ? "alert" : "status" }, text);
  }

  static button(text, onClick, cls = "btn", attrs = {}) {
    return Dom.el("button", { type: "button", class: cls, onClick, ...attrs }, text);
  }

  /** A labelled input. Returns {wrap, input}. */
  static field(labelText, name, attrs = {}, optional = false) {
    const id = `f-${name}-${Math.random().toString(36).slice(2, 8)}`;
    const input = Dom.el("input", { id, name, ...attrs });
    const label = Dom.el("label", { for: id }, labelText, optional ? Dom.el("span", { class: "opt" }, " (optional)") : null);
    const wrap = Dom.el("div", { class: `field ${attrs["data-width"] || ""}` }, label, input);
    return { wrap, input };
  }

  static select(labelText, name, options, attrs = {}) {
    const id = `f-${name}-${Math.random().toString(36).slice(2, 8)}`;
    const select = Dom.el("select", { id, name, ...attrs },
      options.map(([value, text]) => Dom.el("option", { value }, text)));
    const wrap = Dom.el("div", { class: "field" }, Dom.el("label", { for: id }, labelText), select);
    return { wrap, input: select };
  }

  static table(headings, rows, numeric = []) {
    return Dom.el("div", { class: "scroll" },
      Dom.el("table", {},
        Dom.el("thead", {}, Dom.el("tr", {}, headings.map((h, i) =>
          Dom.el("th", { class: numeric.includes(i) ? "num" : null, scope: "col" }, h)))),
        Dom.el("tbody", {}, rows.map((row) => Dom.el("tr", {}, row.map((cell, i) =>
          Dom.el("td", { class: numeric.includes(i) ? "num" : null }, cell)))))));
  }

  /** Read a form's named inputs into a plain object. */
  static values(form) {
    const out = {};
    for (const input of form.querySelectorAll("input, select, textarea")) {
      if (!input.name) continue;
      if (input.type === "checkbox") out[input.name] = input.checked;
      else if (input.type === "radio") { if (input.checked) out[input.name] = input.value; }
      else out[input.name] = input.value.trim();
    }
    return out;
  }
}

/** A row of tabs; calls onChange(key) and remembers the selection. */
export class Tabs {
  #buttons = new Map();
  #onChange;
  constructor(items, selected, onChange) {
    this.#onChange = onChange;
    this.node = Dom.el("div", { class: "tabs", role: "tablist" });
    for (const [key, text, count] of items) {
      const button = Dom.el("button", { type: "button", role: "tab", onClick: () => this.select(key) },
        text, count ? Dom.el("span", { class: "count" }, count) : null);
      this.#buttons.set(key, button);
      this.node.append(button);
    }
    this.select(selected, false);
  }

  select(key, notify = true) {
    for (const [k, b] of this.#buttons) b.setAttribute("aria-selected", String(k === key));
    if (notify) this.#onChange(key);
  }
}
