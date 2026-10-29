// Application shell: start Python, show the portals and the message feed.
import { Dom } from "./dom.js";
import { Cards } from "./cards.js";
import { PythonBridge, DocumentStore } from "./bridge.js";
import { CustomerPortal } from "./customer.js";
import { OfficePortal } from "./office.js";
import { DriverPortal } from "./driver.js";

class TrackPortal {
  #api;
  constructor(api) { this.#api = api; }

  render(root) {
    const out = Dom.el("div", { "aria-live": "polite", style: "margin-top:1rem" });
    const ref = Dom.field("Tracking reference", "ref", { placeholder: "YW10009", autocomplete: "off" });
    Dom.replace(root, Dom.el("h2", {}, "Track a delivery"),
      Dom.el("p", { class: "muted" }, "Recipients and customers: enter the reference from your message."),
      Dom.el("form", { class: "row", onSubmit: (e) => { e.preventDefault();
        try { Dom.replace(out, Cards.delivery(this.#api.call("track", { ref: ref.input.value }))); }
        catch (error) { Dom.replace(out, Dom.notice(error.message)); } } },
        ref.wrap, Dom.el("div", { class: "field", style: "flex:0" }, Dom.el("button", { type: "submit", class: "btn" }, "Track"))),
      out);
  }
}

class MessageFeed {
  #list; #empty;
  constructor(node) {
    this.#list = Dom.el("ol");
    this.#empty = Dom.el("p", { class: "small muted" }, "Messages the system sends will appear here.");
    Dom.replace(node, Dom.el("h2", {}, "Messages sent"),
      Dom.el("p", { class: "small muted" }, "SMS, email and office alerts. In this demo nothing leaves your browser."),
      this.#empty, this.#list);
  }

  add(lines) {
    if (!lines.length) return;
    this.#empty.hidden = true;
    const time = new Date().toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit" });
    for (const line of lines) {
      const match = line.match(/^\[(.+?)\] (.*)$/);
      const to = match ? match[1] : "";
      const body = match ? match[2] : line;
      this.#list.prepend(Dom.el("li", { class: `msg${to.startsWith("ALERT") ? " alert" : ""}` },
        Dom.el("span", { class: "to" }, to.replace(/^ALERT to /, "Office alert: ").replace(/^(SMS|Email) to /, "$1 to ")),
        body, Dom.el("time", {}, time)));
    }
  }
}

class App {
  #api; #meta; #portals; #main; #rail; #current = "customer";

  async start() {
    const store = new DocumentStore();
    this.#api = new PythonBridge(store);
    const main = document.querySelector("main");
    const status = document.querySelector("#load-status");
    try {
      await this.#api.start((text) => { status.textContent = text; });
    } catch (error) {
      Dom.replace(main, Dom.notice(`The system could not start: ${error.message}`));
      return;
    }
    const feed = new MessageFeed(document.querySelector(".outbox"));
    this.#api.onNotices((lines) => feed.add(lines));
    this.#meta = this.#api.call("meta");
    document.querySelector(".sub").textContent = this.#meta.heading;
    this.#tick();
    setInterval(() => this.#tick(), 30000);
    this.#main = main;
    this.#portals = {
      customer: new CustomerPortal(this.#api, this.#meta),
      office: new OfficePortal(this.#api, this.#meta),
      driver: new DriverPortal(this.#api, this.#meta),
      track: new TrackPortal(this.#api),
    };
    this.#rail = document.querySelector(".rail");
    for (const button of this.#rail.querySelectorAll("button[data-portal]")) {
      button.addEventListener("click", () => this.show(button.dataset.portal));
    }
    this.#rail.querySelector(".reset").addEventListener("click", () => {
      if (!confirm("Start again with the sample data? Everything you entered in this browser is removed.")) return;
      store.clear();
      this.#api.call("reset_demo");
      this.show(this.#current);
    });
    this.show(location.hash.slice(1) in this.#portals ? location.hash.slice(1) : "customer");
  }

  show(name) {
    this.#current = name;
    history.replaceState(null, "", `#${name}`);
    for (const button of this.#rail.querySelectorAll("button[data-portal]")) {
      if (button.dataset.portal === name) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
    try { this.#portals[name].render(this.#main); }
    catch (error) { Dom.replace(this.#main, Dom.notice(error.message)); }
    this.#main.focus({ preventScroll: true });
  }

  #tick() {
    try { document.querySelector(".clock").textContent = this.#api.call("meta").now; }
    catch { /* clock is cosmetic */ }
  }
}

new App().start();
