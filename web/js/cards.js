// Read-only displays shared by several portals.
import { Dom } from "./dom.js";

export class Cards {
  /** The yellow consignment label with tracking reference and PIN. */
  static label(ref, lines, pin) {
    return Dom.el("div", { class: "label-card" },
      Dom.el("div", {},
        Dom.el("div", { class: "ref" }, ref),
        lines.map((line) => Dom.el("div", { class: "meta" }, line))),
      pin ? Dom.el("div", { class: "pin" }, "Handover PIN", Dom.el("strong", {}, pin)) : Dom.el("div"));
  }

  /** Itemised quote with windows, expiry and terms. */
  static quote(quote) {
    const rows = quote.lines.map(([label, amount]) => Dom.el("tr", {},
      Dom.el("td", {}, label), Dom.el("td", {}, amount)));
    return Dom.el("div", { class: "quote" },
      Dom.el("table", {}, Dom.el("tbody", {}, rows,
        Dom.el("tr", { class: "total" }, Dom.el("td", {}, "Total incl. GST"), Dom.el("td", {}, quote.amount)))),
      quote.set_by ? Dom.el("p", { class: "small muted" }, `Price set by office staff: ${quote.reason}`) : null,
      Dom.el("p", { class: "small" },
        `Pickup ${quote.pickup}. Delivery ${quote.delivery}. Valid until ${quote.expires}.`),
      Dom.el("p", { class: "small muted" },
        "Payment is taken at pickup by card or cash. Your details are used only to deliver this order (Privacy Act 1988)."));
  }

  /** Delivery status, proof and history (staff see more). */
  static delivery(view) {
    const facts = [
      ["Status", view.status], ["From", view.from], ["To", view.to],
      ["Recipient", view.recipient], ["Parcels", String(view.parcels)],
      ["Pickup window", view.pickup], ["Delivery window", view.delivery],
    ];
    if (view.driver) facts.push(["Driver", view.driver]);
    if (view.proof && view.proof.receiver_name) {
      facts.push(["Proof", `Received by ${view.proof.receiver_name}` +
        (view.proof.photo ? `, photo ${view.proof.photo}` : "") + ", PIN checked"]);
    }
    const node = Dom.el("div", {},
      Cards.label(view.ref, [view.status, `To ${view.to}`]),
      Dom.el("div", { class: "split", style: "margin-top:1rem" },
        Dom.el("div", {}, Dom.el("h3", {}, "Details"),
          Dom.table(["", ""], facts)),
        Dom.el("div", {}, Dom.el("h3", {}, "History"),
          Dom.el("ol", { class: "timeline" }, view.events.map((e) =>
            Dom.el("li", { class: e.status ? "change" : null },
              Dom.el("time", {}, e.when),
              e.status ? Dom.el("strong", {}, `${e.status}. `) : null, e.note))))));
    if (view.allocations) {
      node.append(Dom.el("h3", {}, "Allocations"),
        Dom.table(["Id", "Driver", "Status", "Offered", "Note"],
          view.allocations.map((a) => [a.id, `${a.staff} ${a.name}`, a.status, a.offered, a.reason])));
      node.append(Dom.el("h3", {}, "Payments"),
        view.payments.length
          ? Dom.table(["Id", "Amount", "Method", "Status"],
              view.payments.map((p) => [p.id, p.amount, p.method, p.status]), [1])
          : Dom.el("p", { class: "muted" }, `Nothing paid yet. Owing ${view.owing}.`));
      for (const p of view.payments) {
        if (p.receipt.length) {
          node.append(Dom.el("pre", { class: "panel small", style: "white-space:pre-wrap" }, p.receipt.join("\n")));
        }
      }
    }
    return node;
  }
}
