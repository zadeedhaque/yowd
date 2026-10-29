// Office staff portal (dispatch) and owner tools.
import { Dom, Tabs } from "./dom.js";
import { Cards } from "./cards.js";
import { RequestForm } from "./request-form.js";

export class OfficePortal {
  #api; #meta; #root; #tab = "allocate"; #body; #flash = null;

  constructor(api, meta) { this.#api = api; this.#meta = meta; }

  render(root) {
    this.#root = root;
    if (this.#api.call("session").officer) this.#home(); else this.#signIn();
  }

  #signIn() {
    const out = Dom.el("div", { "aria-live": "polite" });
    const id = Dom.field("Staff ID", "staff_id", { placeholder: "S002", autocomplete: "username" });
    Dom.replace(this.#root, Dom.el("h2", {}, "Office staff portal"),
      Dom.el("p", { class: "muted" }, "Review requests, allocate drivers, reconcile cash. Owners also see statistics and staff."),
      Dom.el("form", { class: "panel", style: "max-width:24rem", onSubmit: (e) => {
        e.preventDefault();
        try { this.#api.call("office_sign_in", { staff_id: id.input.value }); this.#home(); }
        catch (error) { Dom.replace(out, Dom.notice(error.message)); } } },
        id.wrap, out, Dom.el("button", { type: "submit", class: "btn" }, "Sign in"),
        Dom.el("p", { class: "small muted", style: "margin-top:0.75rem" }, "Demo: S002 (office) or S001 (owner)")));
  }

  #home() {
    const session = this.#api.call("session");
    const home = this.#api.call("office_home");
    const items = [["allocate", "Allocate", home.unallocated.length], ["review", "Review", home.review.length],
      ["walkin", "Walk-in request"], ["quotes", "Open quotes", home.open_quotes.length],
      ["cash", "Cash", home.cash.length], ["track", "Track"]];
    if (home.owner) items.push(["stats", "Statistics"], ["staff", "Staff"]);
    this.#body = Dom.el("div");
    Dom.replace(this.#root,
      Dom.el("div", { class: "row between" },
        Dom.el("h2", {}, `${session.officer} (${home.owner ? "owner" : "office"})`),
        Dom.button("Sign out", () => { this.#api.call("sign_out", { portal: "office" }); this.#tab = "allocate"; this.#signIn(); }, "btn quiet small")),
      new Tabs(items, this.#tab, (key) => { this.#tab = key; this.#flash = null; this.#home(); }).node,
      this.#flash ? Dom.notice(this.#flash, "ok") : null,
      this.#body);
    const views = { allocate: () => this.#allocate(home), review: () => this.#review(home),
      walkin: () => this.#walkIn(), quotes: () => this.#quotes(home), cash: () => this.#cash(home),
      track: () => this.#trackForm(), stats: () => this.#stats(home), staff: () => this.#staff(home) };
    (views[this.#tab] || views.allocate)();
  }

  #done(message) { this.#flash = message; this.#home(); }

  #try(target, work) {
    try { work(); } catch (error) { Dom.replace(target, Dom.notice(error.message)); }
  }

  // ---------------------------------------------------------- allocate
  #allocate(home) {
    if (!home.unallocated.length) { Dom.replace(this.#body, Dom.el("p", { class: "muted" }, "Every accepted delivery has a driver.")); return; }
    const detail = Dom.el("div", { "aria-live": "polite" });
    Dom.replace(this.#body, Dom.el("p", { class: "muted" }, "Waiting for a driver, earliest pickup first."),
      Dom.table(["Tracking", "Pickup window", "From", "To", "Note", ""],
        home.unallocated.map((d) => {
          const last = d.allocations.at(-1);
          const note = [d.urgent ? "Urgent" : "", last ? `Came back: ${last.reason}` : ""].filter(Boolean).join(". ");
          return [d.ref, d.pickup, d.from, d.to, Dom.el("span", { class: d.urgent ? "urgent" : null }, note),
            Dom.button("Find drivers", () => this.#candidates(d, detail), "btn small")];
        })), detail);
  }

  #candidates(delivery, target) {
    this.#try(target, () => {
      const staff = this.#api.call("candidates", { ref: delivery.ref });
      Dom.replace(target, Dom.el("div", { class: "panel", style: "margin-top:1rem" },
        Dom.el("h3", { style: "margin-top:0" }, `Drivers free for ${delivery.ref} (${delivery.pickup})`),
        staff.length
          ? Dom.table(["Staff", "Name", "Phone", ""], staff.map((s) => [s.id, s.name, s.phone,
              Dom.button("Allocate", () => this.#try(target, () => {
                const result = this.#api.call("allocate", { ref: delivery.ref, staff_id: s.id });
                this.#done(`${delivery.ref} offered to ${result.driver}; waiting for them to accept.`);
              }), "btn small")]))
          : Dom.notice("No driver is free then. Ask a driver to add availability, or contact the customer to move the pickup.")));
    });
  }

  // ------------------------------------------------------------ review
  #review(home) {
    if (!home.review.length) { Dom.replace(this.#body, Dom.el("p", { class: "muted" }, "No requests need checking.")); return; }
    Dom.replace(this.#body, home.review.map((r) => {
      const out = Dom.el("div", { "aria-live": "polite" });
      const amount = Dom.field("Price incl. GST ($)", "amount", { inputmode: "decimal", "data-width": "narrow" });
      const reason = Dom.field("Reason", "reason", { placeholder: "e.g. Approved regional run" });
      return Dom.el("div", { class: "panel" },
        Dom.el("h3", { style: "margin-top:0" }, `${r.id} for ${r.customer}`),
        r.flags.map((f) => Dom.notice(f)),
        Dom.el("p", {}, `${r.pickup.line} to ${r.dropoff.line}. ${r.parcels.length} parcel(s).`),
        Dom.el("div", { class: "row" }, amount.wrap, reason.wrap),
        out,
        Dom.el("div", { class: "row" },
          Dom.button("Send this price", () => this.#try(out, () => {
            const q = this.#api.call("manual_quote", { request: r.id, amount: amount.input.value, reason: reason.input.value });
            this.#done(`Quote ${q.quote.id} for ${q.quote.amount} sent to ${r.customer}.`);
          })),
          Dom.button("Reject request", () => this.#try(out, () => {
            this.#api.call("reject_request", { request: r.id, reason: reason.input.value });
            this.#done(`${r.id} rejected.`);
          }), "btn danger")));
    }));
  }

  // ----------------------------------------------------------- walk-in
  #walkIn() {
    const out = Dom.el("div", { "aria-live": "polite" });
    const key = Dom.field("Customer mobile or email", "key", { inputmode: "tel" });
    const name = Dom.field("Name (new customers only)", "name");
    Dom.replace(this.#body, Dom.el("form", { class: "panel", onSubmit: (e) => {
      e.preventDefault();
      this.#try(out, () => {
        const customer = this.#api.call("walk_in", { key: key.input.value, name: name.input.value });
        Dom.replace(this.#body, new RequestForm(this.#api, this.#meta, customer,
          { asOffice: true, onDone: (r) => this.#done(r ? `Request ${r.id} logged.` : "Request discarded.") }).render());
      }); } },
      Dom.el("p", { class: "muted" }, "Find the caller, or create a guest customer if they're new."),
      Dom.el("div", { class: "row" }, key.wrap, name.wrap), out,
      Dom.el("button", { type: "submit", class: "btn" }, "Continue")));
  }

  // ------------------------------------------------------------ quotes
  #quotes(home) {
    if (!home.open_quotes.length) { Dom.replace(this.#body, Dom.el("p", { class: "muted" }, "No quotes are waiting for customers.")); return; }
    Dom.replace(this.#body, Dom.el("p", { class: "muted" }, "Change a price before the customer answers. A reason is kept with the quote."),
      home.open_quotes.map((r) => {
        const out = Dom.el("div", { "aria-live": "polite" });
        const amount = Dom.field("New price ($)", "amount", { inputmode: "decimal", value: r.quote.amount.replace("$", ""), "data-width": "narrow" });
        const reason = Dom.field("Reason", "reason");
        return Dom.el("div", { class: "panel" },
          Dom.el("h3", { style: "margin-top:0" }, `${r.id} for ${r.customer}: ${r.quote.amount}, expires ${r.quote.expires}`),
          Dom.el("div", { class: "row" }, amount.wrap, reason.wrap,
            Dom.el("div", { class: "field", style: "flex:0" }, Dom.button("Change price", () => this.#try(out, () => {
              const q = this.#api.call("override_quote", { request: r.id, amount: amount.input.value, reason: reason.input.value });
              this.#done(`${r.id} now ${q.quote.amount}; the customer has been told.`);
            })))), out);
      }));
  }

  // -------------------------------------------------------------- cash
  #cash(home) {
    const out = Dom.el("div", { "aria-live": "polite" });
    Dom.replace(this.#body, home.cash.length
      ? [Dom.el("p", { class: "muted" }, "Cash collected by drivers and not yet handed in."), out,
         Dom.table(["Driver", "Payments", "Total", ""], home.cash.map((c) => [`${c.staff.id} ${c.staff.name}`,
           String(c.count), c.total, Dom.button("Mark handed in", () => this.#try(out, () => {
             const r = this.#api.call("reconcile", { staff_id: c.staff.id });
             this.#done(`Reconciled ${r.count} cash payment(s), ${r.total}.`);
           }), "btn small")]), [1, 2])]
      : Dom.el("p", { class: "muted" }, "No driver is holding cash."));
  }

  // ------------------------------------------------------------- track
  #trackForm() {
    const out = Dom.el("div", { "aria-live": "polite" });
    const ref = Dom.field("Tracking reference", "ref", { placeholder: "YW10001" });
    Dom.replace(this.#body, Dom.el("form", { class: "row", onSubmit: (e) => { e.preventDefault();
      this.#try(out, () => Dom.replace(out, Cards.delivery(this.#api.call("track_staff", { ref: ref.input.value })))); } },
      ref.wrap, Dom.el("div", { class: "field", style: "flex:0" }, Dom.el("button", { type: "submit", class: "btn" }, "Show"))), out);
  }

  // ------------------------------------------------------------- owner
  #stats(home) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const kind = Dom.select("Period", "kind", [["day", "Day"], ["week", "Week"], ["month", "Month"], ["year", "Year"], ["ytd", "Year to date"]]);
    kind.input.value = "month";
    const date = Dom.field("Any date in the period", "date", { type: "date", value: this.#meta.today });
    const staff = Dom.select("Scope", "staff", [["", "All deliveries"], ...(home.staff || []).map((s) => [s.id, `${s.id} ${s.name}`])]);
    const run = () => this.#try(out, () => {
      const report = this.#api.call("statistics", { kind: kind.input.value, date: date.input.value, staff_id: staff.input.value });
      Dom.replace(out, Dom.table(["Measure", "Value"], report.rows, [1]),
        Dom.el("p", { style: "margin-top:0.75rem" }, Dom.button("Download CSV", () => {
          const link = Dom.el("a", { href: URL.createObjectURL(new Blob([report.csv], { type: "text/csv" })), download: report.file });
          link.click(); URL.revokeObjectURL(link.href);
        }, "btn quiet")));
    });
    Dom.replace(this.#body, Dom.el("form", { class: "row", onSubmit: (e) => { e.preventDefault(); run(); } },
      kind.wrap, date.wrap, staff.wrap, Dom.el("div", { class: "field", style: "flex:0" }, Dom.el("button", { type: "submit", class: "btn" }, "Show"))), out);
    run();
  }

  #staff(home) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const name = Dom.field("Name", "name");
    const phone = Dom.field("Mobile", "phone", { inputmode: "tel" });
    const email = Dom.field("Email", "email", { type: "email" }, true);
    Dom.replace(this.#body, out,
      Dom.table(["Staff", "Name", "Phone", "Status", "Open jobs", ""], home.staff.map((s) => [s.id, s.name, s.phone,
        s.active ? "Active" : "Left", String(s.open_jobs),
        s.active ? Dom.button("Mark as left", () => this.#try(out, () => {
          const r = this.#api.call("deactivate_driver", { staff_id: s.id });
          this.#done(`${s.name} marked as left; ${r.released} job(s) returned for reallocation. History is kept.`);
        }), "btn danger small") : ""]), [4]),
      Dom.el("form", { class: "panel", style: "margin-top:1rem", onSubmit: (e) => { e.preventDefault();
        this.#try(out, () => {
          const s = this.#api.call("add_driver", { name: name.input.value, phone: phone.input.value, email: email.input.value });
          this.#done(`Added ${s.id} ${s.name}. They can now add their availability.`);
        }); } },
        Dom.el("h3", { style: "margin-top:0" }, "Add a delivery staff member"),
        Dom.el("div", { class: "row" }, name.wrap, phone.wrap, email.wrap),
        Dom.el("button", { type: "submit", class: "btn" }, "Add driver")));
  }
}
