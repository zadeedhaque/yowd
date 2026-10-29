"""Dispatcher: matches work waiting to be done with free drivers.

Pure fabrication (A2 CRC 4.17) and AvailabilityListener (Observer of
DeliveryStaff).  Office staff still make the final allocation decision.
"""

from datetime import date, datetime, time, timedelta

from yowd.domain.allocation import Allocation
from yowd.domain.clock import MELBOURNE
from yowd.domain.errors import BusinessRuleError
from yowd.domain.ports import AvailabilityListener, Clock
from yowd.domain.statuses import DeliveryStatus
from yowd.domain.values import TimeWindow


class Dispatcher(AvailabilityListener):
    """Lists unallocated work, finds free staff and creates allocations."""

    SEARCH_DAYS = 7
    __slots__ = ("__registry", "__config", "__clock", "__notifier")

    def __init__(self, registry, config, clock: Clock, notifier) -> None:
        self.__registry = registry
        self.__config = config
        self.__clock = clock
        self.__notifier = notifier

    # ---------------------------------------------------------- listing
    def unallocated(self) -> list[tuple[object, bool]]:
        """Accepted deliveries in pickup order with an 'urgent' flag."""
        now = self.__clock.now()
        urgent_by = now + timedelta(
            hours=self.__config.time_limit("urgent_within_hours"))
        waiting = [d for d in self.__registry.deliveries()
                   if d.status is DeliveryStatus.ACCEPTED]
        waiting.sort(key=lambda d: d.quote.pickup_window.start)
        return [(d, d.quote.pickup_window.start <= urgent_by)
                for d in waiting]

    def available_staff(self, window: TimeWindow) -> list:
        """Active drivers whose availability covers the window and who
        have no other active job overlapping it."""
        free = []
        for staff in self.__registry.active_delivery_staff():
            if not staff.is_available_for(window):
                continue
            busy = any(a.window.overlaps(window)
                       for a in self.__registry.active_allocations_for(
                           staff.staff_id))
            if not busy:
                free.append(staff)
        return free

    def estimate_pickup_window(self, preferred: date,
                               now: datetime) -> TimeWindow:
        """Earliest window on/after the preferred date a driver can do.

        Searches hour by hour from max(preferred 08:00, now + lead time)
        for up to a week.  If nobody is free the next-day 09:00 window
        is returned and the office confirms it when allocating.
        """
        length = timedelta(hours=self.__config.time_limit(
            "pickup_window_hours"))
        earliest = now + timedelta(hours=self.__config.time_limit(
            "lead_time_hours"))
        start = max(datetime.combine(preferred, time(8, 0), MELBOURNE),
                    earliest)
        start = (start + timedelta(minutes=59)).replace(minute=0, second=0)
        for step in range(self.SEARCH_DAYS * 24):
            candidate = TimeWindow(start + timedelta(hours=step),
                                   start + timedelta(hours=step) + length)
            if 8 <= candidate.start.hour <= 18 and \
                    self.available_staff(candidate):
                return candidate
        fallback = datetime.combine(start.date() + timedelta(days=1),
                                    time(9, 0), MELBOURNE)
        return TimeWindow(fallback, fallback + length)

    # ------------------------------------------------------- allocating
    def allocate(self, delivery, staff, officer) -> Allocation:
        """Create an Allocation and move the delivery to Scheduled."""
        if delivery.status is not DeliveryStatus.ACCEPTED:
            raise BusinessRuleError(
                f"{delivery.tracking_ref} is {delivery.status.value}; only "
                "deliveries awaiting allocation can be allocated.")
        window = delivery.quote.pickup_window
        if staff not in self.available_staff(window):
            raise BusinessRuleError(
                f"{staff.contact.name} is not available for "
                f"{window.label()}. Choose someone from the list.")
        now = self.__clock.now()
        allocation = Allocation(self.__registry.next_id("A"), delivery,
                                staff, window, officer.staff_id, now)
        delivery.add_allocation(allocation)
        delivery.change_status(DeliveryStatus.SCHEDULED, officer.staff_id,
                               now, now, f"Allocated to {staff.staff_id} "
                               f"{staff.contact.name}")
        self.__notifier.send(staff.contact, "Allocation",
                             ref=delivery.tracking_ref,
                             window=window.label())
        return allocation

    def check_acknowledgements(self) -> list[Allocation]:
        """Revoke offers not acknowledged in time; alert the office."""
        now = self.__clock.now()
        timeout = self.__config.time_limit("ack_timeout_minutes")
        revoked = []
        for delivery in self.__registry.deliveries():
            allocation = delivery.current_allocation
            if allocation is not None and allocation.is_overdue(now,
                                                                timeout):
                self.__release(allocation, f"not acknowledged within "
                               f"{timeout} minutes", "SYSTEM")
                revoked.append(allocation)
        return revoked

    # ------------------------------------------------ observer callback
    def availability_withdrawn(self, staff, period) -> None:
        """Return affected deliveries to the unallocated list (Task 4)."""
        for allocation in self.__registry.active_allocations_for(
                staff.staff_id):
            if allocation.delivery.status is DeliveryStatus.SCHEDULED \
                    and period.covers(allocation.window) \
                    and not staff.is_available_for(allocation.window):
                self.__release(allocation, f"{staff.contact.name} withdrew "
                               "availability", staff.staff_id)

    def staff_deactivated(self, staff, actor_id: str) -> list[Allocation]:
        """Release every open job of a leaver (Task 10)."""
        released = []
        for allocation in self.__registry.active_allocations_for(
                staff.staff_id):
            if allocation.delivery.status is DeliveryStatus.SCHEDULED:
                self.__release(allocation, f"{staff.contact.name} left the "
                               "business", actor_id)
                released.append(allocation)
        return released

    def __release(self, allocation, reason: str, actor_id: str) -> None:
        now = self.__clock.now()
        allocation.revoke(now, reason)
        delivery = allocation.delivery
        if delivery.status is DeliveryStatus.SCHEDULED:
            delivery.change_status(DeliveryStatus.ACCEPTED, actor_id, now,
                                   now, f"Allocation revoked: {reason}")
        self.__notifier.notify_office(
            "Reallocate", ref=delivery.tracking_ref, reason=reason)
