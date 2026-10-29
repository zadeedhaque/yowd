# YOWD Delivery Management System (SWE30003 Assignment 3, Group 5)

The Delivery Management System designed in Assignment 2, written in
strictly object-oriented Python using only the standard library. There are
two front ends on the same domain code:

* a console program (`python main.py`), and
* a web UI for GitHub Pages that runs the same Python in the browser with
  Pyodide. There is no server, and each browser keeps its own data.

## Requirements

* Python 3.12 or newer (developed and tested with 3.13).
* No third-party packages are needed to run anything.
* `flake8` is only needed for the PEP 8 check.

## Running the console program

```
python main.py            # start (sample data is created on first run)
python main.py --reset    # delete saved records and start again
python tools/build_executable.py   # package as yowd_dms.pyz
```

Sample users:

| Role | ID / login |
|------|-----------|
| Owner (office staff with owner role) | S001 Maya Fernando |
| Office staff | S002 Josh Patel |
| Delivery staff | D001 Liam Nguyen, D002 Aisha Rahman, D003 Tom Walker |
| Customers | sarah.chen@example.com, orders@bellas.com.au, d.okafor@example.com |

## Running the web UI locally

```
python tools/build_web.py --pyodide   # builds ./site, bundling Pyodide
python -m http.server -d site 8000    # open http://localhost:8000
```

If you leave out `--pyodide`, the page loads Pyodide from the jsDelivr CDN
instead. The left rail switches between the Customer, Office, Driver and
Track portals. "Messages sent" shows every SMS, email and alert the system
would have sent. In the Driver portal, the Signal switch takes the phone
offline: actions are queued and then uploaded in order when the signal
comes back.

## Deploying to GitHub Pages

1. Push this folder to a GitHub repository (branch `main`).
2. In the repository, open **Settings → Pages** and set **Source** to
   **GitHub Actions**.
3. The workflow in `.github/workflows/pages.yml` runs flake8 and the unit
   tests, builds the site with `tools/build_web.py --pyodide`, and deploys
   it. The site address appears in the workflow run and on the Pages
   settings screen.

Pull requests run only the test job.

## Checking the build

```
flake8 .                    # PEP 8 check (settings in setup.cfg)
python -m unittest -v       # 65 unit and integration tests
```

## Object-oriented conventions

Python has no `interface` keyword and no private fields, so the code uses
these conventions throughout:

| Need | How it is done |
|------|----------------|
| Interfaces | Abstract base classes (`abc.ABC` with `@abstractmethod`) in `yowd/domain/ports.py`: `Clock`, `AddressService`, `PaymentGateway`, `DeliveryObserver`, `AvailabilityListener`, `MessageOutbox`, `TextStorage`, `RecordStore`. A class that does not implement every method cannot be instantiated. `add_observer` and `add_listener` reject objects that are not instances of the interface. |
| Private state | Name-mangled `__fields` (stored as `_ClassName__field`), exposed only through read-only `@property` getters. State changes only through methods that enforce the business rules, such as `Delivery.change_status`. |
| No stray attributes | `__slots__` on the domain classes, so a typo such as `delivery.statsu = ...` raises an error instead of creating a new attribute. |
| Immutable values | `@dataclass(frozen=True)` for value objects (`ContactDetails`, `TimeWindow`, `Receipt`, `DeliveryEvent`). Collections are returned as tuples and mappings as `MappingProxyType`. |
| Rebuilding from storage | `restore(...)` class methods recreate an object from saved data without going through the business-rule checks again, so the persistence layer never touches private fields. |
| Polymorphism | `FieldAction` is an abstract Command with a Template Method (`execute` runs the shared checks, then the subclass's `_apply`). Subclasses register themselves through `__init_subclass__`, and `FieldAction.create(kind, ...)` builds one by name. |

## Testing

Every external dependency is passed in through the constructor:

```python
system = DeliveryManagementSystem(
    MemoryWorkspace(config_text),   # no files are written
    clock=FixedClock(START),        # time only moves when the test says so
    payment_gateway=DecliningGateway(),  # any PaymentGateway subclass
)
```

`tests/support.py` provides the shared fixtures, so tests need no files,
network or real clock. `tests/test_object_design.py` checks the conventions
above: the interfaces, private fields, slots, the factory and the injected
fakes.

## Folder layout

```
main.py                   console entry point
data/config.json          business settings (pricing, area, statuses...)
yowd/domain/              business classes and the interfaces (ports.py)
yowd/services/            adapters: address, payment, outbox, storage
yowd/persistence/         Registry and JSON storage
yowd/config/              SystemConfiguration
yowd/app/                 facade (DeliveryManagementSystem), workspaces,
                          input parsing and sample data
yowd/ui/                  console screens
yowd/web/                 WebApi and Presenter used by the browser UI
web/                      static page: HTML, CSS and ES-module JavaScript
tools/                    build_web.py (site) and build_executable.py (.pyz)
tests/                    unittest suite
.github/workflows/        CI and GitHub Pages deployment
```

Files created at run time (`data/yowd_data.json`, `data/outbox.log`,
`data/device/`, `data/exports/`) and the built `site/` are ignored by git.
