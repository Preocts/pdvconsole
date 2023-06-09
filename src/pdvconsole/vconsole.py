"""VConsole class for the pdvconsole package."""
from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncGenerator
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from secretbox import SecretBox

from .kbhit import KeyboardListener

secrets = SecretBox(auto_load=True)

MIN_DISPLAY_ROWS = 5
PANEL_OFFSET = 6  # Number of rows used by the header and footer
# Time between PagerDuty API calls in seconds
POLL_TIME_SECONDS = int(secrets.get("POLL_TIME_SECONDS", "60"))
POLL_LIMIT = 25  # Number of incidents to return per API call

INCIDENT_ROW = (
    "{assigned:^3}|{status:^6}|{urgency:^6}|{priority:^4}|{duration:>4.0f}m | {title}"
)


class SortBy(Enum):
    """Enum for sorting incidents."""

    CREATED_AT = 0
    PRIORITY = 1
    URGENCY = 2


@dataclasses.dataclass(frozen=True)
class Incident:
    """Incident class."""

    pdid: str
    title: str
    urgency: str
    status: str
    priority: str
    created_at: str
    self_assigned: bool
    last_seen: datetime = dataclasses.field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, incident: dict[str, Any]) -> Incident:
        """Create an Incident from a dict."""
        priority = incident.get("priority") or {}
        return cls(
            pdid=incident["id"],
            title=incident["title"],
            urgency=incident["urgency"],
            status=incident["status"],
            created_at=incident["created_at"],
            priority=priority.get("summary", ""),
            self_assigned=Incident._is_assigned(incident),
        )

    @staticmethod
    def _is_assigned(incident: dict[str, Any]) -> bool:
        """Return True if the incident is assigned to the user."""
        assignments = incident.get("assignments", [])
        ids = {assignment["assignee"]["id"] for assignment in assignments}
        return secrets.get("PAGERDUTY_USER_ID") in ids


@dataclasses.dataclass(frozen=True)
class Priority:
    """Priority class."""

    index: int
    pdid: str
    name: str


class VConsole:
    """VConsole class for the pdvconsole package."""

    def __init__(self) -> None:
        """Initialize the VConsole."""
        self.last_updated: str = datetime.now().strftime("%H:%M:%S")
        self.update_interval: int = POLL_TIME_SECONDS
        self.total_incidents: int = 0
        self.total_triggered: int = 0
        self.total_acknowledged: int = 0
        self.total_assigned: int = 0
        self._incidents: dict[str, Incident] = {}
        self.priorities: list[Priority] = []
        self.priority_filter: str | None = None
        self.urgency_filter: str | None = None
        self.sort_by: SortBy = SortBy.CREATED_AT
        self.reverse: bool = False

    @property
    def incidents(self) -> list[Incident]:
        """Return a list of incidents."""
        incidents_ = list(self._incidents.values())

        if self.priority_filter:
            incidents_ = [
                incident
                for incident in incidents_
                if incident.priority == self.priority_filter
            ]

        if self.urgency_filter:
            incidents_ = [
                incident
                for incident in incidents_
                if incident.urgency == self.urgency_filter
            ]

        incidents_ = sorted(incidents_, key=self._sort_key)

        return incidents_ if not self.reverse else incidents_[::-1]

    def _sort_key(self, incident: Incident) -> tuple[Any, ...]:
        """Return a tuple of sort keys."""
        # Sort by priority and created_at
        if self.sort_by == SortBy.PRIORITY:
            return (incident.priority, incident.created_at)

        # Sort by urgency and created_at
        elif self.sort_by == SortBy.URGENCY:
            return (incident.urgency, incident.created_at)

        # Sort by created_at by default
        else:
            return (incident.created_at,)

    def update(self, incident: Incident) -> None:
        """Update the VConsole."""
        self._incidents[incident.pdid] = incident

    def clean(self) -> None:
        """Remove incidents not updated after the POLL_TIME_SECONDS parameter."""
        now = datetime.now()
        for incident in list(self._incidents.values()):
            if (now - incident.last_seen).seconds > self.update_interval:
                del self._incidents[incident.pdid]

    def update_counts(self) -> None:
        """Update the incident counts."""
        self.total_incidents = len(self.incidents)
        self.total_triggered = len(
            [inc for inc in self.incidents if inc.status == "triggered"]
        )
        self.total_acknowledged = len(
            [inc for inc in self.incidents if inc.status == "acknowledged"]
        )
        self.total_assigned = len([inc for inc in self.incidents if inc.self_assigned])

    def on_press(self, key: str) -> bool:
        """Handle key presses."""
        # Filter by priority
        if key in list("1234567890"):
            pri_map = {p.index: p.name for p in self.priorities}
            # toggle filter if already selected
            if pri_map.get(int(key)) == self.priority_filter:
                self.priority_filter = None
            else:
                self.priority_filter = pri_map.get(int(key))

        # Filter by urgency
        if key.lower() in "hla":
            self.urgency_filter = {"h": "high", "l": "low", "a": None}.get(key)

        # Rotate SortBy enum selected
        if key.lower() == "s":
            self.sort_by = SortBy((self.sort_by.value + 1) % len(SortBy))

        # Reverse sort order
        if key.lower() == "r":
            self.reverse = not self.reverse

        # Quit
        if key.lower() == "q":
            return False

        return True


async def get_priorities() -> list[Priority]:
    """Get priorities."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.pagerduty+json;version=2",
        "Authorization": f"Token token={secrets.get('PAGERDUTY_TOKEN')}",
    }

    url = "https://api.pagerduty.com/priorities"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

    priorities = []
    for idx, pri in enumerate(resp.json()["priorities"], start=1):
        priorities.append(Priority(index=idx, pdid=pri["id"], name=pri["name"]))

    return priorities


async def fetch_incidents() -> AsyncGenerator[Incident, None]:
    """Iterate through incidents."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.pagerduty+json;version=2",
        "Authorization": f"Token token={secrets.get('PAGERDUTY_TOKEN')}",
    }
    params = {
        "sort_by": "created_at:desc",
        "statuses[]": ["triggered", "acknowledged"],
        "time_zone": "UTC",
        "limit": str(POLL_LIMIT),
        "offset": "0",
    }
    url = "https://api.pagerduty.com/incidents"

    more = True
    async with httpx.AsyncClient() as client:
        while more:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            for inc in resp.json()["incidents"]:
                yield Incident.from_dict(inc)

            more = resp.json().get("more", False)
            params["offset"] = str(int(resp.json().get("offset", "0")) + POLL_LIMIT)


def vlayout() -> Layout:
    """VConsole class for the pdvconsole package."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=2),
        Layout(name="body", ratio=1, minimum_size=MIN_DISPLAY_ROWS),
        Layout(name="footer", size=2),
    )
    layout["body"].split_row(
        Layout(name="incidents", ratio=3, minimum_size=MIN_DISPLAY_ROWS),
        Layout(name="details"),
    )

    return layout


def render_incident_panel(pd_details: VConsole, panel_height: int) -> Panel:
    """Incident Panel."""
    if len(pd_details.incidents) > panel_height:
        # -1 for the hidden count line
        incidents_ = pd_details.incidents[: panel_height - 1]
        hidden_count = len(pd_details.incidents) - panel_height + 1
    else:
        hidden_count = 0
        incidents_ = pd_details.incidents

    pd_details.update_counts()
    string_version = []
    for incident in incidents_:
        created_at = datetime.strptime(incident.created_at, "%Y-%m-%dT%H:%M:%SZ")
        open_duration = datetime.utcnow() - created_at
        string_version.append(
            INCIDENT_ROW.format(
                assigned="X" if incident.self_assigned else "",
                status=incident.status[:4],
                urgency=incident.urgency,
                priority=incident.priority,
                duration=abs(open_duration.total_seconds() / 60),
                pdid=incident.pdid,
                title=incident.title,
            )
        )

    if hidden_count:
        string_version.append(f"... {hidden_count} more incidents hidden ...")

    text = Text.assemble("\n".join(string_version), overflow="ellipsis", no_wrap=True)

    return Panel(text, title="Incidents", expand=True)


def render_details_panel(pd_details: VConsole) -> Panel:
    """Details Panel."""
    text = Text.assemble(
        f"Current time:\n\t{datetime.now().strftime('%H:%M:%S')}\n"
        f"Last updated:\n\t{pd_details.last_updated}\n",
        f"Update interval:\n\t{pd_details.update_interval} seconds\n"
        f"Total incidents:\n\t{pd_details.total_incidents}\n",
        f"Triggered:\n\t{pd_details.total_triggered}\n",
        f"Acknowledged:\n\t{pd_details.total_acknowledged}\n",
        f"Assigned:\n\t{pd_details.total_assigned}\n",
        f"Sorted by:\n\t{pd_details.sort_by.name}\n",
        f"Priority filter:\n\t{pd_details.priority_filter}\n",
        f"Urgency filter:\n\t{pd_details.urgency_filter}\n",
    )

    return Panel(text, title="Details", expand=True)


def calc_max_height(console: Console) -> int:
    """Calculate the max height of the incident panel."""
    max_height = (
        console.size.height - PANEL_OFFSET
        if console.size.height > MIN_DISPLAY_ROWS
        else MIN_DISPLAY_ROWS
    )
    return max_height


async def fetch_priorities(pd_details: VConsole) -> None:
    """Fetch the priorities."""
    pd_details.last_updated = "Fetching priorities..."
    pd_details.priorities = await get_priorities()


async def update_pd_details(pd_details: VConsole) -> None:
    """Update the pd_details object."""
    first_run = True

    while True:
        if not first_run:
            pd_details.clean()
            pd_details.last_updated = datetime.now().strftime("%H:%M:%S")
            await asyncio.sleep(POLL_TIME_SECONDS)

        first_run = False
        pd_details.last_updated = "Updating..."

        # Fetch the incidents using a generator and update the pd_details object
        async for incident in fetch_incidents():
            pd_details.update(incident)


async def render_vconsole(console: Console, pd_details: VConsole) -> None:
    """Render the VConsole."""
    layout = vlayout()
    layout["header"].update("")
    layout["footer"].update("")

    with Live(layout, refresh_per_second=4, screen=True):
        while True:
            mxh = calc_max_height(console)

            layout["incidents"].update(render_incident_panel(pd_details, mxh))
            layout["details"].update(render_details_panel(pd_details))

            await asyncio.sleep(0.2)


async def catch_stop(
    event_loop: asyncio.AbstractEventLoop,
    keyboard_listener: KeyboardListener,
) -> None:
    """Catch the stop event."""
    while keyboard_listener.is_listening:
        await asyncio.sleep(0.5)

    event_loop.stop()


def main() -> int:
    """Main entry point for the pdvconsole package."""
    console = Console(tab_size=2)
    pd_details = VConsole()
    keyboard_listener = KeyboardListener(on_press=pd_details.on_press)
    keyboard_listener.start()

    event_loop = asyncio.get_event_loop()
    event_loop.create_task(fetch_priorities(pd_details))
    event_loop.create_task(update_pd_details(pd_details))
    event_loop.create_task(render_vconsole(console, pd_details))
    event_loop.create_task(catch_stop(event_loop, keyboard_listener))
    event_loop.run_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
