// The delivery request form (Task 1), used by customers and by office
// staff for walk-in or phone customers. Each part is checked by the
// Python domain as soon as it is filled in.
import { Dom } from "./dom.js";
import { Cards } from "./cards.js";

export class RequestForm {
  #api; #meta; #customer; #asOffice; #onDone;
  #parcels = [];
  #editing = -1;
  #node; #parcelList; #parcelBox; #result;

  constructor(api, meta, customer, { asOffice = false, onDone = () => {} } = {}) {
    this.#api = api;
    this.#meta = meta;
    this.#customer = customer;
    this.#asOffice = asOffice;
    this.#onDone = onDone;
  }

  render() {
    const saved = this.#customer.addresses;
    const recipients = this.#customer.recipients;
    this.#parcelList = Dom.el("div");
    this.#parcelBox = Dom.el("div");
    this.#result = Dom.el("div", { "aria-live": "polite" });
    const suburbs = Dom.el("datalist", { id: "suburb-list" },
      this.#meta.suburbs.map(([name]) => Dom.el("option", { value: name })));
    this.#node = Dom.el("form", { class: "panel", novalidate: true, onSubmit: (e) => { e.preventDefault(); this.#submit(); } },
      suburbs,
      Dom.el("h2", {}, this.#asOffice ? `New request for ${this.#customer.contact.name}` : "Send a delivery"),
      this.#addressSet("pickup", "Pickup address", saved),
      this.#addressSet("dropoff", "Drop-off address", []),
      this.#recipientSet(recipients),
      Dom.el("fieldset", {}, Dom.el("legend", {}, "Parcels"),
        Dom.el("p", { class: "small muted" }, "Up to 10 parcels, 30 kg each. Dangerous goods, animals, firearms and refrigerated food can't be carried."),
        this.#parcelList, this.#parcelBox),
      this.#dateSet(),
      Dom.el("div", { class: "row" },
        Dom.el("button", { type: "submit", class: "btn" }, "Get a quote"),
        Dom.button("Discard", () => this.#onDone(null), "btn quiet")),
      this.#result);
    this.#showParcels();
    this.#showParcelEditor();
    return this.#node;
  }

  // ------------------------------------------------------------ parts
  #addressSet(prefix, legend, saved) {
    const street = Dom.field("Street number and name", `${prefix}_street`, { autocomplete: "address-line1", required: true });
    const suburb = Dom.field("Suburb", `${prefix}_suburb`, { list: "suburb-list", required: true });
    const postcode = Dom.field("Postcode", `${prefix}_postcode`, { inputmode: "numeric", maxlength: 4, required: true, "data-width": "narrow" });
    const notes = Dom.field("Delivery instructions", `${prefix}_instructions`, { maxlength: 120 }, true);
    const message = Dom.el("div", { class: "fieldmsg", "aria-live": "polite" });
    const fill = (a) => { street.input.value = a.street; suburb.input.value = a.suburb; postcode.input.value = a.postcode; notes.input.value = a.instructions || ""; };
    suburb.input.addEventListener("change", () => {
      const hit = this.#meta.suburbs.find(([name]) => name.toLowerCase() === suburb.input.value.trim().toLowerCase());
      if (hit && !postcode.input.value) postcode.input.value = hit[1];
    });
    const check = () => this.#check("check_address", this.#address(prefix), message);
    for (const f of [street, suburb, postcode]) f.input.addEventListener("blur", () => { if (street.input.value && suburb.input.value && postcode.input.value) check(); });
    const picker = saved.length ? Dom.select("Saved address", `${prefix}_saved`,
      [["", "Enter a new address"], ...saved.map((a, i) => [String(i), a.line])]) : null;
    if (picker) picker.input.addEventListener("change", () => { const a = saved[Number(picker.input.value)]; if (a) { fill(a); message.textContent = ""; } });
    return Dom.el("fieldset", {}, Dom.el("legend", {}, legend), picker ? picker.wrap : null,
      street.wrap, Dom.el("div", { class: "row" }, suburb.wrap, postcode.wrap), notes.wrap, message);
  }

  #recipientSet(saved) {
    const name = Dom.field("Recipient name", "recipient_name", { autocomplete: "off", required: true });
    const phone = Dom.field("Recipient mobile", "recipient_phone", { inputmode: "tel", placeholder: "04xx xxx xxx", required: true });
    const email = Dom.field("Recipient email", "recipient_email", { type: "email" }, true);
    const message = Dom.el("div", { class: "fieldmsg", "aria-live": "polite" });
    phone.input.addEventListener("blur", () => { if (name.input.value && phone.input.value) this.#check("check_recipient", this.#recipient(), message); });
    const picker = saved.length ? Dom.select("Saved recipient", "recipient_saved",
      [["", "Enter a new recipient"], ...saved.map((r, i) => [String(i), `${r.name} ${r.phone}`])]) : null;
    if (picker) picker.input.addEventListener("change", () => {
      const r = saved[Number(picker.input.value)];
      if (r) { name.input.value = r.name; phone.input.value = r.phone; email.input.value = r.email || ""; message.textContent = ""; }
    });
    return Dom.el("fieldset", {}, Dom.el("legend", {}, "Recipient"), picker ? picker.wrap : null,
      Dom.el("div", { class: "row" }, name.wrap, phone.wrap), email.wrap, message);
  }

  #dateSet() {
    const date = Dom.field("Preferred pickup date", "date", { type: "date", value: this.#meta.today, min: this.#meta.today });
    const message = Dom.el("div", { class: "fieldmsg", "aria-live": "polite" });
    date.input.addEventListener("change", () => this.#check("check_date", { date: date.input.value }, message));
    return Dom.el("fieldset", {}, Dom.el("legend", {}, "When"), date.wrap, message);
  }

  #showParcels() {
    if (!this.#parcels.length) {
      Dom.replace(this.#parcelList, Dom.el("p", { class: "muted" }, "No parcels yet. Add the first one below."));
      return;
    }
    Dom.replace(this.#parcelList, Dom.table(["", "Parcel", "Size band", ""],
      this.#parcels.map((p, i) => [String(i + 1), p.view.summary, p.view.band,
        Dom.el("span", { class: "row" },
          Dom.button("Edit", () => { this.#editing = i; this.#showParcelEditor(); }, "btn quiet small"),
          Dom.button("Remove", () => { this.#parcels.splice(i, 1); this.#editing = -1; this.#showParcels(); this.#showParcelEditor(); }, "btn danger small"))])));
  }

  #showParcelEditor() {
    if (this.#parcels.length >= 10 && this.#editing < 0) { Dom.clear(this.#parcelBox); return; }
    const current = this.#editing >= 0 ? this.#parcels[this.#editing].raw : {};
    const options = [...this.#meta.categories.map((c) => [c, c]),
      ...this.#meta.refused.map((c) => [c, `${c} (not carried)`])];
    const description = Dom.field("Description", "p_description", { placeholder: "e.g. Box of books", value: current.description || "" });
    const category = Dom.select("Category", "p_category", options);
    if (current.category) category.input.value = current.category;
    const dims = ["length", "width", "height"].map((d) => Dom.field(`${d[0].toUpperCase()}${d.slice(1)} (cm)`, `p_${d}`, { inputmode: "decimal", value: current[d] || "", "data-width": "narrow" }));
    const weight = Dom.field("Weight (kg)", "p_weight", { inputmode: "decimal", value: current.weight || "", "data-width": "narrow" });
    const message = Dom.el("div", { "aria-live": "polite" });
    const save = () => {
      const raw = { description: description.input.value, category: category.input.value,
        length: dims[0].input.value, width: dims[1].input.value, height: dims[2].input.value, weight: weight.input.value };
      try {
        const view = this.#api.call("check_parcel", raw);
        if (this.#editing >= 0) this.#parcels[this.#editing] = { raw, view };
        else this.#parcels.push({ raw, view });
        this.#editing = -1;
        this.#showParcels();
        this.#showParcelEditor();
      } catch (error) { Dom.replace(message, Dom.notice(error.message)); }
    };
    Dom.replace(this.#parcelBox, Dom.el("div", { class: "panel", style: "background:#fff" },
      Dom.el("h3", { style: "margin-top:0" }, this.#editing >= 0 ? `Edit parcel ${this.#editing + 1}` : `Parcel ${this.#parcels.length + 1}`),
      Dom.el("div", { class: "row" }, description.wrap, category.wrap),
      Dom.el("div", { class: "row" }, dims.map((d) => d.wrap), weight.wrap),
      message,
      Dom.el("div", { class: "row" },
        Dom.button(this.#editing >= 0 ? "Save parcel" : "Add parcel", save, "btn quiet"),
        this.#editing >= 0 ? Dom.button("Cancel edit", () => { this.#editing = -1; this.#showParcelEditor(); }, "btn quiet") : null)));
  }

  // ------------------------------------------------------- submitting
  #address(prefix) {
    const v = Dom.values(this.#node);
    return { street: v[`${prefix}_street`], suburb: v[`${prefix}_suburb`],
      postcode: v[`${prefix}_postcode`], instructions: v[`${prefix}_instructions`] };
  }

  #recipient() {
    const v = Dom.values(this.#node);
    return { name: v.recipient_name, phone: v.recipient_phone, email: v.recipient_email };
  }

  #check(command, payload, target) {
    try { this.#api.call(command, payload); target.textContent = ""; return true; }
    catch (error) { target.textContent = error.message; return false; }
  }

  #submit() {
    Dom.clear(this.#result);
    if (!this.#parcels.length) { Dom.append(this.#result, [Dom.notice("Add at least one parcel before asking for a quote.")]); return; }
    const payload = { pickup: this.#address("pickup"), dropoff: this.#address("dropoff"),
      recipient: this.#recipient(), parcels: this.#parcels.map((p) => p.raw),
      date: Dom.values(this.#node).date, as_office: this.#asOffice };
    try {
      const request = this.#api.call("submit_request", payload);
      Dom.replace(this.#node, this.#outcome(request));
    } catch (error) {
      Dom.append(this.#result, [Dom.notice(error.message)]);
    }
  }

  #outcome(request) {
    if (!request.quote) {
      return Dom.el("div", {},
        Dom.el("h2", {}, `Request ${request.id} needs a check`),
        request.flags.map((f) => Dom.notice(f)),
        Dom.el("p", {}, "Office staff will check the address and send a price. Nothing has been charged."),
        Dom.button("Done", () => this.#onDone(request)));
    }
    if (this.#asOffice) {
      return Dom.el("div", {}, Dom.el("h2", {}, `Quote ${request.quote.id} sent to ${request.customer}`),
        Cards.quote(request.quote),
        Dom.el("p", {}, "The customer accepts or declines from their own account."),
        Dom.button("Done", () => this.#onDone(request)));
    }
    return QuoteDecision.render(this.#api, request, this.#onDone);
  }
}

/** Accept / decline / later for one quote (Task 3). */
export class QuoteDecision {
  static render(api, request, onDone) {
    const out = Dom.el("div", { "aria-live": "polite" });
    const node = Dom.el("div", {},
      Dom.el("h2", {}, `Your quote for ${request.id}`),
      Cards.quote(request.quote),
      Dom.el("div", { class: "row" },
        Dom.button("Accept quote", () => answer(true)),
        Dom.button("Decline", () => answer(false), "btn danger"),
        Dom.button("Decide later", () => onDone(request), "btn quiet")),
      out);
    const answer = (accept) => {
      try {
        const updated = api.call("respond_quote", { request: request.id, accept });
        if (accept) {
          Dom.replace(node, Dom.el("h2", {}, "Booked"),
            Cards.label(updated.tracking, [`To ${updated.dropoff.line}`, `Pickup ${updated.quote.pickup}`], updated.pin),
            Dom.el("p", { style: "margin-top:1rem" }, `Give the PIN to ${updated.recipient.name}; the driver asks for it at the door. We'll message you when a driver is booked.`),
            Dom.button("Done", () => onDone(updated)));
        } else {
          Dom.replace(node, Dom.notice(`Quote declined. Request ${updated.id} is closed.`, "ok"),
            Dom.button("Done", () => onDone(updated)));
        }
      } catch (error) { Dom.replace(out, Dom.notice(error.message)); }
    };
    return node;
  }
}
