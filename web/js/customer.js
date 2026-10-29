// Customer portal: sign in or register, send deliveries, answer quotes.
import { Dom, Tabs } from "./dom.js";
import { Cards } from "./cards.js";
import { RequestForm, QuoteDecision } from "./request-form.js";

export class CustomerPortal {
  #api; #meta; #root; #tab = "deliveries";

  constructor(api, meta) { this.#api = api; this.#meta = meta; }

  render(root) {
    this.#root = root;
    const session = this.#api.call("session");
    if (session.customer) this.#home(); else this.#signIn();
  }

  #signIn() {
    const out = Dom.el("div", { "aria-live": "polite" });
    const key = Dom.field("Email or mobile", "key", { autocomplete: "username", placeholder: "sarah.chen@example.com" });
    const name = Dom.field("Full name or business name", "name", { autocomplete: "name" });
    const phone = Dom.field("Mobile", "phone", { inputmode: "tel", placeholder: "04xx xxx xxx" });
    const email = Dom.field("Email", "email", { type: "email", autocomplete: "email" });
    const channel = Dom.select("Send me updates by", "channel", [["SMS", "SMS"], ["Email", "Email"]]);
    const run = (command, payload) => {
      try { this.#api.call(command, payload); this.#home(); }
      catch (error) { Dom.replace(out, Dom.notice(error.message)); }
    };
    Dom.replace(this.#root,
      Dom.el("h2", {}, "Customer portal"),
      Dom.el("p", { class: "muted" }, "Send parcels across Greater Melbourne, see your quotes and follow your deliveries."),
      out,
      Dom.el("div", { class: "split" },
        Dom.el("form", { class: "panel", onSubmit: (e) => { e.preventDefault(); run("customer_sign_in", { key: key.input.value }); } },
          Dom.el("h3", { style: "margin-top:0" }, "I've used YOWD before"), key.wrap,
          Dom.el("button", { type: "submit", class: "btn" }, "Sign in"),
          Dom.el("p", { class: "small muted", style: "margin-top:0.75rem" }, "Demo customer: sarah.chen@example.com")),
        Dom.el("form", { class: "panel", onSubmit: (e) => { e.preventDefault(); run("customer_register",
          { name: name.input.value, phone: phone.input.value, email: email.input.value, channel: channel.input.value }); } },
          Dom.el("h3", { style: "margin-top:0" }, "I'm new here"), name.wrap,
          Dom.el("div", { class: "row" }, phone.wrap, channel.wrap), email.wrap,
          Dom.el("button", { type: "submit", class: "btn" }, "Create my account"))));
  }

  #home() {
    const home = this.#api.call("customer_home");
    const awaiting = home.requests.filter((r) => r.awaiting);
    const body = Dom.el("div");
    const tabs = new Tabs([["deliveries", "My deliveries"], ["quotes", "Quotes to answer", awaiting.length],
      ["new", "Send a delivery"]], this.#tab, (key) => { this.#tab = key; this.#show(key, body, home); });
    Dom.replace(this.#root,
      Dom.el("div", { class: "row between" },
        Dom.el("h2", {}, home.customer.contact.name),
        Dom.button("Sign out", () => { this.#api.call("sign_out", { portal: "customer" }); this.#tab = "deliveries"; this.#signIn(); }, "btn quiet small")),
      tabs.node, body);
    this.#show(this.#tab, body, home);
  }

  #show(key, body, home) {
    if (key === "new") {
      Dom.replace(body, new RequestForm(this.#api, this.#meta, home.customer,
        { onDone: () => { this.#tab = "deliveries"; this.#home(); } }).render());
    } else if (key === "quotes") {
      const awaiting = home.requests.filter((r) => r.awaiting);
      Dom.replace(body, awaiting.length
        ? awaiting.map((r) => Dom.el("div", { class: "panel" },
            QuoteDecision.render(this.#api, r, () => this.#home())))
        : Dom.el("p", { class: "muted" }, "No quotes are waiting for you. Send a delivery to get one."));
    } else {
      Dom.replace(body, home.requests.length
        ? Dom.table(["Request", "Logged", "To", "Status", "Tracking", "Delivery"],
            home.requests.map((r) => [r.id, r.created, r.dropoff.suburb,
              r.status + (r.flags.length && r.status === "Requested" ? " (checking address)" : ""),
              r.tracking ? Dom.button(r.tracking, () => this.#track(body, r.tracking), "btn quiet small") : "",
              r.delivery_status]))
        : Dom.el("p", { class: "muted" }, "You haven't sent anything yet. Use “Send a delivery” to get a quote."));
    }
  }

  #track(body, ref) {
    Dom.replace(body, Dom.button("Back to my deliveries", () => this.#home(), "btn quiet small"),
      Dom.el("div", { style: "margin-top:1rem" }, Cards.delivery(this.#api.call("track", { ref }))));
  }
}
