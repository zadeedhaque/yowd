"""WebApi: the JSON interface the browser UI calls (through Pyodide).

The page calls ``api.call(command, payload_json)`` and always gets back
JSON: ``{"ok": true, "data": ...}`` or ``{"ok": false, "error": ...}``.
Every command is a method of this class registered in ``__commands``;
an unknown command name is refused, so the page cannot reach anything
else in the system.  WebApi only translates - the work is done by the
DeliveryManagementSystem facade, exactly as for the console.
"""

import json
from typing import Callable

from yowd.app.system import DeliveryManagementSystem
from yowd.app.workspace import MemoryWorkspace
from yowd.domain.errors import AuthorisationError, DmsError
from yowd.domain.ports import Clock
from yowd.domain.statuses import FieldActionKind
from yowd.web.presenter import Presenter


class WebSession:
    """Who is signed in on this browser tab."""

    __slots__ = ("__customer", "__officer", "__driver", "__queue",
                 "__walk_in")

    def __init__(self) -> None:
        self.__customer = None
        self.__officer = None
        self.__driver = None
        self.__queue = None
        self.__walk_in = None

    def sign_in_customer(self, customer) -> None:
        """Customer portal user."""
        self.__customer = customer

    def sign_in_officer(self, officer) -> None:
        """Office portal user."""
        self.__officer = officer
        self.__walk_in = None

    def sign_in_driver(self, driver, queue) -> None:
        """Driver portal user and their device queue."""
        self.__driver, self.__queue = driver, queue

    def choose_walk_in(self, customer) -> None:
        """Customer an office user is logging a request for."""
        self.__walk_in = customer

    def sign_out(self, portal: str) -> None:
        """Forget the user of one portal."""
        if portal == "customer":
            self.__customer = None
        elif portal == "office":
            self.__officer = self.__walk_in = None
        elif portal == "driver":
            self.__driver = self.__queue = None

    def customer(self):
        """Signed-in customer, or AuthorisationError."""
        return self.__need(self.__customer, "customer")

    def officer(self):
        """Signed-in office staff member, or AuthorisationError."""
        return self.__need(self.__officer, "office staff member")

    def driver(self):
        """Signed-in driver, or AuthorisationError."""
        return self.__need(self.__driver, "delivery staff member")

    def queue(self):
        """The signed-in driver's device queue."""
        self.driver()
        return self.__queue

    def walk_in(self):
        """Walk-in customer chosen by the office user."""
        return self.__need(self.__walk_in, "walk-in customer (find or "
                                           "create one first)")

    def summary(self) -> dict:
        """Who is signed in, for the page header."""
        def name(person):
            return person.contact.name if person else ""
        return {"customer": name(self.__customer),
                "customer_id": (self.__customer.customer_id
                                if self.__customer else ""),
                "officer": name(self.__officer),
                "officer_id": (self.__officer.staff_id
                               if self.__officer else ""),
                "owner": bool(self.__officer and self.__officer.is_owner),
                "driver": name(self.__driver),
                "driver_id": (self.__driver.staff_id
                              if self.__driver else "")}

    @staticmethod
    def __need(user, label: str):
        if user is None:
            raise AuthorisationError(f"Please sign in as a {label} first.")
        return user


class WebApi:
    """Command dispatcher between the browser and the facade."""

    __slots__ = ("__workspace", "__system", "__session", "__commands",
                 "__clock")

    def __init__(self, config_text: str, documents_json: str = "{}",
                 clock: Clock | None = None) -> None:
        self.__workspace = MemoryWorkspace(config_text)
        for name, text in json.loads(documents_json or "{}").items():
            if name != "config.json":
                self.__workspace.document(name).write(text)
        self.__clock = clock
        self.__system = DeliveryManagementSystem(self.__workspace, clock)
        self.__session = WebSession()
        self.__commands: dict[str, Callable[[dict], object]] = {
            "meta": self.__meta,
            "session": self.__session_summary,
            "notifications": self.__notifications,
            "reset_demo": self.__reset_demo,
            "track": self.__track,
            # customer portal
            "customer_sign_in": self.__customer_sign_in,
            "customer_register": self.__customer_register,
            "sign_out": self.__sign_out,
            "customer_home": self.__customer_home,
            "check_address": self.__check_address,
            "check_recipient": self.__check_recipient,
            "check_parcel": self.__check_parcel,
            "check_date": self.__check_date,
            "submit_request": self.__submit_request,
            "respond_quote": self.__respond_quote,
            # office portal
            "office_sign_in": self.__office_sign_in,
            "office_home": self.__office_home,
            "walk_in": self.__walk_in,
            "manual_quote": self.__manual_quote,
            "reject_request": self.__reject_request,
            "override_quote": self.__override_quote,
            "candidates": self.__candidates,
            "allocate": self.__allocate,
            "reconcile": self.__reconcile,
            "track_staff": self.__track_staff,
            "statistics": self.__statistics,
            "add_driver": self.__add_driver,
            "deactivate_driver": self.__deactivate_driver,
            # driver portal
            "driver_sign_in": self.__driver_sign_in,
            "driver_home": self.__driver_home,
            "declare": self.__declare,
            "change_period": self.__change_period,
            "withdraw": self.__withdraw,
            "acknowledge": self.__acknowledge,
            "set_online": self.__set_online,
            "field": self.__field,
            "sync": self.__sync,
        }

    # ================================================================ API
    def call(self, command: str, payload_json: str = "{}") -> str:
        """Run one command; always return a JSON envelope."""
        handler = self.__commands.get(command)
        if handler is None:
            return json.dumps({"ok": False,
                               "error": f"Unknown command '{command}'."})
        try:
            payload = json.loads(payload_json or "{}")
            data = handler(payload)
            return json.dumps({"ok": True, "data": data,
                               "notices": self.__system
                               .recent_notifications()})
        except DmsError as error:
            return json.dumps({"ok": False, "error": str(error),
                               "kind": type(error).__name__,
                               "notices": self.__system
                               .recent_notifications()})

    def commands(self) -> list[str]:
        """Names of every command the page may call."""
        return sorted(self.__commands)

    def documents(self) -> str:
        """Stored documents as JSON for the page to keep.

        The settings come from the site itself and the message log is
        shown live, so neither is kept in browser storage.
        """
        return json.dumps({name: self.__workspace.document(name).read()
                           for name in self.__workspace.names()
                           if name not in ("config.json", "outbox.log")})

    # ============================================================ general
    def __meta(self, _: dict) -> dict:
        carried, refused = self.__system.parcel_categories()
        return {"heading": self.__system.heading(),
                "now": f"{self.__system.now():%a %d %b %Y %H:%M}",
                "today": f"{self.__system.now():%Y-%m-%d}",
                "categories": carried, "refused": refused,
                "suburbs": self.__system.known_suburbs()}

    def __session_summary(self, _: dict) -> dict:
        return self.__session.summary()

    def __notifications(self, _: dict) -> list:
        return []      # notices are attached to every reply

    def __reset_demo(self, _: dict) -> dict:
        self.__workspace.reset()
        self.__system = DeliveryManagementSystem(self.__workspace,
                                                 self.__clock)
        self.__session = WebSession()
        return {"reset": True}

    def __track(self, payload: dict) -> dict:
        return Presenter.delivery(self.__system.track(payload["ref"]))

    def __sign_out(self, payload: dict) -> dict:
        self.__session.sign_out(payload.get("portal", ""))
        return self.__session.summary()

    # =========================================================== customer
    def __customer_sign_in(self, payload: dict) -> dict:
        customer = self.__system.find_customer(payload.get("key", ""))
        self.__session.sign_in_customer(customer)
        return Presenter.customer(customer)

    def __customer_register(self, payload: dict) -> dict:
        customer = self.__system.register_customer(
            payload.get("name", ""), payload.get("phone", ""),
            payload.get("email", ""), payload.get("channel", "SMS"))
        self.__session.sign_in_customer(customer)
        return Presenter.customer(customer)

    def __customer_home(self, _: dict) -> dict:
        customer = self.__session.customer()
        waiting = {r.request_id for r in
                   self.__system.quotes_awaiting(customer)}
        return {"customer": Presenter.customer(customer),
                "requests": [dict(Presenter.request(r),
                                  awaiting=r.request_id in waiting)
                             for r in reversed(
                                 self.__system.requests_of(customer))]}

    def __check_address(self, payload: dict) -> dict:
        address = self.__system.make_address(
            payload.get("street", ""), payload.get("suburb", ""),
            payload.get("postcode", ""), payload.get("instructions", ""))
        return Presenter.address(address)

    def __check_recipient(self, payload: dict) -> dict:
        recipient = self.__system.make_recipient(
            payload.get("name", ""), payload.get("phone", ""),
            payload.get("email", ""))
        return Presenter.contact(recipient.contact)

    def __check_parcel(self, payload: dict) -> dict:
        return Presenter.parcel(self.__parcel(payload))

    def __check_date(self, payload: dict) -> dict:
        chosen = self.__system.parse_preferred_date(payload.get("date", ""))
        return {"date": f"{chosen:%Y-%m-%d}", "label": f"{chosen:%a %d %b}"}

    def __submit_request(self, payload: dict) -> dict:
        if payload.get("as_office"):
            officer = self.__session.officer()
            customer, actor = self.__session.walk_in(), officer.staff_id
        else:
            customer = self.__session.customer()
            actor = customer.customer_id
        system = self.__system
        pickup = system.make_address(**self.__address_fields(
            payload["pickup"]))
        dropoff = system.make_address(**self.__address_fields(
            payload["dropoff"]))
        recipient = system.make_recipient(
            payload["recipient"].get("name", ""),
            payload["recipient"].get("phone", ""),
            payload["recipient"].get("email", ""))
        parcels = [self.__parcel(p) for p in payload.get("parcels", [])]
        preferred = system.parse_preferred_date(payload.get("date", ""))
        request = system.submit_request(customer, pickup, dropoff,
                                        recipient, parcels, preferred,
                                        actor)
        return Presenter.request(request)

    def __respond_quote(self, payload: dict) -> dict:
        customer = self.__session.customer()
        self.__system.respond_to_quote(customer, payload["request"],
                                       bool(payload.get("accept")))
        request = next(r for r in self.__system.requests_of(customer)
                       if r.request_id == payload["request"])
        return Presenter.request(request)

    # ============================================================= office
    def __office_sign_in(self, payload: dict) -> dict:
        officer = self.__system.login_office(payload.get("staff_id", ""))
        self.__session.sign_in_officer(officer)
        return self.__session.summary()

    def __office_home(self, _: dict) -> dict:
        officer = self.__session.officer()
        system = self.__system
        home = {
            "review": [Presenter.request(r)
                       for r in system.requests_for_review(officer)],
            "open_quotes": [Presenter.request(r)
                            for r in system.open_quotes(officer)],
            "unallocated": [dict(Presenter.delivery(d, True),
                                 urgent=urgent)
                            for d, urgent in system.unallocated(officer)],
            "cash": [{"staff": Presenter.staff(s),
                      "total": Presenter.money(sum(p.amount for p in cash)),
                      "count": len(cash)}
                     for s, cash in system.cash_holders(officer)],
            "owner": officer.is_owner,
        }
        if officer.is_owner:
            home["staff"] = [dict(Presenter.staff(s), open_jobs=jobs)
                             for s, jobs in system.staff_overview(officer)]
        return home

    def __walk_in(self, payload: dict) -> dict:
        self.__session.officer()
        customer = self.__system.lookup_customer(payload.get("key", ""))
        if customer is None:
            customer = self.__system.register_customer(
                payload.get("name", ""), payload.get("key", ""), "", "SMS",
                has_login=False)
        self.__session.choose_walk_in(customer)
        return Presenter.customer(customer)

    def __manual_quote(self, payload: dict) -> dict:
        return Presenter.request(self.__system.manual_quote(
            self.__session.officer(), payload["request"],
            payload.get("amount", ""), payload.get("reason", "")))

    def __reject_request(self, payload: dict) -> dict:
        self.__system.reject_request(self.__session.officer(),
                                     payload["request"],
                                     payload.get("reason", ""))
        return {"rejected": payload["request"]}

    def __override_quote(self, payload: dict) -> dict:
        return Presenter.request(self.__system.override_quote(
            self.__session.officer(), payload["request"],
            payload.get("amount", ""), payload.get("reason", "")))

    def __candidates(self, payload: dict) -> list:
        return [Presenter.staff(s) for s in self.__system.candidates_for(
            self.__session.officer(), payload["ref"])]

    def __allocate(self, payload: dict) -> dict:
        allocation = self.__system.allocate(self.__session.officer(),
                                            payload["ref"],
                                            payload["staff_id"])
        return {"allocation": allocation.allocation_id,
                "driver": allocation.staff.contact.name}

    def __reconcile(self, payload: dict) -> dict:
        payments = self.__system.reconcile_cash(self.__session.officer(),
                                                payload["staff_id"])
        return {"count": len(payments),
                "total": Presenter.money(sum(p.amount for p in payments))}

    def __track_staff(self, payload: dict) -> dict:
        self.__session.officer()
        return Presenter.delivery(self.__system.track(payload["ref"]),
                                  staff_view=True)

    def __statistics(self, payload: dict) -> dict:
        report = self.__system.statistics(
            self.__session.officer(), payload.get("kind", ""),
            payload.get("date", ""), payload.get("staff_id", ""))
        return Presenter.report(report)

    def __add_driver(self, payload: dict) -> dict:
        return Presenter.staff(self.__system.add_driver(
            self.__session.officer(), payload.get("name", ""),
            payload.get("phone", ""), payload.get("email", "")))

    def __deactivate_driver(self, payload: dict) -> dict:
        released = self.__system.deactivate_driver(
            self.__session.officer(), payload["staff_id"])
        return {"released": len(released)}

    # ============================================================= driver
    def __driver_sign_in(self, payload: dict) -> dict:
        driver = self.__system.login_driver(payload.get("staff_id", ""))
        self.__session.sign_in_driver(driver,
                                      self.__system.device_queue(driver))
        return self.__session.summary()

    def __driver_home(self, _: dict) -> dict:
        driver, queue = self.__session.driver(), self.__session.queue()
        now = self.__system.now()
        return {"driver": Presenter.staff(driver),
                "online": queue.online,
                "pending": [a.label() for a in queue.pending],
                "periods": [Presenter.period(p) for p in driver.availability
                            if p.is_current(now)],
                "jobs": [Presenter.job(a)
                         for a in self.__system.jobs_of(driver)]}

    def __declare(self, payload: dict) -> dict:
        return Presenter.period(self.__system.declare_availability(
            self.__session.driver(), payload.get("day", ""),
            payload.get("start", ""), payload.get("end", ""),
            bool(payload.get("weekly"))))

    def __change_period(self, payload: dict) -> dict:
        return Presenter.period(self.__system.change_availability(
            self.__session.driver(), payload["period"],
            payload.get("day", ""), payload.get("start", ""),
            payload.get("end", "")))

    def __withdraw(self, payload: dict) -> dict:
        return Presenter.period(self.__system.withdraw_availability(
            self.__session.driver(), payload["period"]))

    def __acknowledge(self, payload: dict) -> dict:
        allocation = self.__system.acknowledge(self.__session.driver(),
                                               payload["ref"])
        return {"ref": payload["ref"], "status": allocation.status.value}

    def __set_online(self, payload: dict) -> dict:
        queue = self.__session.queue()
        if payload.get("online"):
            queue.go_online()
            return {"online": True, "uploaded": self.__upload(queue)}
        queue.go_offline()
        return {"online": False, "uploaded": []}

    def __field(self, payload: dict) -> dict:
        driver, queue = self.__session.driver(), self.__session.queue()
        action = self.__system.new_field_action(
            driver, FieldActionKind[payload["kind"]], payload["ref"],
            payload.get("data", {}), queue.online)
        if not queue.online:
            queue.enqueue(action)
            return {"queued": True, "message":
                    f"No signal: saved on this phone at "
                    f"{action.device_time:%H:%M:%S}. "
                    f"{len(queue.pending)} action(s) waiting to upload."}
        return {"queued": False,
                "message": self.__system.perform_field_action(action)}

    def __sync(self, _: dict) -> dict:
        return {"uploaded": self.__upload(self.__session.queue())}

    # ============================================================ helpers
    def __upload(self, queue) -> list:
        return [{"action": action.label(), "message": message, "ok": ok}
                for action, message, ok in
                queue.flush(self.__system.perform_field_action)]

    def __parcel(self, raw: dict):
        return self.__system.make_parcel(
            raw.get("description", ""), raw.get("category", ""),
            raw.get("length", ""), raw.get("width", ""),
            raw.get("height", ""), raw.get("weight", ""))

    @staticmethod
    def __address_fields(raw: dict) -> dict:
        return {"street": raw.get("street", ""),
                "suburb": raw.get("suburb", ""),
                "postcode": raw.get("postcode", ""),
                "instructions": raw.get("instructions", "")}
