"""VConsole class for the pdvconsole package."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from secretbox import SecretBox


MIN_DISPLAY_ROWS = 5
POLL_TIME_SECONDS = 10  # Time between PagerDuty API calls
POLL_LIMIT = 100  # Number of incidents to return per API call
secrets = SecretBox(auto_load=True)


@dataclass(frozen=True)
class Incident:
    """Incident class."""

    pdid: str
    title: str
    urgency: str
    status: str
    created_at: str

    @classmethod
    def from_dict(cls, incident: dict[str, Any]) -> Incident:
        """Create an Incident from a dict."""
        return cls(
            pdid=incident["id"],
            title=incident["title"],
            urgency=incident["urgency"],
            status=incident["status"],
            created_at=incident["created_at"],
        )


async def get_incidents(assigned_to: bool = False) -> list[Incident]:
    """
    Get incidents, sorted by created_at.

    If assigned_to is True, only incidents assigned to the user will be returned.
    """
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
    if assigned_to:
        params["user_ids[]"] = [secrets.get("PAGERDUTY_USER_ID")]

    more = True
    incidents: list[Incident] = []
    async with httpx.AsyncClient() as client:
        while more:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            incidents.extend(
                [Incident.from_dict(incident) for incident in resp.json()["incidents"]]
            )
            more = resp.json().get("more", False)
            params["offset"] = str(int(resp.json().get("offset", "0")) + POLL_LIMIT)

    return incidents


def vlayout() -> Layout:
    """VConsole class for the pdvconsole package."""
    layout = Layout()
    layout.split_row(
        Layout(name="incidents", ratio=3),
        Layout(name="details"),
    )

    return layout


def incident_panel(incidents: list[Incident], panel_height: int) -> Panel:
    """Incident Panel."""
    if len(incidents) > panel_height:
        incidents_ = incidents[: panel_height - 1]  # -1 for the hidden count
        hidden_count = len(incidents) - panel_height + 1
    else:
        hidden_count = 0
        incidents_ = incidents

    string_version = []
    for incident in incidents_:
        created_at = datetime.strptime(incident.created_at, "%Y-%m-%dT%H:%M:%SZ")
        open_duration = datetime.utcnow() - created_at
        string_version.append(
            f"{incident.status.upper()[0:4]:^6}|{incident.urgency.upper()[0:4]:^6}|"
            f"{open_duration.total_seconds() // 60:>6.0f}m | {incident.title}"
        )

    if hidden_count:
        string_version.append(f"... {hidden_count} more incidents hidden ...")

    return Panel("\n".join(string_version), title="Incidents", expand=True)


def details_panel() -> Panel:
    """Details Panel."""
    return Panel("Details", title="Details", expand=True)


def calc_max_height(console: Console) -> int:
    """Calculate the max height of the incident panel."""
    max_height = (
        console.size.height - 5
        if console.size.height > MIN_DISPLAY_ROWS
        else MIN_DISPLAY_ROWS
    )
    return max_height


async def update_incidents(console: Console, layout: Layout) -> None:
    """Update the incidents panel."""
    incidents = await get_incidents(assigned_to=True)
    max_height = calc_max_height(console)
    incidents = await get_incidents()
    layout["incidents"].update(incident_panel(incidents, max_height))


async def main(console: Console) -> int:
    """Main entry point for the pdvconsole package."""
    tic = datetime.now().timestamp()
    incidents: list[Incident] = []
    layout = vlayout()
    layout["incidents"].update(incident_panel(incidents, calc_max_height(console)))
    layout["details"].update(details_panel())

    try:
        with Live(layout, refresh_per_second=4, screen=True) as livedisplay:
            while True:
                toc = datetime.now().timestamp()
                if toc - tic > POLL_TIME_SECONDS:
                    tic = toc
                    await update_incidents(console, layout)
                    livedisplay.update(layout)

    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    console = Console()

    exit_code = asyncio.run(main(console))
    raise SystemExit(exit_code)
