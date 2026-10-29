"""YOWD Delivery Management System (SWE30003 Assignment 3, Group 5).

The package is organised in four layers:

* ``yowd.ui``          - presentation layer (text-based console screens)
* ``yowd.app``         - application layer (the DeliveryManagementSystem
                         facade and the bootstrap process)
* ``yowd.domain``      - domain layer (business classes from the design)
* ``yowd.services`` /
  ``yowd.persistence`` /
  ``yowd.config``      - infrastructure (external service adapters,
                         JSON storage and business configuration)
"""

__version__ = "1.0.0"
