// Driver portal, laid out as the phone screen drivers use (Tasks 4-7).
// The status-bar switch simulates losing signal: work recorded while
// offline is queued on the "phone" and uploaded when signal returns.
import { Dom, Tabs } from "./dom.js";

const FAIL_REASONS = ["Nobody at the address", "Address could not be found",
  "Recipient refused the parcels", "Access blocked"];

export class DriverPortal {
  #api; #meta; #root; #tab = "jobs"; #open = null; #flash = null;

  constructor(api, meta) { this.#api = api; this.#meta = meta; }

  render(root) {
    this.#root = root;
    if (this.#api.call("session").driver) this.#home(); else this.#signIn();
  }

  #signIn() {
    const out = Dom.el("div", { "aria-live": "polite" });
    const id = Dom.field("Staff ID", "staff_id", { placeholder: "D001", autocomplete: "username" });
    Dom.replace(this.#root, Dom.el("div", { class: "phone" },
      Dom.el("div", { class: "statusbar" }, Dom.el("span", { class: "who" }, "YOWD Driver")),
      Dom.el("form", { class: "screen", onSubmit: (e) => { e.preventDefault();
        try { this.#api.call("driver_sign_in", { staff_id: id.input.value }); this.#home(); }
        catch (error) { Dom.replace(out, Dom.notice(error.message)); } } },
        Dom.el("h2", {}, "Sign in"), id.wrap, out,
        Dom.el("button", { type: "submit", class: "btn" }, "Sign in"),
        Dom.el("p", { class: "small muted", style: "margin-top:0.75rem" }, "Demo drivers: D001, D002, D003"))));
  }

  #home() {
    const home = this.#api.call("driver_home");
    const toggle = Dom.el("input", { type: "checkbox", role: "switch", "aria-label": "Mobile signal", checked: home.online,
      onChange: () => this.#setOnline(toggle.checked) });
    const body = Dom.el("div");
    const offered = home.jobs.filter((j) => j.job_status === "Offered").length;
    Dom.replace(this.#root, Dom.el("div", { class: "phone" },
      Dom.el("div", { class: "statusbar" },
        Dom.el("span", { class: "who" }, `${home.driver.id} ${home.driver.name}`),
        Dom.el("label", { class: "switch", style: "margin:0;color:#fff;font-weight:400" }, toggle, home.online ? "Signal" : "No signal")),
      Dom.el("div", { class: "screen" },
        home.pending.length ? Dom.el("div", { class: "notice bad" },
          `${home.pending.length} action(s) waiting to upload.`,
          home.online ? Dom.el("div", { style: "margin-top:0.4rem" }, Dom.button("Upload now", () => this.#sync(), "btn small")) : null) : null,
        this.#flash ? this.#flash : null,
        new Tabs([["jobs", "Jobs", offered], ["availability", "Availability"]], this.#tab,
          (key) => { this.#tab = key; this.#flash = null; this.#home(); }).node,
        body,
        Dom.el("p", { style: "margin-top:1rem" }, Dom.button("Sign out", () => {
          this.#api.call("sign_out", { portal: "driver" }); this.#open = null; this.#signIn(); }, "btn quiet small")))));
    if (this.#tab === "availability") this.#availability(body, home); else this.#jobs(body, home);
    this.#flash = null;
  }

  #say(text, kind = "ok") { this.#flash = Dom.notice(text, kind); this.#home(); }

  #setOnline(online) {
    try {
      const result = this.#api.call("set_online", { online });
      if (online && result.uploaded.length) this.#flash = this.#uploadReport(result.uploaded);
      else this.#flash = Dom.notice(online ? "Signal is back." : "No signal: work is saved on this phone until signal returns.", "ok");
    } catch (error) { this.#flash = Dom.notice(error.message); }
    this.#home();
  }

  #sync() {
    try { this.#flash = this.#uploadReport(this.#api.call("sync").uploaded); }
    catch (error) { this.#flash = Dom.notice(error.message); }
    this.#home();
  }

  #uploadReport(results) {
    return Dom.el("div", {}, Dom.el("p", { class: "small" }, "Uploaded in the order the work happened:"),
      results.map((r) => Dom.notice(`${r.action}: ${r.message}`, r.ok ? "ok" : "bad")));
  }

  // -------------------------------------------------------------- jobs
  #jobs(body, home) {
    if (!home.jobs.length) { Dom.replace(body, Dom.el("p", { class: "muted" }, "No jobs right now. The office will offer you jobs inside your availability.")); return; }
    Dom.replace(body, home.jobs.map((job) => {
      const card = Dom.el("article", { class: "job" },
        Dom.el("header", {}, Dom.el("span", { class: "ref" }, job.ref), Dom.el("span", { class: "status" }, job.status)),
        Dom.el("div", { class: "small" }, `Pickup ${job.window}`),
        Dom.el("div", {}, `From ${job.pickup.line}`),
        job.pickup.instructions ? Dom.el("div", { class: "small muted" }, job.pickup.instructions) : null,
        Dom.el("div", {}, `To ${job.dropoff.line}`),
        Dom.el("div", { class: "small" }, `${job.parcels.length} parcel(s). Collect ${job.owing}.`));
      if (job.job_status === "Offered") {
        card.append(Dom.el("div", { class: "actions" }, Dom.button("Accept job", () => {
          try { this.#api.call("acknowledge", { ref: job.ref }); this.#say(`${job.ref} accepted. The office can see it.`); }
          catch (error) { this.#say(error.message, "bad"); } })));
      } else {
        const panel = Dom.el("div");
        card.append(this.#actionButtons(job, panel), panel);
        if (this.#open && this.#open.ref === job.ref) this.#open.build(panel);
      }
      return card;
    }));
  }

  #actionButtons(job, panel) {
    const show = (builder) => { this.#open = { ref: job.ref, build: builder }; builder(panel); };
    return Dom.el("div", { class: "actions" },
      Dom.button("Arrived", () => this.#record(job, "ARRIVED_PICKUP"), "btn quiet"),
      Dom.button("Collect", () => show((p) => this.#collectForm(job, p)), "btn quiet"),
      Dom.button("Leave for drop-off", () => this.#record(job, "DEPART"), "btn quiet"),
      Dom.button("Deliver", () => show((p) => this.#deliverForm(job, p)), "btn quiet"),
      Dom.button("Failed attempt", () => show((p) => this.#failedForm(job, p)), "btn danger"));
  }

  #record(job, kind, data = {}, target = null) {
    try {
      const result = this.#api.call("field", { ref: job.ref, kind, data });
      this.#open = null;
      this.#say(result.message, "ok");
    } catch (error) {
      if (target) Dom.replace(target, Dom.notice(error.message)); else this.#say(error.message, "bad");
    }
  }

  #collectForm(job, panel) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const boxes = job.parcels.map((p, i) => Dom.el("label", { class: "check" },
      Dom.el("input", { type: "checkbox", name: `parcel${i}` }), `${i + 1}. ${p.description} (${p.band})`));
    const owing = Number(job.owing_value) > 0;
    const method = Dom.select("Payment", "method", [["Cash", "Cash"], ["Card", "Card (needs signal)"]]);
    const last4 = Dom.field("Last 4 digits on the card terminal", "last4", { inputmode: "numeric", maxlength: 4 });
    last4.wrap.hidden = true;
    method.input.addEventListener("change", () => { last4.wrap.hidden = method.input.value !== "Card"; });
    Dom.replace(panel, Dom.el("form", { class: "panel", style: "margin-top:0.75rem", onSubmit: (e) => {
      e.preventDefault();
      const collected = panel.querySelectorAll("input[type=checkbox]:checked").length;
      if (collected !== job.parcels.length) {
        Dom.replace(out, Dom.notice(`${collected} of ${job.parcels.length} parcels checked off. Collect every parcel, or record a failed attempt and call the office.`));
        return;
      }
      this.#record(job, "PICKUP_AND_PAYMENT", { collected, method: method.input.value, card_last_four: last4.input.value }, out);
    } },
      Dom.el("h3", { style: "margin-top:0" }, "Check off every parcel"), boxes,
      owing ? [Dom.el("p", { style: "margin:0.75rem 0 0.25rem" }, `Collect ${job.owing}`), method.wrap, last4.wrap] : Dom.el("p", {}, "Nothing to collect."),
      out, Dom.el("button", { type: "submit", class: "btn" }, "Confirm pickup")));
  }

  #deliverForm(job, panel) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const receiver = Dom.field("Name of the person taking the parcels", "receiver", { value: job.recipient.name });
    const pin = Dom.field("Handover PIN from the recipient", "pin", { inputmode: "numeric", maxlength: 4 });
    const photo = Dom.field("Photo file name", "photo", { placeholder: `pod_${job.ref}.jpg` }, true);
    Dom.replace(panel, Dom.el("form", { class: "panel", style: "margin-top:0.75rem", onSubmit: (e) => { e.preventDefault();
      this.#record(job, "DELIVER", { receiver_name: receiver.input.value, pin: pin.input.value, photo: photo.input.value }, out); } },
      Dom.el("h3", { style: "margin-top:0" }, `Hand over to ${job.recipient.name}`), receiver.wrap, pin.wrap, photo.wrap, out,
      Dom.el("button", { type: "submit", class: "btn" }, "Complete delivery")));
  }

  #failedForm(job, panel) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const reason = Dom.select("What happened", "reason", FAIL_REASONS.map((r) => [r, r]));
    Dom.replace(panel, Dom.el("form", { class: "panel", style: "margin-top:0.75rem", onSubmit: (e) => { e.preventDefault();
      this.#record(job, "FAILED_ATTEMPT", { reason: reason.input.value }, out); } },
      reason.wrap, out, Dom.el("button", { type: "submit", class: "btn danger" }, "Record failed attempt")));
  }

  // ------------------------------------------------------ availability
  #availability(body, home) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const editor = Dom.el("div");
    const rows = home.periods.map((p) => [p.label, Dom.el("span", { class: "row" },
      p.weekly ? null : Dom.button("Change", () => this.#periodForm(editor, out, p), "btn quiet small"),
      Dom.button("Withdraw", () => {
        if (!confirm(`Withdraw ${p.label}? Jobs inside it go back to the office.`)) return;
        try { const r = this.#api.call("withdraw", { period: p.id }); this.#say(`Withdrawn ${r.label}.`); }
        catch (error) { Dom.replace(out, Dom.notice(error.message)); } }, "btn danger small"))]);
    Dom.replace(body, out,
      rows.length ? Dom.table(["When I can work", ""], rows) : Dom.el("p", { class: "muted" }, "You haven't added any availability."),
      editor);
    this.#periodForm(editor, out, null);
  }

  #periodForm(editor, out, period) {
    const day = Dom.field("Day", "day", { type: "date", min: this.#meta.today, value: period ? period.day : this.#meta.today });
    const start = Dom.field("From", "start", { type: "time", value: period ? period.start : "08:00", "data-width": "narrow" });
    const end = Dom.field("Until", "end", { type: "time", value: period ? period.end : "16:00", "data-width": "narrow" });
    const weekly = Dom.el("label", { class: "check" }, Dom.el("input", { type: "checkbox", name: "weekly" }), "Repeat every week");
    Dom.replace(editor, Dom.el("form", { class: "panel", style: "margin-top:1rem", onSubmit: (e) => { e.preventDefault();
      const payload = { day: day.input.value, start: start.input.value, end: end.input.value, weekly: weekly.querySelector("input").checked };
      try {
        const r = period ? this.#api.call("change_period", { ...payload, period: period.id }) : this.#api.call("declare", payload);
        this.#say(`${period ? "Changed to" : "Saved"} ${r.label}. The office can see it now.`);
      } catch (error) { Dom.replace(out, Dom.notice(error.message)); } } },
      Dom.el("h3", { style: "margin-top:0" }, period ? `Change ${period.label}` : "Add availability"),
      day.wrap, Dom.el("div", { class: "row" }, start.wrap, end.wrap), period ? null : weekly,
      Dom.el("div", { class: "row", style: "margin-top:0.75rem" },
        Dom.el("button", { type: "submit", class: "btn" }, period ? "Save change" : "Add"),
        period ? Dom.button("Cancel", () => this.#periodForm(editor, out, null), "btn quiet") : null)));
  }
}
